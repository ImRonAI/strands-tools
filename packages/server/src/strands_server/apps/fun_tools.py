# pyright: strict
"""Strands Fun Tools workspace: 17 interactive system, vision, audio, UI, and game tools."""

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
        "human_typer",
        "cursor",
        "clipboard",
        "dynamic_package",
        "template",
        "utility",
        "chess",
        "bluetooth",
        "screen_reader",
        "yolo_vision",
        "face_recognition",
        "take_photo",
        "listen",
        "spinner_generator",
        "npm",
        "dialog",
        "asciimatics_ui",
    }
)


class UtilityRunForm(BaseModel):
    action: str = "uuid"
    text: str = "Strands Fun Tools"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-fun-tools")

fun_tools_list = register_list_backend(
    app,
    name="fun_tools_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"query": "strands_fun_tools"},
    ),
)
fun_tool_detail = register_detail_backend(
    app,
    name="fun_tool_detail",
    tool="search",
    id_param="query",
    static_args={"query": "strands_fun_tools"},
)
fun_utility_run = register_form_backend(
    app, name="fun_utility_run", tool="utility", model=UtilityRunForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Fun Tools Workspace (17 Creative & System Tools)",
        list_backend=fun_tools_list,
        columns=COLUMNS,
        detail_backend=fun_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(UtilityRunForm, fun_utility_run),
        notes=(
            "Includes human_typer, cursor, clipboard, chess, bluetooth, yolo_vision, face_recognition, spinner_generator, and utility.",
        ),
    )


@app.ui("fun_tools_workspace", description="Open the Strands Fun Tools workspace.")
def fun_tools_workspace() -> PrefabApp:
    return workspace()
