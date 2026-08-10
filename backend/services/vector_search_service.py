"""Vector search over data/embeddings.db using OpenAI text-embedding-3-small."""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import numpy as np
from openai import OpenAI

from backend.config import BASE

logger = logging.getLogger(__name__)

EMBEDDINGS_DB = BASE / "data" / "embeddings.db"
MODEL = "text-embedding-3-small"
DIMS = 1536

_ids: np.ndarray | None = None
_matrix: np.ndarray | None = None
_meta: dict[int, dict] | None = None

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
    """Load the full embedding matrix into memory."""
    global _ids, _matrix, _meta

    conn = sqlite3.connect(str(EMBEDDINGS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, source_type, act, section, section_title, embedding_text, embedding FROM embeddings"
        ).fetchall()
    finally:
        conn.close()

    ids = np.empty(len(rows), dtype=np.int64)
    vecs = np.empty((len(rows), DIMS), dtype=np.float32)
    meta = {}
    for i, row in enumerate(rows):
        ids[i] = row["id"]
        vecs[i] = np.frombuffer(row["embedding"], dtype=np.float32)
        meta[row["id"]] = {
            "source_type": row["source_type"],
            "act": row["act"],
            "section": row["section"],
            "section_title": row["section_title"],
            "embedding_text": row["embedding_text"],
        }

    _ids, _matrix, _meta = ids, vecs, meta
    logger.info(f"Vector search loaded: {len(rows)} embeddings (1536-dim)")


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
        m = _meta[emb_id]
        source_type = m.get("source_type", "section")
        results.append({
            "embedding_id": emb_id,
            "source_type": source_type,
            "act": "tax-cases" if source_type == "case" else ("rulings" if source_type == "ruling" else m["act"]),
            "section": m["section"],
            "title": m["section_title"],
            "score": float(scores[idx]),
            "snippet": m["embedding_text"][:300],
        })
    return results
