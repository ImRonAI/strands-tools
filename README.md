# Heterogeneous Strands graph tool

`strands-heterogeneous-graph-tool` exposes one model-facing Strands `AgentTool`, named `graph`. It compiles strict JSON formations into fresh native Strands `Graph`, `Swarm`, and concrete `Agent` executors for every run.

One formation can mix:

- regular Agent nodes;
- first-class isolated `skill_agent` nodes;
- regular Agents with `AgentSkills` through `skills`;
- regular or skill-enabled Agents with an isolated `use_skill` child-agent tool through `dynamic_skills`;
- Swarms containing concrete regular and skill-enabled Agents;
- recursively nested Graphs;
- bounded concurrent registered-tool batches and trusted registered executors.

The tool also owns validation, immutable graph registration, execution, event streaming, status, interruption resume, cancellation, and deletion. It does not implement or select a model provider.

## Model inheritance

`model` is optional on every formation node. When omitted, the node receives the exact model instance of the Agent that invoked `graph`; nested nodes inherit the nearest explicitly selected ancestor model. No provider setting or model registry is required for the normal case.

Applications may register explicit model overrides under trusted IDs when a node genuinely needs a different model. Model-facing JSON can refer only to those IDs—it cannot supply provider classes, import paths, credentials, or arbitrary constructor arguments.

## Install and verify

```bash
uv sync --extra test
uv run pytest -q
uvx ruff check src/strands_graph_tool tests
uvx pyright --pythonpath .venv/bin/python
```

The package requires Python 3.10+ and `strands-agents>=1.50.2,<2`. The current
checkout is verified with Python 3.14.5 and Strands Agents 1.50.2. The upper
bound prevents an untested major SDK upgrade; the real contract checks live in
the compiler/runtime tests rather than a duplicate runtime introspection layer.

## Application setup

The application—not the model—registers resources and grants capabilities:

```python
from pathlib import Path

from strands import Agent
from strands_graph_tool import (
    GraphRuntime,
    GraphTool,
    PolicyStore,
    PrincipalGrant,
    RegistryBundle,
    SqliteGraphStore,
)

registries = RegistryBundle()
registries.register_skill(
    "github-research",
    Path("skills/github-research"),
    version="2026-07-26",
)

policies = PolicyStore()
policies.put(
    PrincipalGrant(
        tenant_id="acme",
        principal_id="user-42",
        actions=frozenset(
            {"validate", "register", "run", "resume", "status", "cancel", "delete"}
        ),
        skills=frozenset({"github-research"}),
        registered_graphs=frozenset({"delivery"}),
        allow_inline_formations=True,
    )
)

store = SqliteGraphStore(".graph-tool/state.sqlite3")
runtime = GraphRuntime(store=store, sessions_dir=".graph-tool/sessions")
graph = GraphTool(
    registries=registries,
    policies=policies,
    store=store,
    runtime=runtime,
    default_graphs={"acme": "delivery"},
)

parent = Agent(tools=[graph])
result = parent(
    "Use the graph tool to research and verify this change.",
    invocation_state={
        "strands_graph_tool.tenant_id": "acme",
        "strands_graph_tool.principal_id": "user-42",
        "strands_graph_tool.request_id": "request-123",
    },
)
```

The Strands tool executor injects the calling `agent` and `model` into the tool invocation state. Tenant and principal values must come from trusted application context; never copy them from model output.

Tool and model registrations are factories because every run builds a fresh executor tree. A skill registration accepts a real Strands `Skill`, a `SKILL.md` path, or a skill directory and records a content hash in topology provenance.

## Model-facing request

`action` defaults to `run`. If the tenant has a configured default graph, the smallest request is:

```json
{
  "task": "Research, design, implement, and verify the feature."
}
```

An inline heterogeneous formation can look like:

