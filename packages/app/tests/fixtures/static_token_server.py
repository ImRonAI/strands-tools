"""Static-token FastMCP fixture server for the packages/app TypeScript tests.

Builds the real Strands Tools MCP server, binds it to a real localhost port,
prints `OUBLIAI_FIXTURE_URL=<url>` (single line, flushed) for the vitest global
setup, and exits cleanly on SIGTERM/SIGINT.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

# Ensure packages/server/src is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[4]
SERVER_SRC = REPO_ROOT / "packages" / "server" / "src"
if str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))

from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.utilities.tests import run_server_async
from fastmcp_tasks import TasksExtension

from strands_server import build_server

FIXTURE_TOKEN = "e2e-token"


async def _main() -> None:
    server = build_server(
        auth=StaticTokenVerifier(
            tokens={FIXTURE_TOKEN: {"client_id": "e2e", "scopes": []}}
        ),
        tasks=TasksExtension(url="memory://"),
        mask_error_details=False,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    async with run_server_async(server, host="127.0.0.1") as url:
        print(f"OUBLIAI_FIXTURE_URL={url}", flush=True)
        await stop_event.wait()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
