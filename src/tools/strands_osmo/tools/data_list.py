"""List objects in an OSMO bucket prefix."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_data_list(prefix: str = "", bucket: str = "", limit: int = 100) -> dict:
    """List objects in a storage prefix.

    Args:
        prefix: Object key prefix to list (default: bucket root).
        bucket: Override bucket name.
        limit: Max objects to return.
    """
    args = ["data", "list"]
    if prefix:
        args += [prefix]
    if bucket:
        args += ["--bucket", bucket]
    if limit:
        args += ["--limit", str(limit)]
    args += ["--format-type", "json"]
    proc = osmo_run(*args, parse_json=True, timeout_s=60)
    return proc_result(proc, success_text="data list")
