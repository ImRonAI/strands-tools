"""
strands-zero: Strands Agents tools for the Zero programming language.

Wraps the `zero` CLI (https://zerolang.ai) so AI agents can write, check,
compile, and run Zero code with structured JSON feedback.

Usage:
    from strands import Agent
    from strands_zero import (
        zero_check, zero_run, zero_build, zero_doctor,
        zero_explain, zero_fix, zero_write, zero_skills,
        zero_graph, zero_size, zero_test, zero_new,
        zero_version, zero_install,
    )

    agent = Agent(tools=[zero_check, zero_run, zero_build, zero_explain, zero_write])
    agent("Write a Zero program that prints 'hello' and run it")
"""

from strands_zero._runner import find_zero_binary, run_zero
from strands_zero.tools import (
    zero_version,
    zero_check,
    zero_run,
    zero_build,
    zero_ship,
    zero_test,
    zero_fmt,
    zero_doctor,
    zero_explain,
    zero_fix,
    zero_skills,
    zero_graph,
    zero_size,
    zero_mem,
    zero_routes,
    zero_targets,
    zero_clean,
    zero_new,
    zero_write,
    zero_install,
)

__version__ = "0.1.0"

__all__ = [
    # Core helpers
    "find_zero_binary",
    "run_zero",
    # Tool functions
    "zero_version",
    "zero_check",
    "zero_run",
    "zero_build",
    "zero_ship",
    "zero_test",
    "zero_fmt",
    "zero_doctor",
    "zero_explain",
    "zero_fix",
    "zero_skills",
    "zero_graph",
    "zero_size",
    "zero_mem",
    "zero_routes",
    "zero_targets",
    "zero_clean",
    "zero_new",
    "zero_write",
    "zero_install",
]
