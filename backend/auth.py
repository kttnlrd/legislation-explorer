"""Microsoft Entra ID (Azure AD) authentication for legislation-explorer.

Uses authlib OAuth client + signed session cookies.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from authlib.integrations.starlette_client import OAuth
from jose import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from urllib.parse import quote

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

CLIENT_ID = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]
TENANT_ID = os.environ["AZURE_TENANT_ID"]
SESSION_SECRET = os.environ.get("SESSION_SECRET", CLIENT_SECRET)
REDIRECT_URI = "https://legislation.scriptkitty.yachts/auth/callback"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Whitelist: paths that don't require authentication
PUBLIC_PATHS = {
    "/auth/login",
    "/auth/callback",
    "/auth/logout",
    "/health",
    "/health/check",
    "/favicon.ico",
    "/api/cadena/mcp",
    "/.well-known/oauth-authorization-server",
}

# Only these email domains may sign in (comma-separated env override).
ALLOWED_EMAIL_DOMAINS = {
    d.strip().lower()
    for d in os.environ.get("ALLOWED_EMAIL_DOMAINS", "cadenalegal.com.au").split(",")
    if d.strip()
}

# Static asset extensions served at the SPA root (favicon, images, manifest, fonts)
# that must stay public so the browser can load them before/around sign-in. Not
# sensitive — all legal data is served via /api/* JSON, which remains session-gated.
_PUBLIC_STATIC_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".webmanifest", ".woff", ".woff2", ".ttf", ".otf",
)


def _email_allowed(email: str) -> bool:
    """True if the email's domain is in the allowlist (case-insensitive)."""
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].strip().lower() in ALLOWED_EMAIL_DOMAINS

# ── OAuth client ────────────────────────────────────────────────────────────

oauth = OAuth()
oauth.register(
    name="microsoft",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    server_metadata_url=f"{AUTHORITY}/v2.0/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ── Session token helpers ────────────────────────────────────────────────────


def create_session_token(claims: dict[str, Any]) -> str:
    """Create a signed JWT session token."""
    payload = {
        **claims,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


def decode_session_token(token: str) -> dict[str, Any] | None:
    """Decode a signed JWT session token. Returns None if invalid/expired."""
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except Exception:
        return None

# ── Gated paths (require login to access) ────────────────────────────────────

GATED_PREFIXES = {
    "/api/cadena/",
    "/mcp/cadena/",
    # Premium / internal-only Cadena IP — must not be reachable unauthenticated
    # (firm pricing, procedural maps, CCH commentary, Keays insolvency, private
    # rulings, proposed law, ATO legal database, internal issue queue).
    "/api/private-rulings",
    "/api/private-ruling",
    "/api/quotes",
    "/api/maps",
    "/api/ato",
    "/api/proposed-law",
    "/api/commentary",
    "/api/insolvency",
    "/api/issues",
}

# ── Auth routes ──────────────────────────────────────────────────────────────


async def login(request: Request) -> RedirectResponse:
    """Redirect the user to Microsoft Entra ID login. Supports ?next= redirect after auth."""
    next_url = request.query_params.get("next", "/")
    if next_url and next_url != "/":
        # Store next_url in session so it survives the Azure AD round-trip
        request.session["auth_next"] = next_url
    redirect = await oauth.microsoft.authorize_redirect(request, redirect_uri=REDIRECT_URI)
    return redirect


async def callback(request: Request) -> RedirectResponse:
    """Handle the OAuth callback from Microsoft."""
    try:
        token = await oauth.microsoft.authorize_access_token(request)
        userinfo = token.get("userinfo") or {}
        id_token = token.get("id_token") or {}

        # Build session claims
        claims = {
            "sub": userinfo.get("sub") or id_token.get("sub", ""),
            "name": userinfo.get("name") or id_token.get("name", ""),
            "email": userinfo.get("email") or id_token.get("preferred_username", ""),
        }

        # Only authorized email domains may sign in.
        if not _email_allowed(claims.get("email", "")):
            logger.warning("Denied login for non-allowlisted email domain: %s", claims.get("email", ""))
            return RedirectResponse(url="/?error=not_authorized", status_code=303)

        session_token = create_session_token(claims)
        # Log the login
        from backend.services.login_log import log_login
        log_login(claims.get("email", ""), claims.get("name", ""))

        # Check if we have a ?next= redirect from the OAuth authorize flow
        # First try query param (legacy), then session (OAuth flow)
        next_url = request.query_params.get("next")
        if not next_url or next_url == "/":
            next_url = request.session.pop("auth_next", "/")
        if next_url == "":
            next_url = "/"

        response = RedirectResponse(url=next_url, status_code=303)
        response.set_cookie(
            key="session",
            value=session_token,
            max_age=28800,  # 8 hours
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response
    except Exception as e:
        logger.exception("Auth callback failed")
        return RedirectResponse(url=f"/?error=auth_failed", status_code=303)


async def logout(request: Request) -> RedirectResponse:
    """Clear the session cookie and redirect to Microsoft logout."""
    response = RedirectResponse(
        url=f"{AUTHORITY}/oauth2/v2.0/logout?post_logout_redirect_uri=https://legislation.scriptkitty.yachts",
        status_code=303,
    )
    response.delete_cookie("session", path="/")
    return response


async def me(request: Request) -> JSONResponse:
    """Return the current user's info if authenticated."""
    session = getattr(request.state, "user", None)
    if not session:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return JSONResponse({
        "name": session.get("name", ""),
        "email": session.get("email", ""),
        "authenticated": True,
    })


# ── Middleware ────────────────────────────────────────────────────────────────


class AuthMiddleware(BaseHTTPMiddleware):
    """Protect the entire site behind Microsoft Entra ID auth, restricted to
    allowlisted email domains. Only /auth/*, /health, static assets, OAuth,
    well-known, and the MCP mounts (which carry their own token auth) are
    public. Everything else requires an Entra session.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        path = request.url.path

        # Public (no session): auth flow, health, static assets, OAuth,
        # well-known, and the MCP mounts (token-gated by MCPAuthMiddleware).
        if (path in PUBLIC_PATHS
                or path.startswith("/assets/")
                or path == "/mcp"
                or path.startswith("/mcp/")
                or path.startswith("/auth/")
                or path.startswith("/oauth/")
                or path.startswith("/.well-known/")
                or path.startswith("/api/cadena/mcp")
                or path.startswith("/api/private/mcp")
                or path.startswith("/api/v2/query")
                or path.startswith("/api/rpc")
                or path.lower().endswith(_PUBLIC_STATIC_EXTS)):
            request.state.user = None
            return await call_next(request)

        # Everything else requires an Azure (Entra ID) session.
        session_token = request.cookies.get("session")
        user = decode_session_token(session_token) if session_token else None

        if user:
            email = (user.get("email") or "").lower()
            if not _email_allowed(email):
                return JSONResponse(
                    {"error": "Not authorized", "detail": "Email domain not allowed"},
                    status_code=403,
                )
            request.state.user = user
            return await call_next(request)

        # No session: API callers get 401; browser requests go to Azure sign-in.
        if path.startswith("/api/"):
            return JSONResponse({"error": "Login required"}, status_code=401)
        return RedirectResponse(url=f"/auth/login?next={quote(path, safe='')}", status_code=303)

# ── Helper: get current user in route handlers ─────────────────────────────


def require_user(request: Request) -> dict[str, Any]:
    """Get the authenticated user from request state. Raises 401 if missing."""
    user = getattr(request.state, "user", None)
    if not user:
        from starlette.responses import JSONResponse as JR
        raise JR({"error": "Not authenticated"}, status_code=401)
    return user
