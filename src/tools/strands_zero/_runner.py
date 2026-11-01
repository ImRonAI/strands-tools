"""Internal subprocess runner for the `zero` CLI."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_zero_binary() -> Optional[str]:
    """Locate the `zero` binary.

    Search order:
        1. ZERO_BIN env var (explicit override)
        2. `zero` on PATH
        3. ~/.zero/bin/zero (default install dir)
    """
    explicit = os.environ.get("ZERO_BIN")
    if explicit and Path(explicit).exists() and os.access(explicit, os.X_OK):
        return explicit

    on_path = shutil.which("zero")
    if on_path:
        return on_path

    home_bin = Path.home() / ".zero" / "bin" / "zero"
    if home_bin.exists() and os.access(str(home_bin), os.X_OK):
        return str(home_bin)

    return None


def run_zero(
    args: List[str],
    *,
    cwd: Optional[str] = None,
    timeout: int = 120,
    input_text: Optional[str] = None,
    parse_json: bool = False,
) -> Dict[str, Any]:
    """Execute the zero CLI and return a structured result.

    Returns a dict with:
        ok: bool
        exit_code: int
        stdout: str
        stderr: str
        command: list[str]
        json: parsed JSON if parse_json=True and stdout is valid JSON
        error: error message if zero binary missing or timeout
    """
    binary = find_zero_binary()
    if not binary:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "command": ["zero"] + args,
            "error": (
                "zero binary not found. Install with: "
                "curl -fsSL https://zerolang.ai/install.sh | bash "
                "(then add ~/.zero/bin to PATH), or call zero_install()."
            ),
        }

    cmd = [binary] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "command": cmd,
            "error": f"timeout after {timeout}s",
        }
    except Exception as e:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "command": cmd,
            "error": f"{type(e).__name__}: {e}",
        }

    result: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": cmd,
    }

    if parse_json and proc.stdout.strip():
        try:
            result["json"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            # Some commands print non-JSON warnings before JSON; try last line.
            for line in reversed(proc.stdout.splitlines()):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        result["json"] = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue

    return result


def resolve_target(target: Optional[str]) -> Tuple[str, str]:
    """Resolve a Zero source target. Returns (target_arg, label)."""
    if target is None:
        return ("", "(no target)")
    p = Path(target).expanduser()
    if p.exists():
        return (str(p), str(p))
    return (target, target)
