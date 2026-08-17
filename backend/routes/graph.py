"""Graph data endpoint — returns nodes + edges for force-directed visualization.

Supports three source types:
  - section:  /api/graph/data?type=section&act=itaa-1997&section=8-1
  - ruling:   /api/graph/data?type=ruling&citation=TR%202025/1
  - case:     /api/graph/data?type=case&citation=[2015]%20HCA%2048

Returns { nodes: [{id, label, group, url}], edges: [{source, target, label}] }
where group controls colour: section, ruling, case, definition, commentary.
"""
from __future__ import annotations

import logging
import sqlite3
import re as _re

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.config import BASE

logger = logging.getLogger(__name__)

router = APIRouter()


def _section_url(act: str, section: str) -> str:
    return f"/sections/{act}/{section}"


def _ruling_url(citation: str) -> str:
    from urllib.parse import quote
    return f"/rulings/{quote(citation)}"


def _case_url(citation: str) -> str:
    from urllib.parse import quote
    return f"/tax-cases/{quote(citation)}"


# ── resolve functions (graph.db) ─────────────────────────────────────────────

GRAPH_DB = BASE / "data" / "graph.db"

_EDGE_LABELS = {
    "applies": "applies",
    "interpreted_by": "interpreted by",
    "cites": "cites",
    "considered_in": "considered in",
    "explained_in": "explained in",
    "defines": "defines",
}

# Node types we never expand through — private rulings are anonymous leaves.
_LEAF_TYPES = {"private_ruling"}

_MAX_NODES = 300
_MAX_PRIVATE = 60
_MAX_EDGES = 2000


def _norm(s: str) -> str:
    return _re.sub(r"[\s_]+", "", s or "").upper()


class _GraphIndex:
    """Lazy normalized key -> (node_type, key) index over graph.db nodes."""

    def __init__(self):
        self._keys: dict[str, tuple[str, str]] | None = None

    def _load(self):
        conn = sqlite3.connect(str(GRAPH_DB))
        try:
            self._keys = {
                _norm(k): (nt, k)
                for nt, k in conn.execute("SELECT node_type, key FROM nodes").fetchall()
            }
        finally:
            conn.close()

    def lookup(self, key: str) -> tuple[str, str] | None:
        if self._keys is None:
            self._load()
        return self._keys.get(_norm(key))


_GRAPH_INDEX = _GraphIndex()


def _node_payload(nt: str, key: str, label: str) -> dict:
    """Map a graph.db node to the API node shape."""
    if nt == "section":
        # key: section:{act}:{sec}
        _, act, sec = key.split(":", 2)
        return {"id": key, "label": label, "short_label": sec,
                "group": "section", "url": _section_url(act, sec)}
    if nt == "public_ruling":
        cit = key.split(":", 1)[1]
        return {"id": key, "label": cit, "short_label": cit,
                "group": "ruling", "url": _ruling_url(cit)}
    if nt == "private_ruling":
        auth = key.rsplit("/", 1)[-1]
        return {"id": key, "label": f"EV/{auth}", "short_label": f"EV\u2026{auth[-6:]}",
                "group": "private_ruling", "url": ""}
    if nt == "case":
        cit = key.split(":", 1)[1]
        return {"id": key, "label": cit, "short_label": cit,
                "group": "case", "url": _case_url(cit)}
    if nt == "definition":
        term = label or key.rsplit(":", 1)[-1]
        return {"id": key, "label": term, "short_label": term,
                "group": "definition", "url": ""}
    # commentary
    return {"id": key, "label": label, "short_label": key.rsplit(":", 1)[-1],
            "group": "commentary", "url": ""}


