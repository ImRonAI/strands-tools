"""Clipboard monitoring and control tool with background listening.

Background monitoring for clipboard changes with automatic logging,
plus direct clipboard read/write/clear operations.

Actions:
    Monitoring:
        - start: Start background clipboard monitoring
        - stop: Stop monitoring
        - status: Check if monitoring is running
        - get_history: Get recent clipboard entries
        - list_content: Show unique clipboard content
        - clear_history: Clear clipboard history log

    Control:
        - read: Get current clipboard content
        - write: Set clipboard content
        - clear: Clear clipboard
        - copy: Copy text to clipboard (alias for write)
        - paste: Get clipboard content (alias for read)
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib

try:
    import pyperclip
except ImportError:
    pyperclip = None

from strands import tool

# Global state
_monitor_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None
_save_dir = Path(".clipboard_monitor")
_log_file = _save_dir / "clipboard.jsonl"
_last_content = ""
_last_hash = ""


def _get_content_hash(content: str) -> str:
    """Generate hash for content deduplication."""
    return hashlib.md5(content.encode()).hexdigest()[:16]


def _log_entry(entry: dict):
    """Log clipboard entry to jsonl file."""
    _save_dir.mkdir(exist_ok=True)
    with open(_log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_log() -> list:
    """Read all log entries."""
    if not _log_file.exists():
        return []

    entries = []
    with open(_log_file, "r") as f:
        for line in f:
            try:
                entries.append(json.loads(line.strip()))
            except:
                continue
    return entries


def _monitor_loop(interval: float):
    """Background monitoring loop."""
    global _last_content, _last_hash

    while not _stop_event.is_set():
        try:
            current = pyperclip.paste()
            current_hash = _get_content_hash(current)

            # Only log if content changed
            if current_hash != _last_hash and current:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "content": current,
                    "hash": current_hash,
                    "length": len(current),
                    "type": _classify_content(current),
                }
                _log_entry(entry)
                _last_content = current
                _last_hash = current_hash

        except Exception as e:
            pass

        time.sleep(interval)


def _classify_content(content: str) -> str:
    """Classify clipboard content type."""
    if not content:
        return "empty"

    # Check for URLs
    if content.startswith(("http://", "https://", "www.")):
        return "url"

    # Check for file paths
    if "/" in content or "\\" in content:
        if Path(content).exists():
            return "file_path"

    # Check for code patterns
    code_indicators = [
        "def ",
        "class ",
        "import ",
        "function ",
        "const ",
        "var ",
        "{",
        "}",
        ";",
    ]
    if any(ind in content for ind in code_indicators):
        return "code"

    # Check for email
    if "@" in content and "." in content:
        return "email"

    # Check for numbers
    if content.replace(".", "").replace("-", "").isdigit():
        return "number"

    # Default
    if len(content.split()) > 10:
        return "text"
    else:
        return "snippet"


@tool
def clipboard(
    action: str, content: str = None, interval: float = 1.0, limit: int = 50
) -> Dict[str, Any]:
    """Clipboard monitoring and control tool.

    Background clipboard monitoring with auto-logging plus direct clipboard operations.

    Args:
        action: Action to perform:
            Monitoring: start, stop, status, get_history, list_content, clear_history
            Control: read, write, clear, copy, paste
        content: Text content for write/copy actions
        interval: Monitoring interval in seconds (default: 1.0)
        limit: Max number of history entries to return (default: 50)

    Returns:
        Dict with status and content
    """
    global _monitor_thread, _stop_event, _last_content, _last_hash

    if pyperclip is None:
        return {
            "status": "error",
            "content": [
                {
                    "text": "❌ pyperclip not installed. Run: pipx inject research-agent pyperclip"
                }
            ],
        }

    # Monitoring actions
    if action == "start":
        if _monitor_thread and _monitor_thread.is_alive():
            return {
                "status": "error",
                "content": [{"text": "⚠️ Clipboard monitoring already running"}],
            }

        _stop_event = threading.Event()
        _monitor_thread = threading.Thread(
            target=_monitor_loop, args=(interval,), daemon=True
        )
        _monitor_thread.start()

        # Initialize with current clipboard
        try:
            _last_content = pyperclip.paste()
            _last_hash = _get_content_hash(_last_content)
        except:
            pass

        return {
            "status": "success",
            "content": [
                {
                    "text": f"✅ **Clipboard Monitoring Started**\n"
                    f"⏱️  Interval: {interval}s\n"
                    f"💾 Save dir: `{_save_dir}`"
                }
            ],
        }

    elif action == "stop":
        if not _monitor_thread or not _monitor_thread.is_alive():
            return {
                "status": "error",
                "content": [{"text": "❌ Clipboard monitoring not running"}],
            }

        _stop_event.set()
        _monitor_thread.join(timeout=2)

        return {
            "status": "success",
            "content": [{"text": "✅ **Clipboard Monitoring Stopped**"}],
        }

    elif action == "status":
        running = _monitor_thread and _monitor_thread.is_alive()
        entries = _read_log()
        unique_content = len(set(e.get("hash") for e in entries))

        status_icon = "🟢" if running else "🔴"
        status_text = "✅ Yes" if running else "❌ No"

        return {
            "status": "success",
            "content": [
                {
                    "text": f"{status_icon} **Clipboard Monitor Status**\n"
                    f"Running: {status_text}\n"
                    f"📊 Total entries: {len(entries)}\n"
                    f"🔍 Unique content: {unique_content}\n"
                    f"💾 Save directory: `{_save_dir}`"
                }
            ],
        }

    elif action == "get_history":
        entries = _read_log()

        if not entries:
            return {
                "status": "success",
                "content": [{"text": "📭 No clipboard history yet"}],
            }

        # Get recent entries
        recent = entries[-limit:]

        lines = [f"📋 **Recent {len(recent)} Clipboard Entries:**\n"]
        for entry in reversed(recent):
            ts = entry.get("timestamp", "").split("T")[1].split(".")[0]
            content_preview = entry.get("content", "")[:50]
            if len(entry.get("content", "")) > 50:
                content_preview += "..."
            content_type = entry.get("type", "text")

            lines.append(f"🕐 **{ts}** [{content_type}]: {content_preview}")

        lines.append(f"\n📊 Total entries: {len(entries)}")
        lines.append(f"📁 Full log: `{_log_file}`")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    elif action == "list_content":
        entries = _read_log()

        if not entries:
            return {
                "status": "success",
                "content": [{"text": "📭 No clipboard content logged yet"}],
            }

        # Group by content type
        type_counts = {}
        for entry in entries:
            content_type = entry.get("type", "text")
            type_counts[content_type] = type_counts.get(content_type, 0) + 1

        lines = [
            f"📊 **Clipboard Content Types ({len(set(e.get('hash') for e in entries))} unique):**\n"
        ]
        for content_type, count in sorted(
            type_counts.items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"• **{content_type}**: {count} times")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    elif action == "clear_history":
        if _log_file.exists():
            _log_file.unlink()

        return {
            "status": "success",
            "content": [{"text": "✅ **Clipboard history cleared**"}],
        }

    # Control actions
    elif action in ["read", "paste"]:
        try:
            current = pyperclip.paste()
            content_type = _classify_content(current)

            return {
                "status": "success",
                "content": [
                    {"text": f"📋 **Clipboard Content** [{content_type}]:\n\n{current}"}
                ],
            }
        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Failed to read clipboard: {str(e)}"}],
            }

    elif action in ["write", "copy"]:
        if content is None:
            return {
                "status": "error",
                "content": [
                    {"text": "❌ content parameter required for write/copy action"}
                ],
            }

        try:
            pyperclip.copy(content)
            content_type = _classify_content(content)
            preview = content[:50] + ("..." if len(content) > 50 else "")

            return {
                "status": "success",
                "content": [
                    {"text": f"✅ **Copied to clipboard** [{content_type}]:\n{preview}"}
                ],
            }
        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Failed to write clipboard: {str(e)}"}],
            }

    elif action == "clear":
        try:
            pyperclip.copy("")
            return {
                "status": "success",
                "content": [{"text": "✅ **Clipboard cleared**"}],
            }
        except Exception as e:
            return {
                "status": "error",
                "content": [{"text": f"❌ Failed to clear clipboard: {str(e)}"}],
            }

    else:
        return {
            "status": "error",
            "content": [{"text": f"❌ Unknown action: {action}"}],
        }
