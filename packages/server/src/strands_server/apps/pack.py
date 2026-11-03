# pyright: strict
"""Strands Pack workspace: All non-Google Strands Pack tools + Runtime handlers."""

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


class PackJobRunnerForm(BaseModel):
    action: str = "list"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-pack")

pack_tools_list = register_list_backend(
    app,
    name="pack_tools_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"query": "strands_pack"},
    ),
)
pack_tool_detail = register_detail_backend(
    app,
    name="pack_tool_detail",
    tool="search",
    id_param="query",
    static_args={"query": "strands_pack"},
)
pack_job_run = register_form_backend(
    app, name="pack_job_run", tool="pack_runtime_job_runner", model=PackJobRunnerForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Pack & Runtime Workspace (45 Tools + Approval & Job Runner)",
        list_backend=pack_tools_list,
        columns=COLUMNS,
        detail_backend=pack_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(PackJobRunnerForm, pack_job_run),
        notes=(
            "Includes all non-Google tools from strands-pack, YouTube tools, and runtime approval_handler & job_runner_handler.",
            "Google Workspace/Gemini tools from strands-pack are excluded per specification.",
        ),
    )


@app.ui("pack_workspace", description="Open the Strands Pack & Runtime workspace.")
def pack_workspace() -> PrefabApp:
    return workspace()
