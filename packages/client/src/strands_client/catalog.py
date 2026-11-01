from fastmcp.client.client import CallToolResult
from mcp.types import Tool

from strands_client.connection import StrandsConnection

MODEL_VISIBLE_TOOLS = (
    "execute",
    "generate_prefab_ui",
    "get_schema",
    "search",
)


async def list_model_visible_tools(connection: StrandsConnection) -> list[Tool]:
    tools_by_name = {tool.name: tool for tool in await connection.list_tools()}
    return [
        tools_by_name[name]
        for name in MODEL_VISIBLE_TOOLS
        if name in tools_by_name
    ]


async def search(connection: StrandsConnection, query: str) -> CallToolResult:
    return await connection.call_tool("search", {"query": query})


async def get_schema(
    connection: StrandsConnection, tools: list[str]
) -> CallToolResult:
    return await connection.call_tool("get_schema", {"tools": tools})


async def execute(connection: StrandsConnection, code: str) -> CallToolResult:
    return await connection.call_tool("execute", {"code": code})
