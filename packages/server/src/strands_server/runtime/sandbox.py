"""Runtime environment for the Prefab Pyodide sandbox behind `generate_prefab_ui`."""

import os
import tempfile
from pathlib import Path


def prepare_prefab_sandbox_env() -> None:
    os.environ.setdefault("DENO_DIR", str(Path(tempfile.gettempdir()) / "deno"))
    os.environ.setdefault("DENO_NO_PACKAGE_JSON", "1")
    os.environ.setdefault("DENO_NO_UPDATE_CHECK", "1")
    try:
        from deno import find_deno_bin
    except ImportError:
        return
    try:
        deno_dir = str(Path(find_deno_bin()).parent)
    except FileNotFoundError:
        return
    path = os.environ.get("PATH", "")
    if deno_dir not in path.split(os.pathsep):
        os.environ["PATH"] = os.pathsep.join(filter(None, (deno_dir, path)))
