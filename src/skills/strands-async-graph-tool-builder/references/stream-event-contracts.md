# Async stream and event contracts

## Async iterator contract

Primary page: [Async Iterators for Streaming](https://strandsagents.com/docs/user-guide/concepts/streaming/async-iterators/).

`Agent.stream_async(...)`, `Graph.stream_async(...)`, and `Swarm.stream_async(...)` are async iterators. Consume them with `async for`; do not call synchronous wrappers from an async request path.

Every supported executor must end with a result-bearing event:

- Agent: `{"result": AgentResult}`
- Graph/Swarm: `{"type": "multiagent_result", "result": MultiAgentResult}`
- Tool: terminal `ToolResultEvent`

The parent Graph relies on this invariant. A nested executor that ends without a `result` event fails the node.

## Native event families

Primary page: [Streaming Events](https://strandsagents.com/docs/user-guide/concepts/streaming/).

### Agent and model events

Python Agent streams dictionary-like typed events for lifecycle, model chunks, assembled messages, reasoning, tool use, tool results, force stop, and final result. Preserve unknown event fields to remain forward-compatible.

### Tool events

Current Python event classes:

- [`ToolResultEvent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L282-L311)
- [`ToolStreamEvent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L314-L329)
- [`AgentAsToolStreamEvent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L332-L354)
- [`ToolCancelEvent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L357-L377)
- [`ToolInterruptEvent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L380-L405)

`ToolResultEvent` is terminal inside the tool executor, but it has
`is_callback_event=False` and is not yielded by the enclosing
`Agent.stream_async`. At that layer, observe tool completion through the later
user-role message containing `toolResult`, hooks, and the final `AgentResult`.
A concrete `AgentTool.stream` still must emit exactly one terminal
`ToolResultEvent` for its caller to consume internally.

`ToolStreamEvent.as_dict()` contains:

```python
{
    "type": "tool_stream",
    "tool_stream_event": {
        "tool_use": tool_use,
        "data": yielded_value,
    },
}
```

### Multi-agent events

Current Python event classes and payloads:

| Type | Required fields |
|---|---|
| `multiagent_node_start` | `node_id`, `node_type` |
| `multiagent_node_stream` | `node_id`, nested `event` |
| `multiagent_node_stop` | `node_id`, `node_result` |
| `multiagent_handoff` | `from_node_ids`, `to_node_ids`, optional `message` |
| `multiagent_node_cancel` | `node_id`, `message` |
| `multiagent_node_interrupt` | `node_id`, `interrupts` |
| `multiagent_result` | `result` |

Definitive source: [multi-agent events](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L463-L616).

Use the exact source spelling `multiagent_*`. Do not normalize it to the stale `multi_agent_*` spelling found in some docstrings.

## Nested stream paths

Native Graph wraps a child event in `multiagent_node_stream`. If the child is another Graph, its events are wrapped again. Preserve that raw nesting, but also provide a flattened envelope for clients:

```json
{
  "schema_version": "1.0",
  "run_id": "run_...",
  "graph_id": "root",
  "sequence": 42,
  "event_id": "run_...:42",
  "occurred_at": "2026-07-26T20:00:00.000Z",
  "monotonic_ns": 123456789,
  "path": [
    {"kind": "graph", "id": "root"},
    {"kind": "swarm", "id": "research_team"},
    {"kind": "agent", "id": "medical_researcher"}
  ],
  "type": "node.stream",
  "native_type": "multiagent_node_stream",
  "attempt": 1,
  "provisional": true,
  "payload": {}
}
```

Rules:

1. Assign `sequence` at the outermost stream boundary in arrival order.
2. Treat order between concurrent producers as nondeterministic.
3. Retain the raw native event under a safely serialized payload or debug field.
4. Use a path array rather than concatenated IDs.
5. Carry graph, formation, node, tool-use, and attempt identity separately.
6. Emit one terminal envelope per run and one terminal `ToolResultEvent` per graph-tool call.

## Event serialization

Native events are dictionary-like, but payloads contain dataclasses, enums, content blocks, results, exceptions, binary media, or provider objects.

Implement an explicit serializer for:

- `TypedEvent.as_dict()`;
- `AgentResult.to_dict()` when available;
- `NodeResult.to_dict()` and `MultiAgentResult.to_dict()`;
- `Status.value`;
- `Interrupt.to_dict()`;
- content blocks, including binary references;
- exceptions as safe type/message/cause metadata;
- unknown objects as redacted type markers, not arbitrary `repr` containing secrets.

Set output-size bounds at:

- one event;
- one node;
- one run;
- buffered unsent data.

Large artifacts should be stored through an artifact service and streamed as references.

## Terminal invariants

A run state machine should allow:

```text
created -> compiling -> running
running -> interrupted -> running
running -> completed | failed | cancelled | timed_out
```

Terminal states are mutually exclusive. Once terminal:

- reject further progress events;
- close child generators;
- cancel/await live tasks;
- flush required terminal/error/usage events;
- release registry and transport resources;
- persist final state;
- make repeated cancel/resume requests idempotent.

The final graph-tool result contains the terminal status, run ID, topology hash, result references, usage, elapsed time, interrupt summary, and any failed node paths.

## Retry-aware streaming

The SDK documents that model and tool retry hooks can discard an attempt after its chunks have already streamed. Never present all chunks as irrevocably committed.

Track:

- `model_attempt`;
- `tool_attempt` keyed by `toolUseId`;
- `node_attempt` or execution count;
- `cycle_iteration`;
- `resume_generation`.

Use hook callbacks and trusted invocation state to maintain these counters. Mark progress provisional until the containing operation has an accepted result. The client can group attempts and de-emphasize discarded ones.

## Backpressure and queue policy

Bound every application-owned queue. A suggested policy:

| Event class | Overflow behavior |
|---|---|
| result, interrupt, error, cancel, terminal | never drop |
| node start/stop, tool start/result | never drop |
| text/model delta | coalesce adjacent chunks from the same source |
| progress percentage | keep the newest value per source |
| debug/trace detail | sample or redirect to observability storage |

Expose queue depth, coalesced count, dropped debug count, and consumer lag. If the queue remains full beyond an idle timeout, cancel the run or detach it into a persistent background stream according to explicit policy.

The native Python Graph's internal node queue is currently unbounded. A bounded outer queue alone does not create strict end-to-end backpressure. Document this limit or implement a compatible bounded scheduler.

## Cancellation and disconnects

Cancellation is different from interrupt:

- interrupt pauses for a response and retains resumable state;
- cancellation is terminal and tears down work;
- timeout is a policy-driven cancellation with a distinct terminal reason.

On `asyncio.CancelledError` or client disconnect:

1. set the run cancellation signal;
2. stop accepting new nodes;
3. cancel all live node/tool tasks;
4. close nested async generators;
5. await cancelled tasks with `return_exceptions=True`;
6. persist terminal cancellation;
7. emit or store the terminal record if the transport is gone;
8. re-raise cancellation where framework semantics require it.

Do not swallow `CancelledError` under a generic exception handler.

Native `Agent.cancel()` is cooperative and Graph has no public `cancel()`.
Cancelling an outer Agent therefore does not establish that a running nested
Graph tool stopped. Retain the task that consumes the graph iterator, cancel it
explicitly, close nested generators, and prove that no child task remains.

## UI transport contract

The graph tool's internal async iterator is transport-neutral. Adapt it to SSE or WebSocket with:

- a protocol version;
- event IDs and resumable cursors;
- heartbeat/keepalive separate from graph events;
- JSON framing without terminal sentinels hidden in text;
- authentication per reconnect;
- tenant/run authorization;
- replay from durable storage or an explicit “replay unavailable” error;
- exact once-at-client semantics implemented through event IDs and deduplication, not assumed from the network.

The UI should show nested path, formation type, node state, tool progress, interrupts requiring action, retries, usage, and terminal status.

## Async stream validation checklist

- First progress event arrives before final completion.
- Two ready nodes produce interleaved progress under a real slow I/O workload.
- Nested Graph → Swarm → Agent events retain full paths.
- Skill-subagent events are visible through their node and tool layers.
- The terminal result occurs once.
- Tool/model retries do not make discarded chunks appear committed.
- A slow consumer exercises coalescing and queue metrics.
- Disconnect cancels or detaches according to policy.
- Timeout, explicit cancel, and human interrupt produce different statuses.
- The final usage equals recursively accumulated usage.
- SSE/WebSocket replay deduplicates by event ID in the actual UI.
