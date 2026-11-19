"""Perfil y situacion financiera de la sesion.

- Sesion "inferido": el capital es el que el cliente declaro en la conversacion (hipotetico) y las
  tenencias son las compras hechas en esa sesion.
- Sesion "alpaca" (especial): capital y tenencias se leen en vivo de la cuenta paper real; solo el
  nivel de riesgo se conversa. Asi funcionaria en produccion, con datos del sistema de registro.
"""
from __future__ import annotations

from advisor import runtime
from advisor.policy import profile_limits
from advisor.state import SessionState


def has_profile(state: SessionState) -> bool:
    """Hay perfil utilizable: nivel de riesgo y, salvo en la sesion de Alpaca, capital declarado."""
    p = state.profile or {}
    return bool(p.get("perfil")) and (state.kind == "alpaca" or bool(p.get("capital_invertible_usd")))


async def broker_buying_power() -> float:
    acc = await runtime.alpaca_data("get_account_info")
    # Sin apalancamiento: se usa el poder de compra no marginable.
    return min(float(acc.get("non_marginable_buying_power", 0)), float(acc.get("buying_power", 0)))


async def financials(state: SessionState) -> dict:
    """{"capital_total", "capital_disponible", "tenencias", "fuente"}; capital_total None si aun no se conoce."""
    if state.kind == "alpaca":
        acc = await runtime.alpaca_data("get_account_info")
        raw = await runtime.alpaca_data("get_all_positions")
        positions = raw.get("result", raw) if isinstance(raw, dict) else raw
        tenencias = {p["symbol"]: {"cantidad": float(p.get("qty", 0)), "monto_usd": round(float(p.get("market_value", 0)), 2)}
                     for p in (positions or []) if isinstance(p, dict) and p.get("symbol")}
        disponible = min(float(acc.get("non_marginable_buying_power", 0)), float(acc.get("buying_power", 0)))
        return {"capital_total": round(float(acc.get("equity", 0)), 2), "capital_disponible": round(disponible, 2),
                "tenencias": tenencias, "fuente": "cuenta real de Alpaca (paper trading)"}
    capital = (state.profile or {}).get("capital_invertible_usd")
    invertido = round(sum(h["monto_usd"] for h in state.holdings.values()), 2)
    return {"capital_total": capital, "capital_disponible": None if capital is None else round(capital - invertido, 2),
            "tenencias": state.holdings, "fuente": "declarado por el cliente en la conversacion"}


def profile_view(state: SessionState, fin: dict) -> dict:
    """Lo que ven el agente (tool de perfil y contexto) y la interfaz (chip de la barra lateral)."""
    p = state.profile
    base = {"sesion": "cuenta real de Alpaca (paper)" if state.kind == "alpaca" else "perfil inferido en la conversacion",
            "capital_invertible_usd": fin["capital_total"], "capital_disponible_usd": fin["capital_disponible"],
            "tenencias": fin["tenencias"], "fuente_del_capital": fin["fuente"]}
    if not has_profile(state):
        faltan = ["perfil de riesgo (declarado, o perdida tolerable y horizonte)"]
        if state.kind != "alpaca":
            faltan.insert(0, "capital invertible")
        return {"perfil_registrado": False, **base, "faltan": faltan}
    return {"perfil_registrado": True, "perfil_de_riesgo": p["perfil"], "origen": p["origen"], "motivo": p.get("motivo"),
            "horizonte_anios": p.get("horizonte_anios"), "perdida_tolerable_pct": p.get("perdida_tolerable_pct"),
            "objetivo": p.get("objetivo"), **base, "limites_recomendados": profile_limits(p["perfil"])}
