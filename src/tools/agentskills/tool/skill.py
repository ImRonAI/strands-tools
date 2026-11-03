"""Skill tool for Strands Agents (Pattern #2: Inline Mode)

This module creates a Strands tool for progressive disclosure of skills.
The skill tool loads instructions (and optional bundled resources) into the main agent's context.

For Pattern #3 (Agent as Tool pattern / isolated sub-agents), see agent_skill.py
"""

import logging
from pathlib import Path
from typing import Annotated, Any, List, Optional

from strands import tool

from ..errors import SkillActivationError
from ..models import SkillProperties
from ..tool_utils import build_skill_header, validate_skill_name

logger = logging.getLogger(__name__)


def create_skill_tool(
    skills: List[SkillProperties],
    skills_dir: str | Path,
    include_header: bool = True,
) -> Any:
    """Create a Strands tool for skill activation (Pattern #2: Inline Mode)

    This factory function creates a tool that implements Progressive Disclosure:
    - Phase 1: Metadata in system prompt (already loaded via generate_skills_prompt)
    - Phase 2: Load full instructions when skill is invoked
    - Phase 3: LLM uses file_read or optional resource_path parameter to access resources as needed

    Args:
        skills: List of discovered skill properties
        skills_dir: Base directory containing skills
        include_header: Whether to prepend skill header and resource manifest

    Returns:
        A Strands tool function decorated with @tool
    """
    skills_dir = Path(skills_dir).expanduser().resolve()

    # Create a lookup map for fast skill access (exact and case-insensitive)
    skill_map = {s.name: s for s in skills}
    lower_map = {s.name.lower(): s for s in skills}

    @tool
    def skill(
        skill_name: Annotated[
            str,
            "Name of the AgentSkill to load (use `list_available_skills` or `list_resources` to browse all 697+ skills).",
        ],
        resource_path: Annotated[
            Optional[str],
            "Optional relative path to a bundled file inside the skill directory (e.g. 'references/guide.md', 'scripts/run.py', 'assets/template.tsx'). Omit to load SKILL.md instructions.",
        ] = None,
    ) -> str:
        """Load specialized skill instructions or a bundled skill resource (Pattern #2: Inline Mode).

        Args:
            skill_name: Name of the skill (see system prompt for available skills)
            resource_path: Optional relative path to a bundled resource file inside the skill directory
                (e.g., "references/api-docs.md" or "scripts/helper.py"). Omit to load SKILL.md instructions.

        Returns:
            Full skill instructions (with resource paths) or the requested resource file content.
        """
        resolved_name = skill_name if skill_name in skill_map else lower_map.get(skill_name.lower(), None)
        if isinstance(resolved_name, SkillProperties):
            skill_props = resolved_name
        else:
            skill_props = validate_skill_name(skill_name, skill_map)

        try:
            from ..parser import load_instructions, load_resource

            if resource_path:
                content = load_resource(skill_props.skill_dir, resource_path)
                return f"<skill_resource name=\"{skill_props.name}\" path=\"{resource_path}\">\n{content}\n</skill_resource>"

            instructions = load_instructions(skill_props.path)
            logger.info(f"Loaded skill: {skill_props.name}")
            if include_header:
                header = build_skill_header(skill_props, include_resources=True)
                return f"<skill_instructions name=\"{skill_props.name}\">\n{header}{instructions}\n</skill_instructions>"
            return instructions

        except Exception as e:
            logger.error(f"Error loading skill '{skill_name}': {e}", exc_info=True)
            raise SkillActivationError(
                f"Failed to load skill '{skill_name}': {e}"
            ) from e

    return skill


__all__ = ["create_skill_tool"]
