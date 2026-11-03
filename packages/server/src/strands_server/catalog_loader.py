# pyright: strict
"""Native FastMCP 4.1.0 tool registration for Strands capabilities and `@tool` suites.

Uses only native FastMCP 4.1.0 primitives verified against installed `fastmcp==4.1.0`:
- `Tool.from_function`: `fastmcp/tools/base.py:293-336` (`FunctionTool.from_function` at `fastmcp/tools/function_tool.py:261-409`)
- `Tool.from_tool`: `fastmcp/tools/base.py:338-388` (`TransformedTool.from_tool` at `fastmcp/tools/tool_transform.py:424-629`)
- `ArgTransform`: `fastmcp/tools/tool_transform.py:67-160`
- `ToolTransform` & `ToolTransformConfig`: `fastmcp/server/transforms/tool_transform.py:34-92` & `fastmcp/tools/tool_transform.py:300-420`
- `FastMCP.add_tool` & `FastMCP.add_transform`: `fastmcp/server/server.py:1143, 1244`
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Annotated, Literal, cast

from fastmcp import FastMCP
from fastmcp.server.transforms import ToolTransform
from fastmcp.tools.base import Tool
from fastmcp.tools.tool_transform import ArgTransform, ToolTransformConfig
from mcp_types import ToolAnnotations
from pydantic import Field
from strands_harness.types.agent import Effort

logger = logging.getLogger(__name__)
PromptMode = Literal["default", "minimal", "append", "none"]

os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_DIR = REPO_ROOT / "src"
TOOLS_DIR = SRC_DIR / "tools"
STRANDS_TOOLS_ECOSYSTEM_DIR = SRC_DIR / "strands_tools"
SKILLS_DIR = SRC_DIR / "skills"
SAMPLE_SKILLS_DIR = (
    STRANDS_TOOLS_ECOSYSTEM_DIR / "sessions_and_skills" / "sample_agent_skills" / "skills"
)


def _ensure_sys_paths() -> None:
    """Ensure local Strands source directories are importable with `src/tools` first."""
    candidate_paths = [
        TOOLS_DIR,
        SRC_DIR,
        STRANDS_TOOLS_ECOSYSTEM_DIR / "sessions_and_skills" / "sample_agent_skills",
    ]
    if STRANDS_TOOLS_ECOSYSTEM_DIR.exists():
        for category_dir in sorted(STRANDS_TOOLS_ECOSYSTEM_DIR.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
                continue
            for pkg_dir in sorted(category_dir.iterdir()):
                if not pkg_dir.is_dir() or pkg_dir.name.startswith((".", "_")):
                    continue
                src_sub = pkg_dir / "src"
                candidate_paths.append(src_sub if src_sub.exists() else pkg_dir)

    for p in reversed(candidate_paths):
        p_str = str(p)
        if p.exists():
            if p_str in sys.path:
                sys.path.remove(p_str)
            sys.path.insert(0, p_str)

    # Ensure `strands_tools` package path includes `src/tools/strands_tools`
    agent_tools_pkg = str(TOOLS_DIR / "strands_tools")
    if "strands_tools" in sys.modules:
        st_mod = sys.modules["strands_tools"]
        st_path_raw: object = getattr(st_mod, "__path__", None)
        if isinstance(st_path_raw, list):
            st_path = cast(list[str], st_path_raw)
            if agent_tools_pkg not in st_path:
                st_path.insert(0, agent_tools_pkg)


_ensure_sys_paths()

EXCLUDED_STRANDS_PACK_GOOGLE_MODULES: frozenset[str] = frozenset(
    {
        "calendar",
        "docs",
        "drive",
        "forms",
        "gmail",
        "google_auth",
        "google_calendar",
        "google_docs",
        "google_drive",
        "google_forms",
        "google_sheets",
        "google_tasks",
        "sheets",
        "tasks",
        "gemini_image",
        "gemini_music",
        "gemini_video",
        "gemini_Thinking",
        "gemini_thinking",
    }
)


def _load_module_from_file(module_name: str, file_path: Path) -> object | None:
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        logger.debug("Skipping module %s (%s): %s", module_name, file_path, exc)
        return None


def _build_native_tool(
    tool_obj: object,
    *,
    name: str,
    domain_suite: str,
    description: str | None = None,
    tags: Iterable[str] = (),
    annotations: ToolAnnotations | None = None,
) -> Tool | None:
    """Register a Strands `@tool` function or Python callable via native `Tool.from_function` and `Tool.from_tool`."""
    fn_candidate: object = getattr(tool_obj, "_tool_func", tool_obj)
    if not callable(fn_candidate):
        return None
    tag_set = {domain_suite, *tags}
    meta: dict[str, object] = {"domain_suite": domain_suite}
    try:
        base_tool = Tool.from_function(
            fn_candidate,
            name=name,
            description=description,
            tags=tag_set,
            annotations=annotations,
            meta=meta,
        )
    except Exception as exc:
        logger.debug("Skipping %s (not compatible with Tool.from_function): %s", name, exc)
        return None

    props = base_tool.parameters.get("properties")
    arg_transforms: dict[str, ArgTransform] = {}
    if isinstance(props, Mapping):
        for hidden_param in ("agent", "tool_context"):
            if hidden_param in props:
                arg_transforms[hidden_param] = ArgTransform(hide=True, default=None)

    if arg_transforms or description is not None:
        return Tool.from_tool(
            base_tool,
            name=name,
            description=description or base_tool.description,
            tags=tag_set,
            annotations=annotations,
            meta=meta,
            transform_args=arg_transforms if arg_transforms else None,
        )
    return base_tool


def _collect_decorated_tools_from_module(
    mod: object,
    *,
    domain_suite: str,
    default_tags: Iterable[str] = (),
    prefix: str = "",
) -> tuple[ list[Tool], dict[str, object] ]:
    """Collect `@tool`-decorated functions from a Python module using `Tool.from_function`."""
    tools: list[Tool] = []
    raw_map: dict[str, object] = {}
    seen: set[str] = set()
    for attr_name in dir(mod):
        if attr_name.startswith("_"):
            continue
        attr: object = getattr(mod, attr_name, None)
        if attr is None or not hasattr(attr, "_tool_func"):
            continue
        raw_name = str(getattr(attr, "tool_name", getattr(attr, "__name__", attr_name)))
        reg_name = f"{prefix}{raw_name}" if prefix and not raw_name.startswith(prefix) else raw_name
        if reg_name in seen:
            continue
        native = _build_native_tool(
            attr,
            name=reg_name,
            domain_suite=domain_suite,
            tags=default_tags,
        )
        if native is not None:
            tools.append(native)
            raw_map[reg_name] = attr
            seen.add(reg_name)
    return tools, raw_map


def _build_create_harness_tool() -> tuple[Tool, Callable[..., object]]:
    """Build the native FastMCP `create_harness` tool wrapping `strands_harness.create_harness`."""
    from agentskills.tool.agent_skill import register_available_tools
    from strands_harness import create_harness as sdk_create_harness

    from strands_graph_tool.agent_factory import register_agent_config, register_factory_tools
    from strands_graph_tool.graph import get_model_factories

    async def create_harness(
        name: Annotated[
            str,
            Field(
                description="Unique name for the harness agent (used to reference this agent in `graph` nodes)."
            ),
        ] = "harness_agent",
        instructions: Annotated[
            str | None,
            Field(description="System prompt or instructions for the harness agent."),
        ] = None,
        description: Annotated[
            str | None,
            Field(description="Short description of the harness agent's role for subagent/graph routing."),
        ] = None,
        model: Annotated[
            str | None,
            Field(
                description="Model identifier (e.g. 'google/gemini-4-argon', 'gemini-3.8-flash', or 'stub')."
            ),
        ] = None,
        workspace: Annotated[
            str | None,
            Field(description="Optional workspace directory path for file, bash, and memory tools."),
        ] = None,
        prompt_mode: Annotated[
            PromptMode,
            Field(description="Harness system prompt mode: 'default', 'minimal', 'Append', or 'none'."),
        ] = "default",
        effort: Annotated[
            Effort,
            Field(description="Reasoning effort level ('auto', 'minimal', 'low', 'medium', 'high', 'max')."),
        ] = "auto",
        include_default_tools: Annotated[
            bool,
            Field(description="Whether to attach default harness tools (read, write, edit, bash, glob, grep)."),
        ] = True,
        skills: Annotated[
            list[str] | bool | None,
            Field(description="Skill directories or True/False to enable harness skills."),
        ] = None,
        tools: Annotated[
            list[str] | None,
            Field(description="Additional registered Strands tool names to attach to this harness agent."),
        ] = None,
        session: Annotated[
            str | bool,
            Field(description="Session persistence setting (False for stateless sub-agent execution in graphs)."),
        ] = False,
        memory: Annotated[
            str | bool,
            Field(description="Whether to enable harness persistent memory."),
        ] = False,
        task: Annotated[
            str | None,
            Field(
                description="Optional task prompt to execute immediately with the created harness agent."
            ),
        ] = None,
    ) -> dict[str, object]:
        """Build a `strands_harness` Agent from arguments, register it for `graph` node resolution, and optionally execute a task."""
        from strands_graph_tool.agent_factory import resolve_agent_tools

        resolved_extra_tools = resolve_agent_tools(tools) if tools else None
        factories = get_model_factories()
        resolved_model: object = model
        builtin_tools: dict[str, object] | list[str] | None = None
        if isinstance(model, str) and model in factories:
            resolved_model = factories[model]()
            if not include_default_tools:
                builtin_tools = []
            else:
                builtin_tools = {"web_search": False}
        elif not include_default_tools:
            builtin_tools = []

        effective_desc = description or (
            instructions.splitlines()[0] if instructions else f"Harness agent {name}"
        )

        harness_kwargs: dict[str, object] = {
            "name": name,
            "description": effective_desc,
            "instructions": instructions,
            "effort": effort,
            "skills": skills if skills is not None else False,
            "tools": resolved_extra_tools,
            "session": session,
            "memory": memory,
            "callback_handler": None,
        }
        if resolved_model is not None:
            harness_kwargs["model"] = resolved_model
        if builtin_tools is not None:
            harness_kwargs["builtin_tools"] = builtin_tools

        create_fn = cast(Callable[..., object], sdk_create_harness)
        agent_obj = create_fn(**harness_kwargs)

        cfg_record: dict[str, object] = {
            "id": name,
            "name": name,
            "engine": "harness",
            "description": effective_desc,
            "instructions": instructions or "",
            "prompt_mode": prompt_mode,
            "effort": effort,
            "include_default_tools": include_default_tools,
        }
        if model is not None:
            cfg_record["model_id"] = model
        if workspace is not None:
            cfg_record["workspace"] = workspace
        if tools is not None:
            cfg_record["tools"] = list(tools)
        register_agent_config(name, cfg_record)

        as_tool_fn = getattr(agent_obj, "as_tool", None)
        if callable(as_tool_fn):
            subagent_tool: object = as_tool_fn(
                name=name,
                description=effective_desc,
                preserve_context=False,
            )
            register_available_tools({name: subagent_tool})
            register_factory_tools({name: subagent_tool})

        raw_tool_names: object = getattr(agent_obj, "tool_names", [])
        tool_names = (
            [str(t) for t in cast(Iterable[object], raw_tool_names)]
            if isinstance(raw_tool_names, Iterable)
            else []
        )
        result_payload: dict[str, object] = {
            "status": "success",
            "agent_name": name,
            "engine": "strands_harness",
            "description": effective_desc,
            "tool_names": tool_names,
            "registered_for_graph": True,
        }

        if task is not None and task.strip():
            stream_fn = getattr(agent_obj, "stream_async", None)
            if callable(stream_fn):
                final_res: object = None
                stream_iter = cast(
                    Iterable[object],
                    stream_fn(task),
                )
                if hasattr(stream_iter, "__aiter__"):
                    from collections.abc import AsyncIterable

                    async for event in cast(AsyncIterable[object], stream_iter):
                        if isinstance(event, Mapping) and "result" in event:
                            final_res = cast(Mapping[str, object], event)["result"]
                result_payload["output"] = str(final_res).strip() if final_res is not None else ""

        return result_payload

    tool_instance = Tool.from_function(
        create_harness,
        name="create_harness",
        description=(
            "Build a `strands_harness` Agent from arguments (`name`, `instructions`, `model`, `workspace`, "
            "`prompt_mode`, `effort`, `include_default_tools`, `skills`, `tools`), register it for `graph` "
            "node execution, and optionally run a `task`."
        ),
        tags={"strands_harness", "harness", "agent", "factory", "create_harness"},
        meta={"domain_suite": "strands_harness"},
    )
    return tool_instance, create_harness


def _load_skills_tools(
    raw_tool_registry: Mapping[str, object],
) -> tuple[list[Tool], dict[str, object]]:
    """Discover all workspace skills, call `configure_skills` on `strands_graph_tool`, and build native skill tools."""
    from agentskills import (
        assign_tools_to_skill,
        create_skill_agent_tool,
         create_skill_tool,
        discover_skills,
        get_assigned_skill_tools,
        register_available_tools,
        set_default_skill_tools,
    )

    from strands_graph_tool.agent_factory import register_factory_tools
    from strands_graph_tool.graph import StubModel, configure_skills
    from strands_server.skills_provider import get_all_skill_roots

    register_available_tools(dict(raw_tool_registry))
    register_factory_tools(raw_tool_registry)

    all_skills: dict[str, object] = {}
    for folder in get_all_skill_roots(include_vendor_roots=True):
        if folder.exists():
            for s in discover_skills(folder):
                if s.name not in all_skills:
                    all_skills[s.name] = s

    skills_list = list(all_skills.values())
    primary_dir = SKILLS_DIR if SKILLS_DIR.exists() else SAMPLE_SKILLS_DIR

    default_skill_tool_names = ["calculator", "current_time", "file_read", "file_write"]
    default_skill_tools = [
        raw_tool_registry[n] for n in default_skill_tool_names if n in raw_tool_registry
    ]

    configure_skills(
        skills_list,
        base_agent_model=StubModel("stub_skill"),
        additional_tools=default_skill_tools,
    )

    tools: list[Tool] = []
    raw_map: dict[str, object] = {}

    if skills_list:
        from agentskills.models import SkillProperties

        typed_skills = [cast(SkillProperties, s) for s in skills_list]
        skill_tool_obj: object = create_skill_tool(typed_skills, primary_dir)
        use_skill_obj: object = create_skill_agent_tool(
            typed_skills,
            primary_dir,
            base_agent_model=StubModel("stub_skill"),
            additional_tools=default_skill_tools,
            tool_registry=dict(raw_tool_registry),
        )
        register_available_tools({"skill": skill_tool_obj, "use_skill": use_skill_obj})
        register_factory_tools({"skill": skill_tool_obj, "use_skill": use_skill_obj})

        skill_native = _build_native_tool(
            skill_tool_obj,
            name="skill",
            domain_suite="skills",
            description="Load instructions and metadata for a specialized AgentSkill on-demand (Pattern #2).",
            tags={"skills", "agent_skills", "pattern2"},
            annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        )
        if skill_native is not None:
            tools.append(skill_native)
            raw_map["skill"] = skill_tool_obj

        use_skill_native = _build_native_tool(
            use_skill_obj,
            name="use_skill",
            domain_suite="skills",
            description=(
                "Execute a specialized AgentSkill in an isolated sub-agent (Pattern #3) with its own "
                "context, system prompt, `references/` KB, `scripts/` sandbox, `assets/` tools, and "
                "`assigned_tools` from the Strands tool registry."
            ),
            tags={"skills", "agent_skills", "subagent", "pattern3", "use_skill"},
        )
        if use_skill_native is not None:
            tools.append(use_skill_native)
            raw_map["use_skill"] = use_skill_obj

    def configure_skill_tools(
        action: Annotated[
            str,
            Field(
                description="One of 'inspect', 'assign_skill', 'set_global', or 'list_assignable'."
            ),
        ] = "inspect",
        skill_name: Annotated[
            str | None,
            Field(description="Target skill name when action='assign_skill' or 'inspect'."),
        ] = None,
        tool_names: Annotated[
            list[str] | None,
            Field(description="List of registered Strands tool names to assign to the skill sub-agent."),
        ] = None,
        append: Annotated[
            bool,
            Field(description="If True, append to existing per-skill tools instead of replacing."),
        ] = False,
    ) -> dict[str, object]:
        """Configure or inspect tools assigned to Pattern #3 `use_skill` isolated skill sub-agents."""
        if action == "list_assignable":
            info = get_assigned_skill_tools()
            available_raw: object = info.get("available_registry_tools", [])
            available_list = (
                [str(x) for x in cast(Iterable[object], available_raw)]
                if isinstance(available_raw, Iterable)
                else []
            )
            return {
                "registered_tool_count": info.get("registered_tool_count", 0),
                "sample_assignable_tools": available_list,
                "assignable_tools": available_list,
                "total_assignable_tools": len(available_list),
            }
        if action == "set_global":
            assigned = set_default_skill_tools(list(tool_names or []))
            return {"status": "updated_global_defaults", "default_additional_tools": assigned}
        if action == "assign_skill":
            if not skill_name:
                raise ValueError("`skill_name` is required when action='assign_skill'.")
            assigned = assign_tools_to_skill(skill_name, list(tool_names or []), append=append)
            return {"status": "updated_skill_tools", "skill_name": skill_name, "assigned_tools": assigned}
        return dict(get_assigned_skill_tools(skill_name))

    def list_available_skills(
        query: Annotated[
            str | None,
            Field(description="Optional substring filter on skill name or description."),
        ] = None,
    ) -> dict[str, object]:
        """List all discovered AgentSkills available to `skill`, `use_skill`, `read_resource` (`skill://`), and `graph` nodes."""
        q = (query or "").strip().lower()
        rows: list[dict[str, object]] = []
        for s in skills_list:
            s_name = str(getattr(s, "name", ""))
            s_desc = str(getattr(s, "description", ""))
            s_dir = str(getattr(s, "skill_dir", ""))
            if q and q not in s_name.lower() and q not in s_desc.lower():
                continue
            rows.append(
                {
                    "name": s_name,
                    "description": s_desc,
                    "skill_dir": s_dir,
                    "allowed_tools": getattr(s, "allowed_tools", None),
                    "skill_md_uri": f"skill://{s_name}/SKILL.md",
                    "manifest_uri": f"skill://{s_name}/_manifest",
                    "template_uri": f"skill://{s_name}/{{path*}}",
                }
            )
        return {"count": len(rows), "skills": rows}

    cfg_tool = Tool.from_function(
        configure_skill_tools,
        name="configure_skill_tools",
        tags={"skills", "agent_skills", "configuration"},
        meta={"domain_suite": "skills"},
    )
    list_tool = Tool.from_function(
        list_available_skills,
        name="list_available_skills",
        tags={"skills", "agent_skills", "discovery"},
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        meta={"domain_suite": "skills"},
    )
    tools.extend([cfg_tool, list_tool])
    raw_map["configure_skill_tools"] = configure_skill_tools
    raw_map["list_available_skills"] = list_available_skills
    return tools, raw_map


