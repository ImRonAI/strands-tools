# pyright: strict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

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
    raw: Mapping[str, object]
    result: CallToolResult

    @property
    def prefab_version(self) -> str:
        prefab = cast(Mapping[str, object], self.raw["$prefab"])
        return cast(str, prefab["version"])

    @property
    def view(self) -> Mapping[str, object]:
        return cast(Mapping[str, object], self.raw["view"])

    @property
    def tool_names(self) -> tuple[str, ...]:
        meta = self.raw.get("_meta")
        if not isinstance(meta, Mapping):
            return ()
        typed_meta = cast(Mapping[str, object], meta)
        fastmcp = typed_meta.get("fastmcp")
        if not isinstance(fastmcp, Mapping):
            return ()
        typed_fastmcp = cast(Mapping[str, object], fastmcp)
        names = typed_fastmcp.get("toolNames")
        if isinstance(names, Mapping):
            typed_names_map = cast(Mapping[object, object], names)
            return tuple(name for name in typed_names_map if isinstance(name, str))
        if not isinstance(names, list):
            return ()
        typed_names_list = cast(list[object], names)
        return tuple(name for name in typed_names_list if isinstance(name, str))


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
