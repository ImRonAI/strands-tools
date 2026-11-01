# Skill agents and tool scoping

## Definitive use_skill implementation

Reference implementation: [`create_skill_agent_tool`](https://github.com/aws-samples/sample-strands-agents-agentskills/blob/c5564fcd2e7c249ec57b32027ffbea49e9abeb7b/agentskills/tool/agent_skill.py#L26-L123).

Current behavior:

1. Discover skills and build a name lookup.
2. Create a decorated async-generator `use_skill(skill_name, request)`.
3. Validate the selected skill name.
4. Load that skill's instructions.
5. Create a fresh isolated Agent.
6. Give it the model and `additional_tools` captured by the factory.
7. stream `sub_agent.stream_async(request)`;
8. wrap every sub-agent event with skill and Agent metadata;
9. yield a final result string.

The child Agent is isolated and does not inherit caller tools, messages, invocation state, or graph structure automatically.

## Skill-agent participation modes

Primary page: [Agents as Tools](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agents-as-tools/).

Support two distinct modes:

### Dynamic use_skill tool

Give an ordinary Agent node the `use_skill` tool when the model should choose a skill at runtime.

Path:

```text
Graph node Agent
  -> tool use_skill
    -> isolated skill Agent
      -> skill Agent events
```

Native stream nesting is:

```text
multiagent_node_stream
  -> Agent event
    -> tool_stream_event
      -> wrapped skill Agent event
```

The stream normalizer must recurse through both the graph-node and tool-stream layers.

### First-class skill_agent node

Compile a fixed skill as the node's actual Agent or as a custom `SkillAgentNode(MultiAgentBase)`. Use this when the topology explicitly names the skill and needs direct scheduling, path identity, limits, interrupts, usage, or results.

At build time:

1. resolve the skill from an allowlisted registry;
2. verify its metadata and path are trusted;
3. load instructions and record a content hash;
4. resolve an explicit model policy;
5. resolve an explicit capability policy;
6. construct a fresh skill Agent;
7. add it directly through `GraphBuilder.add_node`.

Use a custom `MultiAgentBase` only when lifecycle behavior exceeds a normal Agent—for example, late-bound skill resolution at invocation, custom state serialization, or specialized normalized events.

## Dynamic skill node design

An improved dynamic skill node should accept model-controlled intent only:

```text
skill_name
request
optional structured input allowed by the skill
```

Resolve all authority from trusted context:

- allowed skill names;
- skill source roots;
- model/provider;
- allowed tools;
- sandbox;
- resource and network policy;
- timeout and budgets;
- session/artifact access.

Do not let `allowed-tools` metadata or model input grant capabilities beyond the parent application's policy. Effective capabilities are the intersection:

```text
application policy
∩ tenant policy
∩ graph/node policy
∩ skill policy
∩ runtime availability
```

## Tool scoping

Tool scoping is deny-by-default:

1. each node declares capability names, not arbitrary import paths;
2. a trusted resolver maps names to registered `AgentTool` objects;
3. unknown or denied names fail compilation;
4. an omitted tool list means no tools unless an explicit policy profile says otherwise;
5. nested formations cannot broaden parent authority;
6. dynamic skill Agents receive a computed tool list for that invocation;
7. the compiled plan records tool names and policy decisions without secrets.

Never copy the entire parent Agent registry as a convenience default.

## Current graph-wrapper gaps

The current [`strands_tools.graph`](https://github.com/strands-agents/tools/blob/a762ed8be7d4bbfe2dcd021cfaa249042c754c2e/src/strands_tools/graph.py#L125-L275) is a useful baseline but not the target architecture:

- its topology creates an ordinary Agent for every node;
- its JSON schema cannot declare nested Graph, Swarm, workflow, batch, A2A, function, or first-class skill nodes;
- it invokes `graph(task)` synchronously and returns only summarized final text;
- it stores live graphs in a global manager;
- in the default-model branch it copies all parent tools and ignores a node's requested tool subset;
- conditional edges, joins, limits, hooks, sessions, interrupts, cancellation, and normalized async streaming are not expressed by its model-facing schema.

Preserve backwards compatibility only through a migration adapter. Do not preserve unsafe defaults.

## Dynamic tools and npm/package tools

If nodes can load tools or packages dynamically:

- resolve package/tool names against trusted registries;
- pin versions and verify hashes/signatures;
- install into a sandbox or per-run environment, never the host interpreter by default;
- record provenance and license;
- scan package metadata and install scripts;
- prohibit dependency changes from escalating node capabilities;
- cache only immutable verified artifacts;
- make installation progress streamable;
- include environment identity in the run record.

Template, npm, and dynamic-package tools are capabilities; they are not implicit privileges of every skill Agent.

## Skill stream and result requirements

The sample `use_skill` yields dictionaries containing the live Agent object. That object is not wire-safe and may expose internal state.

Normalize skill events to:

- skill name and content hash;
- skill-node path;
- child event type and safe payload;
- child tool/model attempt;
- usage and timing;
- interrupt/failure state.

Do not serialize:

- live Agent/model/tool objects;
- raw invocation state;
- secrets;
- arbitrary exception representations.

The final skill result remains typed inside the graph. Convert it to safe JSON only at the graph-tool boundary.

## Skill-agent validation checklist

- A dynamic `use_skill` Agent can select and run an allowed real skill.
- A first-class skill node is scheduled directly and contributes to downstream nodes.
- Both modes expose nested progress before final completion.
- The skill Agent receives exactly the computed tools and no parent-registry leakage.
- A denied tool and denied skill fail before execution.
- Two concurrent calls create isolated child Agents.
- Skill content hashes and tool/model policy appear in provenance.
- Nested skill interrupts and failures preserve full paths.
- Live Agent objects and invocation state never cross the wire.
- Package/template/npm capabilities run only in their declared sandbox.
