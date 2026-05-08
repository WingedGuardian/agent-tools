"""Agent Tools — main FastAPI application."""

from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .endpoints import dns, qr
from .mcp_server import mcp


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

# Mount endpoint routers
app.include_router(qr.router)
app.include_router(dns.router)

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
        ],
        "payment": {
            "x402": "USDC on Base (EIP-3009)",
            "api_key": "X-API-Key header",
        },
        "mcp": "/mcp",
        "docs": "/docs",
    }
