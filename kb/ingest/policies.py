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
    lim, clasif = pol["limites_de_orden"], pol["clasificacion_de_perfil"]
    cortes = clasif["por_perdida_tolerable_pct"]

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
    sec_perfiles = [
        {
            "title": "Alcance de la politica de perfiles de riesgo",
            "text": f"{NOTA} Version {version}, vigente desde {vigente}. Antes de dar una recomendacion personalizada o "
                    "de ejecutar una compra se determina el perfil de riesgo del cliente: conservador, moderado o "
                    "agresivo. No se requiere perfil para consultas informativas (hechos de documentos, educacion al "
                    "inversor o datos de mercado).",
        },
        {
            "title": "Como se determina el perfil de riesgo",
            "text": "El perfil se obtiene en la conversacion con el cliente. Si el cliente declara explicitamente su "
                    "perfil, se registra el declarado. Si no, se clasifica segun la perdida maxima que dice tolerar sin "
                    f"vender: hasta el {cortes['conservador_hasta']}% es conservador; hasta el {cortes['moderado_hasta']}% "
                    "es moderado; por encima es agresivo. Si su horizonte de inversion es menor a "
                    f"{clasif['horizonte_corto_anios']} anios, el perfil baja un nivel, porque un plazo corto reduce la "
                    "capacidad de recuperarse de una caida. Tambien se registra el capital invertible que el cliente indica.",
        },
    ]
    for nombre, p in perfiles.items():
        sec_perfiles.append({
            "title": f"Perfil {nombre}",
            "text": (
                f"Perfil de riesgo {nombre}. Objetivo: {p['objetivo']} "
                f"El riesgo maximo recomendado por activo es '{p['riesgo_maximo_por_activo']}'. "
                f"Se recomienda que la exposicion total a renta variable (acciones individuales y ETF de acciones) no "
                f"supere el {p['max_renta_variable_pct']}% del capital invertible, y que una sola orden no supere "
                f"el {p['max_orden_pct_capital']}% del capital invertible."
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
            if pct > 0 else f"no se recomienda invertir en activos de la clase '{clase}'"
            for clase, pct in p["max_concentracion_por_activo_pct"].items()
        ]
        sec_conc.append({
            "title": f"Limites recomendados de concentracion por activo - perfil {nombre}",
            "text": f"Para un cliente de perfil {nombre}, el limite recomendado de concentracion por activo es: "
                    + "; ".join(partes) + ".",
        })

    # --- 3. Idoneidad y ordenes ---
    sec_ord = [
        {
            "title": "Regla de idoneidad (suitability): limites recomendados y advertencias",
            "text": f"{NOTA} Los limites del perfil (riesgo maximo por activo, concentracion por activo, exposicion a "
                    "renta variable y tope por orden) son limites recomendados, no prohibiciones. Si una orden los "
                    "excede, no se rechaza: primero se advierte al cliente, de forma amable, cual es el monto "
                    "recomendado para su perfil y por cuanto lo excede; si desea continuar, se le explican los riesgos "
                    "concretos y se le pregunta de nuevo; si aun asi desea continuar, la orden pasa a la confirmacion "
                    "final. La decision de operar fuera de los limites recomendados queda registrada como excepcion.",
        },
        {
            "title": "Limites duros por orden",
            "text": f"Los unicos limites que bloquean una orden sin excepcion son: solo operaciones de compra (lado "
                    f"'{lim['lado_permitido']}'), de tipo '{lim['tipo_permitido']}' con vigencia "
                    f"'{lim['vigencia_permitida']}'; el activo debe pertenecer al universo operable; y el monto no puede "
                    "superar el poder de compra, que es el menor entre el capital disponible del cliente y el saldo real "
                    "de la cuenta. No se permiten ventas, ventas en corto, opciones ni criptoactivos.",
        },
        {
            "title": "Confirmacion humana obligatoria",
            "text": "Ninguna orden se envia al mercado sin la confirmacion explicita del usuario. El sistema muestra "
                    "un resumen de la orden (activo, cantidad, precio de referencia, monto estimado, validaciones y "
                    "advertencias aceptadas) y espera la aprobacion. Si el usuario rechaza, la orden no se ejecuta.",
        },
    ]

    return [
        {"meta": meta("politica-perfiles-riesgo", "Politica interna de perfiles de riesgo"), "sections": sec_perfiles},
        {"meta": meta("politica-limites-concentracion", "Politica interna de limites de concentracion"), "sections": sec_conc},
        {"meta": meta("politica-idoneidad-ordenes", "Politica interna de idoneidad y ejecucion de ordenes"), "sections": sec_ord},
    ]
