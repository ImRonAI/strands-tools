from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from fastmcp.client.client import CallToolResult

from strands_client.catalog import execute
from strands_client.connection import StrandsConnection

WORKSPACE_DOMAINS: tuple[str, ...] = (
    "google",
    "fun_tools",
    "agent_tools",
    "pack",
    "youtube",
    "telegram",
    "zero",
    "utcp",
    "harness",
    "docs",
    "skills",
    "ccxt",
    "inspect",
    "ecosystem",
)


@dataclass(frozen=True)
class WorkspacePayload:
    domain: str
    raw: Mapping[str, Any]
    result: CallToolResult

    @property
    def prefab_version(self) -> str:
        prefab = cast(Mapping[str, Any], self.raw["$prefab"])
        return cast(str, prefab["version"])

    @property
    def view(self) -> Mapping[str, Any]:
        return cast(Mapping[str, Any], self.raw["view"])

    @property
    def tool_names(self) -> tuple[str, ...]:
        meta = self.raw.get("_meta")
        if not isinstance(meta, Mapping):
            return ()
        fastmcp = meta.get("fastmcp")
        if not isinstance(fastmcp, Mapping):
            return ()
        names = fastmcp.get("toolNames")
        if isinstance(names, Mapping):
            return tuple(name for name in names if isinstance(name, str))
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            return ()
        return tuple(names)


async def open_workspace(
    connection: StrandsConnection,
    domain: str,
) -> WorkspacePayload:
    if domain not in WORKSPACE_DOMAINS:
        raise ValueError(f"unknown workspace domain: {domain}")

    result = await execute(
        connection,
        f"return await call_tool('{domain}_workspace', {{}})",
    )
    raw = result.structured_content
    if raw is None or "$prefab" not in raw:
        raise ValueError("not a prefab payload")
    return WorkspacePayload(domain=domain, raw=raw, result=result)
