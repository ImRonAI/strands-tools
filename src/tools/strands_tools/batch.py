"""
Batch Tool for Multi-Tool Invocation

This tool enables invoking multiple other tools from a single LLM message response. Note the
invocations run sequentially, despite the historical name.
It is designed for use with agents that support tool registration and invocation by name.

Example usage:
    import os
    import sys

    from strands import Agent
    from strands_tools import batch, http_request, use_aws

    # Example usage of the batch with http_request and use_aws tools
    agent = Agent(tools=[batch, http_request, use_aws])
    result = agent.tool.batch(
        invocations=[
            {"name": "http_request", "arguments": {"method": "GET", "url": "https://api.ipify.org?format=json"}},
            {
                "name": "use_aws",
                "arguments": {
                    "service_name": "s3",
                    "operation_name": "list_buckets",
                    "parameters": {},
                    "region": "us-east-1",
                    "label": "List S3 Buckets"
                }
            },
        ]
    )
"""

import logging
import traceback
from typing import Annotated, Any

from strands import tool

from strands_tools.utils import console_util

logger = logging.getLogger(__name__)

_DEPRECATION_MESSAGE = (
    "batch is deprecated. This warning becomes an error log in v0.9.0. Concurrent tool execution is now the default "
    "in the SDK via ConcurrentToolExecutor, so no replacement tool is needed - remove batch and call tools normally. "
    "See https://strandsagents.com/docs/user-guide/concepts/tools/executors/"
)


@tool
def batch(
    invocations: Annotated[
        list[dict[str, Any]],
        "The tool calls to invoke, each with 'name' (str) and 'arguments' (dict)",
    ],
    agent: Any = None,
) -> dict[str, Any]:
    """Invoke multiple other tool calls in sequence from one request.

    Args:
        invocations: List of tool invocation dictionaries, each containing 'name' and 'arguments'.
        agent: Parent agent (automatically provided by Strands framework).

    Returns:
        Dictionary with status and results for each invocation.
    """
    logger.warning("DEPRECATION WARNING: %s", _DEPRECATION_MESSAGE)

    console = console_util.create()
    results: list[dict[str, Any]] = []

    try:
        if not hasattr(agent, "tool") or agent.tool is None:
            raise AttributeError("Agent does not have a valid 'tool' attribute.")

        for invocation in invocations:
            tool_name = invocation.get("name")
            arguments = invocation.get("arguments", {})
            tool_fn = getattr(agent.tool, str(tool_name), None)

            if callable(tool_fn):
                try:
                    # Call the tool function with the provided arguments
                    result = tool_fn(record_direct_tool_call=False, **arguments)

                    # Create a consistent result structure
                    batch_result = {"name": tool_name, "status": "success", "result": result}
                    results.append(batch_result)

                except Exception as e:
                    error_msg = f"Error executing tool '{tool_name}': {str(e)}"
                    console.print(error_msg)

                    batch_result = {
                        "name": tool_name,
                        "status": "error",
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }
                    results.append(batch_result)
            else:
                error_msg = f"Tool '{tool_name}' not found in agent"
                console.print(error_msg)

                batch_result = {"name": tool_name, "status": "error", "error": error_msg}
                results.append(batch_result)

        # Create a readable summary for the agent
        summary_lines = []
        summary_lines.append(f"Batch execution completed with {len(results)} tool(s):")

        for result in results:
            if result["status"] == "success":
                summary_lines.append(f"✓ {result['name']}: Success")
            else:
                summary_lines.append(f"✗ {result['name']}: Error - {result['error']}")

        summary_text = "\n".join(summary_lines)

        return {
            "status": "success",
            "content": [
                {"text": summary_text},
                {
                    "json": {
                        "batch_summary": {
                            "total_tools": len(results),
                            "successful": len([r for r in results if r["status"] == "success"]),
                            "failed": len([r for r in results if r["status"] == "error"]),
                        },
                        "results": results,
                    }
                },
            ],
        }

    except Exception as e:
        error_msg = f"Error in batch tool: {str(e)}\n{traceback.format_exc()}"
        console.print(f"Error in batch tool: {str(e)}")
        return {
            "status": "error",
            "content": [{"text": error_msg}],
        }
