"""Skill agent tool for Strands Agents (Pattern #3: Agent as Tool / Isolated Sub-Agent Mode)

This module creates a Strands tool that executes skills in isolated sub-agents.
Each skill runs in a separate agent with its own context, system prompt, and assigned tools.

Supports:
1. Assigning other tools to Pattern #3 skill sub-agents via `additional_tools`, `per_skill_tools`,
   `assign_tools_to_skill`, `SKILL.md` `allowed-tools`, and per-call `assigned_tools`.
2. Automatic subdirectory capability tools when applicable on a skill:
   - `references/` -> `query_skill_references`: Knowledge Base search, listing, and reading.
   - `scripts/` -> `run_skill_script`: Sandboxed runnable code inspection and execution.
   - `assets/` -> `use_skill_asset`: Reusable component & template inspection and integration.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Iterable
from pathlib import Path
from typing import Any

from strands import Agent, tool
from strands.models import Model, ModelRouter

from ..agent_model import get_gemini_agent_model
from ..errors import SkillActivationError
from ..models import SkillProperties
from ..parser import load_instructions
from ..prompt import OUTPUT_DIR, SCRATCH_DIR, generate_skill_instructions_prompt
from ..tool_utils import (
    build_skill_header,
    scan_skill_resources_by_category,
    validate_skill_name,
)

logger = logging.getLogger(__name__)

# Global runtime registry of tools and per-skill tool assignments for Pattern #3
_GLOBAL_TOOL_REGISTRY: dict[str, Any] = {}
_GLOBAL_PER_SKILL_TOOLS: dict[str, list[Any]] = {}
_GLOBAL_DEFAULT_ADDITIONAL_TOOLS: list[Any] = []


def register_available_tools(tools: dict[str, Any] | Iterable[Any]) -> None:
    """Register tools in the global Pattern #3 tool registry so they can be assigned by name."""
    if isinstance(tools, dict):
        for name, t in tools.items():
            _GLOBAL_TOOL_REGISTRY[str(name)] = t
    else:
        for t in tools:
            name = getattr(t, "tool_name", None) or getattr(t, "__name__", None)
            if name:
                _GLOBAL_TOOL_REGISTRY[str(name)] = t


def assign_tools_to_skill(skill_name: str, tools: list[Any], *, append: bool = False) -> list[str]:
    """Assign tools (tool objects or registered tool names) to a specific skill for Pattern #3."""
    key = skill_name.strip()
    existing = list(_GLOBAL_PER_SKILL_TOOLS.get(key, [])) if append else []
    existing.extend(tools)
    _GLOBAL_PER_SKILL_TOOLS[key] = existing
    return [str(getattr(t, "tool_name", getattr(t, "__name__", str(t)))) for t in existing]


def set_default_skill_tools(tools: list[Any]) -> list[str]:
    """Set default additional tools provided to all Pattern #3 skill sub-agents."""
    _GLOBAL_DEFAULT_ADDITIONAL_TOOLS.clear()
    _GLOBAL_DEFAULT_ADDITIONAL_TOOLS.extend(tools)
    return [
        str(getattr(t, "tool_name", getattr(t, "__name__", str(t))))
        for t in _GLOBAL_DEFAULT_ADDITIONAL_TOOLS
    ]


def get_assigned_skill_tools(skill_name: str | None = None) -> dict[str, Any]:
    """Inspect tools currently assigned to a specific skill or globally."""

    def _name(t: Any) -> str:
        return str(getattr(t, "tool_name", getattr(t, "__name__", str(t))))

    if skill_name:
        per_skill = [_name(t) for t in _GLOBAL_PER_SKILL_TOOLS.get(skill_name, [])]
        defaults = [_name(t) for t in _GLOBAL_DEFAULT_ADDITIONAL_TOOLS]
        return {
            "skill_name": skill_name,
            "per_skill_tools": per_skill,
            "default_additional_tools": defaults,
            "effective_tools": list(dict.fromkeys([*defaults, *per_skill])),
        }
    return {
        "default_additional_tools": [_name(t) for t in _GLOBAL_DEFAULT_ADDITIONAL_TOOLS],
        "per_skill_tools": {
            k: [_name(t) for t in v] for k, v in _GLOBAL_PER_SKILL_TOOLS.items()
        },
        "registered_tool_count": len(_GLOBAL_TOOL_REGISTRY),
        "available_registry_tools": sorted(_GLOBAL_TOOL_REGISTRY.keys()),
    }


