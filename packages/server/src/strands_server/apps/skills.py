"""Strands Agent Skills workspace: Pattern #2 (`skill`) & Pattern #3 (`use_skill` with assignable tools)."""

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

GENERATED_TOOLS = frozenset({"skill", "use_skill", "configure_skill_tools", "list_available_skills"})


class AssignSkillToolsForm(BaseModel):
    action: str = "assign"
    skill_name: str = "file-processing"
    tool_names: str = "calculator,current_time,file_read,file_write"


COLUMNS = (
    ColumnSpec("name", "Skill Name"),
    ColumnSpec("description", "Description"),
    ColumnSpec("path", "Path"),
)

app = FastMCPApp("strands-skills")

skills_list = register_list_backend(
    app,
    name="skills_list",
    spec=ListSpec(
        tool="strands_my_catalog",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_skills", "limit": 50},
    ),
)
skill_detail = register_detail_backend(
    app,
    name="skill_detail",
    tool="skill",
    id_param="skill_name",
)
skill_assign_tools = register_form_backend(
    app, name="skill_assign_tools", tool="configure_skill_tools", model=AssignSkillToolsForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Agent Skills Workspace (Pattern #2 skill & Pattern #3 use_skill)",
        list_backend=skills_list,
        columns=COLUMNS,
        detail_backend=skill_detail,
        detail_fields=(("text", "Skill Instructions"),),
        create_form=(AssignSkillToolsForm, skill_assign_tools),
        notes=(
            "Implements Pattern #2 (create_skill_tool -> skill) and Pattern #3 (create_skill_agent_tool -> use_skill).",
            "Pattern #3 (use_skill) can be dynamically assigned any tools from the server catalog via configure_skill_tools or the assigned_tools argument.",
        ),
    )


@app.ui("skills_workspace", description="Open the Strands Agent Skills (Pattern #2 & Pattern #3) workspace.")
def skills_workspace() -> PrefabApp:
    return workspace()
