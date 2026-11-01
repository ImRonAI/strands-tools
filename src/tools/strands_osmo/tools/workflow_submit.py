"""Submit an OSMO workflow YAML to a pool."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_workflow_submit(
    workflow_yaml: str,
    pool: str,
    set_vars: dict | None = None,
    priority: str = "",
    name: str = "",
    extra_args: list[str] | None = None,
) -> dict:
    """Submit a workflow YAML to a compute pool.

    Args:
        workflow_yaml: Path to a workflow YAML file (must exist).
        pool: Pool name from ``osmo_pool_list``.
        set_vars: Jinja overrides, e.g. ``{"num_gpu": 4}``. Each becomes
                  ``--set key=value``.
        priority: ``"LOW"`` to bypass quota using idle capacity (preemptible),
                  or ``""`` for default priority.
        name: Optional workflow name (defaults to spec ``workflow.name``).
        extra_args: Additional CLI flags passed verbatim.

    Returns the workflow ID(s) the server allocated. Use
    ``osmo_workflow_status(workflow_id=...)`` to track progress.
    """
    p = Path(workflow_yaml).expanduser()
    if not p.exists():
        return err(f"workflow YAML not found: {p}")
    if not pool:
        return err("pool is required (use osmo_pool_list to discover pools)")

    args: list[str] = ["workflow", "submit", str(p), "--pool", pool]
    if set_vars:
        for k, v in set_vars.items():
            args += ["--set", f"{k}={v}"]
    if priority:
        args += ["--priority", priority.upper()]
    if name:
        args += ["--name", name]
    if extra_args:
        args += list(extra_args)

    proc = osmo_run(*args, timeout_s=120)
    return proc_result(
        proc,
        success_text=f"submitted to pool={pool}",
        fail_text="workflow submit failed",
    )
