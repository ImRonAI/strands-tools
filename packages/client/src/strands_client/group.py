# pyright: strict
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from fastmcp import Client
from fastmcp.client.client import ConnectMode
from fastmcp.client.group import ClientGroup
from fastmcp.client.transports import ClientTransport
from fastmcp.mcp_config import MCPConfig

from strands_client.connection import StrandsConnection, connect
from strands_client.rea_proxy import create_rea_client


def group(clients: Mapping[str, Client[ClientTransport]]) -> ClientGroup:
    return ClientGroup(clients)


def group_from_mcp_config(
    config: MCPConfig | dict[str, object], *, default_mode: ConnectMode = "auto"
) -> ClientGroup:
    return ClientGroup.from_config(config, default_mode=default_mode)


def group_with_rea(
    strands_target: StrandsConnection | str,
    *,
    rea_dir: str | Path | None = None,
) -> ClientGroup:
    """Create a `ClientGroup` combining the Strands FastMCP Server (`strands`) and the proxied REA MCP server (`rea`)."""
    strands_client = connect(strands_target)
    rea_client = cast(Client[ClientTransport], create_rea_client(rea_dir))
    return ClientGroup({"strands": strands_client, "rea": rea_client})
