# pyright: strict
"""Domain FastMCPApp providers. Mounted on the operations child before CodeMode.

`ALL_APPS` is the single import point for `server.build_operations`. App names are
unique server-wide (`strands-<domain>`).
"""

from fastmcp.apps.app import FastMCPApp

from strands_server.apps import (
    agent_tools,
    ccxt,
    docs,
    ecosystem,
    fun_tools,
    google,
    harness,
    inspect_app,
    pack,
    skills,
    telegram,
    utcp,
    youtube,
    zero,
)

ALL_APPS: tuple[FastMCPApp, ...] = (
    google.app,
    fun_tools.app,
    agent_tools.app,
    pack.app,
    youtube.app,
    telegram.app,
    zero.app,
    utcp.app,
    harness.app,
    docs.app,
    skills.app,
    ccxt.app,
    inspect_app.app,
    ecosystem.app,
)

__all__ = ["ALL_APPS"]
