"""Ejecuta los escenarios del reto directamente contra el servicio (sin HTTP).

    python -m scripts.escenarios [1|2|3 ...]     # el 3 coloca una orden REAL en paper trading
"""
from __future__ import annotations

import asyncio
import sys

from advisor.service import AdvisorService


def show(title: str, r: dict) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    print(r["answer"])
    print("\n-- herramientas:", [(e["tool"], e["status"]) for e in r["trace"] if e["event"] == "tool_call"])
    print("-- citas:", [(c["sid"], c["titulo"][:45], c["seccion"][:25], c["pagina"]) for c in r["citations"]])
    print("-- flags:", r["flags"], "| abstuvo:", r["abstained"], "| ms:", r["latency_ms"], "| uso:",
          {k: v for k, v in (r["usage"] or {}).items() if k in ("input_token_count", "output_token_count")})
    if r["pending_approvals"]:
        print("-- APROBACION PENDIENTE:", r["pending_approvals"][0]["arguments"])
    if r["orders"]:
        print("-- ordenes:", r["orders"])


async def main() -> None:
    which = set(sys.argv[1:]) or {"1", "2"}
    svc = AdvisorService()
    await svc.start()
    try:
        if "1" in which:
            show("1. RAG con citas", await svc.chat("demo-1", "MOD-10K",
                 "¿Qué riesgos menciona Apple en su último reporte anual?"))
        if "0" in which:
            show("0. Sin respuesta en la base", await svc.chat("demo-0", "MOD-10K",
                 "¿Qué riesgos menciona Tesla en su último reporte anual?"))
        if "2" in which:
            show("2. Analisis de oportunidades", await svc.chat("demo-2", "MOD-10K",
                 "Tengo un perfil moderado y USD 10,000. ¿Qué oportunidades ves entre MSFT, NVDA y un ETF de bonos?"))
        if "3" in which:
            r = await svc.chat("demo-3", "MOD-10K", "Compra 1 acción de MSFT.")
            show("3a. Orden: validacion y solicitud de confirmacion", r)
            if r["pending_approvals"]:
                r2 = await svc.approve("demo-3", r["pending_approvals"][0]["approval_id"], True)
                show("3b. Orden: tras la confirmacion", r2)
        if "4" in which:
            r = await svc.chat("demo-4", "CON-10K", "Compra 5 acciones de NVDA.")
            show("4. Orden no idonea (conservador)", r)
    finally:
        await svc.stop()


if __name__ == "__main__":
    asyncio.run(main())
