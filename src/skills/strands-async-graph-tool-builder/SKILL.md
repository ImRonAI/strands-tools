---
name: strands-async-graph-tool-builder
description: Build, redesign, audit, or extend production Strands Agents Python graph tools with nested Graph, Swarm, workflow, parallel, batch, skill-agent, and A2A nodes; strict tool scoping; hooks, interrupts, sessions, cancellation; and real asynchronous streaming to a UI. Use whenever implementing or reviewing a Strands orchestration or graph tool, especially when nested formations or dynamic skill subagents must participate as nodes.
compatibility: Python 3.10+; validate against the installed strands-agents and strands-agents-tools versions.
---

# Strands async graph tool builder

Build against the installed Python SDK and native contracts. Treat this skill as
an ordered implementation and proof gate, not a design suggestion.

## 0. Establish the proof bar

Before changing code, state:

- the requested runtime behavior and user-visible outcome;
- the target repository, branch, package, application, and transport;
- which production model, tools, sessions, services, and UI are available;
- which claims require actual integration or Playwright proof;
- which constraints are currently blocked.

Read the [proof standard](references/validation-matrix.md#proof-standard).
Never substitute mocks, stubs, fake agents, synthetic streams, or injected UI
events for advertised runtime behavior.

## 1. Inspect the exact environment

Read repository instructions and preserve unrelated changes. Inspect:

- installed `strands-agents` and tools versions;
- dependency metadata, lockfiles, imports, and Python version;
- graph, workflow, swarm, batch, `use_agent`, skill, package/npm, template,
  shell, filesystem, browser, and dynamic-tool implementations;
- actual backend transport and frontend stream consumer;
- session repository, run registry, hooks, telemetry, and security boundaries.

Use Context7 for current Strands documentation, then compare installed source
with the [snapshot policy](references/source-manifest.md#snapshot-policy) and
[definitive source map](references/source-manifest.md#definitive-source-map).
Do not copy a current-main signature into an older installed release.

## 2. Inventory behavior and gaps

Trace one request from outer Agent tool selection through topology handling,
executor construction, node streams, result delivery, persistence, and the UI.

Write a gap table covering node/edge kinds, native versus wrapper behavior, sync
versus async paths, capabilities, joins, cycles, limits, retries, failures,
hooks, interrupts, cancellation, sessions, restart, serialization, backpressure,
replay, terminal states, tenants, secrets, and side effects.

Compare with the
[known source traps](references/source-manifest.md#known-documentation-and-source-traps)
and [current graph-wrapper gaps](references/skill-agents-and-tool-scoping.md#current-graph-wrapper-gaps).

## 3. Define trust and policy first

Separate model-controlled topology input from trusted application policy.
Declare:

- tenant and principal ownership;
- model and tool allowlists;
- skill, package/npm, template, shell, filesystem, browser, network, secrets,
  A2A, and deployment grants;
- approval-required side effects;
- concurrency, token, cost, time, output, event, and artifact budgets;
- redaction, audit, session, retention, and replay policies.

Use hooks for call-time enforcement; a system prompt is not authorization. Follow
[policy hooks](references/hooks-interrupts-sessions.md#policy-hooks) and
[tool scoping](references/skill-agents-and-tool-scoping.md#tool-scoping).

## 4. Specify a recursive topology

Define a strict, versioned, discriminated recursive node union for Agent, Graph,
Swarm, workflow, parallel, tool batch, skill Agent, A2A, and trusted registered
executors. Define typed edges, input mappings, joins, conditions, limits, and
outputs.

Use the [recursive topology schema](references/implementation-blueprint.md#recursive-topology-schema)
and [recursive node specification](references/graph-and-nested-formations.md#recursive-node-specification).

Reject unknown fields, arbitrary Python/imports/callables, model-supplied
credentials and paths, unbounded nesting, missing budgets, duplicate IDs,
invalid Swarm members, unsafe cycles, nonpositive limits, and topology-hash
mismatches.

## 5. Compile formations recursively

Implement a pure validation/compiler stage before execution:

1. parse and migrate schema;
2. authorize and resolve registry references;
3. validate topology and budgets;
4. resolve models and exact tool sets;
5. calculate a canonical topology hash;
6. recursively construct factories;
7. instantiate a fresh executor tree for the run;
8. attach policies, hooks, sessions, and trace attributes;
9. inspect the built tree before calls begin.

Follow the [compiler pipeline](references/implementation-blueprint.md#compiler-pipeline)
and [node compilers](references/implementation-blueprint.md#node-compilers).

Use native Graph as the structural composition root. Nested Graph and Swarm are
already valid Graph nodes. Swarm members must be fresh local Agents. Compile
workflow and parallel into nested Graphs. Implement batch as bounded real async
work or expanded nodes; do not reuse a sequential batch loop.

## 6. Make skill agents first-class

Support both explicit modes:

- a `skill_agent` node that participates in routing, hooks, results,
  persistence, and nested streaming;
- a dynamic skill tool using a scoped child Agent through native
  `Agent.as_tool()` or a production custom equivalent.

Read [skill-agent participation modes](references/skill-agents-and-tool-scoping.md#skill-agent-participation-modes),
[dynamic skill node design](references/skill-agents-and-tool-scoping.md#dynamic-skill-node-design),
and [tool and skill policy](references/implementation-blueprint.md#tool-and-skill-policy).

Current `AgentSkills` activates instructions on the same Agent; the older
`use_skill` sample spawns a child. Declare which behavior each node uses. Never
implicitly give a child every parent tool.

## 7. Implement explicit joins conditions and failures

Python Graph fan-in is OR by default. Compile all-joins to explicit conditions on
every incoming edge. Use a safe expression language for other conditions.

Follow [Python join semantics](references/graph-and-nested-formations.md#python-join-semantics),
[conditional edges and cycles](references/graph-and-nested-formations.md#conditional-edges-and-cycles),
and [results failures and joins](references/implementation-blueprint.md#results-failures-and-joins).

Treat raised Agent errors, returned `Status.FAILED`, cancellation, timeout, and
interrupt as distinct states. Do not describe an edge as an error edge unless
the implementation explicitly routes a typed failure result.

## 8. Build a run-scoped runtime

Persist immutable topology versions and factories, not live Graphs. Create a
fresh object tree and trusted invocation state per run. Own live tasks in an
injected tenant-aware registry with cancellation, session locking, bounded event
buffers, durable cursors, and cleanup.

Use the [runtime factory and registry](references/implementation-blueprint.md#runtime-factory-and-registry)
and [registry and lifecycle](references/hooks-interrupts-sessions.md#registry-and-lifecycle).

Native siblings share a mutable invocation-state dictionary. Do not assume
parallel context isolation; implement a safe strategy and run the
[invocation state race acceptance](references/validation-matrix.md#invocation-state-race-acceptance).

## 9. Expose a true streaming AgentTool

Implement a concrete `AgentTool.stream` async generator. Continuously consume
`Graph.stream_async`, normalize events, persist accepted cursors, yield
intermediate `ToolStreamEvent`s, and emit one final `ToolResultEvent`.

Read the [low-level AgentTool contract](references/custom-tools-and-tool-streaming.md#low-level-agenttool-contract),
[streaming GraphTool](references/implementation-blueprint.md#streaming-graphtool),
and [terminal invariants](references/stream-event-contracts.md#terminal-invariants).

Do not use direct `agent.tool.name()` as the streaming boundary. Do not assume
the internal `ToolResultEvent` is yielded by the enclosing
`Agent.stream_async`; follow [tool events](references/stream-event-contracts.md#tool-events).

## 10. Normalize nested events for transport

Own a versioned JSON-safe event union with event ID, cursor, run/topology IDs,
node path, formation kind, attempt, sequence, provisional flag, redaction
metadata, and payload.

Recursively unwrap `multiagent_node_stream.event`, preserve source meaning, and
support cancel and interrupt events. Derive formation labels from compiled
topology, not unreliable native labels.

Follow [normalized event envelope](references/implementation-blueprint.md#normalized-event-envelope),
[nested stream paths](references/stream-event-contracts.md#nested-stream-paths),
[event serialization](references/stream-event-contracts.md#event-serialization),
and [retry-aware streaming](references/stream-event-contracts.md#retry-aware-streaming).

## 11. Enforce backpressure and cancellation honestly

Bound every application-owned queue, define event-class overflow behavior, and
measure queue depth and lag. The native Graph merger is unbounded, so a bounded
outer queue is not strict end-to-end backpressure.

On cancellation or disconnect, cancel the graph-consumer task, close nested
generators, cancel and await child tasks, persist one terminal state, and release
locks. Outer `Agent.cancel()` alone is insufficient proof.

Use [backpressure and queue policy](references/stream-event-contracts.md#backpressure-and-queue-policy),
[cancellation and disconnects](references/stream-event-contracts.md#cancellation-and-disconnects),
and [cancellation timeout and cleanup acceptance](references/validation-matrix.md#cancellation-timeout-and-cleanup-acceptance).

## 12. Integrate hooks interrupts sessions and resume

Attach policies and telemetry at Graph/Swarm and inner Agent/tool/model layers.
Use explicit hook ordering. Persist interrupt state before returning control.

Read [hook lifecycle](references/hooks-interrupts-sessions.md#hook-lifecycle),
[interrupt and resume contract](references/hooks-interrupts-sessions.md#interrupt-and-resume-contract),
[nested interrupts](references/hooks-interrupts-sessions.md#nested-interrupts),
and [session and crash-resume contract](references/hooks-interrupts-sessions.md#session-and-crash-resume-contract).

Rebuild the exact topology and rehydrate trusted invocation state after restart.
Feature-gate A2A interrupt/resume until an actual endpoint proves it.

## 13. Package and document installation

Declare core and optional dependency groups for every advertised node/tool type.
Provide clean-environment install commands, supported version bounds, external
executables, browser/runtime installs, credentials, platform requirements, and
service setup.

Record compiler, event schema, topology schema, SDK, tools, and dependency-lock
versions. Follow [compatibility and migration](references/implementation-blueprint.md#compatibility-and-migration)
and [production readiness checklist](references/custom-tools-and-tool-streaming.md#production-readiness-checklist).

## 14. Validate the actual feature and UI

Run the [contract and compatibility checks](references/validation-matrix.md#contract-and-compatibility-checks),
[graph formation acceptance](references/validation-matrix.md#graph-formation-acceptance),
[async streaming acceptance](references/validation-matrix.md#async-streaming-acceptance),
[interrupt session and restart acceptance](references/validation-matrix.md#interrupt-session-and-restart-acceptance),
and [UI Playwright acceptance](references/validation-matrix.md#ui-playwright-acceptance).

Use the real installed SDK, configured model, actual tools and services, real
session repository, deployed transport, and visible application. Capture proof.
If something cannot be run, label it blocked.

## 15. Report without overclaiming

Lead with the implemented outcome. Include:

- exact files and architecture;
- supported node kinds and safety policies;
- dependencies and install commands;
- actual commands and proof artifacts;
- installed versions and source pins;
- completed, partial, blocked, and untested proof;
- known native limitations and application mitigations.

Use the [release evidence](references/validation-matrix.md#release-evidence).
Never call the graph production-ready while required actual integration,
restart, cancellation, load, or Playwright proof remains missing.
