# pyright: strict
"""Strands Harness SDK Tools workspace: Sandbox files, Monty programmatic tool caller, subagent, web_fetch, Exa."""

from fastmcp.apps.app import FastMCPApp
from prefab_ui.app import PrefabApp
from pydantic import BaseModel

from strands_server.apps.recipes import (
    ColumnSpec,
    ListSpec,
    list_workspace,
    register_detail_backend,
    register_form_backend,
    register_list_backend,
)

GENERATED_TOOLS = frozenset(
    {
        "read",
        "write",
        "edit",
        "web_fetch",
        "web_search",
        "exa_web_search",
        "programmatic_tool_caller",
        "subagent",
        "bash",
    }
)


class MontyPtcForm(BaseModel):
    code: str = "print('Monty Rust sandbox active:', 6 * 7)"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-harness")

harness_tools_list = register_list_backend(
    app,
    name="harness_tools_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"query": "strands_harness"},
    ),
)
harness_tool_detail = register_detail_backend(
    app,
    name="harness_tool_detail",
    tool="search",
    id_param="query",
    static_args={"query": "strands_harness"},
)
harness_ptc_run = register_form_backend(
    app, name="harness_ptc_run", tool="programmatic_tool_caller", model=MontyPtcForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Harness SDK Tools Workspace (Sandbox File I/O, Monty PTC, Subagent, Web)",
        list_backend=harness_tools_list,
        columns=COLUMNS,
        detail_backend=harness_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(MontyPtcForm, harness_ptc_run),
        notes=(
            "Includes read, write, edit, web_fetch, web_search (exa_web_search), programmatic_tool_caller, subagent, and bash.",
            "programmatic_tool_caller executes Python inside a Monty Rust VM with async access to all registered Strands tools.",
        ),
    )


@app.ui("harness_workspace", description="Open the Strands Harness SDK tools workspace.")
def harness_workspace() -> PrefabApp:
    return workspace()
