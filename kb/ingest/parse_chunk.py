"""Parseo y chunking de los documentos.

Estrategia (justificada en el README):
- Parser especializado por formato: sec2md para HTML de EDGAR (detecta PART/ITEM y conserva
  paginas y tablas), pymupdf4llm para PDF (respeta columnas y da numero de pagina),
  BeautifulSoup + markdownify para paginas web.
- Chunking por estructura: primero se corta por seccion real (Item o encabezado) y solo
  despues por tamano (~600 tokens, solape ~90). Las tablas no se parten.
- Contexto antepuesto: cada chunk se embebe con una cabecera "emisor | documento | seccion",
  que es la version determinista y gratuita del "contextual retrieval".
- Higiene: se eliminan enlaces e imagenes, y se pone en cuarentena cualquier chunk con
  patrones tipicos de prompt injection.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import tiktoken

from kb.ingest.policies import build_policy_docs
from kb.settings import (
    CHUNK_OVERLAP, CHUNK_TOKENS, CHUNKS_PATH, MAX_TABLE_TOKENS, MIN_SECTION_TOKENS,
    PROCESSED_DIR, RAW_DIR, load_catalog,
)

_enc = tiktoken.get_encoding("cl100k_base")


def n_tokens(text: str) -> int:
    return len(_enc.encode(text, disallowed_special=()))


# ---------------------------------------------------------------- higiene / seguridad
INJECTION_PATTERNS = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|disregard (the |all )?(previous|above)|"
    r"you are now|system prompt|<\s*/?\s*system\s*>|ignora (todas )?las instrucciones|"
    r"olvida (todas )?(tus|las) instrucciones|nuevas instrucciones:)",
    re.IGNORECASE,
)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]*)\)")


def clean(text: str) -> str:
    text = _MD_IMAGE.sub("", text)
    text = _MD_LINK.sub(r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------- secciones de filings SEC
SECTION_KEYS_10K = {"1": "business", "1A": "risk_factors", "1C": "cybersecurity", "3": "legal_proceedings",
                    "7": "mda", "7A": "market_risk", "8": "financial_statements", "15": "financial_statements"}
SECTION_KEYS_10Q = {("I", "1"): "financial_statements", ("I", "2"): "mda", ("I", "3"): "market_risk",
                    ("II", "1"): "legal_proceedings", ("II", "1A"): "risk_factors"}
SKIP_ITEMS_10K = {"16", "6", "1B", "4", "9", "9B", "9C"}


def _item_code(item: str | None) -> str:
    return re.sub(r"(?i)item\s*", "", item or "").strip().upper()


def _part_code(part: str | None) -> str:
    return re.sub(r"(?i)part\s*", "", part or "").strip().upper()


def chunk_edgar(doc: dict, html: str) -> list[dict]:
    import sec2md

    pages = sec2md.parse_filing(html, include_elements=False)
    form = doc["doc_type"]
    sections = sec2md.extract_sections(pages, form)
    fiscal = f"FY{doc['fiscal_year']}" if doc["fiscal_period"] == "FY" else f"{doc['fiscal_period']} FY{doc['fiscal_year']}"
    out: list[dict] = []
    for sec in sections:
        item, part = _item_code(sec.item), _part_code(sec.part)
        if not item:
            continue
        if form == "10-K":
            if item in SKIP_ITEMS_10K:
                continue
            # El Item 15 solo interesa cuando contiene los estados financieros (caso NVIDIA).
            if item == "15" and sec.tokens < 3000:
                continue
            key = SECTION_KEYS_10K.get(item, "other")
            label = f"Item {item}"
        else:
            key = SECTION_KEYS_10Q.get((part, item), "other")
            label = f"Part {part} Item {item}"
        if sec.tokens < MIN_SECTION_TOKENS:
            continue
        title = (sec.item_title or "").strip()
        header = f"{doc['ticker']} | {doc['issuer']} Form {form} {fiscal} | {label} {title}".strip()
        chunks = sec2md.chunk_section(sec, chunk_size=CHUNK_TOKENS, chunk_overlap=CHUNK_OVERLAP,
                                      max_table_tokens=MAX_TABLE_TOKENS, header=header)
        slug = re.sub(r"[^a-z0-9]+", "", label.lower())
        for ch in chunks:
            text = clean(ch.content)
            if n_tokens(text) < 15:
                continue
            out.append({
                "chunk_id": f"{doc['doc_id']}:{slug}:{ch.index:03d}",
                "section": label, "section_key": key, "section_title": title,
                "page_start": ch.start_page, "page_end": ch.end_page,
                "has_table": bool(ch.has_table), "header": header, "text": text,
            })
    return out


# ---------------------------------------------------------------- chunker generico (Markdown)
def _blocks_from_markdown(md: str, page: int | None) -> list[dict]:
    """Divide Markdown en bloques: encabezado, tabla (atomica) o parrafo."""
    blocks, buf, buf_table = [], [], False

    def flush():
        nonlocal buf, buf_table
        if buf:
            blocks.append({"kind": "table" if buf_table else "text", "text": "\n".join(buf).strip(), "page": page})
        buf, buf_table = [], False

    for line in md.splitlines():
        stripped = line.strip()
        is_table = stripped.startswith("|")
        if re.match(r"^#{1,6}\s+\S", stripped):
            flush()
            blocks.append({"kind": "heading", "text": re.sub(r"^#{1,6}\s+", "", stripped).strip("* _"), "page": page})
        elif not stripped:
            if not buf_table:
                flush()
        elif is_table != buf_table and buf:
            flush()
            buf, buf_table = [line], is_table
        else:
            buf.append(line)
            buf_table = is_table
    flush()
    return [b for b in blocks if b["text"]]


def _split_long(text: str, limit: int) -> list[str]:
    """Parte un parrafo demasiado largo por oraciones."""
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if cur and n_tokens(cur + " " + sent) > limit:
            parts.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


def chunk_markdown(doc: dict, pages: list[tuple[int | None, str]]) -> list[dict]:
    """pages = [(numero_de_pagina | None, markdown)]. Corta por encabezado y luego por tamano."""
    blocks: list[dict] = []
    for page, md in pages:
        blocks.extend(_blocks_from_markdown(clean(md), page))

    out: list[dict] = []
    section_title, cur, idx = "", [], 0

    def emit():
        nonlocal cur, idx
        if not cur:
            return
        text = "\n\n".join(b["text"] for b in cur).strip()
        if n_tokens(text) >= 15:
            pgs = [b["page"] for b in cur if b["page"] is not None]
            header = f"{doc.get('ticker') or doc['issuer']} | {doc['title']}" + (f" | {section_title}" if section_title else "")
            out.append({
                "chunk_id": f"{doc['doc_id']}:{idx:03d}",
                "section": section_title or "Documento", "section_key": "other", "section_title": section_title,
                "page_start": min(pgs) if pgs else None, "page_end": max(pgs) if pgs else None,
                "has_table": any(b["kind"] == "table" for b in cur), "header": header, "text": text,
            })
            idx += 1
        # solape: se arrastra el ultimo parrafo si es corto y no es tabla
        last = cur[-1]
        cur = [last] if last["kind"] == "text" and n_tokens(last["text"]) <= CHUNK_OVERLAP * 1.5 and len(cur) > 1 else []

    for b in blocks:
        if b["kind"] == "heading":
            emit()
            cur = []
            section_title = b["text"][:120]
            continue
        pieces = [b]
        if b["kind"] == "text" and n_tokens(b["text"]) > CHUNK_TOKENS:
            pieces = [{**b, "text": t} for t in _split_long(b["text"], CHUNK_TOKENS)]
        for piece in pieces:
            size = sum(n_tokens(x["text"]) for x in cur)
            if cur and size + n_tokens(piece["text"]) > CHUNK_TOKENS:
                emit()
            cur.append(piece)
    emit()
    return out


# ---------------------------------------------------------------- lectores por formato
def read_pdf(path: Path) -> list[tuple[int, str]]:
    import pymupdf4llm

    pages = pymupdf4llm.to_markdown(str(path), page_chunks=True, show_progress=False)
    return [(i + 1, p["text"]) for i, p in enumerate(pages)]


def read_web(path: Path) -> list[tuple[None, str]]:
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    main = soup.find("main") or soup.find("article") or soup.body
    for tag in main.find_all(["script", "style", "nav", "footer", "header", "form", "aside", "noscript"]):
        tag.decompose()
    return [(None, markdownify(str(main), heading_style="ATX", strip=["a", "img"]))]


# ---------------------------------------------------------------- pipeline
BASE_META = ["doc_id", "doc_type", "ticker", "issuer", "fiscal_year", "fiscal_period", "period_end",
             "filed_date", "as_of_date", "language"]


def build_chunks() -> dict:
    catalog = load_catalog()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    all_chunks, report = [], {"documentos": {}, "cuarentena": [], "faltantes": []}

    def finish(doc: dict, chunks: list[dict]):
        kept = []
        for ch in chunks:
            if INJECTION_PATTERNS.search(ch["text"]):
                report["cuarentena"].append({"chunk_id": ch["chunk_id"], "extracto": ch["text"][:200]})
                continue
            rec = {k: doc.get(k) for k in BASE_META}
            rec.update(ch)
            rec.update({
                "doc_title": doc["title"],
                "source_url": doc["url"],
                "sha256": manifest.get(doc["doc_id"], {}).get("sha256"),
                "retrieved_at": manifest.get(doc["doc_id"], {}).get("retrieved_at"),
                "is_simulated": bool(doc.get("is_simulated", False)),
                "is_latest": True,  # el catalogo solo contiene la version vigente de cada documento
                "n_tokens": n_tokens(ch["text"]),
                "embedding_text": f"{ch['header']}\n\n{ch['text']}",
            })
            kept.append(rec)
        report["documentos"][doc["doc_id"]] = {"chunks": len(kept), "tokens": sum(c["n_tokens"] for c in kept)}
        (PROCESSED_DIR / f"{doc['doc_id']}.md").write_text(
            "\n\n---\n\n".join(f"<!-- {c['chunk_id']} | p.{c['page_start']} -->\n{c['embedding_text']}" for c in kept),
            encoding="utf-8")
        all_chunks.extend(kept)

    for doc in catalog["documentos"]:
        ext = "pdf" if doc["format"] == "pdf" else "html"
        path = RAW_DIR / f"{doc['doc_id']}.{ext}"
        if not path.exists():
            report["faltantes"].append(doc["doc_id"])
            continue
        try:
            if doc["format"] == "edgar_html":
                chunks = chunk_edgar(doc, path.read_text(encoding="utf-8", errors="replace"))
            elif doc["format"] == "pdf":
                chunks = chunk_markdown(doc, read_pdf(path))
            else:
                chunks = chunk_markdown(doc, read_web(path))
        except Exception as exc:
            report["faltantes"].append(f"{doc['doc_id']} (error de parseo: {exc})")
            continue
        finish(doc, chunks)

    # Politicas internas simuladas: un chunk por regla.
    for pdoc in build_policy_docs():
        meta = pdoc["meta"]
        chunks = [{
            "chunk_id": f"{meta['doc_id']}:{i:03d}", "section": s["title"], "section_key": "policy",
            "section_title": s["title"], "page_start": None, "page_end": None, "has_table": False,
            "header": f"Politica interna | {meta['title']} | {s['title']}", "text": s["text"],
        } for i, s in enumerate(pdoc["sections"])]
        finish(meta, chunks)

    with CHUNKS_PATH.open("w", encoding="utf-8") as fh:
        for rec in all_chunks:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    report["total_chunks"] = len(all_chunks)
    report["total_tokens"] = sum(c["n_tokens"] for c in all_chunks)
    (PROCESSED_DIR / "ingest_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    rep = build_chunks()
    for doc_id, info in rep["documentos"].items():
        print(f"{doc_id:38s} {info['chunks']:4d} chunks  {info['tokens']:7d} tokens")
    print(f"TOTAL: {rep['total_chunks']} chunks, {rep['total_tokens']} tokens")
    print("Faltantes:", rep["faltantes"] or "ninguno")
    print("Cuarentena:", len(rep["cuarentena"]))
