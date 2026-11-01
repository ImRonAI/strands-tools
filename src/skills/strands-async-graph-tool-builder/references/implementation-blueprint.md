# Production implementation blueprint

## Target architecture

Build a graph tool as five explicit layers:

```text
model-facing GraphTool (AgentTool)
  -> action and topology validation
  -> recursive topology compiler
  -> fresh run-scoped native executors
  -> stream normalizer and durable run registry
```

Keep schema, policy, compiler, runtime, transport, and persistence independent.
The model never supplies live Python objects, import paths, arbitrary callables,
edge-condition code, filesystem roots, credentials, or unrestricted package
names.

## Public actions and lifecycle

Expose a small action API instead of a process-global mutable manager:

- `validate`: parse, authorize, normalize, and hash a topology without running;
- `register`: persist an immutable, tenant-owned topology version;
- `run`: compile a registered or inline authorized topology and stream it;
- `resume`: continue a persisted interrupt with exact response IDs and topology hash;
- `cancel`: terminally stop a live run by tenant and run ID;
- `status`: return durable status, cursors, interrupts, and result references;
- `delete`: remove only an authorized inactive topology version or expired run.

Separate topology IDs, topology-version hashes, session IDs, run IDs, request
IDs, and tool-use IDs. Make retryable actions idempotent.

```text
validate -> register -> compile -> run
run -> interrupted -> resume -> run
run -> completed | failed | cancelled | timed_out
```

## Recursive topology schema

Use a discriminated recursive union:

```text
NodeSpec =
  AgentNode
  | GraphNode
  | SwarmNode
  | WorkflowNode
  | ParallelNode
  | ToolBatchNode
  | SkillAgentNode
  | A2ANode
  | RegisteredExecutorNode
```

Every node has:

- stable local ID, kind, and schema version;
- input mapping and structured output contract;
- explicit model and tool capability policies;
- timeout, retry, usage, and output-size budgets;
- trust and side-effect classification;
- streaming, redaction, hook, and approval policies.

Edges declare source, destination, input mapping, and join semantics. Conditions
come from a bounded declarative expression language over trusted invocation
state and typed prior results. Never evaluate model-provided Python or shell.

## Compiler pipeline

Compile in this order:

1. Parse strict typed models and reject unknown fields.
2. Upgrade old schema versions through explicit migrations.
3. Resolve tenant ownership and authorization.
4. Resolve registry references to immutable versions.
5. Validate unique IDs, executor identity rules, entry points, cycles, joins,
   positive limits, and total expanded size.
6. Resolve models and tools through trusted allowlists.
7. Compute the canonical topology hash.
8. Recursively turn every node into a factory.
9. Build fresh executor instances for the run.
10. Attach root and nested hooks, sessions, trace attributes, and policy.
11. Run a dry structural inspection before any model or tool call.

Return structured compiler diagnostics with node paths. Never partially execute
an invalid topology.

## Node compilers

| Node kind | Runtime form |
|---|---|
| `agent` | fresh `Agent` or authorized `AgentBase` |
| `graph` | nested native `Graph` |
| `swarm` | native `Swarm` containing only fresh local `Agent` members |
| `workflow` | nested Graph with dependency edges and explicit all-joins |
| `parallel` | nested Graph with sibling entry nodes and explicit collector join |
| `tool_batch` | bounded async custom `MultiAgentBase` or expanded graph nodes |
| `skill_agent` | first-class Agent with `AgentSkills`, or isolated Agent exposed through `Agent.as_tool()` when tool semantics are desired |
| `a2a` | `A2AAgent`, with remote interrupt/resume feature-gated |
| `registered` | trusted factory returning `AgentBase` or `MultiAgentBase` |

Graph is the universal structural composition root. Swarm is a leaf formation,
not a container for Graph, Swarm, or A2A executors.

Do not reuse the community `batch` loop as a parallel primitive. Do not reuse a
singleton workflow manager. Do not pretend a decorated workflow tool is a native
formation when structural events, hooks, interrupts, and sessions are required.

## Tool and skill policy

Resolve tools by stable registry ID and version. For every Agent, compute the
exact allowed tool set from trusted policy. An omitted list means no tools, not
“inherit everything.”

Treat shell, filesystem, browser, package, npm, template, dynamic-tool, secrets,
network, and deployment capabilities as separate grants. Validate arguments at
call time through hooks because model intent can change after compilation.

Support skill agents in two modes:

- first-class `skill_agent` node: participates directly in graph routing,
  results, sessions, hooks, and events;
