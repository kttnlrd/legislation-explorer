"""In-memory sliding-window rate limiter for FastAPI.

Uses a dict-of-deques keyed by (ip, route_prefix) so that:
  - /api/search/* has its own bucket
  - /mcp/sse has its own bucket (tighter limit)
  - Admin endpoints have a moderate limit
"""

import time
import logging
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

# (route_prefix, window_seconds, max_requests)
RATE_LIMITS: list[tuple[str, int, int]] = [
    ("/mcp/sse",       60, 60),    # 60 req/min
    ("/mcp/messages",  60, 120),   # 120 req/min
    ("/auth/",         60, 60),    # 60 req/min
    ("/api/admin/",    60, 60),    # 60 req/min
    ("/api/user/",     60, 60),    # 60 req/min
    ("/api/mcp-token", 60, 60),    # 60 req/min
    ("/api/",          60, 300),   # 300 req/min — general API
    ("",               60, 600),   # fallback: 600 req/min
]

_STRICT_PREFIXES = {"/mcp/sse", "/mcp/messages", "/auth/"}


def _find_limit(path: str) -> tuple[int, int]:
    for prefix, window, max_req in RATE_LIMITS:
        if path.startswith(prefix):
            return window, max_req
    return 60, 300  # fallback


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by (ip, prefix)."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        # buckets[(ip, prefix)] = deque of timestamps
        self._buckets: dict[tuple[str, str], deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Skip static assets
        path = request.url.path
        if path.startswith("/assets/"):
            return await call_next(request)

        # Get client IP (respecting Cloudflare / proxy headers)
        ip = request.headers.get("cf-connecting-ip")
        if not ip:
            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
            ip = ip.split(",")[0].strip()

        window, max_req = _find_limit(path)
        key = (ip, path)

        now = time.time()
        bucket = self._buckets[key]

        # Prune timestamps outside the window
        cutoff = now - window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_req:
            retry_after = int(bucket[0] + window - now) + 1
            logger.warning(
                "Rate limit hit",
                extra={"extra_info": {"ip": ip, "path": path, "limit": max_req, "window": window}},
            )
            return JSONResponse(
                {"detail": f"Rate limit exceeded. Try again in {retry_after}s."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        return await call_next(request)
