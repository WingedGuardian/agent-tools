"""Agent Tools — main FastAPI application."""

from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .endpoints import dns, email, headers, ip, qr, url, whois
from .mcp_server import mcp
from .payments import create_x402_middleware_args

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage MCP session lifecycle."""
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Agent Tools",
    version="0.1.0",
    description=(
        "Agent-native utility API bundle. "
        "Wraps high-demand utilities into clean JSON endpoints "
        "with x402 micropayments and MCP tool access."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow all origins for agent access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# x402 payment middleware — enabled when AGENT_TOOLS_PAY_TO is set
x402_args = create_x402_middleware_args()
if x402_args:
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI

    app.add_middleware(PaymentMiddlewareASGI, **x402_args)
    logger.info("x402 payments enabled (testnet=%s)", x402_args["paywall_config"].testnet)
else:
    logger.info("x402 payments disabled — set AGENT_TOOLS_PAY_TO to enable")

# Mount endpoint routers
app.include_router(qr.router)
app.include_router(dns.router)
app.include_router(email.router)
app.include_router(ip.router)
app.include_router(url.router)
app.include_router(whois.router)
app.include_router(headers.router)

# Mount MCP server at /mcp (streamable-http transport)
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health() -> dict:
    """Health check."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/")
async def root() -> dict:
    """Service discovery root — machine-readable capabilities."""
    return {
        "service": "agent-tools",
        "version": "0.1.0",
        "description": (
            "Agent-native utility API. QR code generation, DNS health checks, "
            "and more. Supports x402 micropayments and MCP tool access."
        ),
        "endpoints": [
            {
                "path": "/v1/qr/generate/image",
                "method": "GET",
                "description": "Generate QR code image from text/URL",
                "price": "$0.001",
            },
            {
                "path": "/v1/dns/health",
                "method": "GET",
                "description": "DNS health check — records, mail security, resolution",
                "price": "$0.003",
            },
            {
                "path": "/v1/email/validate",
                "method": "GET",
                "description": "Email validation — format, MX, disposable, SMTP probe",
                "price": "$0.005",
            },
            {
                "path": "/v1/ip/lookup",
                "method": "GET",
                "description": "IP geolocation, ISP, proxy/hosting detection, reverse DNS",
                "price": "$0.005",
            },
            {
                "path": "/v1/url/health",
                "method": "GET",
                "description": "URL health check — status, redirects, SSL, response time",
                "price": "$0.003",
            },
            {
                "path": "/v1/whois/lookup",
                "method": "GET",
                "description": "WHOIS domain lookup — registrar, dates, nameservers",
                "price": "$0.005",
            },
            {
                "path": "/v1/headers/analyze",
                "method": "GET",
                "description": "HTTP security headers analysis with score",
                "price": "$0.003",
            },
        ],
        "payment": {
            "x402": "USDC on Base (EIP-3009)",
            "api_key": "X-API-Key header",
        },
        "mcp": "/mcp",
        "docs": "/docs",
    }
