"""Busqueda hibrida sobre la base de conocimiento (denso + BM25, fusion RRF, filtros por metadata)."""
from __future__ import annotations

from functools import cached_property

from openai import OpenAI
from qdrant_client import QdrantClient, models

from kb.settings import COLLECTION, EMBEDDING_MODEL, QDRANT_DIR, SPARSE_MODEL, load_catalog

DOC_TYPES = ["10-K", "10-Q", "etf_fact_sheet", "etf_prospectus", "investor_education",
             "regulation_pe", "annual_report_pe", "internal_policy"]
SECTION_KEYS = ["business", "risk_factors", "mda", "market_risk", "financial_statements",
                "legal_proceedings", "cybersecurity", "policy", "other"]


class KnowledgeBase:
    def __init__(self) -> None:
        self.qdrant = QdrantClient(path=str(QDRANT_DIR))
        self.openai = OpenAI()
        self.tickers = sorted({d["ticker"] for d in load_catalog()["documentos"] if d.get("ticker")})

    @cached_property
    def _sparse(self):
        from fastembed import SparseTextEmbedding
        return SparseTextEmbedding(SPARSE_MODEL)

    def coverage(self) -> dict:
        return {"tickers": self.tickers, "doc_types": DOC_TYPES}

    def search(self, query: str, ticker: str | None = None, doc_type: str | None = None,
               section: str | None = None, top_k: int = 6) -> dict:
        """Devuelve {"results": [...], "max_dense_score": float, "coverage_note": str | None}."""
        if ticker:
            ticker = ticker.upper().strip()
            if ticker not in self.tickers:
                return {"results": [], "max_dense_score": 0.0,
                        "coverage_note": f"{ticker} no esta en la base de conocimiento. "
                                         f"Tickers disponibles: {', '.join(self.tickers)}."}
        must = []
        for key, value in (("ticker", ticker), ("doc_type", doc_type), ("section_key", section)):
            if value:
                must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        flt = models.Filter(must=must) if must else None

        dense = self.openai.embeddings.create(model=EMBEDDING_MODEL, input=[query]).data[0].embedding
        sp = next(iter(self._sparse.query_embed(query)))
        sparse = models.SparseVector(indices=sp.indices.tolist(), values=sp.values.tolist())

        fused = self.qdrant.query_points(
            COLLECTION,
            prefetch=[models.Prefetch(query=dense, using="dense", limit=24, filter=flt),
                      models.Prefetch(query=sparse, using="bm25", limit=24, filter=flt)],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k, with_payload=True,
        ).points
        # Similitud coseno maxima: solo se usa como "puerta gruesa" para detectar consultas fuera de dominio.
        top_dense = self.qdrant.query_points(COLLECTION, query=dense, using="dense", limit=1,
                                             query_filter=flt, with_payload=False).points
        return {
            "results": [{**p.payload, "rrf_score": round(p.score, 4)} for p in fused],
            "max_dense_score": round(top_dense[0].score, 4) if top_dense else 0.0,
            "coverage_note": None,
        }

    def close(self) -> None:
        self.qdrant.close()
