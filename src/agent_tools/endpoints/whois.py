"""WHOIS domain lookup endpoint.

Self-hosted via asyncwhois library. Returns registrar, creation/expiry
dates, nameservers, and registrant info when available.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/whois", tags=["whois"])


class WhoisResult(BaseModel):
    domain: str
    registered: bool = False
    registrar: str | None = None
    creation_date: str | None = None
    expiration_date: str | None = None
    updated_date: str | None = None
    nameservers: list[str] = []
    status: list[str] = []
    registrant_org: str | None = None
    registrant_country: str | None = None
    dnssec: str | None = None
    error: str | None = None


@router.get("/lookup", response_model=WhoisResult)
async def whois_lookup(
    domain: str = Query(..., max_length=253, description="Domain to look up"),
) -> WhoisResult:
    """WHOIS lookup — registrar, dates, nameservers, registrant info."""
    import asyncio

    result: dict = {"domain": domain, "registered": False}

    try:
        raw = await asyncio.wait_for(
            _async_whois(domain),
            timeout=10.0,
        )
        if not raw:
            result["error"] = "No WHOIS data returned"
            return WhoisResult(**result)

        result["registered"] = True
        result["registrar"] = _extract(raw, "Registrar:")
        result["creation_date"] = _extract(raw, "Creation Date:")
        result["expiration_date"] = _extract(raw, "Registry Expiry Date:")
        result["updated_date"] = _extract(raw, "Updated Date:")
        result["dnssec"] = _extract(raw, "DNSSEC:")
        result["registrant_org"] = _extract(raw, "Registrant Organization:")
        result["registrant_country"] = _extract(raw, "Registrant Country:")

        # Nameservers (may appear multiple times)
        result["nameservers"] = _extract_all(raw, "Name Server:")

        # Status codes
        result["status"] = _extract_all(raw, "Domain Status:")

    except TimeoutError:
        result["error"] = "WHOIS lookup timed out"
    except OSError as e:
        result["error"] = f"WHOIS connection failed: {e}"

    return WhoisResult(**result)


async def _async_whois(domain: str) -> str:
    """Perform async WHOIS query via TCP socket."""
    import asyncio

    # Determine WHOIS server
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    whois_server = f"{tld}.whois-servers.net" if tld else "whois.iana.org"

    reader, writer = await asyncio.open_connection(whois_server, 43)
    try:
        writer.write(f"{domain}\r\n".encode())
        await writer.drain()
        data = await reader.read(65536)
        return data.decode(errors="replace")
    finally:
        writer.close()
        await writer.wait_closed()


def _extract(text: str, label: str) -> str | None:
    """Extract the first value for a WHOIS label."""
    for line in text.splitlines():
        if line.strip().lower().startswith(label.lower()):
            _, _, value = line.partition(":")
            value = value.strip()
            if value:
                return value
    return None


def _extract_all(text: str, label: str) -> list[str]:
    """Extract all values for a WHOIS label."""
    values = []
    for line in text.splitlines():
        if line.strip().lower().startswith(label.lower()):
            _, _, value = line.partition(":")
            value = value.strip()
            if value:
                # Strip URL suffixes from status codes
                if " " in value:
                    value = value.split()[0]
                values.append(value.lower())
    return list(dict.fromkeys(values))  # dedup preserving order
