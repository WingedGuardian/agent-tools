"""Email validation endpoint.

Validates email addresses via format check, MX record lookup, and
optionally SMTP mailbox probe. No upstream API required — all checks
are self-hosted using DNS and direct SMTP connection.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/email", tags=["email"])

# RFC 5322 simplified — catches most invalid formats
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

# Known disposable email domains (top providers)
_DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
    "dispostable.com", "trashmail.com", "10minutemail.com", "temp-mail.org",
    "fakeinbox.com", "mailnesia.com", "maildrop.cc", "discard.email",
    "tmpmail.net", "tmpmail.org", "getnada.com", "emailondeck.com",
})


class EmailValidationResult(BaseModel):
    email: str
    valid_format: bool
    domain: str | None = None
    has_mx: bool = False
    mx_records: list[str] = []
    is_disposable: bool = False
    is_role_account: bool = False
    smtp_reachable: bool | None = None
    error: str | None = None


@router.get("/validate", response_model=EmailValidationResult)
async def validate_email(
    email: str = Query(..., max_length=254, description="Email address to validate"),
    check_smtp: bool = Query(False, description="Probe SMTP server (slower, ~2-5s)"),
) -> EmailValidationResult:
    """Validate an email address — format, MX records, disposable check, optional SMTP probe."""
    email = email.strip().lower()
    result: dict = {"email": email, "valid_format": False}

    # Format check
    if not _EMAIL_RE.match(email) or len(email) > 254:
        result["error"] = "Invalid email format"
        return EmailValidationResult(**result)

    result["valid_format"] = True
    local, domain = email.rsplit("@", 1)
    result["domain"] = domain

    # Role account check
    role_prefixes = {
        "admin", "info", "support", "sales", "contact", "help", "abuse",
        "postmaster", "webmaster", "noreply", "no-reply", "mailer-daemon",
    }
    result["is_role_account"] = local in role_prefixes

    # Disposable domain check
    result["is_disposable"] = domain in _DISPOSABLE_DOMAINS

    # MX record lookup
    import dns.asyncresolver
    import dns.resolver

    try:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = 5.0
        answers = await resolver.resolve(domain, "MX")
        mx_list = sorted(
            [(r.preference, r.exchange.to_text().rstrip(".")) for r in answers],
            key=lambda x: x[0],
        )
        result["has_mx"] = True
        result["mx_records"] = [mx for _, mx in mx_list]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        result["has_mx"] = False
        result["error"] = f"No MX records for {domain}"
        return EmailValidationResult(**result)
    except TimeoutError:
        result["error"] = "DNS lookup timed out"
        return EmailValidationResult(**result)

    # Optional SMTP probe
    if check_smtp and result["mx_records"]:
        result["smtp_reachable"] = await _probe_smtp(result["mx_records"][0], email)

    return EmailValidationResult(**result)


async def _probe_smtp(mx_host: str, email: str) -> bool:
    """Probe SMTP server to check if mailbox exists.

    Connects to the MX server and issues MAIL FROM / RCPT TO.
    Returns True if the server accepts the recipient.
    """
    import asyncio

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, 25),
            timeout=5.0,
        )
        try:
            # Read greeting
            greeting = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not greeting.startswith(b"220"):
                return False

            # EHLO
            writer.write(b"EHLO agent-tools.local\r\n")
            await writer.drain()
            # Read EHLO response (may be multi-line)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if line[3:4] == b" ":
                    break

            # MAIL FROM
            writer.write(b"MAIL FROM:<check@agent-tools.local>\r\n")
            await writer.drain()
            resp = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not resp.startswith(b"250"):
                return False

            # RCPT TO — this is the actual mailbox check
            writer.write(f"RCPT TO:<{email}>\r\n".encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.readline(), timeout=5.0)

            # QUIT
            writer.write(b"QUIT\r\n")
            await writer.drain()

            # 250 = accepted, 550/551/552/553 = rejected
            return resp.startswith(b"250")
        finally:
            writer.close()
            await writer.wait_closed()
    except (TimeoutError, OSError):
        return False
