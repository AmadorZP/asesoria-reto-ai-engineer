"""Pruebas deterministas de los guardrails (no llaman a ningun LLM ni a Alpaca).

    pytest -q
"""
from __future__ import annotations

import time

from advisor.middleware import find_ticket
from advisor.policy import evaluate_order, policies
from advisor.tools.calculadora import calcular
from kb.ingest.policies import build_policy_docs

BP = 100_000.0  # poder de compra del broker


def failed(result: dict) -> set[str]:
    return {c["regla"] for c in result["validaciones"] if not c["ok"]}


def test_moderado_compra_pequena_es_valida():
    r = evaluate_order("MOD-100K", "MSFT", 2, 500.0, {}, BP)
    assert r["valida"] and r["monto_estimado_usd"] == 1000.0


def test_conservador_no_puede_comprar_acciones_individuales():
    r = evaluate_order("CON-100K", "NVDA", 3, 150.0, {}, BP)
    assert not r["valida"] and {"idoneidad_riesgo", "concentracion_por_activo"} <= failed(r)


def test_limite_de_concentracion_y_tope_por_orden():
    r = evaluate_order("MOD-10K", "MSFT", 5, 500.0, {}, BP)          # USD 2,500 > 10% y > 15% de 10,000
    assert {"concentracion_por_activo", "limite_orden_del_perfil"} <= failed(r)


def test_concentracion_considera_tenencias_previas():
    holdings = {"MSFT": {"cantidad": 1, "monto_usd": 900.0}}
    assert "concentracion_por_activo" in failed(evaluate_order("MOD-10K", "MSFT", 1, 500.0, holdings, BP))


def test_tope_duro_por_orden():
    assert "monto_maximo_por_orden" in failed(evaluate_order("AGR-1M", "MSFT", 200, 500.0, {}, 1e9))


def test_poder_de_compra_usa_el_minimo_entre_cliente_y_broker():
    assert "poder_de_compra" in failed(evaluate_order("AGR-1M", "AGG", 100, 100.0, {}, 5_000.0))


def test_ticker_fuera_del_universo():
    assert "universo_operable" in failed(evaluate_order("AGR-1M", "TSLA", 1, 300.0, {}, BP))


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


def test_politica_documental_y_codigo_no_divergen():
    """Una sola fuente de verdad: los limites del YAML aparecen literalmente en los documentos citables."""
    text = " ".join(s["text"] for d in build_policy_docs() for s in d["sections"])
    for nombre, perfil in policies()["perfiles"].items():
        assert f"el {perfil['max_renta_variable_pct']}% del capital" in text
        assert f"el {perfil['max_orden_pct_capital']}% del capital" in text
    assert f"USD {policies()['limites_de_orden']['monto_maximo_usd']:,}" in text


def test_calculadora():
    assert calcular("costo_orden", precio=508.5, cantidad=5)["monto_usd"] == 2542.5
    assert calcular("max_acciones", precio=508.5, monto=1000)["acciones_enteras"] == 1
    m = calcular("metricas_de_precios", precios=[100, 110, 99, 105])
    assert m["retorno_periodo_pct"] == 5.0 and m["max_drawdown_pct"] == -10.0
