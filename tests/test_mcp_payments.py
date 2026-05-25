"""Tests for MCPPaymentMiddleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_tools.mcp_payments import MCPPaymentMiddleware, _FREE_METHODS, _TOOL_PRICES


def _make_app(server=None, testnet=True):
    """Build a minimal FastAPI app wrapped by MCPPaymentMiddleware."""
    app = FastAPI()

    @app.post("/mcp")
    async def mcp_endpoint():
        return {"ok": True}

    if server is None:
        server = MagicMock()

    return MCPPaymentMiddleware(app, server=server, testnet=testnet)


def _mock_server():
    """Build a mock x402 server that accepts payment headers."""
    server = MagicMock()
    server._initialized = True  # skip init check
    server.initialize.return_value = None
    server.build_payment_requirements.return_value = [MagicMock()]
    pr = MagicMock()
    pr.model_dump_json.return_value = '{"x402Version":2,"accepts":[]}'
    server.create_payment_required_response.return_value = pr
    verify = MagicMock()
    verify.is_valid = True
    server.verify_payment = AsyncMock(return_value=verify)
    settle = MagicMock()
    settle.success = True
    server.settle_payment = AsyncMock(return_value=settle)
    return server


@pytest.mark.asyncio
async def test_non_mcp_path_passthrough():
    """GET /health and other non-/mcp paths are never inspected."""
    inner = FastAPI()

    @inner.get("/health")
    async def health():
        return {"status": "ok"}

    app = MCPPaymentMiddleware(inner, server=MagicMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_free_method_tools_list_passthrough():
    """tools/list passes through without X-PAYMENT."""
    server = _mock_server()
    app = _make_app(server=server)

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/mcp", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    server.verify_payment.assert_not_called()


@pytest.mark.asyncio
async def test_free_method_initialize_passthrough():
    """initialize passes through without X-PAYMENT."""
    server = _mock_server()
    app = _make_app(server=server)

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/mcp", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    server.verify_payment.assert_not_called()


@pytest.mark.asyncio
async def test_tools_call_without_payment_returns_402():
    """tools/call without X-PAYMENT header returns 402."""
    server = _mock_server()

    with patch("agent_tools.mcp_payments.encode_payment_required_header", return_value="encoded"):
        app = _make_app(server=server)
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "dns_health", "arguments": {"domain": "example.com"}},
        })
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/mcp", content=body, headers={"Content-Type": "application/json"}
            )

    assert resp.status_code == 402
    assert "X-Payment-Required" in resp.headers or "x-payment-required" in resp.headers
    server.verify_payment.assert_not_called()


@pytest.mark.asyncio
async def test_tools_call_invalid_payment_header_returns_402():
    """tools/call with a malformed X-PAYMENT header returns 402."""
    server = _mock_server()

    with patch(
        "agent_tools.mcp_payments.decode_payment_signature_header",
        side_effect=ValueError("bad header"),
    ):
        app = _make_app(server=server)
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "dns_health", "arguments": {}},
        })
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/mcp", content=body,
                headers={"Content-Type": "application/json", "X-PAYMENT": "garbage"},
            )

    assert resp.status_code == 402
    assert "Invalid X-PAYMENT header" in resp.text


@pytest.mark.asyncio
async def test_tools_call_valid_payment_passes_through():
    """tools/call with valid X-PAYMENT reaches the endpoint and settles."""
    server = _mock_server()

    with (
        patch("agent_tools.mcp_payments.decode_payment_signature_header", return_value=MagicMock()),
        patch("agent_tools.mcp_payments.encode_payment_required_header", return_value="enc"),
        patch("agent_tools.mcp_payments.encode_payment_response_header", return_value="settled"),
    ):
        app = _make_app(server=server)
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "dns_health", "arguments": {}},
        })
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/mcp", content=body,
                headers={"Content-Type": "application/json", "X-PAYMENT": "valid-token"},
            )

    assert resp.status_code == 200
    server.verify_payment.assert_called_once()
    server.settle_payment.assert_called_once()
    assert "x-payment-response" in resp.headers


@pytest.mark.asyncio
async def test_tool_prices_match_expected():
    """Spot-check that tool prices are correct."""
    assert _TOOL_PRICES["qr_generate"] == "$0.001"
    assert _TOOL_PRICES["dns_health"] == "$0.003"
    assert _TOOL_PRICES["email_validate"] == "$0.005"
    assert len(_TOOL_PRICES) == 9


@pytest.mark.asyncio
async def test_unknown_tool_defaults_to_highest_price():
    """Unknown tools default to $0.005 (most expensive tier)."""
    server = _mock_server()

    with patch("agent_tools.mcp_payments.encode_payment_required_header", return_value="encoded"):
        app = _make_app(server=server)
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/mcp", content=body, headers={"Content-Type": "application/json"}
            )

    assert resp.status_code == 402
    # Verify the ResourceConfig was built with the default price
    call_kwargs = server.build_payment_requirements.call_args[0][0]
    assert call_kwargs.price == "$0.005"
