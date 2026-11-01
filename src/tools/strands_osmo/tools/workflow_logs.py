"""Fetch logs for a running or completed workflow."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_workflow_logs(
    workflow_id: str,
    task: str = "",
    follow: bool = False,
    tail: int = 200,
) -> dict:
    """Fetch logs for a workflow (or one of its tasks).

    Args:
        workflow_id: Workflow UUID.
        task: Restrict to a single task name.
        follow: Stream logs (blocks). Off by default - agents should poll.
        tail: Max lines to return.
    """
    if not workflow_id:
        return err("workflow_id is required")
    args = ["workflow", "logs", workflow_id]
    if task:
        args += ["--task", task]
    if follow:
        args += ["--follow"]
    if tail:
        args += ["--tail", str(tail)]
    timeout = 600 if follow else 60
    proc = osmo_run(*args, timeout_s=timeout)
    return proc_result(proc, success_text=f"logs for {workflow_id}")
