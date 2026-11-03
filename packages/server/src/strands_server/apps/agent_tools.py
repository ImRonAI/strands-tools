# pyright: strict
"""Strands Agent Tools workspace: Official strands-agents/tools + heterogeneous graph."""

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


class CalculatorRunForm(BaseModel):
    expression: str = "2 * sin(pi / 4) + sqrt(16)"
    mode: str = "evaluate"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-agent-tools")

agent_tools_list = register_list_backend(
    app,
    name="agent_tools_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"query": "strands_tools"},
    ),
)
agent_tool_detail = register_detail_backend(
    app,
    name="agent_tool_detail",
    tool="search",
    id_param="query",
    static_args={"query": "strands_tools"},
)
calculator_run = register_form_backend(
    app, name="calculator_run", tool="calculator", model=CalculatorRunForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Official Agent Tools Workspace (49 Core Tools + Heterogeneous Graph)",
        list_backend=agent_tools_list,
        columns=COLUMNS,
        detail_backend=agent_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(CalculatorRunForm, calculator_run),
        notes=(
            "Includes calculator, current_time, file_read, file_write, editor, shell, python_repl, http_request, swarm, workflow, graph, heterogeneous_graph, use_aws, memory, and more.",
        ),
    )


@app.ui("agent_tools_workspace", description="Open the official Strands Agent Tools workspace.")
def agent_tools_workspace() -> PrefabApp:
    return workspace()
