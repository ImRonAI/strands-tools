# Custom tools and tool streaming

## Official document: Creating Custom Tools

Primary page: [Creating Custom Tools](https://strandsagents.com/docs/user-guide/concepts/tools/custom-tools/).

The relevant official headings are:

- `Async Invocation`: an `async def` decorated tool can await I/O.
- `ToolContext`: `@tool(context=True)` injects the calling Agent, `ToolUse`, and invocation state.
- `Accessing State in Tools`: request-scoped state belongs in `ToolContext.invocation_state`, not model-visible arguments.
- `Tool Streaming`: an async-generator tool yields progress; the SDK surfaces each yield under `tool_stream_event`.
- `Tool Response Format`: the final tool result is a `ToolResult` with `toolUseId`, `status`, and typed content blocks.

Pinned documentation source: [`custom-tools.mdx`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/site/src/content/docs/user-guide/concepts/tools/custom-tools.mdx#L189-L470).

## Decorated function tool contract

Use `@tool` for ordinary sync, coroutine, or simple progress-streaming functions:

```python
from strands import ToolContext, tool

@tool(context=True)
async def lookup(query: str, tool_context: ToolContext) -> dict:
    tenant_id = tool_context.invocation_state["tenant_id"]
    return {"tenant_id": tenant_id, "query": query}
```

The decorator derives the input schema from the signature and docstring, validates model input, injects framework-owned context, and wraps the return value into a `ToolResultEvent`.

The source contract is [`DecoratedFunctionTool.stream`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/tools/decorator.py#L586-L700):

- async generator: every yielded item becomes a `ToolStreamEvent`; after exhaustion, the last item is wrapped as the final `ToolResultEvent`;
- coroutine: the awaited return value becomes the final `ToolResultEvent`;
- synchronous function: it runs in `asyncio.to_thread` and its return value becomes the final event;
- validation and execution exceptions are converted to error tool results.

Consequences for a graph tool:

1. An async-generator decorated tool must yield at least once because the current implementation uses the last yielded item as its result.
2. Its last item appears once as streamed data and again as the final tool result.
3. This convenience behavior is useful for progress tools but is imprecise for a nested event protocol with a single, non-duplicated terminal event.

## Low-level AgentTool contract

For a production graph tool, prefer a concrete [`AgentTool`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L212-L287) when terminal semantics, cancellation, and event identity must be exact.

Implement:

```python
from collections.abc import AsyncGenerator
from strands.types._events import ToolResultEvent, ToolStreamEvent
from strands.types.tools import AgentTool, ToolUse

class GraphTool(AgentTool):
    @property
    def tool_name(self) -> str: ...

    @property
    def tool_spec(self) -> dict: ...

    @property
    def tool_type(self) -> str:
        return "python"

    async def stream(
        self,
        tool_use: ToolUse,
        invocation_state: dict,
        **kwargs,
    ) -> AsyncGenerator:
        async for envelope in self._execute(tool_use, invocation_state):
            yield ToolStreamEvent(tool_use, envelope)
        yield ToolResultEvent(self._result(tool_use))
```

This pattern is a starting shape, not copy-paste-complete code. A real implementation must close child streams in `finally`, surface interrupts, preserve hook behavior, and return a valid final `ToolResult`.

Relevant types:

- [`ToolSpec`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L23-L38)
- [`ToolUse`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L53-L67)
- [`ToolResultContent` and `ToolResult`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L70-L101)
- [`ToolContext`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L130-L162)
- [`ToolGenerator`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L179-L183)

## ToolContext and invocation state

`ToolContext` is framework-created. Do not construct it yourself. Its fields are:

- `tool_use`: the exact tool request, including `toolUseId`, name, and input;
- `agent`: the executing Agent;
- `invocation_state`: caller-provided request state shared through the invocation.

Use invocation state for tenant identity, request IDs, capability policy, session IDs, tracing objects, cancellation handles, and other request-scoped values that must not enter the prompt.

Do not accept authorization policy, registry handles, or a model/provider object from model-controlled tool input. Resolve them from trusted application state.

## Tool execution choices

Primary page: [Tools Overview](https://strandsagents.com/docs/user-guide/concepts/tools/).

The official `Direct Method Calls` heading documents `agent.tool.<name>(...)`. The current implementation routes direct calls through the SDK's tool execution machinery and returns the final `ToolResult`, but it consumes intermediate stream events. It therefore does not provide a streaming primitive for a parallel tool-batch node.

The `Tool Executors` heading distinguishes concurrent and sequential model-requested tool execution. In the Python SDK, [`ConcurrentToolExecutor`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/tools/executors/concurrent.py#L19-L134) creates one task per `ToolUse` and merges their events through a queue.

Use these choices deliberately:

| Need | Preferred contract |
|---|---|
| Simple return value | decorated sync/coroutine tool |
| Simple progress and duplicated final progress is acceptable | decorated async-generator tool |
| Exact event/terminal protocol | `AgentTool.stream` |
| Model emits several independent tool uses in one turn | Agent with concurrent tool executor |
| Deterministic direct tool batch with streaming | a dedicated formation that invokes `AgentTool.stream` with hooks/tracing preserved, or an upstream-supported public executor API |

Avoid importing private executor methods into a general-purpose graph tool unless the dependency is pinned and a compatibility test guards the exact signature.

## Result and error requirements

A valid final result uses the model-facing shape:

```python
{
    "toolUseId": tool_use["toolUseId"],
    "status": "success",  # or "error"
    "content": [
        {"json": {"run_id": run_id, "status": "completed"}},
        {"text": "Graph completed"},
    ],
}
```

Requirements:

1. Always echo the original `toolUseId`.
2. Use `status="error"` for validation, policy, compile, or execution failure.
3. Keep a structured JSON block for machines and a concise text block for the model.
4. Redact secrets and non-serializable application objects.
5. Preserve a stable error code, failed node path, retryability, and causality chain.
6. Never turn a cancelled or interrupted run into a success result.
7. Emit exactly one terminal `ToolResultEvent`.

## Tool retry and idempotency

[`AfterToolCallEvent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/hooks/events.py#L176-L225) permits a hook to set `retry=True`. Intermediate `ToolStreamEvent`s from the discarded attempt have already reached consumers, while only the last attempt emits the accepted result.

Therefore:

- include `toolUseId`, `attempt`, `event_id`, and `provisional=true` on progress events;
- make side-effecting node operations idempotent using application keys;
- let the UI replace or group discarded-attempt progress rather than treating all chunks as committed;
- distinguish model retry, tool retry, node retry, and graph-cycle revisit.

## Production readiness checklist

- The implementation uses the installed SDK's actual `AgentTool`, event, and result types.
- The tool schema is a strict discriminated schema with size/depth/count bounds.
- Trusted request context comes from invocation state, not model input.
- Intermediate and terminal events are not accidentally duplicated.
- Child async generators are closed in `finally`.
- Cancellation propagates to every live child task and stream.
- Tool retries are visible and side effects are idempotent.
- No global mutable registry shares a live graph between tenants or concurrent runs.
- A real Agent invocation proves the model can call the tool and receive the final result.
- A real streaming client proves progress arrives before completion.
