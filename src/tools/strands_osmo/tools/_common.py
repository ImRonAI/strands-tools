"""Shared helpers for strands-osmo tools.

Tool return format (Strands @tool-compatible):
    {
        "status": "success" | "error",
        "content": [
            {"text": "..."},
            {"json": {...}},
        ],
    }

Design:
    OSMO ships a production CLI (`osmo`). All tools shell out to that binary
    rather than re-binding to internal service modules. This makes tools
    version-tolerant and lets operators run the same commands by hand.
"""
from __future__ import annotations

import json as _json
import os
import shutil
import subprocess


# ── ToolResult builders ──────────────────────────────────────────────────
def ok(text: str = "", data: dict | None = None) -> dict:
    """Build a success ToolResult."""
    content: list[dict] = []
    if text:
        content.append({"text": text})
    if data is not None:
        content.append({"json": data})
    if not content:
        content.append({"text": "ok"})
    return {"status": "success", "content": content}


def err(msg: str, data: dict | None = None) -> dict:
    """Build an error ToolResult."""
    content: list[dict] = [{"text": f"❌ {msg}"}]
    if data is not None:
        content.append({"json": data})
    return {"status": "error", "content": content}


# ── osmo CLI runner ──────────────────────────────────────────────────────
_OSMO_BIN = os.getenv("STRANDS_OSMO_BIN", "osmo")


def osmo_available() -> bool:
    """Return True if the `osmo` binary is on PATH."""
    return shutil.which(_OSMO_BIN) is not None


def osmo_run(
    *args: str,
    timeout_s: int = 300,
    env: dict | None = None,
    cwd: str | None = None,
    extra_env: dict | None = None,
    parse_json: bool = False,
) -> dict:
    """Invoke `osmo <args...>` and return a normalized proc dict.

    Args:
        *args: Arguments passed to `osmo` (e.g. `osmo_run("pool", "list")`).
        timeout_s: Subprocess timeout in seconds.
        env: Replace environment entirely.
        extra_env: Merge into environment.
        cwd: Working directory.
        parse_json: If True, attempt to parse stdout as JSON into `proc["data"]`.

    Returns:
        {"ok": bool, "returncode": int, "stdout": str, "stderr": str,
         "cmd": str, "data": Any | None}
    """
    if not osmo_available():
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": f"`{_OSMO_BIN}` not found on PATH. Install: "
                      f"curl -fsSL https://raw.githubusercontent.com/NVIDIA/OSMO/main/install.sh | bash",
            "cmd": f"{_OSMO_BIN} " + " ".join(args),
            "data": None,
        }

    cmd = [_OSMO_BIN, *[str(a) for a in args]]
    run_env = os.environ.copy() if env is None else dict(env)
    if extra_env:
        run_env.update(extra_env)

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=cwd,
            env=run_env,
        )
        result: dict = {
            "ok": p.returncode == 0,
            "returncode": p.returncode,
            "stdout": p.stdout[-16000:],
            "stderr": p.stderr[-4000:],
            "cmd": " ".join(cmd),
            "data": None,
        }
        if parse_json and p.returncode == 0 and p.stdout.strip():
            try:
                result["data"] = _json.loads(p.stdout)
            except _json.JSONDecodeError:
                result["data"] = None
        return result
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"timeout after {timeout_s}s",
            "cmd": " ".join(cmd),
            "data": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"{type(e).__name__}: {e}",
            "cmd": " ".join(cmd),
            "data": None,
        }


def proc_result(proc: dict, success_text: str = "", fail_text: str = "") -> dict:
    """Convert an osmo_run output into a ToolResult."""
    if proc.get("ok"):
        tail = proc.get("stdout", "").strip()
        text = success_text or "ok"
        if tail:
            text = f"{text}\n\n{tail}" if success_text else tail
        out_data = {
            "cmd": proc.get("cmd"),
            "returncode": proc.get("returncode"),
        }
        if proc.get("data") is not None:
            out_data["parsed"] = proc["data"]
        return ok(text=text[:8000], data=out_data)
    stderr_tail = (proc.get("stderr") or "").strip()
    return err(
        fail_text or f"exit {proc.get('returncode')}: {stderr_tail[-400:] or 'no stderr'}",
        data={"cmd": proc.get("cmd"), "stderr": stderr_tail[-1000:]},
    )


def add_format_json(args: list[str]) -> list[str]:
    """Append --format-type json if not already present (for parsing)."""
    if any(a.startswith("--format-type") for a in args):
        return args
    return args + ["--format-type", "json"]
