"""Upload a file or directory to OSMO storage."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_data_upload(
    src: str,
    dest: str,
    bucket: str = "",
    recursive: bool = True,
) -> dict:
    """Upload local data to an OSMO bucket path.

    Args:
        src: Local file or directory.
        dest: Destination path (e.g. ``s3://my-bucket/path/`` or ``my-bucket/path``).
        bucket: Override default bucket. If empty, uses dest's prefix.
        recursive: When True (default), uploads directories recursively.
    """
    p = Path(src).expanduser()
    if not p.exists():
        return err(f"src not found: {p}")
    args = ["data", "upload", str(p), dest]
    if bucket:
        args += ["--bucket", bucket]
    if recursive:
        args += ["--recursive"]
    proc = osmo_run(*args, timeout_s=3600)
    return proc_result(proc, success_text=f"uploaded {p} → {dest}")
