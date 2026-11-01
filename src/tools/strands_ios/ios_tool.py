"""
📱 strands-ios — iOS device control as a @tool.

One tool, many actions. Wraps pymobiledevice3 (USB mux / RemoteXPC tunnel)
with structured arguments, safety checks, and LLM-friendly responses.

Actions grouped by domain:
  device:  list_devices, select_device, device_info, battery, storage
  syslog:  syslog (live tail, like adb logcat)
  screen:  screenshot, screenrecord_start, screenrecord_stop
  apps:    list_apps, launch, kill, install, uninstall, current_app
  files:   afc_ls, afc_pull, afc_push  (sandboxed unless app-specific)
  crash:   crash_logs, pcap_start, pcap_stop
  ui:      tap, swipe, type_text, press  (requires WebDriverAgent running)
  misc:    open_url, set_location, reboot

iOS 17+ requires a RemoteXPC tunnel (pymobiledevice3 handles it, but may
need `sudo` for the first tunnel creation). This tool surfaces that info
in error messages.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from strands import tool

logger = logging.getLogger("strands_ios")

# ----------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------

class IOSError(RuntimeError):
    pass


# Per-process selected device UDID (overridable per call via `udid=`)
_SELECTED_UDID: Optional[str] = os.getenv("IOS_UDID") or None

# WebDriverAgent URL (for UI automation). Set via env or passed per call.
_WDA_URL: Optional[str] = os.getenv("WDA_URL") or None

# Background syslog/pcap processes keyed by name
_BG_PROCS: Dict[str, subprocess.Popen] = {}


def _pmd3_bin() -> str:
    return os.getenv("PYMOBILEDEVICE3_BIN", "pymobiledevice3")


# ----------------------------------------------------------------------------
# Subprocess helper (wraps `pymobiledevice3` CLI — most reliable path)
# ----------------------------------------------------------------------------

def _run(
    args: List[str],
    udid: Optional[str] = None,
    timeout: int = 30,
    check: bool = False,
    input_data: Optional[str] = None,
    json_out: bool = False,
) -> Dict[str, Any]:
    """Run a pymobiledevice3 CLI command."""
    cmd = [_pmd3_bin()]
    cmd += args
    u = udid or _SELECTED_UDID
    if u:
        cmd += ["--udid", u]

    logger.debug("pmd3: %s", " ".join(shlex.quote(c) for c in cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_data,
        )
    except FileNotFoundError as e:
        raise IOSError(
            f"{_pmd3_bin()} not found — install with: pip install pymobiledevice3"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise IOSError(f"pmd3 command timed out after {timeout}s: {args}") from e

    result = {
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "returncode": proc.returncode,
        "cmd": cmd,
    }
    if check and proc.returncode != 0:
        raise IOSError(f"pmd3 failed ({proc.returncode}): {proc.stderr.strip()}")
    if json_out and proc.returncode == 0 and proc.stdout.strip():
        try:
            result["json"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result["json"] = None
    return result


def _ok(text: str, **extra) -> Dict[str, Any]:
    return {"status": "success", "content": [{"text": text}], **extra}


def _err(text: str) -> Dict[str, Any]:
    return {"status": "error", "content": [{"text": text}]}


# ----------------------------------------------------------------------------
# Device
# ----------------------------------------------------------------------------

def _handle_list_devices() -> Dict[str, Any]:
    r = _run(["usbmux", "list"], json_out=True)
    if r["returncode"] != 0:
        return _err(f"list_devices failed: {r['stderr']}")
    devices = r.get("json") or []
    # Normalize to stable shape
    out = []
    for d in devices:
        out.append({
            "udid": d.get("Identifier") or d.get("SerialNumber") or d.get("udid"),
            "name": d.get("DeviceName") or d.get("Name"),
            "product": d.get("ProductType"),
            "ios": d.get("ProductVersion"),
            "connection": d.get("ConnectionType", "USB"),
        })
    return _ok(f"{len(out)} device(s):\n" + json.dumps(out, indent=2), devices=out)


def _handle_select_device(udid: str) -> Dict[str, Any]:
    global _SELECTED_UDID
    _SELECTED_UDID = udid
    return _ok(f"selected udid: {udid}")


def _handle_device_info(udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["lockdown", "info"], udid=udid, json_out=True)
    if r["returncode"] != 0:
        return _err(f"device_info failed: {r['stderr']}")
    info = r.get("json") or {}
    keys = ["DeviceName", "ProductType", "ProductVersion", "BuildVersion",
            "UniqueDeviceID", "SerialNumber", "HardwareModel", "CPUArchitecture"]
    slim = {k: info.get(k) for k in keys if k in info}
    return _ok(json.dumps(slim, indent=2), info=slim)


def _handle_battery(udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["diagnostics", "battery"], udid=udid, json_out=True)
    if r["returncode"] != 0:
        return _err(f"battery failed: {r['stderr']}")
    return _ok(r["stdout"], data=r.get("json"))


def _handle_storage(udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["apps", "list", "--no-user", "--no-system"], udid=udid, json_out=True)
    # Storage info really lives in lockdown DiskUsage — fall back gracefully
    info = _run(["lockdown", "info"], udid=udid, json_out=True).get("json", {}) or {}
    free = info.get("DiskUsage", {})
    return _ok(json.dumps(free, indent=2) if free else "disk info unavailable", disk=free)


# ----------------------------------------------------------------------------
# Syslog (adb logcat equivalent)
# ----------------------------------------------------------------------------

def _handle_syslog(
    udid: Optional[str],
    lines: int = 50,
    filter_proc: Optional[str] = None,
    timeout: int = 5,
) -> Dict[str, Any]:
    """Capture N lines of syslog then return. Use syslog_stream_start for live tail."""
    args = ["syslog", "live"]
    if filter_proc:
        args += ["--process", filter_proc]
    # pymobiledevice3 syslog live streams — we'll wrap in timeout
    cmd = [_pmd3_bin()] + args
    u = udid or _SELECTED_UDID
    if u:
        cmd += ["--udid", u]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        captured: List[str] = []
        start = time.time()
        while time.time() - start < timeout and len(captured) < lines:
            line = proc.stdout.readline() if proc.stdout else ""
            if line:
                captured.append(line.rstrip())
            else:
                time.sleep(0.05)
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        return _ok("\n".join(captured[-lines:]), lines=captured[-lines:])
    except FileNotFoundError:
        return _err("pymobiledevice3 not found")


def _handle_syslog_stream_start(
    udid: Optional[str], filter_proc: Optional[str], name: str = "default"
) -> Dict[str, Any]:
    if name in _BG_PROCS:
        return _err(f"stream '{name}' already running (pid={_BG_PROCS[name].pid})")
    log_file = Path(f"/tmp/strands_ios_syslog_{name}.log")
    args = [_pmd3_bin(), "syslog", "live"]
    if filter_proc:
        args += ["--process", filter_proc]
    u = udid or _SELECTED_UDID
    if u:
        args += ["--udid", u]
    with open(log_file, "w") as f:
        proc = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT)
    _BG_PROCS[name] = proc
    return _ok(f"syslog stream '{name}' started → {log_file} (pid={proc.pid})",
               log_file=str(log_file), pid=proc.pid)


def _handle_syslog_stream_stop(name: str = "default") -> Dict[str, Any]:
    proc = _BG_PROCS.pop(name, None)
    if not proc:
        return _err(f"no stream named '{name}'")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    return _ok(f"stream '{name}' stopped")


# ----------------------------------------------------------------------------
# Screen
# ----------------------------------------------------------------------------

def _handle_screenshot(
    udid: Optional[str],
    output_path: Optional[str],
    return_image: bool = True,
) -> Dict[str, Any]:
    """Take a screenshot. Returns Converse API image block if return_image=True."""
    out = output_path or f"/tmp/strands_ios_screenshot_{int(time.time())}.png"
    r = _run(["developer", "dvt", "screenshot", out], udid=udid, timeout=20)
    if r["returncode"] != 0:
        return _err(f"screenshot failed: {r['stderr']}\n"
                    f"(note: DVT requires developer mode + tunnel on iOS 17+)")
    if not Path(out).exists():
        return _err(f"screenshot command ran but file missing: {out}")

    result = {"status": "success", "content": [{"text": f"screenshot → {out}"}], "path": out}
    if return_image:
        try:
            img_bytes = Path(out).read_bytes()
            # Converse API image block
            result["content"].append({
                "image": {
                    "format": "png",
                    "source": {"bytes": img_bytes},
                }
            })
        except Exception as e:
            logger.warning("could not attach image block: %s", e)
    return result


def _handle_screenrecord_start(udid: Optional[str], name: str = "default") -> Dict[str, Any]:
    if name in _BG_PROCS:
        return _err(f"recording '{name}' already running")
    out = f"/tmp/strands_ios_record_{name}_{int(time.time())}.mp4"
    args = [_pmd3_bin(), "developer", "dvt", "screenrecord", out]
    u = udid or _SELECTED_UDID
    if u:
        args += ["--udid", u]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _BG_PROCS[name] = proc
    return _ok(f"recording '{name}' started → {out} (pid={proc.pid})",
               path=out, pid=proc.pid)


def _handle_screenrecord_stop(name: str = "default") -> Dict[str, Any]:
    proc = _BG_PROCS.pop(name, None)
    if not proc:
        return _err(f"no recording named '{name}'")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return _ok(f"recording '{name}' stopped")


# ----------------------------------------------------------------------------
# Apps
# ----------------------------------------------------------------------------

def _handle_list_apps(udid: Optional[str], include_system: bool = False) -> Dict[str, Any]:
    args = ["apps", "list"]
    if not include_system:
        args.append("--no-system")
    r = _run(args, udid=udid, json_out=True, timeout=30)
    if r["returncode"] != 0:
        return _err(f"list_apps failed: {r['stderr']}")
    apps = r.get("json") or {}
    slim = [
        {"bundle_id": bid,
         "name": meta.get("CFBundleDisplayName") or meta.get("CFBundleName"),
         "version": meta.get("CFBundleShortVersionString")}
        for bid, meta in apps.items()
    ]
    return _ok(f"{len(slim)} apps:\n" + json.dumps(slim[:50], indent=2), apps=slim)


def _handle_launch(bundle_id: str, udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["developer", "dvt", "launch", bundle_id], udid=udid)
    if r["returncode"] != 0:
        return _err(f"launch failed: {r['stderr']}")
    return _ok(f"launched {bundle_id}\n{r['stdout']}")


def _handle_kill(bundle_id: str, udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["developer", "dvt", "kill", bundle_id], udid=udid)
    if r["returncode"] != 0:
        return _err(f"kill failed: {r['stderr']}")
    return _ok(f"killed {bundle_id}")


def _handle_install(ipa_path: str, udid: Optional[str]) -> Dict[str, Any]:
    if not Path(ipa_path).exists():
        return _err(f"IPA not found: {ipa_path}")
    r = _run(["apps", "install", ipa_path], udid=udid, timeout=300)
    if r["returncode"] != 0:
        return _err(f"install failed: {r['stderr']}")
    return _ok(f"installed {ipa_path}")


def _handle_uninstall(bundle_id: str, udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["apps", "uninstall", bundle_id], udid=udid)
    if r["returncode"] != 0:
        return _err(f"uninstall failed: {r['stderr']}")
    return _ok(f"uninstalled {bundle_id}")


def _handle_current_app(udid: Optional[str]) -> Dict[str, Any]:
    # Best-effort: list running processes via DVT
    r = _run(["developer", "dvt", "proclist"], udid=udid, json_out=True, timeout=15)
    if r["returncode"] != 0:
        return _err(f"current_app failed: {r['stderr']}")
    procs = r.get("json") or []
    # iOS foreground heuristic — topmost app-like process
    return _ok(f"{len(procs)} processes", processes=procs[:20])


# ----------------------------------------------------------------------------
# Files via AFC
# ----------------------------------------------------------------------------

def _handle_afc_ls(remote: str, udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["afc", "ls", remote], udid=udid)
    if r["returncode"] != 0:
        return _err(f"afc_ls failed: {r['stderr']}")
    return _ok(r["stdout"])


def _handle_afc_pull(remote: str, local: str, udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["afc", "pull", remote, local], udid=udid, timeout=120)
    if r["returncode"] != 0:
        return _err(f"afc_pull failed: {r['stderr']}")
    return _ok(f"pulled {remote} → {local}")


def _handle_afc_push(local: str, remote: str, udid: Optional[str]) -> Dict[str, Any]:
    if not Path(local).exists():
        return _err(f"local file not found: {local}")
    r = _run(["afc", "push", local, remote], udid=udid, timeout=120)
    if r["returncode"] != 0:
        return _err(f"afc_push failed: {r['stderr']}")
    return _ok(f"pushed {local} → {remote}")


# ----------------------------------------------------------------------------
# Crash logs, pcap
# ----------------------------------------------------------------------------

def _handle_crash_logs(udid: Optional[str], limit: int = 10) -> Dict[str, Any]:
    r = _run(["crash", "ls"], udid=udid, timeout=20)
    if r["returncode"] != 0:
        return _err(f"crash_logs failed: {r['stderr']}")
    lines = r["stdout"].splitlines()[:limit]
    return _ok("\n".join(lines), crashes=lines)


def _handle_pcap_start(udid: Optional[str], name: str = "default") -> Dict[str, Any]:
    if name in _BG_PROCS:
        return _err(f"pcap '{name}' already running")
    out = f"/tmp/strands_ios_pcap_{name}_{int(time.time())}.pcap"
    args = [_pmd3_bin(), "pcap", out]
    u = udid or _SELECTED_UDID
    if u:
        args += ["--udid", u]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    _BG_PROCS[name] = proc
    return _ok(f"pcap '{name}' started → {out} (pid={proc.pid})", path=out, pid=proc.pid)


def _handle_pcap_stop(name: str = "default") -> Dict[str, Any]:
    proc = _BG_PROCS.pop(name, None)
    if not proc:
        return _err(f"no pcap named '{name}'")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    return _ok(f"pcap '{name}' stopped")


# ----------------------------------------------------------------------------
# UI automation (via WebDriverAgent — optional)
# ----------------------------------------------------------------------------

def _wda_client(wda_url: Optional[str]):
    try:
        import wda  # facebook-wda
    except ImportError as e:
        raise IOSError(
            "UI automation requires: pip install 'strands-ios[ui]' (facebook-wda)"
        ) from e
    url = wda_url or _WDA_URL or "http://localhost:8100"
    return wda.Client(url)


def _handle_tap(x: int, y: int, wda_url: Optional[str]) -> Dict[str, Any]:
    try:
        c = _wda_client(wda_url)
        c.tap(x, y)
        return _ok(f"tap({x},{y})")
    except Exception as e:
        return _err(f"tap failed: {e}\n(is WebDriverAgent running? export WDA_URL=http://localhost:8100)")


def _handle_swipe(x1: int, y1: int, x2: int, y2: int, duration: float,
                  wda_url: Optional[str]) -> Dict[str, Any]:
    try:
        c = _wda_client(wda_url)
        c.swipe(x1, y1, x2, y2, duration)
        return _ok(f"swipe({x1},{y1})→({x2},{y2})")
    except Exception as e:
        return _err(f"swipe failed: {e}")


def _handle_type(text: str, wda_url: Optional[str]) -> Dict[str, Any]:
    try:
        c = _wda_client(wda_url)
        c.send_keys(text)
        return _ok(f"typed {len(text)} chars")
    except Exception as e:
        return _err(f"type failed: {e}")


def _handle_press(button: str, wda_url: Optional[str]) -> Dict[str, Any]:
    # home, volumeUp, volumeDown, power
    try:
        c = _wda_client(wda_url)
        c.press(button)
        return _ok(f"pressed {button}")
    except Exception as e:
        return _err(f"press failed: {e}")


# ----------------------------------------------------------------------------
# Misc
# ----------------------------------------------------------------------------

def _handle_open_url(url: str, udid: Optional[str]) -> Dict[str, Any]:
    # Open URL via Safari URL scheme trick — needs WDA or springboard service
    try:
        c = _wda_client(None)
        c.open_url(url)
        return _ok(f"opened {url}")
    except Exception:
        # Fallback: just tell the user
        return _err(f"open_url needs WDA running (export WDA_URL=...)")


def _handle_set_location(lat: float, lon: float, udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["developer", "dvt", "simulate-location", "set", str(lat), str(lon)],
             udid=udid, timeout=10)
    if r["returncode"] != 0:
        return _err(f"set_location failed: {r['stderr']}")
    return _ok(f"location set: {lat},{lon}")


def _handle_reboot(udid: Optional[str]) -> Dict[str, Any]:
    r = _run(["diagnostics", "restart"], udid=udid)
    if r["returncode"] != 0:
        return _err(f"reboot failed: {r['stderr']}")
    return _ok("reboot triggered")


# ----------------------------------------------------------------------------
# The @tool
# ----------------------------------------------------------------------------

@tool
def ios(
    action: str,
    # selectors
    udid: Optional[str] = None,
    bundle_id: Optional[str] = None,
    # coords / ui
    x: Optional[int] = None,
    y: Optional[int] = None,
    x2: Optional[int] = None,
    y2: Optional[int] = None,
    duration: float = 0.2,
    text: Optional[str] = None,
    button: Optional[str] = None,
    # files
    local: Optional[str] = None,
    remote: Optional[str] = None,
    ipa_path: Optional[str] = None,
    output_path: Optional[str] = None,
    # syslog / streams
    lines: int = 50,
    filter_proc: Optional[str] = None,
    name: str = "default",
    timeout: int = 30,
    # location
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    # wda
    wda_url: Optional[str] = None,
    # misc
    include_system: bool = False,
    return_image: bool = True,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    📱 Control an iOS device (iPhone/iPad) over USB via pymobiledevice3.

    Actions:
      Device:
        list_devices                     — enumerate connected devices
        select_device(udid)              — set default device
        device_info                      — name, iOS version, product
        battery                          — battery level + health
        storage                          — disk usage

      Syslog (like adb logcat):
        syslog(lines, filter_proc)       — capture N lines
        syslog_stream_start(name, filter_proc)
        syslog_stream_stop(name)

      Screen:
        screenshot(output_path, return_image)  — DVT-based, iOS 14+
        screenrecord_start(name)
        screenrecord_stop(name)

      Apps:
        list_apps(include_system)
        launch(bundle_id)
        kill(bundle_id)
        install(ipa_path)
        uninstall(bundle_id)
        current_app                      — running processes

      Files (AFC — sandboxed):
        afc_ls(remote)
        afc_pull(remote, local)
        afc_push(local, remote)

      Diagnostics:
        crash_logs(lines)
        pcap_start(name)  / pcap_stop(name)

      UI (requires WebDriverAgent running):
        tap(x, y)
        swipe(x, y, x2, y2, duration)
        type_text(text)
        press(button)                    — home|volumeUp|volumeDown|power

      Misc:
        open_url(url)
        set_location(lat, lon)           — DVT simulate location
        reboot

    Env:
      IOS_UDID                 — default device UDID
      WDA_URL                  — WebDriverAgent base URL
      PYMOBILEDEVICE3_BIN      — override pmd3 binary path

    Note: iOS 17+ requires a RemoteXPC tunnel for developer services
    (DVT, screenshot, launch). Start one with:
      sudo pymobiledevice3 remote tunneld
    """
    try:
        # --- device ---
        if action == "list_devices":
            return _handle_list_devices()
        if action == "select_device":
            if not udid:
                return _err("select_device requires udid")
            return _handle_select_device(udid)
        if action == "device_info":
            return _handle_device_info(udid)
        if action == "battery":
            return _handle_battery(udid)
        if action == "storage":
            return _handle_storage(udid)

        # --- syslog ---
        if action == "syslog":
            return _handle_syslog(udid, lines=lines, filter_proc=filter_proc,
                                  timeout=timeout)
        if action == "syslog_stream_start":
            return _handle_syslog_stream_start(udid, filter_proc, name)
        if action == "syslog_stream_stop":
            return _handle_syslog_stream_stop(name)

        # --- screen ---
        if action == "screenshot":
            return _handle_screenshot(udid, output_path, return_image)
        if action == "screenrecord_start":
            return _handle_screenrecord_start(udid, name)
        if action == "screenrecord_stop":
            return _handle_screenrecord_stop(name)

        # --- apps ---
        if action == "list_apps":
            return _handle_list_apps(udid, include_system)
        if action == "launch":
            if not bundle_id:
                return _err("launch requires bundle_id")
            return _handle_launch(bundle_id, udid)
        if action == "kill":
            if not bundle_id:
                return _err("kill requires bundle_id")
            return _handle_kill(bundle_id, udid)
        if action == "install":
            if not ipa_path:
                return _err("install requires ipa_path")
            return _handle_install(ipa_path, udid)
        if action == "uninstall":
            if not bundle_id:
                return _err("uninstall requires bundle_id")
            return _handle_uninstall(bundle_id, udid)
        if action == "current_app":
            return _handle_current_app(udid)

        # --- files ---
        if action == "afc_ls":
            if not remote:
                return _err("afc_ls requires remote")
            return _handle_afc_ls(remote, udid)
        if action == "afc_pull":
            if not (remote and local):
                return _err("afc_pull requires remote + local")
            return _handle_afc_pull(remote, local, udid)
        if action == "afc_push":
            if not (local and remote):
                return _err("afc_push requires local + remote")
            return _handle_afc_push(local, remote, udid)

        # --- crash / pcap ---
        if action == "crash_logs":
            return _handle_crash_logs(udid, lines)
        if action == "pcap_start":
            return _handle_pcap_start(udid, name)
        if action == "pcap_stop":
            return _handle_pcap_stop(name)

        # --- UI (WDA) ---
        if action == "tap":
            if x is None or y is None:
                return _err("tap requires x, y")
            return _handle_tap(x, y, wda_url)
        if action == "swipe":
            if None in (x, y, x2, y2):
                return _err("swipe requires x, y, x2, y2")
            return _handle_swipe(x, y, x2, y2, duration, wda_url)
        if action == "type_text":
            if text is None:
                return _err("type_text requires text")
            return _handle_type(text, wda_url)
        if action == "press":
            if not button:
                return _err("press requires button (home|volumeUp|volumeDown|power)")
            return _handle_press(button, wda_url)

        # --- misc ---
        if action == "open_url":
            if not url:
                return _err("open_url requires url")
            return _handle_open_url(url, udid)
        if action == "set_location":
            if lat is None or lon is None:
                return _err("set_location requires lat, lon")
            return _handle_set_location(lat, lon, udid)
        if action == "reboot":
            return _handle_reboot(udid)

        return _err(f"unknown action: {action}")

    except IOSError as e:
        return _err(str(e))
    except Exception as e:
        logger.exception("ios tool crashed")
        return _err(f"unexpected error: {e}")
