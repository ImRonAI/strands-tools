"""Skill discovery - Phase 1 of Progressive Disclosure

This module implements the discovery phase where skills are scanned
from a directory and their lightweight metadata is loaded.

The discovery process follows these principles:
1. Scan skill directories for SKILL.md files
2. Load only frontmatter metadata (~100 tokens per skill)
3. Validate metadata against Agent Skills specification
4. Return lightweight SkillMetadata objects for prompt injection
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Import from unified modules
from .parser import find_skill_md, load_metadata
from .errors import ParseError, ValidationError
from .models import SkillProperties

logger = logging.getLogger(__name__)

_DISCOVERY_MEM_CACHE: Dict[str, List[SkillProperties]] = {}


def is_safe_path(path: Path, base_dir: Path) -> bool:
    """Validate that path is safely contained within base_dir

    Prevents directory traversal attacks through symlinks or path manipulation.

    Args:
        path: Path to validate
        base_dir: Base directory that should contain the path

    Returns:
        True if path is safe, False otherwise
    """
    try:
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        resolved_path.relative_to(resolved_base)
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def discover_skills(skills_dir: str | Path) -> List[SkillProperties]:
    """Discover all skills in a directory

    Scans the skills directory and loads metadata from each skill's
    SKILL.md frontmatter. This is Phase 1 of progressive disclosure.

    Directory structure:
        skills/
        ├── web-research/
        │   ├── SKILL.md          # Required
        │   ├── scripts/          # Optional
        │   │   └── helper.py
        │   └── references/       # Optional
        │       └── docs.md
        └── code-review/
            └── SKILL.md

    Args:
        skills_dir: Path to directory containing skill subdirectories

    Returns:
        List of SkillProperties objects, sorted by skill name

    Example:
        >>> skills = discover_skills("./skills")
        >>> for skill in skills:
        ...     print(f"{skill.name}: {skill.description}")
        ...     print(f"  Location: {skill.path}")
    """
    skills_dir = Path(skills_dir).expanduser().resolve()
    cache_key = str(skills_dir)
    if cache_key in _DISCOVERY_MEM_CACHE:
        return list(_DISCOVERY_MEM_CACHE[cache_key])

    if not skills_dir.exists():
        logger.info(f"Skills directory does not exist: {skills_dir}")
        return []

    if not skills_dir.is_dir():
        logger.warning(f"Skills path is not a directory: {skills_dir}")
        return []

    disk_cache = skills_dir / ".skills_discovery_cache.json"
    if disk_cache.exists():
        try:
            raw_items = json.loads(disk_cache.read_text(encoding="utf-8"))
            cached_skills: List[SkillProperties] = []
            for item in raw_items:
                raw_path = Path(str(item["path"]))
                raw_skill_dir = Path(str(item.get("skill_dir") or raw_path.parent))
                resolved_skill_dir = (skills_dir / raw_skill_dir.name).resolve()
                resolved_md_path = (resolved_skill_dir / raw_path.name).resolve()
                cached_skills.append(
                    SkillProperties(
                        name=str(item["name"]),
                        description=str(item["description"]),
                        path=str(resolved_md_path if resolved_md_path.exists() else raw_path),
                        skill_dir=str(resolved_skill_dir if resolved_skill_dir.exists() else raw_skill_dir),
                        license=item.get("license"),
                        compatibility=item.get("compatibility"),
                        allowed_tools=item.get("allowed_tools"),
                        metadata=item.get("metadata") or {},
                    )
                )
            _DISCOVERY_MEM_CACHE[cache_key] = cached_skills
            return list(cached_skills)
        except Exception:
            pass

    skills: List[SkillProperties] = []

    # Scan each subdirectory
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        # Security: validate path
        if not is_safe_path(skill_dir, skills_dir):
            logger.warning(f"Skipping unsafe path: {skill_dir}")
            continue

        # Look for SKILL.md
        skill_md_path = find_skill_md(skill_dir)
        if skill_md_path is None:
            logger.debug(f"No SKILL.md found in {skill_dir}")
            continue

        # Security: validate SKILL.md path
        if not is_safe_path(skill_md_path, skills_dir):
            logger.warning(f"Skipping unsafe SKILL.md: {skill_md_path}")
            continue

        # Parse metadata
        try:
            skill_props = load_metadata(skill_dir)
            skills.append(skill_props)
            logger.debug(f"Discovered skill: {skill_props.name}")

        except (ParseError, ValidationError) as e:
            logger.warning(f"Skipping invalid skill in {skill_dir}: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error parsing {skill_dir}: {e}")
            continue

    # Sort by name for consistent ordering
    skills.sort(key=lambda s: s.name)
    _DISCOVERY_MEM_CACHE[cache_key] = list(skills)
    try:
        disk_cache.write_text(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "description": s.description,
                        "path": str(s.path),
                        "skill_dir": str(s.skill_dir),
                        "license": s.license,
                        "compatibility": s.compatibility,
                        "allowed_tools": s.allowed_tools,
                        "metadata": s.metadata,
                    }
                    for s in skills
                ]
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    logger.info(f"Discovered {len(skills)} skills in {skills_dir}")
    return skills
