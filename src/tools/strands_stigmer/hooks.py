"""Pre-action authorization hook for Strands agents.

A `BeforeToolCallEvent` hook that checks, before a tool executes, whether the
agent's current AWS identity is actually allowed to perform the operation it
is about to call. This is the medium-tier move: it authorizes *any* tool (not
just use_aws), ships in your own package, and needs no upstream approval.

The check is delegated to AWS's own policy simulator via Stigmer's authorize
MCP tool, which returns two independent fields:

    resolution: exact | partial | unresolved   (Stigmer's map)
    evaluation: allowed | denied | unknown     (AWS's simulator)

Policy decision (honest, never fabricated):

  * evaluation == denied   -> cancel the call, list the missing permissions
  * evaluation == allowed  -> let it through
  * evaluation == unknown  -> fail closed if configured (default: pass
                              through, because unknown means AWS itself could
                              not answer, not that access is wrong)

Usage:
    from strands import Agent
    from strands_stigmer import StigmerAuthHook

    agent = Agent(
        tools=[...],
        hooks=[StigmerAuthHook()],          # check use_aws tool calls
    )

    # Strict mode: any operation that cannot be verified is blocked too.
    agent = Agent(
        tools=[...],
        hooks=[StigmerAuthHook(fail_closed=True)],
    )
"""

from __future__ import annotations

import json
import re

from strands.hooks import BeforeToolCallEvent

from . import DEFAULT_URL, _mcp_call

# Tools whose arguments carry a service_name + operation_name pair that maps
# to IAM actions. use_aws is the universal boto3 passthrough; anything else
# in this set is treated the same way.
_AWS_TOOLS = {"use_aws"}

_SYMBOL_RE = re.compile(r"^[a-zA-Z0-9.-]+$")


def _operation_to_symbol(service_name: str, operation_name: str) -> str:
    """Convert boto3 snake_case names to a Stigmer SDK symbol.

    boto3 uses put_object; botocore's operation keys and Stigmer's map use
    PutObject. e.g. (s3, put_object) -> s3.PutObject.
    """
    parts = [p for p in operation_name.split("_") if p]
    camel = "".join(p[0].upper() + p[1:] for p in parts) if parts else operation_name
    return f"{service_name}.{camel}"


def _parse_authorize_text(text: str) -> dict:
    """Parse the authorize MCP text payload into a dict. Never raises."""
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


class StigmerAuthHook:
    """BeforeToolCallEvent hook that authorizes AWS tool calls pre-execution."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        tools: set[str] | None = None,
        fail_closed: bool = False,
        timeout: int = 10,
    ) -> None:
        self.url = url
        self.tools = set(tools) if tools is not None else set(_AWS_TOOLS)
        self.fail_closed = fail_closed
        self.timeout = timeout

    def _authorize(self, symbol: str) -> dict:
        text = _mcp_call("authorize", {"operations": symbol}, self.url)
        return _parse_authorize_text(text)

    def __call__(self, event: BeforeToolCallEvent) -> None:
        tool_name = (event.tool_use or {}).get("name", "")
        if tool_name not in self.tools:
            return

        arguments = (event.tool_use or {}).get("arguments", {}) or {}
        service_name = arguments.get("service_name") or arguments.get("service") or ""
        operation_name = arguments.get("operation_name") or arguments.get("operation") or ""
        if not service_name or not operation_name:
            return

        symbol = _operation_to_symbol(service_name, operation_name)
        try:
            result = self._authorize(symbol)
        except Exception as ex:
            if self.fail_closed:
                event.cancel_tool = (
                    f"stigmer authorize could not verify {symbol}: {ex}. "
                    f"Blocked by fail_closed policy."
                )
            return

        evaluation = result.get("evaluation")
        resolution = result.get("resolution", "unknown")
        missing = result.get("missing_permissions", [])

        if evaluation == "denied":
            detail = f"resolution={resolution}, missing_permissions={missing}"
            event.cancel_tool = (
                f"Stigmer pre-action authorization denied {symbol}: {detail}. "
                f"The agent's current identity is not allowed to perform this "
                f"operation. Missing IAM permissions: {', '.join(missing) if missing else 'unspecified'}."
            )
            return

        if evaluation == "unknown" and self.fail_closed:
            reason = result.get("reason") or "AWS's policy simulator could not produce a verdict"
            event.cancel_tool = (
                f"Stigmer pre-action authorization could not verify {symbol} "
                f"(resolution={resolution}): {reason}. Blocked by fail_closed policy."
            )
            return

        # evaluation == allowed, or evaluation == unknown with fail-open: pass through.


def stigmer_authorize_hook(**kwargs) -> StigmerAuthHook:
    """Convenience factory for StigmerAuthHook (drop-in for Agent(hooks=[...]))."""
    return StigmerAuthHook(**kwargs)


__all__ = ["StigmerAuthHook", "stigmer_authorize_hook"]
