"""MCP server — exposes agent-tools endpoints as MCP tools.

Mounted into the FastAPI app at /mcp via streamable-http transport.
Agents connect remotely and discover tools like qr_generate, dns_health.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Agent Tools",
    instructions=(
        "Utility tools for agents. QR code generation, DNS health checks, "
        "and more. Each tool returns structured JSON."
    ),
    stateless_http=True,
)


@mcp.tool()
async def qr_generate(data: str, size: int = 256) -> str:
    """Generate a QR code image from text or URL.

    Returns base64-encoded PNG image data.

    Args:
        data: The text or URL to encode in the QR code.
        size: Image size in pixels (64-2048). Default 256.
    """
    import base64

    from .endpoints.qr import QRFormat, _render_qr

    if len(data) > 4000:
        return "Error: data exceeds 4000 character limit"
    size = max(64, min(2048, size))
    img_bytes = _render_qr(data, size, QRFormat.png)
    b64 = base64.b64encode(img_bytes).decode()
    return f"data:image/png;base64,{b64}"


@mcp.tool()
async def dns_health(domain: str, include_txt: bool = False) -> dict:
    """Check DNS health for a domain.

    Returns A/AAAA/MX/NS records, SPF/DMARC mail security status,
    and whether the domain resolves.

    Args:
        domain: The domain name to check (e.g. "example.com").
        include_txt: Whether to include all TXT records. Default false.
    """

    # Reuse the endpoint logic directly
    from .endpoints.dns import dns_health as _dns_health_endpoint

    result = await _dns_health_endpoint(domain=domain, include_txt=include_txt)
    return result.model_dump()


@mcp.tool()
async def email_validate(email: str, check_smtp: bool = False) -> dict:
    """Validate an email address.

    Checks format, MX records, disposable domain, role account,
    and optionally probes SMTP to verify the mailbox exists.

    Args:
        email: The email address to validate.
        check_smtp: Whether to probe the SMTP server (slower, 2-5s). Default false.
    """
    from .endpoints.email import validate_email as _validate_email_endpoint

    result = await _validate_email_endpoint(email=email, check_smtp=check_smtp)
    return result.model_dump()


@mcp.tool()
async def ip_lookup(ip: str, geo: bool = True) -> dict:
    """Look up an IP address.

    Returns geolocation, ISP, proxy/hosting detection, and reverse DNS.

    Args:
        ip: IPv4 or IPv6 address to look up.
        geo: Include geolocation data (country, city, lat/lon). Default true.
    """
    from .endpoints.ip import ip_lookup as _ip_lookup_endpoint

    result = await _ip_lookup_endpoint(ip=ip, geo=geo)
    return result.model_dump()


@mcp.tool()
async def url_health(url: str, follow_redirects: bool = True) -> dict:
    """Check if a URL is alive and healthy.

    Returns status code, redirect chain, SSL certificate info,
    response time, and server details.

    Args:
        url: The URL to check (e.g. "https://example.com").
        follow_redirects: Whether to follow redirects. Default true.
    """
    from .endpoints.url import url_health as _url_health_endpoint

    result = await _url_health_endpoint(url=url, follow_redirects=follow_redirects)
    return result.model_dump()


@mcp.tool()
async def whois_lookup(domain: str) -> dict:
    """WHOIS lookup for a domain.

    Returns registrar, creation/expiration dates, nameservers,
    domain status codes, and registrant info when available.

    Args:
        domain: The domain name to look up (e.g. "example.com").
    """
    from .endpoints.whois import whois_lookup as _whois_endpoint

    result = await _whois_endpoint(domain=domain)
    return result.model_dump()


@mcp.tool()
async def headers_analyze(url: str) -> dict:
    """Analyze HTTP response headers for a URL.

    Returns all response headers plus a security header audit
    with a 0-100 score checking HSTS, CSP, X-Frame-Options, etc.

    Args:
        url: The URL to analyze (e.g. "https://example.com").
    """
    from .endpoints.headers import analyze_headers as _headers_endpoint

    result = await _headers_endpoint(url=url)
    return result.model_dump()


@mcp.tool()
async def extract_text(url: str, max_length: int = 5000) -> dict:
    """Extract clean readable text from a webpage.

    Strips HTML, navigation, ads, scripts, and boilerplate.
    Returns clean text, title, description, word count, and language.

    Args:
        url: The URL to extract text from.
        max_length: Max characters to return (100-50000). Default 5000.
    """
    from .endpoints.extract import extract_text as _extract_endpoint

    max_length = max(100, min(50000, max_length))
    result = await _extract_endpoint(url=url, max_length=max_length)
    return result.model_dump()


@mcp.tool()
async def tech_detect(url: str) -> dict:
    """Detect the technology stack of a website.

    Analyzes HTTP headers, HTML, and script sources to identify
    frameworks (React, Vue, Next.js), CMS (WordPress, Shopify),
    CDN (Cloudflare, Fastly), analytics, and more.

    Args:
        url: The URL to analyze (e.g. "https://example.com").
    """
    from .endpoints.techdetect import detect_tech as _tech_endpoint

    result = await _tech_endpoint(url=url)
    return result.model_dump()
