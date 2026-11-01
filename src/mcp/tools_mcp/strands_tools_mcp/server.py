"""MCP server that exposes Strands Agents tools over the MCP stdio transport.

Uses the raw ``mcp`` library directly (no FastMCP) so we can register tools
with their existing JSON schemas and dispatch calls through the unified
``AgentTool.stream()`` interface — which handles both ``@tool``-decorated
functions and ``TOOL_SPEC`` module-based tools transparently.

Configuration is via environment variables:

- ``STRANDS_TOOLS`` — comma-separated module names from the
  ``strands-agents-tools`` package (e.g. ``"shell,file_read,current_time"``).
- ``STRANDS_TOOLS_PATHS`` — comma-separated file paths to custom ``.py``
  tool files.

At least one must be set.
"""

import asyncio
import logging
import os
import sys
import uuid
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from strands.types.tools import AgentTool

from strands_tools_mcp.loader import load_tools_from_names, load_tools_from_paths

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool invocation helper
# ---------------------------------------------------------------------------


async def _call_strands_tool(tool: AgentTool, arguments: dict[str, Any]) -> str:
    """Invoke a Strands ``AgentTool`` and return the result as text.

    Both ``DecoratedFunctionTool`` and ``PythonAgentTool`` implement
    ``AgentTool.stream()``.  The stream yields events; the last one
    contains the ``ToolResult``.

    Args:
        tool: The Strands tool to invoke.
        arguments: The MCP call arguments (maps to ``tool_use["input"]``).

    Returns:
        A string representation of the tool's output.
    """
    tool_use = {
        "toolUseId": str(uuid.uuid4()),
        "name": tool.tool_name,
        "input": arguments,
    }

    last_event: dict[str, Any] | None = None
    async for event in tool.stream(tool_use, invocation_state={}):
        # Events are ToolResultEvent / ToolStreamEvent dicts
        last_event = event if isinstance(event, dict) else getattr(event, "__dict__", {"raw": str(event)})

    if last_event is None:
        return ""

    # Extract the ToolResult from the event wrapper
    result = last_event.get("tool_result", last_event)
    content = result.get("content", [])
    texts = [c.get("text", str(c)) for c in content if isinstance(c, dict)]
    return "\n".join(texts) if texts else str(result)


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


def create_server() -> tuple[Server, list[AgentTool]]:
    """Create an MCP ``Server`` and load tools from environment variables.

    Returns:
        A ``(server, tools)`` tuple.  The server has ``list_tools`` and
        ``call_tool`` handlers registered.
    """
    tool_names_env = os.environ.get("STRANDS_TOOLS", "")
    tool_paths_env = os.environ.get("STRANDS_TOOLS_PATHS", "")

    if not tool_names_env and not tool_paths_env:
        logger.error("No tools configured. Set STRANDS_TOOLS and/or STRANDS_TOOLS_PATHS environment variables.")
        sys.exit(1)

    tools: list[AgentTool] = []

    if tool_names_env:
        names = [n.strip() for n in tool_names_env.split(",") if n.strip()]
        tools.extend(load_tools_from_names(names))

    if tool_paths_env:
        paths = [p.strip() for p in tool_paths_env.split(",") if p.strip()]
        tools.extend(load_tools_from_paths(paths))

    if not tools:
        logger.error(
            "No tools were loaded successfully. Check the logs above for errors (missing dependencies, bad URLs, etc.)."
        )
        sys.exit(1)

    # Build a name → tool lookup for call dispatching
    tool_map: dict[str, AgentTool] = {t.tool_name: t for t in tools}

    server = Server("strands-tools-mcp")

    # ---- list_tools handler ----
    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        mcp_tools: list[types.Tool] = []
        for t in tools:
            spec = t.tool_spec
            mcp_tools.append(
                types.Tool(
                    name=spec["name"],
                    description=spec.get("description", ""),
                    inputSchema=spec.get("inputSchema", {}).get("json", {"type": "object", "properties": {}}),
                )
            )
        return mcp_tools

    # ---- call_tool handler ----
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[types.TextContent]:
        if name not in tool_map:
            raise ValueError(f"Unknown tool: {name}")

        result_text = await _call_strands_tool(tool_map[name], arguments or {})
        return [types.TextContent(type="text", text=result_text)]

    logger.info("Registered %d tool(s) with MCP server", len(tools))
    return server, tools


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``strands-tools-mcp`` CLI command."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Strands tools like shell and python_repl check BYPASS_TOOL_CONSENT and
    # will block waiting for interactive confirmation if it's not set.  In an
    # MCP server there's nobody at the terminal to approve, so default to true.
    os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

    server, tools = create_server()
    tool_names = [t.tool_name for t in tools]
    logger.info("Starting MCP stdio server with tools: %s", tool_names)

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
