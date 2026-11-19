"""Juez LLM del evaluador.

Decisiones de diseno:
- Modelo distinto y superior al del asesor (JUDGE_MODEL), para reducir el sesgo de autopreferencia.
- Veredictos binarios por afirmacion contra evidencia textual, no notas 1-5: el puntaje es una fraccion
  calculada en codigo y cada veredicto es auditable (trae su cita de evidencia).
- Salida estructurada (Pydantic): el juez no puede salirse del esquema.
"""
from __future__ import annotations

import os
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-6.1-terra")
_client: OpenAI | None = None


class Claim(BaseModel):
    afirmacion: str
    evidencia: str
    veredicto: Literal["respaldada", "no_respaldada", "contradicha"]


class FaithfulnessVerdict(BaseModel):
    afirmaciones: list[Claim]


class FactCheck(BaseModel):
    hecho: str
    evidencia: str
    veredicto: Literal["presente", "ausente", "contradicho"]


class CorrectnessVerdict(BaseModel):
    hechos: list[FactCheck]


FAITHFULNESS_PROMPT = """Eres un auditor de fidelidad (groundedness) de un asistente financiero.
Recibes la RESPUESTA del asistente y la EVIDENCIA que tuvo disponible (fragmentos de documentos, salidas de
herramientas de mercado, perfil del cliente y calculos).
1. Extrae las afirmaciones factuales verificables de la RESPUESTA (maximo 12, las mas importantes): cifras,
   hechos sobre empresas, fondos, politicas, precios, limites del cliente. Ignora saludos, avisos legales,
   opiniones explicitamente marcadas como tales, preguntas y descripciones de lo que el asistente hara.
2. Para cada afirmacion, busca en la EVIDENCIA un texto que la respalde y copialo literal en `evidencia`
   (cadena vacia si no existe).
3. Veredicto: "respaldada" si la EVIDENCIA la sostiene (se aceptan parafrasis, traducciones y redondeos
   razonables; un calculo es valido si se deriva de cifras de la EVIDENCIA); "contradicha" si la EVIDENCIA dice lo
   contrario; "no_respaldada" si no aparece en la EVIDENCIA.
Juzga solo contra la EVIDENCIA, nunca con tu conocimiento propio."""

CORRECTNESS_PROMPT = """Eres un evaluador de correccion de un asistente financiero.
Recibes la PREGUNTA, la RESPUESTA del asistente y una lista de HECHOS DE REFERENCIA (hechos o comportamientos
esperados). Para cada hecho de referencia, en el mismo orden:
- copia el hecho en `hecho`;
- copia en `evidencia` el fragmento literal de la RESPUESTA que lo cumple o lo contradice (vacio si no hay);
- veredicto: "presente" si la RESPUESTA lo afirma o lo cumple (se aceptan parafrasis y redondeos razonables),
  "contradicho" si afirma o hace lo contrario, "ausente" si no lo trata.
Evalua solo lo que dice la RESPUESTA."""


def _parse(system: str, user: str, schema):
    global _client
    _client = _client or OpenAI()
    resp = _client.responses.parse(model=JUDGE_MODEL, text_format=schema,
                                   input=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return resp.output_parsed


def judge_faithfulness(answer: str, evidence: str) -> FaithfulnessVerdict:
    return _parse(FAITHFULNESS_PROMPT, f"# EVIDENCIA\n{evidence}\n\n# RESPUESTA\n{answer}", FaithfulnessVerdict)


def judge_correctness(question: str, answer: str, facts: list[str]) -> CorrectnessVerdict:
    listado = "\n".join(f"{i}. {f}" for i, f in enumerate(facts, start=1))
    return _parse(CORRECTNESS_PROMPT,
                  f"# PREGUNTA\n{question}\n\n# RESPUESTA\n{answer}\n\n# HECHOS DE REFERENCIA\n{listado}",
                  CorrectnessVerdict)


# ---------------------------------------------------------------- chequeo barato del propio juez
SANITY_EVIDENCE = ("[S1] El expense ratio del fondo es 0.03%. El fondo sigue el Bloomberg US Aggregate Bond Index.\n"
                   "[S2] Los ingresos del año fiscal 2026 fueron de USD 215.9 mil millones, 65% más que el año anterior.\n"
                   "[herramienta get_stock_snapshot] {\"MSFT\": {\"latestTrade\": {\"p\": 508.5}}}")
SANITY_CASES = [  # (respuesta, es_fiel)
    ("El fondo tiene un expense ratio de 0.03% y sigue el Bloomberg US Aggregate Bond Index.", True),
    ("El fondo tiene un expense ratio de 0.30% y sigue el índice S&P 500.", False),
    ("Los ingresos del año fiscal 2026 fueron de USD 215.9 mil millones, un alza de 65%.", True),
    ("Los ingresos del año fiscal 2026 fueron de USD 315.9 mil millones, un alza de 25%.", False),
    ("MSFT cotiza alrededor de USD 508.50 según el último trade.", True),
    ("MSFT cotiza alrededor de USD 620 y paga un dividendo de 4% anual.", False),
]


def judge_sanity() -> dict:
    """Canarios: respuestas fieles y las mismas con un dato falso. Mide si el juez distingue unas de otras."""
    tp = tn = 0
    for answer, faithful in SANITY_CASES:
        claims = judge_faithfulness(answer, SANITY_EVIDENCE).afirmaciones
        all_supported = bool(claims) and all(c.veredicto == "respaldada" for c in claims)
        tp += faithful and all_supported
        tn += (not faithful) and (not all_supported)
    n_pos = sum(f for _, f in SANITY_CASES)
    return {"n": len(SANITY_CASES), "fieles_reconocidas": f"{tp}/{n_pos}",
            "corruptas_detectadas": f"{tn}/{len(SANITY_CASES) - n_pos}", "juez": JUDGE_MODEL}
