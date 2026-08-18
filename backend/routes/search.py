from __future__ import annotations

import re
import logging
import math
import os
import sqlite3
from pathlib import Path

from fastapi import HTTPException, APIRouter

from backend.config import DATA_DIR, SEARCH_DB
from backend.services.data_loader import load_tree
from backend.services.search_service import (
    search_conn, init_search_index as build_search_index,
    search_sections as fts_search, search_rulings, search_section_ids,
)
from backend.services import vector_search_service, reranker
from backend.services.graph_neighborhood import neighborhoods as graph_neighborhoods
from backend.services.graph_alias import lookup as alias_lookup

logger = logging.getLogger(__name__)
router = APIRouter()

RRF_K = 60

# --- Graph authority boost -------------------------------------------------
# A section cited/interpreted by many rulings and cases is more likely to be
# the answer than an obscure neighbour with the same text match.
GRAPH_BOOST = float(os.getenv("GRAPH_BOOST", "0.02"))
GRAPH_DEGREE_CAP = int(os.getenv("GRAPH_DEGREE_CAP", "50"))
GRAPH_DB = Path(os.getenv("GRAPH_DB", str(Path(__file__).resolve().parents[2] / "data" / "graph.db")))

_graph_degree: dict[str, int] | None = None


def _graph_degrees() -> dict[str, int]:
    """{'section:act:id': degree} loaded once. Empty dict if graph.db is unusable."""
    global _graph_degree
    if _graph_degree is None:
        _graph_degree = {}
        try:
            conn = sqlite3.connect(f"file:{GRAPH_DB}?mode=ro", uri=True)
            try:
                # ponytail: count in Python — an OR self-join over 331k edges can't
                # use either single-column index.
                deg: dict[int, int] = {}
                for s, t in conn.execute("SELECT source_id, target_id FROM graph_edges"):
                    deg[s] = deg.get(s, 0) + 1
                    deg[t] = deg.get(t, 0) + 1
                for nid, key in conn.execute("SELECT id, key FROM nodes WHERE node_type = 'section'"):
                    _graph_degree[key.lower()] = deg.get(nid, 0)
            finally:
                conn.close()
            logger.info("[graph] loaded degree for %d section nodes from %s", len(_graph_degree), GRAPH_DB)
        except Exception as e:
            logger.warning("[graph] authority boost disabled (%s: %s)", type(e).__name__, e)
    return _graph_degree
MAX_SUGGEST = 12

SECTION_NUMBER_RE = re.compile(r'^[0-9]+(-[0-9]+)?$')

# Normalize old-format citations (e.g. "2015_FCAFC_168" → "[2015] FCAFC 168")
CITATION_NORMALIZE_RE = re.compile(r'^(\d{4})_([A-Z]+)_(\d+)$')

def _normalize_citation(s: str) -> str:
    """Convert old filename-style citation to proper format."""
    m = CITATION_NORMALIZE_RE.match(s)
    if m:
        return f"[{m.group(1)}] {m.group(2)} {m.group(3)}"
    return s


