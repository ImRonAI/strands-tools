# pyright: strict
"""CORS for browser-based hosts that call the MCP endpoint directly."""

import json
from collections.abc import Mapping, Sequence
from typing import TypeGuard

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

BROWSER_ORIGINS_ENV = "STRANDS_BROWSER_ORIGINS"
FALLBACK_ORIGINS_ENV = "OUBLIAI_BROWSER_ORIGINS"
MCP_REQUEST_HEADERS = ("mcp-protocol-version", "mcp-session-id", "Authorization", "Content-Type")
MCP_EXPOSED_HEADERS = ("mcp-session-id",)


def _is_obj_sequence(val: object) -> TypeGuard[Sequence[object]]:
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes))


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
    origins_raw: object = json.loads(raw)
    if not _is_obj_sequence(origins_raw) or not all(isinstance(o, str) for o in origins_raw):
        raise SystemExit(f"{BROWSER_ORIGINS_ENV} must be a JSON list of origin strings")
    origins = [str(o) for o in origins_raw]
    if "*" in origins:
        raise SystemExit(f"{BROWSER_ORIGINS_ENV} must list exact origins, not '*'")
    return origins
