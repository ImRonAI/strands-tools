"""Strands Inspect workspace: Package inspection, @watch, @lock, and KernelSandbox."""

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

GENERATED_TOOLS = frozenset({"inspect_tool"})


class InspectPackageForm(BaseModel):
    action: str = "inspect"
    package_name: str = "json"
    include_private: bool = False


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-inspect")

inspect_tools_list = register_list_backend(
    app,
    name="inspect_tools_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_tools", "suite": "strands_inspect"},
    ),
)
inspect_tool_detail = register_detail_backend(
    app,
    name="inspect_tool_detail",
    tool="strands_my_catalog",
    id_param="query",
    static_args={"action": "list_tools", "suite": "strands_inspect"},
)
inspect_package_run = register_form_backend(
    app, name="inspect_package_run", tool="inspect_tool", model=InspectPackageForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Inspect & KernelSandbox Workspace",
        list_backend=inspect_tools_list,
        columns=COLUMNS,
        detail_backend=inspect_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(InspectPackageForm, inspect_package_run),
        notes=(
            "Includes inspect_tool, @watch, @lock, and KernelSandbox from cagataycali/strands-inspect.",
        ),
    )


@app.ui("inspect_workspace", description="Open the Strands Inspect & KernelSandbox workspace.")
def inspect_workspace() -> PrefabApp:
    return workspace()
