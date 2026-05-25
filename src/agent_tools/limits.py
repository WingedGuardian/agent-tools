"""IP rate limiting middleware.

Applies a per-IP request rate limit to all incoming traffic.
Paying agents (requests carrying X-PAYMENT header) are exempt —
payment IS the economic rate limiter for paid endpoints.

Uses the `limits` library (bundled with slowapi) for in-memory counting.
Fixed-window strategy: simple, low-overhead, no external state required.
"""

from __future__ import annotations

import os

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


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit by client IP, exempting requests that carry X-PAYMENT."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # Paying agents carry X-PAYMENT — payment is the rate limiter for them
        if request.headers.get("x-payment"):
            return await call_next(request)

        ip = (request.client.host if request.client else None) or "unknown"
        if not _limiter.hit(_limit, ip):
            return JSONResponse(
                {"error": f"Rate limit exceeded — {_FREE_RPM} req/min per IP. Retry after 60s."},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
