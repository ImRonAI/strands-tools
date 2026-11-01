"""List OSMO compute pools."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_pool_list(mode: str = "used") -> dict:
    """List compute pools the active profile can submit to.

    Args:
        mode: ``"used"`` (default - shows used/total GPU counts) or
              ``"free"`` (shows what's free right now). Free mode is the
              right call when you're about to submit.

    Effective availability = ``min(Quota Free, Total Free)``. If
    ``Quota Free == 0`` but ``Total Free > 0``, you can still submit with
    ``--priority LOW`` (preemptible).
    """
    args = ["pool", "list"]
    if mode and mode != "used":
        args += ["--mode", mode]
    args += ["--format-type", "json"]
    proc = osmo_run(*args, parse_json=True, timeout_s=30)
    return proc_result(proc, success_text=f"pool list (mode={mode})")
