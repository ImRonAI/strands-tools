# pyright: strict
import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from fastmcp.client.client import CallToolResult
import fastmcp_tasks
from fastmcp_tasks import ToolTask

from strands_client.connection import StrandsConnection


async def call_tool_task(
    client: StrandsConnection,
    name: str,
    arguments: dict[str, object] | None = None,
    *,
    timeout: float | int | None = None,
    raise_on_error: bool = True,
    version: str | None = None,
    meta: dict[str, object] | None = None,
) -> ToolTask:
    raw_fn = cast(
        Callable[..., Awaitable[ToolTask]],
        getattr(fastmcp_tasks, "call_tool_task"),
    )
    return await raw_fn(
        client,
        name,
        arguments,
        timeout=timeout,
        raise_on_error=raise_on_error,
        version=version,
        meta=meta,
    )


async def await_strands_job_task(
    connection: StrandsConnection,
    *,
    kind: str = "pack_job",
    job_id: str | None = None,
    tool_name: str | None = None,
    tool_args: dict[str, object] | None = None,
) -> ToolTask:
    args: dict[str, object] = {"kind": kind}
    if job_id is not None:
        args["job_id"] = job_id
    if tool_name is not None:
        args["tool_name"] = tool_name
    if tool_args is not None:
        args["tool_args"] = tool_args
    return await call_tool_task(
        connection,
        "await_strands_job",
        args,
    )


async def wait_for(
    task: ToolTask,
    *,
    timeout: float = 72 * 3600.0,
) -> CallToolResult:
    """Drive the task to its result, bounded by `timeout`."""
    return await asyncio.wait_for(task.result(), timeout)


__all__ = [
    "ToolTask",
    "await_strands_job_task",
    "call_tool_task",
    "wait_for",
]
