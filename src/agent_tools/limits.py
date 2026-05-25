"""IP rate limiting middleware.

Applies a per-IP request rate limit to all incoming traffic.
OPTIONS preflight requests are exempt (browser CORS — no cost to server).

Paying agents are NOT given a blanket bypass via X-PAYMENT header because
that header is trivially forgeable and would allow anyone to skip rate limits
on free endpoints. Paid endpoints are already gated by x402 signature
verification at the middleware level — payment is enforced there, not here.

Uses the `limits` library (bundled with slowapi) for in-memory counting.
Fixed-window strategy: simple, low-overhead, no external state required.

IMPORTANT: MemoryStorage is per-process. With multiple uvicorn workers each
worker gets an independent counter, so the effective limit is RPM × workers.
We run single-worker in Docker (CMD has no --workers flag) so this is safe.
To support multi-worker: replace MemoryStorage with RedisStorage.
"""

from __future__ import annotations

import math
import os
import time

from limits import parse as _parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_FREE_RPM = int(os.getenv("RATE_LIMIT_FREE_PER_MIN", "60"))

_storage = MemoryStorage()
_limiter = FixedWindowRateLimiter(_storage)
_limit = _parse(f"{_FREE_RPM}/minute")


def _client_ip(request: Request) -> str | None:
    """Extract the real client IP, preferring Cloudflare's CF-Connecting-IP."""
    # Cloudflare sets this to the original client IP (trusted behind CF tunnel)
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    # Standard forwarded header (may be spoofed without trusted proxy)
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit by client IP. OPTIONS preflight requests are exempt."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # OPTIONS preflight — exempt (no cost, breaks CORS otherwise)
        if request.method == "OPTIONS":
            return await call_next(request)

        ip = _client_ip(request)
        if ip is None:
            # No identifiable client — reject rather than funnel into shared bucket
            return JSONResponse(
                {"error": "Unable to identify client address"},
                status_code=400,
            )

        if not _limiter.hit(_limit, ip):
            # Calculate seconds until the current window resets
            window_reset = math.ceil(60 - (time.time() % 60))
            return JSONResponse(
                {"error": f"Rate limit exceeded — {_FREE_RPM} req/min per IP."},
                status_code=429,
                headers={"Retry-After": str(window_reset)},
            )
        return await call_next(request)
