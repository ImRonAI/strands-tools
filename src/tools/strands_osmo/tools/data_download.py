"""Download data from OSMO storage."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_data_download(src: str, dest: str, bucket: str = "") -> dict:
    """Download a path from OSMO storage to a local directory.

    Args:
        src: Remote path (e.g. ``s3://my-bucket/path/file.bin``).
        dest: Local destination.
        bucket: Override bucket name.
    """
    if not src or not dest:
        return err("src and dest are required")
    Path(dest).expanduser().parent.mkdir(parents=True, exist_ok=True)
    args = ["data", "download", src, dest]
    if bucket:
        args += ["--bucket", bucket]
    proc = osmo_run(*args, timeout_s=3600)
    return proc_result(proc, success_text=f"downloaded {src} → {dest}")
