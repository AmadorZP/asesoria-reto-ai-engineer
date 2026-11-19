"""Clasificacion del perfil de riesgo y validacion de ordenes, en codigo (deterministas).

Lee kb/policies/politicas.yaml, el mismo archivo del que se generan los documentos de politica
que el agente cita. El modelo extrae datos de la conversacion; quien decide el perfil y si una
orden pasa, se advierte o se bloquea es este modulo.

Dos tipos de regla:
- DURAS (bloquean): cantidad valida, universo operable y poder de compra.
- SUAVES (advierten): limites recomendados del perfil (riesgo por activo, tope por orden,
  concentracion por activo, exposicion a renta variable).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RISK_ORDER = {"bajo": 1, "medio": 2, "alto": 3}
PERFILES = ["conservador", "moderado", "agresivo"]
RENTA_VARIABLE = {"accion_individual", "etf_renta_variable"}


@lru_cache
def policies() -> dict:
    return yaml.safe_load((ROOT / "kb" / "policies" / "politicas.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- perfil de riesgo
def classify_profile(perdida_tolerable_pct: float, horizonte_anios: float) -> dict:
    """Regla determinista: la perdida tolerable fija el nivel y un horizonte corto lo baja un escalon."""
    rule = policies()["clasificacion_de_perfil"]
    cortes = rule["por_perdida_tolerable_pct"]
    nivel = 0 if perdida_tolerable_pct <= cortes["conservador_hasta"] else \
        1 if perdida_tolerable_pct <= cortes["moderado_hasta"] else 2
    motivo = [f"tolera una perdida de hasta {perdida_tolerable_pct:g}% -> {PERFILES[nivel]}"]
    if horizonte_anios < rule["horizonte_corto_anios"] and nivel > 0:
        nivel -= 1
        motivo.append(f"horizonte de {horizonte_anios:g} anios (menor a {rule['horizonte_corto_anios']}) -> baja a {PERFILES[nivel]}")
    return {"perfil": PERFILES[nivel], "motivo": "; ".join(motivo)}


def profile_limits(perfil: str) -> dict:
    p = policies()["perfiles"][perfil]
    return {"objetivo": p["objetivo"], "riesgo_maximo_por_activo": p["riesgo_maximo_por_activo"],
            "max_renta_variable_pct": p["max_renta_variable_pct"],
            "max_concentracion_por_activo_pct": p["max_concentracion_por_activo_pct"],
            "max_orden_pct_capital": p["max_orden_pct_capital"],
            "caracter": "limites RECOMENDADOS: excederlos genera advertencias, no bloqueo"}


# ---------------------------------------------------------------- ordenes
def evaluate_order(perfil: str, capital_total: float, capital_disponible: float, symbol: str, qty: int,
                   price: float, holdings: dict[str, dict], broker_buying_power: float) -> dict:
    """Devuelve {"bloqueos": [...], "advertencias": [...], "validaciones": [...], "monto_estimado_usd": float}.

    holdings = {simbolo: {"cantidad": n, "monto_usd": x}} del cliente.
    """
    pol = policies()
    limits = pol["perfiles"][perfil]
    symbol = symbol.upper().strip()
    monto = round(qty * price, 2)
    checks: list[dict] = []

    def check(regla: str, tipo: str, ok: bool, detalle: str, **extra) -> None:
        checks.append({"regla": regla, "tipo": tipo, "ok": bool(ok), "detalle": detalle, **extra})

    def result() -> dict:
        return {"monto_estimado_usd": monto, "validaciones": checks,
                "bloqueos": [c for c in checks if c["tipo"] == "dura" and not c["ok"]],
                "advertencias": [c for c in checks if c["tipo"] == "suave" and not c["ok"]]}

    # ---- Reglas duras
    check("cantidad_valida", "dura", isinstance(qty, int) and qty > 0, f"Cantidad {qty}; debe ser un entero positivo.")
    clase = pol["universo"].get(symbol)
    check("universo_operable", "dura", clase is not None,
          f"{symbol} pertenece a la clase '{clase}'." if clase else
          f"{symbol} no esta en el universo operable ({', '.join(pol['universo'])}).")
    if clase is None:
        return result()
    poder = max(min(capital_disponible, broker_buying_power), 0.0)
    limita = "el capital disponible del cliente" if capital_disponible <= broker_buying_power else "el saldo real de la cuenta"
    check("poder_de_compra", "dura", monto <= poder,
          f"Monto USD {monto:,.2f} vs. poder de compra USD {poder:,.2f} (lo limita {limita}: capital disponible "
          f"USD {capital_disponible:,.2f}; saldo real de la cuenta USD {broker_buying_power:,.2f}).",
          limite_usd=round(poder, 2), exceso_usd=round(max(monto - poder, 0), 2))

    # ---- Reglas suaves (limites recomendados del perfil)
    def soft(regla: str, valor: float, limite: float, detalle: str) -> None:
        check(regla, "suave", valor <= limite, detalle, limite_usd=round(limite, 2), exceso_usd=round(max(valor - limite, 0), 2))

    riesgo = pol["clases_de_activo"][clase]["riesgo"]
    check("idoneidad_riesgo", "suave", RISK_ORDER[riesgo] <= RISK_ORDER[limits["riesgo_maximo_por_activo"]],
          f"El riesgo de este tipo de activo es '{riesgo}'; para un perfil {perfil} se recomienda como maximo "
          f"'{limits['riesgo_maximo_por_activo']}'.")
    tope_orden = capital_total * limits["max_orden_pct_capital"] / 100
    soft("limite_orden_del_perfil", monto, tope_orden,
         f"Monto USD {monto:,.2f}; para un perfil {perfil} se recomienda no superar el {limits['max_orden_pct_capital']}% "
         f"del capital por orden (USD {tope_orden:,.2f}).")
    actual = holdings.get(symbol, {}).get("monto_usd", 0.0)
    pct_conc = limits["max_concentracion_por_activo_pct"][clase]
    soft("concentracion_por_activo", actual + monto, capital_total * pct_conc / 100,
         f"La posicion en {symbol} quedaria en USD {actual + monto:,.2f}; para un perfil {perfil} se recomienda no "
         f"concentrar mas del {pct_conc}% del capital en un mismo activo de este tipo (USD {capital_total * pct_conc / 100:,.2f}).")
    rv = sum(h["monto_usd"] for s, h in holdings.items() if pol["universo"].get(s) in RENTA_VARIABLE)
    rv += monto if clase in RENTA_VARIABLE else 0
    tope_rv = capital_total * limits["max_renta_variable_pct"] / 100
    soft("exposicion_renta_variable", rv, tope_rv,
         f"La renta variable quedaria en USD {rv:,.2f}; para un perfil {perfil} se recomienda no superar el "
         f"{limits['max_renta_variable_pct']}% del capital (USD {tope_rv:,.2f}).")
    return result()
