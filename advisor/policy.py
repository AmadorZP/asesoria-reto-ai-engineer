"""Reglas de idoneidad y limites de orden, evaluadas en codigo (deterministas).

Lee kb/policies/politicas.yaml, el mismo archivo del que se generan los documentos de politica
que el agente cita. El modelo nunca decide si una orden cumple: lo decide esta funcion.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RISK_ORDER = {"bajo": 1, "medio": 2, "alto": 3}
RENTA_VARIABLE = {"accion_individual", "etf_renta_variable"}


@lru_cache
def policies() -> dict:
    return yaml.safe_load((ROOT / "kb" / "policies" / "politicas.yaml").read_text(encoding="utf-8"))


@lru_cache
def clients() -> dict[str, dict]:
    data = json.loads((ROOT / "advisor" / "data" / "clientes.json").read_text(encoding="utf-8"))
    return {c["client_id"]: c for c in data["clientes"]}


def get_client(client_id: str) -> dict:
    if client_id not in clients():
        raise KeyError(f"Cliente desconocido: {client_id}")
    return clients()[client_id]


def client_view(client_id: str, holdings: dict[str, dict]) -> dict:
    """Perfil + limites + tenencias: lo que devuelve la tool de perfil y se inyecta como contexto."""
    c, pol = get_client(client_id), policies()
    perfil = pol["perfiles"][c["perfil"]]
    invertido = round(sum(h["monto_usd"] for h in holdings.values()), 2)
    return {
        "client_id": c["client_id"], "nombre": c["nombre"], "perfil_de_riesgo": c["perfil"],
        "capital_invertible_usd": c["capital_invertible_usd"],
        "capital_ya_invertido_usd": invertido,
        "capital_disponible_usd": round(c["capital_invertible_usd"] - invertido, 2),
        "tenencias": holdings,
        "limites_del_perfil": {
            "objetivo": perfil["objetivo"],
            "riesgo_maximo_por_activo": perfil["riesgo_maximo_por_activo"],
            "max_renta_variable_pct": perfil["max_renta_variable_pct"],
            "max_concentracion_por_activo_pct": perfil["max_concentracion_por_activo_pct"],
            "max_orden_pct_capital": perfil["max_orden_pct_capital"],
        },
        "universo_operable": pol["universo"],
        "politica_version": pol["version"],
    }


def evaluate_order(client_id: str, symbol: str, qty: int, price: float,
                   holdings: dict[str, dict], broker_buying_power: float) -> dict:
    """Devuelve {"valida": bool, "validaciones": [{regla, ok, detalle}], "monto_estimado_usd": float}."""
    pol, c = policies(), get_client(client_id)
    perfil, lim = pol["perfiles"][c["perfil"]], pol["limites_de_orden"]
    capital = float(c["capital_invertible_usd"])
    symbol = symbol.upper().strip()
    monto = round(qty * price, 2)
    checks: list[dict] = []

    def check(regla: str, ok: bool, detalle: str) -> None:
        checks.append({"regla": regla, "ok": bool(ok), "detalle": detalle})

    check("cantidad_valida", isinstance(qty, int) and 0 < qty <= lim["cantidad_maxima_acciones"],
          f"Cantidad {qty}; debe ser un entero entre 1 y {lim['cantidad_maxima_acciones']}.")

    clase = pol["universo"].get(symbol)
    check("universo_operable", clase is not None,
          f"{symbol} pertenece a la clase '{clase}'." if clase else
          f"{symbol} no esta en el universo operable ({', '.join(pol['universo'])}).")
    if clase is None:
        return {"valida": False, "validaciones": checks, "monto_estimado_usd": monto}

    riesgo = pol["clases_de_activo"][clase]["riesgo"]
    check("idoneidad_riesgo", RISK_ORDER[riesgo] <= RISK_ORDER[perfil["riesgo_maximo_por_activo"]],
          f"Riesgo del activo '{riesgo}' vs. maximo del perfil {c['perfil']} '{perfil['riesgo_maximo_por_activo']}'.")

    check("monto_maximo_por_orden", monto <= lim["monto_maximo_usd"],
          f"Monto USD {monto:,.2f} vs. tope duro USD {lim['monto_maximo_usd']:,}.")

    tope_orden = capital * perfil["max_orden_pct_capital"] / 100
    check("limite_orden_del_perfil", monto <= tope_orden,
          f"Monto USD {monto:,.2f} vs. {perfil['max_orden_pct_capital']}% del capital (USD {tope_orden:,.2f}).")

    actual = holdings.get(symbol, {}).get("monto_usd", 0.0)
    tope_conc = capital * perfil["max_concentracion_por_activo_pct"][clase] / 100
    check("concentracion_por_activo", actual + monto <= tope_conc,
          f"Posicion resultante en {symbol} USD {actual + monto:,.2f} vs. limite "
          f"{perfil['max_concentracion_por_activo_pct'][clase]}% (USD {tope_conc:,.2f}).")

    rv_actual = sum(h["monto_usd"] for s, h in holdings.items() if pol["universo"].get(s) in RENTA_VARIABLE)
    rv_nueva = rv_actual + (monto if clase in RENTA_VARIABLE else 0)
    tope_rv = capital * perfil["max_renta_variable_pct"] / 100
    check("exposicion_renta_variable", rv_nueva <= tope_rv,
          f"Renta variable resultante USD {rv_nueva:,.2f} vs. limite {perfil['max_renta_variable_pct']}% (USD {tope_rv:,.2f}).")

    disponible = capital - sum(h["monto_usd"] for h in holdings.values())
    poder = min(disponible, broker_buying_power)
    check("poder_de_compra", monto <= poder,
          f"Monto USD {monto:,.2f} vs. poder de compra USD {poder:,.2f} "
          f"(capital disponible del cliente USD {disponible:,.2f}; cuenta del broker USD {broker_buying_power:,.2f}).")

    return {"valida": all(ch["ok"] for ch in checks), "validaciones": checks, "monto_estimado_usd": monto}
