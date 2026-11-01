"""Launch the upstream OmniVoice Gradio demo (background process)."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path

from strands import tool

from .._common import err, ok

_PID_FILE = Path("/tmp/strands-omnivoice-demo.pid")
_LOG_FILE = Path("/tmp/strands-omnivoice-demo.log")


def _read_pid() -> int | None:
    if not _PID_FILE.exists():
        return None
    try:
        pid = int(_PID_FILE.read_text().strip())
    except Exception:  # noqa: BLE001
        return None
    # Liveness check
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        try:
            _PID_FILE.unlink()
        except Exception:  # noqa: BLE001
            pass
        return None


@tool
def omnivoice_demo_serve(
    action: str = "start",
    ip: str = "0.0.0.0",
    port: int = 8001,
    model_id: str = "",
) -> dict:
    """Manage the upstream ``omnivoice-demo`` Gradio web UI as a background process.

    Actions:
      - ``start``: spawn ``omnivoice-demo`` on ``ip:port`` (returns immediately).
      - ``stop``: kill the running demo, if any.
      - ``status``: report whether the demo process is alive.
      - ``logs``: tail the demo log file.

    Args:
        action: One of ``start`` / ``stop`` / ``status`` / ``logs``.
        ip: Bind address (default: ``0.0.0.0``).
        port: Bind port (default: ``8001``).
        model_id: Optional model override (HF repo or local path).
    """
    action = action.lower()

    if action == "status":
        pid = _read_pid()
        return ok(
            text=("running" if pid else "not running"),
            data={"alive": pid is not None, "pid": pid, "log": str(_LOG_FILE)},
        )

    if action == "logs":
        if not _LOG_FILE.exists():
            return ok(text="(no log yet)", data={"log": str(_LOG_FILE)})
        tail = _LOG_FILE.read_text(errors="ignore")[-4000:]
        return ok(text=tail, data={"log": str(_LOG_FILE)})

    if action == "stop":
        pid = _read_pid()
        if pid is None:
            return ok(text="demo is not running", data={"alive": False})
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as e:
            return err(f"failed to kill pid {pid}: {e}")
        try:
            _PID_FILE.unlink()
        except Exception:  # noqa: BLE001
            pass
        return ok(text=f"🛑 stopped demo (pid {pid})", data={"pid": pid})

    if action == "start":
        if _read_pid() is not None:
            return err("demo already running — use action='stop' first or check 'status'")
        if not shutil.which("omnivoice-demo"):
            return err(
                "`omnivoice-demo` binary not found on PATH. "
                "Install with `pip install 'strands-omnivoice[demo]'` or `pip install omnivoice gradio`."
            )

        cmd = ["omnivoice-demo", "--ip", ip, "--port", str(port)]
        if model_id:
            cmd += ["--model", model_id]

        log_fh = open(_LOG_FILE, "ab")  # noqa: SIM115
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        _PID_FILE.write_text(str(proc.pid))
        return ok(
            text=f"🌐 demo starting on http://{ip}:{port} (pid {proc.pid}) — tail: {_LOG_FILE}",
            data={"pid": proc.pid, "url": f"http://{ip}:{port}", "log": str(_LOG_FILE)},
        )

    return err(f"unknown action: {action!r}. Valid: start, stop, status, logs")
