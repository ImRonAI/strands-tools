"""
x402 tool for Strands Agents — HTTP 402 internet-native payments for AI agents.

Complete integration with the x402 Python SDK (https://x402.org):
  - Client: Make paid API calls using x402HTTPClientSync + proper header encoding
  - Server: Protect your agent's endpoints and verify/settle payments
  - Discover: Find x402-enabled services via Bazaar extension
  - Facilitator: Check facilitator supported kinds

Completes the ERC-8004 payment loop:
  erc8004(action="register_agent", ...) → x402(action="pay", ...) → agent gets paid

Requires: pip install x402[httpx,evm]
"""

import json
import os
from typing import Any, Dict
from pathlib import Path

from strands import tool

# ── Lazy loading state ───────────────────────────────────────────────────────
_x402_loaded = False


def _ensure_x402():
    """Lazy-load x402 SDK."""
    global _x402_loaded
    if _x402_loaded:
        return True
    try:
        import x402 as _mod  # noqa: F841
        _x402_loaded = True
        return True
    except ImportError:
        return False


# ── Wallet helpers ───────────────────────────────────────────────────────────


def _get_wallet_data(wallet_name: str) -> dict:
    """Load wallet JSON from known directories."""
    data_dir = Path(os.environ.get("ERC8004_DATA_DIR", "/tmp/strands_erc8004"))
    wallet_dirs = [Path("./wallets"), data_dir / "wallets"]

    for wd in wallet_dirs:
        wallet_file = wd / f"{wallet_name}.json"
        if wallet_file.exists():
            with open(wallet_file) as f:
                return json.load(f)

    raise ValueError(
        f"Wallet '{wallet_name}' not found. "
        f"Create one with: blockchain(action='wallet_create', name='{wallet_name}')"
    )


def _get_private_key(wallet_name: str) -> str:
    """Get private key from wallet file or env var."""
    if wallet_name:
        wallet_data = _get_wallet_data(wallet_name)
        pk = wallet_data.get("private_key") or wallet_data.get("privateKey")
        if pk:
            return pk

    pk = os.environ.get("BLOCKCHAIN_PRIVATE_KEY")
    if pk:
        return pk

    raise ValueError(
        f"No private key found for wallet '{wallet_name}'. "
        f"Create one with: blockchain(action='wallet_create', name='{wallet_name}')"
    )


def _get_evm_signer(wallet_name: str):
    """Get an EthAccountSigner from a wallet file (proper SDK signer)."""
    from eth_account import Account
    from x402.mechanisms.evm.signers import EthAccountSigner

    pk = _get_private_key(wallet_name)
    account = Account.from_key(pk)
    return EthAccountSigner(account)


# ── Chain mapping ────────────────────────────────────────────────────────────


def _chain_to_caip2(chain: str) -> str:
    """Convert chain name to CAIP-2 network ID."""
    chain_map = {
        "ethereum": "eip155:1",
        "base": "eip155:8453",
        "polygon": "eip155:137",
        "arbitrum": "eip155:42161",
        "optimism": "eip155:10",
        "sepolia": "eip155:11155111",
        "base_sepolia": "eip155:84532",
        "amoy": "eip155:80002",
        "arbitrum_sepolia": "eip155:421614",
        "local": "eip155:31337",
    }
    if chain.startswith("eip155:") or chain.startswith("solana:"):
        return chain
    return chain_map.get(chain, f"eip155:{chain}")


def _get_facilitator_url() -> str:
    """Get the facilitator URL from env or default."""
    from x402.http.constants import DEFAULT_FACILITATOR_URL
    return os.environ.get("X402_FACILITATOR_URL", DEFAULT_FACILITATOR_URL)


# ── Tool definition ──────────────────────────────────────────────────────────


