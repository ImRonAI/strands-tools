"""Strands @tool wrappers for the Zero CLI.

Every tool returns a dict with keys: ok, stdout, stderr, exit_code, command,
and (when --json was used) a parsed `json` field. Tools are deliberately thin
wrappers — the agent decides what to do with the output.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from strands import tool

from strands_zero._runner import run_zero, find_zero_binary
from strands_zero.installer import install_zero


# ---------------------------------------------------------------------------
# Meta / environment
# ---------------------------------------------------------------------------

@tool
def zero_version(json_output: bool = True) -> Dict[str, Any]:
    """Get the installed Zero compiler version and host info.

    Args:
        json_output: Return structured JSON (default True).
    """
    args = ["--version"] + (["--json"] if json_output else [])
    return run_zero(args, parse_json=json_output)


@tool
def zero_install(install_dir: Optional[str] = None) -> Dict[str, Any]:
    """Install (or reinstall) the Zero compiler from zerolang.ai.

    Args:
        install_dir: Optional install directory (defaults to ~/.zero/bin).
    """
    return install_zero(install_dir)


@tool
def zero_doctor(json_output: bool = True) -> Dict[str, Any]:
    """Run `zero doctor` to check the toolchain and environment health."""
    args = ["doctor"] + (["--json"] if json_output else [])
    return run_zero(args, parse_json=json_output)


@tool
def zero_targets() -> Dict[str, Any]:
    """List available compilation targets."""
    return run_zero(["targets"])


@tool
def zero_skills(action: str = "list", name: Optional[str] = None,
                full: bool = False) -> Dict[str, Any]:
    """Access Zero's built-in skill docs (language, diagnostics, builds, etc).

    Args:
        action: One of "list", "get", "path".
        name: Skill name when action="get" or action="path"
              (e.g. "zero-language", "zero-diagnostics", "zero-agent").
        full: When True with get, request full skill body.
    """
    if action == "list":
        return run_zero(["skills", "list", "--json"], parse_json=True)
    if action in ("get", "path"):
        if not name:
            return {"ok": False, "error": f"name required for action='{action}'"}
        args = ["skills", action, name]
        if action == "get" and full:
            args.append("--full")
        return run_zero(args)
    return {"ok": False, "error": f"unknown action: {action}"}


# ---------------------------------------------------------------------------
# Authoring
# ---------------------------------------------------------------------------

@tool
def zero_write(
    code: str,
    path: Optional[str] = None,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Write Zero source code (`.0`) to disk.

    Args:
        code: The Zero source to write.
        path: Destination path. If None, writes to a temp `.0` file.
              If a path without `.0` extension is given, `.0` is appended.
        overwrite: Overwrite existing file (default True).

    Returns: dict with ok, path, bytes_written.
    """
    if path is None:
        fd, tmp = tempfile.mkstemp(suffix=".0", prefix="zero_")
        os.close(fd)
        target = Path(tmp)
    else:
        target = Path(path).expanduser()
        if target.suffix == "":
            target = target.with_suffix(".0")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            return {
                "ok": False,
                "error": f"file exists and overwrite=False: {target}",
                "path": str(target),
            }

    target.write_text(code, encoding="utf-8")
    return {
        "ok": True,
        "path": str(target),
        "bytes_written": len(code.encode("utf-8")),
    }


