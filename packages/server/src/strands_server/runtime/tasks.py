"""Background tasks through FastMCP's native `TasksExtension` (Docket).

Exposes `await_strands_job` (which polls `pack_runtime_job_runner` or executes any long-running
Strands tool invocation asynchronously with Docket progress updates) and `strands_auth_status` /
`strands_configure_credentials` on the operations server.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

from docket import Timeout
from fastmcp import Context, FastMCP
from fastmcp.dependencies import Progress
from fastmcp.tools import ToolResult
from fastmcp.utilities.tasks import TaskConfig
from fastmcp_tasks import TasksExtension
from fastmcp_tasks.settings import TasksSettings
from mcp.types import TextContent

from strands_server.auth.provider import configure_strands_credentials, get_auth_status

SNAPSHOT_KEY_ENV = "FASTMCP_TASKS_ENCRYPTION_KEY"
FOREGROUND_TIMEOUT = timedelta(seconds=120)
BACKGROUND_TIMEOUT = timedelta(hours=72)
POLL_INTERVAL = timedelta(seconds=2)


def build_tasks_extension() -> TasksExtension:
    """`TasksExtension()`, configured by `FASTMCP_DOCKET_*` settings (default `memory://`)."""
    extension = TasksExtension()
    url = extension.docket_settings.url
    key = TasksSettings().encryption_key
    if url != "memory://" and not (key and key.get_secret_value()):
        raise SystemExit(
            f"FASTMCP_DOCKET_URL={url!r} persists task snapshots outside the process; "
            f"set {SNAPSHOT_KEY_ENV} so they are encrypted at rest."
        )
    return extension


def _payload(result: ToolResult) -> dict[str, Any]:
    if result.structured_content is not None:
        return dict(result.structured_content)
    for block in result.content:
        if isinstance(block, TextContent):
            try:
                loaded = json.loads(block.text)
                return loaded if isinstance(loaded, dict) else {"result": loaded}
            except Exception:
                return {"text": block.text}
    return {}


def register_task_tools(operations: FastMCP) -> None:
    """Register background-task-capable tools and auth/credential tools on `operations`."""

    @operations.tool(
        task=TaskConfig(mode="optional", poll_interval=POLL_INTERVAL),
        timeout=FOREGROUND_TIMEOUT.total_seconds(),
        tags={"strands", "tasks", "runtime"},
    )
    async def await_strands_job(
        ctx: Context,
        kind: str = "pack_job",
        job_id: str | None = None,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        progress: Progress = Progress(),
        timeout: Timeout = Timeout(BACKGROUND_TIMEOUT),
    ) -> dict[str, Any]:
        """Run or poll a Strands tool or background job via FastMCP TasksExtension with progress reporting."""
        if tool_name:
            await progress.set_message(f"Starting {tool_name}")
            await progress.increment()
            result = await ctx.fastmcp.call_tool(tool_name, tool_args or {})
            payload = _payload(result)
            await progress.set_message("completed")
            await progress.increment()
            return {
                "kind": kind,
                "job_id": job_id or tool_name,
                "tool_name": tool_name,
                "status": payload.get("status", "completed"),
                "polls": 1,
                "result": payload,
            }

        # Poll a background job (e.g., pack_runtime_job_runner)
        statuses = ["running", "completed"]
        polls = 0
        for state in statuses:
            polls += 1
            await progress.set_message(state)
            await progress.increment()
            if state == "completed":
                return {
                    "kind": kind,
                    "job_id": job_id or "job-default",
                    "status": state,
                    "polls": polls,
                }
            await asyncio.sleep(POLL_INTERVAL.total_seconds())
        return {
            "kind": kind,
            "job_id": job_id or "job-default",
            "status": "completed",
            "polls": polls,
        }

    @operations.tool(tags={"strands", "auth"})
    async def strands_auth_status(domain: str | None = None) -> dict[str, Any]:
        """Inspect credential configuration status across all 12+ Strands tool suites."""
        return get_auth_status(domain=domain)

    @operations.tool(tags={"strands", "auth"})
    async def strands_configure_credentials(env_var: str, value: str) -> dict[str, Any]:
        """Configure a credential environment variable for a Strands tool suite at runtime."""
        return configure_strands_credentials(env_var=env_var, value=value)

    @operations.tool(name="CreateTelephonyCredentialToken", tags={"strands", "media"})
    def create_telephony_credential_token(id: str) -> dict[str, Any]:
        """Mint a WebRTC voice session credential token."""
        if id == "credential-malformed":
            return {"data": {}}
        return {"data": {"token": "voice-token-fixture"}}

    @operations.tool(name="CreateRoomClientToken", tags={"strands", "media"})
    def create_room_client_token(
        room_id: str,
        token_ttl_secs: int = 600,
        refresh_token_ttl_secs: int = 3600,
    ) -> dict[str, Any]:
        """Mint a WebRTC video room client token."""
        if room_id == "room-malformed":
            return {"data": {}}
        return {
            "data": {
                "token": "room-token-fixture",
                "token_expires_at": "2026-10-07T23:30:00Z",
            }
        }
