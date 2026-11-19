"""Tool local: validacion determinista de una orden de compra y emision del ticket.

Flujo de una orden (defensa en profundidad):
  1. preparar_orden      -> el CODIGO valida perfil, limites y poder de compra; emite un ticket.
  2. place_stock_order   -> herramienta MCP de Alpaca; el framework exige aprobacion humana.
  3. middleware          -> justo antes de ejecutar, verifica que la llamada coincide con el ticket
                            (mismo simbolo y cantidad, solo compra a mercado) y lo marca como usado.
"""
from __future__ import annotations

import secrets
import time
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from advisor import runtime
from advisor.policy import evaluate_order, policies
from advisor.state import LEDGER, current_turn

TICKET_TTL_SECONDS = 600


@tool(approval_mode="never_require")
async def preparar_orden(
    simbolo: Annotated[str, Field(description="Ticker a comprar, p. ej. MSFT")],
    cantidad: Annotated[int, Field(description="Numero entero de acciones a comprar", gt=0)],
) -> dict:
    """PASO OBLIGATORIO antes de cualquier compra. Valida la orden contra el perfil de riesgo del cliente, los
    limites de la politica interna y el poder de compra, usando el precio actual del mercado. Si es valida,
    devuelve un ticket y el resumen que debes mostrar al usuario; despues llama a place_stock_order con el mismo
    simbolo y cantidad (side='buy', type='market', time_in_force='day'). Si no es valida, explica los motivos y
    NO intentes colocar la orden."""
    turn = current_turn()
    turn.data_calls += 1
    symbol = simbolo.upper().strip()
    client_id = turn.state.client_id

    if symbol not in policies()["universo"]:
        res = evaluate_order(client_id, symbol, cantidad, 0.0, LEDGER.holdings(client_id), 0.0)
        return {"valida": False, "simbolo": symbol, "cantidad": cantidad, "validaciones": res["validaciones"]}

    snapshot = (await runtime.alpaca_data("get_stock_snapshot", symbols=symbol, feed="iex")).get(symbol) or {}
    price = (snapshot.get("latestTrade") or {}).get("p") or (snapshot.get("dailyBar") or {}).get("c")
    if not price:
        return {"valida": False, "simbolo": symbol, "error": "No se pudo obtener el precio de mercado."}
    account = await runtime.alpaca_data("get_account_info")
    clock = await runtime.alpaca_data("get_clock")
    # Sin apalancamiento: se usa el poder de compra no marginable.
    broker_bp = min(float(account.get("non_marginable_buying_power", 0)), float(account.get("buying_power", 0)))

    res = evaluate_order(client_id, symbol, cantidad, float(price), LEDGER.holdings(client_id), broker_bp)
    out = {
        "valida": res["valida"],
        "resumen_de_la_orden": {
            "operacion": "COMPRA", "simbolo": symbol, "cantidad": cantidad, "tipo": "market", "vigencia": "day",
            "precio_referencia_usd": float(price), "monto_estimado_usd": res["monto_estimado_usd"],
            "modo": "paper trading (simulado, sin dinero real)",
        },
        "validaciones": res["validaciones"],
        "mercado": {
            "abierto": bool(clock.get("is_open")), "proxima_apertura": clock.get("next_open"),
            "nota": None if clock.get("is_open") else
            "Mercado cerrado: la orden quedara ACEPTADA y en cola; se ejecutara en la proxima apertura.",
        },
    }
    if res["valida"]:
        ticket_id = f"asesoria-{turn.state.session_id[:24]}-{secrets.token_hex(4)}"
        turn.state.tickets[ticket_id] = {
            "ticket_id": ticket_id, "symbol": symbol, "qty": cantidad, "price": float(price),
            "monto": res["monto_estimado_usd"], "validaciones": res["validaciones"], "mercado": out["mercado"],
            "expires": time.time() + TICKET_TTL_SECONDS, "estado": "validado",
        }
        out["ticket_id"] = ticket_id
        out["llamada_exacta_place_stock_order"] = {
            "symbol": symbol, "side": "buy", "qty": str(cantidad), "type": "market",
            "time_in_force": "day", "client_order_id": ticket_id}
        out["siguiente_paso"] = ("Llama ahora a place_stock_order con EXACTAMENTE los argumentos de "
                                 "'llamada_exacta_place_stock_order'. El sistema pedira la confirmacion humana.")
    else:
        out["siguiente_paso"] = "Orden BLOQUEADA. Explica al usuario las validaciones que fallaron. No coloques la orden."
    return out
