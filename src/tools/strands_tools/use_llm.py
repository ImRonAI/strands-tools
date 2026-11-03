"""
Dynamic LLM instance creation for Strands Agent.

This module provides functionality to start new AI event loops with specified prompts,
allowing you to create isolated agent instances for specific tasks or use cases.
Each invocation creates a fresh agent with its own context and state.

Strands automatically handles the lifecycle of these nested agent instances,
making them powerful for delegation, specialized processing, or isolated computation.

Usage with Strands Agent:
```python
from strands import Agent
from strands_tools import use_llm

agent = Agent(tools=[use_llm])

# Basic usage with just a prompt and system prompt (inherits all parent tools)
result = agent.tool.use_llm(
    prompt="Tell me about the advantages of tool-building in AI agents",
    system_prompt="You are a helpful AI assistant specializing in AI development concepts."
)

# Usage with specific tools filtered from parent agent
result = agent.tool.use_llm(
    prompt="Calculate 2 + 2 and retrieve some information",
    system_prompt="You are a helpful assistant.",
    tools=["calculator", "retrieve"]
)

# Usage with mixed tool filtering from parent agent
result = agent.tool.use_llm(
    prompt="Analyze this data file",
    system_prompt="You are a data analyst.",
    tools=["file_read", "calculator", "python_repl"]
)

# The response is available in the returned object
print(result["content"][0]["text"])  # Prints the response text
```

See the use_llm function docstring for more details on configuration options and parameters.
"""

import logging
from typing import Annotated, Any

from strands import Agent, tool
from strands.telemetry.metrics import metrics_to_string

logger = logging.getLogger(__name__)


@tool
def use_llm(
    prompt: Annotated[str, "What should this AI event loop do?"],
    system_prompt: Annotated[str, "System prompt for the new event loop"],
    tools: Annotated[
        list[str] | None,
        (
            "List of tool names to make available to the nested agent. "
            "Tool names must exist in the parent agent's tool registry. "
            "If not provided, inherits all tools from parent agent."
        ),
    ] = None,
    agent: Any = None,
) -> dict[str, Any]:
    """Start a new AI event loop with a specified prompt.

    Args:
        prompt: The prompt to process with the new agent instance.
        system_prompt: Custom system prompt for the agent.
        tools: List of tool names to make available to the nested agent.
        agent: Parent agent (automatically provided by Strands framework).

    Returns:
        Dictionary containing status and response content.
    """
    logger.warning(
        "DEPRECATION WARNING: use_llm will be removed in the next major release. "
        "Migration path: replace use_llm calls with use_agent for equivalent functionality."
    )

    resolved_tools: list[Any] = []
    trace_attributes: dict[str, Any] = {}
    extra_kwargs: dict[str, Any] = {}

    if agent is not None:
        trace_attributes = getattr(agent, "trace_attributes", {})
        extra_kwargs["callback_handler"] = getattr(agent, "callback_handler", None)

        # If specific tools are provided, filter parent tools; otherwise inherit all tools from parent
        if tools is not None:
            filtered_tools = []
            for tool_name in tools:
                if tool_name in agent.tool_registry.registry:
                    filtered_tools.append(agent.tool_registry.registry[tool_name])
                else:
                    logger.warning(f"Tool '{tool_name}' not found in parent agent's tool registry")
            resolved_tools = filtered_tools
        else:
            resolved_tools = list(agent.tool_registry.registry.values())
    elif tools is not None:
        resolved_tools = list(tools)

    # Display input prompt
    logger.debug(f"\n--- Input Prompt ---\n{prompt}\n")

    # Visual indicator for new LLM instance
    logger.debug("🔄 Creating new LLM instance...")

    # Initialize the new Agent with provided parameters
    nested_agent = Agent(
        messages=[],
        tools=resolved_tools,
        system_prompt=system_prompt,
        trace_attributes=trace_attributes,
        **extra_kwargs,
    )
    # Run the agent with the provided prompt
    result = nested_agent(prompt)

    # Extract response
    assistant_response = str(result)

    # Display assistant response
    logger.debug(f"\n--- Assistant Response ---\n{assistant_response.strip()}\n")

    # Print metrics if available
    metrics_text = ""
    if result.metrics:
        metrics = result.metrics
        metrics_text = metrics_to_string(metrics)
        logger.debug(metrics_text)

    return {
        "status": "success",
        "content": [
            {"text": f"Response: {assistant_response}"},
            {"text": f"Metrics: {metrics_text}"},
        ],
    }
