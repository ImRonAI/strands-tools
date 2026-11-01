"""Describe a single task."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_task_describe(workflow_id: str, task: str) -> dict:
    """Show full metadata, resources, exit code, and dashboard URLs for one task."""
    if not workflow_id or not task:
        return err("workflow_id and task are required")
    proc = osmo_run(
        "task", "describe", "--workflow", workflow_id, "--task", task,
        "--format-type", "json",
        parse_json=True, timeout_s=30,
    )
    return proc_result(proc, success_text=f"task {workflow_id}/{task}")
