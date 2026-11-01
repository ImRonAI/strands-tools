# pyright: strict
"""Root FastMCP Server entrypoint for FastMCP Cloud and `fastmcp run server.py`.

Exposes `mcp` (and aliases `server`, `app`, `create_server`) at module top-level
so FastMCP Cloud can load `server.py` directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
for _rel in ("src/tools", "src", "packages/server/src", "packages/client/src"):
    _path_str = str(REPO_ROOT / _rel)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from fastmcp import FastMCP  # noqa: E402
from strands_server.__main__ import create_server, main  # noqa: E402

mcp: FastMCP = create_server()
server: FastMCP = mcp
app: FastMCP = mcp

__all__ = ["app", "create_server", "main", "mcp", "server"]

if __name__ == "__main__":
    main()
