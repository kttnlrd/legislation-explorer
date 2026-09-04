"""backend/main.py — FastAPI app for Legislation Explorer.

Serves:
  - React SPA static files
  - JSON API for tree, sections, definitions, search
  - MCP over Streamable HTTP
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import ALLOWED_ORIGINS, FRONTEND_DIST, SEARCH_DB
from backend import config
from backend.logging_config import setup_logging
from backend.middleware.metrics import MetricsMiddleware
from backend.middleware.ratelimit import RateLimitMiddleware
from backend.routes.api import router as api_router
from backend.routes.maps import router as maps_router
from backend.routes.social import router as social_router
from backend.routes.mcp import router as mcp_router
from backend.routes.ato import router as ato_router
from backend.routes.quotes import router as quotes_router
from backend.routes.proposed_law import router as proposed_law_router
from backend.fastmcp_server import mcp as fastmcp, MCPAuthMiddleware
from backend.services.search_service import init_search_index
from backend.services import vector_search_service

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build search index in background on startup if missing or stale."""
    loop = asyncio.get_running_loop()
    if not SEARCH_DB.exists():
        logger.info("Search index missing, building in background...")
        await loop.run_in_executor(None, init_search_index)
    await loop.run_in_executor(None, vector_search_service.load)

    # Preload lazy caches so the first request doesn't pay cold-start cost.
    from backend.routes.search import _load_private_rulings_index
    from backend.services.graph_alias import _load_alias_map, _graph_key_set
    from backend.services.data_loader import load_tree, load_acts_meta

    def _preload_trees():
        for a in load_acts_meta():
            load_tree(a["id"])

    for _name, _fn in (
        ("private_rulings_index", _load_private_rulings_index),
        ("alias_map", _load_alias_map),
        ("graph_keys", _graph_key_set),
        ("act_trees", _preload_trees),
    ):
        try:
            await loop.run_in_executor(None, _fn)
        except Exception:
            logger.exception("Startup preload failed: %s", _name)

    # Run FastMCP session manager (handles Streamable HTTP connections)
    async with fastmcp._session_manager.run():
        yield


app = FastAPI(title="Legislation Explorer", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# GZip compression for large JSON payloads
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Metrics
app.add_middleware(MetricsMiddleware)

# Rate limiting (on by default, disable with RATE_LIMIT_ENABLED=false)
app.add_middleware(RateLimitMiddleware, enabled=os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true")

# ---------------------------------------------------------------------------
# Microsoft Entra ID SSO auth
# ---------------------------------------------------------------------------

if os.environ.get("AZURE_CLIENT_ID"):
    from starlette.middleware.sessions import SessionMiddleware
    from backend.auth import AuthMiddleware, login, callback, logout, me
    from backend.oauth_provider import (
        handle_well_known,
        handle_authorize,
        handle_token,
        handle_register,
        handle_revoke,
    )

    app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "change-me"), session_cookie="starlette_session")
    app.add_middleware(AuthMiddleware)

    app.add_api_route("/auth/login", login, methods=["GET"])
    app.add_api_route("/auth/callback", callback, methods=["GET"])
    app.add_api_route("/auth/logout", logout, methods=["GET"])
    app.add_api_route("/auth/me", me, methods=["GET"])

    # OAuth 2.1 endpoints for MCP Connector auth
    app.add_api_route(
        "/.well-known/oauth-authorization-server",
        handle_well_known,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route("/oauth/authorize", handle_authorize, methods=["GET"])
    app.add_api_route("/oauth/token", handle_token, methods=["POST"])
    app.add_api_route("/oauth/register", handle_register, methods=["POST"])
    app.add_api_route("/oauth/revoke", handle_revoke, methods=["POST"])
    logger.info("Microsoft Entra ID auth enabled")
    logger.info("OAuth 2.1 MCP endpoints enabled")

# ---------------------------------------------------------------------------
# Fallback: bearer token auth (when SSO is not configured)
# ---------------------------------------------------------------------------

if not os.environ.get("AZURE_CLIENT_ID"):

    @app.middleware("http")
    async def bearer_auth_middleware(request: Request, call_next):
        path = request.url.path
        if path in ("/health", "/", "/favicon.ico") or path.startswith(("/assets/", "/mcp/", "/api/cadena/", "/api/private/", "/api/v2/", "/api/rpc/", "/auth/", "/oauth/", "/.well-known/")):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        if config.BEARER_TOKEN is None:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != config.BEARER_TOKEN:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


# Health check
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Detailed health check for monitoring
# ---------------------------------------------------------------------------

@app.get("/health/check")
def health_check():
    """Detailed health check: DB, FTS5 search, memory, PG connectivity.

    Returns structured pass/fail with diagnostics. Unauthenticated so the
    monitor cron can hit it without a token.
    """
    import psutil

    checks = {}

    # 1. Search DB exists and FTS5 queryable
    try:
        conn = sqlite3.connect(str(SEARCH_DB))
        conn.execute("SELECT 1 FROM sections_fts LIMIT 1")
        conn.close()
        checks["search_db"] = {"status": "pass"}
    except Exception as e:
        checks["search_db"] = {"status": "fail", "detail": str(e)}

    # 2. PostgreSQL connectivity (via PGHOST from env)
    pg_host = os.environ.get("PGHOST", "")
    if pg_host:
        import subprocess
        try:
            r = subprocess.run(
                ["psql", "-h", pg_host, "-U", os.environ.get("PGUSER", "postgres"),
                 "-d", os.environ.get("PGDATABASE", "cadena_knowledge"),
                 "-c", "SELECT 1", "-t", "-q"],
                capture_output=True, timeout=5,
                env={**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "")}
            )
            if r.returncode == 0:
                checks["postgres"] = {"status": "pass"}
            else:
                checks["postgres"] = {"status": "fail", "detail": r.stderr.decode()[:200]}
        except Exception as e:
            checks["postgres"] = {"status": "fail", "detail": str(e)}

    # 3. Memory usage
    mem = psutil.virtual_memory()
    checks["memory"] = {
        "status": "pass" if mem.percent < 90 else "warn",
        "percent": mem.percent,
        "available_mb": mem.available // (1024 * 1024),
    }

    # 4. Process uptime
    try:
        p = psutil.Process(os.getpid())
        created = datetime.fromtimestamp(p.create_time())
        checks["uptime"] = {
            "status": "pass",
            "seconds": int((datetime.now() - created).total_seconds()),
        }
    except Exception as e:
        checks["uptime"] = {"status": "error", "detail": str(e)}

    overall = all(c.get("status") == "pass" for c in checks.values())
    return {
        "status": "ok" if overall else "degraded",
        "checks": checks,
    }


