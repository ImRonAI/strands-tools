"""FastMCP Agent Skills Provider (`SkillsDirectoryProvider` & `SkillProvider`).

Exposes all workspace skills (`src/strands_tools/sessions_and_skills/sample_agent_skills/skills`
and `src/skills`) as native FastMCP `skill://` MCP resources:
- `skill://{name}/SKILL.md`: Main skill instruction file (`text/markdown`)
- `skill://{name}/_manifest`: JSON manifest listing all files (`references/`, `scripts/`, `assets/`) with size & sha256 hash
- `skill://{name}/{path*}`: ResourceTemplate for reading any supporting file in `references/`, `scripts/`, or `assets/`
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastmcp.server.providers.skills import SkillProvider, SkillsDirectoryProvider

from strands_server.catalog_loader import SAMPLE_SKILLS_DIR, SKILLS_DIR

_CACHED_PROVIDER: dict[str, SkillsDirectoryProvider] = {}


def get_skills_directory_provider(
    *,
    supporting_files: Literal["template", "resources"] = "template",
    reload: bool = False,
) -> SkillsDirectoryProvider:
    """Return a cached `SkillsDirectoryProvider` exposing all Strands Agent Skills as `skill://` MCP resources."""
    cache_key = f"{supporting_files}:{reload}"
    if cache_key in _CACHED_PROVIDER and not reload:
        return _CACHED_PROVIDER[cache_key]

    roots: list[Path] = []
    if SAMPLE_SKILLS_DIR.exists():
        roots.append(SAMPLE_SKILLS_DIR)
    if SKILLS_DIR.exists():
        roots.append(SKILLS_DIR)

    provider = SkillsDirectoryProvider(
        roots=roots,
        reload=reload,
        main_file_name="SKILL.md",
        supporting_files=supporting_files,
    )
    if not reload:
        _CACHED_PROVIDER[cache_key] = provider
    return provider


__all__ = [
    "SkillProvider",
    "SkillsDirectoryProvider",
    "get_skills_directory_provider",
]
