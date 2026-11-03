# pyright: strict
"""Runtime environment for the Prefab Pyodide sandbox behind `generate_prefab_ui`."""

import importlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import cast


def prepare_prefab_sandbox_env() -> None:
    os.environ.setdefault("DENO_DIR", str(Path(tempfile.gettempdir()) / "deno"))
    os.environ.setdefault("DENO_NO_PACKAGE_JSON", "1")
    os.environ.setdefault("DENO_NO_UPDATE_CHECK", "1")
    try:
        deno_mod = importlib.import_module("deno")
    except ImportError:
        return
    find_deno_bin_obj: object = getattr(deno_mod, "find_deno_bin", None)
    if not callable(find_deno_bin_obj):
        return
    find_deno_bin = cast(Callable[[], str], find_deno_bin_obj)
    try:
        deno_dir = str(Path(find_deno_bin()).parent)
    except FileNotFoundError:
        return
    path = os.environ.get("PATH", "")
    if deno_dir not in path.split(os.pathsep):
        os.environ["PATH"] = os.pathsep.join(filter(None, (deno_dir, path)))
