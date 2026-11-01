"""Demo functions against the in-process Strands MCP server fixture and REA proxy."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for pkg_src in (
    REPO_ROOT / "packages" / "client" / "src",
    REPO_ROOT / "packages" / "server" / "src",
    Path(__file__).resolve().parent,
):
    if str(pkg_src) not in sys.path:
        sys.path.insert(0, str(pkg_src))

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import ClientTransport
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.utilities.tests import asgi_client
from fastmcp_tasks import TasksExtension

from strands_server import build_server
from strands_server.runtime import tasks as server_tasks

from workspace_demo import (
    open_google,
    renderer_info,
    show_catalog,
    show_rea_proxy,
    summarize,
    track_strands_job,
)


@pytest.fixture(scope="module")
def real_server() -> Callable[[], FastMCP]:
    server = build_server(
        auth=StaticTokenVerifier(
            tokens={"user-token": {"client_id": "client", "scopes": []}}
        ),
        tasks=TasksExtension(url="memory://"),
    )

    def get_server() -> FastMCP:
        return server

    return get_server


@pytest.fixture
async def http_client(real_server: Callable[[], FastMCP]) -> AsyncIterator[Client[ClientTransport]]:
    async with asgi_client(real_server(), auth="user-token") as client:
        yield client


async def test_summarize_lists_the_four_model_visible_tools(
    http_client: Client[ClientTransport],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await summarize(http_client)
    out = capsys.readouterr().out
    assert "server:" in out
    for name in ("search", "get_schema", "execute", "generate_prefab_ui"):
        assert f"- {name}" in out


async def test_show_catalog_prints_search_and_schema_results(
    http_client: Client[ClientTransport],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await show_catalog(http_client)
    out = capsys.readouterr().out
    assert out.count("use_google") >= 1


async def test_open_google_prints_the_prefab_version(
    http_client: Client[ClientTransport],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await open_google(http_client)
    out = capsys.readouterr().out
    assert "workspace google: prefab 0.3" in out


async def test_renderer_info_prints_mime_and_uri(
    http_client: Client[ClientTransport],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await renderer_info(http_client)
    out = capsys.readouterr().out
    assert "ui://prefab/generative.html" in out
    assert "text/html;profile=mcp-app" in out


async def test_track_strands_job_prints_completed(
    http_client: Client[ClientTransport],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_tasks, "POLL_INTERVAL", timedelta(seconds=0.01))
    await track_strands_job(http_client, "job-1")
    out = capsys.readouterr().out
    assert "strands job job-1: completed (polls=2)" in out


async def test_show_rea_proxy_lists_rea_tools(
    capsys: pytest.CaptureFixture[str],
) -> None:
    await show_rea_proxy()
    out = capsys.readouterr().out
    assert "proxied rea tools:" in out
    assert "first=" in out