@tool
def x402(
    action: str,
    url: str = None,
    wallet_name: str = None,
    chain: str = "base",
    amount: str = None,
    pay_to: str = None,
    method: str = "GET",
    body: str = None,
    headers: str = None,
    description: str = None,
    facilitator_url: str = None,
    max_amount: int = None,
) -> Dict[str, Any]:
    """x402 internet-native payments — let your agent pay for and charge for API access.

    Actions:
      - pay: Make a paid HTTP request to an x402-protected endpoint
      - check: Check if a URL requires x402 payment (without paying)
      - discover: Search the x402 Bazaar for available paid services
      - status: Show x402 SDK status and configuration
      - create_config: Generate x402 payment config for your agent's endpoints

    Args:
        action: One of: pay, check, discover, status, create_config
        url: Target URL for pay/check actions
        wallet_name: Wallet to pay from (from ./wallets/ directory)
        chain: Chain for payments (default: base). Options: base, ethereum, polygon, arbitrum, sepolia, base_sepolia
        amount: Maximum amount willing to pay (e.g. "0.01" for $0.01 USDC)
        pay_to: Address to receive payments (for create_config)
        method: HTTP method for pay action (default: GET)
        body: Request body for POST/PUT requests (JSON string)
        headers: Additional headers as JSON string
        description: Description for create_config
        facilitator_url: Custom facilitator URL (default: https://x402.org/facilitator)
        max_amount: Max payment amount in smallest unit (e.g. 1000000 = 1 USDC)
    """

    def _ok(text: str, data: dict = None) -> Dict[str, Any]:
        content = [{"text": text}]
        if data:
            content.append({"json": data})
        return {"status": "success", "content": content}

    def _err(text: str) -> Dict[str, Any]:
        return {"status": "error", "content": [{"text": text}]}

    if not _ensure_x402():
        return _err(
            "x402 SDK not installed. Install with: pip install 'x402[httpx,evm]'"
        )

    facilitator = facilitator_url or _get_facilitator_url()

    # ── STATUS ───────────────────────────────────────────────────────────
    if action == "status":
        import x402 as x402_mod

        mechanisms = []
        try:
            from x402.mechanisms.evm.exact import ExactEvmScheme  # noqa: F401
            mechanisms.append("evm")
        except ImportError:
            pass
        try:
            from x402.mechanisms.svm.exact import ExactSvmScheme  # noqa: F401
            mechanisms.append("svm")
        except ImportError:
            pass

        # Find available wallets
        data_dir = Path(os.environ.get("ERC8004_DATA_DIR", "/tmp/strands_erc8004"))
        wallet_dirs = [Path("./wallets"), data_dir / "wallets"]
        wallets = []
        for wd in wallet_dirs:
            if wd.exists():
                wallets.extend([f.stem for f in wd.glob("*.json")])

        # Try to get facilitator supported kinds
        facilitator_info = None
        try:
            from x402.http import HTTPFacilitatorClientSync, FacilitatorConfig

            fac_client = HTTPFacilitatorClientSync(
                FacilitatorConfig(url=facilitator, timeout=5.0)
            )
            supported = fac_client.get_supported()
            facilitator_info = {
                "url": facilitator,
                "kinds": [
                    {
                        "scheme": k.scheme,
                        "network": k.network,
                        "x402_version": k.x402_version,
                    }
                    for k in supported.kinds
                ],
                "extensions": supported.extensions,
                "signers": supported.signers,
            }
            fac_client.close()
        except Exception as e:
            facilitator_info = {"url": facilitator, "error": str(e)}

        status_data = {
            "x402_installed": True,
            "version": getattr(x402_mod, "__version__", "unknown"),
            "facilitator": facilitator_info,
            "default_chain": chain,
            "mechanisms": mechanisms,
            "available_wallets": list(set(wallets)),
        }

        version = status_data["version"]
        return _ok(
            f"x402 SDK v{version} — mechanisms: {', '.join(mechanisms) or 'none'}, "
            f"wallets: {len(status_data['available_wallets'])}",
            status_data,
        )

    # ── CHECK ────────────────────────────────────────────────────────────
    elif action == "check":
        if not url:
            return _err("url required for check action")

        import httpx
        from x402.http.utils import (
            detect_payment_required_version,
            decode_payment_required_header,
        )
        from x402.http.constants import (
            PAYMENT_REQUIRED_HEADER,
            X_PAYMENT_HEADER,
        )

        try:
            resp = httpx.request(
                method.upper(), url, follow_redirects=True, timeout=10
            )

            if resp.status_code == 402:
                result = {
                    "requires_payment": True,
                    "status_code": 402,
                    "url": url,
                }

                # Detect protocol version (V1 or V2)
                resp_headers = dict(resp.headers)
                try:
                    version = detect_payment_required_version(
                        resp_headers, resp.content
                    )
                    result["x402_version"] = version
                except ValueError:
                    result["x402_version"] = "unknown"

                # Parse payment requirements using SDK
                normalized = {k.upper(): v for k, v in resp_headers.items()}
                header_value = normalized.get(PAYMENT_REQUIRED_HEADER) or normalized.get(
                    X_PAYMENT_HEADER
                )

                if header_value:
                    try:
                        payment_required = decode_payment_required_header(header_value)
                        pr_dict = payment_required.model_dump(
                            by_alias=True, exclude_none=True
                        )
                        result["payment_required"] = pr_dict
                    except Exception as e:
                        result["header_parse_error"] = str(e)
                        result["header_raw"] = header_value[:300]

                # Also try body-based requirements (V1 fallback)
                try:
                    body_json = resp.json()
                    if "accepts" in body_json or "paymentRequirements" in body_json:
                        result["payment_body"] = body_json
                except Exception:
                    pass

                return _ok(f"402 Payment Required at {url}", result)
            else:
                return _ok(
                    f"No payment required ({resp.status_code})",
                    {
                        "requires_payment": False,
                        "status_code": resp.status_code,
                        "url": url,
                    },
                )

        except Exception as e:
            return _err(f"Failed to check URL: {e}")

    # ── PAY ───────────────────────────────────────────────────────────────
    elif action == "pay":
        if not url:
            return _err("url required for pay action")
        if not wallet_name:
            return _err(
                "wallet_name required. Create one with: "
                "blockchain(action='wallet_create', name='my-wallet')"
            )

        try:
            import httpx
            from x402 import x402ClientSync
            from x402 import max_amount as max_amount_policy
            from x402.mechanisms.evm.exact import register_exact_evm_client
            from x402.http import (
                x402HTTPClientSync,
                PAYMENT_REQUIRED_HEADER,
                PAYMENT_SIGNATURE_HEADER,
                PAYMENT_RESPONSE_HEADER,
                X_PAYMENT_HEADER,
                X_PAYMENT_RESPONSE_HEADER,
            )
            from x402.http.utils import (
                detect_payment_required_version,
                decode_payment_response_header,
            )

            # 1. Build SDK client with proper signer
            signer = _get_evm_signer(wallet_name)
            client = x402ClientSync()

            # Register EVM exact scheme (V2 wildcard + V1 legacy networks)
            register_exact_evm_client(client, signer)

            # Register max_amount policy if specified
            if max_amount:
                client.register_policy(max_amount_policy(max_amount))

            # 2. Wrap in HTTP client for proper header handling
            http_client = x402HTTPClientSync(client)

            # 3. Make initial request
            extra_headers = json.loads(headers) if headers else {}
            request_kwargs = {
                "follow_redirects": True,
                "timeout": 30,
                "headers": extra_headers,
            }

            if method.upper() in ("POST", "PUT", "PATCH") and body:
                request_kwargs["content"] = body
                if "Content-Type" not in extra_headers:
                    request_kwargs["headers"]["Content-Type"] = "application/json"

            resp = httpx.request(method.upper(), url, **request_kwargs)

            # 4. Not 402? No payment needed
            if resp.status_code != 402:
                return _ok(
                    f"No payment needed ({resp.status_code})",
                    {
                        "paid": False,
                        "status_code": resp.status_code,
                        "body": resp.text[:2000],
                    },
                )

            # 5. Handle 402 using SDK's proper header parsing
            resp_headers = dict(resp.headers)
            payment_headers, payment_payload = http_client.handle_402_response(
                resp_headers, resp.content
            )

            # 6. Retry request with payment headers
            retry_headers = {**extra_headers, **payment_headers}
            retry_kwargs = {
                "follow_redirects": True,
                "timeout": 30,
                "headers": retry_headers,
            }

            if method.upper() in ("POST", "PUT", "PATCH") and body:
                retry_kwargs["content"] = body

            paid_resp = httpx.request(method.upper(), url, **retry_kwargs)

            # 7. Build result
            result = {
                "paid": True,
                "status_code": paid_resp.status_code,
                "chain": chain,
                "wallet": wallet_name,
                "payer": signer.address,
                "x402_version": payment_payload.x402_version,
                "scheme": payment_payload.get_scheme(),
                "network": payment_payload.get_network(),
            }

            # 8. Parse settlement response using SDK
            normalized_resp = {k.upper(): v for k, v in paid_resp.headers.items()}
            settlement_header = normalized_resp.get(
                PAYMENT_RESPONSE_HEADER
            ) or normalized_resp.get(X_PAYMENT_RESPONSE_HEADER)

            if settlement_header:
                try:
                    settle_response = decode_payment_response_header(settlement_header)
                    result["settlement"] = settle_response.model_dump(
                        by_alias=True, exclude_none=True
                    )
                except Exception as e:
                    result["settlement_parse_error"] = str(e)

            # 9. Parse response body
            try:
                result["response"] = paid_resp.json()
            except Exception:
                result["response"] = paid_resp.text[:2000]

            return _ok(
                f"Payment successful ({paid_resp.status_code}) via {wallet_name} on {chain}",
                result,
            )

        except ImportError as e:
            return _err(
                f"Missing x402 dependency: {e}. "
                f"Install with: pip install 'x402[httpx,evm]'"
            )
        except Exception as e:
            return _err(f"Payment failed: {e}")

    # ── DISCOVER ─────────────────────────────────────────────────────────
    elif action == "discover":
        try:
            import httpx

            # Try SDK's Bazaar extension first
            try:
                from x402.http import HTTPFacilitatorClientSync, FacilitatorConfig
                from x402.extensions.bazaar import (
                    with_bazaar,
                    ListDiscoveryResourcesParams,
                )

                fac_url = facilitator
                fac_client = HTTPFacilitatorClientSync(
                    FacilitatorConfig(url=fac_url, timeout=10.0)
                )
                bazaar_client = with_bazaar(fac_client)

                params = ListDiscoveryResourcesParams(type="http", limit=20)
                resources_resp = bazaar_client.extensions.discovery.list_resources(
                    params
                )

                resources = [
                    {"url": r.url, "type": r.type, "metadata": r.metadata}
                    for r in resources_resp.resources
                ]

                fac_client.close()

                return _ok(
                    f"Found {len(resources)} services via Bazaar SDK",
                    {
                        "services": resources[:20],
                        "chain_filter": chain,
                        "facilitator_url": fac_url,
                        "count": len(resources),
                        "total": resources_resp.total,
                        "source": "bazaar_sdk",
                    },
                )
            except (ImportError, AttributeError, Exception) as bazaar_err:
                # Fallback to raw HTTP
                bazaar_url = os.environ.get(
                    "X402_BAZAAR_URL", "https://x402.org/bazaar"
                )
                params = {}
                if chain:
                    params["network"] = _chain_to_caip2(chain)

                resp = httpx.get(
                    f"{bazaar_url}/api/services",
                    params=params,
                    timeout=10,
                    follow_redirects=True,
                )

                if resp.status_code == 200:
                    services = resp.json()
                    count = len(services) if isinstance(services, list) else "unknown"
                    return _ok(
                        f"Found {count} services on {chain}",
                        {
                            "services": (
                                services[:20]
                                if isinstance(services, list)
                                else services
                            ),
                            "chain_filter": chain,
                            "bazaar_url": bazaar_url,
                            "count": count,
                            "source": "http_fallback",
                            "bazaar_sdk_error": str(bazaar_err),
                        },
                    )
                else:
                    return _err(
                        f"Bazaar returned {resp.status_code}. "
                        f"Service may not be available yet. "
                        f"SDK error: {bazaar_err}"
                    )

        except Exception as e:
            return _err(f"Discovery failed: {e}")

    # ── CREATE_CONFIG ────────────────────────────────────────────────────
    elif action == "create_config":
        if not pay_to:
            return _err(
                "pay_to address required. Use your agent's payment wallet address."
            )
        if not amount:
            return _err("amount required (e.g. '0.01' for $0.01 USDC)")

        try:
            from x402 import x402ResourceServerSync, ResourceConfig
            from x402.http import (
                HTTPFacilitatorClientSync,
                FacilitatorConfig,
                x402HTTPResourceServerSync,
                PaywallConfig,
                RouteConfig,
                RoutesConfig,
            )
            from x402.mechanisms.evm.exact import (
                ExactEvmServerScheme,
                register_exact_evm_server,
            )

            network = _chain_to_caip2(chain)

            # Build proper server configuration using SDK
            fac_config = FacilitatorConfig(url=facilitator, timeout=10.0)
            fac_client = HTTPFacilitatorClientSync(fac_config)

            server = x402ResourceServerSync(fac_client)
            register_exact_evm_server(server)
            server.initialize()

            # Build payment requirements using SDK
            resource_config = ResourceConfig(
                scheme="exact",
                network=network,
                pay_to=pay_to,
                price=f"${amount}",
                description=description or "Agent API access",
            )

            requirements = server.build_payment_requirements(resource_config)

            # Serialize requirements for config
            requirements_dicts = [
                r.model_dump(by_alias=True, exclude_none=True) for r in requirements
            ]

            # Build route config
            route_path = url or "/"
            route_method = method.upper()

            config = {
                "x402": {
                    "version": "v2",
                    "facilitator_url": facilitator,
                    "routes": {
                        f"{route_method} {route_path}": {
                            "accepts": requirements_dicts,
                            "description": description or "Paid agent endpoint",
                        },
                    },
                },
                "registration_file_update": {"x402Support": True},
            }

            # Generate SDK-based middleware examples
            fastapi_example = f"""\
# FastAPI middleware example
from fastapi import FastAPI
from x402 import x402ResourceServerSync, ResourceConfig
from x402.http import (
    HTTPFacilitatorClientSync, FacilitatorConfig,
    x402HTTPResourceServerSync, PaywallConfig, RouteConfig, RoutesConfig,
)
from x402.mechanisms.evm.exact import register_exact_evm_server

app = FastAPI()

# Configure x402 server
fac_client = HTTPFacilitatorClientSync(FacilitatorConfig(url="{facilitator}"))
resource_server = x402ResourceServerSync(fac_client)
register_exact_evm_server(resource_server)
resource_server.initialize()

# Configure paywall
routes = RoutesConfig(routes={{
    "{route_method} {route_path}": RouteConfig(
        scheme="exact",
        network="{network}",
        pay_to="{pay_to}",
        price="${amount}",
        description="{description or 'Agent API access'}",
    ),
}})

http_server = x402HTTPResourceServerSync(resource_server, routes)

# Add middleware
from x402.http.middleware.fastapi import fastapi_payment_middleware
app.middleware("http")(fastapi_payment_middleware(http_server))
"""

            flask_example = f"""\
# Flask middleware example
from flask import Flask
from x402 import x402ResourceServerSync, ResourceConfig
from x402.http import (
    HTTPFacilitatorClientSync, FacilitatorConfig,
    x402HTTPResourceServerSync, PaywallConfig, RouteConfig, RoutesConfig,
)
from x402.mechanisms.evm.exact import register_exact_evm_server
from x402.http.middleware.flask import FlaskPaymentMiddleware

app = Flask(__name__)

# Configure x402 server
fac_client = HTTPFacilitatorClientSync(FacilitatorConfig(url="{facilitator}"))
resource_server = x402ResourceServerSync(fac_client)
register_exact_evm_server(resource_server)
resource_server.initialize()

# Configure paywall
routes = RoutesConfig(routes={{
    "{route_method} {route_path}": RouteConfig(
        scheme="exact",
        network="{network}",
        pay_to="{pay_to}",
        price="${amount}",
        description="{description or 'Agent API access'}",
    ),
}})

http_server = x402HTTPResourceServerSync(resource_server, routes)
FlaskPaymentMiddleware(app, http_server)
"""

            fac_client.close()

            return {
                "status": "success",
                "content": [
                    {
                        "text": (
                            f"x402 config for {pay_to} — ${amount} USDC on {chain}\n"
                            f"Requirements built via SDK with facilitator at {facilitator}\n\n"
                            f"## FastAPI Example:\n```python\n{fastapi_example}\n```\n\n"
                            f"## Flask Example:\n```python\n{flask_example}\n```\n\n"
                            f"Update ERC-8004 registration: "
                            f"erc8004(action='update_agent', ...) with x402Support: true"
                        )
                    },
                    {"json": config},
                ],
            }

        except Exception as e:
            # Fallback: generate static config without connecting to facilitator
            network = _chain_to_caip2(chain)
            amount_micro = str(int(float(amount) * 1_000_000))

            config = {
                "x402": {
                    "version": "v2",
                    "facilitator_url": facilitator,
                    "routes": {
                        f"{method.upper()} {url or '/'}": {
                            "accepts": [
                                {
                                    "scheme": "exact",
                                    "network": network,
                                    "maxAmountRequired": amount_micro,
                                    "resource": url or "https://your-agent.com/api",
                                    "description": description or "Agent API access",
                                    "payTo": pay_to,
                                    "extra": {"name": "USDC", "version": "2"},
                                }
                            ],
                            "description": description or "Paid agent endpoint",
                        }
                    },
                },
                "registration_file_update": {"x402Support": True},
                "_note": f"Static config (facilitator unavailable: {e})",
            }

            return _ok(
                f"x402 static config for {pay_to} — ${amount} USDC on {chain} "
                f"(facilitator unavailable: {e})",
                config,
            )

    else:
        return _err(
            f"Unknown action: {action}. Valid: pay, check, discover, status, create_config\n\n"
            f"Examples:\n"
            f'  x402(action="check", url="https://api.example.com/weather")\n'
            f'  x402(action="pay", url="...", wallet_name="my-agent", chain="base")\n'
            f'  x402(action="status")\n'
            f'  x402(action="discover", chain="base")\n'
            f'  x402(action="create_config", pay_to="0x...", amount="0.01", chain="base")'
        )
