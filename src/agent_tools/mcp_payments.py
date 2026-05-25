"""x402 payment middleware for MCP tool calls.

Intercepts POST /mcp requests at the ASGI level. Methods other than
tools/call (initialize, tools/list, ping, etc.) pass through free.
For tools/call:
  - No X-PAYMENT header → 402 with X-PAYMENT-REQUIRED header + body
  - Valid X-PAYMENT header → verify → forward → settle → X-PAYMENT-RESPONSE

Settlement happens after the downstream response is confirmed non-error
(status < 400). A failed settlement logs but does not break the response.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid body-consume
issues — we buffer the receive stream ourselves and replay it downstream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from x402.http.utils import (
    decode_payment_signature_header,
    encode_payment_required_header,
    encode_payment_response_header,
)
from x402.schemas.config import ResourceConfig

logger = logging.getLogger(__name__)

# Per-tool prices — must match build_route_configs() in payments.py
_TOOL_PRICES: dict[str, str] = {
    "qr_generate": "$0.001",
    "dns_health": "$0.003",
    "email_validate": "$0.005",
    "ip_lookup": "$0.005",
    "url_health": "$0.003",
    "whois_lookup": "$0.005",
    "headers_analyze": "$0.003",
    "extract_text": "$0.005",
    "tech_detect": "$0.005",
}

# MCP methods that don't require payment
_FREE_METHODS = frozenset({
    "initialize",
    "tools/list",
    "ping",
    "notifications/initialized",
    "notifications/cancelled",
    "$/cancelRequest",
    "resources/list",
    "resources/read",
    "prompts/list",
    "prompts/get",
    "completion/complete",
})


class MCPPaymentMiddleware:
    """x402 payment gate for MCP tools/call requests.

    Mounts on the FastAPI app before FastMCP's /mcp mount. Only POST requests
    to /mcp or /mcp/ are inspected; all other paths pass through immediately.
    """

    def __init__(self, app: ASGIApp, *, server, testnet: bool = False) -> None:
        self.app = app
        self._server = server
        self._testnet = testnet
        self._init_done = False
        self._init_lock = asyncio.Lock()

    async def _ensure_initialized(self) -> None:
        """Lazy-initialize the x402 server (fetches /supported from facilitator)."""
        if not self._init_done:
            async with self._init_lock:
                if not self._init_done:
                    await asyncio.to_thread(self._server.initialize)
                    self._init_done = True

    def _build_requirements(self, price: str) -> list:
        pay_to = os.environ.get("AGENT_TOOLS_PAY_TO", "")
        network = "eip155:84532" if self._testnet else "eip155:8453"
        config = ResourceConfig(
            scheme="exact",
            pay_to=pay_to,
            price=price,
            network=network,
            max_timeout_seconds=300,
        )
        return self._server.build_payment_requirements(config)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "")

        if method != "POST" or path not in ("/mcp", "/mcp/"):
            await self.app(scope, receive, send)
            return

        # Buffer the full body (may arrive in chunks)
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        # Replay callable for downstream
        async def replay() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        # Parse MCP method
        try:
            data: dict = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            await self.app(scope, replay, send)
            return

        mcp_method: str = data.get("method", "")

        if mcp_method in _FREE_METHODS or mcp_method != "tools/call":
            await self.app(scope, replay, send)
            return

        # tools/call — payment required
        tool_name: str = (data.get("params") or {}).get("name", "unknown")
        price: str = _TOOL_PRICES.get(tool_name, "$0.005")

        # Extract X-PAYMENT header from ASGI scope headers (bytes)
        headers_map = {k.lower(): v for k, v in scope.get("headers", [])}
        payment_header = headers_map.get(b"x-payment", b"").decode("utf-8", errors="replace")

        await self._ensure_initialized()
        requirements = self._build_requirements(price)

        if not payment_header:
            # Return 402 Payment Required
            payment_required = self._server.create_payment_required_response(requirements)
            pr_json = json.loads(
                payment_required.model_dump_json(by_alias=True, exclude_none=True)
            )
            response = JSONResponse(
                content=pr_json,
                status_code=402,
                headers={
                    "X-PAYMENT-REQUIRED": encode_payment_required_header(payment_required),
                    "Access-Control-Expose-Headers": "X-PAYMENT-REQUIRED",
                },
            )
            await response(scope, replay, send)
            return

        # Decode and verify the payment
        try:
            payload = decode_payment_signature_header(payment_header)
        except Exception as exc:
            response = JSONResponse(
                content={"error": f"Invalid X-PAYMENT header: {exc}"},
                status_code=402,
            )
            await response(scope, replay, send)
            return

        verify_response = await self._server.verify_payment(payload, requirements)
        if not verify_response.is_valid:
            response = JSONResponse(
                content={"error": f"Payment invalid: {verify_response.invalid_reason}"},
                status_code=402,
            )
            await response(scope, replay, send)
            return

        # Payment verified — forward request, settle after non-error response
        async def send_with_settlement(message: dict) -> None:
            if message["type"] == "http.response.start" and message.get("status", 500) < 400:
                try:
                    settle = await self._server.settle_payment(payload, requirements)
                    if settle.success:
                        hdrs = list(message.get("headers", []))
                        hdrs.append((
                            b"x-payment-response",
                            encode_payment_response_header(settle).encode("utf-8"),
                        ))
                        message = {**message, "headers": hdrs}
                    else:
                        logger.warning(
                            "MCP payment settlement failed for %s: %s",
                            tool_name, settle.error_reason,
                        )
                except Exception:
                    logger.exception("MCP payment settlement error for tool %s", tool_name)
            await send(message)

        await self.app(scope, replay, send_with_settlement)
