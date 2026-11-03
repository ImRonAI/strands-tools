"""
User handoff tool for Strands Agent.

This module provides functionality to hand off control from the agent to the user,
allowing for human intervention in automated workflows. It's particularly useful for:

1. Getting user confirmation before proceeding with critical actions
2. Requesting additional information that the agent cannot determine
3. Allowing users to review and approve agent decisions
4. Creating interactive workflows where human input is required
5. Debugging and troubleshooting by pausing execution for user review

Usage with Strands Agent:
```python
from strands import Agent
from strands_tools import handoff_to_user

agent = Agent(tools=[handoff_to_user])

# Request user input and continue
response = agent.tool.handoff_to_user(
    message="I need your approval to proceed with deleting these files. Type 'yes' to confirm.",
    breakout_of_loop=False
)

# Stop execution and hand off to user
agent.tool.handoff_to_user(
    message="Task completed. Please review the results and take any necessary follow-up actions.",
    breakout_of_loop=True
)
```

The handoff tool can either pause for user input or completely stop the event loop,
depending on the breakout_of_loop parameter.
"""

import logging
from typing import Annotated, Any

from rich.panel import Panel
from strands import ToolContext, tool

from strands_tools.utils import console_util
from strands_tools.utils.user_input import get_user_input

# Initialize logging and console
logger = logging.getLogger(__name__)


@tool(context=True)
def handoff_to_user(
    message: Annotated[
        str,
        "Message to display to the user with context and instructions",
    ] = "Agent requesting user handoff",
    breakout_of_loop: Annotated[
        bool,
        "Whether to stop the event loop (True) or wait for user input (False)",
    ] = False,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Hand off control from agent to user for confirmation, input, or complete task handoff.

    Args:
        message: Message to display to the user with context and instructions.
        breakout_of_loop: Whether to stop the event loop (True) or wait for user input (False).
        tool_context: Framework-provided tool execution context.

    Returns:
        Dictionary containing status and response content.
    """
    invocation_state = (
        tool_context.invocation_state
        if tool_context is not None and isinstance(tool_context.invocation_state, dict)
        else {}
    )
    request_state = invocation_state.get("request_state", {})
    if not isinstance(request_state, dict):
        request_state = {}

    # Display handoff notification using rich console
    console = console_util.create()
    console.print()
    handoff_panel = Panel(
        f"🤝 [bold green]AGENT REQUESTING USER HANDOFF[/bold green]\n\n{message}", border_style="green", padding=(1, 2)
    )
    console.print(handoff_panel)

    if breakout_of_loop:
        # Stop the event loop and hand off control
        request_state["stop_event_loop"] = True

        stop_panel = Panel(
            "🛑 [bold red]Agent execution stopped. Control handed off to user.[/bold red]",
            border_style="red",
            padding=(0, 2),
        )
        console.print(stop_panel)
        console.print()

        logger.info(f"Agent handoff initiated with message: {message}")

        return {
            "status": "success",
            "content": [{"text": f"Agent handoff completed. Message displayed to user: {message}"}],
        }
    else:
        # Wait for user input and continue
        try:
            user_response = get_user_input(
                f"<bold>Agent requested user input:</bold> {message}\n<bold>Your response:</bold> "
            ).strip()

            console.print()

            logger.info(f"User handoff completed. User response: {user_response}")

            return {
                "status": "success",
                "content": [{"text": f"User response received: {user_response}"}],
            }
        except KeyboardInterrupt:
            console.print()
            interrupt_panel = Panel(
                "🛑 [bold red]User interrupted. Stopping execution.[/bold red]", border_style="red", padding=(0, 2)
            )
            console.print(interrupt_panel)
            console.print()
            request_state["stop_event_loop"] = True

            logger.info("User interrupted handoff. Execution stopped.")

            return {
                "status": "success",
                "content": [{"text": "User interrupted handoff. Execution stopped."}],
            }
        except Exception as e:
            logger.error(f"Error during user handoff: {e}")

            error_panel = Panel(
                f"❌ [bold red]Error getting user input: {e}[/bold red]", border_style="red", padding=(0, 2)
            )
            console.print(error_panel)
            console.print()

            return {
                "status": "error",
                "content": [{"text": f"Error during user handoff: {str(e)}"}],
            }
