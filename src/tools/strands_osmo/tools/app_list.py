"""List published OSMO apps."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_app_list(name: str = "", limit: int = 100) -> dict:
    """List published apps (reusable workflow specs).

    Args:
        name: App name filter.
        limit: Max results.
    """
    args = ["app", "list", "--format-type", "json"]
    if name:
        args += ["--name", name]
    if limit:
        args += ["--limit", str(limit)]
    proc = osmo_run(*args, parse_json=True, timeout_s=30)
    return proc_result(proc, success_text="app list")
