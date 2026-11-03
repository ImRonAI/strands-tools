# pyright: strict
"""Server composition: Strands tool suites + FastMCPApp workspaces behind CodeMode, plus native GenerativeUI.

Mirrors the FastMCP 4.1.0 reference architecture:
- CodeMode (`get_tags`, `search`, `get_schema`, `execute`) lives on the mounted `operations` server with unbounded tool calls and unbounded Monty sandbox limits.
- `ResourcesAsTools` (`list_resources`, `read_resource`) and `PromptsAsTools` (`list_prompts`, `get_prompt`) sit on `operations` before `CodeMode` so `execute()` can inspect `skill://` resources, manifests, and prompts directly inside CodeMode Python scripts.
- Interactive `FastMCPApp` providers (`Approval`, `Choice`, `FileUpload`) sit on `operations` before `CodeMode`.
- `GenerativeUI` (`generate_prefab_ui` + `ui://prefab/generative.html`) is a provider of the root server.
- `TasksExtension` is registered on the root server.
- 14 domain `FastMCPApp` workspaces sit on `operations` before `CodeMode`.
- Native `ResponseCachingMiddleware`, `PingMiddleware`, `TimingMiddleware`, and `@server.completion` argument completion are enabled on the root server.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
for _extra_path in (
    _REPO_ROOT / "src" / "tools",
    _REPO_ROOT / "src",
    _REPO_ROOT / "packages" / "server" / "src",
    _REPO_ROOT / "packages" / "client" / "src",
):
    _extra_str = str(_extra_path)
    if _extra_str not in sys.path:
        sys.path.insert(0, _extra_str)

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env", override=False)
except Exception:
    pass

import mcp_types
from fastmcp import FastMCP
from fastmcp.apps.approval import Approval
from fastmcp.apps.choice import Choice
from fastmcp.apps.file_upload import FileUpload
from fastmcp.apps.generative import GenerativeUI
from fastmcp.experimental.transforms.code_mode import (
    CodeMode,
    GetSchemas,
    GetTags,
    MontySandboxProvider,
    Search,
)
from fastmcp.mcp_config import MCPConfig, RemoteMCPServer, StdioMCPServer
from fastmcp.server import create_proxy
from fastmcp.server.auth import AuthProvider
from fastmcp.server.completions import CompletionReference, CompletionValues
from fastmcp.server.middleware.caching import CallToolSettings, ResponseCachingMiddleware
from fastmcp.server.middleware.ping import PingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools, ToolTransform
from fastmcp.tools.tool_transform import ToolTransformConfig
from fastmcp_tasks import TasksExtension
from starlette.requests import Request
from starlette.responses import JSONResponse

from strands_server.apps import ALL_APPS
from strands_server.catalog_loader import register_catalog_on_operations
from strands_server.runtime.approval_gate import ApprovalGate
from strands_server.runtime.sandbox import prepare_prefab_sandbox_env
from strands_server.runtime.tasks import build_tasks_extension, register_task_tools
from strands_server.skills_provider import get_all_skill_roots

SERVER_NAME = "Strands Tools MCP"
DEFAULT_MAX_TOOL_CALLS: int | None = None
logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """Strands Tools & Agent Factory MCP Server (FastMCP 4.1.0 CodeMode + Agent Skills + Prefab UI).

## 1. Progressive Tool Discovery & Execution (CodeMode)
All 400+ Strands tools, multi-agent orchestrators, interactive apps, and resource/prompt bridges are accessed through four root discovery & execution tools:
1. `get_tags(detail="brief" | "full")`: Browse capability domains (`strands_tools`, `strands_harness`, `skills`, `strands_pack`, `strands_google`, `strands_fun_tools`, `strands_ccxt`, `strands_telegram`, `strands_zero`, `strands_utcp`, `strands_docs`, `strands_inspect`, `ecosystem`).
2. `search(query=..., tags=[...], detail="brief" | "detailed" | "full")`: Find tools by keyword and/or tag filter.
3. `get_schema(tools=[...], detail="detailed" | "full")`: Inspect exact JSON parameter schemas before calling unfamiliar tools.
4. `execute(code="return await call_tool('<tool_name>', {...})")`: Run async Python scripts that chain multiple `await call_tool(...)` calls in a single round-trip.

