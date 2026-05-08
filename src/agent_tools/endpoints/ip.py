"""IP geolocation and reputation endpoint.

Uses ip-api.com free tier (45 RPM, non-commercial) for geolocation
and self-hosted checks for basic reputation signals.
"""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/ip", tags=["ip"])


class IPInfo(BaseModel):
    ip: str
    valid: bool
    version: int | None = None
    is_private: bool = False
    is_loopback: bool = False
    is_reserved: bool = False
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    lat: float | None = None
    lon: float | None = None
    timezone: str | None = None
    isp: str | None = None
    org: str | None = None
    as_number: str | None = None
    is_proxy: bool | None = None
    is_hosting: bool | None = None
    reverse_dns: str | None = None
    error: str | None = None


@router.get("/lookup", response_model=IPInfo)
async def ip_lookup(
    ip: str = Query(..., description="IPv4 or IPv6 address to look up"),
    geo: bool = Query(True, description="Include geolocation data"),
) -> IPInfo:
    """Look up IP address — geolocation, ISP, proxy/hosting detection, reverse DNS."""
    ip = ip.strip()
    result: dict = {"ip": ip, "valid": False}

    # Validate IP
    try:
        addr = ipaddress.ip_address(ip)
        result["valid"] = True
        result["version"] = addr.version
        result["is_private"] = addr.is_private
        result["is_loopback"] = addr.is_loopback
        result["is_reserved"] = addr.is_reserved
    except ValueError:
        result["error"] = "Invalid IP address format"
        return IPInfo(**result)

    # Skip external lookups for private/reserved IPs
    if addr.is_private or addr.is_loopback or addr.is_reserved:
        return IPInfo(**result)

    # Reverse DNS
    import dns.asyncresolver
    import dns.resolver

    try:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = 3.0
        rev_name = dns.reversename.from_address(ip)
        answers = await resolver.resolve(rev_name, "PTR")
        result["reverse_dns"] = answers[0].to_text().rstrip(".")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        pass
    except TimeoutError:
        pass

    # Geolocation via ip-api.com (free tier: 45 RPM, fields param for efficiency)
    if geo:
        import httpx

        fields = (
            "status,country,countryCode,regionName,city,"
            "lat,lon,timezone,isp,org,as,proxy,hosting"
        )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip}?fields={fields}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        result["country"] = data.get("country")
                        result["country_code"] = data.get("countryCode")
                        result["region"] = data.get("regionName")
                        result["city"] = data.get("city")
                        result["lat"] = data.get("lat")
                        result["lon"] = data.get("lon")
                        result["timezone"] = data.get("timezone")
                        result["isp"] = data.get("isp")
                        result["org"] = data.get("org")
                        result["as_number"] = data.get("as")
                        result["is_proxy"] = data.get("proxy")
                        result["is_hosting"] = data.get("hosting")
                elif resp.status_code == 429:
                    result["error"] = "Rate limited — try again in a moment"
        except (httpx.TimeoutException, httpx.ConnectError):
            result["error"] = "Geolocation service unavailable"

    return IPInfo(**result)
