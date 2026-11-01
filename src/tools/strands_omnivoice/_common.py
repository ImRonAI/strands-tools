"""Shared helpers for Strands tool results.

Tool return format (@tool-compatible):
    {
        "status": "success" | "error",
        "content": [{"text": "..."}, {"json": {...}}],
    }
"""
from __future__ import annotations

from pathlib import Path


def ok(text: str = "", data: dict | None = None) -> dict:
    """Build a success ToolResult."""
    content: list[dict] = []
    if text:
        content.append({"text": text})
    if data is not None:
        content.append({"json": data})
    if not content:
        content.append({"text": "ok"})
    return {"status": "success", "content": content}


def err(msg: str, data: dict | None = None) -> dict:
    """Build an error ToolResult."""
    content: list[dict] = [{"text": f"❌ {msg}"}]
    if data is not None:
        content.append({"json": data})
    return {"status": "error", "content": content}


def resolve_path(p: str) -> Path:
    """Expand `~` and resolve to absolute path."""
    return Path(p).expanduser().resolve()


def ensure_parent(p: Path) -> Path:
    """Make parent dir for an output path; return path."""
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
