"""Client-side proxy for the non-Strands REA MCP server (https://github.com/morluto/rea).

Provides:
- `rea_transport`: `StdioTransport` launching `node src/mcp/rea/scripts/rea.mjs mcp`.
- `create_rea_client`: FastMCP `Client` connected to the REA MCP server.
- `create_rea_proxy`: FastMCP proxy server (`fastmcp.server.create_proxy`) wrapping the REA client/transport.
- `list_rea_tools` and `call_rea_tool`: convenience helpers for inspecting and calling proxied REA tools.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import StdioTransport
from fastmcp.server import create_proxy
from mcp.types import Tool

DEFAULT_REA_DIR = Path(__file__).resolve().parents[4] / "src" / "mcp" / "rea"


def rea_transport(rea_dir: str | Path | None = None) -> StdioTransport:
    """Build a `StdioTransport` for the local `morluto/rea` MCP server (`io.github.morluto/rea`)."""
    root = Path(rea_dir) if rea_dir is not None else DEFAULT_REA_DIR
    script = root / "scripts" / "rea.mjs"
    if not script.exists():
        raise FileNotFoundError(f"REA entrypoint not found at {script}")
    return StdioTransport(
        command="node",
        args=[str(script), "mcp"],
        cwd=str(root),
        log_file=Path(os.devnull),
    )


def create_rea_client(rea_dir: str | Path | None = None, *, name: str = "rea") -> Client[StdioTransport]:
    """Create a FastMCP `Client` connected to the non-Strands `morluto/rea` MCP server."""
    return Client(rea_transport(rea_dir), name=name)


def create_rea_proxy(
    target: Client[Any] | StdioTransport | str | Path | None = None,
    *,
    name: str = "REA Reverse Engineering Proxy",
) -> FastMCP:
    """Create a FastMCP proxy server (`fastmcp.server.create_proxy`) over the REA MCP server."""
    if target is None or isinstance(target, (str, Path)):
        proxy_target: Any = create_rea_client(target)
    else:
        proxy_target = target
    return create_proxy(proxy_target, name=name)


async def list_rea_tools(rea_dir: str | Path | None = None) -> list[Tool]:
    """Connect to the proxied REA MCP server and list all reverse-engineering tools."""
    async with create_rea_client(rea_dir) as rea_client:
        proxy = create_rea_proxy(rea_client)
        async with Client(proxy) as client:
            return await client.list_tools()


async def call_rea_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    rea_dir: str | Path | None = None,
) -> CallToolResult:
    """Invoke a tool on the proxied REA MCP server."""
    async with create_rea_client(rea_dir) as rea_client:
        proxy = create_rea_proxy(rea_client)
        async with Client(proxy) as client:
            return await client.call_tool(tool_name, arguments or {})