```json
{
  "task": "Research, design, implement, and verify the feature.",
  "formation": {
    "type": "graph",
    "nodes": [
      {
        "id": "planner",
        "type": "agent",
        "goal": "Create the execution plan"
      },
      {
        "id": "github_researcher",
        "type": "skill_agent",
        "skills": ["github-research"],
        "goal": "Inspect upstream implementations"
      },
      {
        "id": "coder",
        "type": "agent",
        "goal": "Implement the verified design",
        "dynamic_skills": ["github-research"],
        "depends_on": ["planner", "github_researcher"]
      }
    ]
  }
}
```

Supported actions are `run`, `validate`, `register`, `resume`, `status`, `cancel`, and `delete`. Unknown fields fail validation. Invalid requests return one structured, repairable tool error instead of partial execution.

Compact lifecycle calls stay within the same tool:

```json
{"graph": "delivery", "task": "Run the registered delivery graph."}
```

```json
{"action": "status", "run_id": "run_123", "cursor": 42}
```

When `cursor` is present, `status` includes persisted events after that cursor, up to `event_limit` (maximum 1,000). This is the tool-level reconnect/replay contract.

```json
{"action": "cancel", "run_id": "run_123"}
```

```json
{
  "action": "resume",
  "run_id": "run_123",
  "responses": [{"interrupt_id": "interrupt_456", "response": "approve"}]
}
```

## Execution guarantees

- Dependencies become explicit native Graph edges. Fan-in defaults to `all`; `any` and `quorum` joins are supported.
- Registries, tenant grants, capability profiles, and per-call tool argument authorizers are enforced before compilation. Model and tool access is reauthorized at call time so revocation takes effect during a run.
- SQLite WAL storage owns immutable topologies, run state, interrupt responses, monotonic event cursors, replay, and cross-process cancellation flags.
- Every run builds new Agents, AgentSkills plugins, dynamic child Agents, Graphs, Swarms, hooks, and sessions. No mutable executor tree is shared between runs.
- Each Graph's `limits.max_concurrency` bounds its direct nodes. Nested Graphs enforce their own declared limit, matching Strands' native nested-orchestrator boundary. Per-node deadlines cover Agents, tool batches, A2A nodes, and registered executors; nested Graph and Swarm deadlines use their native formation limits.
- Token limits are passed to native Agents. Cost limits require a priced explicit model registration. Event-count and serialized-output limits are charged to the producing node and each containing formation.
- Runs sharing one tenant/session ID within one `GraphRuntime` process serialize access to the File session manager. `session: "inherit"` keeps dynamic skill-child sessions durable; `session: "ephemeral"` gives those children no session manager. A multi-process deployment must provide an application-owned distributed session lease.
- Normalized event envelopes preserve nested node paths, native event meaning, provenance, redaction counts, and one terminal event. Oversized payloads can be moved to `LocalArtifactStore`.
- A2A nodes can use only application-registered endpoint factories. Remote interrupt forwarding is intentionally disabled until it can preserve the same durable resume contract.

## Source layout

This remains one public tool, split along failure and ownership boundaries:

- `schema.py` and `normalize.py`: strict input and deterministic shorthand expansion;
- `registry.py`, `policy.py`, and `compiler.py`: trusted resources, authorization, and native executor construction;
- `execution.py`, `events.py`, `store.py`, and `runtime.py`: the deterministic async tool-batch executor, policy hooks, dynamic skill subagents, event normalization, durability, cancellation, and resume;
- `tool.py`: the single `GraphTool` boundary presented to a parent Agent.

There is no provider layer, HTTP service, CLI, UI, or alternate orchestration framework in this package.

## Verification boundary

The local suite uses real Strands executors, SQLite/File session persistence, real loopback TCP tool I/O, bounded concurrency, cancellation, budget failure, timeout classification, and approval resume after recreating the runtime. It also proves the heterogeneous native Graph/Swarm/Agent/AgentSkills structure and exact parent-model identity.

This repository does not contain a backend transport or visible graph UI, and this environment has no configured model-provider credentials. Live provider execution, dynamic skill-agent model turns, A2A transport, and Playwright UI acceptance are therefore not claimed here. Those checks must run in the integrating application with its real provider, backend stream, and visible UI.

