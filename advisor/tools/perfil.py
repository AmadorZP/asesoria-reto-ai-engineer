"""Tool local: perfil de riesgo e idoneidad del cliente."""
from __future__ import annotations

from agent_framework import tool

from advisor.policy import client_view
from advisor.state import LEDGER, current_turn


@tool(approval_mode="never_require")
def consultar_perfil_cliente() -> dict:
    """Devuelve el perfil de riesgo REGISTRADO del cliente de esta sesion, su capital invertible y disponible,
    sus tenencias y los limites que la politica interna le impone (riesgo maximo por activo, concentracion,
    renta variable, tope por orden). No recibe parametros: el cliente lo fija la sesion autenticada, no el chat."""
    turn = current_turn()
    turn.data_calls += 1
    return client_view(turn.state.client_id, LEDGER.holdings(turn.state.client_id))
