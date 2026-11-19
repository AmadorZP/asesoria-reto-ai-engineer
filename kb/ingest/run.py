"""Pipeline completo de ingesta:  python -m kb.ingest.run  [--skip-download] [--skip-index]"""
from __future__ import annotations

import sys

from kb.ingest.download import download_all
from kb.ingest.index import build_index
from kb.ingest.parse_chunk import build_chunks


def main() -> None:
    args = set(sys.argv[1:])
    if "--skip-download" not in args:
        print("== 1/3 Descarga ==")
        download_all()
    print("== 2/3 Parseo y chunking ==")
    rep = build_chunks()
    for doc_id, info in rep["documentos"].items():
        print(f"  {doc_id:38s} {info['chunks']:4d} chunks  {info['tokens']:7d} tokens")
    print(f"  TOTAL: {rep['total_chunks']} chunks, {rep['total_tokens']} tokens")
    if rep["faltantes"]:
        print("  FALTANTES:", rep["faltantes"])
    if rep["cuarentena"]:
        print("  EN CUARENTENA (posible prompt injection):", [c["chunk_id"] for c in rep["cuarentena"]])
    if "--skip-index" not in args:
        print("== 3/3 Embeddings e indice ==")
        print(f"  Indexados {build_index()} chunks")


if __name__ == "__main__":
    main()