def _safe_resolve_within(base_dir: Path, relative_target: str) -> Path:
    """Resolve `relative_target` strictly within `base_dir`, raising ValueError on traversal."""
    resolved_base = base_dir.resolve()
    cleaned = relative_target.strip().lstrip("/")
    if cleaned.startswith(f"{resolved_base.name}/"):
        cleaned = cleaned[len(resolved_base.name) + 1 :]
    candidate = (resolved_base / cleaned).resolve()
    if not candidate.is_relative_to(resolved_base):
        raise ValueError(f"Path '{relative_target}' escapes allowed directory '{resolved_base.name}/'.")
    return candidate


def _make_references_kb_tool(skill: SkillProperties, ref_files: list[Path]) -> Any:
    """Create a scoped Knowledge Base tool (`query_skill_references`) for a skill's `references/` folder."""
    skill_dir = Path(skill.skill_dir).resolve()
    refs_dir = (skill_dir / "references").resolve()

    @tool(name="query_skill_references")
    def query_skill_references(
        action: str = "search",
        query: str | None = None,
        file_path: str | None = None,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Query the skill's `references/` subdirectory as an authoritative domain knowledge base.

        Args:
            action: One of "list" (list reference docs), "search" (keyword/regex search across references),
                or "read" (read a specific file from `references/`).
            query: Search query string or regex pattern when action="search".
            file_path: Relative file path inside `references/` when action="read".
            max_results: Maximum number of search matches to return (default 10).
        """
        if action == "list":
            items = [
                {
                    "path": f.relative_to(refs_dir).as_posix(),
                    "skill_relative_path": f.relative_to(skill_dir).as_posix(),
                    "resource_uri": f"skill://{skill.name}/{f.relative_to(skill_dir).as_posix()}",
                    "size_bytes": f.stat().st_size,
                }
                for f in ref_files
                if f.exists()
            ]
            return {
                "status": "success",
                "content": [{"text": json.dumps({"skill": skill.name, "references": items}, indent=2)}],
            }

        if action == "read":
            if not file_path:
                return {
                    "status": "error",
                    "content": [{"text": "`file_path` is required when action='read'."}],
                }
            try:
                target = _safe_resolve_within(refs_dir, file_path)
            except ValueError as exc:
                return {"status": "error", "content": [{"text": str(exc)}]}
            if not target.exists() or not target.is_file():
                return {
                    "status": "error",
                    "content": [{"text": f"Reference file not found: {file_path}"}],
                }
            text = target.read_text(encoding="utf-8", errors="replace")
            return {
                "status": "success",
                "content": [
                    {
                        "text": (
                            f"# Reference: {target.relative_to(skill_dir).as_posix()}\n"
                            f"URI: skill://{skill.name}/{target.relative_to(skill_dir).as_posix()}\n\n"
                            f"{text}"
                        )
                    }
                ],
            }

        if action == "search":
            q = (query or "").strip()
            if not q:
                return {
                    "status": "error",
                    "content": [{"text": "`query` is required when action='search'."}],
                }
            matches: list[dict[str, Any]] = []
            try:
                pattern = re.compile(q, re.IGNORECASE)
            except re.error:
                pattern = re.compile(re.escape(q), re.IGNORECASE)

            for f in ref_files:
                if not f.exists():
                    continue
                try:
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue
                for idx, line in enumerate(lines):
                    if pattern.search(line):
                        start = max(0, idx - 2)
                        end = min(len(lines), idx + 3)
                        snippet = "\n".join(lines[start:end])
                        rel = f.relative_to(skill_dir).as_posix()
                        matches.append(
                            {
                                "file": f.relative_to(refs_dir).as_posix(),
                                "resource_uri": f"skill://{skill.name}/{rel}",
                                "line": idx + 1,
                                "snippet": snippet,
                            }
                        )
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "skill": skill.name,
                                "query": q,
                                "match_count": len(matches),
                                "matches": matches,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        return {"status": "error", "content": [{"text": f"Unknown action: {action}"}]}

    return query_skill_references


def _make_scripts_sandbox_tool(skill: SkillProperties, script_files: list[Path]) -> Any:
    """Create a sandboxed script runner tool (`run_skill_script`) for a skill's `scripts/` folder."""
    skill_dir = Path(skill.skill_dir).resolve()
    scripts_dir = (skill_dir / "scripts").resolve()

    @tool(name="run_skill_script")
    def run_skill_script(
        action: str = "run",
        script_path: str | None = None,
        args: list[str] | None = None,
        stdin_text: str | None = None,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """List, inspect, or execute runnable code from the skill's `scripts/` subdirectory inside an isolated sandbox.

        Args:
            action: One of "list" (list scripts), "inspect" (read script source), or "run" (execute in sandbox).
            script_path: Relative path to the script inside `scripts/` (e.g. "extract_text.py").
            args: Optional CLI arguments list to pass to the script when action="run".
            stdin_text: Optional standard input text to pass to the script when action="run".
            timeout_seconds: Execution timeout in seconds (default 30, max 120).
        """
        if action == "list":
            items = [
                {
                    "path": f.relative_to(scripts_dir).as_posix(),
                    "skill_relative_path": f.relative_to(skill_dir).as_posix(),
                    "resource_uri": f"skill://{skill.name}/{f.relative_to(skill_dir).as_posix()}",
                    "size_bytes": f.stat().st_size,
                }
                for f in script_files
                if f.exists()
            ]
            return {
                "status": "success",
                "content": [{"text": json.dumps({"skill": skill.name, "scripts": items}, indent=2)}],
            }

        if not script_path:
            return {
                "status": "error",
                "content": [{"text": "`script_path` is required for action='inspect' or action='run'."}],
            }

        try:
            target = _safe_resolve_within(scripts_dir, script_path)
        except ValueError as exc:
            return {"status": "error", "content": [{"text": str(exc)}]}

        if not target.exists() or not target.is_file():
            return {
                "status": "error",
                "content": [{"text": f"Script not found in scripts/: {script_path}"}],
            }

        if action == "inspect":
            code = target.read_text(encoding="utf-8", errors="replace")
            return {
                "status": "success",
                "content": [
                    {
                        "text": (
                            f"# Script: {target.relative_to(skill_dir).as_posix()}\n"
                            f"URI: skill://{skill.name}/{target.relative_to(skill_dir).as_posix()}\n\n"
                            f"{code}"
                        )
                    }
                ],
            }

        if action == "run":
            sandbox_dir = (SCRATCH_DIR / f"sandbox_{skill.name}_{uuid.uuid4().hex[:8]}").resolve()
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            suffix = target.suffix.lower()
            if suffix == ".py":
                cmd = [sys.executable, str(target)]
            elif suffix in (".js", ".mjs", ".cjs"):
                cmd = ["node", str(target)]
            elif suffix == ".sh":
                cmd = ["bash", str(target)]
            else:
                cmd = [sys.executable, str(target)]

            if args:
                cmd.extend(str(a) for a in args)

            sanitized_env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(sandbox_dir),
                "TMPDIR": str(sandbox_dir),
                "SKILL_DIR": str(skill_dir),
                "SANDBOX_DIR": str(sandbox_dir),
                "OUTPUT_DIR": str(OUTPUT_DIR.resolve()),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            effective_timeout = max(1, min(int(timeout_seconds), 120))
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(sandbox_dir),
                    env=sanitized_env,
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Script '{script_path}' timed out after {effective_timeout}s in sandbox '{sandbox_dir}'."
                        }
                    ],
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "content": [{"text": f"Sandbox execution error for '{script_path}': {exc}"}],
                }

            created_files = [
                f.relative_to(sandbox_dir).as_posix()
                for f in sorted(sandbox_dir.rglob("*"))
                if f.is_file()
            ]
            payload = {
                "skill": skill.name,
                "script": target.relative_to(skill_dir).as_posix(),
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "sandbox_dir": str(sandbox_dir),
                "created_files": created_files,
            }
            status_str = "success" if proc.returncode == 0 else "error"
            return {
                "status": status_str,
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        return {"status": "error", "content": [{"text": f"Unknown action: {action}"}]}

    return run_skill_script


def _make_assets_component_tool(skill: SkillProperties, asset_files: list[Path]) -> Any:
    """Create a component & asset integration tool (`use_skill_asset`) for a skill's `assets/` folder."""
    skill_dir = Path(skill.skill_dir).resolve()
    assets_dir = (skill_dir / "assets").resolve()

    @tool(name="use_skill_asset")
    def use_skill_asset(
        action: str = "list",
        asset_path: str | None = None,
        destination_path: str | None = None,
        template_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """List, inspect, or integrate reusable components and assets from the skill's `assets/` subdirectory.

        Args:
            action: One of "list" (list all components/assets), "read" (read component source/metadata),
                or "integrate" (copy/instantiate the component into the output/workspace directory).
            asset_path: Relative path to the component/asset inside `assets/`.
            destination_path: Relative destination path inside the output directory when action="integrate".
            template_vars: Optional dict of template variables (`{{key}}` / `${key}`) to substitute when integrating text/code components.
        """
        if action == "list":
            items = []
            for f in asset_files:
                if not f.exists():
                    continue
                mime_type, _ = mimetypes.guess_type(str(f))
                rel_skill = f.relative_to(skill_dir).as_posix()
                items.append(
                    {
                        "path": f.relative_to(assets_dir).as_posix(),
                        "skill_relative_path": rel_skill,
                        "resource_uri": f"skill://{skill.name}/{rel_skill}",
                        "mime_type": mime_type or "application/octet-stream",
                        "size_bytes": f.stat().st_size,
                    }
                )
            return {
                "status": "success",
                "content": [{"text": json.dumps({"skill": skill.name, "assets": items}, indent=2)}],
            }

        if not asset_path:
            return {
                "status": "error",
                "content": [{"text": "`asset_path` is required for action='read' or action='integrate'."}],
            }

        try:
            target = _safe_resolve_within(assets_dir, asset_path)
        except ValueError as exc:
            return {"status": "error", "content": [{"text": str(exc)}]}

        if not target.exists() or not target.is_file():
            return {
                "status": "error",
                "content": [{"text": f"Asset component not found in assets/: {asset_path}"}],
            }

        mime_type, _ = mimetypes.guess_type(str(target))
        is_text = bool(
            (mime_type and (mime_type.startswith("text/") or mime_type in ("application/json", "image/svg+xml")))
            or target.suffix.lower() in (".md", ".txt", ".json", ".yaml", ".yml", ".tsx", ".ts", ".jsx", ".js", ".html", ".css", ".py", ".svg", ".glsl")
        )

        if action == "read":
            rel_skill = target.relative_to(skill_dir).as_posix()
            if is_text:
                content = target.read_text(encoding="utf-8", errors="replace")
                if template_vars:
                    for k, v in template_vars.items():
                        content = content.replace(f"{{{{{k}}}}}", str(v)).replace(f"${{{k}}}", str(v))
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": (
                                f"# Component Asset: {rel_skill}\n"
                                f"URI: skill://{skill.name}/{rel_skill}\n\n"
                                f"{content}"
                            )
                        }
                    ],
                }
            raw_bytes = target.read_bytes()
            b64_preview = base64.b64encode(raw_bytes[:2048]).decode("ascii")
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "skill": skill.name,
                                "asset": rel_skill,
                                "resource_uri": f"skill://{skill.name}/{rel_skill}",
                                "mime_type": mime_type or "application/octet-stream",
                                "size_bytes": len(raw_bytes),
                                "base64_prefix": b64_preview,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if action in ("integrate", "copy"):
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            dest_rel = destination_path or target.relative_to(assets_dir).as_posix()
            try:
                dest_file = _safe_resolve_within(OUTPUT_DIR.resolve(), dest_rel)
            except ValueError as exc:
                return {"status": "error", "content": [{"text": str(exc)}]}

            dest_file.parent.mkdir(parents=True, exist_ok=True)
            if is_text and template_vars:
                rendered = target.read_text(encoding="utf-8", errors="replace")
                for k, v in template_vars.items():
                    rendered = rendered.replace(f"{{{{{k}}}}}", str(v)).replace(f"${{{k}}}", str(v))
                dest_file.write_text(rendered, encoding="utf-8")
            else:
                shutil.copy2(target, dest_file)

            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "status": "integrated",
                                "skill": skill.name,
                                "source_asset": target.relative_to(skill_dir).as_posix(),
                                "destination_path": str(dest_file),
                                "templated": bool(is_text and template_vars),
                            },
                            indent=2,
                        )
                    }
                ],
            }

        return {"status": "error", "content": [{"text": f"Unknown action: {action}"}]}

    return use_skill_asset


