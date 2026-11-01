"""Refs: short handles the model can point at, backed by something re-resolvable.

A ref is issued by ``snapshot`` or ``find`` and spent by a later action. Between the
two the UI may have re-rendered, so a ref never resolves through a stored pointer if
it can help it. In order of preference it resolves through:

1. ``[stable_id='...']`` — the platform's own identity for the node;
2. a structural selector path (``window[name='X'] > group:nth(2) > button[name='Save']``);
3. the live element handle captured at snapshot time.

The first two produce a Locator, which re-queries and auto-waits on every action;
only the third can go stale, and it is the last resort.

Ref ids are never reused. A stale ref therefore fails loudly instead of quietly
addressing whatever element inherited its slot.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, List, Optional

from ._errors import ToolError


def quote(value: str) -> Optional[str]:
    """Quote an attribute value for a selector, or return None if it cannot be quoted.

    xa11y accepts single or double quotes and defines no escape sequence, so a value
    containing both kinds of quote has no representation. Callers fall back to a
    coarser selector when this returns None.
    """
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return None


def segment(role: str, name: Optional[str], index: int, total: int) -> str:
    """Build one step of a structural selector path.

    ``index`` is 1-based among siblings sharing the same role and name, and ``total``
    is how many such siblings there are; the positional filter is omitted when the
    step is already unique.
    """
    step = role
    if name:
        quoted = quote(name)
        if quoted is not None:
            step = f"{role}[name={quoted}]"
    if total > 1:
        step = f"{step}:nth({index})"
    return step


@dataclass
class Ref:
    """One issued ref."""

    ref: str
    app_key: str
    role: str
    name: Optional[str] = None
    value: Optional[str] = None
    stable_id: Optional[str] = None
    path: Optional[str] = None
    element: Optional[Any] = None

    def selectors(self) -> List[str]:
        """Selectors to try, best first."""
        candidates = []
        if self.stable_id:
            quoted = quote(self.stable_id)
            if quoted is not None:
                candidates.append(f"[stable_id={quoted}]")
        if self.path:
            candidates.append(self.path)
        return candidates

    def describe(self) -> str:
        label = f'{self.role} "{self.name}"' if self.name else self.role
        return f"{self.ref} ({label})"


class RefStore:
    """Process-wide ref table with a bounded history."""

    def __init__(self, capacity: int = 2000) -> None:
        self._entries: "OrderedDict[str, Ref]" = OrderedDict()
        self._counter = 0
        self._capacity = capacity

    def issue(self, app_key: str, role: str, **fields: Any) -> Ref:
        self._counter += 1
        ref = Ref(ref=f"e{self._counter}", app_key=app_key, role=role, **fields)
        self._entries[ref.ref] = ref
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)
        return ref

    def get(self, ref: str) -> Ref:
        entry = self._entries.get(ref)
        if entry is None:
            raise ToolError(
                f"Unknown ref '{ref}'. Refs come from 'snapshot' or 'find' and are not reused; "
                f"this one was never issued or has aged out. Take a fresh snapshot."
            )
        return entry

    def __len__(self) -> int:
        return len(self._entries)


REFS = RefStore()
