#!/usr/bin/env python3
"""Auto-update AI Elements API props snapshot.

Usage:
  python3 scripts/update_api_props.py

Writes: references/api-props.md
"""

import re
import sys
from pathlib import Path

try:
    import requests
except Exception:
    print("Missing dependency: requests. Install with: python3 -m pip install requests", file=sys.stderr)
    raise

BASE_DIR = Path(__file__).resolve().parent.parent
REFS_DIR = BASE_DIR / "references"
DOCS_INDEX = REFS_DIR / "ai-elements-docs.md"
COMPONENT_INDEX = REFS_DIR / "component-index.md"
OUTPUT = REFS_DIR / "api-props.md"

EDIT_RE = re.compile(r"https://github\.com/vercel/ai-elements/edit/main/[^\"\s]+")
URL_RE = re.compile(r"https?://[^\s)]+")


def _load_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return URL_RE.findall(text)


def _component_urls() -> list[str]:
    urls = _load_urls(DOCS_INDEX) + _load_urls(COMPONENT_INDEX)
    components = {u for u in urls if "/elements/components/" in u}
    return sorted(components)


def _edit_to_raw(edit_url: str) -> str:
    rel = edit_url.split("/edit/main/")[-1]
    return "https://raw.githubusercontent.com/vercel/ai-elements/main/" + rel


def _extract_props_section(mdx: str) -> str:
    idx = mdx.find("## Props")
    if idx == -1:
        return ""
    tail = mdx[idx:]
    m = re.search(r"\n##\s+", tail[1:])
    if not m:
        return tail.strip()
    end = m.start() + 1
    return tail[:end].strip()


def _extract_title(mdx: str) -> str:
    m = re.search(r"^title:\s*(.+)$", mdx, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", mdx, re.MULTILINE)
    return m.group(1).strip() if m else "Component"


def main() -> int:
    urls = _component_urls()
    if not urls:
        print("No component URLs found. Check references/ai-elements-docs.md and references/component-index.md", file=sys.stderr)
        return 1

    session = requests.Session()
    entries = []
    failed = []

    for url in urls:
        try:
            html = session.get(url, timeout=20).text
            m = EDIT_RE.search(html)
            if not m:
                failed.append((url, "edit link not found"))
                continue
            raw_url = _edit_to_raw(m.group(0))
            mdx = session.get(raw_url, timeout=20).text
            title = _extract_title(mdx)
            props = _extract_props_section(mdx)
            if not props:
                failed.append((url, "props section not found"))
                continue
            entries.append((title, url, raw_url, props))
        except Exception as exc:
            failed.append((url, str(exc)))

    out = []
    out.append("# AI Elements API Props (Snapshot)\n\n")
    out.append("This file is a snapshot of the `## Props` sections from the AI Elements docs.\n")
    out.append("Update rule: regenerate from docs when new links appear.\n\n")

    for title, url, raw_url, props in entries:
        out.append(f"## {title}\n")
        out.append(f"Doc: {url}\n")
        out.append(f"Source: {raw_url}\n\n")
        out.append("```mdx\n")
        out.append(props)
        out.append("\n```\n\n")

    if failed:
        out.append("## Extraction failures\n")
        for url, reason in failed:
            out.append(f"- {url} ({reason})\n")

    OUTPUT.write_text("".join(out), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"Entries: {len(entries)}")
    print(f"Failed: {len(failed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
