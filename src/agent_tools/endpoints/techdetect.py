"""Technology detection endpoint.

Lightweight Wappalyzer-style detection: analyzes HTTP headers,
HTML meta tags, script sources, and page content to identify
the technology stack of a website. Self-hosted, no upstream cost.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..safety import validate_url_safe

router = APIRouter(prefix="/v1/tech", tags=["tech"])


class TechMatch(BaseModel):
    name: str
    category: str
    confidence: str  # "high", "medium", "low"
    evidence: str


class TechDetectResult(BaseModel):
    url: str
    technologies: list[TechMatch] = []
    summary: dict[str, list[str]] = {}  # category -> [tech names]
    error: str | None = None


# Detection signatures: (name, category, check_type, pattern, confidence)
_SIGNATURES: list[tuple[str, str, str, str, str]] = [
    # Web servers
    ("nginx", "Web Server", "header:server", r"nginx", "high"),
    ("Apache", "Web Server", "header:server", r"Apache", "high"),
    ("Cloudflare", "CDN", "header:server", r"cloudflare", "high"),
    ("LiteSpeed", "Web Server", "header:server", r"LiteSpeed", "high"),
    ("IIS", "Web Server", "header:server", r"Microsoft-IIS", "high"),
    ("Vercel", "Hosting", "header:server", r"Vercel", "high"),
    ("Netlify", "Hosting", "header:server", r"Netlify", "high"),
    ("Fly.io", "Hosting", "header:server", r"fly\.io", "high"),
    # CDN / Proxy
    ("Cloudflare", "CDN", "header:cf-ray", r".", "high"),
    ("Fastly", "CDN", "header:x-served-by", r"cache-", "high"),
    ("AWS CloudFront", "CDN", "header:x-amz-cf-id", r".", "high"),
    ("Akamai", "CDN", "header:x-akamai-transformed", r".", "high"),
    # Frameworks (headers)
    ("Express", "Framework", "header:x-powered-by", r"Express", "high"),
    ("ASP.NET", "Framework", "header:x-powered-by", r"ASP\.NET", "high"),
    ("PHP", "Language", "header:x-powered-by", r"PHP", "high"),
    ("Next.js", "Framework", "header:x-powered-by", r"Next\.js", "high"),
    # Frameworks (HTML)
    ("React", "Framework", "html", r'id="__next"|_next/static|react-root|reactroot', "medium"),
    ("Next.js", "Framework", "html", r"_next/static|__next", "medium"),
    ("Vue.js", "Framework", "html", r"__vue|v-app|nuxt|vue\.js|vue\.min\.js", "medium"),
    ("Nuxt.js", "Framework", "html", r"__nuxt|_nuxt/", "medium"),
    ("Angular", "Framework", "html", r"ng-version|ng-app|angular\.js|angular\.min\.js", "medium"),
    ("Svelte", "Framework", "html", r"svelte|__svelte", "medium"),
    ("Gatsby", "Framework", "html", r"gatsby-", "medium"),
    ("WordPress", "CMS", "html", r"wp-content|wp-includes|wordpress", "high"),
    ("Drupal", "CMS", "html", r"drupal\.js|drupal\.min\.js|Drupal\.settings", "high"),
    ("Joomla", "CMS", "html", r"/media/jui/|joomla", "medium"),
    ("Shopify", "E-commerce", "html", r"cdn\.shopify\.com|shopify\.com", "high"),
    ("Squarespace", "CMS", "html", r"squarespace\.com|sqsp", "high"),
    ("Wix", "CMS", "html", r"wix\.com|wixstatic\.com", "high"),
    ("Webflow", "CMS", "html", r"webflow\.com|wf-", "high"),
    # JavaScript libraries
    ("jQuery", "Library", "html", r"jquery[\.-]|jquery\.min\.js", "high"),
    ("Bootstrap", "CSS Framework", "html", r"bootstrap[\.-]|bootstrap\.min", "high"),
    ("Tailwind CSS", "CSS Framework", "html", r"tailwindcss|tailwind\.css", "medium"),
    # Analytics / tracking
    ("Google Analytics", "Analytics", "html", r"google-analytics\.com|gtag|ga\.js", "high"),
    ("Google Tag Manager", "Analytics", "html", r"googletagmanager\.com|gtm\.js", "high"),
    ("Meta Pixel", "Analytics", "html", r"facebook\.net/en_US/fbevents|fbq\(", "high"),
    ("Hotjar", "Analytics", "html", r"hotjar\.com|hj\(", "high"),
    ("Plausible", "Analytics", "html", r"plausible\.io", "high"),
    # Security
    ("reCAPTCHA", "Security", "html", r"recaptcha|grecaptcha", "high"),
    ("hCaptcha", "Security", "html", r"hcaptcha\.com", "high"),
    ("Cloudflare Turnstile", "Security", "html", r"turnstile|challenges\.cloudflare", "medium"),
    # Other
    ("Font Awesome", "Library", "html", r"fontawesome|font-awesome", "high"),
    ("Google Fonts", "Font Service", "html", r"fonts\.googleapis\.com", "high"),
    ("Stripe", "Payment", "html", r"js\.stripe\.com|stripe\.js", "high"),
]


@router.get("/detect", response_model=TechDetectResult)
async def detect_tech(
    url: str = Query(..., max_length=2048, description="URL to analyze"),
) -> TechDetectResult:
    """Detect technologies used by a website — frameworks, CMS, CDN, analytics, etc."""
    import httpx

    result: dict = {"url": url}

    url = await validate_url_safe(url)
    result["url"] = url

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "AgentTools/0.1 (tech detection)"},
        ) as client:
            resp = await client.get(url)

        html = resp.text if resp.status_code == 200 else ""
        headers_lower = {k.lower(): v.lower() for k, v in resp.headers.items()}

        matches: dict[str, TechMatch] = {}  # dedup by name

        for name, category, check_type, pattern, confidence in _SIGNATURES:
            if name in matches:
                continue

            matched = False
            evidence = ""

            if check_type.startswith("header:"):
                header_name = check_type.split(":", 1)[1]
                header_val = headers_lower.get(header_name, "")
                if header_val and re.search(pattern, header_val, re.IGNORECASE):
                    matched = True
                    evidence = f"{header_name}: {header_val[:80]}"
            elif check_type == "html":
                m = re.search(pattern, html, re.IGNORECASE)
                if m:
                    matched = True
                    # Extract a short snippet around the match
                    start = max(0, m.start() - 10)
                    end = min(len(html), m.end() + 10)
                    evidence = f"...{html[start:end]}..."

            if matched:
                matches[name] = TechMatch(
                    name=name,
                    category=category,
                    confidence=confidence,
                    evidence=evidence[:120],
                )

        tech_list = list(matches.values())
        result["technologies"] = tech_list

        # Build category summary
        summary: dict[str, list[str]] = {}
        for tech in tech_list:
            summary.setdefault(tech.category, []).append(tech.name)
        result["summary"] = summary

    except httpx.ConnectError as e:
        result["error"] = f"Connection failed: {e}"
    except httpx.TimeoutException:
        result["error"] = "Request timed out (15s)"
    except Exception as e:
        result["error"] = str(e)

    return TechDetectResult(**result)
