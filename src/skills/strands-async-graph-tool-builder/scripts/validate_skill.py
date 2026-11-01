#!/usr/bin/env python3
"""Deterministically validate this skill's structure and reference anchors."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = SKILL_ROOT / "SKILL.md"
REFERENCES = SKILL_ROOT / "references"
EVALS_FILE = SKILL_ROOT / "evals" / "evals.json"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def slugify(heading: str) -> str:
    value = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"[\s_-]+", "-", value).strip("-")


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        fail("SKILL.md must begin with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        fail("SKILL.md frontmatter is not closed")
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            fail(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def reference_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    occurrences: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        base = slugify(match.group(1))
        count = occurrences.get(base, 0)
        occurrences[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def validate_links(skill_text: str) -> None:
    local_links = re.findall(
        r"\[[^\]]+\]\((references/[^)#]+\.md)(?:#([^)]+))?\)",
        skill_text,
    )
    if not local_links:
        fail("SKILL.md has no local reference links")

    linked_files: set[str] = set()
    for relative, anchor in local_links:
        linked_files.add(relative)
        target = SKILL_ROOT / relative
        if not target.is_file():
            fail(f"missing reference: {relative}")
        if not anchor:
            fail(f"reference link lacks a heading anchor: {relative}")
        if anchor not in reference_anchors(target):
            fail(f"unknown heading anchor: {relative}#{anchor}")

    actual_files = {f"references/{path.name}" for path in REFERENCES.glob("*.md")}
    missing = sorted(actual_files - linked_files)
    if missing:
        fail(f"reference files not anchored from SKILL.md: {', '.join(missing)}")


def validate_evals() -> None:
    try:
        document = json.loads(EVALS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid evals file: {exc}")
    if not isinstance(document, dict) or set(document) != {"skill_name", "evals"}:
        fail("evals.json must have exactly skill_name and evals")
    if document["skill_name"] != SKILL_ROOT.name:
        fail("evals.json skill_name must match the skill directory")
    evals = document["evals"]
    if not isinstance(evals, list) or not 2 <= len(evals) <= 3:
        fail("evals.json must contain two or three evaluations")
    required = {"id", "prompt", "expected_output", "files"}
    identifiers: set[int] = set()
    for index, item in enumerate(evals):
        if not isinstance(item, dict) or set(item) != required:
            fail(f"eval {index} must have exactly {sorted(required)}")
        if not all(
            isinstance(item[key], str) and item[key].strip()
            for key in ("prompt", "expected_output")
        ):
            fail(f"eval {index} has an empty string field")
        if not isinstance(item["files"], list):
            fail(f"eval {index} files must be a list")
        if not isinstance(item["id"], int) or item["id"] <= 0:
            fail(f"eval {index} id must be a positive integer")
        if item["id"] in identifiers:
            fail(f"duplicate eval id: {item['id']}")
        identifiers.add(item["id"])


def main() -> None:
    skill_text = SKILL_FILE.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(skill_text)
    if frontmatter.get("name") != SKILL_ROOT.name:
        fail("frontmatter name must match the skill directory")
    if not frontmatter.get("description"):
        fail("frontmatter description is required")
    if len(frontmatter["description"]) > 1024:
        fail("frontmatter description exceeds 1024 characters")

    required_phrases = (
        "Context7",
        "AgentTool.stream",
        "Graph.stream_async",
        "skill_agent",
        "invocation-state",
        "Playwright",
        "Do not",
    )
    for phrase in required_phrases:
        if phrase not in skill_text:
            fail(f"SKILL.md is missing required guidance: {phrase}")

    numbered_sections = [
        int(value)
        for value in re.findall(r"^##\s+(\d+)\.", skill_text, re.MULTILINE)
    ]
    if numbered_sections != list(range(16)):
        fail("ordered implementation sections must run from 0 through 15")

    validate_links(skill_text)
    validate_evals()
    eval_count = len(
        json.loads(EVALS_FILE.read_text(encoding="utf-8"))["evals"]
    )
    print(
        f"OK: {SKILL_ROOT.name}; "
        f"{len(list(REFERENCES.glob('*.md')))} references; "
        f"{eval_count} evals"
    )


if __name__ == "__main__":
    main()
