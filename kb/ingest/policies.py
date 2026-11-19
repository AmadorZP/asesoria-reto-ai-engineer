"""Genera los documentos de politica interna (Markdown) a partir de politicas.yaml.

El YAML es la unica fuente de verdad: el codigo de validacion lo lee directamente y estos
documentos son su version "legible y citable" para la base de conocimiento.
"""
from __future__ import annotations

from kb.settings import load_policies

NOTA = (
    "Documento SIMULADO, redactado para el reto tecnico AsesorIA. "
    "No es una politica real de Credicorp Capital."
)


def build_policy_docs() -> list[dict]:
    """Devuelve [{meta, sections:[{title, text}]}], una seccion por regla."""
    pol = load_policies()
    version, vigente = pol["version"], pol["vigente_desde"]
    clases, universo, perfiles = pol["clases_de_activo"], pol["universo"], pol["perfiles"]
    lim = pol["limites_de_orden"]

    def meta(doc_id: str, title: str) -> dict:
        return {
            "doc_id": doc_id,
            "title": f"{title} (simulada) v{version}",
            "doc_type": "internal_policy",
            "format": "policy",
            "issuer": "AsesorIA - Politicas internas simuladas",
            "language": "es",
            "url": f"interno://politicas/{doc_id}/v{version}",
            "as_of_date": vigente,
            "is_simulated": True,
        }

    # --- 1. Perfiles de riesgo ---
    sec_perfiles = [{
        "title": "Alcance de la politica de perfiles de riesgo",
        "text": f"{NOTA} Version {version}, vigente desde {vigente}. Todo cliente tiene asignado uno de tres "
                "perfiles de riesgo: conservador, moderado o agresivo. El perfil determina que clases de activo "
                "puede comprar y en que proporcion de su capital invertible.",
    }]
    for nombre, p in perfiles.items():
        sec_perfiles.append({
            "title": f"Perfil {nombre}",
            "text": (
                f"Perfil de riesgo {nombre}. Objetivo: {p['objetivo']} "
                f"El riesgo maximo permitido por activo es '{p['riesgo_maximo_por_activo']}'. "
                f"La exposicion total a renta variable (acciones individuales y ETF de acciones) no puede superar "
                f"el {p['max_renta_variable_pct']}% del capital invertible. "
                f"Una sola orden no puede superar el {p['max_orden_pct_capital']}% del capital invertible."
            ),
        })

    # --- 2. Limites de concentracion ---
    sec_conc = [{
        "title": "Clases de activo y nivel de riesgo",
        "text": f"{NOTA} " + " ".join(
            f"La clase '{k}' ({v['descripcion']}) tiene riesgo {v['riesgo']}." for k, v in clases.items()
        ) + " Universo operable y su clase: " + ", ".join(f"{t} ({c})" for t, c in universo.items()) + ".",
    }]
    for nombre, p in perfiles.items():
        partes = [
            f"hasta {pct}% del capital invertible en un mismo activo de la clase '{clase}'"
            if pct > 0 else f"no puede invertir en activos de la clase '{clase}'"
            for clase, pct in p["max_concentracion_por_activo_pct"].items()
        ]
        sec_conc.append({
            "title": f"Limites de concentracion por activo - perfil {nombre}",
            "text": f"Para un cliente de perfil {nombre}, el limite de concentracion por activo es: "
                    + "; ".join(partes) + ".",
        })

    # --- 3. Idoneidad y ordenes ---
    sec_ord = [
        {
            "title": "Regla de idoneidad (suitability)",
            "text": f"{NOTA} Antes de proponer o ejecutar una compra se verifica la idoneidad: (1) el activo debe "
                    "pertenecer al universo operable; (2) el nivel de riesgo de su clase no puede superar el riesgo "
                    "maximo del perfil del cliente; (3) la posicion resultante no puede exceder el limite de "
                    "concentracion por activo del perfil; (4) la exposicion total a renta variable no puede exceder "
                    "el maximo del perfil. Si alguna verificacion falla, la orden se bloquea y se explica el motivo.",
        },
        {
            "title": "Limites duros por orden",
            "text": f"Toda orden debe cumplir: solo operaciones de compra (lado '{lim['lado_permitido']}'); solo "
                    f"ordenes de tipo '{lim['tipo_permitido']}' con vigencia '{lim['vigencia_permitida']}'; monto "
                    f"maximo de USD {lim['monto_maximo_usd']:,} por orden; cantidad maxima de "
                    f"{lim['cantidad_maxima_acciones']:,} acciones por orden; y el monto no puede superar el poder de "
                    "compra disponible del cliente. No se permiten ventas, ventas en corto, opciones ni criptoactivos.",
        },
        {
            "title": "Confirmacion humana obligatoria",
            "text": "Ninguna orden se envia al mercado sin la confirmacion explicita del usuario. El sistema muestra "
                    "un resumen de la orden (activo, cantidad, precio de referencia, monto estimado y resultado de las "
                    "validaciones) y espera la aprobacion. Si el usuario rechaza, la orden no se ejecuta.",
        },
    ]

    return [
        {"meta": meta("politica-perfiles-riesgo", "Politica interna de perfiles de riesgo"), "sections": sec_perfiles},
        {"meta": meta("politica-limites-concentracion", "Politica interna de limites de concentracion"), "sections": sec_conc},
        {"meta": meta("politica-idoneidad-ordenes", "Politica interna de idoneidad y ejecucion de ordenes"), "sections": sec_ord},
    ]
