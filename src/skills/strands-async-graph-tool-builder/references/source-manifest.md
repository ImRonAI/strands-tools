# Primary-source manifest

## Snapshot policy

This reference set was assembled on 2026-07-26 and revalidated on 2026-07-30.
Treat published documentation as the behavioral guide, but verify every
implementation-sensitive claim against the pinned source before changing code.
The documentation and code are developed in the same monorepo and can drift
between releases.

At the time of inspection, the latest Python release was
[`python/v1.50.2`](https://github.com/strands-agents/sdk-python/releases/tag/python/v1.50.2)
at `fa63da5d1fb10da4710947789799f212546e23ac`. The current Python SDK `main`
commit inspected on 2026-07-30 was
`f4a8f9f50803682e6078624153dcff14818bc120`. The installed package version
remains the authority.

The current Tools release was
[`v0.8.5`](https://github.com/strands-agents/tools/releases/tag/v0.8.5) at
`a762ed8be7d4bbfe2dcd021cfaa249042c754c2e`; the current `main` commit inspected
on 2026-07-30 was `60b63901e5640f0176a8eb25352ac730765fd8ce`.

Trust sources in this order:

1. the installed `strands-agents` and `strands-agents-tools` versions in the target environment;
2. the matching release tag or commit in the Python SDK and Tools repositories;
3. the current official documentation;
4. examples and community integrations.

Never silently substitute TypeScript behavior for Python behavior. The graph join, timeout, streaming, and event APIs differ.

## Pinned repositories

| Repository | Commit inspected | Purpose |
|---|---|---|
| [`strands-agents/sdk-python`](https://github.com/strands-agents/sdk-python/tree/fa63da5d1fb10da4710947789799f212546e23ac) | `fa63da5d1fb10da4710947789799f212546e23ac` | Python SDK, documentation source, graph/swarm runtime, hooks, events, sessions, tools |
| [`strands-agents/tools`](https://github.com/strands-agents/tools/tree/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e) | `a762ed8be7d4bbfe2dcd021cfaa249042c754c2e` | Model-facing `graph`, `workflow`, `batch`, `swarm`, and `use_agent` tools |
| [`strands-agents/samples`](https://github.com/strands-agents/samples/tree/04b9f0263b2957ddb307c5aaedc4dfb59f031311) | `04b9f0263b2957ddb307c5aaedc4dfb59f031311` | Current official Agent Skills sample |
| [`aws-samples/sample-strands-agents-agentskills`](https://github.com/aws-samples/sample-strands-agents-agentskills/tree/c5564fcd2e7c249ec57b32027ffbea49e9abeb7b) | `c5564fcd2e7c249ec57b32027ffbea49e9abeb7b` | `create_skill_agent_tool` / `use_skill` reference implementation |
| [`strands-agents/docs`](https://github.com/strands-agents/docs/tree/658b6f05a2d4cbe8e1b8ffc860915c8dafc6b654) | `658b6f05a2d4cbe8e1b8ffc860915c8dafc6b654` | Archived documentation repository; current documentation lives in `sdk-python/site/` |

The historical GitHub `harness-sdk` URLs redirect to the current `sdk-python`
repository. Before re-anchoring these references, the relevant graph, swarm,
hook, type, tool-decorator, and session paths were diffed between the old
snapshot and `python/v1.50.2`; they were unchanged.

## Official documentation pulled

Each page below is represented in this skill's curated reference files. The linked heading is the primary section used.

| Official document | Headings used | Local reference |
|---|---|---|
| [Creating Custom Tools](https://strandsagents.com/docs/user-guide/concepts/tools/custom-tools/) | `Async Invocation`, `ToolContext`, `Accessing State in Tools`, `Tool Streaming`, `Tool Response Format` | [Custom tools](custom-tools-and-tool-streaming.md#official-document-creating-custom-tools) |
| [Tools Overview](https://strandsagents.com/docs/user-guide/concepts/tools/) | `Direct Method Calls`, `Tool Executors`, `Building & Loading Tools`, `Agents as Tools` | [Tool execution choices](custom-tools-and-tool-streaming.md#tool-execution-choices) |
| [Streaming Events](https://strandsagents.com/docs/user-guide/concepts/streaming/) | `Event Types`, `Tool Events`, `Multi-Agent Events`, `Event Serialization`, `Sub-Agent Streaming Example` | [Native event families](stream-event-contracts.md#native-event-families) |
| [Async Iterators for Streaming](https://strandsagents.com/docs/user-guide/concepts/streaming/async-iterators/) | `Basic Usage`, `Server examples`, `Agentic Loop` | [Async iterator contract](stream-event-contracts.md#async-iterator-contract) |
| [Graph Multi-Agent Pattern](https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/) | `Graph Components`, `Conditional Edges with Runtime Context`, `Waiting for All Dependencies`, `Nested Multi-Agent Patterns`, `Custom Node Types`, `Streaming Events`, `Common Graph Topologies` | [Native graph contract](graph-and-nested-formations.md#native-graph-contract) |
| [Swarm Multi-Agent Pattern](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/) | `Swarm Configuration`, `Shared State`, `Streaming Events`, `Safety Mechanisms` | [Swarm contract and limits](graph-and-nested-formations.md#swarm-contract-and-limits) |
| [Multi-agent Patterns](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/) | `Difference in Graph, Swarm and Workflow`, `When to Use Each Pattern`, `Shared State Across Multi-Agent Patterns` | [Formation selection](graph-and-nested-formations.md#formation-selection) |
| [Agent Workflows](https://strandsagents.com/docs/user-guide/concepts/multi-agent/workflow/) | `Quick Start with the Workflow Tool`, `Key Parameters and Features`, `Context Passing Between Tasks` | [Workflow compilation](graph-and-nested-formations.md#workflow-compilation) |
| [Agents as Tools](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agents-as-tools/) | `The Concept`, `Implementing Agents as Tools` | [Skill-agent participation modes](skill-agents-and-tool-scoping.md#skill-agent-participation-modes) |
| [Hooks](https://strandsagents.com/docs/user-guide/concepts/agents/hooks/) | `Multi-Agent Lifecycle`, `Available Events`, `Event Properties`, `Callback Ordering`, `Accessing Invocation State in Hooks`, `HookProvider Protocol` | [Hook lifecycle](hooks-interrupts-sessions.md#hook-lifecycle) |
| [Interrupts](https://strandsagents.com/docs/user-guide/concepts/interrupts/) | `Graph`, `Components`, `Rules` | [Interrupt and resume contract](hooks-interrupts-sessions.md#interrupt-and-resume-contract) |
| [Session Management](https://strandsagents.com/docs/user-guide/concepts/agents/session-management/) | `Multi-Agent Sessions`, `Session Persistence Triggers`, `Data Models`, `Session Persistence Best Practices` | [Session and crash-resume contract](hooks-interrupts-sessions.md#session-and-crash-resume-contract) |
| [State Management](https://strandsagents.com/docs/user-guide/concepts/agents/state/) | `Using State in Tools`, `Invocation State`, `Persisting State Across Sessions` | [Invocation state](hooks-interrupts-sessions.md#invocation-state) |
| [Agent-to-Agent Protocol](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agent-to-agent/) | `Installation`, `Consuming Remote Agents`, `A2AAgent in Multi-Agent Patterns` | [Remote A2A nodes](graph-and-nested-formations.md#remote-a2a-nodes) |

## Definitive source map

Use these permalinks to validate signatures and behavior:

- [`MultiAgentBase`, `NodeResult`, `MultiAgentResult`, and `Status`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/base.py#L26-L315)
- [`GraphNode.executor` and `GraphBuilder.add_node`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L223-L333)
- [`GraphBuilder` limits, hooks, plugins, sessions, and build`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L335-L479)
- [`Graph.stream_async`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L594-L705)
- [Graph ready-node parallel stream merge](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L759-L940)
- [Nested `AgentBase` / `MultiAgentBase` streaming](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L976-L1143)
- [Graph state serialization and resume](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/graph.py#L1239-L1317)
- [`Swarm` accepts `list[Agent]`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/swarm.py#L237-L316)
- [Swarm validation and coordination-tool injection](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/multiagent/swarm.py#L488-L570)
- [`DecoratedFunctionTool.stream`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/tools/decorator.py#L586-L700)
- [`AgentTool`, `ToolContext`, `ToolUse`, and `ToolResult`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/tools.py#L23-L287)
- [Tool and multi-agent event classes](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/types/_events.py#L282-L616)
- [Hook event dataclasses](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/hooks/events.py#L26-L418)
- [`HookProvider` and `HookRegistry`](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/hooks/registry.py#L48-L340)
- [Session lifecycle hooks](https://github.com/strands-agents/sdk-python/blob/fa63da5d1fb10da4710947789799f212546e23ac/strands-py/src/strands/session/session_manager.py#L31-L129)
- [Current model-facing graph wrapper](https://github.com/strands-agents/tools/blob/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e/src/strands_tools/graph.py#L125-L275)
- [Current `batch` implementation](https://github.com/strands-agents/tools/blob/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e/src/strands_tools/batch.py#L65-L173)
- [Current workflow parallel scheduler](https://github.com/strands-agents/tools/blob/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e/src/strands_tools/workflow.py#L560-L709)
- [Current `create_skill_agent_tool` implementation](https://github.com/aws-samples/sample-strands-agents-agentskills/blob/c5564fcd2e7c249ec57b32027ffbea49e9abeb7b/agentskills/tool/agent_skill.py#L26-L162)

## Known documentation and source traps

1. Python graph joins use OR semantics by default. A visual fan-in is not an AND barrier unless each incoming edge has an all-dependencies condition.
2. A nested `Graph` or `Swarm` is valid through native `GraphBuilder.add_node`, but the current `strands_tools.graph` topology schema constructs only ordinary `Agent` nodes.
3. A Python `Swarm` contains only `Agent` members. Put the Swarm inside a Graph to nest formations.
4. The current `batch` tool describes simultaneous execution but loops over invocations sequentially.
5. The current workflow tool uses a thread pool and runs ready tasks in parallel, but it is a decorated tool/manager, not a `MultiAgentBase` structural graph node and it does not expose the native graph stream contract.
6. The current `use_skill` factory captures a fixed `additional_tools` list and creates an isolated Agent per call. It does not inherit caller tools or automatically become a structural node.
7. `Graph` and its Agents hold mutable run state. A registry should store validated specifications or factories, not reuse one live Graph instance across concurrent runs.
8. The Python graph's ready-node merger uses an unbounded `asyncio.Queue`. Do not claim end-to-end backpressure without either bounding that queue in a compatible implementation or proving the deployment's event rate and buffering limits.
9. Parallel Graph nodes receive the same mutable invocation-state dictionary. Prove isolation under real concurrency or give each branch an application-owned child view before allowing tools to rely on mutable framework keys.
10. `Graph` has no public cancellation method. Cancelling an outer Agent is not proof that a currently running nested graph tool and all child tasks stopped.
11. `max_node_executions` and total execution timeout are checked between ready-node batches. They are not strict in-flight batch cancellation limits.
12. Native Graph failures raised by an Agent are fail-fast. Do not advertise arbitrary “error edges” unless the implementation converts failures to an explicitly routed result contract.
13. Remote A2A `input_required` and `auth_required` do not currently map cleanly to local Graph interrupt responses. Feature-gate that resume path until it has real integration proof.
