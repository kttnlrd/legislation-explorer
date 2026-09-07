"""FastMCP server for Legislation Explorer — replaces old mcp_server.py.

Mount via streamable_http_app() on the main FastAPI app.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re as _re
import sqlite3
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from backend.config import DATA_DIR, TREATIES_DIR
from backend.mcp_token_manager import token_manager
from backend.routes.api import VERSION, CHANGELOG
from backend.routes.rulings import get_ruling as _get_ruling
from backend.services.graph_alias import lookup as alias_lookup
from backend.services.data_loader import (
    load_tree,
    load_rulings,
    get_definition_text,
    get_definition_across_acts,
)
from backend.services.text_cleaner import strip_scraped_markup
from backend.services.search_service import search_sections as fts_search, search_rulings, search_conn

from backend.routes.regulatory_guides import (
    _load_rg_section_index,
)
from backend.services.case_db_service import (
    build_download_urls,
    get_case_metadata,
    get_case_references,
)
from backend.services.tax_case_sql import _sql, _sql_dict, _sql_write_params

logger = logging.getLogger(__name__)

# Appended to error/null returns of data tools: tells the LLM to re-check
# get_info (query formats, citation conventions, routing) before giving up.
_GET_INFO_HINT = (
    "If this result is unexpected, call get_info to review query formats, "
    "citation conventions, and tool routing, then retry."
)

# Public hostnames that hit this server via Cloudflare Tunnel / Caddy.
# FastMCP auto-enables DNS-rebinding protection for localhost host defaults and
# only allows 127.0.0.1:*/localhost:* — public Host headers then get 421.
_MCP_ALLOWED_HOSTS = [
    "127.0.0.1:*",
    "localhost:*",
    "[::1]:*",
    "legislation.scriptkitty.yachts",
    "legislation.scriptkitty.yachts:*",
    "rpc.scriptkitty.yachts",
    "rpc.scriptkitty.yachts:*",
    "mcp.scriptkitty.yachts",
    "mcp.scriptkitty.yachts:*",
    "dev.scriptkitty.yachts",
    "dev.scriptkitty.yachts:*",
]

# Public base for absolute download links in tool output. Override via env for
# non-prod hosts (e.g. LEGISLATION_PUBLIC_BASE=https://dev.scriptkitty.yachts).
_PUBLIC_BASE = os.environ.get("LEGISLATION_PUBLIC_BASE", "https://legislation.scriptkitty.yachts").rstrip("/")

def _abs(path: str) -> str:
    """Turn a relative API path into an absolute public URL."""
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return f"{_PUBLIC_BASE}{path if path.startswith('/') else '/' + path}"
_MCP_ALLOWED_ORIGINS = [
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
    "https://legislation.scriptkitty.yachts",
    "https://rpc.scriptkitty.yachts",
    "https://mcp.scriptkitty.yachts",
    "https://dev.scriptkitty.yachts",
]

# FastMCP sub-app — Mount strips /mcp prefix, so route must be at "/"
mcp = FastMCP(
    "legislation-explorer",
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_MCP_ALLOWED_HOSTS,
        allowed_origins=_MCP_ALLOWED_ORIGINS,
    ),
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_CASE_CITATION_RE = _re.compile(r'\[(\d{4})\]\s*([A-Z]+(?:\s*[A-Z]+)*)\s*(\d+(?:[-–]\d+)*)')

_CASE_CITATION_BRACKETLESS_RE = _re.compile(r'(\d{4})\s+([A-Z]+(?:\s*[A-Z]+)*)\s+(\d+(?:[-–]\d+)*)')

# Report-series -> medium-neutral alias map (data/atc_alias_map.json).
# Populated only with individually verified case pairs — never mass-generated.
@functools.lru_cache(maxsize=1)
def _load_case_citation_aliases() -> dict:
    p = DATA_DIR / "atc_alias_map.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _resolve_case_citation_alias(citation_norm: str) -> str:
    """Map a normalised report-series citation to its canonical medium-neutral
    citation when a verified alias exists (e.g. '[2009] ATC 1-016' ->
    '[2009] AATA 805'). Returns the input unchanged when no alias is known."""
    if not citation_norm:
        return citation_norm
    return _load_case_citation_aliases().get(citation_norm, citation_norm)

def _normalise_case_citation(raw: str) -> str | None:
    m = _CASE_CITATION_RE.search(raw)
    if m:
        return f"[{m.group(1)}] {m.group(2)} {m.group(3)}"
    m = _CASE_CITATION_BRACKETLESS_RE.search(raw)
    if m:
        return f"[{m.group(1)}] {m.group(2)} {m.group(3)}"
    return None

# ---------------------------------------------------------------------------
# Auth middleware — applied to the streamable_http_app in main.py
# ---------------------------------------------------------------------------

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.requests import Request
import json

# OAuth token validation
from backend.oauth_provider import provider as oauth_provider


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """Token auth + rate limiting for MCP endpoints.

    Accepts token from:
      - Authorization: Bearer ***
      - X-API-Key: *** (alternative to Bearer, for Cloudflare WAF bypass)
      - ?token=<token> query param
      - /mcp/<token>  path segment (bypasses Cloudflare WAF)
    Skips auth when DEV_MODE=true.
    """

    async def dispatch(self, request: Request, call_next):
        if os.environ.get("DEV_MODE", "").lower() in ("true", "1", "yes"):
            return await call_next(request)

        token = ""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            token = request.headers.get("X-API-Key", "")
        if not token:
            token = request.query_params.get("token", "")
        if not token:
            token = request.query_params.get("v", "")
        if not token:
            token = request.query_params.get("_auth", "")
        if not token:
            token = request.query_params.get("x", "")
        # Path-segment token: /mcp/<token>
        if not token:
            path = request.url.path
            if path.startswith("/api/cadena/mcp/") and len(path) > 16:
                token = path.split("/api/cadena/mcp/", 1)[-1].split("?")[0].split("/")[0]
            elif path.startswith("/api/private/mcp/") and len(path) > 18:
                token = path.split("/api/private/mcp/", 1)[-1].split("?")[0].split("/")[0]
            elif path.startswith("/mcp/") and len(path) > 5:
                token = path.split("/mcp/", 1)[-1].split("?")[0].split("/")[0]
            elif path.startswith("/api/rpc/") and len(path) > 10:
                token = path.split("/api/rpc/", 1)[-1].split("?")[0].split("/")[0]

        # Body-based auth (JSON-RPC params._auth) — bypasses Cloudflare WAF
        if not token:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body = json.loads(body_bytes)
                    params = body.get("params", {})
                    if isinstance(params, dict):
                        token = params.get("_auth", "") or params.get("token", "")
            except Exception:
                pass

        # Cookie-based auth — Cloudflare doesn't inspect cookies as credentials
        if not token:
            token = request.cookies.get("token", "")

        # Custom header auth — X-Session-Id bypasses Cloudflare DDoS
        if not token:
            token = request.headers.get("X-Session-Id", "")

        if not token:
            return Response("Missing token", status_code=401,
                            headers={"WWW-Authenticate": "Bearer"})

        if not token_manager.validate_token(token):
            # Fallback: try static MCP_AUTH_TOKEN from env
            mcp_auth_token = os.environ.get("MCP_AUTH_TOKEN", "") or os.environ.get("LEGISLATION_BEARER_TOKEN", "")
            if mcp_auth_token and token == mcp_auth_token:
                pass  # valid
            else:
                # Fallback: try OAuth access token
                oauth_data = oauth_provider.load_access_token(token)
                if not oauth_data:
                    return Response("Invalid or revoked token", status_code=403)

        allowed, reason = token_manager.check_rate_limit(token)
        if not allowed:
            return Response(reason, status_code=429)

        return await call_next(request)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(structured_output=False)
async def search_legislation(
    query: str,
    act: str | None = None,
    limit: int = 20,
) -> str:
    """Search legislation sections by keyword or section number.

    All query terms must appear in section text (AND matching).
    Section-number-shaped queries (e.g. '8-1') are exact-matched
    to rank the cited section first.
    """
    result = fts_search(query.strip(), act, limit=min(100, max(1, limit)))
    return json.dumps({
        "query": query,
        "total": result["total_count"],
        "results": result["results"],
    }, indent=2)


_ALIAS_PATTERNS: list[tuple[_re.Pattern, str, str | None, str, str | None, str | None]] = [
    # (compiled_regex, act_id, resolved_ref, display_act, description, url_suffix)
    # Order matters: more specific patterns first.

    # --- ITAA 1936 well-known aliases ---
    (
        _re.compile(r'^(?:s(?:ec(?:tion)?)?\.?\s*)?(?:div(?:ision)?\.?\s*)?7[AEae](?:\s|$)', _re.IGNORECASE),
        "itaa-1936",
        "Division 7A",
        "ITAA 1936",
        "Division 7A — Private company dividends (ss 109Y–109ZQ)",
        "itaa-1936#Division_7A",
    ),
    (
        _re.compile(r'^(?:s(?:ec(?:tion)?)?\.?\s*)?100[AEae](?:\s|$)', _re.IGNORECASE),
        "itaa-1936",
        "100A",
        "ITAA 1936",
        "s 100A — Reimbursement agreements",
        "itaa-1936#100A",
    ),
    (
        _re.compile(r'^(?:s(?:ec(?:tion)?)?\.?\s*)?Part IV[AEae](?:\s|$)', _re.IGNORECASE),
        "itaa-1936",
        "Part IVA",
        "ITAA 1936",
        "Part IVA — General anti-avoidance rules (ss 177A–177P)",
        "itaa-1936#Part_IVA",
    ),
    (
        _re.compile(r'^(?:s(?:ec(?:tion)?)?\.?\s*)?109[YZ](?:\s|$)', _re.IGNORECASE),
        "itaa-1936",
        None,  # will resolve specific section via exact match fallback
        "ITAA 1936",
        None,
        None,
    ),
    # --- ITAA 1997 well-known aliases ---
    (
        _re.compile(r'^(?:s(?:ec(?:tion)?)?\.?\s*)?(?:Subdiv(?:ision)?\.?\s*)?115-C(?:\s|$)', _re.IGNORECASE),
        "itaa-1997",
        "Subdivision 115-C",
        "ITAA 1997",
        "Subdivision 115-C — Net capital gain (ss 115-215 to 115-228)",
        "itaa-1997#Subdivision_115-C",
    ),
    (
        _re.compile(r'^(?:s(?:ec(?:tion)?)?\.?\s*)?(?:Div(?:ision)?\.?\s*)?152(?:\s|$)', _re.IGNORECASE),
        "itaa-1997",
        "Division 152",
        "ITAA 1997",
        "Division 152 — Small business relief (ss 152-1 to 152-430)",
        "itaa-1997#Division_152",
    ),
]


# ── Hyphenated section routing helpers ─────────────────────────────

@functools.lru_cache(maxsize=8)
def _get_act_section_ids(act: str) -> set[str]:
    """Return a set of all section, division, and subdivision IDs in an act."""
    from backend.services.data_loader import load_tree
    try:
        tree = load_tree(act)
    except Exception:
        return set()
    ids: set[str] = set()
    for part in tree.get("parts", []):
        for sec in part.get("sections", []):
            ids.add(sec.get("id", ""))
        for div in part.get("divisions", []):
            ids.add(div.get("id", ""))  # collect division IDs too (e.g. "Division 7A")
            for sec in div.get("sections", []):
                ids.add(sec.get("id", ""))
            for sub in div.get("subdivisions", []):
                ids.add(sub.get("id", ""))  # collect subdivision IDs too
                for sec in sub.get("sections", []):
                    ids.add(sec.get("id", ""))
    return ids


def _resolve_hyphenated_act(bare: str) -> str:
    """Probe candidate acts to find which one contains the given hyphenated section.
    Prefers non-ITAA1997 acts when a section exists in multiple (e.g. 195-1 is in
    both itaa-1997 and gst-1999 — the GST Act is the correct one)."""
    candidates = ["gst-1999", "taa-1953", "itaa-1997"]
    found = [act for act in candidates if bare in _get_act_section_ids(act)]
    if not found:
        return "itaa-1997"  # fallback
    # If found in only one act, use it
    if len(found) == 1:
        return found[0]
    # If found in multiple, prefer the first non-itaa-1997 hit
    for act in found:
        if act != "itaa-1997":
            return act
    return "itaa-1997"


def _section_exists_in_act(act: str, section_id: str) -> bool:
    """Check if a section ID exists in the given act's tree via section-index lookup.

    Returns True if the section exists in the act, False otherwise.
    Used to prevent pattern-based alias resolution from returning false positives
    for non-existent references.
    
    Normalizes 'Division X' → bare 'X' to match tree IDs.
    """
    if not section_id or not act:
        return False
    ids = _get_act_section_ids(act)
    if section_id in ids:
        return True
    # Try normalized form: "Division 7A" → "7A", "Part IVA" → "IVA"
    for prefix in ("Division ", "Part ", "Subdivision "):
        if section_id.startswith(prefix):
            normalized = section_id[len(prefix):]
            if normalized in ids:
                return True
    return False


@mcp.tool(structured_output=False)
async def resolve_alias(reference: str) -> str:
    """Resolve a section alias or short-hand reference to its act and section number.

    Handles common shorthand: 's 100A', 'Div 7A', 'Part IVA', 'Subdiv 115-C',
    '109Y', '8-1', 'Div 152', etc.

    Rules:
    - Div 7A          → ITAA 1936, Division 7A (ss 109Y-109ZQ)
    - s 100A          → ITAA 1936, s 100A
    - Part IVA        → ITAA 1936, Part IVA (ss 177A-177P)
    - Subdiv 115-C    → ITAA 1997, Subdivision 115-C (ss 115-215 to 115-228)
    - Simple section numbers like 109Y → ITAA 1936, s 109Y
    - Section-number-shaped like 8-1   → ITAA 1997, s 8-1
    - Div 152         → ITAA 1997, Division 152

    Falls back to search_legislation when no rule matches.
    """
    ref = reference.strip()
    if not ref:
        return json.dumps({"error": "Empty reference provided.", "hint": _GET_INFO_HINT})

    # -- Step 1: Check well-known patterns --
    for pattern, act, resolved_ref, display_act, description, url_suffix in _ALIAS_PATTERNS:
        if pattern.match(ref):
            if resolved_ref is None and description is None:
                # Partial match that needs fallback but act is known
                # e.g. 109* — resolve via search
                break
            # Validate the resolved section actually exists in the act's tree
            if resolved_ref is None or not _section_exists_in_act(act, resolved_ref):
                # Section doesn't exist — fall through to search
                break
            return json.dumps({
                "reference": ref,
                "act": act,
                "act_display": display_act,
                "section": resolved_ref,
                "description": description,
                "url": f"https://legislation.scriptkitty.yachts/{url_suffix}" if url_suffix else None,
                "resolved_by": "exact_rule",
            }, indent=2)

    # -- Step 2: Try regex-based routing for common patterns not in the well-known list --

    # 'Div X' or 'Division X' → ITAA 1997 (by default, but could be either)
    m = _re.match(r'^(?:div(?:ision)?\.?\s*)(\S+)$', ref, _re.IGNORECASE)
    if m:
        div = m.group(1)
        return json.dumps({
            "reference": ref,
            "act": "itaa-1997",
            "act_display": "ITAA 1997",
            "section": f"Division {div}",
            "description": f"Division {div} — resolved from bare division reference (defaulting to ITAA 1997)",
            "url": f"https://legislation.scriptkitty.yachts/itaa-1997#Division_{div}",
            "resolved_by": "division_pattern",
            "note": "Division references are assumed ITAA 1997 by default. If you need ITAA 1936, use 's 109Y' format instead.",
        }, indent=2)

    # 'Part X' or 'Part X-Y' → ITAA 1936
    m = _re.match(r'^(?:Part\s+)([A-Za-z0-9]+(?:[-][A-Za-z0-9]+)?)$', ref, _re.IGNORECASE)
    if m:
        part = m.group(1)
        act_id = "itaa-1936"
        act_display = "ITAA 1936"
        # If it has a hyphen (e.g. "Part 3-1"), it's ITAA 1997
        if '-' in part:
            act_id = "itaa-1997"
            act_display = "ITAA 1997"
        return json.dumps({
            "reference": ref,
            "act": act_id,
            "act_display": act_display,
            "section": f"Part {part}",
            "description": f"Part {part} — resolved from bare Part reference",
            "url": f"https://legislation.scriptkitty.yachts/{act_id}#Part_{part}",
            "resolved_by": "part_pattern",
        }, indent=2)

    # 'Subdiv X' or 'Subdivision X' → ITAA 1997
    m = _re.match(r'^(?:subdiv(?:ision)?\.?\s+)(\S+)$', ref, _re.IGNORECASE)
    if m:
        subdiv = m.group(1)
        return json.dumps({
            "reference": ref,
            "act": "itaa-1997",
            "act_display": "ITAA 1997",
            "section": f"Subdivision {subdiv}",
            "description": f"Subdivision {subdiv} — resolved from bare subdivision reference",
            "url": f"https://legislation.scriptkitty.yachts/itaa-1997#Subdivision_{subdiv}",
            "resolved_by": "subdivision_pattern",
        }, indent=2)

    # Strip leading 's', 'sec', 'section' prefix
    bare = _re.sub(r'^(?:s(?:ec(?:tion)?)?\.?\s+)', '', ref, flags=_re.IGNORECASE).strip()

    # Section-number-shaped with hyphen → probe across candidate acts
    if _re.match(r'^\d+[-]\d+[A-Za-z0-9]*$', bare):
        act_id = _resolve_hyphenated_act(bare)
        act_display = {
            "itaa-1997": "ITAA 1997", "gst-1999": "GST Act", "taa-1953": "TAA 1953"
        }.get(act_id, "ITAA 1997")
        # Validate the section actually exists in the resolved act's tree
        if _section_exists_in_act(act_id, bare):
            return json.dumps({
                "reference": ref,
                "act": act_id,
                "act_display": act_display,
                "section": bare,
                "description": f"s {bare} — hyphenated section number routed to {act_display}",
                "url": f"https://legislation.scriptkitty.yachts/get_section?act={act_id}&section={bare}",
                "resolved_by": "hyphenated_section_pattern",
            }, indent=2)

    # Unhyphenated alphanumeric section → ITAA 1936 style (e.g. '109Y', '100A', '23AH')
    if _re.match(r'^[A-Za-z0-9]+$', bare):
        # Validate the section actually exists in ITAA 1936 before returning
        if _section_exists_in_act("itaa-1936", bare):
            return json.dumps({
                "reference": ref,
                "act": "itaa-1936",
                "act_display": "ITAA 1936",
                "section": bare,
                "description": f"s {bare} — unhyphenated section routed to ITAA 1936",
                "url": f"https://legislation.scriptkitty.yachts/get_section?act=itaa-1936&section={bare}",
                "resolved_by": "unhyphenated_section_pattern",
            }, indent=2)

    # -- Step 3: Entity alias map (21,548 LLM-mapped refs, e.g. "FBTAA section 49",
    #    "Glenn v Federal Commissioner of Land Tax") — verified against graph.db --
    try:
        key = alias_lookup(ref)
        if key:
            return json.dumps({
                "reference": ref,
                "graph_key": key,
                "resolved_by": "entity_alias_map",
                "note": "Resolved via entity alias map (pipeline.entity_backstop). "
                        "Use graph_neighbourhood for the node's context block.",
            }, indent=2)
    except Exception:
        pass

    # -- Step 4: Fallback to full-text search --
    try:
        result = fts_search(ref, None, limit=5)
        hits = result.get("results", [])
        if hits:
            best = hits[0]
            return json.dumps({
                "reference": ref,
                "act": best.get("act", ""),
                "act_display": best.get("act", ""),
                "section": best.get("section", ""),
                "description": best.get("title", ""),
                "url": f"https://legislation.scriptkitty.yachts/get_section?act={best.get('act', '')}&section={best.get('section', '')}",
                "resolved_by": "search_fallback",
                "search_results": [
                    {
                        "act": h.get("act", ""),
                        "section": h.get("section", ""),
                        "title": h.get("title", ""),
                    }
                    for h in hits[:3]
                ],
            }, indent=2)
    except Exception:
        pass

    return json.dumps({
        "reference": ref,
        "error": f"Could not resolve reference '{ref}'. Try search_legislation or a more specific format.",
        "hint": _GET_INFO_HINT,
    }, indent=2)


def _display_case_citation(c: str) -> str:
    """'1940_HCA_33' -> '[1940] HCA 33' (medium-neutral, tool-usable by get_case)."""
    if not c:
        return c
    if "[" in c:  # already medium-neutral
        return c
    return _normalise_case_citation(c.replace("_", " ")) or c


def _display_ruling_citation(c: str) -> str:
    """'AID_2002_46' -> 'AID 2002/46'; 'TR_2024_1' -> 'TR 2024/1'."""
    if not c:
        return c
    m = _re.match(r'^([A-Z]+(?:_[A-Z]+)*)_(\d{4})_(\d+)$', c)
    if m:
        return f"{m.group(1)} {m.group(2)}/{m.group(3)}"
    return c


_GRAPH_DB = DATA_DIR / "graph.db"

_PUB_DISPLAY = {
    "master-tax-guide": "Master Tax Guide",
    "master-gst-guide": "Master GST Guide",
    "master-tax-examples": "Master Tax Examples",
}


def _graph_commentary_for_section(act: str, section: str, limit: int = 10) -> list[dict]:
    """Commentary linked to a section via graph `explained_in` edges.

    Replaces the archived commentary_index path (get_commentary_for_section):
    that index is stale relative to graph.db — e.g. s109C had zero archive
    entries while the graph carries 2 explained_in commentary nodes.

    Returns entries shaped for get_section's related.commentary block:
    publication, chapter_number, chapter_title, heading_title, url, snippet
    (+ content when include_commentary=True is handled by the caller).
    """
    if not _GRAPH_DB.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{_GRAPH_DB}?mode=ro", uri=True, timeout=10)
        try:
            row = conn.execute(
                "SELECT id FROM nodes WHERE key=?", (f"section:{act}:{section}",)
            ).fetchone()
            if row is None:
                return []
            cid = row[0]
            rows = conn.execute(
                """
                SELECT n.key AS nkey, n.label AS nlabel, n.content_ref
                FROM graph_edges e
                JOIN nodes n ON n.id = CASE WHEN e.source_id=? THEN e.target_id ELSE e.source_id END
                WHERE (e.source_id=? OR e.target_id=?)
                  AND e.edge_type='explained_in' AND n.node_type='commentary'
                GROUP BY n.id
                ORDER BY e.weight DESC
                LIMIT ?
                """,
                (cid, cid, cid, limit),
            ).fetchall()
            out = []
            for nkey, nlabel, content_ref in rows:
                entry = _graph_commentary_entry(nkey, nlabel, content_ref)
                if entry:
                    out.append(entry)
            return out
        finally:
            conn.close()
    except Exception:
        return []


def _graph_commentary_entry(nkey: str, nlabel: str, content_ref: str | None) -> dict | None:
    """Build a related.commentary entry from a commentary graph node.

    key format: commentary:<publication>:ch-<n>/<section-slug>
    e.g. commentary:master-tax-examples:ch-10/10-240-division-7a-...
    """
    try:
        _, pub, path = nkey.split(":", 2)
    except ValueError:
        return None
    if "/" not in path:
        return None  # chapter-level node has no single section target
    ch_part, slug = path.split("/", 1)
    if not slug:
        return None
    snippet = ""
    if content_ref:
        md_path = DATA_DIR / content_ref.removeprefix("data/")
        try:
            body = md_path.read_text(encoding="utf-8")
            if body.startswith("---"):
                fm_end = _re.search(r"\n---\s*\n", body)
                if fm_end:
                    body = body[fm_end.end():]
            body = _re.sub(r"\n---\s*\*Last updated:.*?\*", "", body, flags=_re.DOTALL)
            body = _re.sub(r"\n---\s*$", "", body)
            body = strip_scraped_markup(body).strip()
            body = _re.sub(r"^#\s+.*\n+", "", body)  # drop H1 (already in heading_title)
            snippet = body[:500]
        except Exception:
            snippet = ""
    return {
        "publication": _PUB_DISPLAY.get(pub, pub),
        "chapter_number": ch_part.removeprefix("ch-"),
        "chapter_title": "",
        "heading_title": nlabel,
        "url": f"/{pub}/{slug}",
        "snippet": snippet,
        "content_ref": content_ref,
    }


def _graph_edges_to(act: str, section: str, edge_type: str, node_type: str, limit: int = 10) -> list[tuple[str, str, str]]:
    """Graph neighbours of a section node: (key, label, meta_json).

    Shared by cases/rulings/commentary lookups — single read-only connection,
    exact key match only (graph keys are canonical).
    """
    if not _GRAPH_DB.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{_GRAPH_DB}?mode=ro", uri=True, timeout=10)
        try:
            row = conn.execute(
                "SELECT id FROM nodes WHERE key=?", (f"section:{act}:{section}",)
            ).fetchone()
            if row is None:
                return []
            cid = row[0]
            rows = conn.execute(
                """
                SELECT n.key AS nkey, n.label AS nlabel, n.meta AS nmeta
                FROM graph_edges e
                JOIN nodes n ON n.id = CASE WHEN e.source_id=? THEN e.target_id ELSE e.source_id END
                WHERE (e.source_id=? OR e.target_id=?)
                  AND e.edge_type=? AND n.node_type=?
                GROUP BY n.id
                ORDER BY e.weight DESC
                LIMIT ?
                """,
                (cid, cid, cid, edge_type, node_type, limit),
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def _graph_cases_for_section(act: str, section: str, limit: int = 10) -> list[dict]:
    """Cases linked to a section via graph `considered_in` edges."""
    cases = _load_cases_map()
    out = []
    for key, label, meta_json in _graph_edges_to(act, section, "considered_in", "case", limit):
        citation = key.split(":", 1)[1] if ":" in key else key
        meta = {}
        try:
            meta = json.loads(meta_json or "{}")
        except Exception:
            pass
        out.append({
            "type": "case",
            "citation": citation,
            "title": cases.get(citation, {}).get("title") or label,
            "court": meta.get("court") or "",
        })
    return out


def _graph_rulings_for_section(act: str, section: str, limit: int = 10) -> list[dict]:
    """Public rulings linked to a section via graph `interpreted_by` edges.

    `applies` edges to public rulings are parallel duplicates of
    `interpreted_by` (provenance-verified), so they're not double-counted.
    Private rulings are returned separately via `applies` → private_ruling.
    """
    rulings = _load_rulings_map()
    out = []
    for key, label, _meta in _graph_edges_to(act, section, "interpreted_by", "public_ruling", limit):
        citation = key.split(":", 1)[1] if ":" in key else key
        title = ""
        # Ruling file stems use several conventions: TR_2014_5 (space→_), PSLA_2007_20 (space dropped), ATOID_2012_3.
        candidates = {
            citation,
            citation.replace("ATOID ", "AID "),
            citation.replace("ATOID_", "AID_", 1),
            citation.replace(" ", "_").replace("/", "_").replace("-", "_"),
            citation.replace(" ", "").replace("/", "_").replace("-", "_"),
        }
        r = None
        title = ""
        for cand in candidates:
            r = rulings.get(cand)
            if r:
                title = r.get("full_title") or r.get("title") or ""
                break
        dl_citation = _re.sub(r"[\s/]+", "_", citation).strip("_")
        out.append({
            "type": "ruling",
            "citation": citation,
            "title": title or label,
            "ato_url": r.get("ato_url", "") if r else "",
            "austlii_url": r.get("austlii_url", "") if r else "",
            "download_url": _abs(f"/api/ruling/{dl_citation}/download"),
        })
    return out


def _graph_private_rulings_for_section(act: str, section: str, limit: int = 10) -> list[dict]:
    """Private rulings linked to a section via graph `applies` edges."""
    out = []
    for key, label, _meta in _graph_edges_to(act, section, "applies", "private_ruling", limit):
        auth = key.rsplit("/", 1)[-1]
        out.append({
            "type": "private_ruling",
            "auth_number": auth,
            "label": label if label.startswith("EV/") else f"EV/{auth}",
            "url": f"/private-rulings/{auth}",
            "ato_url": (f"https://www.ato.gov.au/law/view/print"
                        f"?DocID=EV/{auth}&PiT=99991231235958"),
            "download_url": _abs(f"/api/private-ruling/{auth}/download"),
        })
    return out


@functools.lru_cache(maxsize=1)
def _load_cases_map() -> dict[str, dict]:
    from backend.services.data_loader import load_cases
    return {c.get("citation", ""): c for c in load_cases()}


@functools.lru_cache(maxsize=1)
def _load_rulings_map() -> dict[str, dict]:
    from backend.services.data_loader import load_rulings
    out: dict[str, dict] = {}
    for r in load_rulings():
        out[r.get("citation", "")] = r
        out[r.get("citation", "").replace("ATOID_", "AID_", 1)] = r
    return out


def _tree_same_division(tree: dict, section: str) -> list[dict]:
    """Sections in the same part/division/subdivision of an act tree.

    The graph deliberately has no section→section edges, so related sections
    come from the act tree (the graph's own structural source). Returns the
    same shape as the retired smartlink index: {id, type, score, reason}.
    """
    target = section.split("(")[0].strip().upper()

    def _ids(secs: list[dict]) -> list[str]:
        return [str(s.get("id", "")).split("(")[0].strip().upper()
                for s in secs if s.get("id")]

    def _shape(sids: list[str]) -> list[dict]:
        seen: list[str] = []
        for sid in sids:
            if sid and sid != target and sid not in seen:
                seen.append(sid)
        return [{"id": sid, "type": "section", "score": 0.4,
                 "reason": "same part/division"} for sid in seen]

    for part in tree.get("parts", []):
        part_ids = _ids(part.get("sections", []))
        if target in part_ids:
            return _shape(part_ids)
        for div in part.get("divisions", []):
            div_ids = _ids(div.get("sections", []))
            for sub in div.get("subdivisions", []):
                div_ids += _ids(sub.get("sections", []))
            if target in div_ids:
                return _shape(div_ids)
    return []


@mcp.tool(structured_output=False)
async def get_section(act: str, section: str, max_body_length: int = 50000,
                      include_commentary: bool = False) -> str:
    """Retrieve full text of a legislation section with related cases, rulings, and commentary.

    Leading s/sec/section is stripped automatically. Uses hyphenated format
    (8-1) for ITAA 1997/GST/TAA; unhyphenated (23AH) for ITAA 1936.

    If the exact section is not found, falls back to search and returns
    "did you mean?" suggestions with the top 3 matching results.

    Parameters:
    - act: Act ID (e.g. itaa-1997, gst-1999, taa-1953)
    - section: Section number (e.g. 8-1, 23AH, 995-1)
    - max_body_length: Maximum number of characters for the body text (default 50000)
    - include_commentary: Whether to include full commentary text (default False).
      When False, commentary returns a 500-char snippet + locator.
    """
    section = _re.sub(r'^(?:s(?:ec(?:tion)?)?\.?)\s+', '', section.strip(),
                      flags=_re.IGNORECASE).strip()

    if _re.match(r'^\d+(\.\d)', section):
        return json.dumps({
            "error": f"Section '{section}' not found. Use hyphenated format (e.g. 8-1) not dotted (8.1).",
            "hint": _GET_INFO_HINT
        })

    has_hyphen = '-' in section
    is_1936 = act == 'itaa-1936'
    if has_hyphen and is_1936:
        # Schedule 2D sections (e.g. 57-1, 326-160) ARE hyphenated in ITAA 1936.
        # Only auto-route to itaa-1997 if the section is genuinely absent here.
        if section in _get_act_section_ids('itaa-1936'):
            pass  # legit Schedule 2D section — fall through to normal tree lookup
        else:
            # Try auto-routing to itaa-1997 and also search for suggestions
            suggestions = fts_search(section, None, limit=3)
            hits = suggestions.get("results", [])
            payload = {
                "error": f"Section {section} not found in itaa-1936; ITAA 1936 sections are unhyphenated (e.g. 23AH). Did you mean itaa-1997 s {section}?",
                "hint": _GET_INFO_HINT
            }
            if hits:
                payload["did_you_mean"] = [
                    {"act": h["act"], "section": h["section"], "title": h.get("title", "")}
                    for h in hits
                ]
            return json.dumps(payload)

    tree = load_tree(act)
    section_path = None
    for part in tree.get("parts", []):
        for sec in part.get("sections", []):
            if sec["id"] == section:
                section_path = sec["path"]
                break
        if section_path:
            break
        for div in part.get("divisions", []):
            for sec in div.get("sections", []):
                if sec["id"] == section:
                    section_path = sec["path"]
                    break
            if not section_path:
                for sub in div.get("subdivisions", []):
                    for sec in sub.get("sections", []):
                        if sec["id"] == section:
                            section_path = sec["path"]
                            break
            if section_path:
                break
        if section_path:
            break

    if not section_path:
        for md in (DATA_DIR / act / "sections").rglob(f"{section}.md"):
            section_path = str(md.relative_to(DATA_DIR / act / "sections"))
            break

    if not section_path:
        # Fallback: search and suggest (try without act filter for cross-act searches)
        suggestions = fts_search(section, act, limit=3)
        hits = suggestions.get("results", [])
        if not hits:
            suggestions = fts_search(section, None, limit=3)
            hits = suggestions.get("results", [])
        if hits:
            return json.dumps({
                "error": f"Section '{section}' not found in {act}.",
                "hint": _GET_INFO_HINT,
                "did_you_mean": [
                    {"act": h["act"], "section": h["section"], "title": h.get("title", "")}
                    for h in hits
                ],
            }, indent=2)
        return json.dumps({"error": f"Section '{section}' not found in {act}.", "hint": _GET_INFO_HINT})

    md_path = DATA_DIR / act / "sections" / section_path
    if not md_path.exists():
        return json.dumps({"error": "Section file not found", "hint": _GET_INFO_HINT})

    content = md_path.read_text(encoding="utf-8")
    body = content
    if content.startswith("---"):
        fm_end = _re.search(r'\n---\s*\n', content)
        if fm_end:
            body = content[fm_end.end():]

    body_clean = _re.sub(r'\n---\s*\*Last updated:.*?\*', '', body, flags=_re.DOTALL)
    body_clean = _re.sub(r'\n---\s*$', '', body_clean)
    # Strip HTML anchor tags (e.g. <a id="s8-1-1"></a>) — internal nav markers, not reading content
    body_clean = _re.sub(r'<a\s+id="[^"]*"\s*></a>\s*', '', body_clean)
    body_stripped = body_clean.strip()
    truncated = bool(body_stripped) and not _re.search(r'[.\\)"\'!?]\s*$', body_stripped)

    # Apply max_body_length cap
    body_out = body_stripped
    body_truncated_flag = bool(body_stripped) and len(body_stripped) > max_body_length
    if body_truncated_flag:
        body_out = body_stripped[:max_body_length]

    # Strip scraped markup artifacts from body (CDN-0095)
    body_out = strip_scraped_markup(body_out)

    # Special handling for large definition/interpretation sections
    # These contain hundreds of defined terms — truncate and guide user to get_definition
    # (the definition library). Registry = dictionary sections per act:
    # itaa-1936 s 6 / s 317, itaa-1997 s 995-1, gst-1999 s 195-1, fbt-1986 s 136,
    # taa-1953 s 2, sis-1993 s 10, aml-ctf-2006 s 5, nz-it-2007 YA 1, corps s 9.
    big_def_sections = {
        "itaa-1997": {"995-1": ("the ITAA 1997", "s995-1")},
        "itaa-1936": {"317": ("Part X (CFC measures) of the ITAA 1936", "s317"), "6": ("the ITAA 1936", "s6")},
        "gst-1999": {"195-1": ("the GST Act", "s195-1")},
        "fbt-1986": {"136": ("the FBT Act", "s136")},
        "taa-1953": {"2": ("the TAA 1953", "s2")},
        "sis-1993": {"10": ("the SIS Act", "s10")},
        "aml-ctf-2006": {"5": ("the AML/CTF Act", "s5")},
        "nz-it-2007": {"YA-1": ("the NZ IT Act 2007", "YA 1")},
        "corporations-act-2001": {"9": ("the Corporations Act 2001", "s9")},
    }
    def_section_act = big_def_sections.get(act, {})
    def_section_info = def_section_act.get(section)
    section_def_note = ""
    if def_section_info:
        def_section_label, def_section_ref = def_section_info
        section_def_note = (
            f"This is an interpretation/definitions section for {def_section_label} "
            f"({def_section_ref}). The full text is very large. "
            f"HINT: use the definition library — call get_definition(act='{act}', "
            f"term='TERM') or /api/definitions/{act} for any term instead of "
            f"reading this section in full."
        )
        # Truncate to a concise preview
        body_out = body_out[:10000]

    # Fetch related content (top 10 each) — graph-first: graph.db is the
    # canonical link source (considered_in / interpreted_by / applies /
    # explained_in). The archived citation/commentary/smartlink indexes are
    # retired. Related sections come from the act tree (same part/division) —
    # the graph has no section→section edges.
    try:
        related_cases = _graph_cases_for_section(act, section, limit=10)
    except Exception:
        related_cases = []
    try:
        related_rulings = _graph_rulings_for_section(act, section, limit=10)
    except Exception:
        related_rulings = []
    try:
        related_private_rulings = _graph_private_rulings_for_section(act, section, limit=10)
    except Exception:
        related_private_rulings = []
    try:
        related_commentary_raw = _graph_commentary_for_section(act, section, limit=10)
    except Exception:
        related_commentary_raw = []

    # Graph-driven commentary entries already carry a 500-char snippet + URL.
    # include_commentary=True adds the full body text from the commentary file.
    related_commentary = []
    for entry in related_commentary_raw:
        commentary_entry = {
            "publication": entry.get("publication", ""),
            "chapter_number": entry.get("chapter_number"),
            "chapter_title": entry.get("chapter_title", ""),
            "heading_title": entry.get("heading_title", ""),
            "url": entry.get("url"),
            "snippet": entry.get("snippet", ""),
        }
        if include_commentary and entry.get("content_ref"):
            md_path = DATA_DIR / entry["content_ref"].removeprefix("data/")
            try:
                body = md_path.read_text(encoding="utf-8")
                if body.startswith("---"):
                    fm_end = _re.search(r"\n---\s*\n", body)
                    if fm_end:
                        body = body[fm_end.end():]
                body = _re.sub(r"\n---\s*\*Last updated:.*?\*", "", body, flags=_re.DOTALL)
                body = _re.sub(r"\n---\s*$", "", body)
                commentary_entry["content"] = strip_scraped_markup(body).strip()
            except Exception:
                commentary_entry["content"] = ""
        related_commentary.append(commentary_entry)

    try:
        tree = load_tree(act)
        related_sections = _tree_same_division(tree, section)[:10]
    except Exception:
        related_sections = []

    payload = {
        "act": act,
        "section": section,
        "body": body_out,
        "truncated": truncated or body_truncated_flag,
        "body_truncated_to": max_body_length,
        "related": {
            "cases": related_cases,
            "rulings": related_rulings,
            "sections": related_sections,
        },
    }
    if related_private_rulings:
        payload["related"]["private_rulings"] = related_private_rulings
    if related_commentary:
        payload["related"]["commentary"] = related_commentary
    if section_def_note:
        payload["note"] = section_def_note
    return json.dumps(payload, indent=2)


@mcp.tool(structured_output=False)
async def list_acts() -> str:
    """List all available acts and ATO rulings."""
    acts = []
    for act_dir in sorted(DATA_DIR.iterdir()):
        if act_dir.is_dir() and (act_dir / "tree.json").exists():
            tree = load_tree(act_dir.name)
            acts.append({
                "id": act_dir.name,
                "name": tree.get("act", act_dir.name),
                "compilation_no": int(tree["compilation_no"]) if tree.get("compilation_no") is not None else None,
                "compilation_date": tree.get("compilation_date"),
            })
    acts.append({"id": "rulings", "name": "Public Rulings"})
    return json.dumps({"acts": acts}, indent=2)


@mcp.tool(structured_output=False)
async def get_act_tree(act: str, depth: str = "sections", part: str | None = None,
                       offset: int = 0) -> str:
    """Get the structure of an act (parts, divisions, sections).

    depth: 'parts' returns only parts (fast), 'divisions' includes divisions,
           'sections' (default) includes all sections.

    part: Optional part ID to scope the result to one part (e.g. '1-1').
          Required for large acts at depth='sections' — the full ITAA 1997
          tree is ~1MB and burns tokens. When part is given, only that part's
          sections are returned.

    offset: Section offset within the current scope (whole act, or the part
            when part= is set). Pages at 400 sections; pass the previous
            response's offset + sections_returned (or the next_offset hint)
            to read further. Largest parts exceed 400 sections (ITAA 1997
            Part 4-5 = 489, ITAA 1936 Part III = 471) — offset is the only
            way to reach their tail sections.
    """
    try:
        tree = load_tree(act)
    except Exception:
        # load_tree raises for unknown acts — return a clean error with hint
        return json.dumps({
            "error": f"Act '{act}' not found.",
            "hint": _GET_INFO_HINT,
            "format_hint": "Valid act ids via list_acts (e.g. itaa-1997, itaa-1936, gst-1999, taa-1953).",
        }, indent=2)

    def _section_rows(parts: list[dict]) -> list[tuple]:
        """Flatten (part, division, subdivision, section) rows in tree order."""
        rows = []
        for p in parts:
            pid, ptitle = p.get("id"), p.get("title")
            for s in p.get("sections", []):
                rows.append((pid, ptitle, None, None, None, None, s.get("id"), s.get("title")))
            for d in p.get("divisions", []):
                did, dtitle = d.get("id"), d.get("title")
                for s in d.get("sections", []):
                    rows.append((pid, ptitle, did, dtitle, None, None, s.get("id"), s.get("title")))
                for sub in d.get("subdivisions", []):
                    sid, stitle = sub.get("id"), sub.get("title")
                    for s in sub.get("sections", []):
                        rows.append((pid, ptitle, did, dtitle, sid, stitle, s.get("id"), s.get("title")))
        return rows

    def _rebuild(rows: list[tuple]) -> list[dict]:
        """Reconstruct pruned part/division/subdivision hierarchy from a row slice."""
        parts: dict = {}
        order: list[str] = []
        for pid, ptitle, did, dtitle, sid, stitle, secid, sectitle in rows:
            if pid not in parts:
                parts[pid] = {"id": pid, "title": ptitle, "sections": [], "divisions": {}}
                order.append(pid)
            p = parts[pid]
            if did is None:
                p["sections"].append({"id": secid, "title": sectitle})
                continue
            if did not in p["divisions"]:
                p["divisions"][did] = {"id": did, "title": dtitle, "sections": [], "subdivisions": {}}
            d = p["divisions"][did]
            if sid is None:
                d["sections"].append({"id": secid, "title": sectitle})
                continue
            if sid not in d["subdivisions"]:
                d["subdivisions"][sid] = {"id": sid, "title": stitle, "sections": []}
            d["subdivisions"][sid]["sections"].append({"id": secid, "title": sectitle})
        out = []
        for pid in order:
            p = parts[pid]
            for d in p["divisions"].values():
                d["subdivisions"] = list(d["subdivisions"].values())
            p["divisions"] = list(p["divisions"].values())
            out.append(p)
        return out

    PAGE = 400
    offset = max(0, offset)

    if part:
        p = next((x for x in tree.get("parts", []) if x.get("id") == part), None)
        if p is None:
            return json.dumps({"error": f"Part '{part}' not found in {act}.",
                               "hint": _GET_INFO_HINT,
                               "available_parts": [x.get("id") for x in tree.get("parts", [])]}, indent=2)
        rows = _section_rows([p])
        page = rows[offset:offset + PAGE]
        truncated = offset + PAGE < len(rows)
        return json.dumps({
            "act": tree.get("act", act),
            "depth": f"sections (part: {part})",
            "sections_total": len(rows),
            "sections_returned": len(page),
            "offset": offset,
            "truncated": truncated,
            "next_offset": offset + len(page) if truncated else None,
            "truncation_note": ("Use offset=<n> to page further.") if truncated else None,
            "parts": _rebuild(page),
        }, indent=2)

    if depth == "parts":
        pruned = {
            "act": tree.get("act", act),
            "compilation_no": tree.get("compilation_no"),
            "compilation_date": tree.get("compilation_date"),
            "depth": "parts",
            "parts": [{"id": p.get("id"), "title": p.get("title")}
                      for p in tree.get("parts", [])
                      if p.get("id") or p.get("title")],  # filter empty nodes
        }
        return json.dumps(pruned, indent=2)
    elif depth == "divisions":
        pruned = {
            "act": tree.get("act", act),
            "compilation_no": tree.get("compilation_no"),
            "compilation_date": tree.get("compilation_date"),
            "depth": "divisions",
            "parts": [],
        }
        for p in tree.get("parts", []):
            if not p.get("id") and not p.get("title"):
                continue  # skip empty parts
            part_obj = {"id": p.get("id"), "title": p.get("title"), "divisions": []}
            for d in p.get("divisions", []):
                part_obj["divisions"].append({"id": d.get("id"), "title": d.get("title")})
            pruned["parts"].append(part_obj)
        return json.dumps(pruned, indent=2)

    # depth == "sections" — prune paths (not needed by LLM) and page at 400.
    # Full ITAA 1997 tree is ~1.1MB; offset walks the rest.
    rows = _section_rows(tree.get("parts", []))
    page = rows[offset:offset + PAGE]
    truncated = offset + PAGE < len(rows)
    return json.dumps({
        "act": tree.get("act", act),
        "compilation_no": tree.get("compilation_no"),
        "compilation_date": tree.get("compilation_date"),
        "depth": "sections",
        "sections_total": len(rows),
        "sections_returned": len(page),
        "offset": offset,
        "truncated": truncated,
        "next_offset": offset + len(page) if truncated else None,
        "truncation_note": ("Use offset=<n> to page further, or part=<part-id> to scope "
                            "to one part.") if truncated else None,
        "parts": _rebuild(page),
    }, indent=2)


@mcp.tool(structured_output=False)
async def list_treaty_articles(country: str) -> str:
    """List all articles for a given Double Tax Agreement country.

    Parameters:
    - country: Country slug (e.g. 'argentina', 'usa', 'china')

    Returns a list of articles with their number, title, and identifier.
    Use ``get_treaty_article`` to retrieve the full text of an article.
    """
    tree_path = TREATIES_DIR / country / "tree.json"
    if not tree_path.exists():
        available = sorted(
            d.name for d in TREATIES_DIR.iterdir()
            if d.is_dir() and (d / "tree.json").exists()
        )
        return json.dumps({
            "error": f"Treaty for '{country}' not found",
            "hint": _GET_INFO_HINT,
            "available_countries": available,
        }, indent=2)
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        return json.dumps({
            "treaty": tree.get("treaty", country),
            "country_slug": country,
            "schedule": tree.get("schedule"),
            "total_articles": tree.get("total", len(tree.get("articles", []))),
            "articles": [
                {"article": a["article"], "title": a["title"]}
                for a in tree.get("articles", [])
            ],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to read treaty: {e}", "hint": _GET_INFO_HINT}, indent=2)


@mcp.tool(structured_output=False)
async def get_treaty_article(country: str, article: int,
                             max_body_length: int = 50000) -> str:
    """Retrieve the full text of a specific treaty article.

    Parameters:
    - country: Country slug (e.g. 'argentina', 'usa', 'china')
    - article: Article number (e.g. 1, 2, 24)
    - max_body_length: Maximum characters for the article body (default 50000)

    Returns the article title, full text, and metadata.
    """
    tree_path = TREATIES_DIR / country / "tree.json"
    if not tree_path.exists():
        return json.dumps({
            "error": f"Treaty for '{country}' not found",
            "hint": _GET_INFO_HINT
        }, indent=2)
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    except Exception as e:
        return json.dumps({"error": f"Failed to read treaty: {e}", "hint": _GET_INFO_HINT}, indent=2)

    # Find the article entry
    art_info = None
    for a in tree.get("articles", []):
        if a["article"] == article:
            art_info = a
            break
    if not art_info:
        available = [a["article"] for a in tree.get("articles", [])]
        return json.dumps({
            "error": f"Article {article} not found for {country}",
            "hint": _GET_INFO_HINT,
            "available_articles": available,
        }, indent=2)

    art_path = TREATIES_DIR / country / art_info["file"]
    if not art_path.exists():
        return json.dumps({
            "error": f"Article file not found for article {article}",
            "hint": _GET_INFO_HINT
        }, indent=2)

    content = art_path.read_text(encoding="utf-8", errors="replace")
    if len(content) > max_body_length:
        content = content[:max_body_length] + f"\n\n... [truncated at {max_body_length} characters]"

    return json.dumps({
        "treaty": tree.get("treaty", country),
        "country_slug": country,
        "article": article,
        "title": art_info["title"],
        "content": content,
    }, indent=2, ensure_ascii=False)


@mcp.tool(structured_output=False)
async def get_definition(act: str, term: str) -> str:
    """Look up the definition of a term, searched across all acts.

    The requested act is preferred; matches in other acts (e.g. a term defined
    in ITAA 1936 s 318 rather than the requested act) are returned under
    ``also_defined_in``.
    """
    result = get_definition_across_acts(term, preferred_act=act)
    if result:
        return json.dumps(result, indent=2)
    return json.dumps({"error": f"Definition for '{term}' not found in any act", "hint": _GET_INFO_HINT})


@mcp.tool(structured_output=False)
async def search_all(
    query: str,
    type_filter: str | None = None,
    act: str | None = None,
    limit: int = 20,
) -> str:
    """Unified search across sections, cases, rulings, and commentary.

    Parameters:
    - query: Free-text search terms
    - type_filter: Optional — 'section', 'case', 'ruling', 'private_ruling', or 'commentary'
                   to restrict results to one content type
    - act: Optional — restrict to a specific act (e.g. 'itaa-1997')
    - limit: Max results per content type (default 20, max 50)

    Returns grouped results by type with snippets and metadata.
    """
    limit = min(50, max(1, limit))
    query = query.strip()
    if not query:
        return json.dumps({"error": "Query required", "results": {}, "hint": _GET_INFO_HINT})

    results = {}

    # Sections
    if type_filter is None or type_filter == "section":
        try:
            sec_results = fts_search(query, act, limit=limit)
            results["sections"] = sec_results.get("results", [])
        except Exception:
            results["sections"] = []

    # Rulings
    if type_filter is None or type_filter == "ruling":
        try:
            results["rulings"] = search_rulings(query, limit=limit)
        except Exception:
            results["rulings"] = []

    # Private rulings (PBRs) — FTS5 index, 57k+ rulings with body text
    if type_filter is None or type_filter in ("ruling", "private_ruling"):
        try:
            from backend.services.search_service import search_private_rulings_fts
            results["private_rulings"] = search_private_rulings_fts(query, limit=limit)
        except Exception:
            results["private_rulings"] = []

    # Cases — search via PostgreSQL + summaries
    if type_filter is None or type_filter == "case":
        try:
            from backend.services.search_service import search_cases_fts
            case_results = search_cases_fts(query, limit * 2)
            case_results = [{
                "citation": r["citation"],
                "case_name": r["case_name"],
                "court": r["court"],
                "has_summary": True,
            } for r in case_results]
            # Also search DB for metadata matches
            if len(case_results) < limit:
                try:
                    words = query.split()
                    import subprocess
                    safe = query.replace("'", "''")
                    like_clause = " OR ".join(
                        f"c.case_name ILIKE '%{w}%' OR c.citation ILIKE '%{w}%'"
                        for w in words
                    )
                    r = subprocess.run(
                        ["docker", "exec", "cadena-postgres", "psql", "-U", "postgres",
                         "-d", "cadena_knowledge", "-tA",
                         "-c", f"SELECT c.citation, c.case_name, c.court FROM cases c "
                               f"WHERE ({like_clause}) ORDER BY c.citation LIMIT {limit};"],
                        capture_output=True, text=True, timeout=10
                    )
                    existing = {c["citation"] for c in case_results}
                    for line in r.stdout.strip().split("\n"):
                        if not line.strip():
                            continue
                        parts = line.split("|", 2)
                        cit = parts[0].strip()
                        if cit in existing:
                            continue
                        case_results.append({
                            "citation": cit,
                            "case_name": parts[1].strip() if len(parts) > 1 else "",
                            "court": parts[2].strip() if len(parts) > 2 else "",
                            "has_summary": False,
                        })
                except Exception:
                    pass
            results["cases"] = case_results[:limit]
        except Exception:
            results["cases"] = []

    # Commentary — search FTS5 commentary index
    if type_filter is None or type_filter == "commentary":
        try:
            with search_conn() as conn:
                words = query.lower().split()
                like_clause = " AND ".join(
                    f"(publication ILIKE '%{w}%' OR chapter_title ILIKE '%{w}%' "
                    f"OR heading_title ILIKE '%{w}%' OR content ILIKE '%{w}%')"
                    for w in words
                )
                rows = conn.execute(
                    f"SELECT publication, chapter_number, chapter_title, "
                    f"heading_title, paragraph_number, content "
                    f"FROM commentary_index WHERE {like_clause} LIMIT ?",
                    (limit,)
                ).fetchall()
                commentary_results = []
                for row in rows:
                    commentary_results.append({
                        "publication": row[0],
                        "chapter": row[1],
                        "chapter_title": row[2],
                        "heading": row[3],
                        "paragraph": row[4],
                    })
                results["commentary"] = commentary_results
        except Exception:
            results["commentary"] = []

    return json.dumps({
        "query": query,
        "filter": type_filter or "all",
        "act": act,
        "results": results,
    }, indent=2)


@mcp.tool(structured_output=False)
async def search_cases(query: str, limit: int = 20) -> str:
    """Search case AI summaries and metadata by topic, case name, or citation.

    Searches across facts, issues, held, reasoning, outcome, cases_cited,
    and legislation_cited fields. Returns matching citations with summaries;
    use get_case for full details and judgment text.
    """
    limit = min(100, max(1, limit))
    query = query.strip().lower()
    if not query:
        return json.dumps({"total": 0, "results": [], "note": "Query required"})
    words = query.split()

    # FTS5 search over case summaries (much faster than brute-force file scan)
    from backend.services.search_service import search_cases_fts
    results = search_cases_fts(query, limit * 2)

    # Also search PostgreSQL for cases with metadata but no summary
    if len(results) < limit * 2:
        safe = query.replace("'", "''")
        try:
            import subprocess
            like_clause = " OR ".join(
                f"c.case_name ILIKE '%{w}%' OR c.citation ILIKE '%{w}%'"
                for w in words
            )
            r = subprocess.run(
                ["docker", "exec", "cadena-postgres", "psql", "-U", "postgres",
                 "-d", "cadena_knowledge", "-tA",
                 "-c", f"SELECT c.citation, c.case_name, c.court FROM cases c "
                       f"WHERE ({like_clause}) ORDER BY c.citation LIMIT {limit};"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("|", 2)
                cit = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                court = parts[2].strip() if len(parts) > 2 else ""
                if any(r["citation"] == cit for r in results):
                    continue
                from urllib.parse import quote
                results.append({
                    "citation": cit,
                    "case_name": name,
                    "court": court,
                    "year": cit[1:5] if cit.startswith("[") else "",
                    "has_summary": False,
                    "html_url": f"https://legislation.scriptkitty.yachts/tax-cases/{quote(cit)}",
                })
        except Exception:
            pass

    # Rank results: exact/substring case_name+citation matches first
    def _relevance_score(item: dict) -> int:
        """Score 0-3: higher = better match.
        3 = exact case_name or citation match
        2 = all query words appear in case_name
        1 = some query words appear in citation
        0 = general content match only
        """
        name = (item.get("case_name") or "").lower()
        cit = (item.get("citation") or "").lower()
        q_lower = query.lower()
        # Exact match
        if name == q_lower or cit == q_lower:
            return 3
        # All words in case_name (phrase-like match)
        if all(w in name for w in words):
            return 2
        # Some words in citation
        if any(w in cit for w in words):
            return 1
        return 0

    results.sort(key=_relevance_score, reverse=True)

    return json.dumps({
        "total": len(results),
        "results": results[:limit],
        "note": "Searches AI summaries and case metadata. Results with summaries are "
                "richer than metadata-only results. Use get_case for full details.",
    }, indent=2)


@mcp.tool(structured_output=False)
async def find_similar_rulings(query: str, limit: int = 10, outcome: str = "",
                               source: str = "all") -> str:
    """Semantic search over 57,608 ATO private rulings plus 12k+ public rulings.

    Embeds the query and returns the most similar rulings by meaning (not
    keyword match). For private rulings the response includes the QA pairs —
    the actual question the taxpayer asked and how the ATO answered (the
    'outcome' label: yes = favourable, no = unfavourable, mixed).

    Parameters:
    - query: a fact pattern, e.g. "contractor vs employee software developer
      home office" or "CGT main residence exemption deceased estate"
    - limit: max results (default 10, max 20)
    - outcome: filter private rulings by outcome label — yes | no | mixed
      (empty = no filter). 'no' answers = likely adverse ATO positions on the
      fact pattern (useful for objections); 'yes' = favourable positions.
    - source: private | public | all (default all)

    Returns each match's citation, title, date, score, snippet, ato_url and
    download_url links, and for private rulings the QA pairs and outcome label.
    """
    limit = min(20, max(1, limit))
    query = query.strip()
    if not query:
        return json.dumps({"total": 0, "results": [], "note": "Query required"})
    source = (source or "all").strip().lower()
    if source not in ("private", "public", "all"):
        source = "all"
    want_outcome = (outcome or "").strip().lower()
    if want_outcome not in ("", "yes", "no", "mixed"):
        want_outcome = ""

    from backend.services import vector_search_service as _vss
    from backend.services import private_ruling_outcomes as _outcomes

    try:
        top = _vss.search(query, limit=50)
    except Exception as exc:  # pragma: no cover - network/API failure path
        return json.dumps({"error": f"vector search failed: {exc}"})

    # Keep rulings only; dedupe by (act, section) keeping best score per ruling
    best: dict[tuple[str, str], dict] = {}
    for r in top:
        st = r.get("source_type")
        if st not in ("ruling", "private_ruling"):
            continue
        if source == "private" and st != "private_ruling":
            continue
        if source == "public" and st != "ruling":
            continue
        key = (r["act"], r["section"])
        if key not in best or r["score"] > best[key]["score"]:
            best[key] = r

    ranked = sorted(best.values(), key=lambda r: -r["score"])[:limit]
    results = []
    for r in ranked:
        item = {
            "source": r.get("source_type"),  # private_ruling | ruling
            "citation": r.get("section"),
            "title": r.get("title"),
            "score": round(r["score"], 4),
            "snippet": r.get("snippet", ""),
        }
        if r.get("source_type") == "private_ruling":
            authnum = r.get("section") or ""
            item["ato_url"] = (f"https://www.ato.gov.au/law/view/print"
                               f"?DocID=EV/{authnum}&PiT=99991231235958")
            item["download_url"] = _abs(f"/api/private-ruling/{authnum}/download")
            rec = _outcomes.get(r.get("section") or "")
            if rec:
                item["date"] = rec.get("date_of_advice") or ""
                item["outcome"] = rec.get("outcome") or "unknown"
                item["qa"] = rec.get("qa") or []
                if not item["title"]:
                    item["title"] = rec.get("name") or ""
            else:
                item["outcome"] = "unknown"
            if want_outcome and item.get("outcome") != want_outcome:
                continue
        else:
            item["ato_url"] = r.get("ato_url", "") or ""
            item["download_url"] = _abs(f"/api/ruling/{r.get('section')}/download")
        results.append(item)

    return json.dumps({
        "total": len(results),
        "results": results,
        "note": "Semantic similarity over ATO private rulings (57,608) and public rulings. "
                "outcome reflects how the ATO answered the taxpayer's own question — "
                "a search aid, not a legal characterisation. Each result carries ato_url "
                "and download_url links. Verify against the full ruling before reliance "
                "(use get_private_ruling).",
    }, indent=2)


@mcp.tool(structured_output=False)
async def insolvency_search(query: str, limit: int = 20) -> str:
    """Search the Keays Insolvency textbook across all chapters.

    Full-text search across 21 chapters covering personal and corporate
    insolvency — bankruptcy, liquidation, receivership, voluntary
    administration, deeds of arrangement, restructuring, and related topics.

    Returns matching chapters with relevance-ranked snippets.
    Use insolvency_get_chapter to read a full chapter.
    """
    from backend.services.search_service import search_insolvency as _search
    limit = min(50, max(1, limit))
    query = query.strip()
    if not query:
        return json.dumps({"total": 0, "results": []})
    result = _search(query, limit=limit)
    return json.dumps(result, indent=2)


@mcp.tool(structured_output=False)
async def insolvency_get_chapter(chapter: int, offset: int = 0,
                                  limit: int = 5000,
                                  max_chars: int = 12000) -> str:
    """Retrieve the full text of a chapter from the Keays Insolvency textbook.

    Parameters:
    - chapter: Chapter number (1–21)
    - offset: Line offset to start from (default 0)
    - limit: Maximum number of lines to return (default 5000, max 50000)
    - max_chars: Hard cap on returned content characters (default 12000).
      Chapters run ~130K chars — cap keeps token burn down; paginate with
      offset to read further.

    Returns paginated chapter text including section markers like [1.05].
    Use offset and limit to paginate through long chapters; check
    total_lines in the response to determine if more pages remain.
    """
    from backend.services.search_service import get_insolvency_chapter as _get
    result = _get(chapter)
    if result is None:
        return json.dumps({"error": f"Chapter {chapter} not found", "hint": _GET_INFO_HINT})
    content = result["content"]
    lines = content.splitlines()
    total_lines = len(lines)
    offset = max(0, offset)
    limit = min(50000, max(1, limit))
    end = offset + limit
    selected = lines[offset:end]
    selected_text = "\n".join(selected)
    char_capped = False
    if len(selected_text) > max_chars:
        # Cap at a line boundary so pagination never loses a partial line:
        # trim back to the last newline inside the budget.
        selected_text = selected_text[:max_chars]
        nl = selected_text.rfind("\n")
        if nl != -1:
            selected_text = selected_text[:nl]
        char_capped = True
    returned_lines = selected_text.count("\n") + (1 if selected_text else 0)
    next_offset = None
    if char_capped and returned_lines > 0:
        next_offset = offset + returned_lines
    elif not char_capped and offset + len(selected) < total_lines:
        # limit (not max_chars) truncated the page — keep paginating
        next_offset = offset + len(selected)
    return json.dumps({
        "chapter": chapter,
        "title": result.get("title", ""),
        "slug": result.get("slug", ""),
        "content": selected_text,
        "offset": offset,
        "limit": limit,
        "total_lines": total_lines,
        "returned_lines": returned_lines,
        "char_capped": char_capped,
        "max_chars": max_chars,
        "next_offset": next_offset,
    }, indent=2)


@mcp.tool(structured_output=False)
async def get_regulatory_guide(rg_number: int, max_body_length: int = 8000) -> str:
    """Retrieve an ASIC Regulatory Guide with structured summary.

    Parameters:
    - rg_number: The RG number (e.g. 1, 104, 140)
    - max_body_length: Maximum characters for the body text (default 8000).
      Structured fields (subject, background, ruling, legislation refs) are
      always returned in full.

    Returns the guide's subject, background, ruling, legislation references,
    cases cited, related RGs, and body text (capped).
    """
    from backend.routes.regulatory_guides import get_regulatory_guide as _get_rg
    import json as _json
    try:
        result = _get_rg(rg_number)
        body = result.get("body", "")
        if len(body) > max_body_length:
            result["body"] = body[:max_body_length] + \
                f"\n\n... [truncated at {max_body_length} characters]"
            result["body_truncated"] = True
            result["body_total_length"] = len(body)
        return _json.dumps(result, indent=2, default=str)
    except Exception as e:
        return _json.dumps({"error": str(e), "hint": _GET_INFO_HINT})


@mcp.tool(structured_output=False)
async def get_rg_sections(rg_number: int) -> str:
    """Retrieve the Corps Act sections cited by an ASIC Regulatory Guide.

    Parameters:
    - rg_number: The RG number (e.g. 1, 104, 140)

    Returns a list of sections referenced in the RG with their titles.
    """
    import json as _json
    index = _load_rg_section_index()
    key = f"RG_{rg_number}"
    sections = index.get(key, [])
    if not sections:
        return _json.dumps({"rg_number": rg_number, "count": 0, "sections": []})
    # Enrich with titles
    try:
        tree = load_tree("corporations-act-2001")
        sec_map: dict[str, str] = {}
        for part in tree.get("parts", []):
            for sec in part.get("sections", []):
                sec_map[sec["id"]] = sec.get("title", "")
            for div in part.get("divisions", []):
                for sec in div.get("sections", []):
                    sec_map[sec["id"]] = sec.get("title", "")
                for sub in div.get("subdivisions", []):
                    for sec in sub.get("sections", []):
                        sec_map[sec["id"]] = sec.get("title", "")
        enriched = [{**s, "title": sec_map.get(s["section"], "")} for s in sections]
        sections = enriched
    except Exception:
        pass
    return _json.dumps({"rg_number": rg_number, "count": len(sections), "sections": sections}, indent=2)


@mcp.tool(structured_output=False)
async def get_info() -> str:
    """Return server version, usage conventions, tool descriptions, and coverage counts.

    Call this FIRST before using any other tool, and call it AGAIN whenever a
    tool fails, returns null, or returns an unexpected empty result — the
    failure is usually a query-format or citation-format problem documented here.
    """
    rulings_count = len(load_rulings())
    try:
        import subprocess
        r = subprocess.run(
            ["docker", "exec", "cadena-postgres", "psql", "-U", "postgres",
             "-d", "cadena_knowledge", "-tA",
             "-c", "SELECT COUNT(*) FROM cases c WHERE EXISTS "
                   "(SELECT 1 FROM case_paragraphs cp WHERE cp.case_id = c.id);"],
            capture_output=True, text=True, timeout=10
        )
        cases_count = int(r.stdout.strip())
    except Exception:
        cases_count = 7375

    summaries_dir = "/home/harrison/legislation-explorer/scripts/cleaned/summaries"
    summaries_count = len([f for f in os.listdir(summaries_dir)
                          if f.endswith(".json")]) if os.path.isdir(summaries_dir) else 0

    # Query issues table for known issues
    known_issues = []
    try:
        rows = _sql_dict(
            ["ticket", "tool", "known_note"],
            "SELECT ticket, tool, known_note FROM issues WHERE status = 'known' ORDER BY id",
        )
        for row in rows:
            known_issues.append({
                "ticket": row.get("ticket", ""),
                "tool": row.get("tool"),
                "note": row.get("known_note"),
            })
    except Exception:
        pass

    return json.dumps({
        "name": "Legislation Explorer",
        "version": VERSION,
        "usage": {
            "act_ids": ["itaa-1997", "itaa-1936", "gst-1999", "taa-1953", "nz-it-2007",
                        "master-tax-guide", "master-gst-guide", "master-tax-examples", "rulings"],
            "section_format": {
                "itaa-1997": "hyphenated: 8-1, 995-1",
                "itaa-1936": "unhyphenated: 23AH, 177D",
                "gst-1999": "hyphenated: 195-1",
                "taa-1953": "Sch 1: 284-15",
            },
            "citation_format": {
                "rulings": "TR 2024/1 | PCG 2017/13 (types: TR TD PCG PS LA LCG AID IT CR GSTR MT PR SGR TA); 2-digit years auto-expanded; underscores ok; LCR=LCG",
                "cases": "[2024] HCA 1 bracketed medium-neutral (HCA FCAFC FCA ARTA); party-name aliases accepted",
            },
            "query_format": {
                "search_legislation": "keywords, AND matching — all terms must appear; section-shaped queries exact-matched first; omit stopwords",
                "search_all": "keywords; type_filter=section|case|ruling|commentary",
                "search_cases": "topic, case name, or citation",
                "search_case_paragraphs": "exact phrase; omit stopwords",
                "get_definition": "single plain term (e.g. 'dividend'); plural forms auto-stripped ('capital gains' works)",
                "resolve_alias": "'s 100A', 'Div 7A', 'Part IVA', 'Subdiv 115-C', '109Y', '8-1'",
            },
            "other_lookups": {
                "treaty": "country slug: usa, china, argentina (list_treaty_articles for valid slugs)",
                "regulatory guide": "RG int: 1, 104, 140",
                "insolvency": "chapter int 1-21",
                "graph": "canonical keys: 'section:itaa-1997:118-110', 'public_ruling:TR 2025/1', 'case:[2015] HCA 48', 'private_ruling:EV/1011261243735'; resolve_alias output accepted",
            },
            "section_aliases": ["116-30", "s 116-30", "sec 116-30", "section 116-30", "s116-30"],
            "on_failure": "Fail/null/empty → re-call get_info, reformat per the formats above, retry once via resolve_alias / search_legislation / search_all. Never guess a section number or invent a citation.",
            "routing": {
                "provision text + related": "get_section",
                "find a provision by words": "search_legislation",
                "search everything": "search_all",
                "defined term": "get_definition",
                "act structure": "get_act_tree",
                "case by name/topic": "search_all(type_filter=case) → get_case",
                "full judgment text": "get_case().sources.text.url",
                "rulings for a section": "search_all(type_filter=ruling)",
                "ruling by citation": "search_all(type_filter=ruling) — download_url/ato_url included",
                "standards / verification": "standards",
                "bug or data gap": "report_issue",
            },
            "rules": [
                "Answer only from tool results; if a tool returns nothing, say so. Never fill a gap from recall.",
                "Tool fail/null → re-call get_info, reformat, retry before concluding data is missing.",
                "report_issue does not change a citation's status — it stays unverifiable with its [verify] tag.",
            ],
            "standards_topics": ["verification", "matter-structure", "premises", "memory", "toolchain"],
            "coverage": {
                "acts": "compilation 2026-04-01",
                "rulings": rulings_count,
                "cases_in_db_with_text": cases_count,
                "summary_files_on_disk": summaries_count,
                "known_issues": known_issues,
                "note": "cases_in_db and summary_files come from separate sources (DB vs filesystem) and may overlap incompletely.",
            },
        },
    }, indent=2)


@mcp.tool(structured_output=False)
async def standards(topic: str | None = None) -> str:
    """Return Cadena Legal standards for a topic, or list of topics."""
    STANDARDS_DIR = Path(__file__).parent.parent / "standards"
    TOPIC_MAP = {
        "verification": "verification.md",
        "matter-structure": "matter-structure.md",
        "premises": "premises.md",
        "memory": "memory.md",
        "toolchain": "toolchain.json",
    }

    if topic is None:
        return json.dumps({"topics": list(TOPIC_MAP.keys())})

    fname = TOPIC_MAP.get(topic)
    if not fname:
        return json.dumps({"error": f"Unknown topic: {topic}", "hint": _GET_INFO_HINT})

    path = STANDARDS_DIR / fname
    if not path.exists():
        return json.dumps({"error": f"Standard file not found: {fname}", "hint": _GET_INFO_HINT})

    content = path.read_text(encoding="utf-8")

    if fname.endswith(".json"):
        return content  # already JSON

    # Extract frontmatter if present
    last_reviewed = None
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            import re
            m = _re.search(r'last_reviewed:\s*(\S+)', parts[1])
            if m:
                last_reviewed = m.group(1)
            body = parts[2].strip()

    return json.dumps({
        "topic": topic,
        "last_reviewed": last_reviewed,
        "content": body,
    }, indent=2)


# ---------------------------------------------------------------------------
# Helper: clean legislation_referenced entries — filter sentence fragments,
# deduplicate by (act, section).
# ---------------------------------------------------------------------------
_KNOWN_ACT_RE = _re.compile(
    r"^(Income Tax Assessment Act \d{4}|Fringe Benefits Tax(?: Assessment)? Act \d{4}|"
    r"A New Tax System \(Goods and Services Tax\) Act \d{4}|Taxation Administration Act \d{4}|"
    r"Tax Agent Services Act \d{4}|Corporations Act \d{4}|"
    r"Superannuation Industry \(Supervision\) Act \d{4}|"
    r"Superannuation Guarantee \(Administration\) Act \d{4}|"
    r"Family Law Act \d{4}|Social Security Act \d{4}|"
    r"ITAA\s+\d{4}|TAA\s+\d{4})"
    r"(?:\s+\(Cth\))?"
    r"(?:\s+s(?:s|ection)?\.?\s+(\S+))?$",
    _re.IGNORECASE,
)


def _clean_legislation_referenced(items: list[str]) -> list[str]:
    """Filter legislation_referenced to only valid known act entries, dedup by (act, section)."""
    seen: set[tuple[str, str]] = set()
    out: list[str] = []
    for item in items:
        if not item or not isinstance(item, str):
            continue
        m = _KNOWN_ACT_RE.match(item.strip())
        if not m:
            continue
        act_part = m.group(1).strip()
        section_part = (m.group(2) or "").strip().lower()
        key = (act_part.lower(), section_part)
        if key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


_PREFIX_TYPE_MAP = {
    "TR": "Taxation Ruling",
    "TD": "Taxation Determination",
    "IT": "Taxation Ruling",
    "CR": "Class Ruling",
    "GSTR": "Goods and Services Tax Ruling",
    "LCG": "Law Companion Ruling",
    "PCG": "Practical Compliance Guideline",
    "MT": "Miscellaneous Taxation Ruling",
    "PR": "Product Ruling",
    "PS": "Practice Statement Law Administration",
    "PSLA": "Practice Statement Law Administration",
    "SGR": "Superannuation Guarantee Ruling",
    "TA": "Taxpayer Alert",
    "AID": "ATO Interpretative Decision",
}

def _ruling_type_from_citation(citation: str) -> str:
    """Derive the canonical ruling type from the citation prefix.

    E.g. 'TR 2024/1' → 'Taxation Ruling', 'PCG 2017/13' → 'Practical Compliance Guideline'.
    Falls back to an empty string if the prefix is unknown.
    """
    m = _re.match(r'^([A-Za-z]+)', citation.strip())
    if m:
        return _PREFIX_TYPE_MAP.get(m.group(1).upper(), "")
    return ""

@mcp.tool(structured_output=False)
async def get_private_ruling(authnum: str) -> str:
    """Retrieve a single ATO private ruling by authorisation number
    (e.g. 1011261243735 or EV/1011261243735). Returns structured fields plus
    ATO and download links. Private rulings are sensitive — verify context
    before reliance.
    """
    authnum = authnum.strip()
    if authnum.upper().startswith("EV/"):
        authnum = authnum[3:]
    if not authnum.isdigit():
        return json.dumps({
            "error": f"Invalid authorisation number '{authnum}' — expected digits "
                     "only (optionally prefixed EV/)",
            "hint": _GET_INFO_HINT,
        })
    # Same corpus location as backend/routes/private_rulings.py
    corpus = Path(os.environ.get(
        "HERMES_RULINGS_DIR", "/home/harrison/.hermes/private_rulings"))
    path = corpus / "data" / "json" / f"{authnum}.json"
    if not path.exists():
        return json.dumps({"error": f"Private ruling {authnum} not found",
                           "hint": _GET_INFO_HINT})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return json.dumps({"error": f"Private ruling {authnum} unreadable: {exc}",
                           "hint": _GET_INFO_HINT})
    MAX_TEXT = 30000
    text = data.get("formatted_text", "") or ""
    payload = {
        "authnum": authnum,
        "name": data.get("name", ""),
        "date_of_advice": data.get("date_of_advice", ""),
        "subject": data.get("subject", ""),
        # EV print format — the EVR/document variant 404s
        "ato_url": (f"https://www.ato.gov.au/law/view/print"
                    f"?DocID=EV/{authnum}&PiT=99991231235958"),
        "download_url": _abs(f"/api/private-ruling/{authnum}/download"),
        "formatted_text": text[:MAX_TEXT],
        "truncated": len(text) > MAX_TEXT,
    }
    for key in ("qa_pairs", "relevant_legislation", "case_references"):
        if data.get(key):
            payload[key] = data[key]
    return json.dumps(payload, indent=2)


@mcp.tool(structured_output=False)
async def get_case(
    citation: str,
    search: str = "",
    context: int = 2,
) -> str:
    """Get case metadata, AI summary, legislation references, case citations, and judgment text.

    Returns structured summary with facts, issues, held, reasoning, outcome,
    cases cited, legislation cited, and structured sources with fetchable flags.

    When search is provided, performs case-insensitive substring match over
    the full judgment text and returns matching windows with surrounding context.
    A miss returns hits: 0 — not an error.

    Parameters:
    - citation: Case citation, e.g. [2015] HCA 48
    - search: Optional text to find in the full judgment body
    - context: Sentences of context around each match (default 2)
    """
    from urllib.parse import quote
    import html as html_mod
    citation_norm = _normalise_case_citation(citation) or citation
    citation_norm = _resolve_case_citation_alias(citation_norm)
    dev_site_url = f"https://dev.scriptkitty.yachts/tax-cases/{quote(citation_norm)}"
    dl_result = build_download_urls(citation_norm)

    safe_name = citation_norm.replace(" ", "_").replace("[", "").replace("]", "").replace("/", "_")
    summary_path = Path("/home/harrison/legislation-explorer/scripts/cleaned/summaries") / f"{safe_name}.json"
    summary = None
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except Exception:
            pass

    # Fetch case metadata (always includes legislation refs)
    result = get_case_metadata(citation_norm, include_legislation_refs=True)
    if result is None:
        # Summary exists on disk but case is not in the DB — still return it.
        if summary:
            return json.dumps({
                "citation": citation_norm,
                "case_name": summary.get("case_name", ""),
                "summary": summary,
                "note": "Case full text not in database — summary returned from disk. "
                        "Use search_cases to verify the citation format.",
                "hint": _GET_INFO_HINT,
            }, indent=2)
        # Fallback: search for similar cases
        try:
            suggestions = fts_search(citation, limit=3)
            case_suggestions = []
            for r in suggestions.get("results", []):
                act = r.get("act", "")
                sec = r.get("section", "")
                if act == "tax-cases" or (act and sec):
                    case_suggestions.append(f"{act}/{sec}: {r.get('title', '')}")
            if case_suggestions:
                return json.dumps({
                    "error": f"Case not found in database: {citation_norm}",
                    "hint": _GET_INFO_HINT,
                    "did_you_mean": case_suggestions[:3],
                    "format_hint": "Use format [2024] HCA 1 (bracketed medium-neutral citation).",
                })
        except Exception:
            pass
        return json.dumps({
            "error": f"Case not found in database: {citation_norm}",
            "hint": _GET_INFO_HINT,
            "format_hint": "Try search_cases to verify the citation format, "
                    "or check format — required: [2024] HCA 1",
        })

    # Strip unreliable paragraph-layer fields
    result.pop("section_outline", None)
    result.pop("paragraph_count", None)

    # Fetch case citations (cited cases + cited-by)
    refs = get_case_references(citation_norm)

    result["summary"] = summary
    result["legislation_refs"] = result.pop("legislation_refs", [])
    result["case_citations"] = refs.get("case_citations", [])
    result["cited_by"] = refs.get("cited_by", [])

    # Structured sources with fetchable flags
    if dl_result and "sources" in dl_result:
        result["sources"] = dl_result["sources"]
        # Add the hosted browser URL as browser source
        result["sources"]["browser"] = {
            "url": dev_site_url,
            "fetchable": False,
            "note": "SPA route. Browser only.",
        }
    else:
        result["sources"] = {
            "text": {"url": None, "fetchable": False, "note": "Not available."},
            "browser": {"url": dev_site_url, "fetchable": False, "note": "SPA route. Browser only."},
        }

    # Search-in-text feature
    if search.strip():
        m = _CASE_CITATION_RE.search(citation_norm)
        if m:
            year, raw_court, number = m.groups()
            court_key = raw_court.strip()
            filename = f"{year}_{court_key}_{number}.html"
            text_path = DATA_DIR / "case_texts" / filename
            if text_path.exists():
                try:
                    raw_html = text_path.read_text(encoding="utf-8", errors="replace")
                    # Strip scraped markup including HTML tags (CDN-0095)
                    text = strip_scraped_markup(raw_html)
                    text = _re.sub(r"\s+", " ", text).strip()
                    # Decode HTML entities
                    text = html_mod.unescape(text)

                    query = search.strip()
                    matches = []
                    # Case-insensitive find with context windows
                    # Split into sentences for context boundaries
                    sentences = _re.split(r"(?<=[.!?])\s+", text)
                    # For each sentence, check if it matches
                    hit_indices = []
                    for i, sent in enumerate(sentences):
                        if query.lower() in sent.lower():
                            hit_indices.append(i)

                    if hit_indices:
                        for idx in hit_indices:
                            start = max(0, idx - context)
                            end = min(len(sentences), idx + context + 1)
                            window = sentences[start:end]
                            window_text = " ".join(window)
                            # Find character offset in original text
                            char_offset = text.find(window_text[:100])
                            matches.append({
                                "text": window_text,
                                "sentence_index": idx,
                                "char_offset": char_offset,
                                "context_sentences_before": idx - start,
                                "context_sentences_after": end - idx - 1,
                            })

                        # Cap at ~6000 tokens (roughly 24000 chars)
                        token_budget = 24000
                        truncated = False
                        capped_matches = []
                        total_chars = 0
                        for hit in matches:
                            hit_len = len(hit["text"]) + 50  # overhead
                            if total_chars + hit_len > token_budget:
                                truncated = True
                                break
                            capped_matches.append(hit)
                            total_chars += hit_len

                        result["text_search"] = {
                            "query": query,
                            "hits": len(hit_indices),
                            "matches": capped_matches,
                            "truncated": truncated,
                            "note": "Offsets are character positions in the raw text, NOT paragraph or pin-cite numbers.",
                        }
                    else:
                        result["text_search"] = {
                            "query": query,
                            "hits": 0,
                            "matches": [],
                            "truncated": False,
                        }
                except Exception as exc:
                    result["text_search"] = {
                        "query": search.strip(),
                        "error": str(exc),
                        "hits": 0,
                    }
            else:
                result["text_search"] = {
                    "query": search.strip(),
                    "error": f"Full text file not found: {filename}",
                    "hint": _GET_INFO_HINT,
                    "hits": 0,
                }

    return json.dumps(result, indent=2)


@mcp.tool(structured_output=False)
async def case_legislation_refs(citation: str) -> str:
    """Get legislation references and case citations for a case.

    Returns all legislation sections cited in the case, cases cited by the
    case, and cases that cite this case. Use get_case for the full combined view
    including metadata, AI summary, and structured download sources.
    """
    from urllib.parse import quote
    citation_norm = _normalise_case_citation(citation) or citation
    citation_norm = _resolve_case_citation_alias(citation_norm)
    refs = get_case_references(citation_norm)

    return json.dumps({
        "citation": citation_norm,
        "legislation_refs": refs.get("legislation_refs", []),
        "case_citations": refs.get("case_citations", []),
        "cited_by": refs.get("cited_by", []),
    }, indent=2)


@mcp.tool(structured_output=False)
async def list_rulings(
    type: str | None = None,
    year: int | None = None,
    limit: int = 100,
    offset: int = 0,
    counts_only: bool = False,
) -> str:
    """List all ATO rulings grouped by year and type.

    Returns the full ruling tree with ATO.gov.au and AustLII links.
    """
    rulings = load_rulings()

    if type:
        filter_type = type.upper()
        rulings = [r for r in rulings if r.get("type", "").upper() == filter_type]
    if year:
        rulings = [r for r in rulings if r.get("year") == year]

    if counts_only:
        years: dict = {}
        no_year: dict = {}
        for r in rulings:
            y = r.get("year", 0)
            t = r.get("type", "Ruling")
            if y == 0:
                no_year[t] = no_year.get(t, 0) + 1
            else:
                if y not in years:
                    years[y] = {}
                years[y][t] = years[y].get(t, 0) + 1
        payload = {
            "mode": "counts_only",
            "total_rulings": len(rulings),
            "by_year": years,
        }
        if no_year:
            payload["no_year"] = no_year
            payload["no_year_total"] = sum(no_year.values())
            payload["note"] = (
                f"Rulings without a year field ({sum(no_year.values())} total) "
                f"grouped under 'no_year'."
            )
        return json.dumps(payload, indent=2)

    if limit > 0:
        rulings = rulings[offset:offset + limit]
    elif offset > 0:
        rulings = rulings[offset:]

    years_dict: dict = {}
    no_year_items = []
    for r in rulings:
        y = r.get("year", 0)
        t = r.get("type", "Ruling")
        if y == 0:
            no_year_items.append(r)
            continue
        if y not in years_dict:
            years_dict[y] = {}
        if t not in years_dict[y]:
            years_dict[y][t] = []
        years_dict[y][t].append({
            "citation": r["citation"],
            "citation_display": r.get("citation_display", ""),
            "title": r.get("full_title", r.get("title", "")),
            "withdrawn": r.get("withdrawn", False),
            "ato_url": r.get("ato_url", ""),
            "austlii_url": r.get("austlii_url", ""),
            "download_url": _abs(f"/api/ruling/{r['citation']}/download"),
        })

    payload = {
        "ato_rulings_total": len(rulings),
        "filter_type": type,
        "filter_year": year,
        "by_year": years_dict,
    }
    if no_year_items:
        payload["no_year"] = [
            {"citation": r["citation"], "title": r.get("full_title", r.get("title", "")),
             "withdrawn": r.get("withdrawn", False), "ato_url": r.get("ato_url", ""),
             "austlii_url": r.get("austlii_url", ""),
             "download_url": _abs(f"/api/ruling/{r['citation']}/download")}
            for r in no_year_items
        ]
        payload["no_year_total"] = len(no_year_items)
        payload["note"] = (
            f"Rulings without a year field ({len(no_year_items)} total) listed under 'no_year'."
        )

    return json.dumps(payload, indent=2)


@mcp.tool(structured_output=False)
async def get_ruling(citation: str) -> str:
    """Get a public ATO ruling by citation (e.g. 'TR 2024/1', 'CR 2017/74', 'PR 2008/70').

    Returns structured summary data (frontmatter, body, metadata) when a
    summary exists, otherwise raw metadata. Unknown citations return
    {"ok": false, "error": "not found"}.
    """
    from fastapi import HTTPException
    try:
        data = _get_ruling(citation)
    except HTTPException as exc:
        return json.dumps({
            "ok": False,
            "error": "not found",
            "detail": exc.detail,
        }, indent=2)
    except Exception as exc:  # pragma: no cover - unexpected failure path
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)
    return json.dumps(data, indent=2)


@mcp.tool(structured_output=False)
async def report_issue(
    category: Literal["bad_data", "missing_content", "stale_compilation", "wrong_result", "tool_error", "suggestion", "bug"],
    tool: str | None = None,
    params: dict | str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    note: str | None = None,
) -> str:
    """Report a bug or issue with a tool's output.

    Detects duplicates by (param_hash, category). If a matching open or
    known issue already exists, increments the hit counter and returns the
    existing ticket. Otherwise creates a new issue (CDN-NNNN) in the
    issues table.

    Args:
        category: Type of issue being reported.
        tool: Name of the tool that produced the wrong output.
        params: Parameters that were passed to the tool.
        expected: What the correct output should have been.
        actual: What the tool actually returned.
        note: Free-form notes about the issue.

    Returns:
        JSON with ticket, status, and duplicate_of keys.
    """
    # ── guard: reject if nothing meaningful was provided ─────────────────────
    has_content = any(
        str(v).strip()
        for v in (tool, note, expected, actual)
        if v is not None
    )
    if params not in (None, "", {}, []):
        has_content = True
    if not has_content:
        return json.dumps({
            "error": "report_issue requires at least one of tool, params, expected, actual, note",
            "ticket": None,
            "status": "rejected",
        })
    # ── compute param_hash (includes note to avoid hash collision) ────────
    raw_hash = ""
    if tool:
        if isinstance(params, dict):
            canonical_params = json.dumps(params, sort_keys=True, ensure_ascii=True, default=str)
        elif isinstance(params, str):
            try:
                p = json.loads(params)
                canonical_params = json.dumps(p, sort_keys=True, ensure_ascii=True, default=str)
            except (json.JSONDecodeError, TypeError):
                canonical_params = params
        else:
            canonical_params = "null"
        raw_hash = tool + canonical_params + (note or "")
    elif note:
        raw_hash = note
    else:
        raw_hash = str(category)
    param_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()[:16]

    # ── check for existing duplicate ───────────────────────────────────────
    dupes = _sql_dict(
        ["id", "ticket", "status"],
        f"SELECT id, ticket, status FROM issues "
        f"WHERE param_hash = '{param_hash}' AND category = '{category}' "
        f"AND status IN ('open', 'known')",
    )
    if dupes:
        existing = dupes[0]
        _sql_write_params(
            "UPDATE issues SET hits = hits + 1 WHERE id = %s",
            (existing["id"],),
        )
        return json.dumps({
            "ticket": existing["ticket"],
            "status": existing["status"],
            "duplicate_of": existing["ticket"],
        })

    # ── compute next ticket number (insert-first via docker exec, then derive from id) ─────
    import uuid
    placeholder = f"PH_{uuid.uuid4().hex[:12]}"
    params_val = json.dumps(params, default=str) if isinstance(params, (dict, list)) else params

    # Escape values for safe SQL interpolation (docker exec psql, not psycopg2)
    def _sqlesc(v):
        if v is None: return "NULL"
        return "'" + str(v).replace("'", "''") + "'"

    insert_sql = (
        "INSERT INTO issues (ticket, category, tool, params, param_hash, expected, actual, note, "
        "server_ver, compilation, created, status, known_note, hits, fixed) VALUES ("
        f"{_sqlesc(placeholder)}, {_sqlesc(category)}, {_sqlesc(tool)}, {_sqlesc(params_val)}, "
        f"{_sqlesc(param_hash)}, {_sqlesc(expected)}, {_sqlesc(actual)}, {_sqlesc(note)}, "
        f"{_sqlesc(VERSION)}, NULL, NOW(), 'open', NULL, 1, NULL)"
    )
    _sql(insert_sql)

    id_rows = _sql_dict(["new_id"], "SELECT MAX(id) AS new_id FROM issues")
    if not id_rows or not id_rows[0].get("new_id"):
        return json.dumps({"error": "Failed to create issue ticket"})
    new_id = id_rows[0]["new_id"]
    ticket = f"CDN-{new_id:04d}"
    _sql(f"UPDATE issues SET ticket = {_sqlesc(ticket)} WHERE id = {new_id}")
    _sql(f"DELETE FROM issues WHERE ticket = {_sqlesc(placeholder)}")

    return json.dumps({
        "ticket": ticket,
        "status": "open",
        "duplicate_of": None,
    })


@mcp.tool(structured_output=False)
async def list_issues(
    status: str | None = None,
    tool: str | None = None,
    limit: int = 50,
) -> str:
    """List reported issues with their current status and patch notes.

    Args:
        status: Filter by status (open, known, fixed, resolved). Omit for all.
        tool: Filter by tool name (e.g. 'get_section', 'get_case'). Omit for all.
        limit: Max results to return (default 50, max 200).

    Returns:
        JSON array of issues with ticket, category, tool, status, hits,
        fixed (patch note), and note fields.
    """
    where_parts = []
    if status:
        where_parts.append(f"status = '{status.replace(chr(39), chr(39)+chr(39))}'")
    if tool:
        where_parts.append(f"tool = '{tool.replace(chr(39), chr(39)+chr(39))}'")
    where = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    rows = _sql_dict(
        ["ticket", "category", "tool", "status", "hits",
         "fixed", "note", "created"],
        f"SELECT ticket, category, tool, status, hits, "
        f"fixed, LEFT(COALESCE(note, ''), 200)::text, created "
        f"FROM issues {where} ORDER BY id DESC LIMIT {min(max(1, limit), 200)}",
    )

    return json.dumps({
        "issues": rows,
        "total": len(rows),
        "filters_applied": {
            "status": status,
            "tool": tool,
        },
    }, indent=2)


@mcp.tool(structured_output=False)
async def graph_neighbourhood(key: str, depth: int = 1) -> str:
    """Return the graph context block for a node (graph spec §6.2).

    Gives an LLM the compact neighbourhood of any graph node without
    fetching full document text: per-edge-type counts + top exemplars.

    Args:
        key:    canonical graph key, e.g. "section:itaa-1997:118-110",
                "public_ruling:TR 2025/1", "case:[2015] HCA 48",
                "private_ruling:EV/1011261243735", "commentary:MTG:ch12".
                Accepts the resolved_by graph_key from resolve_alias.
        depth:  1 = node neighbourhood (~80 tokens); 2 = + aggregated
                neighbourhood-of-neighbourhood (<=400 tokens). Default 1.

    Returns:
        JSON {key, label, depth, tokens, text} where `text` is the
        token-lean block (header + lines like "INTERPRETED_BY: 4 rulings
        (TR 2025/1 | TD 2024/2)"). Unknown keys return an error object.
    """
    if depth not in (1, 2):
        return json.dumps({"error": "depth must be 1 or 2", "hint": _GET_INFO_HINT}, indent=2)
    from backend.services.graph_serialize import serialize as _serialize

    out = _serialize(key, depth=depth)
    if out is None:
        return json.dumps({
            "error": f"unknown graph key: {key}",
            "hint": _GET_INFO_HINT,
            "format_hint": "Try resolve_alias first, or /api/graph/data on the REST API.",
        }, indent=2)
    return json.dumps(out, indent=2)


@mcp.tool(structured_output=False)
async def graph_path(from_key: str, to_key: str, max_hops: int = 10) -> str:
    """Find the shortest path between two graph nodes (graph spec §6.3).

    Answers "how does this connect to that?" — e.g. the chain of
    rulings/cases/commentary linking a private ruling to a High Court case.

    Args:
        from_key: canonical graph key, e.g. "private_ruling:EV/1011261243735".
        to_key:   canonical graph key, e.g. "case:[1986] HCA 45".
        max_hops: hop cap (1-20, default 10).

    Returns:
        JSON {from, to, hops, path, edges} — path is the ordered node list
        (key + label per hop), edges give the typed connection per hop.
        Unreachable pairs return path: null with a reason.
    """
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    from backend.services.graph_path import (
        FRONTIER_CAP,
        FrontierExceeded,
        find_path as _find_path,
    )

    max_hops = max(1, min(int(max_hops), 20))
    graph_db = _Path(__file__).resolve().parents[1] / "data" / "graph.db"
    conn = _sqlite3.connect(str(graph_db))
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
            return json.dumps({
                "error": f"unknown graph key: {missing}",
                "hint": _GET_INFO_HINT,
                "format_hint": "Try resolve_alias first, or /api/graph/data on the REST API.",
            }, indent=2)

        try:
            path, hops = _find_path(conn, f_id, t_id, max_hops=max_hops)
        except FrontierExceeded as exc:
            return json.dumps({
                "from": from_key, "to": to_key, "path": None, "hops": None,
                "reason": f"frontier exceeded {exc} nodes at a level (cap {FRONTIER_CAP})",
            }, indent=2)

        if path is None:
            return json.dumps({
                "from": from_key, "to": to_key, "path": None, "hops": None,
                "reason": f"no path within {max_hops} hops",
            }, indent=2)

        ids = [nid for nid, _ in path]
        meta: dict[int, tuple[str, str]] = {}
        if ids:
            ph = ",".join("?" * len(ids))
            meta = {r[0]: (r[1], r[2]) for r in conn.execute(
                f"SELECT id, key, label FROM nodes WHERE id IN ({ph})", ids).fetchall()}

        return json.dumps({
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
        }, indent=2)
    finally:
        conn.close()




# ────────────────────────── quoting tool (standalone) ──────────────────────────

@mcp.tool(structured_output=False)
async def quote_info() -> str:
    """List all quotes (title, date, text) plus the library's style rules.

    Quotes are stored anonymised (PII replaced with [KIND_n] placeholders)
    when added via POST; library imports are stored verbatim.
    """
    from backend.routes.quotes import quote_info as _quote_info
    return json.dumps(_quote_info(), indent=2)


@mcp.tool(structured_output=False)
async def quote_fetch(keyword: str = "", limit: int = 10, offset: int = 0) -> str:
    """Browse or search the quote list (title + text).

    Empty keyword = browse all quotes, paginated (default 10 per page).
    Non-empty keyword = simple text search, best matches first (title hits
    weigh double). Response includes total/limit/offset so callers can page
    through with offset=limit.
    """
    from backend.routes.quotes import quote_fetch as _quote_fetch
    return json.dumps(_quote_fetch(keyword, limit=limit, offset=offset), indent=2)


@mcp.tool(structured_output=False)
async def quote_save(title: str, date: str, text: str, names: list[str] | None = None,
                     tag: str | None = None, cost: str | None = None,
                     currency: str | None = None, terms: str | None = None,
                     alt: str | None = None, anonymise: bool = True) -> str:
    """Save a quote to the quote library. Stored anonymised by default — PII
    (names, ABN/ACN, TFN) replaced with [KIND_n] placeholders via the firm's
    one-way masking. Pass names=[...] for exact known names (zero false
    positives). Pass anonymise=False ONLY for verbatim library imports of the
    firm's own texts (label heuristics corrupt business prose)."""
    from backend.routes.quotes import add_quote
    if not title.strip() or not text.strip():
        return json.dumps({"ok": False, "error": "title and text are required"})
    quote = add_quote(title, date, text, names, tag=tag, cost=cost,
                      currency=currency, terms=terms, alt=alt, anonymise=anonymise)
    return json.dumps({"ok": True, "anonymised": anonymise, "quote": quote}, indent=2)


def _parse_acts(acts_json):
    """Parse + validate acts for the proposed-law tree (accepts JSON string OR native list)."""
    import json as _json
    if isinstance(acts_json, str):
        try:
            acts = _json.loads(acts_json)
        except Exception:
            raise ValueError("acts must be a JSON string")
    else:
        acts = acts_json
    if not isinstance(acts, list):
        raise ValueError("acts must be a JSON list")
    clean = []
    for a in acts:
        if not isinstance(a, dict) or not str(a.get("name", "")).strip():
            continue
        rel = a.get("relation", "amended")
        if rel not in ("amended", "new", "introduced"):
            rel = "amended"
        if rel == "introduced":
            rel = "new"
        secs = []
        for sec in (a.get("sections") or []):
            if isinstance(sec, dict) and str(sec.get("title", "")).strip():
                secs.append({"title": str(sec["title"]).strip(),
                             "content": str(sec.get("content", ""))})
        clean.append({"name": str(a["name"]).strip(), "relation": rel, "sections": secs})
    return clean


@mcp.tool(structured_output=False)
async def proposed_law_list() -> str:
    """List all proposed-law items (tracked legislative proposals), newest first."""
    from backend.routes.proposed_law import load_items
    return json.dumps({"items": list(reversed(load_items()))}, indent=2)


@mcp.tool(structured_output=False)
async def proposed_law_add(title: str, summary: str = "", status: str = "announced",
                           measure_type: str = "other", announced_date: str | None = None,
                           source_url: str | None = None, notes: str = "",
                           commentary: str = "", acts: str | list | None = None) -> str:
    """Add an item to the Proposed Law tracker (a measure announced/developing but
    not yet enacted — Treasury Laws Amendment bills, exposure drafts, ATO drafts).
    status: announced | exposure_draft | before_parliament | passed | enacted | withdrawn.
    measure_type: bill | exposure_draft | announcement | ato_draft | other.
    acts: JSON string OR array of [{"name": "<Act name>", "relation": "amended|new",
          "sections": [{"title": "...", "content": "markdown"}]}] — the acts proposed
          to be amended or introduced and their proposed sections. commentary: one big
          markdown section for your notes on the proposal."""
    from backend.routes.proposed_law import STATUSES, MEASURE_TYPES, load_items, save_items
    import datetime as _dt
    if not title.strip():
        return json.dumps({"ok": False, "error": "title is required"})
    if status not in STATUSES:
        return json.dumps({"ok": False, "error": f"status must be one of {sorted(STATUSES)}"})
    if measure_type not in MEASURE_TYPES:
        return json.dumps({"ok": False, "error": f"measure_type must be one of {sorted(MEASURE_TYPES)}"})
    if acts is None:
        acts = "[]"
    items = load_items()
    item = {
        "id": _dt.datetime.now().strftime("%Y%m%d%H%M%S"),
        "title": title.strip(),
        "measure_type": measure_type,
        "status": status,
        "summary": summary.strip(),
        "announced_date": announced_date,
        "source_url": source_url,
        "notes": notes.strip(),
        "commentary": commentary,
        "acts": _parse_acts(acts),
        "added_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    while any(x["id"] == item["id"] for x in items):
        item["id"] += "x"
    items.append(item)
    save_items(items)
    return json.dumps({"ok": True, "item": item}, indent=2)


@mcp.tool(structured_output=False)
async def proposed_law_update(item_id: str, status: str | None = None,
                              measure_type: str | None = None, summary: str | None = None,
                              notes: str | None = None, source_url: str | None = None,
                              commentary: str | None = None, acts: str | list | None = None) -> str:
    """Update a proposed-law item by id. Status/measure_type/summary/notes/source_url
    are scalar. To update the tree content: pass commentary (full markdown string,
    replaces the whole commentary) and/or acts (full JSON string of the acts array —
    {"name":..., "relation":..., "sections":[...]}; replaces the whole acts list).
    Omit a field to leave it unchanged."""
    from backend.routes.proposed_law import STATUSES, MEASURE_TYPES, load_items, save_items
    items = load_items()
    for it in items:
        if it["id"] == item_id:
            if status is not None:
                if status not in STATUSES:
                    return json.dumps({"ok": False, "error": f"status must be one of {sorted(STATUSES)}"})
                it["status"] = status
            if measure_type is not None:
                if measure_type not in MEASURE_TYPES:
                    return json.dumps({"ok": False, "error": f"measure_type must be one of {sorted(MEASURE_TYPES)}"})
                it["measure_type"] = measure_type
            if summary is not None:
                it["summary"] = summary.strip()
            if notes is not None:
                it["notes"] = notes.strip()
            if source_url is not None:
                it["source_url"] = source_url
            if commentary is not None:
                it["commentary"] = commentary
            if acts is not None:
                it["acts"] = _parse_acts(acts)
            save_items(items)
            return json.dumps({"ok": True, "item": it}, indent=2)
    return json.dumps({"ok": False, "error": "item not found"})