def _resolve_from_graph(start_key: str, depth: int) -> dict:
    """BFS ego-graph from a graph.db node key. Private rulings are leaves."""
    conn = sqlite3.connect(str(GRAPH_DB))
    conn.row_factory = sqlite3.Row
    try:
        start = conn.execute(
            "SELECT id, node_type, key, label FROM nodes WHERE key = ?",
            (start_key,),
        ).fetchone()
        if start is None:
            return {"nodes": [], "edges": []}

        seen: dict[int, dict] = {start["id"]: {
            "node_type": start["node_type"], "key": start["key"], "label": start["label"]}}
        edge_set: set[tuple] = set()
        edge_list: list[dict] = []
        frontier = [start["id"]]
        private_total = 0

        for _level in range(depth):
            if not frontier:
                break
            ph = ",".join("?" for _ in frontier)
            rows = conn.execute(
                f"""SELECT e.edge_type, e.weight,
                           sn.id AS sid, sn.key AS skey, sn.node_type AS stype, sn.label AS slabel,
                           tn.id AS tid, tn.key AS tkey, tn.node_type AS ttype, tn.label AS tlabel
                    FROM graph_edges e
                    JOIN nodes sn ON sn.id = e.source_id
                    JOIN nodes tn ON tn.id = e.target_id
                    WHERE e.source_id IN ({ph}) OR e.target_id IN ({ph})
                    LIMIT 4000""",
                frontier + frontier,
            ).fetchall()

            next_frontier: list[int] = []
            for r in rows:
                ekey = (r["skey"], r["tkey"], r["edge_type"])
                if ekey not in edge_set:
                    edge_set.add(ekey)
                    edge_list.append({
                        "source": r["skey"],
                        "target": r["tkey"],
                        "label": _EDGE_LABELS.get(r["edge_type"], r["edge_type"]),
                        "weight": r["weight"] or 1.0,
                        "type": r["edge_type"],
                    })
                for nid, nt, nkey, nlabel in (
                    (r["sid"], r["stype"], r["skey"], r["slabel"]),
                    (r["tid"], r["ttype"], r["tkey"], r["tlabel"]),
                ):
                    if nid in seen or len(seen) >= _MAX_NODES:
                        continue
                    if nt == "private_ruling":
                        private_total += 1
                        if private_total > _MAX_PRIVATE:
                            continue
                    seen[nid] = {"node_type": nt, "key": nkey, "label": nlabel}
                    if nt not in _LEAF_TYPES:
                        next_frontier.append(nid)

            frontier = next_frontier

        # Only emit edges whose endpoints both made it into the response
        node_keys = {n["key"] for n in seen.values()}
        edges = [e for e in edge_list
                 if e["source"] in node_keys and e["target"] in node_keys]
        # Cap edges; keep edges touching the center node first
        if len(edges) > _MAX_EDGES:
            edges.sort(key=lambda e: 0 if e["source"] == start_key or e["target"] == start_key else 1)
            edges = edges[:_MAX_EDGES]

        nodes = [_node_payload(n["node_type"], n["key"], n["label"]) for n in seen.values()]
        return {"nodes": nodes, "edges": edges}
    finally:
        conn.close()


def _resolve_section(act: str, section: str, depth: int) -> dict:
    key = f"section:{act}:{section}"
    if _GRAPH_INDEX.lookup(key) is None:
        return {"nodes": [], "edges": []}
    return _resolve_from_graph(key, depth)


def _resolve_ruling(citation: str, depth: int) -> dict:
    key = f"public_ruling:{citation}"
    if _GRAPH_INDEX.lookup(key) is None:
        return {"nodes": [], "edges": []}
    return _resolve_from_graph(key, depth)


def _resolve_case(citation: str, depth: int) -> dict:
    key = f"case:{citation}"
    if _GRAPH_INDEX.lookup(key) is None:
        return {"nodes": [], "edges": []}
    return _resolve_from_graph(key, depth)


@router.get("/api/graph/serialize")
def graph_serialize(
    key: str = Query(...),
    depth: int = Query(default=1, ge=1, le=2),
):
    """LLM-facing serialization of a graph node (graph spec §6.2).

    Query params:
      key:    canonical graph key, e.g. "section:itaa-1997:118-110"
      depth:  1 = node neighbourhood (≈80 tokens); 2 = + aggregated
              neighbourhood-of-neighbourhood (≤400 tokens, deduped).

    Returns {key, label, depth, tokens, text} where `text` is a token-lean
    block an LLM can read directly (counts + top exemplars per edge type).
    """
    from backend.services.graph_serialize import serialize as _serialize

    out = _serialize(key, depth=depth)
    if out is None:
        return JSONResponse({"error": f"unknown graph key: {key}"}, status_code=404)
    return out


