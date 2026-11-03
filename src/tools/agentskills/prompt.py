"""Generate skills prompt for agent system prompts

This module provides XML-formatted prompt generation following the AgentSkills.io specification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .models import SkillProperties

# Directory paths for agent file operations (fall back to tempfile on read-only container filesystems)
ROOT_DIR = Path(__file__).parent.parent  # Project root
SCRATCH_DIR = ROOT_DIR / "_scratch"
OUTPUT_DIR = ROOT_DIR / "_output"

try:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    _TMP_ROOT = Path(tempfile.gettempdir()) / "strands_agentskills"
    SCRATCH_DIR = _TMP_ROOT / "_scratch"
    OUTPUT_DIR = _TMP_ROOT / "_output"
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_SYSTEM_PROMPT = """
You are a helpful AI assistant. You have access to a skills library that provides specialized capabilities and domain knowledge.

## Tool usage policy

- Use specialized tools instead of bash commands when possible, as this provides a better user experience. Reserve bash tools exclusively for actual system commands and terminal operations that require shell execution. 
- After completing a task that involves tool use, provide a quick summary of the work you've done.

<file_operations_policy>
- **Root directory**: `{root_dir}` - All operations must stay within this boundary
- **Scratch directory**: `{root_dir}/_scratch` - Use for ALL temporary/intermediate files
- **Output directory**: `{root_dir}/_output` - Final deliverables go here
- **[IMPORTANT]**: Never use absolute paths like `/home`, `/tmp`, `/etc`, or `~` that fall outside the root boundary. 
</file_operations_policy>
"""

SKILLS_SYSTEM_PROMPT = """
{default_system_prompt}

## Skills System

You have access to a skills library that provides specialized capabilities and domain knowledge.

<skills_instructions>
**How to Use Skills:**

Your efforts are greatly aided by reading the skill documentation BEFORE writing any code, creating any files, or using any computer tools.
Skills follow a **progressive disclosure** pattern - you know they exist (name + description above), but you only read the full instructions when needed:

1. **Recognize when a skill applies**: Check if the user's task matches any skill's description
2. **Read the skill's full instructions**: 
   - If a `skill` tool is available, call it with the skill name
     - `skill(skill_name="web-research")` - invoke the web-research skill
   - When a user's request matches one of the available skills, use the use_skill tool
     - `use_skill(skill_name="skill-name", request="specific request")`
   - Or read the FastMCP skill resource directly via `skill://<skill-name>/SKILL.md` and `skill://<skill-name>/_manifest`
   - Only use skills listed in <available_skills> below
3. **Follow the skill's instructions**: SKILL.md contains step-by-step workflows, best practices, and examples
4. **Leverage skill subdirectories**:
   - `references/`: Treat as a domain knowledge base to search and cite (`query_skill_references`).
   - `scripts/`: Treat as runnable code to execute inside the skill's sandbox (`run_skill_script`).
   - `assets/`: Treat as reusable components and templates to integrate into what you are creating (`use_skill_asset`).

**When to Use Skills:**
- When the user's request matches a skill's domain (e.g., "research X" → web-research skill)
- When you need specialized knowledge or structured workflows
- When a skill provides proven patterns for complex tasks

**Remember:** Skills are tools to make you more capable and consistent. When in doubt, check if a skill exists for the task!
</skills_instructions>

<available_skills>
{skills_list}
</available_skills>
"""

SKILL_INSTRUCTIONS_PROMPT = """
{default_system_prompt}

## Skill Execution Guidelines

<skills_instructions>
1. **Follow the instructions**: Instructions contain step-by-step workflows, best practices, and examples.
2. **Knowledge Base (`references/`)**: When a `references/` subdirectory is present, use `query_skill_references` (with `action="list"`, `"search"`, or `"read"`) to ground your work in the skill's authoritative reference documentation.
3. **Sandboxed Scripts (`scripts/`)**: When a `scripts/` subdirectory is present, use `run_skill_script` (with `action="list"`, `"inspect"`, or `"run"`) to execute or inspect the skill's runnable scripts inside an isolated sandbox directory.
4. **Integrable Components (`assets/`)**: When an `assets/` subdirectory is present, treat its contents as reusable components, templates, and building blocks that can be read or integrated directly into what you are creating via `use_skill_asset` (with `action="list"`, `"read"`, or `"integrate"`).
</skills_instructions>

## Instructions

{instructions}
"""


def generate_skills_prompt(skills: list[SkillProperties]) -> str:
    """Generate XML system prompt section from SkillProperties list.

    This generates a concise prompt with skill metadata only (Phase 1 of Progressive Disclosure),
    following the AgentSkills.io specification format using XML.

    Args:
        skills: List of discovered skill properties

    Returns:
        XML formatted prompt text with <available_skills> section
    """
    if not skills:
        return ""

    skill_elements = []
    for skill in sorted(skills, key=lambda s: s.name):
        skill_xml = (
            "  <skill>\n"
            f"    <name>{skill.name}</name>\n"
            f"    <description>{skill.description}</description>\n"
            f"    <location>{skill.path}</location>\n"
            f"    <resource_uri>skill://{skill.name}/SKILL.md</resource_uri>\n"
            "  </skill>"
        )
        skill_elements.append(skill_xml)

    skills_list = "\n".join(skill_elements)

    return SKILLS_SYSTEM_PROMPT.format(
        default_system_prompt=generate_default_system_prompt(),
        skills_list=skills_list,
    )


def generate_default_system_prompt() -> str:
    """Generate default system prompt."""
    return DEFAULT_SYSTEM_PROMPT.format(
        root_dir=str(ROOT_DIR.resolve())
    )


def generate_skill_instructions_prompt(instructions: str) -> str:
    """Generate skill instructions prompt."""
    return SKILL_INSTRUCTIONS_PROMPT.format(
        default_system_prompt=generate_default_system_prompt(),
        instructions=instructions,
    )


__all__ = [
    "generate_default_system_prompt",
    "generate_skill_instructions_prompt",
    "generate_skills_prompt",
]
