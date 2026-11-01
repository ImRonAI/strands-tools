"""Unified catalog loader and FastMCP Tool wrapper for all Strands tool suites.

Loads and normalizes all tools from:
1. Strands Google (`strands_google`)
2. Strands Fun Tools (`strands_fun_tools`)
3. Strands Agent Tools (`strands_tools` + `strands_graph_tool`)
4. Strands Pack (`strands_pack` — excluding Google/Gemini tools, including YouTube & `runtime/`)
5. Strands Telegram (`strands_telegram` & `strands_telegram_listener`)
6. Strands Zero (`strands_zero`)
7. Strands UTCP (`strands_utcp`)
8. Strands Harness SDK Tools (`strands_harness.tools`)
9. Strands Document MCP Server (`strands_docs_mcp`)
10. Strands Agent Skills (`agentskills` — Pattern #2 `skill` & Pattern #3 `use_skill` with assignable tools)
11. Strands CCXT (`strands_ccxt`)
12. Strands Inspect (`strands_inspect`)
13. Additional `strands.my` Ecosystem Packages (`strands_cloudflare`, `strands_sql`,
    `strands_hackerone`, `strands_ucp`, `strands_erc8004`, `strands_agentcore_tools`, `strands_rendercv`,
    `strands_plan_tool`, `strands_olostep`, `strands_omnivoice`, `strands_osmo`, `strands_adb`,
    `strands_transformers`, `strands_diffusers`, `strands_strudel`, `strands_bitchat`, `strands_icloud`,
    `strands_ios`, `strands_cad`, `strands_apify`, `strands_xa11y`, `strands_stigmer`, and `strands_my_catalog`)
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.tools.base import Tool, ToolResult
from mcp.types import TextContent
from pydantic import Field

logger = logging.getLogger(__name__)

# Locate workspace root (`strands-tools/`) relative to `packages/server/src/strands_server/catalog_loader.py`
REPO_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(REPO_ROOT / ".env", override=False)
SRC_DIR = REPO_ROOT / "src"
TOOLS_DIR = SRC_DIR / "tools"
SKILLS_DIR = SRC_DIR / "skills"
SAMPLE_SKILLS_DIR = SRC_DIR / "strands_tools" / "sessions_and_skills" / "sample_agent_skills" / "skills"

for _p in (str(TOOLS_DIR), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Strictly excluded Google/Gemini modules from `strands_pack` (Requirement #4)
EXCLUDED_STRANDS_PACK_GOOGLE_MODULES: frozenset[str] = frozenset(
    {
        "gmail",
        "google_auth",
        "google_calendar",
        "google_docs",
        "google_drive",
        "google_forms",
        "google_sheets",
        "google_tasks",
        "gemini_image",
        "gemini_music",
        "gemini_video",
    }
)


def _format_tool_output(raw: Any) -> ToolResult:
    """Normalize any Strands tool return value (str, dict, ToolResult, list) into a FastMCP ToolResult."""
    if isinstance(raw, ToolResult):
        return raw

    if isinstance(raw, dict):
        # Strands ToolResult dict shape: {"status": "success"|"error", "content": [{"text": ...}, {"json": ...}]}
        blocks = raw.get("content")
        texts: list[str] = []
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict):
                    if isinstance(b.get("text"), str):
                        texts.append(b["text"])
                    elif "json" in b:
                        texts.append(json.dumps(b["json"], default=str))
        text_out = "\n".join(texts) if texts else json.dumps(raw, default=str)
        structured = dict(raw)
        if "text" not in structured and texts:
            structured["text"] = text_out
        return ToolResult(
            content=[TextContent(type="text", text=text_out)],
            structured_content=structured,
        )

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return ToolResult(
                    content=[TextContent(type="text", text=raw)],
                    structured_content=parsed,
                )
        except Exception:
            pass
        return ToolResult(
            content=[TextContent(type="text", text=raw)],
            structured_content={"status": "success", "text": raw},
        )

    serialized = json.dumps(raw, default=str)
    return ToolResult(
        content=[TextContent(type="text", text=serialized)],
        structured_content={"status": "success", "result": raw},
    )


class StrandsFastMCPTool(Tool):
    """FastMCP Tool backed by a Strands `@tool`, `TOOL_SPEC` module, or `AgentTool`."""

    strands_target: Any = Field(default=None, exclude=True)
    invocation_mode: str = Field(default="decorated", exclude=True)
    domain_suite: str = Field(default="strands", exclude=True)

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        target = self.strands_target
        args = dict(arguments or {})
        try:
            if self.invocation_mode == "spec_func":
                tool_use = {
                    "toolUseId": f"tooluse_{self.name}_{uuid.uuid4().hex[:8]}",
                    "name": self.name,
                    "input": args,
                }
                res = target(tool_use)
                if asyncio.iscoroutine(res):
                    res = await res
                return _format_tool_output(res)

            if self.invocation_mode == "agent_tool" and hasattr(target, "stream") and not callable(target):
                tool_use = {
                    "toolUseId": f"tooluse_{self.name}_{uuid.uuid4().hex[:8]}",
                    "name": self.name,
                    "input": args,
                }
                final_res: Any = None
                async for event in target.stream(tool_use, {}):
                    if hasattr(event, "tool_result"):
                        final_res = event.tool_result
                    elif isinstance(event, dict) and "toolResult" in event:
                        final_res = event["toolResult"]
                return _format_tool_output(final_res or {"status": "success", "content": []})

            if callable(target):
                res = target(**args)
                if inspect.isasyncgen(res):
                    items = []
                    async for item in res:
                        items.append(item)
                    res = items[-1] if items else {"status": "success"}
                elif asyncio.iscoroutine(res):
                    res = await res
                return _format_tool_output(res)

            return _format_tool_output(
                {
                    "status": "error",
                    "content": [{"text": f"Tool {self.name!r} is not executable in current environment."}],
                }
            )
        except Exception as exc:
            return _format_tool_output(
                {
                    "status": "error",
                    "tool": self.name,
                    "error": f"{type(exc).__name__}: {exc}",
                    "content": [{"text": f"Error in {self.name}: {exc}"}],
                }
            )


def wrap_strands_object(
    obj: Any,
    *,
    fallback_name: str | None = None,
    suite: str = "strands",
    tags: set[str] | None = None,
) -> StrandsFastMCPTool | None:
    """Convert a Strands tool object (`DecoratedFunctionTool`, `AgentTool`, module with `TOOL_SPEC`, or callable)
    into a `StrandsFastMCPTool`."""
    if inspect.isclass(obj):
        return None
    effective_tags = {"strands", suite, *(tags or set())}

    # Case 1: DecoratedFunctionTool or AgentTool with .tool_name and .tool_spec
    if hasattr(obj, "tool_name") and hasattr(obj, "tool_spec"):
        spec = obj.tool_spec or {}
        name = fallback_name or str(obj.tool_name)
        desc = str(spec.get("description") or getattr(obj, "__doc__", "") or f"Strands tool {name}").strip()
        schema = spec.get("inputSchema", {}).get("json") or {"type": "object", "properties": {}}
        mode = "decorated" if callable(obj) else "agent_tool"
        return StrandsFastMCPTool(
            name=name,
            description=desc,
            parameters=schema,
            tags=effective_tags,
            strands_target=obj,
            invocation_mode=mode,
            domain_suite=suite,
        )

    # Case 2: Module with TOOL_SPEC and function
    if inspect.ismodule(obj):
        mod_short = obj.__name__.split(".")[-1]
        if hasattr(obj, "TOOL_SPEC") and isinstance(obj.TOOL_SPEC, dict):
            spec = obj.TOOL_SPEC
            fn_name = spec.get("name", mod_short)
            fn = getattr(obj, fn_name, None) or getattr(obj, mod_short, None)
            if callable(fn):
                name = fallback_name or str(fn_name)
                desc = str(spec.get("description") or obj.__doc__ or f"Strands tool {name}").strip()
                schema = spec.get("inputSchema", {}).get("json") or {"type": "object", "properties": {}}
                return StrandsFastMCPTool(
                    name=name,
                    description=desc,
                    parameters=schema,
                    tags=effective_tags,
                    strands_target=fn,
                    invocation_mode="spec_func",
                    domain_suite=suite,
                )
        # Or module contains a DecoratedFunctionTool named after the module
        attr = getattr(obj, mod_short, None)
        if attr is not None and attr is not obj:
            return wrap_strands_object(attr, fallback_name=fallback_name, suite=suite, tags=effective_tags)

    # Case 3: Plain callable
    if callable(obj):
        name = str(fallback_name or getattr(obj, "__name__", "tool"))
        desc = (inspect.getdoc(obj) or f"Strands tool {name}").strip()
        props: dict[str, Any] = {}
        required: list[str] = []
        try:
            sig = inspect.signature(obj)
            for pname, param in sig.parameters.items():
                if pname in ("self", "cls", "tool_context", "kwargs", "args"):
                    continue
                if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    continue
                props[pname] = {"type": "string", "description": f"Parameter {pname}"}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
        except Exception:
            pass
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        return StrandsFastMCPTool(
            name=name,
            description=desc,
            parameters=schema,
            tags=effective_tags,
            strands_target=obj,
            invocation_mode="decorated",
            domain_suite=suite,
        )

    return None


def _ast_fallback_tools_from_file(
    py_path: Path,
    *,
    suite: str,
    tags: set[str],
    import_error: Exception,
) -> list[StrandsFastMCPTool]:
    """Extract `@tool` functions or `TOOL_SPEC` from a Python file via AST if an optional C/cloud dependency
    is not installed at import time, so the tool still appears in the catalog with its full schema and
    returns a clear dependency message if invoked."""
    results: list[StrandsFastMCPTool] = []
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return results

    mod_doc = ast.get_docstring(tree) or ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_tool = any(
                (isinstance(d, ast.Name) and d.id == "tool")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "tool")
                for d in node.decorator_list
            )
            if not is_tool and node.name != py_path.stem:
                continue
            fn_name = node.name
            doc = ast.get_docstring(node) or mod_doc or f"Strands tool {fn_name} from {suite}"
            props: dict[str, Any] = {}
            req: list[str] = []
            num_defaults = len(node.args.defaults)
            num_args = len(node.args.args)
            for idx, arg in enumerate(node.args.args):
                if arg.arg in ("self", "cls", "tool_context", "agent", "tool"):
                    continue
                props[arg.arg] = {"type": "string", "description": f"Argument {arg.arg}"}
                if idx < (num_args - num_defaults):
                    req.append(arg.arg)
            schema: dict[str, Any] = {"type": "object", "properties": props}
            if req:
                schema["required"] = req

            err_msg = f"Optional dependency for {suite}.{fn_name} not active: {import_error}"

            def _make_stub(msg: str, tname: str) -> Any:
                def _stub(**kwargs: Any) -> dict[str, Any]:
                    return {
                        "status": "error",
                        "tool": tname,
                        "input": kwargs,
                        "content": [{"text": msg}],
                    }

                return _stub

            results.append(
                StrandsFastMCPTool(
                    name=fn_name,
                    description=doc.strip(),
                    parameters=schema,
                    tags={"strands", suite, *tags},
                    strands_target=_make_stub(err_msg, fn_name),
                    invocation_mode="decorated",
                    domain_suite=suite,
                )
            )
    return results


def _load_package_tools(
    pkg_name: str,
    *,
    suite: str,
    tags: set[str],
    exclude_modules: frozenset[str] = frozenset(),
    extra_tags_by_module: dict[str, set[str]] | None = None,
) -> list[StrandsFastMCPTool]:
    """Load all tools exported by a package directory under `src/tools/<pkg_name>`."""
    tools: dict[str, StrandsFastMCPTool] = {}
    pkg_dir = TOOLS_DIR / pkg_name
    if not pkg_dir.exists():
        return []

    # Try importing package root first
    try:
        pkg_mod = importlib.import_module(pkg_name)
        for attr_name in getattr(pkg_mod, "__all__", []):
            if attr_name in exclude_modules:
                continue
            try:
                val = getattr(pkg_mod, attr_name)
                mtags = set(tags)
                if extra_tags_by_module and attr_name in extra_tags_by_module:
                    mtags |= extra_tags_by_module[attr_name]
                wrapped = wrap_strands_object(val, suite=suite, tags=mtags)
                if wrapped is not None and wrapped.name not in exclude_modules:
                    tools[wrapped.name] = wrapped
            except Exception:
                pass
    except Exception:
        pass

    # Scan individual .py module files in pkg_dir
    for py_file in sorted(pkg_dir.glob("*.py")):
        stem = py_file.stem
        if stem.startswith("_") or stem in exclude_modules:
            continue
        mod_qual = f"{pkg_name}.{stem}"
        mtags = set(tags)
        if extra_tags_by_module and stem in extra_tags_by_module:
            mtags |= extra_tags_by_module[stem]
        try:
            mod = importlib.import_module(mod_qual)
            found_in_mod = False
            # Look for DecoratedFunctionTool or AgentTool attributes in mod.__dict__ (avoiding inspect.getmembers overhead)
            for attr_name, val in list(vars(mod).items()):
                if attr_name.startswith("_"):
                    continue
                if hasattr(val, "tool_name") and hasattr(val, "tool_spec"):
                    wrapped = wrap_strands_object(val, suite=suite, tags=mtags)
                    if wrapped and wrapped.name not in exclude_modules:
                        tools[wrapped.name] = wrapped
                        found_in_mod = True
            if not found_in_mod and hasattr(mod, "TOOL_SPEC"):
                wrapped = wrap_strands_object(mod, suite=suite, tags=mtags)
                if wrapped and wrapped.name not in exclude_modules:
                    tools[wrapped.name] = wrapped
                    found_in_mod = True
        except Exception as exc:
            for stub_tool in _ast_fallback_tools_from_file(py_file, suite=suite, tags=mtags, import_error=exc):
                if stub_tool.name not in tools and stub_tool.name not in exclude_modules:
                    tools[stub_tool.name] = stub_tool

    return list(tools.values())


# Singleton cache so repeated build_operations calls are instantaneous
_CATALOG_CACHE: list[StrandsFastMCPTool] | None = None


def load_all_strands_tools(*, force_reload: bool = False) -> list[StrandsFastMCPTool]:
    """Load and return all Strands tools across all 12+ required repositories and `strands.my` packages."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None and not force_reload:
        return list(_CATALOG_CACHE)

    catalog: dict[str, StrandsFastMCPTool] = {}

    def _register_many(items: list[StrandsFastMCPTool], *, prefix_on_collision: str | None = None) -> None:
        for item in items:
            if item.name not in catalog:
                catalog[item.name] = item
            elif prefix_on_collision:
                aliased = item.model_copy(update={"name": f"{prefix_on_collision}_{item.name}"})
                catalog[aliased.name] = aliased

    # 1. Strands Google (https://github.com/cagataycali/strands-google)
    _register_many(
        _load_package_tools("strands_google", suite="strands_google", tags={"google", "strands-google"})
    )

    # 2. Strands Fun Tools (https://github.com/cagataycali/strands-fun-tools)
    _register_many(
        _load_package_tools("strands_fun_tools", suite="strands_fun_tools", tags={"fun-tools", "strands-fun-tools"})
    )

    # 3. Strands Agent Tools (https://github.com/strands-agents/tools) + strands_graph_tool
    _register_many(
        _load_package_tools("strands_tools", suite="strands_tools", tags={"agent-tools", "strands-tools"}),
        prefix_on_collision="agent",
    )
    try:
        from strands_graph_tool import graph as heterogeneous_graph_tool  # type: ignore[import-untyped]

        hg_wrapped = wrap_strands_object(
            heterogeneous_graph_tool,
            fallback_name="heterogeneous_graph",
            suite="strands_tools",
            tags={"agent-tools", "strands-tools", "graph"},
        )
        if hg_wrapped:
            catalog[hg_wrapped.name] = hg_wrapped
    except Exception as exc:
        logger.debug("Could not load heterogeneous_graph: %s", exc)

    # 4. Strands Pack (https://github.com/labeveryday/strands-pack)
    # Exclude Google/Gemini tools; include YouTube tools, runtime/, and all other tools.
    yt_tags = {
        m: {"youtube", "strands-pack-youtube"}
        for m in ("youtube", "youtube_read", "youtube_write", "youtube_analytics", "youtube_transcript")
    }
    pack_tools = _load_package_tools(
        "strands_pack",
        suite="strands_pack",
        tags={"strands-pack", "pack"},
        exclude_modules=EXCLUDED_STRANDS_PACK_GOOGLE_MODULES,
        extra_tags_by_module=yt_tags,
    )
    _register_many(pack_tools, prefix_on_collision="pack")
    if "youtube_read" in catalog and "youtube" not in catalog:
        catalog["youtube"] = catalog["youtube_read"].model_copy(update={"name": "youtube"})

    # Explicitly load strands_pack.runtime tools (pack_runtime_approval, pack_runtime_job_runner)
    try:
        from strands_pack.runtime import pack_runtime_approval, pack_runtime_job_runner

        for rt_tool in (pack_runtime_approval, pack_runtime_job_runner):
            w = wrap_strands_object(rt_tool, suite="strands_pack", tags={"strands-pack", "runtime"})
            if w:
                catalog[w.name] = w
    except Exception as exc:
        logger.warning("Failed to load strands_pack.runtime tools: %s", exc)

    # 5. Strands Telegram & Strands Telegram Listener
    _register_many(
        _load_package_tools("strands_telegram", suite="strands_telegram", tags={"telegram", "strands-telegram"})
    )
    _register_many(
        _load_package_tools(
            "strands_telegram_listener",
            suite="strands_telegram_listener",
            tags={"telegram", "telegram-listener", "strands-telegram"},
        )
    )

    # 6. Strands Zero (https://pypi.org/project/strands-zero)
    _register_many(
        _load_package_tools("strands_zero", suite="strands_zero", tags={"zero", "strands-zero"})
    )

    # 7. Strands UTCP (https://github.com/universal-tool-calling-protocol/strands-utcp)
    _register_many(
        _load_package_tools("strands_utcp", suite="strands_utcp", tags={"utcp", "strands-utcp"})
    )

    # 8. Strands Harness SDK Tools (https://github.com/ImRonAI/strands-harness-sdk-python)
    try:
        import strands_harness.tools as harness_tools_mod

        for h_name in ("read", "write", "edit", "web_fetch", "web_search", "exa_web_search", "programmatic_tool_caller", "subagent", "bash"):
            h_obj = getattr(harness_tools_mod, h_name, None)
            if h_obj is not None:
                w = wrap_strands_object(
                    h_obj,
                    fallback_name=h_name,
                    suite="strands_harness",
                    tags={"harness", "strands-harness"},
                )
                if w:
                    catalog[w.name] = w
                    # Also expose `harness_<name>` alias for unambiguous lookup
                    h_alias = f"harness_{h_name}"
                    if h_alias not in catalog:
                        catalog[h_alias] = w.model_copy(update={"name": h_alias})
    except Exception as exc:
        logger.warning("Failed to load strands_harness.tools: %s", exc)

    # 9. Strands Document MCP Server (https://github.com/ImRonAI/strands-harness-sdk-python/tree/main/strands-mcp)
    try:
        from strands_docs_mcp.server import fetch_doc, search_docs

        for doc_fn in (search_docs, fetch_doc):
            w = wrap_strands_object(doc_fn, suite="strands_docs_mcp", tags={"docs-mcp", "strands-docs"})
            if w:
                catalog[w.name] = w
    except Exception as exc:
        logger.warning("Failed to load strands_docs_mcp: %s", exc)

    # 11. Strands CCXT (https://github.com/mertozbas/strands-ccxt)
    _register_many(
        _load_package_tools("strands_ccxt", suite="strands_ccxt", tags={"ccxt", "strands-ccxt", "crypto"})
    )

    # 12. Strands Inspect (https://github.com/cagataycali/strands-inspect)
    _register_many(
        _load_package_tools("strands_inspect", suite="strands_inspect", tags={"inspect", "strands-inspect"})
    )

    # 13. Additional strands.my Ecosystem Packages
    ecosystem_packages = [
        ("strands_cloudflare", {"cloudflare", "ecosystem"}),
        ("strands_sql", {"sql", "database", "ecosystem"}),
        ("strands_hackerone", {"hackerone", "security", "ecosystem"}),
        ("strands_ucp", {"ucp", "commerce", "ecosystem"}),
        ("strands_erc8004", {"erc8004", "web3", "ipfs", "x402", "ecosystem"}),
        ("strands_agentcore_tools", {"agentcore", "aws", "ecosystem"}),
        ("strands_rendercv", {"rendercv", "cv", "ecosystem"}),
        ("strands_plan_tool", {"plan", "planning", "ecosystem"}),
        ("strands_olostep", {"olostep", "scraping", "ecosystem"}),
        ("strands_omnivoice", {"omnivoice", "audio", "tts", "ecosystem"}),
        ("strands_osmo", {"osmo", "nvidia", "robotics", "ecosystem"}),
        ("strands_adb", {"adb", "android", "ecosystem"}),
        ("strands_transformers", {"transformers", "huggingface", "ecosystem"}),
        ("strands_diffusers", {"diffusers", "image-gen", "ecosystem"}),
        ("strands_strudel", {"strudel", "music", "ecosystem"}),
        ("strands_bitchat", {"bitchat", "p2p", "ecosystem"}),
        ("strands_icloud", {"icloud", "apple", "ecosystem"}),
        ("strands_ios", {"ios", "apple", "ecosystem"}),
        ("strands_cad", {"cad", "3d", "ecosystem"}),
        ("strands_apify", {"apify", "actors", "ecosystem"}),
        ("strands_xa11y", {"xa11y", "accessibility", "ecosystem"}),
        ("strands_stigmer", {"stigmer", "ecosystem"}),
    ]
    for pkg_name, pkg_tags in ecosystem_packages:
        _register_many(
            _load_package_tools(pkg_name, suite=pkg_name, tags=pkg_tags),
            prefix_on_collision=pkg_name.replace("strands_", ""),
        )

    # 10. Strands Agent Skills (https://github.com/aws-samples/sample-strands-agents-agentskills)
    # Must implement Pattern #2 (`create_skill_tool` -> `skill`) and Pattern #3 (`create_skill_agent_tool` -> `use_skill`),
    # and Pattern #3 MUST be able to be assigned other tools as well!
    try:
        # Same as upstream examples/3-skill_agent_tool.py: sub-agents run non-interactively.
        os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

        from agentskills import (
            configure_skill_tools,
            create_skill_agent_tool,
            create_skill_tool,
            discover_skills,
            list_available_skills,
            register_available_tools,
        )

        # Register every loaded Strands tool into the AgentSkills assignable tool registry!
        assignable_map: dict[str, Any] = {
            name: tool_item.strands_target
            for name, tool_item in catalog.items()
            if tool_item.strands_target is not None
        }
        register_available_tools(assignable_map)

        # Discover skills from sample_agent_skills and main skills folder
        skills_list = []
        if SAMPLE_SKILLS_DIR.exists():
            skills_list.extend(discover_skills(SAMPLE_SKILLS_DIR))
        if SKILLS_DIR.exists():
            existing_names = {s.name for s in skills_list}
            for s in discover_skills(SKILLS_DIR):
                if s.name not in existing_names:
                    skills_list.append(s)
                    existing_names.add(s.name)

        # Pattern #2: Skill as a tool (`skill`)
        pattern2_tool = create_skill_tool(skills_list, skills_dir=SAMPLE_SKILLS_DIR if SAMPLE_SKILLS_DIR.exists() else SKILLS_DIR)
        w_p2 = wrap_strands_object(
            pattern2_tool,
            fallback_name="skill",
            suite="agentskills",
            tags={"agent-skills", "agentskills", "pattern-2"},
        )
        if w_p2:
            catalog["skill"] = w_p2

        # Pattern #3: Skill as an isolated sub-agent tool (`use_skill`) with assignable tools!
        # Default tools match upstream examples/3-skill_agent_tool.py: [file_read, file_write, shell, editor].
        default_subagent_tools = [
            assignable_map[k]
            for k in ("file_read", "file_write", "shell", "editor")
            if k in assignable_map
        ]
        pattern3_tool = create_skill_agent_tool(
            skills_list,
            skills_dir=SAMPLE_SKILLS_DIR if SAMPLE_SKILLS_DIR.exists() else SKILLS_DIR,
            additional_tools=default_subagent_tools,
            available_tools_registry=assignable_map,
        )
        w_p3 = wrap_strands_object(
            pattern3_tool,
            fallback_name="use_skill",
            suite="agentskills",
            tags={"agent-skills", "agentskills", "pattern-3"},
        )
        if w_p3:
            catalog["use_skill"] = w_p3

        for helper_fn in (configure_skill_tools, list_available_skills):
            w_h = wrap_strands_object(
                helper_fn,
                suite="agentskills",
                tags={"agent-skills", "agentskills"},
            )
            if w_h:
                catalog[w_h.name] = w_h
    except Exception as exc:
        logger.warning("Failed to configure agentskills Pattern #2/#3: %s", exc)

    # Wire all loaded tools into `strands_harness.tools.programmatic_tool_caller` standalone registry!
    try:
        from strands_harness.tools.programmatic_tool_caller import register_standalone_tools

        standalone_callables: dict[str, Any] = {}
        for tname, titem in catalog.items():
            if tname == "programmatic_tool_caller":
                continue

            def _make_runner(item: StrandsFastMCPTool) -> Any:
                async def _runner(**kw: Any) -> Any:
                    res = await item.run(kw)
                    if res.structured_content is not None:
                        return res.structured_content
                    if res.content and isinstance(res.content[0], TextContent):
                        return res.content[0].text
                    return ""

                return _runner

            standalone_callables[tname] = _make_runner(titem)
        register_standalone_tools(standalone_callables)
    except Exception as exc:
        logger.debug("Could not register standalone tools for programmatic_tool_caller: %s", exc)

    # Add `strands_my_catalog` discovery tool for querying suites, tools, and skills
    def strands_my_catalog(
        action: str = "summary",
        suite: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Explore the complete Strands Tools & strands.my catalog loaded into this server.

        Args:
            action: One of 'summary', 'list_tools', 'list_suites', or 'list_skills'.
            suite: Optional domain suite name to filter tools (e.g., 'strands_google', 'strands_pack', 'strands_zero').
            query: Optional search substring for tool/skill names and descriptions.
            limit: Maximum number of rows to return (default 50).
        """
        all_items = list(catalog.values())
        if action == "list_suites":
            by_suite: dict[str, list[str]] = {}
            for item in all_items:
                by_suite.setdefault(item.domain_suite, []).append(item.name)
            rows = [
                {
                    "suite": s,
                    "tool_count": len(names),
                    "sample_tools": ", ".join(sorted(names)[:8]),
                }
                for s, names in sorted(by_suite.items())
            ]
            return {"rows": rows, "meta": {"total_suites": len(rows), "total_tools": len(all_items)}}

        if action == "list_skills":
            from agentskills import discover_skills

            skills = []
            if SAMPLE_SKILLS_DIR.exists():
                skills.extend(discover_skills(SAMPLE_SKILLS_DIR))
            if SKILLS_DIR.exists():
                seen = {s.name for s in skills}
                for s in discover_skills(SKILLS_DIR):
                    if s.name not in seen:
                        skills.append(s)
                        seen.add(s.name)
            q = (query or "").lower().strip()
            filtered = [
                {"name": s.name, "description": s.description, "path": str(s.path)}
                for s in skills
                if not q or q in s.name.lower() or q in s.description.lower()
            ]
            return {"rows": filtered[:limit], "meta": {"total_skills": len(filtered)}}

        q = (query or "").lower().strip()
        filtered_tools = [
            {
                "name": item.name,
                "suite": item.domain_suite,
                "tags": ", ".join(sorted(item.tags)),
                "description": (item.description or "").splitlines()[0][:160],
            }
            for item in all_items
            if (not suite or item.domain_suite == suite or suite in item.tags)
            and (not q or q in item.name.lower() or q in (item.description or "").lower())
        ]
        return {
            "rows": filtered_tools[:limit],
            "meta": {
                "total_matching": len(filtered_tools),
                "total_catalog_tools": len(all_items),
            },
        }

    cat_tool = wrap_strands_object(
        strands_my_catalog,
        fallback_name="strands_my_catalog",
        suite="strands_ecosystem",
        tags={"catalog", "strands-my", "ecosystem"},
    )
    if cat_tool:
        catalog["strands_my_catalog"] = cat_tool

    _CATALOG_CACHE = list(catalog.values())
    return list(_CATALOG_CACHE)


def register_catalog_on_operations(operations: FastMCP, tools: list[StrandsFastMCPTool] | None = None) -> int:
    """Register all loaded `StrandsFastMCPTool` instances onto the `operations` FastMCP server."""
    items = tools if tools is not None else load_all_strands_tools()
    for tool_obj in items:
        operations.add_tool(tool_obj)
    return len(items)
