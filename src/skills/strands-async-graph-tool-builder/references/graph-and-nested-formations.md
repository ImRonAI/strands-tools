# Graphs and nested formations

## Formation selection

Primary page: [Multi-agent Patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/).

Choose the execution primitive according to who controls the path:

| Formation | Path control | Native Python structural type | Best use |
|---|---|---|---|
| Graph | developer-defined nodes, edges, and conditions | `Graph(MultiAgentBase)` | deterministic routing, fan-out, joins, loops |
| Swarm | agents choose handoffs dynamically | `Swarm(MultiAgentBase)` | collaborative exploration and specialist handoffs |
| Workflow tool | developer-defined task DAG managed by a tool | decorated tool/manager, not `MultiAgentBase` | persisted, tool-invoked task orchestration |
| Agent as tool | parent Agent chooses a specialist tool | `Agent.as_tool()` or decorated tool | hierarchical delegation |
| A2AAgent | local graph calls a remote agent | `AgentBase` | distributed specialists |

A powerful graph tool should expose all of these without pretending they have the same runtime contract. Compile recursive topology specifications into native `AgentBase` or `MultiAgentBase` executors wherever possible.

## Native graph contract

Primary page: [Graph Multi-Agent Pattern](https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/).

The Python source defines:

- [`GraphNode.executor: AgentBase | MultiAgentBase`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L223-L235)
- [`GraphBuilder.add_node(executor, node_id)`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L301-L333)
- [`GraphBuilder.add_edge(..., condition=...)`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L335-L365)
- [`Graph(MultiAgentBase)`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L494-L562)

This makes an ordinary Agent, an A2AAgent, a Swarm, a nested Graph, or a custom `MultiAgentBase` implementation a valid graph node.

`GraphBuilder` also exposes:

- `set_entry_point`
- `reset_on_revisit`
- `set_max_node_executions`
- `set_execution_timeout`
- `set_node_timeout`
- `set_graph_id`
- `set_session_manager`
- `set_hook_providers`
- `set_plugins`

Every graph with a cycle needs both an execution-count bound and a wall-clock bound. Every nested formation needs its own local limits as well as the parent's node timeout.

## Graph result and state types

The relevant SDK types are:

