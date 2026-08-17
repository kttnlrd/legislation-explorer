"""Neighborhood enrichment for search results (graph spec §6.1).

Given graph node keys, return per-edge-type counts + top-3 exemplars ranked
by global degree, in one batched pass (no N+1 queries).

Output shape (per key):
    {node, label, edges: {<edge_type>: {count: int, top: [label, ...]}}}

- count: number of typed edges touching the node (either direction)
- top:   3 neighbour labels with the highest global degree (spec §8:
         degree ranking within the neighbourhood; Leiden is deferred to v2)

The counts/top-3 are materialised in `neighborhood_index` (built once by
`python3 -m backend.services.graph_neighborhood` or lazily on first use) so
search-time enrichment is one indexed SELECT per batch — the on-the-fly
computation over hub nodes (s 8-1 ≈ 18k edges) blew the 50 ms gate.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

GRAPH_DB = Path(__file__).resolve().parents[2] / "data" / "graph.db"
INDEX_TABLE = "neighborhood_index"

_build_lock = threading.Lock()


def _global_degrees(conn: sqlite3.Connection) -> dict[int, int]:
    deg: dict[int, int] = {}
    for nid, cnt in conn.execute(
        "SELECT node_id, COUNT(*) FROM ("
        "  SELECT source_id AS node_id FROM graph_edges "
        "  UNION ALL SELECT target_id FROM graph_edges"
        ") GROUP BY node_id"
    ):
        deg[nid] = cnt
    return deg


def build_index(conn: sqlite3.Connection) -> int:
    """(Re)build the materialised neighbourhood index. Returns row count."""
    conn.execute(f"DROP TABLE IF EXISTS {INDEX_TABLE}")
    conn.execute(
        f"""CREATE TABLE {INDEX_TABLE} (
            node_id  INTEGER NOT NULL,
            edge_type TEXT NOT NULL,
            count    INTEGER NOT NULL,
            top_json TEXT NOT NULL,
            PRIMARY KEY (node_id, edge_type)
        )"""
    )
    degree = _global_degrees(conn)

    # per (node, type): edge row count; per (node, type): neighbour_id -> degree
    counts: dict[tuple[int, str], int] = {}
    agg: dict[tuple[int, str], dict[int, int]] = {}
    rows = conn.execute(
        "SELECT source_id, target_id, edge_type FROM graph_edges"
    ).fetchall()
    for s, t, et in rows:
        counts[(s, et)] = counts.get((s, et), 0) + 1
        counts[(t, et)] = counts.get((t, et), 0) + 1
        agg.setdefault((s, et), {})[t] = degree.get(t, 0)
        agg.setdefault((t, et), {})[s] = degree.get(s, 0)

    # labels for the top-3 neighbours
    top_ids: set[int] = set()
    for members in agg.values():
        for nid2, _ in sorted(members.items(), key=lambda kv: -kv[1])[:3]:
            top_ids.add(nid2)
    labels: dict[int, str] = {}
    if top_ids:
        ph = ",".join("?" * len(top_ids))
        labels = {r[0]: r[1] for r in conn.execute(
            f"SELECT id, label FROM nodes WHERE id IN ({ph})", list(top_ids))}

    conn.executemany(
        f"INSERT OR REPLACE INTO {INDEX_TABLE} (node_id, edge_type, count, top_json) VALUES (?,?,?,?)",
        [
            (nid, et, counts.get((nid, et), 0), json.dumps(
                [labels.get(n2, str(n2)) for n2, _ in
                 sorted(members.items(), key=lambda kv: -kv[1])[:3]]))
            for (nid, et), members in agg.items()
        ],
    )
    conn.commit()
    logger.info("[graph] built %s: %d rows", INDEX_TABLE, len(agg))
    return len(agg)


def _index_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (INDEX_TABLE,)
    ).fetchone() is not None


def _ensure_index(conn: sqlite3.Connection) -> None:
    if _index_exists(conn):
        return
    with _build_lock:
        if _index_exists(conn):
            return
        # build needs write access — the caller's conn may be read-only
        wconn = sqlite3.connect(GRAPH_DB, timeout=30)
        try:
            if _index_exists(wconn):
                return
            build_index(wconn)
        finally:
            wconn.close()


def neighborhoods(keys: list[str]) -> dict[str, dict | None]:
    """Batch neighbourhood map. Unknown keys map to None."""
    if not keys:
        return {}
    try:
        conn = sqlite3.connect(f"file:{GRAPH_DB}?mode=ro", uri=True, timeout=10)
    except sqlite3.Error:
        logger.exception("[graph] cannot open %s", GRAPH_DB)
        return {k: None for k in keys}

    try:
        _ensure_index(conn)

        ph = ",".join("?" * len(keys))
        rows = conn.execute(
            f"SELECT id, key, label FROM nodes WHERE key IN ({ph})", keys
        ).fetchall()

        # Case-insensitive fallback for keys that missed (e.g. itaa-1936 109ba
        # vs tree-case 109BA). Rare; a seq scan only happens when needed.
        if len(rows) < len(keys):
            found_keys = {r[1] for r in rows}
            misses = [k for k in keys if k not in found_keys]
            ph_m = ",".join("?" * len(misses))
            rows += conn.execute(
                f"SELECT id, key, label FROM nodes WHERE lower(key) IN ({ph_m})",
                [m.lower() for m in misses],
            ).fetchall()

        if not rows:
            return {k: None for k in keys}

        by_key = {r[1]: r for r in rows}
        lower_to_row = {r[1].lower(): r for r in rows}
        ids = [r[0] for r in rows]
        id_to_label = {r[0]: r[2] for r in rows}

        ph_ids = ",".join("?" * len(ids))
        idx_rows = conn.execute(
            f"SELECT node_id, edge_type, count, top_json FROM {INDEX_TABLE} "
            f"WHERE node_id IN ({ph_ids})",
            ids,
        ).fetchall()
        index_by_id: dict[int, list[tuple[str, int, str]]] = {}
        for nid, et, cnt, top in idx_rows:
            index_by_id.setdefault(nid, []).append((et, cnt, top))

        out: dict[str, dict | None] = {}
        for k in keys:
            r = by_key.get(k) or lower_to_row.get(k.lower())
            if r is None:
                out[k] = None
                continue
            nid = r[0]
            edges: dict[str, dict] = {}
            for et, cnt, top_json in index_by_id.get(nid, []):
                edges[et] = {"count": cnt, "top": json.loads(top_json)}
            out[k] = {"node": r[1], "label": r[2], "edges": edges}
        return out
    except sqlite3.Error:
        logger.exception("[graph] neighbourhood query failed")
        return {k: None for k in keys}
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = sqlite3.connect(GRAPH_DB)
    try:
        n = build_index(conn)
        print(f"built {n} rows in {GRAPH_DB}")
    finally:
        conn.close()
