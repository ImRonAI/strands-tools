"""Publish a workflow YAML as a reusable app."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_app_create(workflow_yaml: str, name: str, version: str = "0.1.0") -> dict:
    """Promote a workflow YAML to a reusable app spec.

    Args:
        workflow_yaml: Path to the YAML.
        name: App name.
        version: SemVer (default ``0.1.0``).
    """
    p = Path(workflow_yaml).expanduser()
    if not p.exists():
        return err(f"workflow YAML not found: {p}")
    args = [
        "app", "create", str(p),
        "--name", name,
        "--version", version,
    ]
    proc = osmo_run(*args, timeout_s=60)
    return proc_result(proc, success_text=f"app {name}@{version} created")
