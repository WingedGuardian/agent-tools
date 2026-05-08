"""HTTP headers analysis endpoint.

Fetches HTTP response headers for a URL and analyzes security headers.
Self-hosted, no upstream cost.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/headers", tags=["headers"])

# Security headers to check
_SECURITY_HEADERS = {
    "strict-transport-security": "HSTS — enforces HTTPS",
    "content-security-policy": "CSP — prevents XSS and injection",
    "x-content-type-options": "Prevents MIME-type sniffing",
    "x-frame-options": "Prevents clickjacking",
    "x-xss-protection": "Legacy XSS filter (deprecated but still checked)",
    "referrer-policy": "Controls referrer information",
    "permissions-policy": "Controls browser feature access",
    "cross-origin-opener-policy": "COOP — isolates browsing context",
    "cross-origin-resource-policy": "CORP — controls resource sharing",
    "cross-origin-embedder-policy": "COEP — controls embedding",
}


class SecurityHeaderCheck(BaseModel):
    header: str
    present: bool
    value: str | None = None
    description: str


class HeadersResult(BaseModel):
    url: str
    status_code: int | None = None
    headers: dict[str, str] = {}
    security_score: int = 0  # 0-100
    security_checks: list[SecurityHeaderCheck] = []
    server: str | None = None
    powered_by: str | None = None
    content_type: str | None = None
    error: str | None = None


@router.get("/analyze", response_model=HeadersResult)
async def analyze_headers(
    url: str = Query(..., max_length=2048, description="URL to analyze"),
) -> HeadersResult:
    """Analyze HTTP response headers — all headers plus security header audit."""
    import httpx

    result: dict = {"url": url}

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
        result["url"] = url

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            verify=True,
        ) as client:
            resp = await client.head(url)

        result["status_code"] = resp.status_code
        result["headers"] = dict(resp.headers)
        result["server"] = resp.headers.get("server")
        result["powered_by"] = resp.headers.get("x-powered-by")
        result["content_type"] = resp.headers.get("content-type")

        # Security header checks
        checks = []
        present_count = 0
        for header, description in _SECURITY_HEADERS.items():
            value = resp.headers.get(header)
            is_present = value is not None
            if is_present:
                present_count += 1
            checks.append(SecurityHeaderCheck(
                header=header,
                present=is_present,
                value=value,
                description=description,
            ))

        result["security_checks"] = checks
        result["security_score"] = int(present_count / len(_SECURITY_HEADERS) * 100)

    except httpx.ConnectError as e:
        result["error"] = f"Connection failed: {e}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out (10s)"
    except Exception as e:
        result["error"] = str(e)

    return HeadersResult(**result)
