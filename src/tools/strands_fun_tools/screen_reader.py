"""Screen reader tool with background OCR monitoring and UI element detection."""

import os
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from strands import tool

try:
    from PIL import ImageGrab, Image
    import pytesseract
except ImportError:
    ImageGrab = None
    pytesseract = None


class ScreenMonitor:
    """Background screen monitoring with OCR."""

    def __init__(self):
        self.thread = None
        self.stop_flag = threading.Event()
        self.running = False
        self.save_dir = Path(".screen_monitor")
        self.save_dir.mkdir(exist_ok=True)
        self.log_file = self.save_dir / "elements.jsonl"

        self.interval = 2.0  # seconds between captures
        self.total_captures = 0
        self.total_elements = 0
        self.last_screen_hash = None

    def start(self, interval: float = 2.0):
        """Start background monitoring."""
        if self.running:
            return "⚠️ Already running"

        self.interval = interval
        self.stop_flag.clear()
        self.running = True

        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

        return f"✅ Screen monitoring started (interval: {interval}s)"

    def stop(self):
        """Stop background monitoring."""
        if not self.running:
            return "⚠️ Not running"

        self.stop_flag.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.running = False

        return "✅ Screen monitoring stopped"

    def _monitor_loop(self):
        """Main monitoring loop."""
        while not self.stop_flag.is_set():
            try:
                # Capture and analyze screen
                elements = self._capture_and_analyze()

                if elements:
                    # Calculate screen hash to detect changes
                    screen_hash = hash(
                        json.dumps(sorted([e["text"] for e in elements]))
                    )

                    # Only log if screen changed
                    if screen_hash != self.last_screen_hash:
                        self._log_elements(elements)
                        self.last_screen_hash = screen_hash
                        self.total_captures += 1
                        self.total_elements += len(elements)

            except Exception as e:
                print(f"⚠️ Screen monitor error: {e}")

            # Wait for interval
            self.stop_flag.wait(self.interval)

    def _capture_and_analyze(self) -> List[Dict[str, Any]]:
        """Capture screen and extract text elements."""
        if ImageGrab is None or pytesseract is None:
            return []

        # Capture screen
        screenshot = ImageGrab.grab()

        # OCR with bounding boxes
        ocr_data = pytesseract.image_to_data(
            screenshot, output_type=pytesseract.Output.DICT
        )

        elements = []
        n_boxes = len(ocr_data["text"])

        for i in range(n_boxes):
            text = ocr_data["text"][i].strip()
            conf = int(ocr_data["conf"][i])

            # Filter: only text with good confidence
            if text and conf > 30:
                x = ocr_data["left"][i]
                y = ocr_data["top"][i]
                w = ocr_data["width"][i]
                h = ocr_data["height"][i]

                elements.append(
                    {
                        "text": text,
                        "x": x,
                        "y": y,
                        "width": w,
                        "height": h,
                        "center": (x + w // 2, y + h // 2),
                        "confidence": conf,
                    }
                )

        return elements

    def _log_elements(self, elements: List[Dict[str, Any]]):
        """Log elements to file."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "element_count": len(elements),
            "elements": elements,
        }

        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_status(self) -> Dict[str, Any]:
        """Get monitoring status."""
        return {
            "running": self.running,
            "interval": self.interval,
            "total_captures": self.total_captures,
            "total_elements": self.total_elements,
            "log_file": str(self.log_file),
        }

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent screen captures."""
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file, "r") as f:
            for line in f:
                entries.append(json.loads(line))

        return entries[-limit:]

    def clear_history(self):
        """Clear log file."""
        if self.log_file.exists():
            self.log_file.unlink()
        self.total_captures = 0
        self.total_elements = 0
        return "✅ History cleared"


# Global monitor instance
_monitor = ScreenMonitor()


