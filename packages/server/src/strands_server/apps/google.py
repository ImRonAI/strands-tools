"""Strands Google workspace: Google APIs discovery, OAuth, and Gmail operations."""

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

GENERATED_TOOLS = frozenset({"use_google", "google_auth", "gmail_send", "gmail_reply"})


class GoogleDiscoverForm(BaseModel):
    action: str = "discover"
    search_query: str = "gmail"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-google")

google_tools_list = register_list_backend(
    app,
    name="google_tools_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_tools", "suite": "strands_google"},
    ),
)
google_tool_detail = register_detail_backend(
    app,
    name="google_tool_detail",
    tool="strands_my_catalog",
    id_param="query",
    static_args={"action": "list_tools", "suite": "strands_google"},
)
google_discover_run = register_form_backend(
    app, name="google_discover_run", tool="use_google", model=GoogleDiscoverForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Google Workspace (Discovery, OAuth, Gmail, Calendar, Drive)",
        list_backend=google_tools_list,
        columns=COLUMNS,
        detail_backend=google_tool_detail,
        detail_fields=(("text", "Tool Info"),),
        create_form=(GoogleDiscoverForm, google_discover_run),
        notes=(
            "Includes use_google, google_auth, gmail_send, and gmail_reply from cagataycali/strands-google.",
            "Google tools from strands-pack are excluded in favor of this comprehensive Strands Google suite.",
        ),
    )


@app.ui("google_workspace", description="Open the Strands Google API & Workspace explorer.")
def google_workspace() -> PrefabApp:
    return workspace()