def build_skill_subdirectory_tools(skill: SkillProperties) -> list[Any]:
    """Build scoped tools for a skill's `references/`, `scripts/`, and `assets/` subdirectories when present."""
    skill_dir = Path(skill.skill_dir).resolve()
    categorized = scan_skill_resources_by_category(skill_dir)
    subdir_tools: list[Any] = []
    if categorized["references"]:
        subdir_tools.append(_make_references_kb_tool(skill, categorized["references"]))
    if categorized["scripts"]:
        subdir_tools.append(_make_scripts_sandbox_tool(skill, categorized["scripts"]))
    if categorized["assets"]:
        subdir_tools.append(_make_assets_component_tool(skill, categorized["assets"]))
    return subdir_tools


def _resolve_tool_item(
    item: Any,
    tool_registry: dict[str, Any] | None = None,
    tool_resolver: Callable[[str], Any] | None = None,
) -> Any | None:
    """Resolve a tool object or tool name string into an executable Strands tool."""
    if item is None:
        return None
    if not isinstance(item, str):
        return item
    name = item.strip()
    if not name:
        return None
    if tool_registry and name in tool_registry:
        return tool_registry[name]
    if name in _GLOBAL_TOOL_REGISTRY:
        return _GLOBAL_TOOL_REGISTRY[name]
    if tool_resolver is not None:
        resolved = tool_resolver(name)
        if resolved is not None:
            return resolved
    return None


