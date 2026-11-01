"""List tasks of a workflow."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_task_list(workflow_id: str) -> dict:
    """List all tasks (and their status) inside a workflow."""
    if not workflow_id:
        return err("workflow_id is required")
    proc = osmo_run(
        "task", "list", "--workflow", workflow_id, "--format-type", "json",
        parse_json=True, timeout_s=30,
    )
    return proc_result(proc, success_text=f"tasks for {workflow_id}")
