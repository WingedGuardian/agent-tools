# Agent Tools

> Agent-native utility API bundle. 9 endpoints exposed as both REST API and **MCP server** (streamable-http), with **x402 micropayments**. Live at [tools.beethoven2024.com](https://tools.beethoven2024.com).

**For AI agents (Claude, Cursor, custom):** Add this MCP server to your config and use 9 utility tools instantly.

**For developers:** Standard REST API. Use any subdomain example below as a working sample.

## Try it now

### As MCP server (Claude, Cursor, agents)

```json
{
  "mcpServers": {
    "agent-tools": {
      "url": "https://tools.beethoven2024.com/mcp"
    }
  }
}
```

### As REST API

```bash
curl https://tools.beethoven2024.com/health
# {"status":"ok","version":"0.1.0"}

curl "https://tools.beethoven2024.com/v1/dns/health?domain=example.com"
# Full DNS + mail security audit (requires x402 payment)
```

## What's in the bundle

| Tool | Endpoint | What it does | Price |
|------|----------|-------------|-------|
| `qr_generate` | `/v1/qr/generate` | QR code generation (PNG/SVG, 64–2048px) | $0.001 |
| `dns_health` | `/v1/dns/health` | DNS records + SPF/DMARC mail security audit | $0.003 |
| `email_validate` | `/v1/email/validate` | Format, MX, disposable domain, role account, SMTP probe | $0.005 |
| `ip_lookup` | `/v1/ip/lookup` | Geolocation, ISP, proxy/hosting detection, reverse DNS | $0.005 |
| `url_health` | `/v1/url/health` | Status code, redirect chain, SSL cert, response time | $0.003 |
| `whois_lookup` | `/v1/whois/lookup` | Registrar, creation/expiration dates, nameservers, status | $0.005 |
| `headers_analyze` | `/v1/headers/analyze` | HTTP security headers audit with 0–100 score (HSTS, CSP, etc.) | $0.003 |
| `extract_text` | `/v1/extract/text` | Clean text extraction from webpages (strips HTML, nav, ads) | $0.005 |
| `tech_detect` | `/v1/tech/detect` | Website technology stack — frameworks, CMS, CDN, analytics | $0.005 |

**Free:** `/health`, `/`, `/docs` (OpenAPI), and MCP protocol methods `initialize` / `tools/list` / `ping`. All 9 tools require x402 payment via both MCP (`tools/call`) and REST (`/v1/*`).

## Why these endpoints

Every endpoint solves a problem agents can't easily do locally:

- **Network infrastructure** (DNS, WHOIS, headers, URL health, IP) — needs internet probes, can't be done in-process
- **Specialized parsing** (QR, email validation with SMTP, tech detection) — domain-specific logic agents shouldn't reimplement
- **Web extraction** (text extraction) — clean text from messy HTML is hard

8 of 9 endpoints are fully self-hosted (zero upstream API cost). Only IP geolocation uses an external free-tier API.

## Payment

### x402 (machine-to-machine micropayments)

Every paid endpoint returns **HTTP 402 Payment Required** with the price spec when no payment is included. x402-capable agents handle this automatically:

1. Agent calls endpoint → receives 402 with payment_requirements (network, amount, recipient address)
2. Agent signs EIP-3009 `transferWithAuthorization` for USDC on Base
3. Agent retries with `X-PAYMENT` header
4. Service verifies payment via facilitator, executes, returns result

Settlement happens on-chain on Base. Sub-2-second confirmation.

Runs on Base mainnet by default. Set `AGENT_TOOLS_TESTNET=true` to use Base Sepolia with the public testnet facilitator.

### Traditional billing

Coming soon: API key + Stripe usage billing for human developers and businesses.

## Tech stack

- Python 3.12 + FastAPI
- MCP SDK (`mcp` v1.27) — streamable-http transport
- x402 SDK (`x402[fastapi,evm]` >=v2.11) — USDC micropayments on Base
- 8/9 endpoints self-hosted (no upstream API cost)
- Single-process deploy, ~62MB memory footprint

## Self-host

### Fly.io

```bash
git clone https://github.com/WingedGuardian/agent-tools.git
cd agent-tools
fly launch --copy-config
fly secrets set AGENT_TOOLS_PAY_TO=0xYourAddress AGENT_TOOLS_TESTNET=false
fly deploy
```

### Docker

```bash
git clone https://github.com/WingedGuardian/agent-tools.git
cd agent-tools
cp .env.example .env
# Edit .env with your wallet address
docker compose up -d
```

### Manual

```bash
pip install ".[all]"
AGENT_TOOLS_PAY_TO=0xYourAddress uvicorn agent_tools.app:app --host 0.0.0.0 --port 8000
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AGENT_TOOLS_PAY_TO` | No | _(empty)_ | EVM wallet address for receiving USDC payments. Leave empty to run free/dev mode. |
| `AGENT_TOOLS_TESTNET` | No | `true` | `true` = Base Sepolia testnet (default — works with public x402.org facilitator). `false` = Base mainnet (requires mainnet-capable facilitator). |

## Discovery / registries

- GitHub: https://github.com/WingedGuardian/agent-tools
- Smithery: _(pending registration)_
- Glama: _(pending registration)_
- x402-list: _(pending registration)_
- npm: _(pending publish)_

## Keywords

x402, micropayments, USDC, Base, agent-native, MCP, Model Context Protocol, streamable-http, agentic, AI agent tools, DNS lookup API, WHOIS API, email validation API, QR code API, URL health API, web scraping API, tech detection API, security headers analyzer

## License

MIT
