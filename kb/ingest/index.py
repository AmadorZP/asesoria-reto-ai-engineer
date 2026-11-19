"""Embeddings + indexado en Qdrant (modo local, sin servidor).

Cada chunk se guarda con dos vectores:
- "dense": text-embedding-3-large (significado; cruza espanol <-> ingles);
- "bm25": vector disperso (coincidencia exacta de tickers, "Item 1A", cifras).
La busqueda los fusiona con RRF (busqueda hibrida).
"""
from __future__ import annotations

import json
import uuid

from openai import OpenAI
from qdrant_client import QdrantClient, models

from kb.settings import CHUNKS_PATH, COLLECTION, EMBEDDING_DIM, EMBEDDING_MODEL, QDRANT_DIR, SPARSE_MODEL

PAYLOAD_SKIP = {"embedding_text"}


def embed_texts(client: OpenAI, texts: list[str], batch: int = 64) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch):
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts[i:i + batch])
        vectors.extend(d.embedding for d in resp.data)
        print(f"  embeddings {min(i + batch, len(texts))}/{len(texts)}")
    return vectors


def build_index() -> int:
    from fastembed import SparseTextEmbedding

    chunks = [json.loads(line) for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [c["embedding_text"] for c in chunks]

    dense = embed_texts(OpenAI(), texts)
    sparse = list(SparseTextEmbedding(SPARSE_MODEL).embed(texts))

    QDRANT_DIR.mkdir(parents=True, exist_ok=True)
    qdrant = QdrantClient(path=str(QDRANT_DIR))
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
    qdrant.create_collection(
        COLLECTION,
        vectors_config={"dense": models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    points = [
        models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, c["chunk_id"])),
            vector={"dense": d, "bm25": models.SparseVector(indices=s.indices.tolist(), values=s.values.tolist())},
            payload={k: v for k, v in c.items() if k not in PAYLOAD_SKIP},
        )
        for c, d, s in zip(chunks, dense, sparse)
    ]
    for i in range(0, len(points), 128):
        qdrant.upsert(COLLECTION, points=points[i:i + 128])
    qdrant.close()
    return len(points)


if __name__ == "__main__":
    print(f"Indexados {build_index()} chunks en {QDRANT_DIR}")
