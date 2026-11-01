"""List recent OSMO workflows."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_workflow_list(
    status: str = "",
    pool: str = "",
    limit: int = 50,
    user: str = "",
) -> dict:
    """List recent workflows.

    Args:
        status: Filter by status (e.g. ``"RUNNING"``, ``"FAILED"``).
        pool: Filter by pool name.
        limit: Max results.
        user: Filter by owner username (may require admin role).
    """
    args = ["workflow", "list", "--format-type", "json"]
    if status:
        args += ["--status", status.upper()]
    if pool:
        args += ["--pool", pool]
    if user:
        args += ["--user", user]
    if limit:
        args += ["--limit", str(limit)]
    proc = osmo_run(*args, parse_json=True, timeout_s=30)
    return proc_result(proc, success_text="workflow list")
