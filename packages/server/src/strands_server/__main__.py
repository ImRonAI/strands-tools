# pyright: strict
"""HTTP/Stdio entry point: `fastmcp run fastmcp.json` or `python -m strands_server`."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TypeGuard

_SERVER_SRC = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SERVER_SRC.parents[2]
for _extra_path in (
    _REPO_ROOT / "src" / "tools",
    _REPO_ROOT / "src",
    _SERVER_SRC,
    _REPO_ROOT / "packages" / "client" / "src",
):
    _extra_str = str(_extra_path)
    if _extra_str not in sys.path:
        sys.path.insert(0, _extra_str)

from fastmcp import FastMCP

from strands_server.auth.provider import build_auth
from strands_server.runtime.cors import browser_cors_middleware, browser_origins_from_env
from strands_server.runtime.storage import build_client_storage
from strands_server.server import build_server

SINGLE_TENANT_ACCESS_TOKEN_ENV = "STRANDS_ACCESS_TOKEN"
FALLBACK_ACCESS_TOKEN_ENV = "OUBLIAI_ACCESS_TOKEN"
PLATFORM_AUTH_ENV = "STRANDS_PLATFORM_AUTH"
FALLBACK_PLATFORM_AUTH_ENV = "OUBLIAI_PLATFORM_AUTH"
_MIN_ACCESS_TOKEN_LENGTH = 24


def _is_obj_sequence(val: object) -> TypeGuard[Sequence[object]]:
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes))


def create_server() -> FastMCP:
    """Entrypoint for `fastmcp run fastmcp.json` and `python -m strands_server`."""
    access_token = (
        os.environ.get(SINGLE_TENANT_ACCESS_TOKEN_ENV)
        or os.environ.get(FALLBACK_ACCESS_TOKEN_ENV)
        or ""
    )
    if access_token:
        from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

        if len(access_token) < _MIN_ACCESS_TOKEN_LENGTH:
            raise SystemExit(
                f"{SINGLE_TENANT_ACCESS_TOKEN_ENV} must be a random secret of at least "
                f"{_MIN_ACCESS_TOKEN_LENGTH} characters."
            )
        auth = StaticTokenVerifier(
            tokens={access_token: {"client_id": "strands-operator", "scopes": []}}
        )
        return build_server(auth=auth)

    platform_auth = (
        os.environ.get(PLATFORM_AUTH_ENV) or os.environ.get(FALLBACK_PLATFORM_AUTH_ENV) or "true"
    )
    if platform_auth.lower() == "true":
        return build_server(auth=None)

    base_url = os.environ.get("STRANDS_BASE_URL") or os.environ.get("OUBLIAI_BASE_URL")
    client_id = os.environ.get("STRANDS_OAUTH_CLIENT_ID") or os.environ.get("OUBLIAI_TELNYX_CLIENT_ID")
    client_secret = os.environ.get("STRANDS_OAUTH_CLIENT_SECRET") or os.environ.get("OUBLIAI_TELNYX_CLIENT_SECRET")
    jwt_signing_key = os.environ.get("STRANDS_JWT_SIGNING_KEY") or os.environ.get("OUBLIAI_JWT_SIGNING_KEY")
    redirect_uris_raw = os.environ.get("STRANDS_ALLOWED_CLIENT_REDIRECT_URIS") or os.environ.get(
        "OUBLIAI_ALLOWED_CLIENT_REDIRECT_URIS"
    )
    if base_url and client_id and client_secret and jwt_signing_key and redirect_uris_raw:
        raw_loaded: object = json.loads(redirect_uris_raw)
        redirect_uris = [str(u) for u in raw_loaded] if _is_obj_sequence(raw_loaded) else []
        oauth_auth = build_auth(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
            jwt_signing_key=jwt_signing_key,
            allowed_client_redirect_uris=redirect_uris,
            client_storage=build_client_storage(),
        )
        return build_server(auth=oauth_auth)

    return build_server(auth=None)


def run_options() -> dict[str, object]:
    """Keyword arguments for `FastMCP.run()`; CORS when browser origins are configured."""
    transport = os.environ.get("STRANDS_MCP_TRANSPORT", "http")
    options: dict[str, object] = {"transport": transport}
    if transport == "http":
        origins = browser_origins_from_env(os.environ)
        if origins:
            options["middleware"] = browser_cors_middleware(origins)
            options["allowed_origins"] = origins
    return options


def main() -> None:
    opts = run_options()
    transport_val = str(opts.get("transport", "http"))
    if transport_val == "stdio":
        create_server().run(transport="stdio")
    else:
        create_server().run(transport="http")


if __name__ == "__main__":
    main()
