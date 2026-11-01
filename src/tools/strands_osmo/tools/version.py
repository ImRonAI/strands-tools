"""Report OSMO client + server version."""
from __future__ import annotations

from strands import tool

from ._common import osmo_run, proc_result


@tool
def osmo_version() -> dict:
    """Print the OSMO client (and, if reachable, server) version."""
    proc = osmo_run("version", timeout_s=15)
    return proc_result(proc, success_text="osmo version")