@tool
def screen_reader(
    action: str,
    interval: float = 2.0,
    limit: int = 10,
    search_text: Optional[str] = None
) -> Dict[str, Any]:
    """Background screen monitoring with OCR and UI element detection.

    Args:
        action: Action (start, stop, status, get_history, find_element, list_elements, capture_once, clear_history)
        interval: Seconds between captures (default: 2.0)
        limit: Max number of history entries to return (default: 10)
        search_text: Text to search for in elements

    Returns:
        Dict with status and content
    """
    if ImageGrab is None or pytesseract is None:
        return {
            "status": "error",
            "content": [
                {
                    "text": "❌ Dependencies missing. Run: pip install pillow pytesseract && brew install tesseract"
                }
            ],
        }

    try:
        if action == "start":
            result = _monitor.start(interval)
            return {"status": "success", "content": [{"text": result}]}

        elif action == "stop":
            result = _monitor.stop()
            return {"status": "success", "content": [{"text": result}]}

        elif action == "status":
            status = _monitor.get_status()
            text = f"""📊 **Screen Monitor Status:**
- **Running:** {'✅ Yes' if status['running'] else '❌ No'}
- **Interval:** {status['interval']}s
- **Total Captures:** {status['total_captures']}
- **Total Elements:** {status['total_elements']}
- **Log File:** {status['log_file']}"""
            return {"status": "success", "content": [{"text": text}]}

        elif action == "get_history":
            history = _monitor.get_history(limit)
            if not history:
                return {"status": "success", "content": [{"text": "📋 No history yet"}]}

            text = f"📋 **Recent Screen Captures ({len(history)} entries):**\n\n"
            for entry in history[-10:]:  # Show last 10
                ts = entry["timestamp"]
                count = entry["element_count"]
                text += f"- **{ts}** - {count} elements\n"

            return {"status": "success", "content": [{"text": text}]}

        elif action == "find_element":
            if not search_text:
                return {
                    "status": "error",
                    "content": [{"text": "❌ search_text required"}],
                }

            history = _monitor.get_history(limit=1)
            if not history:
                return {
                    "status": "error",
                    "content": [
                        {"text": "⚠️ No screen data yet. Start monitoring first."}
                    ],
                }

            elements = history[-1]["elements"]
            matches = [e for e in elements if search_text.lower() in e["text"].lower()]

            if not matches:
                return {
                    "status": "success",
                    "content": [
                        {"text": f"❌ Text '{search_text}' not found on screen"}
                    ],
                }

            text = f"🔍 **Found {len(matches)} matches for '{search_text}':**\n\n"
            for match in matches[:5]:
                text += f"- **'{match['text']}'** @ ({match['center'][0]}, {match['center'][1]}) - conf: {match['confidence']}%\n"

            return {"status": "success", "content": [{"text": text}]}

        elif action == "list_elements":
            history = _monitor.get_history(limit=1)
            if not history:
                return {
                    "status": "error",
                    "content": [
                        {"text": "⚠️ No screen data yet. Start monitoring first."}
                    ],
                }

            elements = history[-1]["elements"]

            # Get unique texts
            unique_texts = {}
            for e in elements:
                text = e["text"]
                if text not in unique_texts:
                    unique_texts[text] = {"count": 0, "positions": []}
                unique_texts[text]["count"] += 1
                unique_texts[text]["positions"].append(e["center"])

            text = f"📋 **Current Screen Elements ({len(unique_texts)} unique):**\n\n"
            for txt, data in list(unique_texts.items())[:20]:  # Show top 20
                text += f"- **'{txt}'** ({data['count']}x) @ {data['positions'][0]}\n"

            return {"status": "success", "content": [{"text": text}]}

        elif action == "capture_once":
            elements = _monitor._capture_and_analyze()

            if not elements:
                return {
                    "status": "success",
                    "content": [{"text": "⚠️ No text detected on screen"}],
                }

            text = f"📸 **Screen Capture - {len(elements)} elements found:**\n\n"
            for elem in elements[:15]:  # Show top 15
                text += f"- **'{elem['text']}'** @ ({elem['center'][0]}, {elem['center'][1]}) - {elem['confidence']}%\n"

            return {"status": "success", "content": [{"text": text}]}

        elif action == "clear_history":
            result = _monitor.clear_history()
            return {"status": "success", "content": [{"text": result}]}

        else:
            return {
                "status": "error",
                "content": [{"text": f"❌ Unknown action: {action}"}],
            }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