## 2. Discovering & Using Agent Skills (`skill://` Resources & Skill Tools)
Agent Skills can be discovered and executed in three complementary ways inside `execute`:
- **Catalog & Resource Discovery**:
  - `await call_tool("list_available_skills", {"query": "..."})` returns every skill with its `skill_md_uri` (`skill://{name}/SKILL.md`), `manifest_uri` (`skill://{name}/_manifest`), and `template_uri` (`skill://{name}/{path*}`).
  - `await call_tool("list_resources", {})` and `await call_tool("read_resource", {"uri": "skill://<skill_name>/SKILL.md"})` or `skill://<skill_name>/_manifest` read skill files directly as MCP resources inside `execute`.
- **Pattern #2 (In-Context Skill Loading)**:
  - `await call_tool("skill", {"skill_name": "<name>", "resource_path": "references/..."})` loads the skill's instructions or supporting files into your context.
- **Pattern #3 (Isolated Sub-Agent Execution)**:
  - `await call_tool("use_skill", {"skill_name": "<name>", "request": "<task>", "assigned_tools": ["calculator", ...]})` runs the skill in an isolated sub-agent with its own `references/` KB, `scripts/` sandbox, `assets/`, and assigned Strands tools.
  - `await call_tool("configure_skill_tools", {"action": "inspect" | "assign_skill" | "set_global" | "list_assignable", ...})` configures tools available to skill sub-agents.

