"""Strands tools for driving native desktop applications through the accessibility tree.

    from strands import Agent
    from strands_xa11y import use_desktop

    agent = Agent(tools=[use_desktop])
    agent("Open the Calculator and add 7 and 8")

Built on xa11y (https://xa11y.dev), which speaks AXUIElement on macOS, UI Automation on
Windows, and AT-SPI2 on Linux behind one API.
"""

from .models import DesktopInput, ElementTarget, InspectInput, PointerTarget
from .tools import inspect_desktop, use_desktop

__all__ = [
    "DesktopInput",
    "ElementTarget",
    "InspectInput",
    "PointerTarget",
    "inspect_desktop",
    "use_desktop",
]
