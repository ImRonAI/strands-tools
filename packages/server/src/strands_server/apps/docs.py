# pyright: strict
"""Strands Document MCP Server workspace: search_docs and fetch_doc over Strands documentation."""

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

GENERATED_TOOLS = frozenset({"search_docs", "fetch_doc"})


class SearchDocsForm(BaseModel):
    query: str = "mcp tools"
    k: int = 5


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-docs")

docs_tools_list = register_list_backend(
    app,
    name="docs_tools_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"query": "strands_docs_mcp"},
    ),
)
docs_tool_detail = register_detail_backend(
    app,
    name="docs_tool_detail",
    tool="search",
    id_param="query",
    static_args={"query": "strands_docs_mcp"},
)
docs_search_run = register_form_backend(
    app, name="docs_search_run", tool="search_docs", model=SearchDocsForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Document MCP Server Workspace (search_docs & fetch_doc)",
        list_backend=docs_tools_list,
        columns=COLUMNS,
        detail_backend=docs_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(SearchDocsForm, docs_search_run),
        notes=(
            "BM25-indexed search_docs and full-page fetch_doc from ImRonAI/strands-harness-sdk-python/strands-mcp.",
        ),
    )


@app.ui("docs_workspace", description="Open the Strands Document MCP Server workspace.")
def docs_workspace() -> PrefabApp:
    return workspace()
