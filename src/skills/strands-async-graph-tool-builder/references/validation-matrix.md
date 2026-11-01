# Production validation matrix

## Proof standard

Schema and pure-function unit tests are useful, but they are not acceptance
proof. Every advertised runtime behavior must also be exercised through the
actual installed Strands SDK, real executor objects, actual tool dependencies,
the deployed transport, and the visible UI.

Do not replace required integration coverage with mocks, stubs, fake agents,
fake streams, or hand-authored browser events. If credentials or infrastructure
are unavailable, report that proof as blocked rather than manufacturing it.

Pin the tested package versions, commands, environment, model provider, session
backend, transport, browser, and commit.

## Contract and compatibility checks

Before implementation and on every supported SDK upgrade:

1. Inspect the installed package version and module paths.
2. Verify `AgentTool.stream`, `ToolContext`, `ToolResultEvent`,
   `GraphBuilder.add_node`, `Graph.stream_async`, `Swarm`, hooks, interrupts,
   and session signatures.
3. Verify actual emitted `multiagent_*` event dictionaries.
4. Verify the outer `Agent.stream_async` terminal behavior and tool-result
   message behavior.
5. Fail dependency resolution or the installed-SDK contract test suite on
   missing or incompatible contracts.

Record both the installed version and the matching source tag or commit.

## Graph formation acceptance

Run actual model-backed cases:

| Case | Required proof |
|---|---|
| Agent node | model invokes the registered graph tool and completes a real node |
| nested Graph | parent and child paths stream, results and usage aggregate |
| nested Swarm | handoffs stream and the Swarm remains an Agent-only leaf |
| workflow | dependency order and explicit all-joins are correct |
| parallel | two slow real I/O branches overlap and visibly interleave |
| tool batch | bounded concurrent real tool calls, stable item correlation, partial failure policy |
| skill agent | real skill files activate and the skill Agent contributes as a graph node |
| dynamic skill tool | scoped child Agent streams through `Agent.as_tool()` or the production equivalent |
| A2A | actual authenticated endpoint; otherwise the feature remains gated |

Include at least one Graph -> Graph -> Swarm -> skill-enabled Agent topology.

## Joins cycles and failures

Prove:

- `any` runs after the first accepted incoming edge;
- `all` waits for every declared dependency;
- quorum uses the declared threshold;
- cycles exit on their condition;
- cycles stop under positive execution and time limits;
- a parallel batch can exceed native boundary limits and the application strict
  budget handles the difference;
- raised Agent errors fail fast and cancel siblings cleanly;
- returned `Status.FAILED` is represented distinctly;
- downstream error routing exists only when explicitly implemented.

Do not assert deterministic event or execution order among parallel siblings.

## Tool capability and dependency acceptance

For each node kind:

1. inspect the exact tool registry and JSON schemas;
2. invoke an allowed tool through a real model decision;
3. attempt a denied tool and prove it is absent or blocked;
4. exercise argument-level authorization in hooks;
5. verify no parent-tool leakage;
6. run actual shell, filesystem, browser, package, npm, template, dynamic-tool,
   network, and secrets capabilities only in their authorized sandboxes;
7. install optional dependencies from a clean environment using the documented
   extras and commands.

Test dependency failure, version conflict, missing executable, missing browser,
and missing credential errors with actionable messages.

## Async streaming acceptance

Capture the complete actual stream and prove:

- progress arrives before completion;
- ready branches interleave under real latency;
- nested paths and attempts remain attributable;
- source `multiagent_*` events, cancel, and interrupt are handled;
- only one terminal result is accepted;
- the outer Agent's internal `ToolResultEvent` is not falsely advertised as a
  callback event;
- tool/model retries mark discarded attempts as provisional;
- every wire payload is JSON-safe and redacted;
- large content becomes an artifact reference;
- usage totals match recursive results.

Exercise a slow real client. Observe queue depth, coalescing, event rate, memory,
and lag. A bounded outer queue is not proof of native end-to-end backpressure.

## Invocation state race acceptance

Run two parallel real Agents. Give each a context-aware tool that records:

- `ToolContext.agent.name`;
- request, tenant, and run IDs;
- trace/span correlation;
- branch-local state;
- the identity/version of its invocation-state view.

Prove there is no cross-branch contamination across repeated concurrent runs.
The current native Graph passes one mutable dictionary to siblings, so this test
must fail closed until the application provides a safe strategy.

## Interrupt session and restart acceptance

With a real session repository:

1. trigger a before-node hook interrupt while another branch runs;
2. persist and stop the process;
3. recreate registry, session manager, topology, Agents, and Graph;
4. supply the same trusted invocation context;
5. resume with the exact authorized interrupt ID;
6. prove completed siblings do not run twice;
7. trigger a tool-origin interrupt inside a nested formation;
8. reject unknown, replayed, cross-tenant, and topology-mismatched responses;
9. repeat with multiple concurrent interrupts.

Run File and production session backends when both are supported. Lock concurrent
access to one session and prove the lock under load.

## Cancellation timeout and cleanup acceptance

Cancel during:

- child model streaming;
- a long async child tool;
- a nested Graph;
- a Swarm handoff;
- a full application event queue;
- client disconnect.

Prove bounded termination, closed generators, awaited tasks, no orphan work,
released session locks, one durable terminal state, and no post-terminal events.
Test explicit cancel, node timeout, total timeout, idle timeout, and disconnect
as distinct reasons.

## Observability and privacy acceptance

Send actual telemetry to a real OTLP Collector. Verify:

- graph, node, Agent, model, and tool span relationships;
- run/topology/node/tool correlation;
- retries, interrupts, queue lag, cancellation, and errors;
- usage and latency;
- redaction of prompts, arguments, outputs, credentials, and invocation state;
- no cross-tenant log, trace, event, session, or artifact access.

Do not assume SDK tracing is redacted by default.

## UI Playwright acceptance

Start the actual backend and frontend, then use Playwright against the visible
application. In one coherent browser flow:

1. submit a nested topology;
2. observe node and formation hierarchy plus live interleaving;
3. inspect skill-agent and tool progress;
4. answer a real interrupt;
5. disconnect and reconnect with a cursor;
6. verify event deduplication and no missing terminal state;
7. cancel a running nested formation;
8. inspect failed and retried attempts;
9. verify unauthorized topology or run access is rejected.

Save screenshots, trace, browser console, network evidence, backend logs, and
run IDs. Browser assertions against injected or static fixture events do not
satisfy this matrix.

## Release evidence

The handoff must distinguish:

- source inspection complete;
- schema/compiler checks complete;
- local actual-SDK integration complete;
- actual provider/tool integration complete;
- persistence/restart complete;
- transport load proof complete;
- Playwright UI acceptance complete;
- CI complete;
- production environment proof complete.

List blocked proof explicitly. Do not collapse partial evidence into “done.”
