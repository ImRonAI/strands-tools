"""Show status of a single OSMO workflow."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_workflow_status(workflow_id: str) -> dict:
    """Show full status, dashboard URLs, and per-task state for a workflow.

    Args:
        workflow_id: The workflow UUID (from ``osmo_workflow_submit`` or list).
    """
    if not workflow_id:
        return err("workflow_id is required")
    proc = osmo_run(
        "workflow", "describe", workflow_id, "--format-type", "json",
        parse_json=True, timeout_s=30,
    )
    return proc_result(proc, success_text=f"status for {workflow_id}")
