"""Show the user's profiles and visible pools."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_profile_list() -> dict:
    """Show the user's profiles, current active profile, and pool visibility."""
    proc = osmo_run(
        "profile", "list", "--format-type", "json",
        parse_json=True, timeout_s=20,
    )
    return proc_result(proc, success_text="profile list")
