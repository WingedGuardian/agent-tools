"""x402 payment configuration.

Configures the x402 middleware for USDC micropayments on Base.
Uses xpay's facilitator (https://facilitator.xpay.sh) for mainnet,
x402.org for testnet. No blockchain code needed on our side.

Facilitator URL is selected automatically based on AGENT_TOOLS_TESTNET:
- testnet=true  → https://x402.org/facilitator (Base Sepolia only)
- testnet=false → https://facilitator.xpay.sh (Base mainnet, zero fees)
"""

from __future__ import annotations

import os

from x402 import x402ResourceServer
from x402.http import (
    FacilitatorConfig,
    HTTPFacilitatorClient,
    PaymentOption,
    RouteConfig,
)
from x402.http.middleware.fastapi import PaywallConfig

# Base mainnet chain ID (EIP-155)
BASE_NETWORK = "eip155:8453"

# Default to testnet (Base Sepolia) unless AGENT_TOOLS_MAINNET=true
BASE_TESTNET_NETWORK = "eip155:84532"


def get_pay_to() -> str:
    """Get the wallet address to receive payments."""
    addr = os.environ.get("AGENT_TOOLS_PAY_TO", "")
    if not addr:
        raise ValueError(
            "AGENT_TOOLS_PAY_TO environment variable must be set to your "
            "EVM wallet address (e.g. 0x...) to receive x402 payments."
        )
    return addr


def is_testnet() -> bool:
    """Check if running in testnet mode."""
    return os.environ.get("AGENT_TOOLS_TESTNET", "true").lower() in ("true", "1", "yes")


def get_network() -> str:
    """Get the target network."""
    return BASE_TESTNET_NETWORK if is_testnet() else BASE_NETWORK


def make_payment_option(price: str) -> PaymentOption:
    """Create a payment option for a given USD price string (e.g. '$0.01')."""
    return PaymentOption(
        scheme="exact",
        price=price,
        network=get_network(),
        pay_to=get_pay_to(),
    )


def build_route_configs() -> dict[str, RouteConfig]:
    """Build x402 route configurations for all paid endpoints."""
    return {
        "GET /v1/qr/generate/image": RouteConfig(
            accepts=make_payment_option("$0.001"),
            description="Generate QR code image",
        ),
        "POST /v1/qr/generate": RouteConfig(
            accepts=make_payment_option("$0.001"),
            description="Generate QR code metadata",
        ),
        "GET /v1/dns/health": RouteConfig(
            accepts=make_payment_option("$0.003"),
            description="DNS health check",
        ),
        "GET /v1/email/validate": RouteConfig(
            accepts=make_payment_option("$0.005"),
            description="Email validation",
        ),
        "GET /v1/ip/lookup": RouteConfig(
            accepts=make_payment_option("$0.005"),
            description="IP geolocation and reputation",
        ),
        "GET /v1/url/health": RouteConfig(
            accepts=make_payment_option("$0.003"),
            description="URL health check",
        ),
        "GET /v1/whois/lookup": RouteConfig(
            accepts=make_payment_option("$0.005"),
            description="WHOIS domain lookup",
        ),
        "GET /v1/headers/analyze": RouteConfig(
            accepts=make_payment_option("$0.003"),
            description="HTTP headers security analysis",
        ),
        "GET /v1/extract/text": RouteConfig(
            accepts=make_payment_option("$0.005"),
            description="Text extraction from URL",
        ),
        "GET /v1/tech/detect": RouteConfig(
            accepts=make_payment_option("$0.005"),
            description="Technology stack detection",
        ),
    }


def create_x402_middleware_args() -> dict | None:
    """Create x402 middleware arguments, or None if not configured.

    Returns None if AGENT_TOOLS_PAY_TO is not set, allowing the service
    to run without payments during development.
    """
    pay_to = os.environ.get("AGENT_TOOLS_PAY_TO", "")
    if not pay_to:
        return None

    # Select facilitator based on network. xpay supports mainnet with zero fees
    # and no auth; x402.org is testnet-only.
    facilitator_url = (
        "https://x402.org/facilitator"
        if is_testnet()
        else "https://facilitator.xpay.sh"
    )
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url))
    server = x402ResourceServer(facilitator)

    # Register the EVM "exact" payment scheme for the target network
    from x402.mechanisms.evm.exact import ExactEvmServerScheme

    network = get_network()
    server.register(network, ExactEvmServerScheme())

    return {
        "routes": build_route_configs(),
        "server": server,
        "paywall_config": PaywallConfig(
            app_name="Agent Tools",
            testnet=is_testnet(),
        ),
    }
