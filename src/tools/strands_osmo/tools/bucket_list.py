"""List storage buckets visible to the user."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_bucket_list() -> dict:
    """List object-storage buckets configured for the user's pools."""
    proc = osmo_run(
        "bucket", "list", "--format-type", "json",
        parse_json=True, timeout_s=30,
    )
    return proc_result(proc, success_text="bucket list")
