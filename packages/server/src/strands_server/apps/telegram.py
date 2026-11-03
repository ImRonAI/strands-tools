# pyright: strict
"""Strands Telegram workspace: Telegram Bot API & background Telegram Listener."""

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

GENERATED_TOOLS = frozenset({"telegram", "telegram_listener"})


class TelegramListenerStatusForm(BaseModel):
    action: str = "status"


COLUMNS = (
    ColumnSpec("name", "Tool"),
    ColumnSpec("suite", "Suite"),
    ColumnSpec("tags", "Tags"),
    ColumnSpec("description", "Description"),
)

app = FastMCPApp("strands-telegram")

telegram_tools_list = register_list_backend(
    app,
    name="telegram_tools_list",
    spec=ListSpec(
        tool="search",
        data_path=("rows",),
        columns=COLUMNS,
        paging="none",
        static_args={"query": "telegram"},
    ),
)
telegram_tool_detail = register_detail_backend(
    app,
    name="telegram_tool_detail",
    tool="search",
    id_param="query",
    static_args={"query": "telegram"},
)
telegram_listener_run = register_form_backend(
    app, name="telegram_listener_run", tool="telegram_listener", model=TelegramListenerStatusForm
)


def workspace() -> PrefabApp:
    return list_workspace(
        title="Strands Telegram & Telegram Listener Workspace",
        list_backend=telegram_tools_list,
        columns=COLUMNS,
        detail_backend=telegram_tool_detail,
        detail_fields=(("text", "Details"),),
        create_form=(TelegramListenerStatusForm, telegram_listener_run),
        notes=(
            "Includes telegram (60+ Bot API actions) and telegram_listener (real-time polling & event queue).",
            "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_DEFAULT_CHAT_ID via strands_configure_credentials.",
        ),
    )


@app.ui("telegram_workspace", description="Open the Strands Telegram & Telegram Listener workspace.")
def telegram_workspace() -> PrefabApp:
    return workspace()
