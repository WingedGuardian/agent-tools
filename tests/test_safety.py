"""Tests for SSRF protection helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from agent_tools.safety import validate_smtp_target_safe, validate_url_safe


@pytest.mark.asyncio
async def test_blocks_loopback_hostname():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://localhost/test")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_blocks_private_class_c():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://192.168.1.1/admin")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_blocks_private_class_a():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://10.0.0.1/")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_blocks_link_local_metadata():
    # AWS IMDS / cloud metadata endpoint
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://169.254.169.254/latest/meta-data")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_blocks_loopback_ipv4():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://127.0.0.1/")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_blocks_loopback_ipv6():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://[::1]/")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_blocks_private_172_range():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http://172.16.0.1/")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_no_hostname_rejected():
    with pytest.raises(HTTPException) as exc:
        await validate_url_safe("http:///path")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_allows_public_url():
    result = await validate_url_safe("https://example.com")
    assert result == "https://example.com"


@pytest.mark.asyncio
async def test_prepends_https_for_bare_host():
    result = await validate_url_safe("example.com")
    assert result == "https://example.com"


@pytest.mark.asyncio
async def test_smtp_blocks_private_ip(monkeypatch):
    import socket

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.1", 25))]

    monkeypatch.setattr("agent_tools.safety.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HTTPException) as exc:
        await validate_smtp_target_safe("mx.evil.internal")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_smtp_allows_public_mx(monkeypatch):
    import socket

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 25))]

    monkeypatch.setattr("agent_tools.safety.socket.getaddrinfo", fake_getaddrinfo)
    await validate_smtp_target_safe("mail.example.com")  # should not raise
