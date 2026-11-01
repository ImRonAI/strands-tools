"""YAML frontmatter parsing for SKILL.md files

This module handles parsing of SKILL.md files following the AgentSkills.io specification.
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import strictyaml  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from .errors import ParseError, ValidationError

if TYPE_CHECKING:
    from .models import SkillProperties


def find_skill_md(skill_dir: Path) -> Optional[Path]:
    """Find the SKILL.md file in a skill directory

    Prefers SKILL.md (uppercase) but accepts skill.md (lowercase).

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Path to the SKILL.md file, or None if not found
    """
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists():
            return path
    return None


def _parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Parse SKILL.md content into frontmatter and body

    This is the core parsing function that splits SKILL.md into:
    - frontmatter: YAML metadata
    - body: Markdown instructions

    Args:
        content: Raw SKILL.md content

    Returns:
        Tuple of (frontmatter dict, body string)

    Raises:
        ParseError: If frontmatter is invalid
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        raise ParseError("SKILL.md must start with YAML frontmatter (---) and close with ---")

    frontmatter_str = match.group(1)
    body = match.group(2).strip()

    try:
        parsed = strictyaml.load(frontmatter_str)
        frontmatter = parsed.data
    except strictyaml.YAMLError:
        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except Exception as e:
            raise ParseError(f"Invalid YAML in frontmatter: {e}") from e

    if not isinstance(frontmatter, dict):
        raise ParseError("SKILL.md frontmatter must be a YAML mapping")

    # Ensure metadata field is dict of strings
    if "metadata" in frontmatter and isinstance(frontmatter["metadata"], dict):
        frontmatter["metadata"] = {
            str(k): str(v) for k, v in frontmatter["metadata"].items()
        }
    elif frontmatter.get("metadata") is None:
        frontmatter["metadata"] = {}

    return frontmatter, body


def load_metadata(skill_dir: str | Path) -> "SkillProperties":
    """Load skill metadata from SKILL.md frontmatter (Phase 1: ~100 tokens)

    This is Phase 1 of Progressive Disclosure - loads only lightweight metadata
    without the full instructions body.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        SkillProperties with parsed metadata (instructions NOT loaded)

    Raises:
        ParseError: If SKILL.md is missing or has invalid YAML
        ValidationError: If required fields (name, description) are missing
    """
    from .models import SkillProperties

    skill_dir = Path(skill_dir).resolve()
    skill_md = find_skill_md(skill_dir)

    if skill_md is None:
        raise ParseError(f"SKILL.md not found in {skill_dir}")

    # Read file and extract frontmatter (ignoring body)
    content = skill_md.read_text(encoding="utf-8")
    frontmatter, _ = _parse_skill_md(content)

    # Validate required fields
    if "name" not in frontmatter:
        raise ValidationError("Missing required field in frontmatter: name")
    if "description" not in frontmatter:
        raise ValidationError("Missing required field in frontmatter: description")

    name = frontmatter["name"]
    description = frontmatter["description"]

    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Field 'name' must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise ValidationError("Field 'description' must be a non-empty string")

    raw_allowed = frontmatter.get("allowed-tools") or frontmatter.get("allowed_tools")
    if isinstance(raw_allowed, list):
        allowed_tools = ", ".join(str(x).strip() for x in raw_allowed if str(x).strip())
    elif isinstance(raw_allowed, str):
        allowed_tools = raw_allowed.strip()
    else:
        allowed_tools = None

    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return SkillProperties(
        name=name.strip(),
        description=description.strip(),
        path=str(skill_md.absolute()),
        skill_dir=str(skill_dir.absolute()),
        license=frontmatter.get("license"),
        compatibility=frontmatter.get("compatibility"),
        allowed_tools=allowed_tools,
        metadata=metadata,
    )


def load_instructions(skill_path: str | Path) -> str:
    """Load skill instructions from SKILL.md body (Phase 2: <5000 tokens)"""
    skill_path = Path(skill_path)

    try:
        content = skill_path.read_text(encoding="utf-8")
        _, instructions = _parse_skill_md(content)
        return instructions
    except Exception as e:
        raise ParseError(f"Failed to read instructions from {skill_path}: {e}") from e


def load_resource(skill_dir: str | Path, resource_path: str) -> str:
    """Load a resource file from skill directory (Phase 3: as needed)"""
    skill_dir = Path(skill_dir).resolve()
    resource_file = (skill_dir / resource_path).resolve()

    # Security: ensure resource is within skill directory
    try:
        resource_file.relative_to(skill_dir)
    except ValueError as e:
        raise ParseError(f"Resource path '{resource_path}' is outside skill directory") from e

    if not resource_file.exists():
        raise ParseError(f"Resource not found: {resource_path}")

    if not resource_file.is_file():
        raise ParseError(f"Resource is not a file: {resource_path}")

    # File size limit (10MB)
    max_file_size = 10 * 1024 * 1024
    if resource_file.stat().st_size > max_file_size:
        raise ParseError(f"Resource too large (max 10MB): {resource_path}")

    try:
        return resource_file.read_text(encoding="utf-8")
    except Exception as e:
        raise ParseError(f"Failed to read resource {resource_path}: {e}") from e


__all__ = [
    "find_skill_md",
    "load_metadata",
    "load_instructions",
    "load_resource",
]
