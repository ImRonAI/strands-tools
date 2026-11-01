"""Authenticate against the OSMO server."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_login(host: str = "", interactive: bool = True) -> dict:
    """Run ``osmo login`` to authenticate against the OSMO server.

    Args:
        host: OSMO server URL. If empty, uses the configured default.
        interactive: When True, runs the OAuth flow (will print a URL).
                     When False, expects credentials from env (e.g. OSMO_TOKEN).

    Note: Interactive logins block on user action. Prefer pre-issued
    access tokens (``osmo access-token create``) for headless agents.
    """
    if not interactive:
        return err(
            "non-interactive login not supported via this tool. "
            "Use 'osmo access-token create' on a workstation, then export "
            "OSMO_TOKEN for headless agents."
        )
    args = ["login"]
    if host:
        args += ["--host", host]
    proc = osmo_run(*args, timeout_s=180)
    return proc_result(proc, success_text="login flow initiated")
