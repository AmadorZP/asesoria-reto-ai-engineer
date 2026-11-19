"""Rutas y configuracion compartida de la base de conocimiento."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

KB_DIR = ROOT / "kb"
CATALOG_PATH = KB_DIR / "catalog.yaml"
POLICIES_PATH = KB_DIR / "policies" / "politicas.yaml"

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
QDRANT_DIR = DATA_DIR / "qdrant"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"

COLLECTION = "asesoria_kb"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIM = 3072
SPARSE_MODEL = "Qdrant/bm25"

# Chunking (justificacion en el README): secciones reales + ~600 tokens con solape.
CHUNK_TOKENS = 600
CHUNK_OVERLAP = 90
MAX_TABLE_TOKENS = 2000
MIN_SECTION_TOKENS = 40


def load_catalog() -> dict:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


def load_policies() -> dict:
    return yaml.safe_load(POLICIES_PATH.read_text(encoding="utf-8"))
