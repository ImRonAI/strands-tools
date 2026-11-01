"""Contract tests for strands_client and the non-Strands REA MCP proxy."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for pkg_src in (
    REPO_ROOT / "packages" / "client" / "src",
    REPO_ROOT / "packages" / "server" / "src",
):
    if str(pkg_src) not in sys.path:
        sys.path.insert(0, str(pkg_src))

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import ClientTransport
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.utilities.tests import asgi_client
from fastmcp_tasks import TasksExtension

from strands_client import (
    WORKSPACE_DOMAINS,
    create_rea_client,
    create_rea_proxy,
    execute,
    get_schema,
    list_model_visible_tools,
    list_rea_tools,
    open_workspace,
    read_renderer_resource,
    search,
)
from strands_server import build_server


@pytest.fixture(scope="module")
def server_instance() -> FastMCP:
    return build_server(
        auth=StaticTokenVerifier(
            tokens={"client-token": {"client_id": "pytest", "scopes": []}}
        ),
        tasks=TasksExtension(url="memory://"),
    )


@pytest.fixture
async def client_conn(server_instance: FastMCP) -> AsyncIterator[Client[ClientTransport]]:
    async with asgi_client(server_instance, auth="client-token") as client:
        yield client


async def test_client_catalog_and_workspace_helpers(
    client_conn: Client[ClientTransport],
) -> None:
    visible = await list_model_visible_tools(client_conn)
    assert [t.name for t in visible] == [
        "execute",
        "generate_prefab_ui",
        "get_schema",
        "search",
    ]

    found = await search(client_conn, "inspect_tool")
    assert "inspect_tool" in str(found.structured_content)

    schema = await get_schema(client_conn, ["inspect_tool"])
    assert "inspect_tool" in str(schema.structured_content)

    exec_res = await execute(
        client_conn,
        "return await call_tool('strands_my_catalog', {'action': 'summary'})",
    )
    assert not exec_res.is_error
    sc = exec_res.structured_content or {}
    meta = sc.get("meta") or sc.get("result", {}).get("meta", {})
    assert meta.get("total_catalog_tools", 0) >= 350

    for domain in ("google", "skills", "ccxt", "harness"):
        assert domain in WORKSPACE_DOMAINS
        ws = await open_workspace(client_conn, domain)
        assert ws.prefab_version == "0.3"
        assert len(ws.tool_names) > 0

    renderer = await read_renderer_resource(client_conn)
    assert renderer.uri == "ui://prefab/generative.html"
    assert renderer.mime_type == "text/html;profile=mcp-app"


async def test_rea_non_strands_mcp_server_proxied_by_client() -> None:
    # 1. Direct client listing via list_rea_tools()
    tools = await list_rea_tools()
    tool_names = {t.name for t in tools}
    assert len(tool_names) >= 200
    assert "inspect_desktop_application" in tool_names

    # 2. FastMCP proxy server created via create_rea_proxy()
    async with create_rea_client() as rea_client:
        proxy_server = create_rea_proxy(rea_client)
        async with Client(proxy_server) as proxy_client:
            proxied_tools = await proxy_client.list_tools()
            proxied_names = {t.name for t in proxied_tools}
            assert len(proxied_names) >= 200
            assert "inspect_desktop_application" in proxied_names
