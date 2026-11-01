"""Locally lint a workflow YAML before submission."""
from __future__ import annotations

from pathlib import Path

from strands import tool

from ._common import err, ok


def _flatten_tasks(workflow: dict) -> list[dict]:
    """Extract tasks from either `workflow.tasks` or `workflow.groups[].tasks`."""
    tasks: list[dict] = []
    direct = workflow.get("tasks")
    if isinstance(direct, list):
        tasks.extend(t for t in direct if isinstance(t, dict))
    for group in workflow.get("groups", []) or []:
        if isinstance(group, dict):
            for t in group.get("tasks", []) or []:
                if isinstance(t, dict):
                    tasks.append(t)
    return tasks


@tool
def osmo_workflow_validate(workflow_yaml: str) -> dict:
    """Lint a workflow YAML locally (parse + sanity-check shape).

    Catches obvious problems (invalid YAML, missing required keys, undeclared
    task references, missing image) before you spend a quota slot. The OSMO
    server still has the final word at submit time.

    Supports both ``workflow.tasks`` (flat) and ``workflow.groups[].tasks``
    (gang-scheduled) shapes used in the OSMO cookbook.

    Args:
        workflow_yaml: Path to YAML file.
    """
    p = Path(workflow_yaml).expanduser()
    if not p.exists():
        return err(f"file not found: {p}")
    try:
        import yaml  # type: ignore
    except ImportError:
        return err("PyYAML not installed: pip install pyyaml")

    try:
        spec = yaml.safe_load(p.read_text())
    except Exception as e:
        return err(f"YAML parse error: {e}")

    if not isinstance(spec, dict):
        return err("top-level must be a mapping")

    workflow = spec.get("workflow") if isinstance(spec.get("workflow"), dict) else spec
    tasks = _flatten_tasks(workflow if isinstance(workflow, dict) else {})
    if not tasks:
        return err("no tasks found in workflow.tasks or workflow.groups[].tasks")

    issues: list[str] = []
    task_names: set[str] = set()

    # Workflow-level resources can supply defaults if a task lacks resources.
    has_workflow_defaults = (
        isinstance(workflow.get("resources"), dict)
        and isinstance(workflow["resources"].get("default"), dict)
    )

    for i, task in enumerate(tasks):
        name = task.get("name")
        if not name:
            issues.append(f"tasks[{i}]: missing 'name'")
            continue
        if name in task_names:
            issues.append(f"tasks[{i}={name}]: duplicate task name")
        task_names.add(name)
        if not task.get("image"):
            issues.append(f"tasks[{i}={name}]: missing 'image'")
        # Resources may be inherited from workflow.resources.default
        if not task.get("resources") and not task.get("platform") and not has_workflow_defaults:
            issues.append(
                f"tasks[{i}={name}]: needs 'platform', task 'resources', "
                f"or workflow-level 'resources.default'"
            )
        # Command sanity
        if not (task.get("command") or task.get("args") or task.get("workingDir")):
            # Many cookbook examples set command + args; we warn softly only
            # if both are absent
            issues.append(f"tasks[{i}={name}]: no 'command' or 'args' (will use image entrypoint)")

    # Cross-task input refs
    for task in tasks:
        for inp in task.get("inputs", []) or []:
            if isinstance(inp, dict) and inp.get("task") and inp["task"] not in task_names:
                issues.append(
                    f"tasks[{task.get('name')}]: input refers to unknown task '{inp['task']}'"
                )

    summary = {
        "path": str(p),
        "task_count": len(tasks),
        "task_names": sorted(task_names),
        "has_groups": bool(workflow.get("groups")),
        "has_workflow_defaults": has_workflow_defaults,
        "issues": issues,
    }
    # Distinguish blocking errors (missing image / unknown ref) from soft warnings.
    blocking = [i for i in issues if "missing 'image'" in i or "unknown task" in i or "missing 'name'" in i or "duplicate" in i]
    if blocking:
        return err(f"{len(blocking)} blocking issue(s), {len(issues)} total", data=summary)
    if issues:
        # Soft warnings only - still success but flag them.
        return ok(
            text=f"⚠️  {len(issues)} soft warning(s) ({len(tasks)} tasks)",
            data=summary,
        )
    return ok(text=f"✅ {len(tasks)} tasks, no issues", data=summary)
