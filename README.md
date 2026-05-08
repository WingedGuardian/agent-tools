# Agent Tools

Agent-native utility API bundle — 9 endpoints exposed as both REST API and MCP tools, with x402 micropayments.

## Tools

| Tool | Endpoint | What it does | Price |
|------|----------|-------------|-------|
| `qr_generate` | `/v1/qr/generate` | QR code generation (PNG/SVG) | $0.001 |
| `dns_health` | `/v1/dns/health` | DNS records + SPF/DMARC mail security | $0.003 |
| `email_validate` | `/v1/email/validate` | Format, MX, disposable, SMTP probe | $0.005 |
| `ip_lookup` | `/v1/ip/lookup` | Geolocation, ISP, proxy/hosting detection | $0.005 |
| `url_health` | `/v1/url/health` | Status, redirects, SSL cert, response time | $0.003 |
| `whois_lookup` | `/v1/whois/lookup` | Registrar, dates, nameservers | $0.005 |
| `headers_analyze` | `/v1/headers/analyze` | Security headers audit with 0-100 score | $0.003 |
| `extract_text` | `/v1/extract/text` | Clean text extraction from webpages | $0.005 |
| `tech_detect` | `/v1/tech/detect` | Website technology stack detection | $0.005 |

## Access

### REST API
```bash
curl https://your-domain/v1/dns/health?domain=example.com
```

### MCP Server
Connect via streamable-http transport:
```json
{
  "mcpServers": {
    "agent-tools": {
      "url": "https://your-domain/mcp"
    }
  }
}
```

### Payment
- **x402**: USDC on Base — automatic for x402-capable agents
- **Free mode**: runs without payments when `AGENT_TOOLS_PAY_TO` is not set

## Deploy

### Fly.io (recommended)
```bash
fly launch --copy-config
fly secrets set AGENT_TOOLS_PAY_TO=0xYourAddress AGENT_TOOLS_TESTNET=false
fly deploy
```

### Docker
```bash
cp .env.example .env
# Edit .env with your wallet address
docker compose up -d
```

### Manual
```bash
pip install ".[all]"
uvicorn agent_tools.app:app --host 0.0.0.0 --port 8000
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_TOOLS_PAY_TO` | No | EVM wallet address for receiving USDC payments. Leave empty for free mode. |
| `AGENT_TOOLS_TESTNET` | No | `true` (default) for Base Sepolia testnet, `false` for Base mainnet. |

## Tech Stack

- Python 3.12 + FastAPI
- MCP SDK (`mcp` v1.27) — streamable-http transport
- x402 SDK (`x402` v2.9) — USDC micropayments on Base
- Zero upstream API costs (8 of 9 endpoints are fully self-hosted)

## License

MIT
