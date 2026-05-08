"""DNS and domain health check endpoint."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/dns", tags=["dns"])


class DNSRecord(BaseModel):
    type: str
    value: str
    ttl: int | None = None


class MailSecurity(BaseModel):
    has_spf: bool
    has_dkim: bool | None = None  # requires selector, so optional
    has_dmarc: bool
    spf_record: str | None = None
    dmarc_record: str | None = None


class DNSHealthResult(BaseModel):
    domain: str
    resolves: bool
    a_records: list[str] = []
    aaaa_records: list[str] = []
    mx_records: list[DNSRecord] = []
    ns_records: list[str] = []
    mail_security: MailSecurity | None = None
    txt_records: list[str] = []
    error: str | None = None


@router.get("/health", response_model=DNSHealthResult)
async def dns_health(
    domain: str = Query(..., description="Domain to check"),
    include_txt: bool = Query(False, description="Include all TXT records"),
) -> DNSHealthResult:
    """Check DNS health for a domain — records, mail security, resolution."""
    import dns.asyncresolver
    import dns.resolver

    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 5.0

    result: dict[str, Any] = {"domain": domain, "resolves": False}

    try:
        # A records
        try:
            answers = await resolver.resolve(domain, "A")
            result["a_records"] = [r.to_text() for r in answers]
            result["resolves"] = True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass

        # AAAA records
        try:
            answers = await resolver.resolve(domain, "AAAA")
            result["aaaa_records"] = [r.to_text() for r in answers]
            result["resolves"] = True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass

        # MX records
        try:
            answers = await resolver.resolve(domain, "MX")
            result["mx_records"] = [
                DNSRecord(
                    type="MX",
                    value=f"{r.preference} {r.exchange.to_text()}",
                    ttl=answers.rrset.ttl if answers.rrset else None,
                )
                for r in answers
            ]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass

        # NS records
        try:
            answers = await resolver.resolve(domain, "NS")
            result["ns_records"] = [r.to_text() for r in answers]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass

        # Mail security (SPF + DMARC)
        mail_sec: dict[str, Any] = {"has_spf": False, "has_dkim": None, "has_dmarc": False}
        try:
            answers = await resolver.resolve(domain, "TXT")
            txt_values = [r.to_text().strip('"') for r in answers]
            for txt in txt_values:
                if txt.startswith("v=spf1"):
                    mail_sec["has_spf"] = True
                    mail_sec["spf_record"] = txt
            if include_txt:
                result["txt_records"] = txt_values
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass

        try:
            answers = await resolver.resolve(f"_dmarc.{domain}", "TXT")
            for r in answers:
                txt = r.to_text().strip('"')
                if txt.startswith("v=DMARC1"):
                    mail_sec["has_dmarc"] = True
                    mail_sec["dmarc_record"] = txt
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass

        result["mail_security"] = MailSecurity(**mail_sec)

    except asyncio.TimeoutError:
        result["error"] = "DNS resolution timed out"
    except Exception as e:
        result["error"] = str(e)

    return DNSHealthResult(**result)
