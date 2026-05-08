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