## Strands tools inventory

This directory contains the source-backed inventory of Strands Agent repositories and their usable tools, providers, loaders, session integrations, and skills. The research snapshot is dated **2026-07-26**.

The curated, non-redundant architecture derived from this inventory is in [SUPER_AGENT_TOOL_SELECTION.md](SUPER_AGENT_TOOL_SELECTION.md).

## Inventory summary

The original seven repository groupings were preserved exactly. Together they cover **81 repository entries** and **552 detailed inventory rows**. A row may group closely related exported entrypoints, so the row total is not a claim that only 552 concrete tool names exist; every concrete name found in a grouped row is listed in that row.

| Grouping | Repositories | Inventory rows | Detailed report | Coverage |
|---|---:|---:|---|---|
| Official Strands repositories | 12 | 70 | [01-official-strands.md](research/01-official-strands.md) | Official SDK and tools package, shell, SOP, evaluations, MCP server, developer tools, templates, samples, and three archived repositories retained for status accounting |
| Core collections and integrations | 8 | 108 | [02-core-collections-integrations.md](research/02-core-collections-integrations.md) | `strands-fun-tools`, `strands-google`, AgentCore tools, community/examples collections, `strands-pack`, StackOne, and Valyu |
| Service-specific tools | 14 | 22 | [03-service-specific-tools.md](research/03-service-specific-tools.md) | Messaging, communications, data, search, commerce, blockchain, security, and SaaS integrations |
| Multimodal, local-model, and physical tools | 11 | 56 | [04-multimodal-local-physical.md](research/04-multimodal-local-physical.md) | Transformers, Diffusers, ADB, vision/audio, robotics, local inference, rendering, and inspection |
| Tool loaders, adapters, and infrastructure | 15 | 90 | [05-loaders-adapters-infrastructure.md](research/05-loaders-adapters-infrastructure.md) | MCP/UTCP/OpenAPI adapters, dynamic loaders, sandboxes, browser tools, human/VR tools, memory, and infrastructure |
| Strands Labs and framework-adjacent repositories | 11 | 135 | [06-labs-framework-adjacent.md](research/06-labs-framework-adjacent.md) | Labs robotics/Cosmos, AI functions, Compose, RL environments, model providers, and MLX |
| Sessions, extensions, and skills | 10 | 71 | [07-sessions-extensions-skills.md](research/07-sessions-extensions-skills.md) | Extensions, six session-manager surfaces, AgentSkills loaders, general skills, and 40 healthcare/life-science skills |

## Row schema

Every detailed inventory row provides:

1. Repository
2. Tool or exported entrypoint
3. Description
4. Tool type
5. Required dependencies
6. Optional dependencies
7. Install command
8. Installation and implementation context
9. Source evidence

Tool types are limited to the requested taxonomy: coding, computer/browser automation, research, multimodal, communication, fun/leisure, productivity, machine learning, healthcare, and operations.

## Method and boundaries

- Repository source, package manifests, exports, and installation documentation were inspected directly. Reports use live source links and identify pinned source snapshots where relevant.
- Tests, fixtures, fake/no-op tools, deliberately unimplemented templates, and documentation-only snippets were excluded from the production inventory.
- Dynamic tool families are identified explicitly when their final tool names depend on runtime configuration or a remote server.
- Packaging defects, undeclared imports, stale README instructions, missing extras, hardware requirements, credentials, external services, and potentially destructive actions are called out in the implementation-context column.
- The official baseline is Python 3.10+ with `pip install strands-agents strands-agents-tools`; individual tools often require extras, system packages, credentials, cloud resources, model weights, browsers, databases, or physical hardware documented in their rows.
- The graph package now has a dedicated virtual environment and clean build/test workflow. The wider inventory remains a research snapshot; installing every inventoried optional tool is outside the graph package's dependency surface.
