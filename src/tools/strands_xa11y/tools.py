"""The Strands tools: ``use_desktop`` and its read-only counterpart ``inspect_desktop``."""

from __future__ import annotations

import logging
from typing import Any, Dict, Type, TypeVar

from strands import tool

from . import _actions
from .models import DesktopInput, InspectInput

logger = logging.getLogger(__name__)

# Both tools share this guidance, and it is what the model actually reads, so it is
# passed to @tool(description=...) rather than left to the docstrings.
_WORKFLOW = """
Workflow:
  1. 'list_apps' to see what is running, or go straight to 'snapshot' for the foreground app.
  2. 'snapshot' renders the app's accessibility tree, one node per line, each with a ref:
         e14 button "Save" [disabled]
         e15 text_field "File name" value="untitled"
     Refs are the currency of these tools: pass one back as target.ref.
  3. Act on refs: 'click', 'type', 'focus', or 'act' for everything else (toggle, select,
     expand, increment, show_menu, ...).
  4. Re-snapshot after anything that changes the UI. Refs are never reused, so a stale one
     fails loudly instead of hitting the wrong element.

Prefer the accessibility layer. 'key', 'mouse', 'drag', 'scroll', and 'screenshot' synthesise
input or read pixels; reach for them when there is no accessibility equivalent — global
shortcuts, drag-and-drop, wheel scrolling, canvas content — not as a first move. Screenshots
are withheld from the transcript unless send_image=true, which is worth setting only when the
user asked to see the screen or the tree genuinely cannot answer the question.

When a call fails, read the error: it reports what the call was waiting for, what it last
observed, and near-miss elements. That is usually enough to fix the selector or ref on the
next attempt without falling back to pixels.
"""

_USE_DESCRIPTION = (
    "Drive native desktop applications through the operating system's accessibility tree. "
    "Reads and controls real windows on macOS, Windows, and Linux — buttons, text fields, menus, "
    "checkboxes, lists — as structured elements rather than pixels, so targeting is exact and does "
    "not depend on OCR or on guessing coordinates.\n" + _WORKFLOW
)

_INSPECT_DESCRIPTION = (
    "Read the desktop accessibility tree without changing anything. The read-only half of "
    "use_desktop: 'list_apps', 'snapshot', 'find', 'read', 'wait', and 'screenshot'. It cannot "
    "click, type, or launch anything.\n" + _WORKFLOW
)


Envelope = TypeVar("Envelope", DesktopInput, InspectInput)


def _action(payload: Any, model: Type[Envelope]) -> Any:
    """Unwrap the action, validating first when called directly with a plain dict.

    Strands validates the payload when the agent invokes the tool, but these functions
    are still ordinary callables — scripts and tests reach them with a dict, and they
    should get the same validation the agent gets.
    """
    if isinstance(payload, model):
        return payload.action
    return model.model_validate(payload).action


@tool(description=_USE_DESCRIPTION)
def use_desktop(desktop_input: DesktopInput) -> Dict[str, Any]:
    """Drive native desktop applications through the accessibility tree.

    Args:
        desktop_input: The action to perform. Each action type declares its own fields.

    Returns:
        Dict with 'status' and 'content'. Snapshots and reads return text; screenshots may
        additionally return an image when send_image is set.
    """
    action = _action(desktop_input, DesktopInput)
    logger.debug("use_desktop: %s", action.type)
    return _actions.run(action)


@tool(description=_INSPECT_DESCRIPTION)
def inspect_desktop(inspect_input: InspectInput) -> Dict[str, Any]:
    """Read the desktop accessibility tree without changing anything.

    Args:
        inspect_input: The read-only action to perform.

    Returns:
        Dict with 'status' and 'content'.
    """
    action = _action(inspect_input, InspectInput)
    logger.debug("inspect_desktop: %s", action.type)
    return _actions.run(action)