# API routes
app.include_router(social_router)
app.include_router(maps_router)
app.include_router(api_router)
app.include_router(mcp_router)
app.include_router(ato_router)
app.include_router(quotes_router)
app.include_router(proposed_law_router)


# MCP Streamable HTTP via FastMCP
# We add the route directly (not mount) so the FastMCP session manager
# can be run inside the app lifespan below.
from starlette.routing import Route as StarletteRoute

fastmcp_app = fastmcp.streamable_http_app()

# Extract the ASGI handler from the first route and wrap with auth middleware
_mcp_raw_handler = fastmcp_app.routes[0].app  # StreamableHTTPASGIApp.__call__
_mcp_handler = MCPAuthMiddleware(_mcp_raw_handler)
app.router.routes.insert(
    0,
    StarletteRoute("/mcp", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
app.router.routes.insert(
    1,
    StarletteRoute("/mcp/{path:path}", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
# Also mount at /api/cadena/mcp (bypasses Cloudflare WAF)
app.router.routes.insert(
    2,
    StarletteRoute("/api/cadena/mcp", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
app.router.routes.insert(
    3,
    StarletteRoute("/api/cadena/mcp/{path:path}", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
# Also mount at /api/private/mcp (Cloudflare WAF bypass)
app.router.routes.insert(
    4,
    StarletteRoute("/api/private/mcp", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
app.router.routes.insert(
    5,
    StarletteRoute("/api/private/mcp/{path:path}", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
# Also mount at /api/v2/query (no 'mcp' in path — bypasses Cloudflare WAF)
app.router.routes.insert(
    6,
    StarletteRoute("/api/v2/query", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
app.router.routes.insert(
    7,
    StarletteRoute("/api/v2/query/{path:path}", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
# Clean path for rpc.scriptkitty.yachts
app.router.routes.insert(
    8,
    StarletteRoute("/api/rpc", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)
app.router.routes.insert(
    9,
    StarletteRoute("/api/rpc/{path:path}", endpoint=_mcp_handler, methods=["GET", "POST", "DELETE"]),
)


# Static files / SPA fallback
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if SCRIPTS_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(SCRIPTS_DIR)), name="static")

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Return 404 for OAuth probe paths — prevents Claude connector
        # from thinking OAuth metadata endpoints exist
        if full_path.startswith("register") or full_path.startswith("register/"):
            return JSONResponse({"error": "Not found"}, status_code=404)

        # Serve actual files from FRONTEND_DIST (favicon, manifest, etc.)
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path, headers={
                "Cache-Control": "public, max-age=3600",
            })

        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index, headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            })
        return HTMLResponse("<h1>Legislation Explorer</h1><p>Frontend not built yet.</p>")