def _resolve_skill_tools(
    skill: SkillProperties,
    *,
    additional_tools: list[Any] | None = None,
    per_skill_tools: dict[str, list[Any]] | None = None,
    call_assigned_tools: list[Any] | None = None,
    tool_registry: dict[str, Any] | None = None,
    tool_resolver: Callable[[str], Any] | None = None,
) -> list[Any]:
    """Combine and deduplicate all tools assigned to a Pattern #3 skill sub-agent, including subdirectory tools."""
    raw_items: list[Any] = []
    # Automatically attach `references/` KB tool, `scripts/` sandbox tool, and `assets/` component tool when present!
    raw_items.extend(build_skill_subdirectory_tools(skill))
    if _GLOBAL_DEFAULT_ADDITIONAL_TOOLS:
        raw_items.extend(_GLOBAL_DEFAULT_ADDITIONAL_TOOLS)
    if additional_tools:
        raw_items.extend(additional_tools)
    if per_skill_tools and skill.name in per_skill_tools:
        raw_items.extend(per_skill_tools[skill.name])
    if skill.name in _GLOBAL_PER_SKILL_TOOLS:
        raw_items.extend(_GLOBAL_PER_SKILL_TOOLS[skill.name])
    if skill.allowed_tools:
        for token in re.split(r"[,\s]+", skill.allowed_tools):
            token = token.strip()
            if token:
                raw_items.append(token)
    if call_assigned_tools:
        raw_items.extend(call_assigned_tools)

    resolved: list[Any] = []
    seen_keys: set[str] = set()
    for item in raw_items:
        tool_obj = _resolve_tool_item(item, tool_registry=tool_registry, tool_resolver=tool_resolver)
        if tool_obj is None:
            continue
        key = str(getattr(tool_obj, "tool_name", getattr(tool_obj, "__name__", id(tool_obj))))
        if key not in seen_keys:
            seen_keys.add(key)
            resolved.append(tool_obj)
    return resolved


