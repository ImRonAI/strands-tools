# pyright: strict
"""FastMCP Agent Skills Providers (`SkillsDirectoryProvider`, `SkillProvider`, and Vendor Skill Providers).

Exposes all workspace skills (`src/strands_tools/sessions_and_skills/sample_agent_skills/skills`,
`src/skills`, and existing local vendor skill directories) as native FastMCP `skill://` MCP resources:
- `skill://{name}/SKILL.md`: Main skill instruction file (`text/markdown`)
- `skill://{name}/_manifest`: JSON manifest listing all files (`references/`, `scripts/`, `assets/`) with size & sha256 hash
- `skill://{name}/{path*}`: ResourceTemplate for reading any supporting file in `references/`, `scripts/`, or `assets/`
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastmcp.server.providers.skills import (
    ClaudeSkillsProvider,
    CodexSkillsProvider,
    CopilotSkillsProvider,
    CursorSkillsProvider,
    GeminiSkillsProvider,
    GooseSkillsProvider,
    OpenCodeSkillsProvider,
    SkillProvider,
    SkillsDirectoryProvider,
    VSCodeSkillsProvider,
)

from strands_server.catalog_loader import SAMPLE_SKILLS_DIR, SKILLS_DIR

_CACHED_PROVIDER: dict[str, SkillsDirectoryProvider] = {}

VENDOR_SKILL_CANDIDATES: tuple[Path, ...] = (
    Path.home() / ".claude" / "skills",
    Path.home() / ".gemini" / "skills",
    Path.home() / ".cursor" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".copilot" / "skills",
    Path.home() / ".config" / "agents" / "skills",
    Path.home() / ".config" / "opencode" / "skills",
)


def get_all_skill_roots(*, include_vendor_roots: bool = True) -> list[Path]:
    """Return all existing workspace and vendor skill root directories."""
    roots: list[Path] = []
    seen: set[Path] = set()
    candidates: list[Path] = [SAMPLE_SKILLS_DIR, SKILLS_DIR]
    if include_vendor_roots:
        candidates.extend(VENDOR_SKILL_CANDIDATES)
    for root in candidates:
        resolved = root.expanduser().resolve()
        if resolved not in seen and resolved.exists() and resolved.is_dir():
            roots.append(resolved)
            seen.add(resolved)
    return roots


def get_skills_directory_provider(
    *,
    supporting_files: Literal["template", "resources"] = "template",
    reload: bool = False,
    include_vendor_roots: bool = True,
) -> SkillsDirectoryProvider:
    """Return a cached `SkillsDirectoryProvider` exposing all Strands Agent Skills as `skill://` MCP resources."""
    cache_key = f"{supporting_files}:{reload}:{include_vendor_roots}"
    if cache_key in _CACHED_PROVIDER and not reload:
        return _CACHED_PROVIDER[cache_key]

    roots = get_all_skill_roots(include_vendor_roots=include_vendor_roots)
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
    "ClaudeSkillsProvider",
    "CodexSkillsProvider",
    "CopilotSkillsProvider",
    "CursorSkillsProvider",
    "GeminiSkillsProvider",
    "GooseSkillsProvider",
    "OpenCodeSkillsProvider",
    "SkillProvider",
    "SkillsDirectoryProvider",
    "VENDOR_SKILL_CANDIDATES",
    "VSCodeSkillsProvider",
    "get_all_skill_roots",
    "get_skills_directory_provider",
]
