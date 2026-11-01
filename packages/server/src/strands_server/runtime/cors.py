"""CORS for browser-based hosts that call the MCP endpoint directly."""

import json
from collections.abc import Mapping

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

BROWSER_ORIGINS_ENV = "STRANDS_BROWSER_ORIGINS"
FALLBACK_ORIGINS_ENV = "OUBLIAI_BROWSER_ORIGINS"
MCP_REQUEST_HEADERS = ("mcp-protocol-version", "mcp-session-id", "Authorization", "Content-Type")
MCP_EXPOSED_HEADERS = ("mcp-session-id",)


def browser_cors_middleware(origins: list[str]) -> list[Middleware]:
    """Starlette middleware list for `FastMCP.http_app(middleware=...)` / `run(middleware=...)`."""
    return [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=list(MCP_REQUEST_HEADERS),
            expose_headers=list(MCP_EXPOSED_HEADERS),
        )
    ]


def browser_origins_from_env(env: Mapping[str, str]) -> list[str]:
    """Exact browser origins from `STRANDS_BROWSER_ORIGINS` (or `OUBLIAI_BROWSER_ORIGINS`) JSON list."""
    raw = env.get(BROWSER_ORIGINS_ENV) or env.get(FALLBACK_ORIGINS_ENV)
    if not raw:
        return []
    origins = json.loads(raw)
    if not isinstance(origins, list) or not all(isinstance(o, str) for o in origins):
        raise SystemExit(f"{BROWSER_ORIGINS_ENV} must be a JSON list of origin strings")
    if "*" in origins:
        raise SystemExit(f"{BROWSER_ORIGINS_ENV} must list exact origins, not '*'")
    return origins
