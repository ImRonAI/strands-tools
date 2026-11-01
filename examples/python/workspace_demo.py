"""Workspace, task, and REA proxy demo on top of strands_client.

Loads the MCP URL from the repository root mcp.json, then drives search,
workspaces, the renderer resource, a long-running Strands background job task,
and the proxied non-Strands REA MCP server.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for pkg_src in (
    REPO_ROOT / "packages" / "client" / "src",
    REPO_ROOT / "packages" / "server" / "src",
):
    if str(pkg_src) not in sys.path:
        sys.path.insert(0, str(pkg_src))

from strands_client import (
    ProgressRecorder,
    StrandsConnection,
    await_strands_job_task,
    connect,
    file_token_storage,
    get_schema,
    list_model_visible_tools,
    list_rea_tools,
    oauth,
    open_workspace,
    read_renderer_resource,
    search,
    server_summary,
    wait_for,
)

MCP_CONFIG = REPO_ROOT / "mcp.json"
TOKEN_DIR = Path.home() / ".strands_mcp" / "tokens"


def _mcp_url(config_path: Path = MCP_CONFIG) -> str:
    config = json.loads(config_path.read_text())
    url = config["mcpServers"]["strands-tools"]["url"]
    if not isinstance(url, str) or not url:
        raise ValueError("mcp.json: mcpServers.strands-tools.url missing")
    return url


async def summarize(connection: StrandsConnection) -> None:
    info = server_summary(connection)
    print(f"server: {info['name']} {info['version']} (protocol {info['protocol_version']})")
    tools = await list_model_visible_tools(connection)
    print(f"tools ({len(tools)}):")
    for tool in tools:
        print(f"- {tool.name}")


async def show_catalog(connection: StrandsConnection) -> None:
    found = await search(connection, "use_google gmail calendar")
    print("search:", found.structured_content)
    schema = await get_schema(connection, ["use_google"])
    print("schema:", schema.structured_content)


async def open_google(connection: StrandsConnection) -> None:
    workspace = await open_workspace(connection, "google")
    print(f"workspace google: prefab {workspace.prefab_version}")
    print("tools:", ", ".join(workspace.tool_names))


async def renderer_info(connection: StrandsConnection) -> None:
    renderer = await read_renderer_resource(connection)
    print(f"renderer: {renderer.uri} ({renderer.mime_type})")
    if renderer.csp is not None:
        print("csp:", dict(renderer.csp))


async def track_strands_job(
    connection: StrandsConnection,
    job_id: str,
    *,
    recorder: ProgressRecorder | None = None,
) -> None:
    task = await await_strands_job_task(connection, kind="pack_job", job_id=job_id)
    result = await wait_for(task, timeout=60.0)
    payload: Mapping[str, Any] = result.structured_content or {}
    print(f"strands job {job_id}: {payload.get('status')} (polls={payload.get('polls')})")
    if recorder is not None:
        print(f"progress events: {len(recorder.events)}")


async def show_rea_proxy() -> None:
    tools = await list_rea_tools()
    print(f"proxied rea tools: {len(tools)} (first={tools[0] if tools else 'none'})")


async def main() -> None:
    url = _mcp_url()
    print(f"NOTE: this performs a real OAuth login against {url}")
    print(f"Tokens persist encrypted under {TOKEN_DIR}.")
    storage = file_token_storage(TOKEN_DIR, os.environ["STRANDS_CLIENT_TOKEN_KEY"])
    async with connect(url, auth=oauth(token_storage=storage)) as connection:
        await summarize(connection)
        await show_catalog(connection)
        await open_google(connection)
        await renderer_info(connection)
        await track_strands_job(connection, "demo-job-1")
        await show_rea_proxy()


if __name__ == "__main__":
    print("Demo requires a running Strands MCP Server; run only when authorized.")
    asyncio.run(main())
