# pyright: strict
"""App-only backend tools that execute Strands tools through FastMCP.

Each helper registers a `@app.tool()` (visibility `["app"]`) on a `FastMCPApp`. The body
calls `await ctx.fastmcp.call_tool(<tool name>, args)` so all tool executions flow through
the unified FastMCP server catalog.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeGuard

from fastmcp import Context
from fastmcp.apps.app import FastMCPApp
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from pydantic import BaseModel

Paging = Literal["page", "cursor", "none"]
Backend = Callable[..., object]
Payload = dict[str, object]


def _is_str_mapping(val: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(val, Mapping)


def _is_obj_sequence(val: object) -> TypeGuard[Sequence[object]]:
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes))


@dataclass(frozen=True)
class ColumnSpec:
    """One DataTable column bound to a field of the listed resource."""

    key: str
    header: str
    format: str | None = None


def _empty_static_args() -> dict[str, object]:
    return {}


@dataclass(frozen=True)
class ListSpec:
    """How a workspace lists its primary resource through a registered Strands tool."""

    tool: str
    data_path: tuple[str, ...] = ("rows",)
    columns: tuple[ColumnSpec, ...] = ()
    paging: Paging = "none"
    static_args: Mapping[str, object] = field(default_factory=_empty_static_args)


def _payload(result: ToolResult) -> Payload:
    if result.structured_content is not None:
        return dict(result.structured_content)
    if result.content:
        first = result.content[0]
        text = getattr(first, "text", None)
        if isinstance(text, str) and text:
            try:
                loaded: object = json.loads(text)
                if _is_str_mapping(loaded):
                    return dict(loaded)
                return {"result": loaded}
            except Exception:
                return {"text": text}
    return {}


def _register(app: FastMCPApp, fn: Backend, *, name: str, description: str) -> Backend:
    """Register `fn` under `name`; `CallTool(fn)` resolves through `fn.__name__`, so align it."""
    fn.__name__ = name
    fn.__qualname__ = name
    return app.tool(fn, name=name, description=description)


def _walk(payload: Payload, path: tuple[str, ...]) -> list[object]:
    node: object = payload
    for part in path:
        if not _is_str_mapping(node):
            return []
        node = node.get(part)
    if _is_obj_sequence(node):
        return list(node)
    if node is not None:
        return [dict(node)] if _is_str_mapping(node) else [{"value": str(node)}]
    if payload:
        return [payload]
    return []


def register_list_backend(app: FastMCPApp, *, name: str, spec: ListSpec) -> Backend:
    """Register a list backend returning `{"rows": [...], "meta": {...}}`."""

    async def _run(ctx: Context, args: dict[str, object]) -> Payload:
        result = await ctx.fastmcp.call_tool(spec.tool, {**spec.static_args, **args})
        payload = _payload(result)
        return {"rows": _walk(payload, spec.data_path), "meta": payload.get("meta", {})}

    if spec.paging == "page":

        async def list_by_page(
            ctx: Context, page_number: int = 1, page_size: int = 25
        ) -> Payload:
            _ = page_number
            return await _run(ctx, {"limit": page_size})

        return _register(app, list_by_page, name=name, description=f"List via {spec.tool}")

    if spec.paging == "cursor":

        async def list_by_cursor(
            ctx: Context, cursor: str | None = None, limit: int = 25
        ) -> Payload:
            args: dict[str, object] = {"limit": limit}
            if cursor:
                args["cursor"] = cursor
            return await _run(ctx, args)

        return _register(app, list_by_cursor, name=name, description=f"List via {spec.tool}")

    async def list_all(ctx: Context) -> Payload:
        return await _run(ctx, {})

    return _register(app, list_all, name=name, description=f"List via {spec.tool}")


def register_detail_backend(
    app: FastMCPApp,
    *,
    name: str,
    tool: str,
    id_param: str,
    static_args: Mapping[str, object] | None = None,
) -> Backend:
    """Register a detail backend: `resource_id` -> Strands tool."""
    extras = dict(static_args or {})

    async def detail(ctx: Context, resource_id: str) -> Payload:
        return _payload(await ctx.fastmcp.call_tool(tool, {**extras, id_param: resource_id}))

    return _register(app, detail, name=name, description=f"Retrieve via {tool}")


def register_form_backend(
    app: FastMCPApp, *, name: str, tool: str, model: type[BaseModel]
) -> Backend:
    """Register a form execution backend fed by `Form.from_model(model)` (`arguments={"data": ...}`)."""

    async def create(ctx: Context, data: BaseModel) -> Payload:
        return _payload(await ctx.fastmcp.call_tool(tool, data.model_dump(exclude_none=True)))

    create.__annotations__["data"] = model
    return _register(app, create, name=name, description=f"Run {tool}")


def register_confirmed_backend(
    app: FastMCPApp,
    *,
    name: str,
    tool: str,
    id_param: str,
    extra_args: Mapping[str, object] | None = None,
) -> Backend:
    """Register a destructive/privileged action that runs only when `confirm == resource_id`."""
    extras = dict(extra_args or {})

    async def confirmed(ctx: Context, resource_id: str, confirm: str) -> Payload:
        if confirm != resource_id:
            raise ToolError(
                f"Confirmation does not match: type the resource id {resource_id!r} to run {tool}."
            )
        return _payload(await ctx.fastmcp.call_tool(tool, {id_param: resource_id, **extras}))

    return _register(app, confirmed, name=name, description=f"Confirmed {tool}")