## 3. Multi-Agent Orchestration (`create_harness`, `graph`, `workflow`, `swarm`)
- `create_harness`: Build and register a `strands_harness` agent so `graph` nodes can reference it by name.
- `graph`: Heterogeneous DAG orchestrator supporting `agent`, `create_harness`, `use_skill`, `swarm`, `workflow`, and `parallel` nodes.
- `workflow`: Task-DAG orchestration with priorities and dependencies.
- `swarm`: Autonomous handoff-based multi-agent team execution.
"""

EXECUTE_DESCRIPTION = (
    "Execute async Python orchestration code with `await call_tool(tool_name, params_dict)` and return "
    "the final result. Supports chaining any number of tool calls in a single turn, including Strands tools "
    "(`calculator`, `create_harness`, `use_skill`, `skill`, `list_available_skills`, `graph`, `workflow`, `swarm`), "
    "MCP resource bridges (`list_resources`, `read_resource` for `skill://{name}/SKILL.md` and `skill://{name}/_manifest`), "
    "MCP prompt bridges (`list_prompts`, `get_prompt`), and interactive apps (`request_approval`, `choose`, `upload_files`)."
)


def _register_skill_and_orchestration_prompts(operations: FastMCP) -> None:
    """Register native MCP prompts on `operations` for skill activation and multi-agent orchestration."""

    @operations.prompt(
        name="activate_skill",
        description="Load an AgentSkill's SKILL.md instructions and file manifest for in-context or sub-agent execution.",
        tags={"skills", "agent_skills", "prompt"},
    )
    def activate_skill(skill_name: str, task: str = "") -> str:
        for root in get_all_skill_roots(include_vendor_roots=True):
            skill_dir = root / skill_name
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text(encoding="utf-8", errors="replace")
                files = sorted(
                    str(p.relative_to(skill_dir))
                    for p in skill_dir.rglob("*")
                    if p.is_file()
                )
                task_line = f"\n\n## Active Task\n{task}" if task else ""
                return (
                    f"# Activated Skill: `{skill_name}`\n"
                    f"- Resource URI: `skill://{skill_name}/SKILL.md`\n"
                    f"- Manifest URI: `skill://{skill_name}/_manifest`\n"
                    f"- Available Files: {', '.join(files)}\n\n"
                    f"## Skill Instructions (`SKILL.md`)\n{content}"
                    f"{task_line}\n\n"
                    f"## Execution Options in `execute`\n"
                    f"- Read supporting files: `await call_tool('read_resource', {{'uri': 'skill://{skill_name}/<path>'}})`\n"
                    f"- Run as isolated sub-agent: `await call_tool('use_skill', {{'skill_name': '{skill_name}', 'request': '...'}})`"
                )
        return (
            f"Skill '{skill_name}' was not found directly by folder name. "
            f"Call `await call_tool('list_available_skills', {{}})` inside `execute` to list all available skills."
        )

    @operations.prompt(
        name="orchestrate_agents",
        description="Generate a ready-to-run CodeMode Python blueprint for `create_harness`, `use_skill`, `graph`, `workflow`, or `swarm`.",
        tags={"orchestration", "multiagent", "graph", "workflow", "swarm", "harness"},
    )
    def orchestrate_agents(goal: str, pattern: str = "graph") -> str:
        return (
            f"# Multi-Agent Orchestration Blueprint (`{pattern}`)\n"
            f"**Goal**: {goal}\n\n"
            "Run the following inside `execute(code=...)`:\n"
            "```python\n"
            "# 1. Create and register a specialized harness agent\n"
            "await call_tool('create_harness', {\n"
            "    'name': 'specialist',\n"
            "    'instructions': 'You are a domain specialist.',\n"
            "    'model': 'stub',\n"
            "    'include_default_tools': False,\n"
            "    'tools': ['calculator', 'current_time'],\n"
            "})\n\n"
            "# 2. Compose a heterogeneous graph combining create_harness + use_skill\n"
            "await call_tool('graph', {\n"
            "    'action': 'create',\n"
            "    'graph_id': 'mission_graph',\n"
            "    'topology': {\n"
            "        'nodes': [\n"
            "            {'id': 'planner', 'type': 'create_harness', 'harness': 'specialist'},\n"
            "            {'id': 'skill_worker', 'type': 'use_skill', 'skill_name': 'file-processing', 'assigned_tools': ['calculator']},\n"
            "        ],\n"
            "        'edges': [{'from': 'planner', 'to': 'skill_worker'}],\n"
            "        'entry_point': 'planner',\n"
            "    },\n"
            "})\n"
            "result = await call_tool('graph', {\n"
            "    'action': 'execute',\n"
            "    'graph_id': 'mission_graph',\n"
            f"    'task': {goal!r},\n"
            "})\n"
            "return result\n"
            "```"
        )


def _register_completion_handler(target_server: FastMCP) -> None:
    """Register native `@server.completion` argument completion for skill names, skill file paths, and domains."""

    @target_server.completion
    def complete_arguments(
        ref: CompletionReference,
        argument: mcp_types.CompletionArgument,
        context: mcp_types.CompletionContext | None,
    ) -> CompletionValues:
        prefix = argument.value.lower()
        arg_name = argument.name

        if arg_name in ("skill_name", "skill"):
            candidates: list[str] = []
            seen: set[str] = set()
            for root in get_all_skill_roots(include_vendor_roots=True):
                if not root.exists():
                    continue
                for child in sorted(root.iterdir()):
                    if child.is_dir() and (child / "SKILL.md").exists():
                        if child.name not in seen and child.name.lower().startswith(prefix):
                            candidates.append(child.name)
                            seen.add(child.name)
            return candidates

        if isinstance(ref, mcp_types.ResourceTemplateReference) and ref.uri.startswith("skill://"):
            # Template URI format: skill://<skill_name>/{path*}
            uri_body = ref.uri[len("skill://") :]
            skill_slug = uri_body.split("/", 1)[0]
            if context and context.arguments and "skill_name" in context.arguments:
                skill_slug = context.arguments["skill_name"]
            if arg_name in ("path", "resource_path"):
                file_candidates: list[str] = []
                for root in get_all_skill_roots(include_vendor_roots=True):
                    skill_dir = root / skill_slug
                    if skill_dir.exists() and skill_dir.is_dir():
                        for p in sorted(skill_dir.rglob("*")):
                            if p.is_file():
                                rel = str(p.relative_to(skill_dir))
                                if rel.lower().startswith(prefix):
                                    file_candidates.append(rel)
                return file_candidates

        if arg_name in ("pattern", "engine"):
            options = ["graph", "workflow", "swarm", "create_harness", "use_skill"]
            return [o for o in options if o.startswith(prefix)]

        return None


def build_proxied_servers() -> list[tuple[str, FastMCP]]:
    """Build proxies for Telnyx, REA, and founder's servers in src/mcp."""
    proxies: list[tuple[str, FastMCP]] = []

    # 1. Telnyx Remote MCP (FR-M2-3.1)
    telnyx_key = os.environ.get("TELNYX_API_KEY")
    if telnyx_key:
        try:
            cfg = MCPConfig(
                mcpServers={
                    "telnyx": RemoteMCPServer(
                        url="https://api.telnyx.com/v2/mcp",
                        transport="http",
                        auth=telnyx_key,
                    )
                }
            )
            proxies.append(("telnyx", create_proxy(cfg)))
        except Exception as e:
            logger.warning("Failed to build telnyx proxy: %s", e)
    else:
        logger.info("TELNYX_API_KEY not set; skipping telnyx proxy mount")

    # 2. REA stdio proxy (mount only when node binary and built REA node_modules exist)
    try:
        from strands_client.rea_proxy import DEFAULT_REA_DIR, create_rea_proxy

        if shutil.which("node") and (DEFAULT_REA_DIR / "node_modules").exists():
            rea_p = create_rea_proxy()
            if rea_p:
                proxies.append(("rea", rea_p))
    except Exception as e:
        logger.warning("REA proxy not available: %s", e)

    # 3. Founder's servers in src/mcp
    mcp_dir = Path(__file__).resolve().parents[4] / "src" / "mcp"
    if mcp_dir.exists():
        server_dirs = [
            "cagatay_mcp_server",
            "cms-coverage-mcp-server",
            "healthcare-mcp-public",
            "mcp-installer",
            "openapi-mcp",
            "strands_mcp_server",
            "utcp",
        ]
        for sdir_name in server_dirs:
            sdir = mcp_dir / sdir_name
            if not sdir.exists():
                continue
            py_entry = sdir / "server.py"
            if py_entry.exists():
                try:
                    cfg = MCPConfig(
                        mcpServers={
                            sdir_name: StdioMCPServer(
                                command=sys.executable,
                                args=[str(py_entry.resolve())],
                            )
                        }
                    )
                    proxies.append((sdir_name, create_proxy(cfg)))
                except Exception as e:
                    logger.warning("Failed to mount %s: %s", sdir_name, e)

    return proxies


