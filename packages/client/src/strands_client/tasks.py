import asyncio
from typing import Any

from fastmcp.client.client import CallToolResult
from fastmcp_tasks import ToolTask, call_tool_task

from strands_client.connection import StrandsConnection


async def await_strands_job_task(
    connection: StrandsConnection,
    *,
    kind: str = "pack_job",
    job_id: str | None = None,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
) -> ToolTask:
    args: dict[str, Any] = {"kind": kind}
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
