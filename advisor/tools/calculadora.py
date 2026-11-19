"""Calculadora financiera local: la aritmetica la hace el codigo, no el modelo."""
from __future__ import annotations

import math
import statistics
from typing import Annotated, Literal

from agent_framework import tool
from pydantic import Field

from advisor.state import TURN

Operacion = Literal[
    "costo_orden", "max_acciones", "variacion_pct", "rendimiento_anualizado",
    "metricas_de_precios", "ratio_pe", "asignacion_cartera", "valor_futuro",
]


def calcular(operacion: str, precio: float | None = None, cantidad: float | None = None,
             monto: float | None = None, valor_inicial: float | None = None, valor_final: float | None = None,
             dias: float | None = None, precios: list[float] | None = None, eps: float | None = None,
             pesos_pct: dict[str, float] | None = None, tasa_anual_pct: float | None = None,
             anios: float | None = None) -> dict:
    def need(**kw):
        faltan = [k for k, v in kw.items() if v is None]
        if faltan:
            raise ValueError(f"La operacion '{operacion}' requiere: {', '.join(faltan)}")

    if operacion == "costo_orden":
        need(precio=precio, cantidad=cantidad)
        return {"monto_usd": round(precio * cantidad, 2), "formula": "precio x cantidad"}
    if operacion == "max_acciones":
        need(precio=precio, monto=monto)
        n = math.floor(monto / precio)
        return {"acciones_enteras": n, "monto_usado_usd": round(n * precio, 2),
                "sobrante_usd": round(monto - n * precio, 2), "formula": "floor(monto / precio)"}
    if operacion == "variacion_pct":
        need(valor_inicial=valor_inicial, valor_final=valor_final)
        return {"variacion_pct": round((valor_final / valor_inicial - 1) * 100, 2), "formula": "(final / inicial - 1) x 100"}
    if operacion == "rendimiento_anualizado":
        need(valor_inicial=valor_inicial, valor_final=valor_final, dias=dias)
        r = (valor_final / valor_inicial) ** (365 / dias) - 1
        return {"rendimiento_anualizado_pct": round(r * 100, 2), "formula": "(final / inicial)^(365 / dias) - 1"}
    if operacion == "metricas_de_precios":
        need(precios=precios)
        if len(precios) < 3:
            raise ValueError("Se requieren al menos 3 precios de cierre en orden cronologico.")
        rets = [precios[i] / precios[i - 1] - 1 for i in range(1, len(precios))]
        pico, max_dd = precios[0], 0.0
        for p in precios:
            pico = max(pico, p)
            max_dd = min(max_dd, p / pico - 1)
        sma = lambda n: round(statistics.fmean(precios[-n:]), 2) if len(precios) >= n else None
        sma20 = sma(20)
        return {
            "n_observaciones": len(precios),
            "retorno_periodo_pct": round((precios[-1] / precios[0] - 1) * 100, 2),
            "volatilidad_anualizada_pct": round(statistics.stdev(rets) * math.sqrt(252) * 100, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "sma_20": sma20, "sma_50": sma(50), "ultimo_precio": precios[-1],
            "tendencia": None if sma20 is None else ("alcista" if precios[-1] > sma20 else "bajista"),
            "formula": "volatilidad = desv.est. de retornos diarios x raiz(252); tendencia = ultimo precio vs. SMA20",
        }
    if operacion == "ratio_pe":
        need(precio=precio, eps=eps)
        if eps <= 0:
            return {"ratio_pe": None, "nota": "EPS no positivo: el P/E no es interpretable."}
        return {"ratio_pe": round(precio / eps, 2), "formula": "precio / EPS diluido anual"}
    if operacion == "asignacion_cartera":
        need(monto=monto, pesos_pct=pesos_pct)
        total = sum(pesos_pct.values())
        if abs(total - 100) > 0.5:
            raise ValueError(f"Los pesos deben sumar 100% (suman {total}).")
        return {"asignacion_usd": {k: round(monto * v / 100, 2) for k, v in pesos_pct.items()}, "formula": "monto x peso"}
    if operacion == "valor_futuro":
        need(monto=monto, tasa_anual_pct=tasa_anual_pct, anios=anios)
        vf = monto * (1 + tasa_anual_pct / 100) ** anios
        return {"valor_futuro_usd": round(vf, 2), "formula": "monto x (1 + tasa)^anios",
                "nota": "Estimacion ilustrativa con tasa constante; no es una proyeccion ni una garantia."}
    raise ValueError(f"Operacion desconocida: {operacion}")


@tool(approval_mode="never_require")
def calculadora_financiera(
    operacion: Annotated[Operacion, Field(description=(
        "costo_orden(precio, cantidad) | max_acciones(precio, monto) | variacion_pct(valor_inicial, valor_final) | "
        "rendimiento_anualizado(valor_inicial, valor_final, dias) | metricas_de_precios(precios: cierres diarios en "
        "orden cronologico -> retorno, volatilidad anualizada, max drawdown, SMA20/50, tendencia) | "
        "ratio_pe(precio, eps) | asignacion_cartera(monto, pesos_pct) | valor_futuro(monto, tasa_anual_pct, anios)"))],
    precio: Annotated[float | None, Field(description="Precio por accion en USD")] = None,
    cantidad: Annotated[float | None, Field(description="Numero de acciones")] = None,
    monto: Annotated[float | None, Field(description="Monto en USD")] = None,
    valor_inicial: float | None = None,
    valor_final: float | None = None,
    dias: Annotated[float | None, Field(description="Dias calendario entre valor_inicial y valor_final")] = None,
    precios: Annotated[list[float] | None, Field(description="Precios de cierre en orden cronologico")] = None,
    eps: Annotated[float | None, Field(description="Utilidad por accion diluida anual en USD")] = None,
    pesos_pct: Annotated[dict[str, float] | None, Field(description="Pesos por activo en %, deben sumar 100")] = None,
    tasa_anual_pct: float | None = None,
    anios: float | None = None,
    etiqueta: Annotated[str | None, Field(description=(
        "A que se refiere el calculo, p. ej. el ticker ('MSFT'). Se devuelve en el resultado para no "
        "confundir cifras entre activos. Indicala siempre que calcules sobre un activo."))] = None,
) -> dict:
    """Calculadora financiera. Usala para TODA operacion numerica del analisis (montos, variaciones,
    volatilidad, P/E, asignaciones). No hagas calculos mentalmente."""
    turn = TURN.get()
    if turn:
        turn.data_calls += 1
    try:
        return {"operacion": operacion, "etiqueta": etiqueta, **calcular(operacion, precio, cantidad, monto, valor_inicial, valor_final,
                                                   dias, precios, eps, pesos_pct, tasa_anual_pct, anios)}
    except (ValueError, ZeroDivisionError) as exc:
        return {"operacion": operacion, "error": str(exc)}