def build_operations(
    *,
    max_tool_calls: int | None = DEFAULT_MAX_TOOL_CALLS,
    mask_error_details: bool | None = None,
) -> FastMCP:
    """All Strands tools, Agent Skills resources/prompts, and FastMCPApp workspaces, discoverable through native CodeMode."""
    operations = FastMCP("Strands operations", mask_error_details=mask_error_details)
    register_catalog_on_operations(operations)
    _register_skill_and_orchestration_prompts(operations)
    _register_completion_handler(operations)

    # Mount proxied servers (Telnyx, REA, founder servers)
    for namespace, proxy in build_proxied_servers():
        try:
            operations.mount(proxy, namespace=namespace)
        except Exception as e:
            logger.warning("Failed to mount %s on operations: %s", namespace, e)

    for domain_app in ALL_APPS:
        operations.add_provider(domain_app)

    # Add native FastMCP 4.1.0 interactive App providers (Approval, Choice, FileUpload with no artificial size/TTL limits)
    operations.add_provider(Approval())
    operations.add_provider(Choice())
    operations.add_provider(
        FileUpload(
            max_file_size=1024 * 1024 * 1024,
            max_total_size=None,
            file_ttl_seconds=None,
        )
    )

    register_task_tools(operations)

    # Expose MCP resources (`skill://*/SKILL.md`, `skill://*/_manifest`, `skill://*/*`) and prompts as tools inside CodeMode
    operations.add_transform(ResourcesAsTools(operations))
    operations.add_transform(PromptsAsTools(operations))
    operations.add_transform(
        ToolTransform(
            {
                "list_resources": ToolTransformConfig(
                    description=(
                        "List all MCP resources and `skill://` resource templates (including `skill://{name}/SKILL.md`, "
                        "`skill://{name}/_manifest`, and `skill://{name}/{path*}`)."
                    ),
                    tags={"skills", "resources", "agent_skills", "discovery"},
                ),
                "read_resource": ToolTransformConfig(
                    description=(
                        "Read any MCP resource or `skill://` URI (e.g. `skill://file-processing/SKILL.md`, "
                        "`skill://file-processing/_manifest`, or `skill://file-processing/references/guide.md`)."
                    ),
                    tags={"skills", "resources", "agent_skills", "read"},
                ),
                "list_prompts": ToolTransformConfig(
                    description="List all reusable MCP prompts (including `activate_skill` and `orchestrate_agents`).",
                    tags={"prompts", "skills", "orchestration", "discovery"},
                ),
                "get_prompt": ToolTransformConfig(
                    description="Render an MCP prompt by `name` and optional `arguments` dict.",
                    tags={"prompts", "skills", "orchestration"},
                ),
            }
        )
    )

    operations.add_transform(
        CodeMode(
            discovery_tools=[GetTags(name="get_tags"), Search(), GetSchemas()],
            max_tool_calls=max_tool_calls,
            sandbox_provider=MontySandboxProvider(limits=None),
            execute_description=EXECUTE_DESCRIPTION,
        )
    )
    return operations


