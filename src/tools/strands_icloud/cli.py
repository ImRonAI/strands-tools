#!/usr/bin/env python3
"""🍎 strands-icloud CLI — the whole Apple ecosystem from your terminal.

Usage:
    strands-icloud <action> [options]
    uvx strands-icloud <action> [options]

Examples:
    strands-icloud messages.search --query flight
    strands-icloud messages.send --to "+15517274110" --text "hey"
    strands-icloud mail.unread --limit 10
    strands-icloud imap.search --query invoice --limit 5
    strands-icloud calendar.events --days 14
    strands-icloud caldav.create --title "Dentist" --start "2026-07-25 14:30"
    strands-icloud contacts.search --query mom
    strands-icloud photos.search --label dog --limit 3 --save ./out
    strands-icloud notes.read --query "meeting"
    strands-icloud reminders.list
    strands-icloud findmy.locate --device iPhone
    strands-icloud actions                # list every action
    strands-icloud                        # no args → MCP stdio server
    strands-icloud mcp [--http --port N]  # explicit MCP server
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _print_result(result: dict, save_dir: str | None = None, as_json: bool = False) -> int:
    """Render a tool result dict to the terminal. Returns exit code."""
    status = result.get("status", "error")
    content = result.get("content", [])

    if as_json:
        # strip raw bytes from json output, note saved paths instead
        out = {"status": status, "content": []}
        img_i = 0
        for block in content:
            if "image" in block:
                img_i += 1
                out["content"].append({"image": f"<{block['image']['format']} bytes omitted>"})
            else:
                out["content"].append(block)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0 if status == "success" else 1

    img_i = 0
    for block in content:
        if "text" in block:
            print(block["text"])
        elif "image" in block:
            img_i += 1
            fmt = block["image"]["format"]
            data = block["image"]["source"]["bytes"]
            if save_dir:
                Path(save_dir).mkdir(parents=True, exist_ok=True)
                p = Path(save_dir) / f"photo_{img_i}.{fmt}"
                p.write_bytes(data)
                print(f"  💾 saved {p}")
            else:
                print(f"  🖼 [{fmt} image, {len(data)//1024} KB — use --save DIR to write]")
    return 0 if status == "success" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="strands-icloud",
        description="🍎 Apple ecosystem CLI — Mail, Calendar, Messages, Contacts, Photos, Notes, Reminders, Find My",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples:")[1] if __doc__ else "",
    )
    parser.add_argument("action", nargs="?", default=None,
                        help="Action (e.g. messages.search) | 'actions' to list | 'mcp' to serve | omit → MCP stdio server")
    parser.add_argument("--query", "-q", default=None)
    parser.add_argument("--to", default=None)
    parser.add_argument("--text", default=None)
    parser.add_argument("--subject", default=None)
    parser.add_argument("--body", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--chat", "--folder", dest="chat", default=None,
                        help="Chat filter (messages) or folder (imap)")
    parser.add_argument("--person", default=None)
    parser.add_argument("--label", default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--calendar", dest="calendar_name", default=None)
    parser.add_argument("--start", default=None, help="YYYY-MM-DD HH:MM")
    parser.add_argument("--end", default=None)
    parser.add_argument("--due", default=None)
    parser.add_argument("--from-date", dest="from_date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--to-date", dest="to_date", default=None)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--no-images", action="store_true", help="Photos: metadata only")
    parser.add_argument("--save", default=None, metavar="DIR", help="Save photo images to directory")
    parser.add_argument("--json", action="store_true", help="JSON output")
    # mcp passthrough flags
    parser.add_argument("--http", action="store_true", help="(mcp) HTTP transport")
    parser.add_argument("--port", type=int, default=8010, help="(mcp) HTTP port")
    parser.add_argument("--stateless", action="store_true", help="(mcp) stateless HTTP")

    args = parser.parse_args()

    # No action → MCP stdio server (so `uvx strands-icloud` just works in MCP clients)
    if args.action is None:
        args.action = "mcp"

    # subcommand: mcp server
    if args.action == "mcp":
        from strands_icloud.mcp import main as mcp_main
        sys.argv = ["strands-icloud-mcp"]
        if args.http:
            sys.argv += ["--http", "--port", str(args.port)]
        if args.stateless:
            sys.argv.append("--stateless")
        mcp_main()
        return

    # subcommand: list actions
    if args.action in ("actions", "list-actions", "help-actions"):
        from strands_icloud.use_apple import use_apple
        doc = use_apple.__doc__ or getattr(getattr(use_apple, "_tool_func", None), "__doc__", "") or ""
        # print the Actions section of the docstring
        print("🍎 strands-icloud actions:\n")
        in_actions = False
        for line in doc.splitlines():
            if "Actions:" in line:
                in_actions = True
                continue
            if in_actions:
                if line.strip().startswith("Requires:"):
                    break
                print(line)
        return

    # regular action dispatch
    from strands_icloud.use_apple import use_apple
    fn = getattr(use_apple, "_tool_func", None) or getattr(use_apple, "original_function", None) or use_apple

    result = fn(
        action=args.action,
        query=args.query,
        to=args.to,
        text=args.text,
        subject=args.subject,
        body=args.body,
        title=args.title,
        chat=args.chat,
        person=args.person,
        label=args.label,
        device=args.device,
        calendar_name=args.calendar_name,
        start=args.start,
        end=args.end,
        due=args.due,
        from_date=args.from_date,
        to_date=args.to_date,
        days=args.days,
        limit=args.limit,
        with_images=not args.no_images,
    )
    sys.exit(_print_result(result, save_dir=args.save, as_json=args.json))


if __name__ == "__main__":
    main()