@router.get("/api/graph/path")
def graph_path(
    from_key: str = Query(alias="from"),
    to_key: str = Query(alias="to"),
    max_hops: int = Query(default=10, ge=1, le=20),
):
    """Shortest path between two graph nodes (graph spec §6.3).

    Query params:
      from, to: canonical graph keys, e.g. "section:itaa-1997:118-110"
      max_hops: hop cap (1-20, default 10)

    Returns {from, to, hops, path, edges} where path is the ordered node
    list and edges give the typed connection per hop (undirected traversal,
    edge type preserved). Unreachable pairs return path: null with a reason.
    """
    from backend.services.graph_path import FRONTIER_CAP, FrontierExceeded, find_path

    conn = sqlite3.connect(str(GRAPH_DB))
    try:
        def _resolve(k: str) -> int | None:
            row = conn.execute("SELECT id FROM nodes WHERE key=?", (k,)).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT id FROM nodes WHERE lower(key)=?", (k.lower(),)).fetchone()
            return row[0] if row else None

        f_id = _resolve(from_key)
        t_id = _resolve(to_key)
        if f_id is None or t_id is None:
            missing = from_key if f_id is None else to_key
            return JSONResponse({"error": f"unknown graph key: {missing}"}, status_code=404)

        try:
            path, hops = find_path(conn, f_id, t_id, max_hops=max_hops)
        except FrontierExceeded as exc:
            return {"from": from_key, "to": to_key, "path": None, "hops": None,
                    "reason": f"frontier exceeded {exc} nodes at a level (cap {FRONTIER_CAP})"}

        if path is None:
            return {"from": from_key, "to": to_key, "path": None, "hops": None,
                    "reason": f"no path within {max_hops} hops"}

        ids = [nid for nid, _ in path]
        meta: dict[int, tuple[str, str]] = {}
        if ids:
            ph = ",".join("?" * len(ids))
            meta = {r[0]: (r[1], r[2]) for r in conn.execute(
                f"SELECT id, key, label FROM nodes WHERE id IN ({ph})", ids).fetchall()}

        return {
            "from": from_key,
            "to": to_key,
            "hops": hops,
            "path": [
                {"key": meta.get(nid, (None, str(nid)))[0],
                 "label": meta.get(nid, (None, str(nid)))[1]}
                for nid in ids
            ],
            "edges": [
                {"type": et, "from": i, "to": i + 1}
                for i, (_, et) in enumerate(path[1:], start=0)
                if et is not None
            ],
        }
    finally:
        conn.close()


@router.get("/api/graph/data")
def graph_data(
    type: str = Query(alias="type"),
    act: str | None = Query(default=None),
    section: str | None = Query(default=None),
    citation: str | None = Query(default=None),
    depth: int = Query(default=1, ge=1, le=3),
):
    """Return nodes and edges for a force-directed graph centered on an item.

    Query params:
      type:      "section", "ruling", or "case"
      act:       act key (required for type=section), e.g. "itaa-1997"
      section:   section id (required for type=section), e.g. "8-1"
      citation:  citation (required for type=ruling or case), e.g. "TR 2025/1"
      depth:     expansion depth (1-3, default 1). Higher = more neighbours.
    """
    if type == "section":
        if not act or not section:
            return JSONResponse({"error": "act and section required for type=section"}, status_code=400)
        result = _resolve_section(act, section, depth)
    elif type == "ruling":
        if not citation:
            return JSONResponse({"error": "citation required for type=ruling"}, status_code=400)
        result = _resolve_ruling(citation, depth)
    elif type == "case":
        if not citation:
            return JSONResponse({"error": "citation required for type=case"}, status_code=400)
        result = _resolve_case(citation, depth)
    else:
        return JSONResponse({"error": f"Unknown type: {type}"}, status_code=400)

    result["meta"] = {"type": type, "depth": depth, "node_count": len(result["nodes"]), "edge_count": len(result["edges"])}
    return result