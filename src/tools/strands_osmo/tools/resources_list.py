"""List available compute resources."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_resources_list() -> dict:
    """List available GPU/CPU/memory profiles across pools."""
    proc = osmo_run(
        "resources", "list", "--format-type", "json",
        parse_json=True, timeout_s=30,
    )
    return proc_result(proc, success_text="resources list")
