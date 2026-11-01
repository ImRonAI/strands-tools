"""Cursor control tool for moving mouse, clicking, typing, and more."""

from typing import Dict, Any, Optional, Tuple
from strands import tool

try:
    import pyautogui

    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
except ImportError:
    pyautogui = None


@tool
def cursor(
    action: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.0,
    duration: float = 0.5,
    text: Optional[str] = None,
    key: Optional[str] = None,
    keys: Optional[list] = None,
    amount: int = 1,
    to_x: Optional[int] = None,
    to_y: Optional[int] = None,
) -> Dict[str, Any]:
    """Control mouse cursor and keyboard.

    Actions:
        - position: Get current cursor position
        - screen_size: Get screen dimensions
        - move: Move cursor to absolute position
        - move_relative: Move cursor relative to current position
        - smooth_move: Animated move to position
        - click: Click mouse button
        - double_click: Double click
        - drag: Drag from current position to target
        - scroll: Scroll up/down
        - type_text: Type text string
        - press_key: Press single key
        - hotkey: Press key combination

    Args:
        action: Action to perform
        x: X coordinate (absolute)
        y: Y coordinate (absolute)
        button: Mouse button (left/right/middle)
        clicks: Number of clicks
        interval: Interval between clicks
        duration: Duration for smooth movements
        text: Text to type
        key: Key to press
        keys: List of keys for hotkey
        amount: Scroll amount
        to_x: Target X for drag
        to_y: Target Y for drag

    Returns:
        Dict with status and content
    """
    if pyautogui is None:
        return {
            "status": "error",
            "content": [
                {
                    "text": "❌ pyautogui not installed. Run: pip install pyautogui"
                }
            ],
        }

    try:
        result = ""

        if action == "position":
            pos = pyautogui.position()
            result = f"📍 **Cursor Position:** x={pos.x}, y={pos.y}"

        elif action == "screen_size":
            size = pyautogui.size()
            result = f"🖥️ **Screen Size:** {size.width}x{size.height}"

        elif action == "move":
            if x is None or y is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ x and y required for move"}],
                }
            pyautogui.moveTo(x, y)
            result = f"🖱️ **Moved to:** ({x}, {y})"

        elif action == "move_relative":
            if x is None or y is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ x and y required for move_relative"}],
                }
            pyautogui.moveRel(x, y)
            new_pos = pyautogui.position()
            result = f"🖱️ **Moved by:** ({x}, {y}) → now at ({new_pos.x}, {new_pos.y})"

        elif action == "smooth_move":
            if x is None or y is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ x and y required for smooth_move"}],
                }
            pyautogui.moveTo(x, y, duration=duration)
            result = f"🖱️ **Smoothly moved to:** ({x}, {y}) in {duration}s"

        elif action == "click":
            if x is not None and y is not None:
                pyautogui.click(x, y, clicks=clicks, interval=interval, button=button)
                result = f"🖱️ **Clicked {button} {clicks}x at:** ({x}, {y})"
            else:
                pyautogui.click(clicks=clicks, interval=interval, button=button)
                pos = pyautogui.position()
                result = f"🖱️ **Clicked {button} {clicks}x at:** ({pos.x}, {pos.y})"

        elif action == "double_click":
            if x is not None and y is not None:
                pyautogui.doubleClick(x, y, button=button)
                result = f"🖱️ **Double-clicked {button} at:** ({x}, {y})"
            else:
                pyautogui.doubleClick(button=button)
                pos = pyautogui.position()
                result = f"🖱️ **Double-clicked {button} at:** ({pos.x}, {pos.y})"

        elif action == "drag":
            if to_x is None or to_y is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ to_x and to_y required for drag"}],
                }
            start = pyautogui.position()
            pyautogui.dragTo(to_x, to_y, duration=duration, button=button)
            result = f"🖱️ **Dragged {button} from:** ({start.x}, {start.y}) → ({to_x}, {to_y})"

        elif action == "scroll":
            pyautogui.scroll(amount)
            direction = "⬆️ up" if amount > 0 else "⬇️ down"
            result = f"🖱️ **Scrolled {direction}:** {abs(amount)} units"

        elif action == "type_text":
            if text is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ text required for type_text"}],
                }
            pyautogui.write(text, interval=interval)
            result = f"⌨️ **Typed:** {text[:50]}{'...' if len(text) > 50 else ''}"

        elif action == "press_key":
            if key is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ key required for press_key"}],
                }
            pyautogui.press(key)
            result = f"⌨️ **Pressed key:** {key}"

        elif action == "hotkey":
            if keys is None or len(keys) == 0:
                return {
                    "status": "error",
                    "content": [{"text": "❌ keys list required for hotkey"}],
                }
            pyautogui.hotkey(*keys)
            result = f"⌨️ **Hotkey pressed:** {'+'.join(keys)}"

        else:
            return {
                "status": "error",
                "content": [{"text": f"❌ Unknown action: {action}"}],
            }

        return {"status": "success", "content": [{"text": result}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
