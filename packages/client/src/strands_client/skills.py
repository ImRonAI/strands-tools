# pyright: strict
"""Native FastMCP 4.1.0 client utilities for discovering, inspecting, downloading, and syncing Agent Skills (`skill://`)."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

from fastmcp.utilities import skills as _fastmcp_skills
from fastmcp.utilities.skills import SkillFile, SkillManifest, SkillSummary

from strands_client.connection import StrandsConnection

_raw_list_skills: object = getattr(_fastmcp_skills, "list_skills")
_raw_get_skill_manifest: object = getattr(_fastmcp_skills, "get_skill_manifest")
_raw_download_skill: object = getattr(_fastmcp_skills, "download_skill")
_raw_sync_skills: object = getattr(_fastmcp_skills, "sync_skills")

list_skills = cast(
    Callable[[StrandsConnection], Awaitable[list[SkillSummary]]],
    _raw_list_skills,
)
get_skill_manifest = cast(
    Callable[[StrandsConnection, str], Awaitable[SkillManifest]],
    _raw_get_skill_manifest,
)
download_skill = cast(
    Callable[..., Awaitable[Path]],
    _raw_download_skill,
)
sync_skills = cast(
    Callable[..., Awaitable[list[Path]]],
    _raw_sync_skills,
)

__all__ = [
    "SkillFile",
    "SkillManifest",
    "SkillSummary",
    "download_skill",
    "get_skill_manifest",
    "list_skills",
    "sync_skills",
]
