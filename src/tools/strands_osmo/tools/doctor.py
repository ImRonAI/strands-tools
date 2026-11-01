"""Diagnose the strands-osmo / OSMO CLI environment."""
from __future__ import annotations

import os
import shutil

from strands import tool

from ._common import ok, osmo_run


@tool
def osmo_doctor() -> dict:
    """Inspect the local environment: osmo binary, version, login state, default pool.

    Returns a structured snapshot useful for troubleshooting agents."""
    osmo_bin = os.getenv("STRANDS_OSMO_BIN", "osmo")
    osmo_path = shutil.which(osmo_bin)
    info: dict = {
        "osmo_bin": osmo_bin,
        "osmo_path": osmo_path,
        "osmo_present": osmo_path is not None,
        "env": {
            "OSMO_HOST": os.getenv("OSMO_HOST"),
            "OSMO_PROFILE": os.getenv("OSMO_PROFILE"),
            "STRANDS_OSMO_BIN": os.getenv("STRANDS_OSMO_BIN"),
        },
    }
    if not osmo_path:
        info["fix"] = (
            "Install OSMO CLI: "
            "curl -fsSL https://raw.githubusercontent.com/NVIDIA/OSMO/main/install.sh | bash"
        )
        return ok(text="osmo CLI not found", data=info)

    ver = osmo_run("version", timeout_s=15)
    info["version_ok"] = bool(ver.get("ok"))
    info["version_stdout"] = (ver.get("stdout") or "").strip()[:500]
    if not ver.get("ok"):
        info["version_stderr"] = (ver.get("stderr") or "").strip()[:500]

    # Profile probe - also tells us whether the user is logged in.
    prof = osmo_run("profile", "list", "--format-type", "json", timeout_s=20)
    info["profile_ok"] = bool(prof.get("ok"))
    if not prof.get("ok"):
        stderr = (prof.get("stderr") or "")
        info["logged_in"] = "auth" not in stderr.lower() and "token" not in stderr.lower()
        info["profile_stderr"] = stderr.strip()[:500]
    else:
        info["logged_in"] = True

    summary = (
        f"osmo: {'OK' if info['osmo_present'] else 'MISSING'} ({osmo_path})\n"
        f"version: {'OK' if info.get('version_ok') else 'FAIL'}\n"
        f"profile: {'OK' if info.get('profile_ok') else 'FAIL (login?)'}"
    )
    return ok(text=summary, data=info)
