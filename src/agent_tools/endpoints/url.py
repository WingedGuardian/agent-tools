"""URL health check endpoint.

Checks if URLs are alive, follows redirects, reports status codes,
SSL certificate info, and response metadata. Self-hosted, no upstream cost.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/url", tags=["url"])


class RedirectHop(BaseModel):
    url: str
    status_code: int


class SSLInfo(BaseModel):
    issuer: str | None = None
    subject: str | None = None
    expires: str | None = None
    valid: bool = False


class URLHealthResult(BaseModel):
    url: str
    reachable: bool
    status_code: int | None = None
    final_url: str | None = None
    redirects: list[RedirectHop] = []
    content_type: str | None = None
    content_length: int | None = None
    server: str | None = None
    response_time_ms: int | None = None
    ssl: SSLInfo | None = None
    error: str | None = None


@router.get("/health", response_model=URLHealthResult)
async def url_health(
    url: str = Query(..., max_length=2048, description="URL to check"),
    follow_redirects: bool = Query(True, description="Follow redirects"),
) -> URLHealthResult:
    """Check if a URL is alive — status, redirects, SSL, response time."""
    import time

    import httpx

    result: dict = {"url": url, "reachable": False}

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
        result["url"] = url

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=follow_redirects,
            verify=True,
        ) as client:
            resp = await client.get(url)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        result["reachable"] = True
        result["status_code"] = resp.status_code
        result["final_url"] = str(resp.url)
        result["content_type"] = resp.headers.get("content-type")
        result["server"] = resp.headers.get("server")
        result["response_time_ms"] = elapsed_ms

        # Content length
        cl = resp.headers.get("content-length")
        if cl and cl.isdigit():
            result["content_length"] = int(cl)

        # Redirect chain
        if resp.history:
            result["redirects"] = [
                RedirectHop(url=str(r.url), status_code=r.status_code)
                for r in resp.history
            ]

        # SSL info for HTTPS URLs
        if str(resp.url).startswith("https://"):
            result["ssl"] = _extract_ssl_info(str(resp.url))

    except httpx.ConnectError as e:
        result["error"] = f"Connection failed: {e}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out (10s)"
    except httpx.TooManyRedirects:
        result["error"] = "Too many redirects"
    except Exception as e:
        result["error"] = str(e)

    return URLHealthResult(**result)


def _extract_ssl_info(url: str) -> SSLInfo:
    """Extract SSL certificate info from a URL."""
    import ssl
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port or 443

    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(
            __import__("socket").create_connection((hostname, port), timeout=5),
            server_hostname=hostname,
        ) as sock:
            cert = sock.getpeercert()
            if not cert:
                return SSLInfo(valid=False)

            issuer = dict(x[0] for x in cert.get("issuer", []))
            subject = dict(x[0] for x in cert.get("subject", []))
            return SSLInfo(
                issuer=issuer.get("organizationName"),
                subject=subject.get("commonName"),
                expires=cert.get("notAfter"),
                valid=True,
            )
    except Exception:
        return SSLInfo(valid=False)
