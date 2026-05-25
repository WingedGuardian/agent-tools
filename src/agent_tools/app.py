"""Agent Tools — main FastAPI application."""

from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .endpoints import dns, email, extract, headers, ip, qr, techdetect, url, whois
from .limits import IPRateLimitMiddleware
from .mcp_payments import MCPPaymentMiddleware
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

# IP rate limiting — 60 req/min per IP for non-paying traffic.
# Paying agents (X-PAYMENT header) are exempt: payment IS the rate limiter.
# CORS allows all origins: agents don't have meaningful browser origins, and
# x402 payment signatures prevent CSRF abuse of paid endpoints.
app.add_middleware(IPRateLimitMiddleware)

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
    # MCP payment gate — added after PaymentMiddlewareASGI so it wraps the outer layer.
    # Request flow: MCPPaymentMiddleware → PaymentMiddlewareASGI → CORSMiddleware → routes.
    # tools/call on /mcp is gated here; /v1/* routes are gated by PaymentMiddlewareASGI.
    app.add_middleware(
        MCPPaymentMiddleware,
        server=x402_args["server"],
        testnet=x402_args["paywall_config"].testnet,
    )
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
app.include_router(extract.router)
app.include_router(techdetect.router)

# Mount MCP server at /mcp (streamable-http transport)
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health() -> dict:
    """Health check."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/.well-known/glama.json")
async def glama_manifest() -> dict:
    """Glama auto-crawl manifest. Glama probes this path during MCP server discovery."""
    return {
        "$schema": "https://glama.ai/mcp/schemas/server.json",
        "name": "agent-tools",
        "description": (
            "9 agent-native utility tools — DNS, WHOIS, email validation, "
            "IP geolocation, URL health, HTTP headers analysis, QR codes, "
            "text extraction, and tech stack detection. With x402 micropayments."
        ),
        "homepage": "https://tools.beethoven2024.com",
        "repository": "https://github.com/WingedGuardian/agent-tools",
        "license": "MIT",
        "language": "python",
        "categories": ["utility", "networking", "web", "security"],
        "tags": ["x402", "micropayments", "agent-native", "USDC", "Base"],
        "remote": {
            "url": "https://tools.beethoven2024.com/mcp",
            "transport": "streamable-http",
        },
    }


@app.get("/.well-known/mcp/server-card.json")
async def mcp_server_card() -> dict:
    """Static MCP server metadata — used by Smithery and other registries for discovery."""
    return {
        "schema_version": "2025-03-26",
        "name": "agent-tools",
        "title": "Agent Tools",
        "description": (
            "Agent-native utility API bundle — 9 tools for DNS, WHOIS, email validation, "
            "IP geolocation, URL health, HTTP headers analysis, QR codes, text extraction, "
            "and tech stack detection. x402 micropayments + streamable-http MCP transport."
        ),
        "version": "0.1.0",
        "endpoint": "https://tools.beethoven2024.com/mcp",
        "transport": "streamable-http",
        "auth": {
            "type": "x402",
            "network": "base",
            "facilitator": "https://facilitator.xpay.sh",
            "description": (
                "Per-call USDC micropayments via x402 protocol on Base mainnet. "
                "MCP tools/call requires payment; initialize, tools/list, and ping pass through free. "
                "REST /v1/* routes also require payment."
            ),
        },
        "tools": [
            "qr_generate", "dns_health", "email_validate", "ip_lookup",
            "url_health", "whois_lookup", "headers_analyze", "extract_text",
            "tech_detect",
        ],
        "homepage": "https://github.com/WingedGuardian/agent-tools",
        "license": "MIT",
        "keywords": [
            "x402", "micropayments", "USDC", "Base", "MCP", "Model Context Protocol",
            "DNS", "WHOIS", "email validation", "IP geolocation", "URL health",
            "HTTP headers", "QR code", "text extraction", "tech detection",
            "agent-native", "agentic",
        ],
    }


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
            {
                "path": "/v1/extract/text",
                "method": "GET",
                "description": "Extract clean text from webpage — strips HTML, nav, ads",
                "price": "$0.005",
            },
            {
                "path": "/v1/tech/detect",
                "method": "GET",
                "description": "Detect website technology stack — CMS, framework, CDN, analytics",
                "price": "$0.005",
            },
        ],
        "payment": {
            "x402": "USDC on Base (EIP-3009)",
            "api_key": "X-API-Key header",
        },
        "mcp": "/mcp",
        "docs": "/docs",
    }
