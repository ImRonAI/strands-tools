"""Tool module for Agent Skills

Provides tools for skill activation in two modes:
- Pattern #2 (Inline Mode): Skills loaded into main agent context (skill.py)
- Pattern #3 (Agent as Tool / Meta-Tool Mode): Skills run in isolated sub-agents with assignable tools (agent_skill.py)
"""

from .agent_skill import (
    _create_skill_agent,
    assign_tools_to_skill,
    build_skill_subdirectory_tools,
    create_skill_agent_tool,
    get_assigned_skill_tools,
    register_available_tools,
    set_default_skill_tools,
)
from .skill import create_skill_tool

__all__ = [
    "create_skill_tool",
    "create_skill_agent_tool",
    "_create_skill_agent",
    "build_skill_subdirectory_tools",
    "register_available_tools",
    "assign_tools_to_skill",
    "set_default_skill_tools",
    "get_assigned_skill_tools",
]
