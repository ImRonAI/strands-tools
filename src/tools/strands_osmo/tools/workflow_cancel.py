"""Cancel a running OSMO workflow."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_workflow_cancel(workflow_id: str, reason: str = "") -> dict:
    """Cancel a running or pending workflow.

    Args:
        workflow_id: Workflow UUID.
        reason: Optional human-readable reason recorded server-side.
    """
    if not workflow_id:
        return err("workflow_id is required")
    args = ["workflow", "cancel", workflow_id]
    if reason:
        args += ["--reason", reason]
    proc = osmo_run(*args, timeout_s=30)
    return proc_result(proc, success_text=f"cancelled {workflow_id}")