def create_skill_agent_tool(
    skills: list[SkillProperties],
    skills_dir: str | Path,
    base_agent_model: Model | ModelRouter | None = None,
    additional_tools: list[Any] | None = None,
    *,
    per_skill_tools: dict[str, list[Any]] | None = None,
    tool_registry: dict[str, Any] | None = None,
    available_tools_registry: dict[str, Any] | None = None,
    tool_resolver: Callable[[str], Any] | None = None,
    sandbox: Any | None = None,
) -> Any:
    """Create a Strands tool that uses an isolated sub-agent for skill execution (Pattern #3: Meta-Tool / Agent as Tool).

    Args:
        skills: List of discovered skill properties
        skills_dir: Base directory containing skills
        base_agent_model: Default model for sub-agents (optional)
        additional_tools: Tools (objects or names) to provide to all skill sub-agents (optional)
        per_skill_tools: Optional dict mapping skill_name -> list of tools (objects or names) for that skill
        tool_registry: Optional dict mapping tool_name -> tool object for resolving tool names
        available_tools_registry: Optional alias for tool_registry
        tool_resolver: Optional callable(tool_name) -> tool object
        sandbox: Optional Strands Sandbox instance (`DockerSandbox`, `SshSandbox`, `PosixShellSandbox`)
            for sandbox-routed execution (per https://strandsagents.com/docs/user-guide/sdk/sandbox/index.md).

    Returns:
        A Strands tool function `use_skill` decorated with @tool
    """
    skills_dir = Path(skills_dir).expanduser().resolve()

    skill_map = {s.name: s for s in skills}
    lower_map = {s.name.lower(): s for s in skills}

    effective_registry = tool_registry or available_tools_registry
    if effective_registry:
        register_available_tools(effective_registry)
    if additional_tools:
        register_available_tools([t for t in additional_tools if not isinstance(t, str)])

    model: Model | ModelRouter | None
    try:
        model = base_agent_model or get_gemini_agent_model()
    except Exception:
        model = base_agent_model

    def get_skill_subdirectories(skill_name: str) -> dict[str, list[str]]:
        """Return the discovered `references/`, `scripts/`, and `assets/` files for a skill."""
        skill = (
            skill_map[skill_name]
            if skill_name in skill_map
            else lower_map.get(skill_name.lower()) or validate_skill_name(skill_name, skill_map)
        )
        s_dir = Path(skill.skill_dir).resolve()
        cats = scan_skill_resources_by_category(s_dir)
        return {
            k: [p.relative_to(s_dir).as_posix() for p in v]
            for k, v in cats.items()
        }

    @tool
    async def use_skill(
        skill_name: str,
        request: str,
        assigned_tools: list[str] | None = None,
    ) -> AsyncIterator[Any]:
        """Execute a specialized skill in an isolated sub-agent with real-time streaming (Pattern #3).

        Automatically equips the sub-agent with:
        - `query_skill_references` when the skill has a `references/` subdirectory (Knowledge Base)
        - `run_skill_script` when the skill has a `scripts/` subdirectory (Sandboxed runnable code)
        - `use_skill_asset` when the skill has an `assets/` subdirectory (Integrable components & templates)

        Args:
            skill_name: Name of the skill to use (see system prompt for available skills)
            request: Specific request or task for the skill sub-agent to accomplish
            assigned_tools: Optional list of additional tool names from the Strands tool registry
                to assign to this skill sub-agent for this execution.

        Yields:
            dict: Intermediate events with keys: skill_name, agent, event, assigned_tools

        Returns:
            Result from the isolated skill sub-agent execution
        """
        skill = (
            skill_map[skill_name]
            if skill_name in skill_map
            else lower_map.get(skill_name.lower()) or validate_skill_name(skill_name, skill_map)
        )

        try:
            logger.info(f"Streaming skill '{skill.name}' execution in isolated sub-agent")

            instructions = load_instructions(skill.path)
            effective_tools = _resolve_skill_tools(
                skill,
                additional_tools=additional_tools,
                per_skill_tools=per_skill_tools,
                call_assigned_tools=assigned_tools,
                tool_registry=effective_registry,
                tool_resolver=tool_resolver,
            )

            sub_agent = _create_skill_agent(
                skill,
                instructions,
                model,
                effective_tools,
                sandbox=sandbox,
            )

            result = None
            tool_names = [
                str(getattr(t, "tool_name", getattr(t, "__name__", str(t))))
                for t in effective_tools
            ]

            async for event in sub_agent.stream_async(request):
                yield {
                    "skill_name": skill.name,
                    "agent": sub_agent,
                    "assigned_tools": tool_names,
                    "event": event,
                }
                if "result" in event:
                    result = event["result"]

            logger.info(f"Skill '{skill.name}' execution completed")

            if result is not None:
                yield str(result.message) if hasattr(result, "message") else str(result)
            else:
                yield f"Skill '{skill.name}' completed successfully"

        except Exception as e:
            logger.error(f"Error executing skill '{skill_name}': {e}", exc_info=True)
            raise SkillActivationError(
                f"Failed to execute skill '{skill_name}': {e}"
            ) from e

    # Expose helpers on the returned tool function for inspection/configuration
    use_skill.skill_map = skill_map  # type: ignore[attr-defined]
    use_skill.assign_tools = assign_tools_to_skill  # type: ignore[attr-defined]
    use_skill.get_assigned_tools = get_assigned_skill_tools  # type: ignore[attr-defined]
    use_skill.get_skill_subdirectories = get_skill_subdirectories  # type: ignore[attr-defined]
    return use_skill