def build_server(
    *,
    auth: AuthProvider | None = None,
    tasks: TasksExtension | None = None,
    max_tool_calls: int | None = DEFAULT_MAX_TOOL_CALLS,
    mask_error_details: bool | None = None,
) -> FastMCP:
    """Build the model-facing server: `get_tags`, `search`, `get_schema`, `execute`, `generate_prefab_ui`."""
    prepare_prefab_sandbox_env()
    server = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        auth=auth,
        providers=[GenerativeUI()],
        mask_error_details=mask_error_details,
        cache_ttl=300,
        cache_scope="public",
    )

    # Register root Money Approval Gate middleware (CAT-115) + FastMCP 4.1.0 performance/connection middlewares
    server.add_middleware(ApprovalGate())
    server.add_middleware(
        ResponseCachingMiddleware(
            call_tool_settings=CallToolSettings(enabled=False),
            max_item_size=100 * 1024 * 1024,
        )
    )
    server.add_middleware(PingMiddleware())
    server.add_middleware(TimingMiddleware())

    _register_completion_handler(server)

    @server.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy"})

    @server.custom_route("/ready", methods=["GET"])
    async def ready(_: Request) -> JSONResponse:
        proxied_names = [ns for ns, _ in build_proxied_servers()]
        return JSONResponse({"status": "ready", "mounted_proxies": proxied_names})

    server.add_extension(tasks if tasks is not None else build_tasks_extension())
    server.mount(
        build_operations(
            max_tool_calls=max_tool_calls,
            mask_error_details=mask_error_details,
        )
    )
    return server
