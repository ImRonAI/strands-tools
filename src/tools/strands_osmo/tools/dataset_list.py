"""List versioned datasets."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_dataset_list(name: str = "", tag: str = "", limit: int = 100) -> dict:
    """List versioned datasets, optionally filtered by name or tag.

    Args:
        name: Dataset name filter.
        tag: Tag filter (e.g. ``"latest"``).
        limit: Max results.
    """
    args = ["dataset", "list", "--format-type", "json"]
    if name:
        args += ["--name", name]
    if tag:
        args += ["--tag", tag]
    if limit:
        args += ["--limit", str(limit)]
    proc = osmo_run(*args, parse_json=True, timeout_s=60)
    return proc_result(proc, success_text="dataset list")
