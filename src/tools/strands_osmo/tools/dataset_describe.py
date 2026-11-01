"""Describe a dataset and its versions."""
from __future__ import annotations

from strands import tool

from ._common import err, osmo_run, proc_result


@tool
def osmo_dataset_describe(name: str, version: str = "") -> dict:
    """Describe a dataset (versions, tags, size, source workflow).

    Args:
        name: Dataset name.
        version: Specific version. Empty → all versions.
    """
    if not name:
        return err("name is required")
    args = ["dataset", "describe", name, "--format-type", "json"]
    if version:
        args += ["--version", version]
    proc = osmo_run(*args, parse_json=True, timeout_s=30)
    return proc_result(proc, success_text=f"dataset {name}")
