"""SSRF protection helpers.

Validates URLs and hostnames before making outbound HTTP/TCP connections.
Blocks requests targeting private networks, loopback, cloud metadata
(169.254.169.254, fd00:ec2::254), and other internal infrastructure.

Known limitation: DNS resolve → validate → connect has a small TOCTOU window
because httpx re-resolves on connect. A sophisticated attacker with TTL=0 DNS
control could flip a public IP to private in that gap. This covers the vast
majority of SSRF attacks. Full IP-pinning transport is deferred.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException


def _is_unsafe_ip(ip_str: str) -> bool:
    """Return True if the IP is in any blocked range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → reject

    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local      # includes 169.254.x.x (cloud metadata IMDS)
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def validate_url_safe(url: str) -> str:
    """Validate a user-supplied URL for SSRF safety.

    Resolves the hostname and checks all returned IPs against the blocklist.
    Raises HTTPException(400) if any resolved IP targets internal infrastructure.

    Returns the normalized URL (with https:// prepended if missing).
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: no hostname")

    # If the hostname is already a raw IP, check it directly without DNS lookup
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        addr = None  # Not a raw IP — it's a hostname; proceed to DNS resolution

    if addr is not None:
        if _is_unsafe_ip(str(addr)):
            raise HTTPException(
                status_code=400,
                detail=f"URL targets internal or reserved address ({hostname})",
            )
        return url

    # Resolve hostname → all IPs (IPv4 + IPv6), blocking call via thread pool
    try:
        infos: list = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except socket.gaierror as e:
        raise HTTPException(status_code=400, detail=f"DNS resolution failed: {e}")

    if not infos:
        raise HTTPException(status_code=400, detail="DNS resolution returned no addresses")

    for (_family, _type, _proto, _canonname, sockaddr) in infos:
        ip = sockaddr[0]
        if _is_unsafe_ip(ip):
            raise HTTPException(
                status_code=400,
                detail=f"URL targets internal or reserved address (resolved to {ip})",
            )

    return url


async def validate_smtp_target_safe(mx_host: str) -> None:
    """Validate an MX hostname before opening an SMTP connection.

    Raises HTTPException(400) if the MX hostname resolves to a private/internal IP.
    Prevents SSRF via the email validation SMTP probe.
    """
    try:
        infos: list = await asyncio.to_thread(
            socket.getaddrinfo,
            mx_host,
            25,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except socket.gaierror as e:
        raise HTTPException(
            status_code=400,
            detail=f"SMTP target DNS resolution failed: {e}",
        )

    for (_family, _type, _proto, _canonname, sockaddr) in infos:
        ip = sockaddr[0]
        if _is_unsafe_ip(ip):
            raise HTTPException(
                status_code=400,
                detail=f"SMTP target resolves to internal address ({ip})",
            )