@router.get("/api/search")
def search(q: str, act: str | None = None, offset: int = 0, limit: int = 50, depth: int = 1):
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0

    if not SEARCH_DB.exists():
        build_search_index()

    q = q.strip()
    all_results = []
    exact_row = None

    if SECTION_NUMBER_RE.match(q):
        with search_conn() as conn:
            if act:
                exact_row = conn.execute(
                    "SELECT act, section, title, part, division FROM sections_meta WHERE act = ? AND section = ?",
                    (act, q)
                ).fetchone()
            else:
                exact_row = conn.execute(
                    "SELECT act, section, title, part, division FROM sections_meta WHERE section = ?",
                    (q,)
                ).fetchone()

            if exact_row:
                all_results.append({
                    "act": exact_row["act"],
                    "section": exact_row["section"],
                    "title": exact_row["title"],
                    "part": exact_row["part"],
                    "division": exact_row["division"],
                    "exact_match": True,
                })

    try:
        fts_results = fts_search(q, act, limit=500).get("results", [])
        for r in fts_results:
            if exact_row and r["act"] == exact_row["act"] and r["section"] == exact_row["section"]:
                continue
            all_results.append(r)
    except Exception:
        logger.exception("FTS search failed")

    if not all_results:
        acts_to_search = [act] if act else [d.name for d in DATA_DIR.iterdir() if d.is_dir()]
        for a in acts_to_search:
            try:
                tree = load_tree(a)
            except HTTPException:
                continue
            q_lower = q.lower()
            for part in tree.get("parts", []):
                for sec in part.get("sections", []):
                    if q_lower in sec["id"].lower() or q_lower in sec.get("title", "").lower():
                        all_results.append({"act": a, "section": sec["id"], "title": sec.get("title", "")})
                for div in part.get("divisions", []):
                    for sec in div.get("sections", []):
                        if q_lower in sec["id"].lower() or q_lower in sec.get("title", "").lower():
                            all_results.append({"act": a, "section": sec["id"], "title": sec.get("title", "")})
                    for sub in div.get("subdivisions", []):
                        for sec in sub.get("sections", []):
                            if q_lower in sec["id"].lower() or q_lower in sec.get("title", "").lower():
                                all_results.append({"act": a, "section": sec["id"], "title": sec.get("title", "")})

    total = len(all_results)
    page = all_results[offset:offset + limit]
    engine = "fallback" if not SEARCH_DB.exists() else "fts5"

    # Graph neighbourhood enrichment (spec §6.1): counts + top-3 per edge type.
    # depth is accepted now; depth=2 aggregation lands with serialization (Phase 2).
    aliases: list[dict] = []
    try:
        graph_keys = [f"section:{r['act']}:{r['section']}" for r in page if r.get("act") and r.get("section")]

        # Entity-alias resolution: the raw query and each result's citation/title/name
        # can map to a canonical graph key the FTS text match missed (e.g. a search
        # for "FBTAA section 49" or "Glenn v Federal Commissioner of Land Tax").
        alias_hits: dict[str, str] = {}

        def _probe(ref) -> None:
            if not ref:
                return
            key = alias_lookup(ref)
            if key and key not in alias_hits:
                alias_hits[key] = ref

        _probe(q)
        for r in page:
            for field in ("citation", "title", "name"):
                _probe(r.get(field))

        result_keys = set(graph_keys)
        extra_keys = [k for k in alias_hits if k not in result_keys]
        neigh = graph_neighborhoods(graph_keys + extra_keys) if (graph_keys or extra_keys) else {}
        for r in page:
            g = neigh.get(f"section:{r['act']}:{r['section']}")
            if g:
                r["graph"] = g
        for k in extra_keys:
            g = neigh.get(k)
            if g:
                aliases.append({"ref": alias_hits[k], "key": k, "graph": g})
    except Exception:
        logger.exception("[graph] neighbourhood enrichment failed — returning search without graph field")

    resp = {"results": page, "total": total, "offset": offset, "limit": limit, "engine": engine}
    if aliases:
        resp["aliases"] = aliases
    return resp


@router.get("/api/unified-search")
def unified_search(q: str, limit: int = 20):
    """Search legislation acts, CCH guides, rulings, and tax cases in one call, grouped by category."""
    from .acts import list_acts
    from .tax_cases import search_tax_cases

    q = q.strip()
    if not q:
        return {"query": q, "categories": []}

    categories = []
    for a in list_acts():
        act_id = a["id"]
        data = search(q, act=act_id, limit=limit)
        results = data.get("results", [])
        if results:
            categories.append({
                "key": act_id,
                "label": a["name"],
                "count": data.get("total", len(results)),
                "results": [
                    {"type": "section", "act": act_id, "section": r.get("section"), "title": r.get("title", "")}
                    for r in results
                ],
            })

    case_data = search_tax_cases(q, limit=limit)
    if case_data["results"]:
        categories.append({
            "key": "cases",
            "label": "Cases",
            "count": case_data["total"],
            "results": [
                {"type": "case", "citation": c.get("citation"), "title": c.get("title", ""), "court_label": c.get("court_label", "")}
                for c in case_data["results"]
            ],
        })

    return {"query": q, "categories": categories}


@router.get("/api/search/flat")
def search_flat(q: str, limit: int = 50):
    """Flat-ranked search across legislation sections AND rulings. Single FTS5 query, BM25 order."""
    q = q.strip()
    if not q:
        return {"query": q, "results": []}
    if not SEARCH_DB.exists():
        build_search_index()
    try:
        section_results = fts_search(q, act=None, limit=limit).get("results", [])
        ruling_results = search_rulings(q, limit=limit)

        # Interleave: take from both sources to show mixed results
        combined = []
        sec_idx = 0
        rul_idx = 0
        while len(combined) < limit and (sec_idx < len(section_results) or rul_idx < len(ruling_results)):
            if sec_idx < len(section_results) and (rul_idx >= len(ruling_results) or len(combined) % 2 == 0):
                r = section_results[sec_idx]
                sec_idx += 1
                combined.append({"type": "section", "act": r["act"], "section": r["section"], "title": r.get("title", ""), "snippet": r.get("snippet", "")})
            elif rul_idx < len(ruling_results):
                r = ruling_results[rul_idx]
                rul_idx += 1
                combined.append({"type": "ruling", "act": "rulings", "section": r["citation"], "title": r.get("title", ""), "snippet": r.get("snippet", "")})

        return {"query": q, "results": combined[:limit]}
    except Exception as e:
        logger.exception("Flat search failed")
        return {"query": q, "results": [], "error": str(e)}


