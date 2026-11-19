"""Middleware de funciones: trazabilidad de cada herramienta y guardrails deterministas.

Se ejecuta para TODAS las herramientas (locales y MCP), justo antes de su ejecucion real
(en el caso de la orden, despues de la aprobacion humana).
"""
from __future__ import annotations

import json
import time
from typing import Any

from agent_framework import FunctionInvocationContext, function_middleware
from pydantic import BaseModel

from advisor.config import ALPACA_ALLOWED_TOOLS, ALPACA_ORDER_TOOL
from advisor.runtime import mcp_text
from advisor.state import LEDGER, TURN, log_event

MAX_RESULT_CHARS = 6000
ORDER_FORBIDDEN_ARGS = ("notional", "limit_price", "stop_price", "order_class", "advanced_instructions",
                        "trail_percent", "trail_price", "take_profit_limit_price",
                        "stop_loss_stop_price", "stop_loss_limit_price")


def _args(context: FunctionInvocationContext) -> dict[str, Any]:
    a = context.arguments
    return a.model_dump() if isinstance(a, BaseModel) else dict(a or {})


def _set_args(context: FunctionInvocationContext, **updates: Any) -> None:
    a = context.arguments
    context.arguments = a.model_copy(update=updates) if isinstance(a, BaseModel) else {**dict(a or {}), **updates}


def find_ticket(tickets: dict[str, dict], args: dict[str, Any]) -> tuple[dict | None, str | None]:
    """Valida los argumentos reales de place_stock_order contra un ticket vigente. Devuelve (ticket, motivo_de_bloqueo)."""
    if str(args.get("side", "")).lower() != "buy":
        return None, "Solo se permiten ordenes de COMPRA (side='buy')."
    if str(args.get("type") or "market").lower() != "market" or str(args.get("time_in_force") or "day").lower() != "day":
        return None, "Solo se permiten ordenes a mercado con vigencia 'day'."
    if args.get("extended_hours"):
        return None, "No se permiten ordenes en horario extendido."
    usados = [k for k in ORDER_FORBIDDEN_ARGS if args.get(k) not in (None, "", {})]
    if usados:
        return None, f"Parametros no permitidos en la orden: {usados}."
    try:
        qty = float(args.get("qty"))
    except (TypeError, ValueError):
        return None, "La orden debe indicar una cantidad entera de acciones (qty)."
    symbol = str(args.get("symbol", "")).upper().strip()
    coid = args.get("client_order_id")
    for t in tickets.values():
        if t["estado"] == "validado" and t["expires"] > time.time() and t["symbol"] == symbol and float(t["qty"]) == qty:
            if coid and coid != t["ticket_id"]:
                continue   # si se indica id de cliente, debe ser el del ticket (idempotencia y trazabilidad)
            return t, None
    return None, (f"No existe una validacion vigente para comprar {qty:g} {symbol}. "
                  "Llama primero a preparar_orden con el mismo simbolo y cantidad.")


@function_middleware
async def audit_and_guard(context: FunctionInvocationContext, call_next) -> None:
    turn = TURN.get()
    name = context.function.name
    args = _args(context)
    started = time.time()
    ticket = None

    def record(status: str, result: Any) -> None:
        text = result if isinstance(result, str) else mcp_text(result) if isinstance(result, list) else \
            json.dumps(result, ensure_ascii=False, default=str)
        log_event(turn, {"event": "tool_call", "tool": name, "origen": "mcp" if name in ALPACA_ALLOWED_TOOLS else "local",
                         "status": status, "args": args, "result": text[:MAX_RESULT_CHARS],
                         "ms": int((time.time() - started) * 1000)})

    # ---- Guardrails previos a la ejecucion ----
    if name == ALPACA_ORDER_TOOL:
        ticket, motivo = find_ticket(turn.state.tickets if turn else {}, args)
        if ticket is None:
            context.result = f"ORDEN BLOQUEADA por politica: {motivo}"
            record("blocked", context.result)
            return
        # Los argumentos NO se tocan: el framework impide que cambien despues de la aprobacion
        # (lo que el humano aprobo es exactamente lo que se ejecuta).
        ticket["estado"] = "enviado"
    elif name in ("get_stock_snapshot", "get_stock_bars"):
        updates: dict[str, Any] = {"feed": "iex"}            # la cuenta gratuita solo tiene el feed IEX
        if name == "get_stock_bars":
            updates["limit"] = min(int(args.get("limit") or 1000), 130)
        _set_args(context, **updates)
        args = _args(context)
    elif name == "get_news":
        _set_args(context, limit=min(int(args.get("limit") or 5), 8), include_content=False)
        args = _args(context)

    if turn and name in ALPACA_ALLOWED_TOOLS:
        turn.data_calls += 1

    try:
        await call_next()
    except Exception as exc:
        record("error", f"{type(exc).__name__}: {exc}")
        raise

    # ---- Post-ejecucion ----
    if ticket is not None and turn is not None:
        text = mcp_text(context.result) if isinstance(context.result, list) else str(context.result)
        try:
            data = json.loads(text).get("data", {})
        except (json.JSONDecodeError, AttributeError):
            data = {}
        if data.get("id"):
            ticket.update(estado="ejecutado", order_id=data["id"], status=data.get("status"))
            LEDGER.add(turn.state.client_id, ticket["symbol"], ticket["qty"], ticket["monto"])
        else:
            ticket["estado"] = "error"
    record("ok", context.result)

    # Compactacion: de las barras historicas el modelo solo necesita fecha y cierre (menos tokens y latencia).
    if name == "get_stock_bars":
        compact = _compact_bars(context.result)
        if compact:
            context.result = compact


def _compact_bars(result: Any) -> str | None:
    try:
        bars = json.loads(mcp_text(result) if isinstance(result, list) else str(result))["data"]["bars"]
        out = {sym: {"desde": rows[0]["t"][:10], "hasta": rows[-1]["t"][:10], "n": len(rows),
                     "cierres": [r["c"] for r in rows]} for sym, rows in bars.items() if rows}
        return json.dumps({"fuente": "Alpaca (datos de mercado, feed IEX)", "barras_diarias": out,
                           "nota": "Cierres en orden cronologico; pasalos a calculadora_financiera(metricas_de_precios)."})
    except Exception:
        return None
