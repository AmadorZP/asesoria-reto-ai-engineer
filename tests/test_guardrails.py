"""Pruebas deterministas de los guardrails (no llaman a ningun LLM ni a Alpaca).

    pytest -q
"""
from __future__ import annotations

import time

from advisor.middleware import find_ticket
from advisor.policy import classify_profile, evaluate_order, policies
from advisor.tools.calculadora import calcular
from kb.ingest.policies import build_policy_docs

BP = 100_000.0  # saldo real de la cuenta del broker


def order(perfil, capital, symbol, qty, price, holdings=None, disponible=None, bp=BP):
    holdings = holdings or {}
    disponible = capital - sum(h["monto_usd"] for h in holdings.values()) if disponible is None else disponible
    return evaluate_order(perfil, capital, disponible, symbol, qty, price, holdings, bp)


def rules(items) -> set[str]:
    return {c["regla"] for c in items}


# ---------------------------------------------------------------- clasificacion del perfil
def test_clasificacion_por_perdida_tolerable():
    assert classify_profile(5, 10)["perfil"] == "conservador"
    assert classify_profile(20, 7)["perfil"] == "moderado"
    assert classify_profile(40, 15)["perfil"] == "agresivo"


def test_horizonte_corto_baja_un_nivel():
    assert classify_profile(30, 2)["perfil"] == "moderado"
    assert classify_profile(20, 2)["perfil"] == "conservador"
    assert classify_profile(5, 1)["perfil"] == "conservador"      # no baja por debajo de conservador


# ---------------------------------------------------------------- reglas suaves: advierten, no bloquean
def test_orden_dentro_del_perfil_no_tiene_advertencias():
    r = order("moderado", 100_000, "MSFT", 2, 500.0)
    assert not r["bloqueos"] and not r["advertencias"] and r["monto_estimado_usd"] == 1000.0


def test_exceder_el_perfil_advierte_pero_no_bloquea():
    r = order("moderado", 10_000, "MSFT", 5, 500.0)               # USD 2,500 > 10% y > 15% de 10,000
    assert not r["bloqueos"]
    assert {"concentracion_por_activo", "limite_orden_del_perfil"} <= rules(r["advertencias"])
    conc = next(a for a in r["advertencias"] if a["regla"] == "concentracion_por_activo")
    assert conc["limite_usd"] == 1000.0 and conc["exceso_usd"] == 1500.0


def test_conservador_con_accion_individual_es_advertencia():
    r = order("conservador", 100_000, "NVDA", 3, 150.0)
    assert not r["bloqueos"] and {"idoneidad_riesgo", "concentracion_por_activo"} <= rules(r["advertencias"])


def test_concentracion_considera_tenencias_previas():
    holdings = {"MSFT": {"cantidad": 1, "monto_usd": 900.0}}
    assert "concentracion_por_activo" in rules(order("moderado", 10_000, "MSFT", 1, 500.0, holdings)["advertencias"])


# ---------------------------------------------------------------- reglas duras: bloquean
def test_el_dinero_del_cliente_es_limite_duro():
    r = order("agresivo", 10_000, "MSFT", 100, 500.0)             # USD 50,000 con USD 10,000
    assert "poder_de_compra" in rules(r["bloqueos"])


def test_el_saldo_real_de_la_cuenta_tambien_limita():
    r = order("agresivo", 1_000_000, "MSFT", 400, 500.0, bp=100_000.0)   # el cliente "tiene" 1M, la cuenta 100k
    assert "poder_de_compra" in rules(r["bloqueos"]) and "saldo real de la cuenta" in r["bloqueos"][0]["detalle"]


def test_sin_tope_fijo_de_monto_ni_de_acciones():
    r = order("agresivo", 1_000_000, "AGG", 5000, 100.0, bp=1_000_000.0)  # USD 500,000 y 5,000 acciones
    assert not r["bloqueos"]


def test_ticker_fuera_del_universo_bloquea():
    assert "universo_operable" in rules(order("agresivo", 1_000_000, "TSLA", 1, 300.0)["bloqueos"])


# ---------------------------------------------------------------- ticket y solo compra
def _ticket(**kw):
    t = {"ticket_id": "t1", "symbol": "MSFT", "qty": 2, "estado": "validado", "expires": time.time() + 60}
    return {"t1": {**t, **kw}}


def test_orden_requiere_ticket_coincidente():
    ok = {"symbol": "MSFT", "side": "buy", "qty": "2", "type": "market", "time_in_force": "day"}
    assert find_ticket(_ticket(), ok)[0] is not None
    assert find_ticket({}, ok)[0] is None                                   # sin validacion previa
    assert find_ticket(_ticket(), {**ok, "qty": "20"})[0] is None           # cantidad distinta a la validada
    assert find_ticket(_ticket(expires=time.time() - 1), ok)[0] is None     # ticket vencido
    assert find_ticket(_ticket(estado="ejecutado"), ok)[0] is None          # ticket ya usado (no se reutiliza)


def test_orden_solo_compra_a_mercado():
    base = {"symbol": "MSFT", "qty": "2", "type": "market", "time_in_force": "day"}
    assert find_ticket(_ticket(), {**base, "side": "sell"})[0] is None
    assert find_ticket(_ticket(), {**base, "side": "buy", "type": "limit", "limit_price": "1"})[0] is None
    assert find_ticket(_ticket(), {**base, "side": "buy", "extended_hours": True})[0] is None
    assert find_ticket(_ticket(), {**base, "side": "buy", "notional": "999999"})[0] is None


# ---------------------------------------------------------------- una sola fuente de verdad
def test_politica_documental_y_codigo_no_divergen():
    """Los limites y cortes del YAML aparecen literalmente en los documentos citables."""
    text = " ".join(s["text"] for d in build_policy_docs() for s in d["sections"])
    for perfil in policies()["perfiles"].values():
        assert f"el {perfil['max_renta_variable_pct']}% del capital" in text
        assert f"el {perfil['max_orden_pct_capital']}% del capital" in text
    cortes = policies()["clasificacion_de_perfil"]["por_perdida_tolerable_pct"]
    assert f"hasta el {cortes['conservador_hasta']}% es conservador" in text
    assert f"hasta el {cortes['moderado_hasta']}% es moderado" in text


def test_calculadora():
    assert calcular("costo_orden", precio=508.5, cantidad=5)["monto_usd"] == 2542.5
    assert calcular("max_acciones", precio=508.5, monto=1000)["acciones_enteras"] == 1
    m = calcular("metricas_de_precios", precios=[100, 110, 99, 105])
    assert m["retorno_periodo_pct"] == 5.0 and m["max_drawdown_pct"] == -10.0