def build_core_capability_transforms() -> ToolTransform:
    """Return a native FastMCP `ToolTransform` enriching core orchestration and skill capabilities on `operations`."""
    return ToolTransform(
        {
            "create_harness": ToolTransformConfig(
                description=(
                    "Build a `strands_harness` agent from arguments (`name`, `instructions`, `model`, "
                    "`workspace`, `prompt_mode`, `effort`, `include_default_tools`, `skills`, `tools`), "
                    "register it so `graph` nodes can reference it by name, and optionally execute a `task`."
                ),
                tags={"strands_harness", "harness", "agent", "factory", "create_harness"},
            ),
            "use_skill": ToolTransformConfig(
                description=(
                    "Run a specialized skill as an isolated sub-agent (Pattern #3) with its own context, "
                    "system prompt, `references/` knowledge base, `scripts/` sandbox, `assets/` tools, "
                    "and `assigned_tools`."
                ),
                tags={"skills", "skill", "agent_skills", "subagent", "use_skill"},
            ),
            "skill": ToolTransformConfig(
                description=(
                    "Load the full `SKILL.md` instructions, metadata, or a specific `resource_path` "
                    "(`references/`, `scripts/`, `assets/`) for any discovered AgentSkill on-demand (Pattern #2)."
                ),
                tags={"skills", "skill", "agent_skills", "pattern2", "instructions"},
            ),
            "list_available_skills": ToolTransformConfig(
                description=(
                    "List all discovered AgentSkills with their `name`, `description`, `skill_dir`, "
                    "`skill_md_uri` (`skill://{name}/SKILL.md`), `manifest_uri` (`skill://{name}/_manifest`), "
                    "and `template_uri` (`skill://{name}/{path*}`)."
                ),
                tags={"skills", "skill", "agent_skills", "discovery", "manifest"},
            ),
            "configure_skill_tools": ToolTransformConfig(
                description=(
                    "Inspect or configure tools assigned to Pattern #3 `use_skill` sub-agents "
                    "(`action`: 'inspect', 'assign_skill', 'set_global', 'list_assignable')."
                ),
                tags={"skills", "skill", "agent_skills", "configuration"},
            ),
            "graph": ToolTransformConfig(
                description=(
                    "Build and execute heterogeneous multi-agent graphs (`action`: 'create', 'execute', "
                    "'status', 'list', 'delete'). Node types (`agent`, `use_skill`, `skill_node`, "
                    "`create_harness`, `harness`, `swarm`, `workflow`, `parallel`, `graph`) can reference "
                    "agents created by `create_harness` and skills run via `use_skill`."
                ),
                tags={"strands_tools", "graph", "multiagent", "orchestration", "dag"},
            ),
            "workflow": ToolTransformConfig(
                description=(
                    "Task-DAG workflow orchestration tool (`action`: 'create', 'start', 'list', 'status', "
                    "'delete', 'pause', 'resume') with dependency resolution, priorities, and parallel execution."
                ),
                tags={"strands_tools", "workflow", "dag", "tasks", "orchestration"},
            ),
            "swarm": ToolTransformConfig(
                description=(
                    "Handoff-based multi-agent team (`Swarm`) execution with shared working memory, "
                    "autonomous agent-to-agent handoffs, timeouts, and repetitive handoff detection."
                ),
                tags={"strands_tools", "swarm", "multiagent", "handoff", "team"},
            ),
        }
    )