- dynamic skill tool: an Agent uses a named skill on demand through a scoped
  `Agent.as_tool()` or production custom equivalent.

The current `AgentSkills` plugin activates skill instructions on the same Agent;
the older `use_skill` sample creates a separate child Agent. Make the mode
explicit. Do not infer parent tool inheritance.

## Runtime factory and registry

Persist immutable topology specs and factories, never live Graph objects.
Instantiate a new object tree per run because Agents, Graphs, Swarms, models,
hooks, and sessions carry mutable state.

Maintain an injected run registry keyed by tenant and run ID. Each entry owns:

- root executor and consumer task;
- cancellation scope and nested task set;
- bounded application event queue;
- session handle and concurrency lock;
- durable event writer and cursor;
- topology hash and compiler/SDK versions;
- current interrupts and terminal record.

Cross-process operation requires a durable coordinator. Session managers are not
assumed thread-safe; serialize concurrent access to one session.

## Streaming GraphTool

Prefer a concrete `AgentTool` whose `stream` method is an async generator. This
gives exact control over intermediate `ToolStreamEvent` records and the single
terminal `ToolResultEvent`.

The tool should:

1. validate the `ToolUse`, action, and trusted `invocation_state`;
2. create or locate the run;
3. start a task that continuously consumes `Graph.stream_async`;
4. recursively normalize native events without losing raw semantics;
5. yield progress as tool-stream events;
6. persist every accepted event before acknowledging a resumable cursor;
7. on terminal Graph result, emit one terminal tool result;
8. on cancellation, explicitly cancel and await the graph consumer and children;
9. on disconnect, follow the declared cancel-or-detach policy;
10. release every task, generator, registry lease, and session lock.

Do not use `agent.tool.name()` as the streaming boundary; direct tool calls
consume intermediate events and return only the final `ToolResult`.

## Normalized event envelope

Own a versioned, wire-safe discriminated union:

```text
protocol_version, event_id, cursor, timestamp
tenant_id, request_id, run_id, topology_hash
node_path, formation_kind, node_kind
attempt, sequence, event_type, provisional
payload, native_event_type, redaction
```

Recursively unwrap `multiagent_node_stream.event` while preserving the complete
path. Accept the source spelling `multiagent_*`, including node cancel and
interrupt. Derive formation kind from compiled topology, not native labels.

Reject or convert live objects, bytes, exceptions, provider events, Pydantic
objects, and result classes before transport. Large data becomes an authorized
artifact reference.

## Results failures and joins

Enforce one terminal state and one terminal tool result. Preserve:

- native `AgentResult`/`MultiAgentResult` status;
- all failed and interrupted node paths;
- recursively accumulated usage and metrics;
- execution counts and revisits;
- artifact references;
- topology and SDK versions.

Python fan-in is OR by default. Compile `join="all"` to explicit conditions on
every incoming edge. Provide `any`, `all`, and bounded `quorum` semantics.

Test raised Agent exceptions separately from nested executors that return
`Status.FAILED`. Native raised failures are fail-fast; an unconditional edge is
not an error edge.

## Limits security and privacy

Validate positive limits at compile time and enforce application-owned strict
budgets where native limits are only batch-boundary checks. Bound:

- expanded topology size and nesting depth;
- node executions, cycle iterations, and swarm handoffs;
- model tokens, cost, execution time, idle time, and node time;
- concurrent nodes, tools, package operations, and remote calls;
- queue bytes/events, event rate, output size, and artifact size.

Authorize every action and resource by tenant and principal. Require approvals
for high-impact side effects. Redact before events, logs, traces, and session
storage. Never send invocation state or secrets to the model or client.

## Compatibility and migration

At process start, record installed package versions and probe required symbols,
signatures, and emitted event shapes. Fail closed on unsupported versions.

Persist topology schema/hash, compiler version, Python and lock versions,
`strands-agents` and tools versions, event protocol version, and session
repository version.

An interrupt resume must rebuild an equivalent topology. Reject mismatches unless
a tested migration maps node IDs, state, interrupts, and cursors.

## Required deliverables

A complete implementation change includes:

- strict recursive schema and migrations;
- policy-aware compiler and factories;
- streaming `AgentTool`;
- normalized event types and transport adapter;
- durable topology/run/session registries;
- cancellation and cleanup;
- hooks, interrupts, resume, and observability;
- package metadata, extras, lockfile, and install commands;
- actual integration and UI acceptance evidence from the validation matrix;
- a written compatibility statement and known limitations.

Do not claim production readiness when a required integration depends on a mock,
stub, fake model, fake tool, or synthetic UI-only event.
