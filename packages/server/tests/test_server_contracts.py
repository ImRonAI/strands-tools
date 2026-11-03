# pyright: strict
"""Contract tests for the Strands Tools FastMCP 4.1.0 Server (strands_server)."""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import TypeGuard, cast

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


def _is_str_mapping(val: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(val, Mapping)


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
    ctx_mgr = cast(
        object,
        asgi_client(server_instance, auth="test-token"),
    )
    aenter = getattr(ctx_mgr, "__aenter__")
    aexit = getattr(ctx_mgr, "__aexit__")
    client = cast(Client[ClientTransport], await aenter())
    try:
        yield client
    finally:
        await aexit(None, None, None)


def test_native_catalog_loads_required_capabilities_and_suites() -> None:
    tools_list = load_all_strands_tools()
    catalog = {t.name: t for t in tools_list}
    tool_names = set(catalog.keys())

    # 1. All 5 required capabilities must be registered natively
    for required_cap in ("create_harness", "use_skill", "graph", "workflow", "swarm"):
        assert required_cap in tool_names, f"Missing required capability: {required_cap}"

    # Bespoke discovery tool `strands_my_catalog` must NOT exist
    assert "strands_my_catalog" not in tool_names

    # 2. Strands Google native @tool functions
    for name in ("use_google", "google_auth", "gmail_send", "gmail_reply"):
        assert name in tool_names, f"Missing Strands Google tool: {name}"
        meta = catalog[name].meta or {}
        assert meta.get("domain_suite") == "strands_google"

    # 3. Strands Fun Tools native @tool functions
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

    # 4. Strands Pack: exclude Google Workspace & Gemini tools; include YouTube & other native @tool functions
    pack_tools = {
        name: entry
        for name, entry in catalog.items()
        if (entry.meta or {}).get("domain_suite") == "strands_pack"
    }
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

    # 8. Strands Harness SDK (`create_harness`, `web_search`)
    assert "create_harness" in tool_names
    assert "web_search" in tool_names

    # 9. Strands Document MCP Server
    assert "search_docs" in tool_names
    assert "fetch_doc" in tool_names

    # 10. Strands Agent Skills (`skill`, `use_skill`, `configure_skill_tools`, `list_available_skills`)
    for name in (
        "skill",
        "use_skill",
        "configure_skill_tools",
        "list_available_skills",
    ):
        assert name in tool_names, f"Missing Agent Skills tool: {name}"

    # 11. Strands CCXT & Strands Inspect
    assert "use_ccxt" in tool_names
    assert "inspect_tool" in tool_names


async def test_model_visible_tools_are_only_five_and_exclude_capabilities(
    mcp_client: Client[ClientTransport],
) -> None:
    tools = await list_model_visible_tools(mcp_client)
    visible_names = [t.name for t in tools]
    assert visible_names == [
        "execute",
        "generate_prefab_ui",
        "get_schema",
        "get_tags",
        "search",
    ]
    for cap in ("create_harness", "use_skill", "graph", "workflow", "swarm"):
        assert cap not in visible_names

    tags_res = await mcp_client.call_tool("get_tags", {"detail": "brief"})
    assert not tags_res.is_error
    assert "strands" in str(tags_res.content)


async def test_all_tools_have_rich_parameter_schemas_via_get_schema(
    mcp_client: Client[ClientTransport],
) -> None:
    schema_res = await mcp_client.call_tool(
        "get_schema",
        {
            "tools": [
                "file_read",
                "file_write",
                "http_request",
                "use_aws",
                "python_repl",
                "generate_image",
                "retrieve",
                "mem0_memory",
                "chat_video",
                "search_video",
            ]
        },
    )
    assert not schema_res.is_error
    schema_text = str(schema_res.content)
    # Every tool must expose its actual typed parameters, never raw ToolUse dicts
    assert "tool: dict[str," not in schema_text
    assert "path" in schema_text
    assert "method" in schema_text
    assert "service_name" in schema_text
    assert "code" in schema_text
    assert "query" in schema_text


async def test_search_and_get_schema_discover_all_five_capabilities(
    mcp_client: Client[ClientTransport],
) -> None:
    capabilities_and_keywords = (
        ("create_harness", "harness"),
        ("use_skill", "skill"),
        ("graph", "graph"),
        ("workflow", "workflow"),
        ("swarm", "swarm"),
    )
    for cap_name, keyword in capabilities_and_keywords:
        by_name = await mcp_client.call_tool("search", {"query": cap_name})
        assert not by_name.is_error
        assert cap_name in str(by_name.content)

        by_keyword = await mcp_client.call_tool("search", {"query": keyword})
        assert not by_keyword.is_error
        assert cap_name in str(by_keyword.content)

        schema_res = await mcp_client.call_tool("get_schema", {"tools": [cap_name]})
        assert not schema_res.is_error
        assert cap_name in str(schema_res.content)


async def test_regression_use_skill_and_create_harness_graph_nodes_execute_end_to_end(
    mcp_client: Client[ClientTransport],
) -> None:
    """Regression test: on the MCP path (`execute`), a graph node using `use_skill` and a graph node
    using a `create_harness` agent both resolve and execute end-to-end without raising
    `Unknown or unresolvable tool 'use_skill'`.
    """
    code = """
harness_info = await call_tool('create_harness', {
    'name': 'harness_reviewer',
    'instructions': 'Review and summarize the skill output.',
    'model': 'stub',
    'include_default_tools': False,
})
created = await call_tool('graph', {
    'action': 'create',
    'graph_id': 'mcp_skill_and_harness_graph',
    'topology': {
        'nodes': [
            {
                'id': 'skill_worker',
                'type': 'use_skill',
                'skill': 'file-processing',
                'model_id': 'stub',
            },
            {
                'id': 'harness_reviewer',
                'type': 'create_harness',
                'agent': 'harness_reviewer',
                'model_id': 'stub',
            },
        ],
        'edges': [['skill_worker', 'harness_reviewer']],
        'entry_point': 'skill_worker',
    },
})
executed = await call_tool('graph', {
    'action': 'execute',
    'graph_id': 'mcp_skill_and_harness_graph',
    'task': 'Extract metadata from sample report and review.',
})
return {'harness': harness_info, 'created': created, 'executed': executed}
"""
    res = await mcp_client.call_tool("execute", {"code": code})
    assert not res.is_error
    sc = res.structured_content or {}
    payload_obj: object = sc.get("result", sc)
    text_repr = json.dumps(payload_obj)
    assert "Unknown or unresolvable tool" not in text_repr
    assert "skill_worker" in text_repr
    assert "harness_reviewer" in text_repr
    assert "Completed with tool result" in text_repr


async def test_pattern_2_and_pattern_3_agent_skills_with_tool_assignment(
    mcp_client: Client[ClientTransport],
) -> None:
    p2_res = await mcp_client.call_tool(
        "execute",
        {"code": "return await call_tool('skill', {'skill_name': 'file-processing'})"},
    )
    assert not p2_res.is_error
    assert "file-processing" in str(p2_res.structured_content)

    p3_cfg = await mcp_client.call_tool(
        "execute",
        {
            "code": (
                "c1 = await call_tool('configure_skill_tools', "
                "{'action': 'set_global', 'tool_names': ['calculator', 'current_time', 'use_ccxt', 'inspect_tool']})\n"
                "c2 = await call_tool('configure_skill_tools', "
                "{'action': 'assign_skill', 'skill_name': 'file-processing', 'tool_names': ['file_read', 'file_write']})\n"
                "c3 = await call_tool('configure_skill_tools', {'action': 'list_assignable'})\n"
                "return {'global': c1, 'per_skill': c2, 'assignable': c3}"
            )
        },
    )
    assert not p3_cfg.is_error
    sc = p3_cfg.structured_content or {}
    payload: object = sc.get("result", sc)
    assert _is_str_mapping(payload)
    assert "calculator" in str(payload.get("global"))
    assert "file_read" in str(payload.get("per_skill"))
    assignable = payload.get("assignable")
    assert _is_str_mapping(assignable)
    reg_count = assignable.get("registered_tool_count", 0)
    assert isinstance(reg_count, int) and reg_count >= 150


async def test_skill_subdirectories_references_scripts_assets_and_resources() -> None:
    import os

    from agentskills import (
        build_skill_subdirectory_tools,
        discover_skills,
        scan_skill_resources_by_category,
    )

    assert os.environ.get("BYPASS_TOOL_CONSENT") == "true"

    root_dir = Path(__file__).resolve().parents[3]
    skills = discover_skills(root_dir / "src" / "skills")
    skill_map = {s.name: s for s in skills}

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
        assert not res.is_error, f"Workspace {domain}_workspace failed: {res.content}"
        sc = res.structured_content or {}
        prefab_meta = sc.get("$prefab")
        assert _is_str_mapping(prefab_meta)
        assert prefab_meta.get("version") == "0.3", f"Workspace {domain} missing $prefab 0.3"


async def test_auth_status_and_credentials_configuration(
    mcp_client: Client[ClientTransport],
) -> None:
    res = await mcp_client.call_tool(
        "execute",
        {"code": "return await call_tool('strands_auth_status', {})"},
    )
    assert not res.is_error
    sc = res.structured_content or {}
    payload: object = sc.get("result", sc)
    assert _is_str_mapping(payload)
    rows = payload.get("rows", [])
    assert "strands_google" in str(rows)
    assert "strands_ccxt" in str(rows)


async def test_resources_as_tools_and_prompts_as_tools_inside_code_mode(
    mcp_client: Client[ClientTransport],
) -> None:
    """Verify `ResourcesAsTools` (`list_resources`, `read_resource`) and `PromptsAsTools`
    (`list_prompts`, `get_prompt`) are discoverable and callable inside `execute`.
    """
    schema_res = await mcp_client.call_tool(
        "get_schema",
        {"tools": ["list_resources", "read_resource", "list_prompts", "get_prompt"]},
    )
    assert not schema_res.is_error
    schema_text = str(schema_res.content)
    assert "read_resource" in schema_text
    assert "get_prompt" in schema_text

    exec_res = await mcp_client.call_tool(
        "execute",
        {
            "code": (
                "skill_md = await call_tool('read_resource', {'uri': 'skill://file-processing/SKILL.md'})\n"
                "manifest = await call_tool('read_resource', {'uri': 'skill://file-processing/_manifest'})\n"
                "prompts = await call_tool('list_prompts', {})\n"
                "activated = await call_tool('get_prompt', {'name': 'activate_skill', 'arguments': {'skill_name': 'file-processing', 'task': 'Parse CSV'}})\n"
                "return {'skill_md': skill_md, 'manifest': manifest, 'prompts': prompts, 'activated': activated}"
            )
        },
    )
    assert not exec_res.is_error
    text_out = str(exec_res.structured_content)
    assert "file-processing" in text_out
    assert "process.py" in text_out
    assert "activate_skill" in text_out
    assert "Parse CSV" in text_out


async def test_interactive_apps_and_unbounded_code_mode_limits(
    mcp_client: Client[ClientTransport],
) -> None:
    """Verify interactive app tools (`request_approval`, `choose`, `upload_files`, `list_uploaded_files`,
    `read_uploaded_file`) are registered and CodeMode has no blind 25-call or 100-tool truncation limits.
    """
    schema_res = await mcp_client.call_tool(
        "get_schema",
        {
            "tools": [
                "request_approval",
                "choose",
                "upload_files",
                "list_uploaded_files",
                "read_uploaded_file",
            ]
        },
    )
    assert not schema_res.is_error
    schema_text = str(schema_res.content)
    for app_tool in (
        "request_approval",
        "choose",
        "upload_files",
        "list_uploaded_files",
        "read_uploaded_file",
    ):
        assert app_tool in schema_text

    # Verify > 25 tool calls in a single `execute` script succeed (no 25-call cap)
    # and `configure_skill_tools(action='list_assignable')` returns all registered tools without [:100] slicing
    many_calls_res = await mcp_client.call_tool(
        "execute",
        {
            "code": (
                "results = []\n"
                "for i in range(30):\n"
                "    r = await call_tool('calculator', {'expression': f'{i} + 1'})\n"
                "    results.append(r)\n"
                "assignable = await call_tool('configure_skill_tools', {'action': 'list_assignable'})\n"
                "skills_info = await call_tool('list_available_skills', {'query': 'file-processing'})\n"
                "return {'call_count': len(results), 'assignable': assignable, 'skills_info': skills_info}"
            )
        },
    )
    assert not many_calls_res.is_error
    sc = many_calls_res.structured_content or {}
    payload: object = sc.get("result", sc)
    assert _is_str_mapping(payload)
    assert payload.get("call_count") == 30
    assignable = payload.get("assignable")
    assert _is_str_mapping(assignable)
    sample_list = assignable.get("sample_assignable_tools")
    total_count = assignable.get("total_assignable_tools")
    assert isinstance(sample_list, list)
    assert isinstance(total_count, int) and total_count > 100
    assert len(cast(list[object], sample_list)) == total_count

    skills_info = payload.get("skills_info")
    assert _is_str_mapping(skills_info)
    assert "skill://file-processing/SKILL.md" in str(skills_info)
    assert "skill://file-processing/_manifest" in str(skills_info)


async def test_argument_completion_and_client_skill_utilities(
    mcp_client: Client[ClientTransport],
    tmp_path: Path,
) -> None:
    """Verify native `@server.completion` autocompletes skill names and `skill://` template paths,
    and `strands_client` skill utilities (`list_skills`, `get_skill_manifest`, `download_skill`) work end-to-end.
    """
    import mcp_types
    from strands_client import download_skill, get_skill_manifest, list_skills

    comp_skill = await mcp_client.complete(
        mcp_types.PromptReference(type="ref/prompt", name="activate_skill"),
        argument={"name": "skill_name", "value": "file-proc"},
    )
    assert "file-processing" in comp_skill.values

    comp_path = await mcp_client.complete(
        mcp_types.ResourceTemplateReference(
            type="ref/resource",
            uri="skill://file-processing/{path*}",
        ),
        argument={"name": "path", "value": "scripts/"},
    )
    assert any("process.py" in v for v in comp_path.values)

    summaries = await list_skills(mcp_client)
    names = {s.name for s in summaries}
    assert "file-processing" in names

    manifest = await get_skill_manifest(mcp_client, "file-processing")
    assert manifest.name == "file-processing"
    assert any(f.path == "SKILL.md" for f in manifest.files)

    downloaded_path = await download_skill(mcp_client, "file-processing", tmp_path)
    assert (downloaded_path / "SKILL.md").exists()

