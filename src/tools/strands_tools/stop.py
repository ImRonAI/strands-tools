"""
Event loop control tool for Strands Agent.

This module provides functionality to gracefully terminate the current event loop cycle
by setting a stop flag in the request state. It's particularly useful for:

1. Ending conversations when a task is complete
2. Preventing further processing when an error condition is encountered
3. Creating logical exit points in complex workflows
4. Implementing cancel/abort functionality in user interfaces

Usage with Strands Agent:
```python
from strands import Agent
from strands_tools import stop

agent = Agent(tools=[stop])

# Basic usage
agent.tool.stop(reason="Task completed successfully")

# In conditional workflows
if condition_met:
    agent.tool.stop(reason="Condition satisfied, no further processing needed")
```

The stop tool sets the 'stop_event_loop' flag in the request state,
which signals the Strands runtime to terminate the current cycle cleanly.
"""

import logging
from typing import Annotated, Any

from strands import ToolContext, tool

# Initialize logging and set paths
logger = logging.getLogger(__name__)


@tool(context=True)
def stop(
    reason: Annotated[
        str,
        "Optional reason for stopping the event loop cycle",
    ] = "No reason provided",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Stops the current event loop cycle by setting the stop_event_loop flag.

    Args:
        reason: Optional string explaining why the event loop is being stopped.
        tool_context: Framework-provided tool execution context.

    Returns:
        Dict containing status and response content.
    """
    invocation_state = (
        tool_context.invocation_state
        if tool_context is not None and isinstance(tool_context.invocation_state, dict)
        else {}
    )
    request_state = invocation_state.get("request_state", {})
    if isinstance(request_state, dict):
        request_state["stop_event_loop"] = True

    logger.debug(f"Reason: {reason}")

    return {
        "status": "success",
        "content": [{"text": f"Event loop cycle stop requested. Reason: {reason}"}],
    }
