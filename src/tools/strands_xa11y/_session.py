"""Resolving apps, targets, and keys; asking for consent."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional

from ._errors import ToolError, xa11y
from ._refs import REFS, Ref
from .models import ElementTarget, PointerTarget

FOREGROUND_ALIASES = {"foreground", "front", "frontmost", "active", "current"}

# Aliases models reach for, mapped onto the key names xa11y expects. Printable
# characters pass through untouched.
_KEY_ALIASES = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "option": "Alt",
    "opt": "Alt",
    "meta": "Meta",
    "cmd": "Meta",
    "command": "Meta",
    "super": "Meta",
    "win": "Meta",
    "windows": "Meta",
    "enter": "Enter",
    "return": "Enter",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "del": "Delete",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "arrowup": "ArrowUp",
    "arrowdown": "ArrowDown",
    "arrowleft": "ArrowLeft",
    "arrowright": "ArrowRight",
}


def normalize_key(key: str) -> str:
    """Map a key alias onto xa11y's spelling, leaving anything unrecognised alone."""
    if len(key) == 1:
        return key
    return _KEY_ALIASES.get(key.replace("_", "").replace("-", "").lower(), key)


def normalize_keys(keys: List[str]) -> List[str]:
    return [normalize_key(key) for key in keys]


# ── Applications ─────────────────────────────────────────────────────────────


def app_key(app: Any) -> str:
    """A string that re-resolves this app later. PID is preferred; names are not unique."""
    pid = getattr(app, "pid", None)
    return f"pid:{pid}" if pid else f"name:{app.name}"


def resolve_app(spec: Optional[str]) -> Any:
    """Resolve an app spec: a name (exact, then fuzzy), 'pid:N', or the foreground app."""
    module = xa11y()
    if spec is None or spec.strip().lower() in FOREGROUND_ALIASES:
        return module.App.foreground()

    spec = spec.strip()
    if spec.lower().startswith("pid:"):
        raw = spec.split(":", 1)[1].strip()
        try:
            return module.App.by_pid(int(raw))
        except ValueError as exc:
            raise ToolError(f"'{spec}' is not a valid pid selector; expected 'pid:1234'") from exc
    if spec.lower().startswith("name:"):
        spec = spec.split(":", 1)[1].strip()

    # Exact match without waiting, so the common case stays fast and the fuzzy pass
    # below does not sit behind a five-second poll.
    try:
        return module.App.by_name(spec, timeout=0)
    except module.XA11yError:
        pass

    matched = _fuzzy_apps(module, spec)
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        names = ", ".join(sorted(f'"{app.name}"' for app in matched))
        raise ToolError(f"'{spec}' matches several running applications: {names}. Use one of those names exactly.")

    # Nothing matched now; wait for it in case it is still starting. When this
    # fails, xa11y's own error lists the running applications.
    return module.App.by_name(spec)


def _fuzzy_apps(module: Any, spec: str) -> List[Any]:
    lowered = spec.lower()
    running = list(module.App.list())
    for predicate in (
        lambda name: name == lowered,
        lambda name: name.startswith(lowered),
        lambda name: lowered in name,
    ):
        matched = [app for app in running if predicate((app.name or "").lower())]
        if matched:
            return matched
    return []


def focus_app(app: Any) -> bool:
    """Try to bring an app's window forward. Returns whether it worked."""
    if getattr(app, "is_foreground", False):
        return True
    try:
        for child in app.children():
            child.focus()
            return True
    except Exception:  # noqa: BLE001 - focus is best-effort; the caller proceeds either way
        return False
    return False


# ── Targets ──────────────────────────────────────────────────────────────────


@dataclass
class Resolved:
    """A resolved target: the app, and the best handle available for acting on it."""

    app: Any
    label: str
    locator: Optional[Any] = None
    element: Optional[Any] = None

    @property
    def actor(self) -> Any:
        """The object to call action verbs on.

        A Locator when one is available — it re-resolves and auto-waits — otherwise a
        captured element handle.
        """
        return self.locator if self.locator is not None else self.element

    def as_element(self) -> Any:
        """An Element, for reading properties or aiming synthesised input."""
        if self.element is not None:
            return self.element
        if self.locator is None:
            raise ToolError(f"{self.label} resolved to no element at all — a point has no accessibility node.")
        return self.locator.element()


def resolve_element(target: ElementTarget) -> Resolved:
    """Resolve a selector-or-ref target."""
    if target.ref is not None:
        return resolve_ref(REFS.get(target.ref))
    app = resolve_app(target.app)
    return Resolved(app=app, label=f"selector {target.selector!r}", locator=app.locator(target.selector))


def resolve_pointer(target: PointerTarget) -> Resolved:
    """Resolve a pointer target. A point target resolves to no element at all."""
    if target.point is not None:
        return Resolved(app=None, label=f"point {tuple(target.point)}")
    return resolve_element(ElementTarget(app=target.app, selector=target.selector, ref=target.ref))


def resolve_ref(entry: Ref) -> Resolved:
    """Re-resolve a ref, preferring a selector over the captured handle."""
    app = resolve_app(entry.app_key)
    for selector in entry.selectors():
        try:
            locator = app.locator(selector)
            if locator.count() == 1:
                return Resolved(app=app, label=entry.describe(), locator=locator)
        except Exception:  # noqa: BLE001 - a selector that no longer parses or match falls through
            continue
    if entry.element is not None:
        return Resolved(app=app, label=entry.describe(), element=entry.element)
    raise ToolError(
        f"Ref {entry.ref} ({entry.role}) no longer resolves to exactly one element — the UI has most "
        f"likely changed since it was issued. Take a fresh snapshot and use the new ref."
    )


def pointer_argument(resolved: Resolved, target: PointerTarget) -> Any:
    """The value to hand xa11y's input layer: a point tuple, or an Element."""
    if target.point is not None:
        return tuple(target.point)
    return resolved.as_element()


# ── Consent ──────────────────────────────────────────────────────────────────


def consent_bypassed() -> bool:
    return os.environ.get("BYPASS_TOOL_CONSENT", "").lower() == "true"


def require_consent(summary: str) -> None:
    """Ask before doing something to the user's machine.

    Set ``BYPASS_TOOL_CONSENT=true`` to hand approval to the host agent runtime — which
    is what you want when the runtime has its own approval UX, or when running
    unattended. Without a terminal to ask on, the action is refused rather than assumed.
    """
    if consent_bypassed():
        return
    if not (sys.stdin and sys.stdin.isatty()):
        raise ToolError(
            f"Consent required for: {summary}\n"
            "No interactive terminal is available to ask on. Set BYPASS_TOOL_CONSENT=true to run "
            "unattended, ideally behind your agent runtime's own approval step."
        )
    answer = input(f"Allow this desktop action? {summary} (y/n) ").strip().lower()
    if answer != "y":
        raise ToolError(f"Action declined by the user: {summary}")
