"""Harness-authored tools.

Thin, self-contained tools that fill gaps in the SDK's vended set. Each is a candidate to port
into the core SDK later; keep them minimal and SDK-idiomatic.
"""

from strands.sandbox.not_a_sandbox_local_environment import NotASandboxLocalEnvironment
from strands.vended_tools.shell import make_shell
from strands_harness.tools.file_tools import edit, make_read, read, write
from strands_harness.tools.programmatic_tool_caller import (
    DEFAULT_PROGRAMMATIC_TOOL_CALLER_DESCRIPTION,
    make_programmatic_tool_caller,
    programmatic_tool_caller,
    register_standalone_tools,
)
from strands_harness.tools.subagent import (
    AgentSpec,
    Choice,
    Fixed,
    Inherit,
    Open,
    Option,
    Preset,
    make_subagent,
    subagent,
)
from strands_harness.tools.web_fetch import make_web_fetch, web_fetch
from strands_harness.tools.web_search import exa_web_search, make_exa_web_search

web_search = exa_web_search
bash = make_shell(sandbox=NotASandboxLocalEnvironment(), name="bash")

__all__ = [
    "DEFAULT_PROGRAMMATIC_TOOL_CALLER_DESCRIPTION",
    "AgentSpec",
    "Choice",
    "Fixed",
    "Inherit",
    "Open",
    "Option",
    "Preset",
    "bash",
    "edit",
    "make_programmatic_tool_caller",
    "make_read",
    "make_subagent",
    "exa_web_search",
    "make_exa_web_search",
    "make_web_fetch",
    "programmatic_tool_caller",
    "read",
    "register_standalone_tools",
    "subagent",
    "web_fetch",
    "web_search",
    "write",
]
