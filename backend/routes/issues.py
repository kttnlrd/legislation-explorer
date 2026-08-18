"""Issues API — list and create issues in the cadena_knowledge DB."""
from __future__ import annotations

import hashlib
import json as _json
import logging

from fastapi import APIRouter, Body, HTTPException

from backend.services.tax_case_sql import _sql_dict, _sql_write

logger = logging.getLogger(__name__)

router = APIRouter()


def _esc(v: object) -> str:
    """Escape a value for SQL string interpolation."""
    if v is None:
        return "NULL"
    s = str(v).replace("'", "''")
    return f"'{s}'"


@router.get("/api/issues")
def list_issues(status: str | None = None):
    """List issues, ordered by most recent first.

    Query params:
      status: filter by status (open, known, fixed). Omit for all.
    """
    where = ""
    if status:
        safe = status.replace("'", "''")
        where = f"WHERE status = '{safe}'"

    rows = _sql_dict(
        ["id", "ticket", "category", "tool", "params", "expected", "actual",
         "note", "server_ver", "status", "hits", "created", "fixed"],
        f"SELECT id, ticket, category, tool, params, "
        f"LEFT(COALESCE(expected, ''), 200)::text, "
        f"LEFT(COALESCE(actual, ''), 200)::text, "
        f"LEFT(COALESCE(note, ''), 200)::text, "
        f"server_ver, status, hits, created, fixed "
        f"FROM issues {where} ORDER BY id DESC",
    )

    for r in rows:
        if r.get("expected") and len(str(r["expected"])) > 200:
            r["expected"] = str(r["expected"])[:200] + "…"
        if r.get("actual") and len(str(r["actual"])) > 200:
            r["actual"] = str(r["actual"])[:200] + "…"
        if r.get("note") and len(str(r["note"])) > 200:
            r["note"] = str(r["note"])[:200] + "…"

    return {"issues": rows, "total": len(rows)}


@router.post("/api/issues")
def create_issue(
    category: str = "bug",
    tool: str | None = Body(None),
    params: str | None = Body(None),
    expected: str | None = Body(None),
    actual: str | None = Body(None),
    note: str | None = Body(None),
):
    """Create a new manual bug report in the issues table."""
    if not any(
        str(v).strip()
        for v in (tool, params, expected, actual, note)
        if v is not None
    ):
        raise HTTPException(
            status_code=422,
            detail="Issue submission must include at least one of tool, params, expected, actual, note",
        )
    max_rows = _sql_dict(["next_id"], "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM issues")
    next_id = max_rows[0]["next_id"] if max_rows else 1
    ticket = f"CDN-{next_id:04d}"

    raw = f"{tool or ''}{params or ''}{note or ''}"
    param_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    from backend.routes.api import VERSION

    _sql_write(
        "INSERT INTO issues "
        "(ticket, category, tool, params, param_hash, expected, actual, note, "
        " server_ver, created, status, hits) "
        f"VALUES ({_esc(ticket)}, {_esc(category)}, {_esc(tool)}, {_esc(params)}, "
        f"{_esc(param_hash)}, {_esc(expected)}, {_esc(actual)}, {_esc(note)}, "
        f"{_esc(VERSION)}, NOW(), 'open', 1)"
    )

    return {"ticket": ticket, "status": "open"}