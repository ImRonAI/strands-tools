"""Open a remote shell inside a running OSMO task."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_workflow_exec(workflow_id: str, task: str, command: str = "bash -lc 'echo hello'") -> dict:
    """Run a one-shot command inside a running task's container.

    Note: Truly interactive sessions (PTY) aren't agent-friendly. This tool
    runs ``osmo workflow exec ... -- <command>`` and returns its output. For
    debugging only.

    Args:
        workflow_id: Workflow UUID.
        task: Task name to attach to (must be RUNNING).
        command: Shell command to run inside the container.
    """
    if not workflow_id or not task:
        return err("workflow_id and task are required")
    args = ["workflow", "exec", workflow_id, "--task", task, "--", "bash", "-lc", command]
    proc = osmo_run(*args, timeout_s=120)
    return proc_result(proc, success_text=f"exec on {workflow_id}/{task}")
