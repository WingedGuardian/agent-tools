"""Text extraction from URL endpoint.

Fetches a webpage and extracts clean readable text, stripping
navigation, ads, footers, and HTML boilerplate. Self-hosted.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/extract", tags=["extract"])


class ExtractResult(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    text: str = ""
    word_count: int = 0
    language: str | None = None
    error: str | None = None


@router.get("/text", response_model=ExtractResult)
async def extract_text(
    url: str = Query(..., max_length=2048, description="URL to extract text from"),
    max_length: int = Query(5000, ge=100, le=50000, description="Max characters to return"),
) -> ExtractResult:
    """Extract clean readable text from a webpage — strips HTML, nav, ads, scripts."""
    import httpx

    result: dict = {"url": url}

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
        result["url"] = url

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "AgentTools/0.1 (text extraction)"},
        ) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return ExtractResult(**result)

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            result["error"] = f"Not HTML: {content_type}"
            return ExtractResult(**result)

        html = resp.text
        result["title"] = _extract_meta(html, "title")
        result["description"] = _extract_meta(html, "description")
        result["language"] = _extract_lang(html)

        text = _html_to_text(html)
        if len(text) > max_length:
            text = text[:max_length] + "..."
        result["text"] = text
        result["word_count"] = len(text.split())

    except httpx.ConnectError as e:
        result["error"] = f"Connection failed: {e}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out (15s)"
    except Exception as e:
        result["error"] = str(e)

    return ExtractResult(**result)


def _extract_meta(html: str, name: str) -> str | None:
    """Extract a meta tag value or title from HTML."""
    if name == "title":
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else None

    # <meta name="description" content="...">
    m = re.search(
        rf'<meta\s+(?:name|property)=["\'](?:og:)?{name}["\']\s+content=["\']([^"\']*)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Reversed attribute order
    m = re.search(
        rf'<meta\s+content=["\']([^"\']*)["\'].*?(?:name|property)=["\'](?:og:)?{name}["\']',
        html,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extract_lang(html: str) -> str | None:
    """Extract language from html tag."""
    m = re.search(r'<html[^>]*\slang=["\']([^"\']+)["\']', html, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _html_to_text(html: str) -> str:
    """Convert HTML to clean readable text."""
    # Remove elements that aren't content
    for tag in ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]:
        html = re.sub(rf"<{tag}[\s>].*?</{tag}>", " ", html, flags=re.IGNORECASE | re.DOTALL)

    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)

    # Replace block elements with newlines
    html = re.sub(r"<(?:br|p|div|h[1-6]|li|tr|blockquote)[^>]*>", "\n", html, flags=re.IGNORECASE)

    # Remove all remaining tags
    html = re.sub(r"<[^>]+>", " ", html)

    # Decode common HTML entities
    html = (
        html.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
        .replace("&#x27;", "'")
        .replace("&#x2F;", "/")
    )

    # Decode numeric entities
    html = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), html)
    html = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), html)

    # Collapse whitespace
    lines = []
    for line in html.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line and len(line) > 2:
            lines.append(line)

    return "\n".join(lines)
