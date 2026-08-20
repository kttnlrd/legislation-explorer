"""Vector search over data/embeddings.db using OpenAI text-embedding-3-small."""
from __future__ import annotations

import logging
import os
import pickle
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from openai import OpenAI

from backend.config import BASE

logger = logging.getLogger(__name__)

EMBEDDINGS_DB = BASE / "data" / "embeddings.db"
MATRIX_FILE = BASE / "data" / "embeddings_matrix.npy"
IDS_FILE = BASE / "data" / "embeddings_ids.npy"
META_FILE = BASE / "data" / "embeddings_meta.pkl"
BUILD_SCRIPT = BASE / "scripts" / "build_vector_matrix.py"
MODEL = "text-embedding-3-small"
DIMS = 1536

_ids: np.ndarray | None = None
_matrix: np.ndarray | None = None
_meta: dict[int, tuple] | None = None

# Load API key from .hermes/.env
_env_path = Path("/home/harrison/.hermes/.env")
_api_key = os.environ.get("OPENAI_API_KEY")
if not _api_key and _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        if _line.startswith("OPENAI_API_KEY="):
            _api_key = _line.strip().split("=", 1)[1]
            break

_client = OpenAI(api_key=_api_key)


def load() -> None:
    """Load the vector matrix (memory-mapped) + compact metadata.

    The matrix snapshot is built by scripts/build_vector_matrix.py; loading
    via mmap keeps RSS flat regardless of corpus size (274K+ embeddings would
    otherwise need ~1.7GB just for the matrix and OOM the 1.5GB cgroup).
    If the DB has grown past the snapshot, rebuild it first (self-heal).
    """
    global _ids, _matrix, _meta

    def _build() -> None:
        logger.info("Vector matrix snapshot stale — rebuilding via %s", BUILD_SCRIPT.name)
        t0 = time.time()
        subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            check=True, capture_output=True, timeout=1800,
        )
        logger.info("Matrix rebuild took %.0fs", time.time() - t0)

    conn = sqlite3.connect(str(EMBEDDINGS_DB))
    try:
        db_rows = conn.execute("SELECT count(*) FROM embeddings").fetchone()[0]
    finally:
        conn.close()

    if not MATRIX_FILE.exists():
        _build()
    else:
        try:
            snapshot_rows = int(np.load(IDS_FILE).shape[0])
        except Exception:
            snapshot_rows = -1
        if snapshot_rows != db_rows:
            logger.info("Matrix snapshot %s rows vs DB %s — rebuilding", snapshot_rows, db_rows)
            _build()

    _ids = np.load(IDS_FILE)
    _matrix = np.load(MATRIX_FILE, mmap_mode="r")
    with open(META_FILE, "rb") as f:
        _meta = pickle.load(f)
    logger.info("Vector search loaded: %d embeddings (1536-dim, mmap)", _ids.shape[0])


def _ensure_loaded() -> None:
    if _ids is None:
        load()


def embed_query(query: str) -> np.ndarray:
    """Embed a single query via OpenAI API."""
    resp = _client.embeddings.create(
        model=MODEL,
        input=[query],
        dimensions=DIMS,
    )
    return np.array(resp.data[0].embedding, dtype=np.float32)


def get_cross_references(embedding_id: int) -> list[dict]:
    conn = sqlite3.connect(str(EMBEDDINGS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ref_type, ref_text, ref_target FROM cross_references WHERE embedding_id = ?",
            (embedding_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        # cross_references table may not exist (new embedding pipeline)
        return []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def search(query: str, limit: int = 50) -> list[dict]:
    """Embed the query and return the top-K nearest chunks by cosine similarity."""
    _ensure_loaded()
    query_vec = embed_query(query)
    scores = _matrix @ query_vec
    top_idx = np.argsort(-scores)[:limit]

    results = []
    for idx in top_idx:
        emb_id = int(_ids[idx])
        # embeddings_meta.pkl stores tuples (see scripts/build_vector_matrix.py)
        source_type, m_act, m_section, m_title, m_text = _meta[emb_id]
        source_type = source_type or "section"
        if source_type == "case":
            act = "tax-cases"
        elif source_type == "ruling" and m_act == "private":
            source_type = "private_ruling"
            act = "private-rulings"
        elif source_type == "ruling":
            act = "rulings"
        else:
            act = m_act
        results.append({
            "embedding_id": emb_id,
            "source_type": source_type,
            "act": act,
            "section": m_section,
            "title": m_title,
            "score": float(scores[idx]),
            "snippet": (m_text or "")[:300],
        })
    return results
