"""Strands CCXT workspace: Unified cryptocurrency exchange API via `use_ccxt`."""

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

GENERATED_TOOLS = frozenset({"use_ccxt"})


class CcxtQueryForm(BaseModel):
    exchange: str = "kraken"
    method: str = "fetch_status"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-ccxt")

ccxt_tools_list = register_list_backend(
    app,
    name="ccxt_tools_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_tools", "suite": "strands_ccxt"},
    ),
)
ccxt_tool_detail = register_detail_backend(
    app,
    name="ccxt_tool_detail",
    tool="strands_my_catalog",
    id_param="query",
    static_args={"action": "list_tools", "suite": "strands_ccxt"},
)
ccxt_query_run = register_form_backend(
    app, name="ccxt_query_run", tool="use_ccxt", model=CcxtQueryForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands CCXT Cryptocurrency Exchange Workspace",
        list_backend=ccxt_tools_list,
        columns=COLUMNS,
        detail_backend=ccxt_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(CcxtQueryForm, ccxt_query_run),
        notes=(
            "Supports 100+ cryptocurrency exchanges via mertozbas/strands-ccxt (use_ccxt).",
            "Configure CCXT_EXCHANGE_ID, CCXT_API_KEY, and CCXT_SECRET for authenticated methods.",
        ),
    )


@app.ui("ccxt_workspace", description="Open the Strands CCXT cryptocurrency exchange workspace.")
def ccxt_workspace() -> PrefabApp:
    return workspace()
