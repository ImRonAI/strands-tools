"""Render a Jinja-templated workflow YAML locally."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, ok


@tool
def osmo_workflow_render(workflow_yaml: str, set_vars: dict, output: str = "") -> dict:
    """Render a Jinja-templated workflow YAML with the given variables.

    Mirrors what ``osmo workflow submit --set k=v`` does server-side, but
    locally - useful for previewing + saving the resolved spec.

    Args:
        workflow_yaml: Path to source YAML (may contain ``{{var}}``).
        set_vars: Variable bindings, e.g. ``{"num_gpu": 4}``.
        output: If set, writes rendered YAML there.
    """
    p = Path(workflow_yaml).expanduser()
    if not p.exists():
        return err(f"file not found: {p}")
    try:
        from jinja2 import BaseLoader, Environment, StrictUndefined  # type: ignore
    except ImportError:
        return err("Jinja2 not installed: pip install jinja2")

    raw = p.read_text()
    env = Environment(loader=BaseLoader(), undefined=StrictUndefined)
    try:
        rendered = env.from_string(raw).render(**(set_vars or {}))
    except Exception as e:
        return err(f"render error: {type(e).__name__}: {e}")

    data = {"path": str(p), "vars": set_vars or {}, "size": len(rendered)}
    if output:
        out_p = Path(output).expanduser()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(rendered)
        data["output"] = str(out_p)

    return ok(text=rendered, data=data)
