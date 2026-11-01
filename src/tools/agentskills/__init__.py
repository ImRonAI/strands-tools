"""Agent Skills - Progressive Disclosure Skill System for Strands Agents SDK

Implements both:
- Pattern #2 (Inline Tool Mode): `create_skill_tool` -> `skill`
- Pattern #3 (Isolated Sub-Agent / Meta-Tool Mode): `create_skill_agent_tool` -> `use_skill`
  with full support for assigning other tools (globally, per-skill, via SKILL.md allowed-tools,
  or per-invocation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from strands import tool as strands_tool

from .agent_model import get_bedrock_agent_model, get_gemini_agent_model
from .discovery import discover_skills
from .errors import (
    ParseError,
    SkillActivationError,
    SkillError,
    SkillNotFoundError,
    ValidationError,
)
from .models import SkillProperties
from .parser import (
    find_skill_md,
    load_instructions,
    load_metadata,
    load_resource,
)
from .prompt import (
    generate_default_system_prompt,
    generate_skill_instructions_prompt,
    generate_skills_prompt,
)
from .tool import (
    _create_skill_agent,
    assign_tools_to_skill,
    build_skill_subdirectory_tools,
    create_skill_agent_tool,
    create_skill_tool,
    get_assigned_skill_tools,
    register_available_tools,
    set_default_skill_tools,
)
from .tool_utils import (
    build_skill_header,
    scan_skill_resources,
    scan_skill_resources_by_category,
    validate_skill_name,
)
from .validator import validate, validate_metadata

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
_CACHED_SKILLS: Optional[List[SkillProperties]] = None


def get_default_skills(skills_dir: str | Path | None = None) -> List[SkillProperties]:
    """Load and cache discovered skills from the workspace skills directory."""
    global _CACHED_SKILLS
    if skills_dir is not None:
        return discover_skills(skills_dir)
    if _CACHED_SKILLS is None:
        _CACHED_SKILLS = discover_skills(DEFAULT_SKILLS_DIR) if DEFAULT_SKILLS_DIR.exists() else []
    return _CACHED_SKILLS


@strands_tool
def configure_skill_tools(
    action: str = "list",
    skill_name: Optional[str] = None,
    tool_names: Optional[List[str]] = None,
    append: bool = True,
) -> Dict[str, Any]:
    """Configure or inspect tools assigned to Pattern #3 (`use_skill`) isolated skill sub-agents.

    Args:
        action: One of "list", "assign", "set_defaults", or "clear".
        skill_name: Skill name when action="assign", "list" (optional), or "clear".
        tool_names: List of tool names from the Strands tool registry to assign.
        append: When action="assign", whether to append to existing per-skill tools (True) or replace (False).

    Returns:
        Dictionary describing the updated or current Pattern #3 tool assignments.
    """
    act = (action or "list").strip().lower()
    if act in ("assign", "assign_skill"):
        if not skill_name:
            return {"status": "error", "error": "skill_name is required for action='assign'"}
        assigned = assign_tools_to_skill(skill_name, list(tool_names or []), append=append)
        return {"status": "success", "skill_name": skill_name, "assigned_tools": assigned}
    if act in ("set_defaults", "set_global"):
        defaults = set_default_skill_tools(list(tool_names or []))
        return {"status": "success", "default_additional_tools": defaults}
    if act == "clear":
        if skill_name:
            assign_tools_to_skill(skill_name, [], append=False)
            return {"status": "success", "cleared": skill_name}
        set_default_skill_tools([])
        return {"status": "success", "cleared": "all_defaults"}
    info = get_assigned_skill_tools(skill_name)
    return {
        "status": "success",
        "total_assignable_tools": len(info.get("available_registry_tools", [])),
        **info,
    }


@strands_tool
def list_available_skills(
    query: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    """Search and list available AgentSkills (SKILL.md packages) in the workspace.

    Args:
        query: Optional case-insensitive substring to filter skill name or description.
        limit: Maximum number of matching skills to return (default 50).

    Returns:
        Dictionary with total discovered count and matching skill metadata.
    """
    skills = get_default_skills()
    q = query.strip().lower()
    matched = [
        s for s in skills
        if not q or q in s.name.lower() or q in s.description.lower()
    ]
    rows = []
    for s in matched[: max(1, min(limit, 500))]:
        cats = scan_skill_resources_by_category(Path(s.skill_dir))
        rows.append(
            {
                "name": s.name,
                "description": s.description[:240],
                "skill_dir": s.skill_dir,
                "resource_uri": f"skill://{s.name}/SKILL.md",
                "manifest_uri": f"skill://{s.name}/_manifest",
                "allowed_tools": s.allowed_tools,
                "assigned_tools": get_assigned_skill_tools(s.name)["effective_tools"],
                "subdirectories": {
                    "references": len(cats["references"]),
                    "scripts": len(cats["scripts"]),
                    "assets": len(cats["assets"]),
                },
            }
        )
    return {
        "total_discovered": len(skills),
        "matched_count": len(matched),
        "skills": rows,
    }


__version__ = "1.0.0"

__all__ = [
    "SkillProperties",
    "find_skill_md",
    "load_metadata",
    "load_instructions",
    "load_resource",
    "validate",
    "validate_metadata",
    "discover_skills",
    "get_default_skills",
    "get_bedrock_agent_model",
    "get_gemini_agent_model",
    "generate_skills_prompt",
    "generate_default_system_prompt",
    "generate_skill_instructions_prompt",
    "create_skill_tool",
    "create_skill_agent_tool",
    "_create_skill_agent",
    "build_skill_subdirectory_tools",
    "register_available_tools",
    "assign_tools_to_skill",
    "set_default_skill_tools",
    "get_assigned_skill_tools",
    "configure_skill_tools",
    "list_available_skills",
    "build_skill_header",
    "scan_skill_resources",
    "scan_skill_resources_by_category",
    "validate_skill_name",
    "SkillError",
    "ParseError",
    "ValidationError",
    "SkillNotFoundError",
    "SkillActivationError",
]
