"""Private rulings API.

Serves the 57,608-strong ATO private ruling corpus
(~/.hermes/private_rulings/data/json/{authnum}.json).

Endpoints:
  GET /api/private-rulings/tree          — years → counts (from index)
  GET /api/private-rulings?year=&limit=  — list by year (from index)
  GET /api/private-ruling/{authnum}      — full ruling JSON

Auth: these routes fall under the global /api bearer/SSO gate in main.py
(no whitelist entry), so they are NOT public — matches the confidentiality
of private ruling content.
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_BASE = Path(__file__).resolve().parents[2]
INDEX_PATH = _BASE / "data" / "private_rulings_index.json"

# Env override for the corpus location (matches the pipeline's HERMES_RULINGS_DIR).
_CORPUS_DIR = Path(os.environ.get(
    "HERMES_RULINGS_DIR", "/home/harrison/.hermes/private_rulings")) / "data" / "json"


@lru_cache(maxsize=1)
def _load_index() -> dict:
    try:
        data = json.loads(INDEX_PATH.read_text())
        if not isinstance(data, dict):
            logger.warning("[private-rulings] index malformed: %s", INDEX_PATH)
            return {}
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.warning("[private-rulings] cannot load index %s: %s", INDEX_PATH, exc)
        return {}


@router.get("/api/private-rulings/tree")
def private_rulings_tree():
    idx = _load_index()
    if not idx:
        return JSONResponse({"error": "private rulings index not built — "
                                      "run scripts/build_private_rulings_index.py"},
                            status_code=503)
    by_year: dict[int, int] = {}
    undated = 0
    for auth, meta in idx.items():
        y = meta.get("year")
        if y:
            by_year[y] = by_year.get(y, 0) + 1
        else:
            undated += 1
    years = [{"year": y, "count": c} for y, c in sorted(by_year.items(), reverse=True)]
    return {"total": len(idx), "undated": undated, "years": years}


@router.get("/api/private-rulings")
def private_rulings_list(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None, ge=1, le=12),
    undated: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    idx = _load_index()
    if not idx:
        return JSONResponse({"error": "private rulings index not built — "
                                      "run scripts/build_private_rulings_index.py"},
                            status_code=503)
    items = []
    for auth, meta in idx.items():
        if undated:
            if meta.get("year") is not None:
                continue
        elif year is not None and meta.get("year") != year:
            continue
        if month is not None:
            m = re.match(r"(\d{4})-(\d{2})", meta.get("date_of_advice") or "")
            if not m or int(m.group(2)) != month:
                continue
        items.append({
            "authnum": auth,
            "name": meta.get("name", ""),
            "date_of_advice": meta.get("date_of_advice", ""),
            "year": meta.get("year"),
        })
    items.sort(key=lambda x: (x["date_of_advice"] or "", x["authnum"]), reverse=True)
    return {"total": len(items), "year": year, "rulings": items[offset:offset + limit]}


@router.get("/api/private-ruling/{authnum}")
def private_ruling_detail(authnum: str):
    authnum = authnum.strip()
    if not authnum.isdigit():
        raise HTTPException(status_code=400, detail="authnum must be numeric")
    path = _CORPUS_DIR / f"{authnum}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no private ruling {authnum}")
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("[private-rulings] cannot read %s: %s", path, exc)
        raise HTTPException(status_code=500, detail="ruling file unreadable")
    # attach the canonical graph key so the frontend can show its neighbourhood
    data["graph_key"] = f"private_ruling:EV/{authnum}"
    return data
