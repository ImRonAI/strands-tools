"""Utility functions for skill tools.

Shared functions used by skill tool implementations, including structured discovery
for `references/` (knowledge base), `scripts/` (sandboxed runnable code), and
`assets/` (integrable components & templates), plus FastMCP `skill://` resource URIs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .errors import SkillNotFoundError
from .models import SkillProperties

logger = logging.getLogger(__name__)


def validate_skill_name(skill_name: str, skill_map: dict[str, SkillProperties]) -> SkillProperties:
    """Validate that a skill exists and return its properties.

    Args:
        skill_name: Name of the skill to validate
        skill_map: Dictionary mapping skill names to SkillProperties

    Returns:
        SkillProperties for the validated skill

    Raises:
        SkillNotFoundError: If the skill doesn't exist
    """
    if skill_name not in skill_map:
        available = ", ".join(skill_map.keys())
        raise SkillNotFoundError(
            f"Skill '{skill_name}' not found. "
            f"Available skills: {available}"
        )
    return skill_map[skill_name]


def scan_skill_resources_by_category(skill_dir: Path) -> dict[str, list[Path]]:
    """Scan skill directory and categorize files into `references`, `scripts`, and `assets`.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Dictionary with keys `"references"`, `"scripts"`, and `"assets"`, each mapping
        to a sorted list of resolved file `Path` objects inside that subdirectory.
    """
    categorized: dict[str, list[Path]] = {
        "references": [],
        "scripts": [],
        "assets": [],
    }
    resolved_root = skill_dir.resolve()
    for subdir in ("references", "scripts", "assets"):
        resource_dir = skill_dir / subdir
        if resource_dir.exists() and resource_dir.is_dir():
            for file_path in sorted(resource_dir.rglob("*")):
                if file_path.is_file():
                    resolved_file = file_path.resolve()
                    if resolved_file.is_relative_to(resolved_root):
                        categorized[subdir].append(resolved_file)
    return categorized


def scan_skill_resources(skill_dir: Path) -> list[str]:
    """Scan skill directory for available resources.

    Scans the standard subdirectories (scripts, references, assets)
    and returns a list of absolute file paths.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        List of absolute file paths to resources
    """
    categorized = scan_skill_resources_by_category(skill_dir)
    resources: list[str] = []
    for subdir in ("scripts", "references", "assets"):
        for file_path in categorized[subdir]:
            resources.append(str(file_path.absolute()))
    return resources


def build_skill_header(
    skill: SkillProperties,
    include_resources: bool = True,
) -> str:
    """Build a header string with skill metadata, FastMCP `skill://` URIs, and categorized resources.

    Args:
        skill: The skill's properties
        include_resources: Whether to scan and include resource lists

    Returns:
        Formatted header string
    """
    header = (
        f"# Skill: {skill.name}\n\n"
        f"**Description:** {skill.description}\n\n"
        f"**Skill Directory:** `{skill.skill_dir}/`\n"
        f"**FastMCP Resource URI:** `skill://{skill.name}/SKILL.md` (Manifest: `skill://{skill.name}/_manifest`)\n\n"
    )

    if skill.allowed_tools:
        header += f"\n**IMPORTANT:** Only use these tools: `{skill.allowed_tools}`\n"

    if include_resources:
        skill_dir = Path(skill.skill_dir).resolve()
        categorized = scan_skill_resources_by_category(skill_dir)
        all_resources = scan_skill_resources(skill_dir)

        if all_resources:
            header += "\n**Available Resources:**\n"
            for resource in all_resources:
                header += f"- `{resource}`\n"
            header += "\n"

        if categorized["references"]:
            header += (
                "### Knowledge Base (`references/`)\n"
                "Use these reference documents as your authoritative domain knowledge base "
                "(searchable and readable via `query_skill_references` or `skill://` resources):\n"
            )
            for ref_file in categorized["references"]:
                rel = ref_file.relative_to(skill_dir).as_posix()
                header += f"- `{rel}` (`skill://{skill.name}/{rel}`)\n"
            header += "\n"

        if categorized["scripts"]:
            header += (
                "### Sandboxed Runnable Scripts (`scripts/`)\n"
                "Execute or inspect these scripts inside the isolated skill sandbox via `run_skill_script`:\n"
            )
            for script_file in categorized["scripts"]:
                rel = script_file.relative_to(skill_dir).as_posix()
                header += f"- `{rel}` (`skill://{skill.name}/{rel}`)\n"
            header += "\n"

        if categorized["assets"]:
            header += (
                "### Integrable Components & Assets (`assets/`)\n"
                "Treat these files as reusable UI/code/document components and templates that can be "
                "inspected and integrated directly into what you are creating via `use_skill_asset`:\n"
            )
            for asset_file in categorized["assets"]:
                rel = asset_file.relative_to(skill_dir).as_posix()
                header += f"- `{rel}` (`skill://{skill.name}/{rel}`)\n"
            header += "\n"

    header += "---\n\n"
    return header


__all__ = [
    "build_skill_header",
    "scan_skill_resources",
    "scan_skill_resources_by_category",
    "validate_skill_name",
]