def _create_skill_agent(
    skill: SkillProperties,
    instructions: str,
    model: Model | ModelRouter | None = None,
    additional_tools: list[Any] | None = None,
    *,
    sandbox: Any | None = None,
) -> Agent:
    """Create a sub-agent configured for a specific skill with header, resources, subdirectory tools, and assigned tools."""
    skill_name = skill.name

    header = build_skill_header(skill, include_resources=True)
    system_prompt = generate_skill_instructions_prompt(f"{header}{instructions}")

    tools = _resolve_skill_tools(
        skill,
        additional_tools=additional_tools,
    )

    if tools:
        tool_list_str = ", ".join(
            str(getattr(t, "tool_name", getattr(t, "__name__", str(t)))) for t in tools
        )
        system_prompt += f"\n\n## Assigned Tools\nYou have been assigned the following tools: `{tool_list_str}`.\n"

    agent_kwargs: dict[str, Any] = {
        "model": model,
        "tools": tools if tools else None,
        "system_prompt": system_prompt,
        "name": f"skill-{skill_name}",
        "description": skill.description,
        "callback_handler": None,
    }
    if isinstance(model, ModelRouter):
        agent_kwargs["retry_strategy"] = None
    if sandbox is not None:
        agent_kwargs["sandbox"] = sandbox

    return Agent(**agent_kwargs)


__all__ = [
    "_create_skill_agent",
    "assign_tools_to_skill",
    "build_skill_subdirectory_tools",
    "create_skill_agent_tool",
    "get_assigned_skill_tools",
    "register_available_tools",
    "set_default_skill_tools",
]
