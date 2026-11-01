"""Strands UTCP workspace: Universal Tool Calling Protocol manual registration & execution."""

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
    {"utcp", "utcp_register_manual", "utcp_list_tools", "utcp_search_tools", "utcp_call_tool"}
)


class UtcpActionForm(BaseModel):
    action: str = "list_tools"
    query: str = ""


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-utcp")

utcp_tools_list = register_list_backend(
    app,
    name="utcp_tools_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_tools", "suite": "strands_utcp"},
    ),
)
utcp_tool_detail = register_detail_backend(
    app,
    name="utcp_tool_detail",
    tool="strands_my_catalog",
    id_param="query",
    static_args={"action": "list_tools", "suite": "strands_utcp"},
)
utcp_action_run = register_form_backend(
    app, name="utcp_action_run", tool="utcp", model=UtcpActionForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands UTCP (Universal Tool Calling Protocol) Workspace",
        list_backend=utcp_tools_list,
        columns=COLUMNS,
        detail_backend=utcp_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(UtcpActionForm, utcp_action_run),
        notes=(
            "Backed by UtcpToolAdapter & UtcpAgentTool from universal-tool-calling-protocol/strands-utcp.",
            "Supports utcp_register_manual, utcp_list_tools, utcp_search_tools, utcp_call_tool, and utcp.",
        ),
    )


@app.ui("utcp_workspace", description="Open the Strands UTCP (Universal Tool Calling Protocol) workspace.")
def utcp_workspace() -> PrefabApp:
    return workspace()
