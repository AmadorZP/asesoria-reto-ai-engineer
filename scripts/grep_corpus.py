"""Busca un patron en los chunks de un documento (apoyo para redactar el ground truth del set de evaluacion).

    python -m scripts.grep_corpus <doc_id> "<regex>" [n] [ancho]
"""
from __future__ import annotations

import json
import re
import sys

from kb.settings import CHUNKS_PATH


def grep(doc: str, pat: str, n: int = 2, w: int = 300) -> None:
    k = 0
    for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["doc_id"] != doc:
            continue
        m = re.search(pat, c["text"], re.I)
        if m:
            s = max(0, m.start() - w // 3)
            print(f"[{doc} | {c['section'][:28]} | p{c['page_start']}] " + c["text"][s:s + w].replace("\n", " "))
            k += 1
            if k >= n:
                return
    if k == 0:
        print(f"[{doc}] SIN COINCIDENCIAS: {pat}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        grep(sys.argv[1], sys.argv[2], *(int(x) for x in sys.argv[3:5]))
    else:
        for args in [
            ("agg-fact-sheet", r"expense ratio", 1), ("agg-fact-sheet", r"benchmark", 1),
            ("bnd-fact-sheet", r"expense ratio", 1), ("voo-fact-sheet", r"expense ratio", 1),
            ("ivv-fact-sheet", r"expense ratio", 1), ("bnd-summary-prospectus", r"interest rate risk", 1, 420),
            ("aapl-10k-fy2026", r"total net sales", 2), ("aapl-10k-fy2026", r"full-time equivalent employees", 1),
            ("msft-10k-fy2026", r"revenue (increased|was)", 2), ("nvda-10k-fy2026", r"export control", 1, 420),
            ("nvda-10k-fy2026", r"revenue (for fiscal year 2026 )?was", 2), ("msft-10q-fy2027-q1", r"revenue increased", 1),
            ("smv-exposicion-motivos-011-2026", r"perfil de riesgo", 2, 520),
            ("smv-resolucion-011-2026", r"recomendaci[oó]n(es)? personalizada", 2, 520),
            ("bvl-memoria-2024", r"monto negociado|capitalizaci[oó]n burs", 2, 380),
            ("sec-asset-allocation-guide", r"diversification is", 1, 420),
            ("sec-risk-tolerance", r"risk tolerance", 1, 420), ("sec-interest-rate-risk", r"prices? .{0,40}fall", 1, 420),
        ]:
            grep(*args)
