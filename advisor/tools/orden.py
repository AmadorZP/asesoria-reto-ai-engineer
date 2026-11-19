"""Tool local: validacion determinista de una orden de compra, advertencias y emision del ticket.

Flujo de una orden (defensa en profundidad):
  1. preparar_orden      -> el CODIGO valida. Reglas duras (dinero, universo, solo compra) bloquean.
                            Reglas suaves (limites recomendados del perfil) generan advertencias en DOS
                            pasos, cada uno en un turno distinto del usuario, antes de emitir el ticket.
  2. place_stock_order   -> herramienta MCP de Alpaca; el framework exige aprobacion humana.
  3. middleware          -> justo antes de ejecutar, verifica que la llamada coincide con el ticket.
"""
from __future__ import annotations

import secrets
import time
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from advisor import runtime
from advisor.policy import evaluate_order, policies
from advisor.profile import broker_buying_power, financials, has_profile
from advisor.state import current_turn, log_event

TICKET_TTL_SECONDS = 600


@tool(approval_mode="never_require")
async def preparar_orden(
    simbolo: Annotated[str, Field(description="Ticker a comprar, p. ej. MSFT")],
    cantidad: Annotated[int, Field(description="Numero entero de acciones a comprar", gt=0)],
    cliente_confirma_continuar: Annotated[bool, Field(description=(
        "True SOLO si, tras una advertencia tuya sobre esta misma orden, el cliente respondio en su ultimo "
        "mensaje que si quiere continuar. En la primera solicitud siempre es False."))] = False,
) -> dict:
    """PASO OBLIGATORIO antes de cualquier compra. Valida la orden con el precio real de mercado.
    Devuelve un campo 'estado':
    - 'requiere_perfil': falta el perfil del cliente; pidelo y registralo antes de seguir.
    - 'bloqueada': incumple un limite duro (dinero disponible, universo operable). Explica y detente.
    - 'advertencia_1' / 'advertencia_2': la orden excede los limites recomendados de su perfil. Sigue las
      instrucciones del resultado, pregunta si desea continuar y ESPERA su respuesta.
    - 'lista_para_confirmar': emite el ticket; llama a place_stock_order con los argumentos indicados."""
    turn = current_turn()
    state = turn.state
    turn.data_calls += 1
    symbol = simbolo.upper().strip()

    if not has_profile(state):
        return {"estado": "requiere_perfil",
                "instruccion": ("Antes de operar se necesita el perfil del cliente. Pidele de forma breve su capital "
                                "invertible y su perfil de riesgo (o cuanto toleraria perder y su horizonte) y llama a "
                                "registrar_perfil. Despues vuelve a preparar_orden.")}
    perfil = state.profile["perfil"]
    fin = await financials(state)

    if symbol not in policies()["universo"]:
        res = evaluate_order(perfil, fin["capital_total"], fin["capital_disponible"], symbol, cantidad, 0.0, fin["tenencias"], 0.0)
        return {"estado": "bloqueada", "simbolo": symbol, "cantidad": cantidad, "bloqueos": res["bloqueos"],
                "instruccion": "Explica que ese activo no esta en el universo operable. No coloques la orden."}

    snapshot = (await runtime.alpaca_data("get_stock_snapshot", symbols=symbol, feed="iex")).get(symbol) or {}
    price = (snapshot.get("latestTrade") or {}).get("p") or (snapshot.get("dailyBar") or {}).get("c")
    if not price:
        return {"estado": "bloqueada", "simbolo": symbol, "error": "No se pudo obtener el precio de mercado."}
    clock = await runtime.alpaca_data("get_clock")
    res = evaluate_order(perfil, fin["capital_total"], fin["capital_disponible"], symbol, cantidad, float(price),
                         fin["tenencias"], await broker_buying_power())
    monto, capital = res["monto_estimado_usd"], fin["capital_total"]
    resumen = {"operacion": "COMPRA", "simbolo": symbol, "cantidad": cantidad, "tipo": "market", "vigencia": "day",
               "precio_referencia_usd": float(price), "monto_estimado_usd": monto,
               "pct_del_capital": round(monto / capital * 100, 1) if capital else None,
               "modo": "paper trading (simulado, sin dinero real)"}
    mercado = {"abierto": bool(clock.get("is_open")), "proxima_apertura": clock.get("next_open"),
               "nota": None if clock.get("is_open") else
               "Mercado cerrado: la orden quedara ACEPTADA y en cola; se ejecutara en la proxima apertura."}
    out = {"resumen_de_la_orden": resumen, "perfil_del_cliente": perfil, "validaciones": res["validaciones"], "mercado": mercado}

    # ---- Limites duros: bloquean siempre, aunque el cliente insista.
    if res["bloqueos"]:
        return {"estado": "bloqueada", **out, "bloqueos": res["bloqueos"],
                "instruccion": ("Orden BLOQUEADA por un limite duro. Explica el motivo con las cifras (cuanto cuesta y cuanto "
                                "hay disponible) y, si aplica, sugiere una cantidad que si alcance. No coloques la orden.")}

    # ---- Limites recomendados del perfil: advertencia en dos pasos, cada uno en un turno distinto del usuario.
    key = f"{symbol}:{cantidad}"
    if res["advertencias"]:
        w = state.warnings.get(key)
        avanzar = bool(w) and cliente_confirma_continuar and state.turn_no > w["turno"]
        if w is None or not avanzar and w["etapa"] == 1:
            if w is None:
                state.warnings[key] = {"etapa": 1, "turno": state.turn_no}
                log_event(turn, {"event": "policy_warning", "etapa": 1, "orden": key,
                                 "reglas": [a["regla"] for a in res["advertencias"]]})
            return {"estado": "advertencia_1", **out, "advertencias": res["advertencias"],
                    "instruccion": ("PRIMERA advertencia. Con tono amable y cercano, dile al cliente que para su perfil lo "
                                    "recomendable es no superar el monto indicado en 'limite_usd' y que con esta orden se "
                                    "excede en 'exceso_usd' (usa las cifras de cada advertencia). No des aun el detalle de "
                                    "riesgos. Pregunta si desea continuar y ESPERA su respuesta; no llames a ninguna otra "
                                    "herramienta.")}
        if w["etapa"] == 1:
            state.warnings[key] = {"etapa": 2, "turno": state.turn_no}
            caida = policies()["limites_de_orden"]["caida_ilustrativa_pct"]
            log_event(turn, {"event": "policy_warning", "etapa": 2, "orden": key,
                             "reglas": [a["regla"] for a in res["advertencias"]]})
            return {"estado": "advertencia_2", **out, "advertencias": res["advertencias"],
                    "escenario_ilustrativo": {
                        "caida_pct": caida, "perdida_usd": round(monto * caida / 100, 2),
                        "perdida_pct_del_capital": round(monto * caida / 100 / capital * 100, 1) if capital else None},
                    "instruccion": ("SEGUNDA advertencia. Habla como lo haria un asesor humano responsable: explica con "
                                    "claridad y sin alarmismo los riesgos concretos de esta orden para su perfil (concentracion "
                                    "en un solo activo, volatilidad, que parte de su capital queda expuesta) y usa el "
                                    "'escenario_ilustrativo' para mostrar cuanto perderia en dolares si el activo cayera ese "
                                    "porcentaje. Vuelve a preguntar si AUN ASI desea continuar y ESPERA su respuesta; no "
                                    "llames a ninguna otra herramienta.")}
        if not avanzar:   # etapa 2 sin nueva respuesta afirmativa del cliente
            return {"estado": "advertencia_2", **out, "advertencias": res["advertencias"],
                    "instruccion": "Ya diste la segunda advertencia. Espera a que el cliente responda si desea continuar."}
        log_event(turn, {"event": "policy_exception", "orden": key, "perfil": perfil,
                         "reglas_excedidas": [a["regla"] for a in res["advertencias"]],
                         "detalle": "El cliente decide operar fuera de los limites recomendados tras dos advertencias."})

    ticket_id = f"asesoria-{state.session_id[:24]}-{secrets.token_hex(4)}"
    state.tickets[ticket_id] = {
        "ticket_id": ticket_id, "symbol": symbol, "qty": cantidad, "price": float(price), "monto": monto,
        "validaciones": res["validaciones"], "advertencias": res["advertencias"], "mercado": mercado,
        "expires": time.time() + TICKET_TTL_SECONDS, "estado": "validado",
    }
    return {"estado": "lista_para_confirmar", **out, "advertencias_aceptadas_por_el_cliente": res["advertencias"],
            "ticket_id": ticket_id,
            "llamada_exacta_place_stock_order": {"symbol": symbol, "side": "buy", "qty": str(cantidad), "type": "market",
                                                 "time_in_force": "day", "client_order_id": ticket_id},
            "instruccion": ("Llama ahora a place_stock_order con EXACTAMENTE los argumentos de "
                            "'llamada_exacta_place_stock_order'. El sistema mostrara la tarjeta de confirmacion.")}