@router.get("/api/search/suggest")
def search_suggest(q: str, limit: int = 12):
    """Quick prefix-based suggestions for autocomplete. Lightweight — titles + section numbers only."""
    q = q.strip()
    if not q or len(q) < 2:
        return {"query": q, "suggestions": []}
    if not SEARCH_DB.exists():
        build_search_index()

    results = []
    with search_conn() as conn:
        # FTS5 prefix match — append * to query for prefix mode
        prefix_q = q.replace('"', '""')
        prefix_q = f'"{prefix_q}"*'

        # Sections
        try:
            rows = conn.execute(
                "SELECT act, section, title, rank FROM sections_fts WHERE sections_fts MATCH ? ORDER BY rank LIMIT ?",
                (prefix_q, limit)
            ).fetchall()
            for r in rows:
                results.append({
                    "act": r["act"],
                    "section": r["section"],
                    "title": r["title"],
                    "type": "section",
                })
        except Exception:
            pass

        # Rulings
        try:
            rows = conn.execute(
                "SELECT citation, title, rank FROM rulings_fts WHERE rulings_fts MATCH ? ORDER BY rank LIMIT ?",
                (prefix_q, limit)
            ).fetchall()
            for r in rows:
                results.append({
                    "act": "rulings",
                    "section": r["citation"],
                    "title": r["title"],
                    "type": "ruling",
                })
        except Exception:
            pass

    # Deduplicate while preserving FTS5 rank order
    seen: set[tuple[str, str]] = set()
    deduped = []
    for r in results[:limit * 2]:
        key = (r["act"], r["section"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return {"query": q, "suggestions": deduped[:limit]}


@router.get("/api/search/hybrid")
def search_hybrid(q: str, act: str | None = None, limit: int = 20, type: str | None = None,
                  offset: int = 0, operator: str = "AND",
                  date_from: str | None = None, date_to: str | None = None):
    if limit > 50:
        limit = 50
    if offset < 0:
        offset = 0

    q = q.strip()
    if not SEARCH_DB.exists():
        build_search_index()

    if operator not in ("AND", "OR"):
        operator = "AND"

    # Parse type filter
    type_filter: set[str] | None = None
    if type:
        type_filter = set(type.lower().split(","))

    try:
        fts_results = fts_search(q, act, limit=50, operator=operator).get("results", [])
    except Exception:
        logger.exception("FTS search failed")
        fts_results = []
    # FTS results are always legislation sections — filter by type when active
    if type_filter and "section" not in type_filter:
        fts_results = []

    try:
        ruling_results = search_rulings(q, limit=50, operator=operator) if not act or act == "rulings" else []
    except Exception:
        logger.exception("Ruling FTS search failed")
        ruling_results = []
    if type_filter and "ruling" not in type_filter:
        ruling_results = []

    try:
        vector_results = vector_search_service.search(q, limit=50)
    except Exception:
        logger.exception("Vector search failed")
        vector_results = []
    if act:
        vector_results = [r for r in vector_results if r["act"] == act]
    if type_filter:
        vector_results = [r for r in vector_results if r.get("source_type", "section") in type_filter]

    # Query the PostgreSQL case database for citation/name matches
    pg_case_results: list[dict] = []
    try:
        import subprocess
        safe_q = q.replace("'", "''").replace('"', '""')
        sql = (
            "SELECT citation, case_name, court, decision_date::text FROM cases "
            f"WHERE citation ILIKE '%{safe_q}%' OR case_name ILIKE '%{safe_q}%' "
            "ORDER BY decision_date DESC LIMIT 20"
        )
        result = subprocess.run(
            ["docker", "exec", "-i", "cadena-postgres", "psql",
             "-U", "postgres", "-d", "cadena_knowledge",
             "-t", "-A", "-F", chr(1), "-c", sql],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                parts = line.split(chr(1))
                if len(parts) >= 4:
                    pg_case_results.append({
                        "act": "tax-cases",
                        "section": parts[0],
                        "title": parts[1],
                        "court": parts[2],
                        "date": parts[3] if len(parts) > 3 else "",
                        "snippet": f"{parts[1]} — Decided {parts[3]}" if parts[3] else parts[1],
                    })
    except Exception:
        logger.exception("PostgreSQL case search failed (non-fatal)")

    # Also search via FTS5 case index for better text matching on case names/summaries
    fts_case_results: list[dict] = []
    try:
        from backend.services.search_service import search_cases_fts
        for cr in search_cases_fts(q, limit=20, operator=operator):
            fts_case_results.append({
                "act": "tax-cases",
                "section": cr["citation"],
                "title": cr["case_name"],
                "court": cr.get("court", ""),
                "snippet": cr.get("case_name", ""),
            })
    except Exception:
        logger.exception("FTS5 case search failed (non-fatal)")

    if type_filter and 'case' not in type_filter:
        pg_case_results = []
        fts_case_results = []

    scores: dict[tuple[str, str], float] = {}
    merged: dict[tuple[str, str], dict] = {}

    for rank, r in enumerate(fts_results):
        key = (r["act"], r["section"])
        scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        merged.setdefault(key, {**r, "embedding_id": None, "source_type": "section"})

    for rank, r in enumerate(vector_results):
        # Normalize citation for case-type results before key computation
        vr = {**r}
        if vr.get("source_type") == "case" or vr.get("act") == "tax-cases":
            vr["section"] = _normalize_citation(vr.get("section", ""))
        key = (vr["act"], vr["section"])
        scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        existing = merged.setdefault(key, {**vr})
        existing.setdefault("embedding_id", vr["embedding_id"])
        existing.setdefault("snippet", vr["snippet"])
        existing["source_type"] = vr.get("source_type", "section")

    for rank, r in enumerate(fts_case_results):
        key = (r["act"], r["section"])
        scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        merged.setdefault(key, {**r, "source_type": "case", "type": "case"})

    for rank, r in enumerate(pg_case_results):
        key = (r["act"], r["section"])
        scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        merged.setdefault(key, {**r, "source_type": "case", "type": "case"})

    for rank, r in enumerate(ruling_results):
        key = (r["act"], r["section"])
        scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank + 1)
        merged.setdefault(key, {**r, "embedding_id": None, "source_type": "ruling"})

    # Citation-style queries ("118-110", "s 6(1)") — exact/prefix hits on the
    # section id, folded in as just another RRF list.
    if not type_filter or "section" in type_filter:
        try:
            for rank, r in enumerate(search_section_ids(q, act, limit=20)):
                key = (r["act"], r["section"])
                scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + rank + 1)
                merged.setdefault(key, {**r, "embedding_id": None, "source_type": "section"})
        except Exception:
            logger.exception("Section-id search failed (non-fatal)")

    if GRAPH_BOOST:
        degrees = _graph_degrees()
        for key in scores:
            if merged[key].get("source_type") != "section":
                continue
            d = degrees.get(f"section:{key[0]}:{key[1]}".lower(), 0)
            if d:
                scores[key] += GRAPH_BOOST * (1 + math.log(1 + min(d, GRAPH_DEGREE_CAP)))

    ranked_keys = sorted(scores, key=lambda k: -scores[k])
    total = len(ranked_keys)

    # Date-range filter — applies to dated items (rulings by year, cases by
    # decision date). Undated items are kept; dated items outside the window
    # are dropped. Sections have no date and are unaffected.
    if date_from or date_to:
        def _item_date(key) -> str | None:
            item = merged[key]
            st = item.get("source_type")
            if st == "ruling":
                y = item.get("year")
                return f"{y}-01-01" if y else None
            if st == "case":
                d = item.get("date") or item.get("decision_date")
                if d:
                    return str(d)[:10]
                y = item.get("year")
                return f"{y}-01-01" if y else None
            return None

        kept = []
        for key in ranked_keys:
            d = _item_date(key)
            if d:
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
            kept.append(key)
        ranked_keys = kept
        total = len(ranked_keys)

    # Rerank the top candidates, then slice — pagination semantics (total) unchanged.
    # `score`/`fusion_score` stay the RRF score; rerank only affects ordering.
    reranked = False
    candidates = ranked_keys[:reranker.RERANK_CANDIDATES]
    rr = reranker.rerank(
        q,
        [f"{merged[k].get('title', '')} {merged[k].get('snippet', '')}" for k in candidates],
        limit,
    )
    if rr is not None:
        reranked = True
        order = sorted(range(len(candidates)), key=lambda i: -rr[i])  # stable: unscored keep RRF order
        ranked_keys = [candidates[i] for i in order] + ranked_keys[len(candidates):]

    ranked_keys = ranked_keys[offset:offset + limit]
    results = []
    for key in ranked_keys:
        r = merged[key]
        r["fusion_score"] = scores[key]
        emb_id = r.get("embedding_id")
        r["cross_references"] = vector_search_service.get_cross_references(emb_id) if emb_id else []
        results.append(r)

    return {"results": results, "total": total, "offset": offset, "limit": limit,
            "meta": {"reranked": reranked}}
