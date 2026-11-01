"""Strands Zero workspace: All 20 Zero compiler and toolchain tools."""

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


class ZeroSkillsForm(BaseModel):
    topic: str = "overview"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-zero")

zero_tools_list = register_list_backend(
    app,
    name="zero_tools_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_tools", "suite": "strands_zero"},
    ),
)
zero_tool_detail = register_detail_backend(
    app,
    name="zero_tool_detail",
    tool="strands_my_catalog",
    id_param="query",
    static_args={"action": "list_tools", "suite": "strands_zero"},
)
zero_skills_run = register_form_backend(
    app, name="zero_skills_run", tool="zero_skills", model=ZeroSkillsForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Zero Compiler Toolchain Workspace (20 Tools)",
        list_backend=zero_tools_list,
        columns=COLUMNS,
        detail_backend=zero_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(ZeroSkillsForm, zero_skills_run),
        notes=(
            "Includes all 20 zero_* tools: zero_version, zero_doctor, zero_targets, zero_skills, zero_write, zero_new, zero_check, zero_explain, zero_fix, zero_run, zero_build, zero_ship, zero_test, zero_fmt, zero_graph, zero_size, zero_mem, zero_routes, zero_clean, zero_install.",
        ),
    )


@app.ui("zero_workspace", description="Open the Strands Zero compiler toolchain workspace.")
def zero_workspace() -> PrefabApp:
    return workspace()
