"""Install/upgrade the Zero compiler binary."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

INSTALL_URL = "https://zerolang.ai/install.sh"


def install_zero(install_dir: str | None = None) -> dict:
    """Run the official Zero install script.

    Args:
        install_dir: Override install dir (defaults to ~/.zero/bin via the script).
    """
    env = os.environ.copy()
    if install_dir:
        env["ZERO_INSTALL_DIR"] = install_dir

    try:
        # Pipe curl into sh, but capture both for the agent.
        curl = subprocess.run(
            ["curl", "-fsSL", INSTALL_URL],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if curl.returncode != 0:
            return {"ok": False, "error": f"curl failed: {curl.stderr}"}

        sh = subprocess.run(
            ["sh", "-s"],
            input=curl.stdout,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        return {
            "ok": sh.returncode == 0,
            "exit_code": sh.returncode,
            "stdout": sh.stdout,
            "stderr": sh.stderr,
            "install_dir": env.get("ZERO_INSTALL_DIR")
            or str(Path.home() / ".zero" / "bin"),
        }
    except FileNotFoundError as e:
        return {"ok": False, "error": f"missing required command: {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "install timed out"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def cli() -> int:
    """Entry point for `strands-zero-install` script."""
    install_dir = sys.argv[1] if len(sys.argv) > 1 else None
    result = install_zero(install_dir)
    if result["ok"]:
        print(result.get("stdout", ""))
        bin_dir = result.get("install_dir", "~/.zero/bin")
        print(f"\n✓ Zero installed. Add to PATH:\n  export PATH=\"{bin_dir}:$PATH\"")
        return 0
    print(f"✗ Install failed: {result.get('error') or result.get('stderr')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(cli())
