"""Server composition: Strands tool suites + FastMCPApp workspaces behind CodeMode, plus native GenerativeUI.

Mirrors the TelnyxMCP FastMCP 4.1.0 reference architecture:
- CodeMode (`search`, `get_schema`, `execute`) lives on the mounted `operations` server.
- `GenerativeUI` (`generate_prefab_ui` + `ui://prefab/generative.html`) is a provider of the root server.
- `TasksExtension` is registered on the root server.
- 14 domain `FastMCPApp` workspaces sit on `operations` before `CodeMode`.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
for _extra_path in (
    _REPO_ROOT / "src" / "tools",
    _REPO_ROOT / "src",
    _REPO_ROOT / "packages" / "server" / "src",
    _REPO_ROOT / "packages" / "client" / "src",
):
    _extra_str = str(_extra_path)
    if _extra_str not in sys.path:
        sys.path.insert(0, _extra_str)

from fastmcp import FastMCP
from fastmcp.apps.generative import GenerativeUI
from fastmcp.experimental.transforms.code_mode import CodeMode, GetSchemas, GetTags, Search
from fastmcp.mcp_config import MCPConfig, RemoteMCPServer, StdioMCPServer
from fastmcp.server import create_proxy
from fastmcp.server.providers.addressing import parse_hashed_backend_name
from fastmcp.tools.base import Tool
from fastmcp_tasks import TasksExtension
from starlette.requests import Request
from starlette.responses import JSONResponse

from strands_server.apps import ALL_APPS
from strands_server.catalog_loader import register_catalog_on_operations
from strands_server.runtime.approval_gate import ApprovalGate
from strands_server.runtime.sandbox import prepare_prefab_sandbox_env
from strands_server.runtime.tasks import build_tasks_extension, register_task_tools

SERVER_NAME = "Strands Tools MCP"
DEFAULT_MAX_TOOL_CALLS = 25
logger = logging.getLogger(__name__)


class _AppAwareCodeMode(CodeMode):
    """CodeMode that also permits `execute` to dispatch identity-addressed (`<hash>_<name>`)
    app backend tools when a gateway only routes `tools/list` names.

    Bare app-only names remain excluded from `search`, `get_schema`, and `execute`.
    """

    @staticmethod
    def _find_tool(name: str, tools: Sequence[Tool]) -> Tool | None:
        found = CodeMode._find_tool(name, tools)
        if found is not None:
            return found
        if parse_hashed_backend_name(name) is not None:
            return Tool(name=name, parameters={"type": "object"})
        return None


def build_proxied_servers() -> list[tuple[str, Any]]:
    """Build proxies for Telnyx, REA, and founder's servers in src/mcp."""
    proxies: list[tuple[str, Any]] = []

    # 1. Telnyx Remote MCP (FR-M2-3.1)
    telnyx_key = os.environ.get("TELNYX_API_KEY")
    if telnyx_key:
        try:
            cfg = MCPConfig(
                mcpServers={
                    "telnyx": RemoteMCPServer(
                        url="https://api.telnyx.com/v2/mcp",
                        transport="http",
                        auth=telnyx_key,
                    )
                }
            )
            proxies.append(("telnyx", create_proxy(cfg)))
        except Exception as e:
            logger.warning("Failed to build telnyx proxy: %s", e)
    else:
        logger.info("TELNYX_API_KEY not set; skipping telnyx proxy mount")

    # 2. REA stdio proxy (mount only when node binary and built REA node_modules exist)
    try:
        from strands_client.rea_proxy import DEFAULT_REA_DIR, create_rea_proxy

        if shutil.which("node") and (DEFAULT_REA_DIR / "node_modules").exists():
            rea_p = create_rea_proxy()
            if rea_p:
                proxies.append(("rea", rea_p))
    except Exception as e:
        logger.warning("REA proxy not available: %s", e)

    # 3. Founder's servers in src/mcp
    mcp_dir = Path(__file__).resolve().parents[4] / "src" / "mcp"
    if mcp_dir.exists():
        server_dirs = [
            "cagatay_mcp_server",
            "cms-coverage-mcp-server",
            "healthcare-mcp-public",
            "mcp-installer",
            "openapi-mcp",
            "strands_mcp_server",
            "tools_mcp",
            "utcp",
        ]
        for sdir_name in server_dirs:
            sdir = mcp_dir / sdir_name
            if not sdir.exists():
                continue
            py_entry = sdir / "server.py"
            if py_entry.exists():
                try:
                    cfg = MCPConfig(
                        mcpServers={
                            sdir_name: StdioMCPServer(
                                command=sys.executable,
                                args=[str(py_entry.resolve())],
                            )
                        }
                    )
                    proxies.append((sdir_name, create_proxy(cfg)))
                except Exception as e:
                    logger.warning("Failed to mount %s: %s", sdir_name, e)

    return proxies


def build_operations(
    *,
    max_tool_calls: int | None = DEFAULT_MAX_TOOL_CALLS,
    mask_error_details: bool | None = None,
) -> FastMCP:
    """All Strands tools and domain FastMCPApp workspaces, discoverable through CodeMode."""
    operations = FastMCP("Strands operations", mask_error_details=mask_error_details)
    register_catalog_on_operations(operations)

    # Mount proxied servers (Telnyx, REA, founder servers)
    for namespace, proxy in build_proxied_servers():
        try:
            operations.mount(proxy, namespace=namespace)
        except Exception as e:
            logger.warning("Failed to mount %s on operations: %s", namespace, e)

    for domain_app in ALL_APPS:
        operations.add_provider(domain_app)
    register_task_tools(operations)
    operations.add_transform(
        _AppAwareCodeMode(
            discovery_tools=[GetTags(), Search(), GetSchemas()],
            max_tool_calls=max_tool_calls,
        )
    )
    return operations


def build_server(
    *,
    tasks: TasksExtension | None = None,
    max_tool_calls: int | None = DEFAULT_MAX_TOOL_CALLS,
    **fastmcp_kwargs: Any,
) -> FastMCP:
    """Build the model-facing server: `search`, `get_schema`, `execute`, `generate_prefab_ui`."""
    prepare_prefab_sandbox_env()
    server = FastMCP(
        SERVER_NAME,
        providers=[GenerativeUI()],
        **fastmcp_kwargs,
    )

    # Register root Money Approval Gate middleware (CAT-115)
    server.add_middleware(ApprovalGate())

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy"})

    @server.custom_route("/ready", methods=["GET"])
    async def ready(_: Request) -> JSONResponse:
        proxied_names = [ns for ns, _ in build_proxied_servers()]
        return JSONResponse({"status": "ready", "mounted_proxies": proxied_names})

    server.add_extension(tasks if tasks is not None else build_tasks_extension())
    server.mount(
        build_operations(
            max_tool_calls=max_tool_calls,
            mask_error_details=fastmcp_kwargs.get("mask_error_details"),
        )
    )
    return server
