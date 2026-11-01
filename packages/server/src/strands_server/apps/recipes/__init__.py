"""Shared list/detail/form/confirmed-action recipe for domain FastMCPApp workspaces."""

from strands_server.apps.recipes.backends import (
    Backend,
    ColumnSpec,
    ListSpec,
    Paging,
    register_confirmed_backend,
    register_detail_backend,
    register_form_backend,
    register_list_backend,
)
from strands_server.apps.recipes.views import confirm_action, list_workspace

__all__ = [
    "Backend",
    "ColumnSpec",
    "ListSpec",
    "Paging",
    "confirm_action",
    "list_workspace",
    "register_confirmed_backend",
    "register_detail_backend",
    "register_form_backend",
    "register_list_backend",
]