_TOOL_CACHE: dict[str, list[Tool]] = {}


def load_all_strands_tools(*, force_reload: bool = False) -> list[Tool]:
    """Load all native `@tool` functions across the workspace using `Tool.from_function` and `Tool.from_tool`."""
    if "tools" in _TOOL_CACHE and not force_reload:
        return list(_TOOL_CACHE["tools"])

    _ensure_sys_paths()
    tools_by_name: dict[str, Tool] = {}
    raw_registry: dict[str, object] = {}

    def _add(tool_item: Tool, raw_obj: object | None = None) -> None:
        if tool_item.name not in tools_by_name:
            tools_by_name[tool_item.name] = tool_item
        if raw_obj is not None and tool_item.name not in raw_registry:
            raw_registry[tool_item.name] = raw_obj

    # 1. Core capability: create_harness (strands_harness)
    harness_tool, harness_fn = _build_create_harness_tool()
    _add(harness_tool, harness_fn)

    # Also register native `@tool` functions from strands_harness.tools (e.g. web_search, exa_web_search)
    for mod_name in ("strands_harness.tools.web_search", "strands_harness.tools.exa_search"):
        try:
            h_mod = importlib.import_module(mod_name)
            h_tools, h_raw = _collect_decorated_tools_from_module(
                h_mod,
                domain_suite="strands_harness",
                default_tags={"strands_harness", "harness"},
            )
            for t in h_tools:
                _add(t, h_raw.get(t.name))
        except Exception as exc:
            logger.debug("Skipping %s: %s", mod_name, exc)

    # 2. Core capabilities: graph (from strands_graph_tool), workflow, swarm (from strands_tools)
    from strands_graph_tool import agent_from_config, graph as graph_tool_obj

    graph_native = _build_native_tool(
        graph_tool_obj,
        name="graph",
        domain_suite="strands_tools",
        description=(
            "Build and execute heterogeneous multi-agent graphs (`action`: 'create', 'execute', 'status', "
            "'list', 'delete') supporting `agent`, `use_skill`, `create_harness`, `swarm`, `workflow`, "
            "and `parallel` nodes."
        ),
        tags={"strands_tools", "graph", "multiagent", "orchestration", "dag"},
    )
    if graph_native is not None:
        _add(graph_native, graph_tool_obj)

    afc_native = _build_native_tool(
        agent_from_config,
        name="agent_from_config",
        domain_suite="strands_tools",
        tags={"strands_tools", "agent", "factory", "config"},
    )
    if afc_native is not None:
        _add(afc_native, agent_from_config)

    # 3. Strands Agent Tools (`src/tools/strands_tools`)
    agent_tools_dir = TOOLS_DIR / "strands_tools"
    if agent_tools_dir.exists():
        for py_file in sorted(agent_tools_dir.glob("*.py")):
            if py_file.name.startswith("_") or py_file.stem == "graph":
                continue
            try:
                mod = importlib.import_module(f"strands_tools.{py_file.stem}")
            except Exception:
                mod = _load_module_from_file(f"strands_tools.{py_file.stem}", py_file)
            if mod is None:
                continue
            m_tools, m_raw = _collect_decorated_tools_from_module(
                mod,
                domain_suite="strands_tools",
                default_tags={"strands_tools", "agent_tools", py_file.stem},
            )
            for t in m_tools:
                _add(t, m_raw.get(t.name))

    # 4. Strands Google (`src/tools/strands_google`)
    try:
        import strands_google

        g_tools, g_raw = _collect_decorated_tools_from_module(
            strands_google,
            domain_suite="strands_google",
            default_tags={"strands_google", "google", "workspace"},
        )
        for t in g_tools:
            _add(t, g_raw.get(t.name))
    except Exception as exc:
        logger.debug("Skipping strands_google: %s", exc)

    # 5. Strands Fun Tools (`src/tools/strands_fun_tools`)
    fun_dir = TOOLS_DIR / "strands_fun_tools"
    if fun_dir.exists():
        for py_file in sorted(fun_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"strands_fun_tools.{py_file.stem}")
            except Exception:
                mod = _load_module_from_file(f"strands_fun_tools.{py_file.stem}", py_file)
            if mod is None:
                continue
            f_tools, f_raw = _collect_decorated_tools_from_module(
                mod,
                domain_suite="strands_fun_tools",
                default_tags={"strands_fun_tools", "fun", py_file.stem},
            )
            for t in f_tools:
                _add(t, f_raw.get(t.name))

    # 6. Strands Pack (`src/tools/strands_pack`)
    pack_dir = TOOLS_DIR / "strands_pack"
    if pack_dir.exists():
        for py_file in sorted(pack_dir.glob("*.py")):
            if py_file.name.startswith("_") or py_file.stem in EXCLUDED_STRANDS_PACK_GOOGLE_MODULES:
                continue
            try:
                mod = importlib.import_module(f"strands_pack.{py_file.stem}")
            except Exception:
                mod = _load_module_from_file(f"strands_pack.{py_file.stem}", py_file)
            if mod is None:
                continue
            p_tools, p_raw = _collect_decorated_tools_from_module(
                mod,
                domain_suite="strands_pack",
                default_tags={"strands_pack", py_file.stem},
            )
            for t in p_tools:
                _add(t, p_raw.get(t.name))
            stem_attr: object = getattr(mod, py_file.stem, None)
            if stem_attr is not None and py_file.stem not in tools_by_name:
                alias_tool = _build_native_tool(
                    stem_attr,
                    name=py_file.stem,
                    domain_suite="strands_pack",
                    tags={"strands_pack", py_file.stem},
                )
                if alias_tool is not None:
                    _add(alias_tool, stem_attr)

    # 7. Strands Telegram & Telegram Listener
    for mod_name in ("strands_telegram", "strands_telegram_listener"):
        try:
            mod = importlib.import_module(mod_name)
            tg_tools, tg_raw = _collect_decorated_tools_from_module(
                mod,
                domain_suite="strands_telegram",
                default_tags={"strands_telegram", "telegram"},
            )
            for t in tg_tools:
                _add(t, tg_raw.get(t.name))
        except Exception as exc:
            logger.debug("Skipping %s: %s", mod_name, exc)

    # 8. Strands Zero (`src/tools/strands_zero`)
    try:
        mod = importlib.import_module("strands_zero.tools")
        z_tools, z_raw = _collect_decorated_tools_from_module(
            mod,
            domain_suite="strands_zero",
            default_tags={"strands_zero", "zero"},
        )
        for t in z_tools:
            _add(t, z_raw.get(t.name))
    except Exception as exc:
        logger.debug("Skipping strands_zero: %s", exc)

    # 9. Strands UTCP (`src/tools/strands_utcp`)
    try:
        mod = importlib.import_module("strands_utcp")
        u_tools, u_raw = _collect_decorated_tools_from_module(
            mod,
            domain_suite="strands_utcp",
            default_tags={"strands_utcp", "utcp"},
        )
        for t in u_tools:
            _add(t, u_raw.get(t.name))
    except Exception as exc:
        logger.debug("Skipping strands_utcp: %s", exc)

    # 10. Strands Docs (`src/tools/strands_docs_mcp`)
    try:
        mod = importlib.import_module("strands_docs_mcp.server")
        for doc_fn_name in ("search_docs", "fetch_doc"):
            doc_fn: object = getattr(mod, doc_fn_name, None)
            if doc_fn is not None:
                doc_tool = _build_native_tool(
                    doc_fn,
                    name=doc_fn_name,
                    domain_suite="strands_docs",
                    tags={"strands_docs", "docs"},
                )
                if doc_tool is not None:
                    _add(doc_tool, doc_fn)
    except Exception as exc:
        logger.debug("Skipping strands_docs_mcp: %s", exc)

    # 11. Strands CCXT (`src/tools/strands_ccxt`)
    try:
        mod = importlib.import_module("strands_ccxt")
        c_tools, c_raw = _collect_decorated_tools_from_module(
            mod,
            domain_suite="strands_ccxt",
            default_tags={"strands_ccxt", "ccxt", "crypto"},
        )
        for t in c_tools:
            _add(t, c_raw.get(t.name))
    except Exception as exc:
        logger.debug("Skipping strands_ccxt: %s", exc)

    # 12. Strands Inspect (`src/tools/strands_inspect`)
    try:
        mod = importlib.import_module("strands_inspect._tool")
        i_tools, i_raw = _collect_decorated_tools_from_module(
            mod,
            domain_suite="strands_inspect",
            default_tags={"strands_inspect", "inspect"},
        )
        for t in i_tools:
            _add(t, i_raw.get(t.name))
    except Exception as exc:
        logger.debug("Skipping strands_inspect: %s", exc)

    # 13. Additional native `@tool` packages in `src/tools/strands_*`
    _core_tool_dirs = {
        "strands",
        "agentskills",
        "strands_tools",
        "strands_google",
        "strands_fun_tools",
        "strands_pack",
        "strands_telegram",
        "strands_telegram_listener",
        "strands_zero",
        "strands_utcp",
        "strands_docs_mcp",
        "strands_ccxt",
        "strands_inspect",
        "strands_harness",
    }
    for pkg_dir in sorted(TOOLS_DIR.iterdir()):
        if not pkg_dir.is_dir() or pkg_dir.name.startswith("_") or pkg_dir.name in _core_tool_dirs:
            continue
        try:
            mod = importlib.import_module(pkg_dir.name)
            e_tools, e_raw = _collect_decorated_tools_from_module(
                mod,
                domain_suite="ecosystem",
                default_tags={"ecosystem", pkg_dir.name},
            )
            for t in e_tools:
                _add(t, e_raw.get(t.name))
        except Exception as exc:
            logger.debug("Skipping %s: %s", pkg_dir.name, exc)

    # 14. AgentSkills (`use_skill`, `skill`, `configure_skill_tools`, `list_available_skills`)
    skill_tools, skill_raw = _load_skills_tools(raw_registry)
    for t in skill_tools:
        _add(t, skill_raw.get(t.name))

    _TOOL_CACHE["tools"] = list(tools_by_name.values())
    return list(_TOOL_CACHE["tools"])


def register_catalog_on_operations(operations: FastMCP) -> int:
    """Register all native tools on the `operations` server and attach native `ToolTransform`."""
    from strands_server.skills_provider import get_skills_directory_provider

    tools = load_all_strands_tools()
    for tool_obj in tools:
        operations.add_tool(tool_obj)

    operations.add_transform(build_core_capability_transforms())

    try:
        operations.add_provider(get_skills_directory_provider())
    except Exception as exc:
        logger.warning("Failed to attach SkillsDirectoryProvider: %s", exc)

    return len(tools)


__all__ = [
    "EXCLUDED_STRANDS_PACK_GOOGLE_MODULES",
    "SAMPLE_SKILLS_DIR",
    "SKILLS_DIR",
    "build_core_capability_transforms",
    "load_all_strands_tools",
    "register_catalog_on_operations",
]
