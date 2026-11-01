"""Universal Tool Calling Protocol (UTCP) integration for Strands Agents SDK.

Provides both `UtcpToolAdapter` / `UtcpAgentTool` (class-based adapter) and
model-invocable `@tool` functions (`utcp`, `utcp_register_manual`, `utcp_search_tools`,
`utcp_list_tools`, `utcp_call_tool`) for dynamic UTCP discovery and tool invocation.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from strands import tool

from .utcp_tool_adapter import (
    UtcpAgentTool,
    UtcpToolAdapter,
    UtcpToolAdapterError,
    format_tool_name_for_bedrock,
)

__version__ = "0.1.0"

_ACTIVE_ADAPTERS: Dict[str, UtcpToolAdapter] = {}


def create_utcp_adapter(config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> UtcpToolAdapter:
    """Create a UTCP tool provider with default settings."""
    return UtcpToolAdapter(config=config, **kwargs)


def _run_coro(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@tool
def utcp_register_manual(
    adapter_id: str = "default",
    manual_call_templates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Initialize or update a UTCP adapter with call templates (http, sse, streamable_http, cli, graphql, mcp, tcp, udp, text).

    Args:
        adapter_id: Logical identifier for this UTCP adapter session (default "default").
        manual_call_templates: List of UTCP call template definitions (each with `name`,
            `call_template_type`, `url`/`command`/`host`, optional `http_method`, `auth`, `headers`).

    Returns:
        Dictionary with adapter status and discovered UTCP tool names.
    """
    config = {"manual_call_templates": list(manual_call_templates or [])}
    adapter = UtcpToolAdapter(config=config)
    try:
        _run_coro(adapter.start())
    except Exception as exc:
        _ACTIVE_ADAPTERS[adapter_id] = adapter
        return {
            "status": "warning",
            "adapter_id": adapter_id,
            "configured_templates": len(config["manual_call_templates"]),
            "message": f"UTCP adapter registered (live discovery deferred: {exc})",
        }
    _ACTIVE_ADAPTERS[adapter_id] = adapter
    tools = adapter.to_strands_tools()
    return {
        "status": "success",
        "adapter_id": adapter_id,
        "configured_templates": len(config["manual_call_templates"]),
        "tool_count": len(tools),
        "tools": [t.tool_name for t in tools],
    }


@tool
def utcp_list_tools(adapter_id: str = "default") -> Dict[str, Any]:
    """List all Strands-adapted UTCP tools currently loaded in an adapter session.

    Args:
        adapter_id: Identifier of the UTCP adapter (default "default").
    """
    adapter = _ACTIVE_ADAPTERS.get(adapter_id)
    if adapter is None:
        return {"status": "success", "adapter_id": adapter_id, "tool_count": 0, "tools": []}
    tools = adapter.to_strands_tools()
    return {
        "status": "success",
        "adapter_id": adapter_id,
        "tool_count": len(tools),
        "tools": [
            {
                "name": t.tool_name,
                "original_name": t.utcp_tool.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ],
    }


@tool
def utcp_search_tools(
    query: str = "",
    adapter_id: str = "default",
    max_results: int = 50,
) -> Dict[str, Any]:
    """Search UTCP tools registered in the given UTCP adapter.

    Args:
        query: Search query string to match UTCP tools.
        adapter_id: Identifier of the UTCP adapter (default "default").
        max_results: Maximum number of tools to return.
    """
    adapter = _ACTIVE_ADAPTERS.get(adapter_id)
    if adapter is None:
        return {"status": "error", "error": f"UTCP adapter '{adapter_id}' is not registered. Call utcp_register_manual first."}
    matched = _run_coro(adapter.search_tools(query=query, max_results=max_results))
    return {
        "status": "success",
        "adapter_id": adapter_id,
        "query": query,
        "count": len(matched),
        "tools": [
            {
                "name": t.tool_name,
                "original_name": t.utcp_tool.name,
                "description": t.description,
            }
            for t in matched
        ],
    }


@tool
def utcp_call_tool(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    adapter_id: str = "default",
) -> Dict[str, Any]:
    """Invoke a UTCP tool by name through a registered UTCP adapter.

    Args:
        tool_name: Name of the UTCP tool (original or Bedrock-sanitized name).
        arguments: Dictionary of tool arguments.
        adapter_id: Identifier of the UTCP adapter (default "default").
    """
    adapter = _ACTIVE_ADAPTERS.get(adapter_id)
    if adapter is None:
        return {"status": "error", "error": f"UTCP adapter '{adapter_id}' is not registered. Call utcp_register_manual first."}
    tool_obj = adapter.get_tool(tool_name)
    target_name = tool_obj.utcp_tool.name if tool_obj is not None else tool_name
    result = _run_coro(adapter.call_tool(target_name, arguments or {}))
    return {"status": "success", "tool_name": target_name, "result": result}


@tool
def utcp(
    action: str = "list",
    adapter_id: str = "default",
    manual_call_templates: Optional[List[Dict[str, Any]]] = None,
    query: str = "",
    tool_name: str = "",
    arguments: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Unified UTCP gateway tool (`register`, `list`, `search`, `call`, `stop`).

    Args:
        action: Action to perform ("register", "list", "search", "call", "stop").
        adapter_id: UTCP adapter session ID.
        manual_call_templates: Call templates when action="register".
        query: Search query when action="search".
        tool_name: Target UTCP tool name when action="call".
        arguments: Tool input dictionary when action="call".
    """
    act = (action or "list").strip().lower()
    if act == "register":
        return utcp_register_manual(adapter_id=adapter_id, manual_call_templates=manual_call_templates)
    if act == "list":
        return utcp_list_tools(adapter_id=adapter_id)
    if act == "search":
        return utcp_search_tools(query=query, adapter_id=adapter_id)
    if act == "call":
        return utcp_call_tool(tool_name=tool_name, arguments=arguments, adapter_id=adapter_id)
    if act == "stop":
        adapter = _ACTIVE_ADAPTERS.pop(adapter_id, None)
        if adapter is not None:
            _run_coro(adapter.stop())
        return {"status": "success", "adapter_id": adapter_id, "stopped": adapter is not None}
    return {"status": "error", "error": f"Unknown UTCP action: {action}"}


__all__ = [
    "UtcpToolAdapter",
    "UtcpAgentTool",
    "UtcpToolAdapterError",
    "format_tool_name_for_bedrock",
    "create_utcp_adapter",
    "utcp",
    "utcp_register_manual",
    "utcp_list_tools",
    "utcp_search_tools",
    "utcp_call_tool",
]
