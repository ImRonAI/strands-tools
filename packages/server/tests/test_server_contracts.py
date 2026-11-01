"""Contract tests for the Strands Tools FastMCP 4.1.0 Server (strands_server)."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for pkg_src in (
    REPO_ROOT / "packages" / "server" / "src",
    REPO_ROOT / "packages" / "client" / "src",
):
    if str(pkg_src) not in sys.path:
        sys.path.insert(0, str(pkg_src))

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import ClientTransport
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.utilities.tests import asgi_client
from fastmcp_tasks import TasksExtension

from strands_client import list_model_visible_tools
from strands_server import build_server
from strands_server.catalog_loader import (
    EXCLUDED_STRANDS_PACK_GOOGLE_MODULES,
    load_all_strands_tools,
)


@pytest.fixture(scope="module")
def server_instance() -> FastMCP:
    return build_server(
        auth=StaticTokenVerifier(
            tokens={"test-token": {"client_id": "pytest", "scopes": []}}
        ),
        tasks=TasksExtension(url="memory://"),
    )


@pytest.fixture
async def mcp_client(server_instance: FastMCP) -> AsyncIterator[Client[ClientTransport]]:
    async with asgi_client(server_instance, auth="test-token") as client:
        yield client


def test_catalog_loads_all_12_repos_and_excludes_pack_google_tools() -> None:
    tools_list = load_all_strands_tools()
    catalog = {t.name: t for t in tools_list}
    tool_names = set(catalog.keys())

    # Total catalog size check
    assert len(tool_names) >= 350

    # 1. Strands Google
    for name in ("use_google", "google_auth", "gmail_send", "gmail_reply"):
        assert name in tool_names, f"Missing Strands Google tool: {name}"
        assert catalog[name].domain_suite == "strands_google"

    # 2. Strands Fun Tools (all 17 modules)
    for name in (
        "human_typer",
        "cursor",
        "clipboard",
        "dynamic_package",
        "template",
        "utility",
        "chess",
        "bluetooth",
        "screen_reader",
        "yolo_vision",
        "face_recognition",
        "take_photo",
        "listen",
        "spinner_generator",
        "npm",
        "dialog",
        "asciimatics_ui",
    ):
        assert name in tool_names, f"Missing Strands Fun Tool: {name}"

    # 3. Strands Agent Tools + heterogeneous_graph
    for name in (
        "calculator",
        "current_time",
        "file_read",
        "file_write",
        "editor",
        "shell",
        "python_repl",
        "http_request",
        "use_aws",
        "graph",
        "swarm",
        "workflow",
        "heterogeneous_graph",
    ):
        assert name in tool_names, f"Missing Strands Agent Tool: {name}"

    # 4. Strands Pack: exclude Google Workspace & Gemini tools; include YouTube, runtime, and other pack tools
    pack_tools = {name: entry for name, entry in catalog.items() if entry.domain_suite == "strands_pack"}
    for excluded in EXCLUDED_STRANDS_PACK_GOOGLE_MODULES:
        assert excluded not in pack_tools, f"Excluded pack tool {excluded} should not be in strands-pack"
    for yt_tool in (
        "youtube",
        "youtube_read",
        "youtube_write",
        "youtube_analytics",
        "youtube_transcript",
    ):
        assert yt_tool in tool_names, f"Missing YouTube tool from strands-pack: {yt_tool}"
    for runtime_tool in ("pack_runtime_approval", "pack_runtime_job_runner"):
        assert runtime_tool in tool_names, f"Missing runtime tool from strands-pack: {runtime_tool}"
    for other_pack in ("discord", "github", "notion", "pdf", "qrcode_tool", "sqlite", "twilio_tool"):
        assert other_pack in tool_names, f"Missing pack tool: {other_pack}"

    # 5. Strands Telegram + Telegram Listener
    assert "telegram" in tool_names
    assert "telegram_listener" in tool_names

    # 6. Strands Zero (all 20 zero_* tools)
    zero_tools = [n for n in tool_names if n.startswith("zero_")]
    assert len(zero_tools) == 20

    # 7. Strands UTCP
    for name in (
        "utcp",
        "utcp_register_manual",
        "utcp_list_tools",
        "utcp_search_tools",
        "utcp_call_tool",
    ):
        assert name in tool_names, f"Missing UTCP tool: {name}"

    # 8. Strands Harness SDK Tools
    for name in (
        "read",
        "write",
        "edit",
        "programmatic_tool_caller",
        "subagent",
        "web_fetch",
        "web_search",
        "bash",
    ):
        assert name in tool_names, f"Missing Harness SDK tool: {name}"

    # 9. Strands Document MCP Server
    assert "search_docs" in tool_names
    assert "fetch_doc" in tool_names

    # 10. Strands Agent Skills (Pattern #2 and Pattern #3 with tool assignment)
    for name in (
        "skill",
        "use_skill",
        "configure_skill_tools",
        "list_available_skills",
    ):
        assert name in tool_names, f"Missing Agent Skills tool: {name}"

    # 11. Strands CCXT
    assert "use_ccxt" in tool_names

    # 12. Strands Inspect
    assert "inspect_tool" in tool_names

    # 13. Strands.my catalog discovery tool
    assert "strands_my_catalog" in tool_names


async def test_model_visible_tools_are_only_four(
    mcp_client: Client[ClientTransport],
) -> None:
    tools = await list_model_visible_tools(mcp_client)
    assert [t.name for t in tools] == [
        "execute",
        "generate_prefab_ui",
        "get_schema",
        "search",
    ]


async def test_pattern_2_and_pattern_3_agent_skills_with_tool_assignment(
    mcp_client: Client[ClientTransport],
) -> None:
    # Pattern #2: Load skill instructions via `skill`
    p2_res = await mcp_client.call_tool(
        "execute",
        {"code": "return await call_tool('skill', {'skill_name': 'file-processing'})"},
    )
    assert not p2_res.is_error
    assert "file-processing" in str(p2_res.structured_content)

    # Pattern #3: Assign additional tools (globally and per-skill) to `use_skill`
    p3_cfg = await mcp_client.call_tool(
        "execute",
        {
            "code": (
                "c1 = await call_tool('configure_skill_tools', "
                "{'action': 'set_global', 'tool_names': ['calculator', 'current_time', 'use_ccxt', 'inspect_tool']})\n"
                "c2 = await call_tool('configure_skill_tools', "
                "{'action': 'assign_skill', 'skill_name': 'file-processing', 'tool_names': ['read', 'write', 'edit']})\n"
                "c3 = await call_tool('configure_skill_tools', {'action': 'list_assignable'})\n"
                "return {'global': c1, 'per_skill': c2, 'assignable': c3}"
            )
        },
    )
    assert not p3_cfg.is_error
    sc = p3_cfg.structured_content or {}
    payload = sc.get("result", sc)
    assert "calculator" in str(payload.get("global"))
    assert "read" in str(payload.get("per_skill"))
    assert payload.get("assignable", {}).get("registered_tool_count", 0) >= 300
    assert payload.get("assignable", {}).get("total_assignable_tools", 0) >= 300


async def test_skill_subdirectories_references_scripts_assets_and_resources() -> None:
    import os
    from pathlib import Path

    from agentskills import (
        build_skill_subdirectory_tools,
        discover_skills,
        scan_skill_resources_by_category,
    )

    assert os.environ.get("BYPASS_TOOL_CONSENT") == "true"

    root_dir = Path(__file__).resolve().parents[3]
    skills = discover_skills(root_dir / "src" / "skills")
    skill_map = {s.name: s for s in skills}

    # 1. Verify `file-processing` has `scripts/` tool (`run_skill_script`)
    fp_skill = skill_map["file-processing"]
    fp_cats = scan_skill_resources_by_category(Path(fp_skill.skill_dir))
    assert len(fp_cats["scripts"]) >= 1
    fp_tools = {
        getattr(t, "tool_name", getattr(t, "__name__", "")): t
        for t in build_skill_subdirectory_tools(fp_skill)
    }
    assert "run_skill_script" in fp_tools

    script_inspect = fp_tools["run_skill_script"](
        action="inspect",
        script_path="process.py",
    )
    assert script_inspect["status"] == "success"
    assert "process.py" in script_inspect["content"][0]["text"]

    # 2. Verify `react-three-fiber` has all three (`references/`, `scripts/`, and `assets/`) tools
    r3f_skill = skill_map["react-three-fiber"]
    r3f_cats = scan_skill_resources_by_category(Path(r3f_skill.skill_dir))
    assert len(r3f_cats["references"]) >= 1
    assert len(r3f_cats["scripts"]) >= 1
    assert len(r3f_cats["assets"]) >= 1

    r3f_tools = {
        getattr(t, "tool_name", getattr(t, "__name__", "")): t
        for t in build_skill_subdirectory_tools(r3f_skill)
    }
    assert "query_skill_references" in r3f_tools
    assert "run_skill_script" in r3f_tools
    assert "use_skill_asset" in r3f_tools

    ref_list = r3f_tools["query_skill_references"](action="list")
    assert ref_list["status"] == "success"
    assert "references" in ref_list["content"][0]["text"]

    asset_list = r3f_tools["use_skill_asset"](action="list")
    assert asset_list["status"] == "success"
    assert "assets" in asset_list["content"][0]["text"]



async def test_all_14_domain_workspaces_return_prefab_0_3(
    mcp_client: Client[ClientTransport],
) -> None:
    domains = (
        "google",
        "fun_tools",
        "agent_tools",
        "pack",
        "youtube",
        "telegram",
        "zero",
        "utcp",
        "harness",
        "docs",
        "skills",
        "ccxt",
        "inspect",
        "ecosystem",
    )
    for domain in domains:
        res = await mcp_client.call_tool(
            "execute",
            {"code": f"return await call_tool('{domain}_workspace', {{}})"},
        )
        assert not res.is_error, f"Workspace {domain}_workspace failed"
        sc = res.structured_content or {}
        assert sc.get("$prefab", {}).get("version") == "0.3", f"Workspace {domain} missing $prefab 0.3"


async def test_auth_status_and_credentials_configuration(
    mcp_client: Client[ClientTransport],
) -> None:
    res = await mcp_client.call_tool(
        "execute",
        {"code": "return await call_tool('strands_auth_status', {})"},
    )
    assert not res.is_error
    sc = res.structured_content or {}
    payload = sc.get("result", sc)
    rows = payload.get("rows", [])
    assert "strands_google" in str(rows)
    assert "strands_ccxt" in str(rows)
