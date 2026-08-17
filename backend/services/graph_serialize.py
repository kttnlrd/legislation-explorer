"""LLM-facing serialization (graph spec §6.2).

Turns a graph node key into a token-lean block an LLM can read directly:

    ## s 118-110 itaa-1997 — Basic case
    INTERPRETED_BY: 4 rulings (TR 2025/1 | TD 2024/2 | ...)
    APPLIES: 57 private rulings (EV/1052514149928 | EV/1052018296927 | ...)
    CONSIDERED_IN: 3 cases ([1986] HCA 45 | [1996] HCA 36 | ...)

Exemplar lists are separated by " | " — verified absent from every node
label (commas and semicolons both occur inside real labels), so the block
round-trips losslessly through `parse_block`.

Rules:
- depth=1: the node's own neighbourhood, per edge type: count + top-2
  exemplars ranked by global degree (spec §6.2 "~80 tokens at depth=1").
- depth=2: appends `LEVEL 2:` — an AGGREGATED neighbourhood-of-neighbourhood
  (counts + top-3 per edge type over the top-20 neighbours by degree), NOT a
  per-node expansion (that blows the context budget per §6.3). Edges already
  counted at level 1 are excluded; exemplar labels are deduped across levels.
- Hard token cap: 80 at depth=1, 400 at depth=2 (defaults). Lines are dropped
  lowest-count-first (level-2 lines before level-1) to fit the budget; the
  header is never dropped.
- Counts are edge ROW counts (provenance-duplicated rows count separately,
  matching §6.1 / the neighbourhood index). A count is omitted only when the
  listed exemplars are exhaustive (count <= len(top)).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path

try:
    import tiktoken
except ImportError:  # service envs without tiktoken: conservative chars/3
    tiktoken = None  # type: ignore[assignment]

_ENC = tiktoken.get_encoding("cl100k_base") if tiktoken is not None else None


def _tokens(text: str) -> int:
    if _ENC is not None:
        return len(_ENC.encode(text))
    return len(text) // 3 + 1

from backend.services.graph_neighborhood import _ensure_index

logger = logging.getLogger(__name__)

GRAPH_DB = Path(__file__).resolve().parents[2] / "data" / "graph.db"

# All 10 edge types from spec §3 — lines are only emitted when count > 0.
EDGE_LABELS = {
    "interpreted_by": "INTERPRETED_BY",
    "applies": "APPLIES",
    "considered_in": "CONSIDERED_IN",
    "cites": "CITES",
    "follows": "FOLLOWS",
    "distinguishes": "DISTINGUISHES",
    "consistent_with": "CONSISTENT_WITH",
    "explained_in": "EXPLAINED_IN",
    "defines": "DEFINES",
    "related_to": "RELATED_TO",
}
LABEL_TO_EDGE = {v: k for k, v in EDGE_LABELS.items()}

TYPE_PHRASES = {
    "section": ("section", "sections"),
    "case": ("case", "cases"),
    "public_ruling": ("public ruling", "public rulings"),
    "private_ruling": ("private ruling", "private rulings"),
    "commentary": ("commentary chapter", "commentary chapters"),
    "definition": ("definition", "definitions"),
}

D1_TOP = 2          # depth=1 exemplars per edge type (spec: top-2 lists)
D2_TOP = 3          # depth=2 exemplars per edge type (spec: top-3 per level)
L2_FRONTIER = 20    # per-hop limit for the level-2 frontier (spec §4 hub guard)


def _open() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{GRAPH_DB}?mode=ro", uri=True, timeout=10)


def _level1(conn: sqlite3.Connection, nid: int, top_n: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for et, cnt, topj, ntype in conn.execute(
        "SELECT edge_type, count, top_json, target_type FROM neighborhood_index WHERE node_id=?",
        (nid,),
    ):
        out[et] = {"count": cnt, "top": json.loads(topj)[:top_n], "type": ntype}
    return out


def _level2(conn: sqlite3.Connection, nid: int, l1_row_ids: set[int], l1_top_labels: set[str]) -> dict[str, dict]:
    """Aggregated neighbourhood-of-neighbourhood.

    Frontier = top-20 neighbours of the center by global degree. Counts every
    edge row incident to the frontier EXCEPT rows already counted at level 1
    (rows touching the center); exemplars are top-3 by neighbour degree with
    level-1 labels deduped out.
    """
    nbr_ids = [r[0] for r in conn.execute(
        "SELECT node_id FROM ("
        " SELECT source_id node_id FROM graph_edges WHERE target_id=?"
        " UNION SELECT target_id FROM graph_edges WHERE source_id=?)",
        (nid, nid),
    )]
    if not nbr_ids:
        return {}
    ph = ",".join("?" * len(nbr_ids))
    deg = dict(conn.execute(
        "SELECT node_id, COUNT(*) FROM ("
        " SELECT source_id node_id FROM graph_edges"
        " UNION ALL SELECT target_id FROM graph_edges)"
        f" WHERE node_id IN ({ph}) GROUP BY node_id",
        nbr_ids,
    ).fetchall())
    frontier = sorted(nbr_ids, key=lambda i: deg.get(i, 0), reverse=True)[:L2_FRONTIER]

    phf = ",".join("?" * len(frontier))
    frontier_set = set(frontier)
    rows = conn.execute(
        f"SELECT id, source_id, target_id, edge_type FROM graph_edges "
        f"WHERE source_id IN ({phf}) OR target_id IN ({phf})",
        frontier + frontier,
    ).fetchall()

    counts: dict[str, int] = {}
    best: dict[str, dict[int, int]] = {}
    others: dict[str, set[int]] = {}
    seen: set[int] = set()
    for rid, s, t, et in rows:
        if rid in seen or rid in l1_row_ids:
            continue
        seen.add(rid)
        counts[et] = counts.get(et, 0) + 1
        other = t if s in frontier_set else s
        best.setdefault(et, {})[other] = deg.get(other, 0)
        others.setdefault(et, set()).add(other)

    # modal neighbour node_type per edge type (exact over all others, chunked)
    modal_types: dict[str, str] = {}
    for et, ids in others.items():
        freq: dict[str, int] = {}
        for i in range(0, len(ids), 900):
            chunk = list(ids)[i:i + 900]
            pht = ",".join("?" * len(chunk))
            for nt, in conn.execute(
                f"SELECT node_type FROM nodes WHERE id IN ({pht})", chunk):
                freq[nt] = freq.get(nt, 0) + 1
        if freq:
            modal_types[et] = max(freq.items(), key=lambda kv: kv[1])[0]

    top_ids = {i for m in best.values() for i, _ in sorted(m.items(), key=lambda kv: -kv[1])[:D2_TOP]}
    labels: dict[int, str] = {}
    if top_ids:
        pht = ",".join("?" * len(top_ids))
        labels = dict(conn.execute(
            f"SELECT id, label FROM nodes WHERE id IN ({pht})", list(top_ids)).fetchall())

    out: dict[str, dict] = {}
    for et, m in best.items():
        ranked = sorted(m.items(), key=lambda kv: -kv[1])
        top = [labels.get(i, str(i)) for i, _ in ranked[:D2_TOP] if labels.get(i) not in l1_top_labels]
        out[et] = {"count": counts[et], "top": top[:D2_TOP], "type": modal_types.get(et, "")}
    return out


def _format_line(et: str, info: dict) -> str:
    cnt, top = info["count"], info["top"]
    tag = EDGE_LABELS.get(et, et.upper())
    sep = " | "
    if cnt <= len(top):
        return f"{tag}: {sep.join(top)}"
    singular, plural = TYPE_PHRASES.get(info.get("type", ""), ("node", "nodes"))
    phrase = singular if cnt == 1 else plural
    return f"{tag}: {cnt} {phrase} ({sep.join(top)}{sep}...)"


def _fit_budget(entries: list[tuple[int, int, str]], max_tokens: int) -> str:
    """entries: (is_level2, count, text). Drop lowest-priority lines to fit."""
    kept = list(entries)
    while len(kept) > 1 and _tokens("\n".join(t for _, _, t in kept)) > max_tokens:
        idx = min(range(1, len(kept)), key=lambda i: (kept[i][0], kept[i][1]))
        kept.pop(idx)
    return "\n".join(t for _, _, t in kept)


def serialize(key: str, depth: int = 1, max_tokens: int | None = None) -> dict | None:
    """Return {key, label, depth, tokens, text} or None for an unknown key."""
    if depth not in (1, 2):
        raise ValueError("depth must be 1 or 2")
    if max_tokens is None:
        max_tokens = 80 if depth == 1 else 400

    conn = _open()
    try:
        _ensure_index(conn)
        row = conn.execute("SELECT id, label FROM nodes WHERE key=?", (key,)).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, label FROM nodes WHERE lower(key)=?", (key.lower(),)).fetchone()
        if row is None:
            return None
        nid, label = row

        l1 = _level1(conn, nid, D1_TOP)
        entries: list[tuple[int, int, str]] = [
            (0, 10**12, f"## {label}")  # header: never dropped (huge count)
        ]
        for et, info in sorted(l1.items(), key=lambda kv: -kv[1]["count"]):
            entries.append((0, info["count"], _format_line(et, info)))

        if depth == 2:
            l1_row_ids = {r[0] for r in conn.execute(
                "SELECT id FROM graph_edges WHERE source_id=? OR target_id=?", (nid, nid))}
            l1_top_labels = {lab for info in l1.values() for lab in info["top"]}
            l2 = _level2(conn, nid, l1_row_ids, l1_top_labels)
            if l2:
                entries.append((1, 10**12, "LEVEL 2:"))
                for et, info in sorted(l2.items(), key=lambda kv: -kv[1]["count"]):
                    entries.append((1, info["count"], _format_line(et, info)))

        text = _fit_budget(entries, max_tokens)
        return {"key": key, "label": label, "depth": depth, "tokens": _tokens(text), "text": text}
    finally:
        conn.close()


_LINE_RE = re.compile(r"^([A-Z_]+): (.+)$")
_CNT_RE = re.compile(r"^(\d+) [a-z ]+ \((.*) \| \.\.\.\)$")


def parse_block(text: str) -> dict:
    """Parse a serialized block → {header, edges, level2}.

    `edges`/`level2` map edge_type → {count, top}. Raises ValueError on
    malformed lines. Round-trip companion to `serialize` (G2 gate).

    Greedy `(.*)` + anchored suffix makes labels containing parens or commas
    parse correctly — the ellipsis is always the final list element, and " | "
    never appears inside a label.
    """
    out: dict = {"header": None, "edges": {}, "level2": {}}
    target = out["edges"]
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            out["header"] = line[3:]
            continue
        if line == "LEVEL 2:":
            target = out["level2"]
            continue
        m = _LINE_RE.match(line)
        if not m:
            raise ValueError(f"unparseable line: {line!r}")
        tag, rest = m.group(1), m.group(2).strip()
        et = LABEL_TO_EDGE.get(tag)
        if et is None:
            raise ValueError(f"unknown edge tag: {tag!r}")
        cm = _CNT_RE.match(rest)
        if cm:
            cnt = int(cm.group(1))
            top = [t.strip() for t in cm.group(2).split(" | ") if t.strip()]
            target[et] = {"count": cnt, "top": top}
        else:
            top = [t.strip() for t in rest.split(" | ") if t.strip()]
            target[et] = {"count": len(top), "top": top}
    return out


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    k = sys.argv[1] if len(sys.argv) > 1 else "section:itaa-1997:118-110"
    d = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    out = serialize(k, depth=d)
    print(json.dumps(out, indent=2) if out else f"unknown key: {k}")
