# pyright: strict
"""Shared Prefab workspace view: list / detail / action form / confirmed actions.

Only installed `prefab_ui` 0.20.2 components and actions are used. UI actions reference
app backends by function (`CallTool(backend)`), which FastMCP resolves to the backend's
identity-addressed name at serialization time.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from prefab_ui.actions import SetState, ShowToast
from prefab_ui.actions.base import Action
from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Alert,
    AlertTitle,
    Button,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    DataTableColumn,
    Dialog,
    Form,
    Heading,
    Input,
    Label,
    Muted,
    Row,
    Tab,
    Tabs,
    Text,
)
from prefab_ui.components.control_flow import If
from prefab_ui.rx import ERROR, EVENT, RESULT, STATE, Rx
from pydantic import BaseModel

from strands_server.apps.recipes.backends import Backend, ColumnSpec, Paging

INITIAL_STATE: dict[str, object] = {
    "rows": [],
    "meta": {},
    "selected": None,
    "page": 1,
    "cursor": None,
    "confirm": "",
}


def _list_args(paging: Paging) -> dict[str, object]:
    if paging == "page":
        return {"page_number": STATE.page, "page_size": 25}
    if paging == "cursor":
        return {"cursor": STATE.cursor, "limit": 25}
    return {}


def _refresh(list_backend: Backend, paging: Paging) -> CallTool:
    return CallTool(
        list_backend,
        arguments=_list_args(paging),
        on_success=[SetState("rows", RESULT.rows), SetState("meta", RESULT.meta)],
        on_error=ShowToast(str(ERROR), variant="error"),
    )


def confirm_action(
    *,
    label: str,
    title: str,
    description: str,
    backend: Backend,
    resource_id_rx: Rx | str,
    extra_args: Mapping[str, object] | None = None,
) -> None:
    """Emit a Dialog gated action: the backend runs only after the user retypes the id."""
    arguments: dict[str, object] = {
        "resource_id": resource_id_rx,
        "confirm": STATE.confirm,
        **dict(extra_args or {}),
    }
    with Dialog(title=title, description=description, dismissible=True):
        Button(label, variant="destructive")
        Label("Type the resource id to confirm")
        Input(name="confirm", required=True)
        Button(
            "Confirm",
            variant="destructive",
            on_click=CallTool(
                backend,
                arguments=arguments,
                on_success=[
                    SetState("selected", RESULT),
                    ShowToast(f"{label} done", variant="success"),
                ],
                on_error=ShowToast(str(ERROR), variant="error"),
            ),
        )


def _paging_controls(list_backend: Backend, paging: Paging) -> None:
    if paging == "page":
        with Row(gap=2):
            Button(
                "Previous",
                variant="outline",
                disabled=bool(STATE.page <= 1),
                on_click=[SetState("page", STATE.page - 1), _refresh(list_backend, paging)],
            )
            Button(
                "Next",
                variant="outline",
                on_click=[SetState("page", STATE.page + 1), _refresh(list_backend, paging)],
            )
    elif paging == "cursor":
        Button(
            "Load more",
            variant="outline",
            disabled=bool(~STATE.meta.has_more),
            on_click=[SetState("cursor", STATE.meta.cursor), _refresh(list_backend, paging)],
        )


def _detail_card(
    detail_fields: Sequence[tuple[str, str]], actions: Sequence[Callable[[], None]]
) -> None:
    with If(STATE.selected):
        with Card():
            with CardHeader():
                CardTitle("Selected")
            with CardContent():
                with Column(gap=2):
                    for key, label in detail_fields:
                        with Row(gap=2):
                            Muted(label)
                            Text(str(STATE.selected[key]))
                    for action in actions:
                        action()


def list_workspace(
    *,
    title: str,
    list_backend: Backend,
    columns: Sequence[ColumnSpec],
    detail_backend: Backend | None = None,
    detail_fields: Sequence[tuple[str, str]] = (),
    create_form: tuple[type[BaseModel], Backend] | None = None,
    actions: Sequence[Callable[[], None]] = (),
    paging: Paging = "none",
    row_id_key: str = "name",
    notes: Sequence[str] = (),
) -> PrefabApp:
    """Build the shared workspace PrefabApp for one Strands domain."""
    row_click: Action | None = None
    if detail_backend is not None:
        row_click = CallTool(
            detail_backend,
            arguments={"resource_id": EVENT[row_id_key]},
            on_success=SetState("selected", RESULT),
            on_error=ShowToast(str(ERROR), variant="error"),
        )
    with Column(gap=4) as view:
        Heading(title, level=2)
        with If(STATE.rows.length() == 0):
            with Alert():
                AlertTitle("No rows loaded")
        DataTable(
            columns=[
                DataTableColumn(key=c.key, header=c.header, format=c.format) for c in columns
            ],
            rows=STATE.rows,
            search=True,
            paginated=False,
            pageSize=25,
            onRowClick=row_click,
        )
        _paging_controls(list_backend, paging)
        _detail_card(detail_fields, actions)
        if create_form is not None:
            model, form_backend = create_form
            with Tabs():
                with Tab("Execute"):
                    Form.from_model(
                        model,
                        on_submit=CallTool(
                            form_backend,
                            on_success=[
                                SetState("selected", RESULT),
                                ShowToast("Executed", variant="success"),
                                _refresh(list_backend, paging),
                            ],
                            on_error=ShowToast(str(ERROR), variant="error"),
                        ),
                    )
        for note in notes:
            Muted(note)
    return PrefabApp(
        title=title,
        view=view,
        state=dict(INITIAL_STATE),
        on_mount=_refresh(list_backend, paging),
    )