@tool
def zero_new(kind: str, name: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Scaffold a new Zero project: `zero new cli|lib|package <name>`.

    Args:
        kind: "cli", "lib", or "package".
        name: Project name.
        cwd: Working directory in which to create the project.
    """
    if kind not in ("cli", "lib", "package"):
        return {"ok": False, "error": f"kind must be cli/lib/package, got: {kind}"}
    return run_zero(["new", kind, name], cwd=cwd)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@tool
def zero_check(target: str, json_output: bool = True,
               cwd: Optional[str] = None) -> Dict[str, Any]:
    """Type-check and validate Zero source without running.

    Args:
        target: Path to a `.0` file, project dir, or `zero.json`.
        json_output: Return structured diagnostics JSON (preferred).
        cwd: Working directory for the check.
    """
    args = ["check"]
    if json_output:
        args.append("--json")
    args.append(target)
    return run_zero(args, cwd=cwd, parse_json=json_output)


@tool
def zero_explain(code: str, json_output: bool = True) -> Dict[str, Any]:
    """Explain a diagnostic code from `zero check`.

    Args:
        code: Diagnostic code (e.g. "E0123").
        json_output: Return JSON.
    """
    args = ["explain"]
    if json_output:
        args.append("--json")
    args.append(code)
    return run_zero(args, parse_json=json_output)


@tool
def zero_fix(target: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Generate a structured fix plan for diagnostics in `target`.

    Runs `zero fix --plan --json <target>`.
    """
    return run_zero(["fix", "--plan", "--json", target], cwd=cwd, parse_json=True)


# ---------------------------------------------------------------------------
# Build / run / test
# ---------------------------------------------------------------------------

@tool
def zero_run(
    target: str,
    args: Optional[List[str]] = None,
    profile: Optional[str] = None,
    target_arch: Optional[str] = None,
    out: Optional[str] = None,
    cwd: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Compile and run a Zero program.

    Args:
        target: Path to `.0` file, project dir, or `zero.json`.
        args: Args to pass to the program (after `--`).
        profile: debug | dev | release-fast | release-small | tiny | audit.
        target_arch: e.g. "darwin-arm64", "linux-musl-x64", "wasm32-wasi".
        out: Optional output binary path.
        cwd: Working directory.
        timeout: Seconds before killing the process (default 120).
    """
    cmd = ["run"]
    if target_arch:
        cmd += ["--target", target_arch]
    if profile:
        cmd += ["--profile", profile]
    if out:
        cmd += ["--out", out]
    cmd.append(target)
    if args:
        cmd += ["--", *args]
    return run_zero(cmd, cwd=cwd, timeout=timeout)


@tool
def zero_build(
    target: str,
    emit: str = "exe",
    profile: Optional[str] = None,
    target_arch: Optional[str] = None,
    out: Optional[str] = None,
    json_output: bool = False,
    cwd: Optional[str] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Compile a Zero program to an executable / object / wasm.

    Args:
        target: Source file, project dir, or `zero.json`.
        emit: "exe" | "obj" | "wasm".
        profile: debug | dev | release-fast | release-small | tiny | audit.
        target_arch: Compilation target triple (e.g. "linux-musl-x64").
        out: Output artifact path.
        json_output: Emit JSON build report.
        cwd: Working directory.
        timeout: Seconds before killing the process.
    """
    if emit not in ("exe", "obj", "wasm"):
        return {"ok": False, "error": f"emit must be exe/obj/wasm, got: {emit}"}
    cmd = ["build"]
    if json_output:
        cmd.append("--json")
    cmd += ["--emit", emit]
    if target_arch:
        cmd += ["--target", target_arch]
    if profile:
        cmd += ["--profile", profile]
    if out:
        cmd += ["--out", out]
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output, timeout=timeout)


@tool
def zero_ship(
    target: str,
    target_arch: Optional[str] = None,
    profile: str = "release-small",
    out: Optional[str] = None,
    json_output: bool = True,
    cwd: Optional[str] = None,
    timeout: int = 600,
) -> Dict[str, Any]:
    """Produce a release-grade artifact via `zero ship`.

    Args:
        target: Source / project / zero.json.
        target_arch: e.g. "linux-musl-x64".
        profile: release-small | tiny | audit (default release-small).
        out: Output path.
        json_output: Emit JSON ship report.
        cwd: Working directory.
        timeout: Seconds budget.
    """
    cmd = ["ship"]
    if json_output:
        cmd.append("--json")
    if target_arch:
        cmd += ["--target", target_arch]
    cmd += ["--profile", profile]
    if out:
        cmd += ["--out", out]
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output, timeout=timeout)


@tool
def zero_test(target: str, json_output: bool = True,
              cwd: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
    """Run `test` blocks in Zero source / project."""
    cmd = ["test"]
    if json_output:
        cmd.append("--json")
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output, timeout=timeout)


@tool
def zero_fmt(target: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Format Zero source in-place."""
    return run_zero(["fmt", target], cwd=cwd)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

@tool
def zero_graph(target: str, json_output: bool = True,
               cwd: Optional[str] = None) -> Dict[str, Any]:
    """Dump the module/package dependency graph."""
    cmd = ["graph"]
    if json_output:
        cmd.append("--json")
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output)


@tool
def zero_size(target: str, artifact: Optional[str] = None,
              json_output: bool = True, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Report binary size breakdown for a built artifact or source target."""
    cmd = ["size"]
    if json_output:
        cmd.append("--json")
    if artifact:
        cmd += ["--out", artifact]
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output)


@tool
def zero_mem(target: str, target_arch: Optional[str] = None,
             json_output: bool = True, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Report static memory layout / usage for a target."""
    cmd = ["mem"]
    if json_output:
        cmd.append("--json")
    if target_arch:
        cmd += ["--target", target_arch]
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output)


@tool
def zero_routes(target: str, json_output: bool = True,
                cwd: Optional[str] = None) -> Dict[str, Any]:
    """List HTTP/web routes declared in a Zero web project."""
    cmd = ["routes"]
    if json_output:
        cmd.append("--json")
    cmd.append(target)
    return run_zero(cmd, cwd=cwd, parse_json=json_output)


@tool
def zero_clean(target_dir: Optional[str] = None, all_artifacts: bool = False,
               cwd: Optional[str] = None) -> Dict[str, Any]:
    """Clean compiled artifacts (`.zero/` cache).

    Args:
        target_dir: Project directory (default cwd).
        all_artifacts: Pass --all to remove the entire `.zero/` cache.
    """
    cmd = ["clean"]
    if all_artifacts:
        cmd.append("--all")
    return run_zero(cmd, cwd=target_dir or cwd)
