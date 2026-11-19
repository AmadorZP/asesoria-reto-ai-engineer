"""Descarga los documentos publicos del catalogo a data/raw.

Controles de seguridad de la ingesta:
- solo se descargan URLs de dominios en la lista blanca del catalogo;
- se guarda sha256, URL y fecha de descarga de cada archivo (procedencia);
- la SEC exige identificar al solicitante (variable SEC_USER_AGENT) y no superar 10 req/s.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from kb.settings import RAW_DIR, load_catalog

GENERIC_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
EXT = {"edgar_html": "html", "web_html": "html", "pdf": "pdf"}
MANIFEST = RAW_DIR / "manifest.json"


def _headers(host: str) -> dict:
    if host.endswith("sec.gov"):
        ua = os.getenv("SEC_USER_AGENT", "").strip()
        if not ua:
            raise RuntimeError("Falta SEC_USER_AGENT en .env (la SEC exige 'Nombre Apellido correo').")
        return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
    return {"User-Agent": GENERIC_UA, "Accept": "*/*"}


def download_all(force: bool = False) -> dict:
    catalog = load_catalog()
    allowed = set(catalog["dominios_permitidos"])
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

    for doc in catalog["documentos"]:
        doc_id, url = doc["doc_id"], doc["url"]
        host = urlparse(url).netloc
        path = RAW_DIR / f"{doc_id}.{EXT[doc['format']]}"
        if host not in allowed:
            print(f"[BLOQUEADO] {doc_id}: dominio fuera de la lista blanca ({host})")
            continue
        if path.exists() and not force:
            print(f"[ok, ya existe] {doc_id}")
            continue
        try:
            resp = requests.get(url, headers=_headers(host), timeout=60)
            resp.raise_for_status()
        except Exception as exc:  # se reporta y se sigue con el resto
            print(f"[ERROR] {doc_id}: {exc}")
            continue
        data = resp.content
        if doc["format"] == "pdf" and not data.startswith(b"%PDF"):
            print(f"[ERROR] {doc_id}: la respuesta no es un PDF")
            continue
        path.write_bytes(data)
        manifest[doc_id] = {
            "source_url": url,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"[descargado] {doc_id} ({len(data) / 1024:.0f} KB)")
        time.sleep(0.4)

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    download_all()
