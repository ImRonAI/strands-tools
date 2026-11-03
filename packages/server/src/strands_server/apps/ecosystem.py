# pyright: strict
"""Strands.my Ecosystem & Authentication workspace: All 27+ suites and credential management."""

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


class ConfigureCredentialForm(BaseModel):
    env_var: str = "BYPASS_TOOL_CONSENT"
    value: str = "true"


COLUMNS = (
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tool_count", "Tools"),
    ColumnSpec("sample_tools", "Sample Tools"),
)

app = FastMCPApp("strands-ecosystem")

ecosystem_suites_list = register_list_backend(
    app,
    name="ecosystem_suites_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"action": "list_suites"},
    ),
)
ecosystem_suite_detail = register_detail_backend(
    app,
    name="ecosystem_suite_detail",
    tool="search",
    id_param="suite",
    static_args={"action": "list_tools"},
)
ecosystem_cred_configure = register_form_backend(
    app,
    name="ecosystem_cred_configure",
    tool="strands_configure_credentials",
    model=ConfigureCredentialForm,
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands.my Ecosystem Catalog & Credentials Workspace",
        list_backend=ecosystem_suites_list,
        columns=COLUMNS,
        detail_backend=ecosystem_suite_detail,
        detail_fields=(("text", "Suite Tools"),),
        create_form=(ConfigureCredentialForm, ecosystem_cred_configure),
        row_id_key="suite",
        notes=(
            "Includes all 12 core repositories plus 22 additional strands.my packages (Cloudflare, SQL, HackerOne, UCP, ERC8004, AgentCore, RenderCV, Plan, Olostep, OmniVoice, Osmo, ADB, Transformers, Diffusers, Strudel, BitChat, iCloud, iOS, CAD, Apify, Xa11y, Stigmer).",
        ),
    )


@app.ui("ecosystem_workspace", description="Open the Strands.my Ecosystem Catalog & Credentials workspace.")
def ecosystem_workspace() -> PrefabApp:
    return workspace()