- [`Status`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/base.py#L26-L41): pending, executing, completed, failed, interrupted.
- [`NodeResult`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/base.py#L44-L126): wraps `AgentResult`, nested `MultiAgentResult`, or exception plus usage, metrics, time, count, and interrupts.
- [`MultiAgentResult`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/base.py#L129-L177): overall status, per-node results, aggregate usage/metrics/time/count, interrupts.
- [`GraphState`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L107-L170): task, node sets, results, execution order, metrics, topology summary.
- [`GraphResult`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L173-L183): graph totals and structural details on top of `MultiAgentResult`.

Do not collapse nested results to strings internally. Preserve typed results and serialize only at the graph-tool boundary.

## Recursive node specification

Use a strict discriminated union. A robust schema supports at least:

```text
NodeSpec =
  AgentNodeSpec
  SkillAgentNodeSpec
  SwarmNodeSpec
  GraphNodeSpec
  WorkflowNodeSpec
  ParallelNodeSpec
  ToolBatchNodeSpec
  A2ANodeSpec
  FunctionNodeSpec
```

Common fields:

- `id`: unique within the containing formation;
- `kind`: discriminator;
- `input_mapping` and `output_mapping`;
- `timeout_seconds`;
- `retry_policy`;
- `capability_policy`;
- `model_policy`;
- `metadata` with no secrets;
- `limits` for tokens, cost, events, and output size.

Recursive nodes carry a nested formation specification. Enforce maximum depth, total expanded nodes, total edges, fan-out, concurrency, and serialized size before allocating Agents.

## Nested Graph and Swarm

The official `Nested Multi-Agent Patterns` heading states that a Graph or Swarm can be a node in another Graph. The native builder confirms this through the `MultiAgentBase` union.

Compilation:

```python
child = compile_formation(child_spec, context)
builder.add_node(child, node_spec.id)
```

At execution, the parent Graph calls `child.stream_async(...)` and wraps every child event in `MultiAgentNodeStreamEvent`. It captures the child's final `result` event without executing the child twice. See [nested executor streaming](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L1013-L1052).

Requirements:

1. Preserve a hierarchical `node_path`; a single `node_id` is ambiguous across nested graphs.
2. Apply limits at each depth.
3. Instantiate unique executor objects; the builder rejects duplicate object instances.
4. Rebuild child instances per run unless intentionally restoring a persisted run.
5. Propagate the same trusted invocation-state object to descendants.
6. Normalize nested result, interrupt, failure, and usage events without discarding their native payload.

## Swarm contract and limits

Primary page: [Swarm Multi-Agent Pattern](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/).

Python [`Swarm.__init__`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/swarm.py#L237-L316) accepts `nodes: list[Agent]`, not arbitrary `MultiAgentBase` values.

Therefore:

- Graph → Swarm is native.
- Graph → Graph is native.
- Swarm → Graph and Swarm → Swarm are not direct member relationships.
- A Swarm Agent may still call a graph, workflow, `use_skill`, or other orchestration tool.

Configure and bound:

- `entry_point`
- `max_handoffs`
- `max_iterations`
- `execution_timeout`
- `node_timeout`
- repetitive-handoff detection
- hooks, session manager, plugins, and trace attributes

Swarm injects a `handoff_to_agent` coordination tool into each member. Reject member tools with the same name. Member Agents may not have their own session managers; attach persistence to the Swarm.

## Workflow compilation

Primary page: [Agent Workflows](https://strandsagents.com/docs/user-guide/concepts/multi-agent/workflow/).

The current Tools repository workflow uses a `ThreadPoolExecutor`, finds dependency-ready tasks, and submits independent tasks concurrently. See [current scheduler](https://github.com/strands-agents/tools/blob/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e/src/strands_tools/workflow.py#L560-L709).

It remains a decorated tool/manager rather than `AgentBase` or `MultiAgentBase`. It is therefore not a native structural Graph node.

Provide two explicit modes:

1. `workflow_tool`: give an Agent node the existing workflow tool. This preserves its file-backed manager behavior but exposes only tool-stream behavior available from that implementation.
2. `workflow`: compile its task DAG into a nested native Graph. This gives structural nesting, graph hooks, native event streaming, interrupts, usage aggregation, and recursive paths.

For compiled workflows:

- translate task dependencies into edges;
- translate independent ready tasks into parallel Graph entry/ready nodes;
- create explicit AND barriers for fan-in;
- map priority only where the runtime actually supports it;
- persist a topology hash with run state;
- preserve task IDs as child node IDs;
- make error policy explicit: fail-fast, continue-independent, or compensate.

Do not claim pause/resume, priority, retry, or persistence unless the compiled implementation proves each feature.

## Parallel and batch compilation

Native Python Graph executes the current ready batch concurrently. It creates one task per ready node and merges events as they arrive. See [ready-node stream merge](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L819-L908).

Use `parallel` for a recursive formation containing Agent or MultiAgent children. Compile it to a nested Graph with multiple entry points and an optional join.

Use `tool_batch` for deterministic tool invocations. The current community [`batch`](https://github.com/strands-agents/tools/blob/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e/src/strands_tools/batch.py#L65-L173) loops sequentially, so do not use it to satisfy true-parallel requirements.

A production `tool_batch` must:

- resolve tools through an allowlisted registry;
- create stable `ToolUse` IDs;
- preserve before/after tool hooks, middleware, tracing, interrupts, and retries;
- run with bounded concurrency;
- merge progress in arrival order;
- cancel siblings according to declared failure policy;
- return results in deterministic input order with per-call status;
- never import a private SDK executor without pinning and compatibility tests.

When a public executor contract cannot meet these requirements, prefer compiling batch work into ordinary graph nodes or contribute the missing public API upstream.

## Python join semantics

The official `Waiting for All Dependencies` heading documents a critical Python behavior: incoming edges use OR semantics by default. A target becomes ready when any incoming source in the completed batch has a traversable edge.

For an AND join, attach the same all-dependencies condition to every incoming edge:

```python
def all_complete(required: tuple[str, ...]):
    def condition(state):
        return all(
            node_id in state.results
            and state.results[node_id].status == Status.COMPLETED
            for node_id in required
        )
    return condition
```

The common graph diagram `worker1, worker2, worker3 -> aggregator` is insufficient by itself in Python. The topology compiler must make `join="all"` explicit and generate conditions.

Support at least:

- `join="any"`: native default;
- `join="all"`: all required sources completed;
- `join="quorum"`: custom condition with a declared threshold;
- `join="expression"`: only from a safe, non-code expression language;
- `join="none"`: entry point.

Never evaluate model-provided Python code for edge conditions.

## Conditional edges and cycles

[`EdgeConditionWithContext`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L66-L104) receives `GraphState` plus keyword-only `invocation_state`. Legacy conditions receive only state.

Compile conditions from a safe declarative representation:

- result status;
- structured output fields;
- invocation-state flags from an allowlist;
- numeric comparisons;
- boolean combinations with bounded complexity.

Cycles require:

- a declared exit condition;
- a strictly positive `max_node_executions`;
- execution and node timeouts;
- a revisit state policy;
- retry/cycle attempt numbers in stream events;
- tests for both exit and limit exhaustion.

`reset_on_revisit=True` restores captured messages, Agent state, and model state. It does not reconstruct arbitrary external resources.

The current builder setters do not reject zero or negative numeric limits. The
topology compiler must validate positive values before construction.

## Custom structural nodes

The official `Custom Node Types` heading demonstrates subclassing `MultiAgentBase`. A production custom node implements:

- `invoke_async`;
- preferably true `stream_async`;
- `serialize_state`;
- `deserialize_state`;
- `add_hook` when it supports plugins/hooks;
- stable `id`;
- metrics, status, interrupts, and final `MultiAgentResult`.

Use this for `SkillAgentNode`, deterministic function nodes, guarded external operations, or a bounded streaming scheduler. Do not create a custom node merely to wrap a type already accepted by `GraphBuilder`.

## Remote A2A nodes

Primary page: [Agent-to-Agent Protocol](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agent-to-agent/).

Python Graph accepts `A2AAgent` because it is an `AgentBase` implementation. Install the documented extra:

```bash
pip install 'strands-agents[a2a]'
```

Treat remote nodes as a separate trust boundary:

- authenticate and authorize the endpoint;
- bound request, stream, and idle timeouts;
- validate remote event/result schemas;
- redact invocation state;
- attach trace correlation IDs;
- handle network retries idempotently;
- never assume remote tools share the local capability policy.

Current A2A `input_required` and `auth_required` states do not provide local
Strands `Interrupt` objects, and the converter rejects local interrupt-response
content. Reject or feature-gate remote interrupt/resume until an actual A2A
endpoint proves the full path.

## Native concurrency and backpressure boundary

The current Python Graph uses `asyncio.Queue()` without a maximum size for the internal ready-node event merger. If the outer consumer stops reading while children continue producing, the queue can grow.

Ready nodes run in discrete concurrent batches. Parallel event order is not
stable, and unrelated children discovered in the same batch can delay the next
generation. Total timeout and maximum-node-execution checks happen between
batches, so an active batch can overshoot those boundaries. Per-node timeout
does wrap nested formations.

For a production UI stream:

1. consume the native graph iterator continuously in a dedicated run task;
2. place normalized events into a bounded application queue;
3. declare the overflow policy by event class—never silently drop terminal, interrupt, error, or tool-result events;
4. coalesce only explicitly coalescible progress/text events;
5. expose queue depth and dropped/coalesced counters;
6. propagate client disconnect cancellation;
7. if strict end-to-end backpressure is required, use a compatible bounded graph scheduler rather than claiming the native unbounded merger provides it.

## Structural compilation checklist

- Every expanded executor is `AgentBase` or `MultiAgentBase`.
- Swarm membership contains only unique Agent instances.
- Workflow and parallel formations compile to nested Graphs when structural streaming is required.
- Tool batch does not rely on the sequential community `batch`.
- Python fan-in has explicit join semantics.
- Cycles have exit conditions and hard limits.
- Numeric limits are validated as positive by the compiler, and documented as
  batch-boundary limits where that is what the native runtime provides.
- All nested levels have unique IDs, path-aware events, timeouts, and budgets.
- Model, tool, skill, A2A, and condition inputs are resolved through trusted allowlists.
- A new executable formation is instantiated per run.
- The implementation proves event streaming, interrupts, cancellation, and final typed results with real integrations.
- Raised Agent failures and returned `Status.FAILED` results are tested
  separately; no “error edge” behavior is claimed unless explicitly implemented.
