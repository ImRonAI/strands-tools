# Hooks, interrupts, state, and sessions

## Hook lifecycle

Primary page: [Hooks](https://strandsagents.com/docs/user-guide/concepts/agents/hooks/).

Single-Agent hooks cover invocation, model, message, and tool lifecycles. Multi-agent hooks cover:

1. `MultiAgentInitializedEvent`
2. `BeforeMultiAgentInvocationEvent`
3. repeated `BeforeNodeCallEvent` / `AfterNodeCallEvent`
4. `AfterMultiAgentInvocationEvent`

Current dataclasses: [hook events](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/hooks/events.py#L26-L418).

Attach hooks at the correct layer:

- Graph/Swarm hooks: policy and telemetry around formation invocation and node execution;
- Agent hooks: model/tool policy, retry tracking, redaction, and per-Agent telemetry;
- tool implementation: domain progress and deterministic resource cleanup.

A Graph hook does not replace Agent tool/model hooks inside a node.

## HookProvider and ordering

[`HookProvider`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/hooks/registry.py#L112-L138) registers callbacks into a `HookRegistry`.

```python
class GraphPolicyHooks:
    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeNodeCallEvent, self.before_node)
        registry.add_callback(AfterNodeCallEvent, self.after_node)
```

Callbacks may be sync or async. `AgentInitializedEvent` is sync-only. Lower `order` values run earlier. After-events reverse ordering within the same order group for cleanup symmetry.

Use explicit order for:

- authorization before observability records “started”;
- retry counters before progress serialization;
- session persistence after state mutation;
- cleanup in reverse acquisition order.

Hook events are mostly read-only. Only mutate documented fields such as `cancel_node`, `cancel_tool`, selected tool/use, retry, result, or invocation resume.

## Invocation state

Primary page: [State Management](https://strandsagents.com/docs/user-guide/concepts/agents/state/), heading `Invocation State`.

Invocation state is shared by reference during one invocation and is not sent to the model. Graph passes the same dictionary to nested Agent and MultiAgent executors and to context-aware edge conditions.

Recommended trusted keys:

```text
request_id
tenant_id
principal
capability_policy
model_policy
run_id
session_id
trace_context
cancellation
attempt_registry
artifact_store
```

Rules:

1. Namespace framework/application keys to avoid collisions.
2. Keep secrets in handles or vault references, not serializable event payloads.
3. Treat model input as untrusted and never merge it wholesale into invocation state.
4. Avoid mutating one shared dictionary concurrently without a lock or per-task child view.
5. Define which child mutations are allowed to propagate upward.
6. Pass the same required trusted state again on interrupt resume; current Graph serialization does not include arbitrary invocation state.

## Policy hooks

Before compiling:

- authorize graph actions and topology;
- resolve tenant-scoped registry and session;
- validate quotas and budget.

Before each node:

- check node capability and model policies;
- enforce run cancellation;
- emit trace context;
- interrupt for human approval on high-impact actions;
- cancel denied nodes with a stable policy code.

Before each tool:

- re-authorize the exact tool call and arguments;
- apply sandbox and path/network policy;
- redact or replace sensitive inputs;
- assign idempotency keys;
- enforce per-tool budgets.

After each node/tool:

- record accepted result, latency, usage, retries, and policy outcome;
- persist durable state;
- redact unsafe output;
- release per-call resources.

Do not rely on a system prompt as authorization.

## Interrupt and resume contract

Primary page: [Interrupts](https://strandsagents.com/docs/user-guide/concepts/interrupts/), headings `Graph`, `Components`, and `Rules`.

A `BeforeNodeCallEvent` can call:

```python
response = event.interrupt(
    "namespace:approval",
    reason={"action": "deploy", "environment": "production"},
)
if response != "approve":
    event.cancel_node = "Approval denied"
```

If no response exists, `interrupt()` raises an internal interrupt signal. The Graph returns `Status.INTERRUPTED` and `Interrupt` objects. Resume with:

```python
responses = [
    {
        "interruptResponse": {
            "interruptId": interrupt.id,
            "response": "approve",
        }
    }
]
result = await graph.invoke_async(responses, invocation_state=trusted_state)
```

Types:

- [`Interrupt`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/interrupt.py#L11-L29)
- [`InterruptResponse` and `InterruptResponseContent`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/interrupt.py#L126-L145)
- [resume validation](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/interrupt.py#L72-L106)

All concurrently running Graph nodes finish their current batch even when one interrupts. Design side effects accordingly.

Requirements:

- namespace interrupt names;
- make reason and response JSON-serializable;
- bind responses to tenant, principal, run, topology hash, node path, and interrupt ID;
- reject unknown, expired, replayed, or unauthorized responses;
- persist interrupt state before returning control;
- treat “deny” as a policy result, not a transport error;
- do not confuse pause with cancellation.

## Nested interrupts

Native parent Graph captures child interrupts through the nested child result. Preserve:

- original child interrupt ID;
- complete node path;
- child formation/run identity;
- reason;
- parent run identity.

The graph-tool API should expose one resume action capable of routing responses to the correct live or restored child formation. A topology change invalidates pending interrupt responses unless an explicit migration exists.

Remote A2A `input_required` or `auth_required` currently maps imperfectly into the local Strands interrupt contract: the resulting AgentResult may signal interrupt without local `Interrupt` objects, and the converter rejects local interrupt-response content. Reject this path or implement and prove a dedicated remote resume contract.

## Session and crash-resume contract

Primary page: [Session Management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/).

[`SessionManager`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/session/session_manager.py#L31-L129) is a hook provider. It restores multi-agent state at initialization and syncs it after node calls and after the formation invocation.

Attach one compatible session manager to the Graph or Swarm. Native validation rejects individual Graph/Swarm member Agents that carry their own session managers.

Graph serialization includes:

- graph ID and status;
- completed, failed, and interrupted nodes;
- node results;
- next nodes;
- current task;
- execution order;
- usage, metrics, count, and elapsed time;
- internal interrupt state.

See [Graph serialization](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L1265-L1317).

It does not store the topology or arbitrary invocation state. Restore must:

1. load the exact validated topology version;
2. reconstruct equivalent executor IDs and formation structure;
3. attach the same compatible session manager;
4. restore Graph state;
5. rehydrate trusted invocation context from the application;
6. reject a topology-hash mismatch unless a tested migration exists.

## Registry and lifecycle

The current community graph tool uses a process-global manager holding live Graph instances. Do not copy that lifecycle for a multi-user service.

Store:

- immutable validated topology specification;
- topology hash and compiler/SDK versions;
- tenant ownership and policy;
- session reference;
- run metadata and durable event cursor.

Create:

- fresh Agent, Swarm, Graph, and custom-node instances per run;
- a run-scoped cancellation handle;
- bounded event buffers;
- run-scoped invocation state.

Live run tasks belong in an injected application registry keyed by tenant and run ID. Expire completed runs and close all resources. Cross-process deployments need a durable coordinator rather than in-memory globals.

## Observability

Use native trace attributes and hooks, but add application-level spans for:

- topology validation and compilation;
- each formation and node path;
- tool resolution and policy;
- queue wait and consumer lag;
- retries and revisits;
- interrupt wait time separately from execution time;
- persistence;
- cancellation cleanup.

Correlate logs, traces, stream envelopes, session records, and artifacts with `request_id`, `run_id`, `graph_id`, topology hash, node path, and `toolUseId`.

Never export prompts, tool arguments, invocation state, or results without a redaction policy.

## Hook and persistence validation checklist

- Hooks run at root and nested Graph/Swarm levels in the expected order.
- Tool/model hooks run inside node Agents.
- Async hook callbacks are awaited.
- A denied node emits cancellation/failure with a stable policy reason.
- A real human interrupt pauses, persists, restores, and resumes the correct nested node.
- Concurrent siblings finish according to documented interrupt semantics.
- Invalid and replayed interrupt responses are rejected.
- The same trusted invocation context is restored explicitly.
- A process restart rebuilds the matching topology and continues from persisted state.
- A topology-hash mismatch fails safely.
- Two tenants cannot access one another's topology, run, events, or interrupts.
- No live Graph instance is shared across concurrent runs.
