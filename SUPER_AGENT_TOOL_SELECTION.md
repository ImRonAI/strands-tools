# Non-redundant Strands super-agent tool selection

Research snapshot: **2026-07-26**

This document selects the strongest useful contribution from every repository in the seven existing inventory groups. It is intentionally not a list of everything that can be installed. Duplicate implementations, archived packages, examples, incomplete packaging, and unnecessarily narrow tools are either replaced by a stronger canonical implementation or kept out of the default runtime.

The objective is a production agent with broader capability than general-purpose agent products, not a claim that repository count alone proves superiority. That claim will require implementation and comparative evaluation.

## Selection rules

Candidates were judged on:

1. **Leverage** — how many real tasks the capability unlocks.
2. **Uniqueness** — whether another selected tool already provides the same result.
3. **Production readiness** — package integrity, maintained source, and real implementations.
4. **Composability** — whether the capability works cleanly with Strands tool loading, MCP, AgentSkills, and subagents.
5. **Operational safety** — whether credentials, side effects, permissions, and isolation can be controlled.

Decision labels:

- **Adopt** — canonical implementation for the super-agent.
- **Conditional** — valuable capability loaded only for a relevant environment, domain, or approved high-risk task.
- **Reference** — useful development pattern or infrastructure, but not a model-visible production tool.
- **Exclude** — redundant, archived, incomplete, or weaker than the selected replacement.

## Recommended runtime architecture

### Always-visible control plane

Only the following compact surface should be placed in the base model context:

| Capability | Canonical tool |
|---|---|
| Semantic capability lookup | `retrieve` |
| Load a local approved tool | `load_tool` |
| Activate an instruction/resource package | native `skills` via `AgentSkills` |
| Delegate to a specialist | `use_agent` / `Agent.as_tool` |
| Delegate to a skill-bound specialist | `use_skill` from `create_skill_agent_tool(...)` |
| Peer multi-agent collaboration | `swarm` |
| Deterministic orchestration | `workflow` |
| Human approval or takeover | `handoff_to_user` |
| Validated final responses | `StructuredOutputTool` |
| Long-term recall | `hindsight_recall` |
| Long-term retention | `hindsight_retain` |
| Memory consolidation | `hindsight_reflect` |
| Safe direct network request | native `http_request` |

MCP servers, SaaS integrations, code execution, browsers, physical devices, financial tools, healthcare skills, and multimodal models should be discoverable through this control plane but loaded only for the active task.

### Canonical capability packs

| Pack | Selected repositories and tools |
|---|---|
| Isolated workspace work | `strands-agents/shell`: MCP `shell`, `read_file`, `write_file`, `list_dir` inside its deny-by-default VFS |
| Native SDK services | `harness-sdk`: `http_request`, `AgentSkills`, `MCPClient`, `ContextOffloader`, structured output, agent-as-tool |
| Sandboxed code | `strands-agents/tools`: AgentCore `code_interpreter`; `strands-inspect`: `inspect_tool` only inside that sandbox |
| Runtime ecosystem expansion | `strands-fun-tools`: `dynamic_package`, `npm`, `template`; approved Python and Node packages are preinstalled and allow-listed |
| Browser and desktop | persistent AgentCore `browser`; official `use_computer`; `strands-adb` for Android |
| Tool expansion | native `MCPClient`; `strands-utcp`; `strands-tools-mcp`; native `AgentSkills` |
| Orchestration | `use_agent`, `use_skill`, `swarm`, `workflow`, native SDK `GraphBuilder`, agent-as-tool, async background tasks; `batch` is retained only as a sequential multi-call aggregator |
| Memory | Hindsight retain/recall/reflect plus mental models and directives; native `ContextOffloader` for oversized results |
| Sessions | PostgreSQL session manager in production; SQLite only for offline/local profiles |
| Research | Perplexity multi-search for broad current research; Valyu for finance, papers, biomedical, patents, SEC, and economics |
| Data | `sql_database`; Google Discovery APIs; StackOne dynamic SaaS actions |
| Communications | Telegram send/listen, official Slack tools, community Teams tool |
| Multimodal | Transformers, Diffusers, OmniVoice, Sapiens, Cosmos, and Strands Robots |
| Documents | RenderCV plus selected Kyopark DOCX/PPTX/XLSX/graph skills and Strands Pack media/PDF utilities |
| Cloud operations | AgentCore lifecycle tools, `use_aws`, Cloudflare operations, OSMO workflows |
| Guardrails | CostGuard; redaction, fallback, retry, and rate-limit plugins; Compose maximum-call and stop guards |
| Evaluation | Strands Evals goal-completion and deterministic match scorers; real end-to-end acceptance flows |
| Domain packs | HCLS healthcare/life-science skills, robotics plugins, commerce, blockchain, or trading only when explicitly enabled |

### Shell and filesystem safety boundary

`strands-agents/shell` is the canonical workspace execution layer. Start each session with an empty VFS, bind source code with `mode="copy"`, bind only a designated output directory with `mode="direct"`, explicitly allowlist URLs, inject credentials per URL, and set time/output/file limits. Do not expose the `strands-agents-tools` host `file_read`, `file_write`, `editor`, or host `shell` in the normal runtime.

Strands Shell is a mediation layer rather than an OS security boundary. Multi-tenant, adversarial, package-execution, or generated-code workloads must still run the entire Shell instance inside a container or microVM.

### Orchestration primitives

| Tool | Distinct responsibility |
|---|---|
| `use_agent` | Creates a general specialist agent with a task-specific prompt, model, and tool set. |
| `use_skill` | Loads one selected Agent Skill into a fresh isolated subagent and streams its result without expanding the parent context. |
| `swarm` | Coordinates peer agents that collaborate and hand work among themselves, with handoff/iteration/time limits. |
| `workflow` | Runs a deterministic, inspectable sequence of agent/tool steps. |
| `graph` | Runs conditional or branching DAG orchestration. |
| `batch` | Aggregates several direct tool calls into one response. The current implementation invokes them sequentially, despite its parallel-execution description. |

### Current nesting support and wrapper gaps

| Formation | Structural graph node through native `GraphBuilder` | Declarable as a node through the model-facing `graph` tool | Invocable from an ordinary graph-node agent |
|---|---|---|---|
| `Agent` / `use_agent` specialist | `Agent` instances: yes; the `use_agent` function itself: no | Ordinary Agent node: yes | `use_agent`: yes, when registered on that node |
| Native `Swarm` | Yes; `Swarm` is a `MultiAgentBase` | No; the wrapper always constructs an ordinary `Agent` for every topology node | Yes; a node agent can call the `swarm` tool |
| Nested native `Graph` | Yes; `Graph` is a `MultiAgentBase` | No | Yes; a node can call the global `graph` tool, but that launches a separate managed graph rather than embedding it structurally |
| `workflow` tool | No; it is a decorated tool/manager, not `AgentBase` or `MultiAgentBase` | No | Yes |
| `batch` tool | No; it is a tool function | No | Yes, but its current implementation is sequential |
| `use_skill` | The decorated tool itself: no | No direct skill-node type | Yes; the graph-node agent can call it and receive the nested skill agent's streamed/final result |

Native SDK graphs can therefore contain a prebuilt `Swarm` or another `Graph` as a real node. The current `strands_tools.graph` JSON topology cannot express either formation because `GraphManager.create_graph()` unconditionally constructs an `Agent` for every node and passes only that Agent to `GraphBuilder.add_node()`.

`use_skill` can participate indirectly anywhere its generated tool is registered:

- a graph-node Agent can call `use_skill`;
- a swarm member can receive `use_skill` in its tool list;
- a workflow task Agent can receive `use_skill`;
- a `use_agent` specialist can inherit or explicitly receive `use_skill`.

The resulting skill Agent is a nested child of the calling Agent. It is not assigned its own graph node ID, does not participate directly in graph edges, and does not automatically inherit the caller's tools or invocation state. Its available tools are the `additional_tools` captured when `create_skill_agent_tool(...)` is constructed.

For a first-class skill node today, create an ordinary graph-node Agent whose only orchestration tool is `use_skill`, or construct the skill-configured Agent directly and add it with native `GraphBuilder`. The first option makes the outer Agent the scheduled node; the second makes the skill Agent itself the scheduled node.

Production code should prefer native `GraphBuilder` for nested topologies. The model-facing `graph` wrapper has a second scoping defect: when a node does not specify a model provider/settings, the implementation ignores that node's `tools` list and copies the entire parent registry. Explicit per-node tool isolation is honored only through the custom-model branch.

## Repository-by-repository decisions

### 1. Official Strands repositories

Full evidence: [01-official-strands.md](research/01-official-strands.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `strands-agents/harness-sdk` | `http_request`, `AgentSkills`, `MCPClient`, `ContextOffloader`, structured output, agent-as-tool | **Adopt** | Native foundation. Its `bash` and `file_editor` are not the default workspace boundary; use them only when explicitly routed through a real Docker/SSH sandbox or another trusted isolated backend. |
| `strands-agents/tools` | `retrieve`, `load_tool`, `code_interpreter`, `use_computer`, `use_agent`, `swarm`, `workflow`, `graph`, auxiliary `batch`, `handoff_to_user`, `use_aws`, Slack | **Adopt** | Primary capability router, sandbox service, orchestration layer, and human-control surface. `use_agent`, `swarm`, and `workflow` are foundational because they provide specialist, peer-collaborative, and deterministic execution modes. Use native `GraphBuilder`, not the current `graph` wrapper, for structural Swarm/nested-Graph nodes and strict per-node tools. `batch` is only a sequential multi-call aggregator in current source. Deliberately omit host `file_read`, `file_write`, `editor`, `shell`, and `python_repl`; confirmation prompts are not filesystem isolation. |
| `strands-agents/shell` | MCP `shell`, `read_file`, `write_file`, `list_dir` | **Adopt** | Canonical workspace shell/file layer: empty VFS by default, explicit copy/direct binds, URL allowlisting and SSRF protection, per-request credential injection, and resource limits. Use copy binds for source and direct binds only for designated outputs. |
| `strands-agents/agent-sop` | `pdd`, `codebase-summary`, `code-assist` | **Adopt** | Development-time planning and codebase comprehension skills; loaded for engineering tasks only. |
| `strands-agents/evals` | goal-completion scorer and deterministic exact/order scorers | **Adopt** | Real outcome evaluation and regression scoring. Exclude `ToolSimulator` from production acceptance because it does not prove live behavior. |
| `strands-agents/mcp-server` | `search_docs`, `fetch_doc` | **Exclude** | The same documentation MCP surface is already shipped in `harness-sdk`. |
| `strands-agents/extension-template` | unimplemented template declarations | **Exclude** | No usable production tool. |
| `strands-agents/devtools` | GitHub issue, PR, review, shell, editor, notebook, and handoff tools | **Adopt** | Canonical engineering/GitHub operations pack. Load only inside an approved repository workspace. |
| `strands-agents/docs` | documentation authoring/audit skills | **Exclude** | Archived and duplicated by `harness-sdk`. |
| `strands-agents/sdk-typescript` | TypeScript vended tools and MCP | **Exclude** | Archived and superseded by `harness-sdk`. |
| `strands-agents/agent-builder` | legacy re-exported tool collection | **Exclude** | Archived and redundant with the current SDK/tools package. |
| `strands-agents/samples` | SRE remediation, financial analysis, healthcare, multimodal, and UX integration patterns | **Reference** | Mine for production patterns, but do not treat application-local sample tools as a reusable runtime package. |

### 2. Core collections and integrations

Full evidence: [02-core-collections-integrations.md](research/02-core-collections-integrations.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `cagataycali/strands-fun-tools` | `dynamic_package`, `npm`, `template`, `yolo_vision`, `screen_reader`, `bluetooth` | **Adopt** | Runtime capability multiplier plus local perception and BLE. `dynamic_package` invokes approved installed Python APIs; `npm` invokes approved installed Node packages; `template` provides deterministic Jinja rendering. These complement `load_tool`, which loads Strands tool modules, and `inspect_tool`, which performs deep package/code analysis. Load this pack only inside a sandbox with package/member allow-lists. Omit cursor, clipboard, duplicate Whisper, and terminal UI utilities. |
| `cagataycali/strands-google` | `use_google` | **Adopt** | One consent-aware gateway to Gmail, Calendar, Drive, Docs, Sheets, Tasks, and other enabled Google APIs. |
| `cagataycali/strands-agentcore-tools` | `configure`, `launch`, `invoke`, `status`, `logs`, `identity`, `session` | **Adopt** | AgentCore deployment and operations pack. Hindsight remains the canonical semantic memory. |
| `eraykeskinmac/strands-tools-community` | `teams` | **Adopt** | Use only its Teams integration. Prefer the dedicated HubSpot/voice choices below for other capabilities. |
| `eraykeskinmac/strands-tools-examples` | examples only | **Exclude** | No reusable production tool surface. |
| `labeveryday/strands-pack` | `pdf_to_markdown`, `ffmpeg`, `youtube_transcript`, `local_embeddings`, `qrcode_tool` | **Adopt** | Document/media conversion and local utility pack. Avoid its browser, Google, GitHub, Gmail, cloud, and office tools where stronger canonical selections exist. |
| `StackOneHQ/strands-stackone` | `stackone_search`, `stackone_execute`, dynamically loaded SaaS actions | **Adopt** | Primary long-tail business SaaS integration layer. Retrieve actions on demand instead of publishing every connector to the model. |
| `valyuAI/valyu-agentcore` | `finance_search`, `paper_search`, `bio_search`, `patent_search`, `sec_search`, `economics_search` | **Adopt** | Specialist research pack. Broad `web_search` is omitted because Perplexity is the canonical general search provider. |

### 3. Service-specific tools

Full evidence: [03-service-specific-tools.md](research/03-service-specific-tools.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `eraykeskinmac/strands-telegram` | `telegram` | **Adopt** | Outbound Telegram messaging, media, and bot administration. |
| `eraykeskinmac/strands-telegram-listener` | `telegram_listener` | **Adopt** | Inbound Telegram events and optional agent replies; complements rather than duplicates the sender. |
| `eraykeskinmac/strands-teams` | `teams` | **Exclude** | Packaging defect and duplicate of the selected community Teams implementation. |
| `eraykeskinmac/strands-hubspot` | `hubspot` | **Exclude** | StackOne is the canonical CRM/SaaS action broker. Use this only if StackOne lacks a required HubSpot operation. |
| `eraykeskinmac/strands-deepgram` | `deepgram` | **Exclude** | OmniVoice is the selected unified transcription/TTS/voice stack. Deepgram remains a cloud fallback, not a default duplicate. |
| `mertozbas/strands-ccxt` | `use_ccxt` | **Conditional** | Market data and trading across exchanges. Require read-only mode by default and explicit approval for orders. |
| `mertozbas/strands-cloudflare` | `use_cloudflare` | **Adopt** | DNS, edge, and Cloudflare operational control with scoped tokens and approvals for mutations. |
| `mertozbas/strands-vercel` | `use_vercel` | **Exclude** | Current source has missing Strands dependency/package-layout problems. |
| `NithiN-1808/strands-sql` | `sql_database` | **Adopt** | Canonical relational data tool with schema inspection, bounded queries, and read-only defaults. |
| `mkmeral/strands-perplexity` | `perplexity_multi_search` | **Adopt** | Default broad, current, multi-angle web research tool. |
| `cagataycali/strands-hackerone` | `hackerone` | **Conditional** | Authorized vulnerability-program and report research. It is read-oriented; the advertised report-creation action is not implemented. |
| `plagtech/strands-agents-spraay` | `spraay_batch_payment` | **Conditional** | Batch blockchain payments only in a separate financial-action sandbox with human approval. Never place in the default tool set. |
| `cagataycali/strands-ucp` | `ucp_discover`, `ucp_checkout_session`, `ucp_complete_checkout` | **Conditional** | Commerce discovery and checkout. Completion requires explicit payment approval. |
| `cagataycali/strands-erc8004` | `erc8004`, `ipfs`, narrowly scoped `x402` | **Conditional** | On-chain agent identity/trust and content storage. Disable transfers, deployments, and paid requests unless separately authorized. |

### 4. Multimodal, local-model, and physical tools

Full evidence: [04-multimodal-local-physical.md](research/04-multimodal-local-physical.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `cagataycali/strands-transformers` | `use_transformers` | **Adopt** | General local Hugging Face inference for classification, extraction, embeddings, and specialist pipelines. |
| `cagataycali/strands-diffusers` | `use_diffusers` | **Adopt** | Local image/video generation and editing pipeline gateway. |
| `cagataycali/strands-adb` | `adb`, `recorder` | **Adopt** | Android device/emulator control plus interaction recording. |
| `cagataycali/strands-sapiens` | `sapiens_seg`, `sapiens_pose`, `sapiens_normal`, `sapiens_pointmap` | **Conditional** | High-value human-centric vision pack after Torch, upstream Sapiens, detectors, checkpoints, and GPU requirements are provisioned. |
| `cagataycali/strands-omnivoice` | `omnivoice_transcribe`, `omnivoice_tts`, `omnivoice_clone`, `omnivoice_design` | **Adopt** | Canonical speech input/output and voice generation pack. |
| `cagataycali/strands-microgpt` | `microgpt_train`, `microgpt_generate` | **Exclude** | Educational/narrow implementation duplicated by full Transformers, MLX, and vLLM stacks. |
| `cagataycali/strands-osmo` | workflow submit/status/logs/exec plus data upload/download | **Adopt** | Distributed GPU/compute workflow operations. |
| `cagataycali/strands-spot` | `use_spot` | **Conditional** | Boston Dynamics Spot adapter only when that hardware is present; the general robotics layer is `strands-labs/robots`. |
| `cagataycali/strands-strudel` | `strudel` | **Conditional** | Creative music/code generation pack after its undeclared WebSocket dependency is handled. |
| `cagataycali/strands-rendercv` | `render_cv` | **Adopt** | Canonical structured resume/CV rendering to PDF, Markdown, HTML, and images. |
| `cagataycali/strands-inspect` | `inspect_tool` | **Adopt** | Extremely powerful package/source inspection, profiling, graphing, calls, and code generation—only inside an isolated sandbox with install/exec approval. |

### 5. Tool loaders, adapters, and infrastructure

Full evidence: [05-loaders-adapters-infrastructure.md](research/05-loaders-adapters-infrastructure.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `universal-tool-calling-protocol/strands-utcp` | `UtcpToolAdapter.to_strands_tools()` | **Adopt** | Dynamic discovery of tools from UTCP providers without writing one-off wrappers. |
| `cagataycali/strands-mcp-server` | `mcp_client`, `mcp_server`, `invoke_agent` | **Exclude** | Native `MCPClient` handles inbound MCP and `strands-tools-mcp` handles outward exposure with less overlap. |
| `mkmeral/strands-tools-mcp` | `create_server()` | **Adopt** | Expose an approved subset of Strands tools through MCP for other agents and clients. |
| `mikegc-aws/async-agentic-tools` | `tool_async`, `handle_task` | **Adopt** | Long-running background work and callback-based subagent tasks without blocking the main interaction. |
| `mikegc-aws/agentcore-browser-tool` | persistent-profile `browser` | **Adopt** | Canonical browser automation with real cookies and local-storage continuity across sessions. |
| `klogins-hash/island-hopper-tools` | `ObjectStorageTool`, `DatabaseTool` | **Exclude** | Missing direct Strands adapter and duplicated by `use_aws`/storage tools plus canonical `sql_database`. |
| `gonzalo123/openapi-toolsmith` | `generate_openapi_tools` | **Exclude** | Useful concept, but the current PoC lacks authentication, endpoint allow-listing, and approvals. UTCP/MCP are the production dynamic API paths. |
| `pingidentity/strands-pingfederate-token-exchange` | authenticated `create_mcp_clients()` | **Adopt** | Enterprise delegated identity for downstream MCP tool calls using token exchange. |
| `wisemanIV/strands-costguard` | `CostGuard` routing/budget/hooks infrastructure | **Adopt** | Canonical cost budget, routing, persistence, and metrics layer even though it is orchestration infrastructure rather than a model-visible tool. |
| `fengclient/strands-sandbox` | E2B `code_interpreter` | **Exclude** | Real backend but incomplete package installation and redundant with the official AgentCore code interpreter. |
| `abekek/strands-arise` | evolved tool family and `list_evolved_skills` | **Conditional** | Controlled self-improvement lane. Generated tools must be sandboxed, evaluated, reviewed, signed, and promoted before production use. |
| `sachi-vr/strands-agents-vrchat-tools` | player move/turn/jump and chat | **Conditional** | Leisure/VR capability pack, isolated because the module starts an interactive loop at import time. |
| `sachi-vr/strands-agents-human-tools` | `speak` | **Exclude** | Duplicates the selected OmniVoice TTS stack. |
| `Vivek0712/clawskills-strands` | `1password`, `apple_notes`, `apple_reminders`, `peekaboo`, `tmux`, `voice_call` | **Adopt** | Compatibility bridge to valuable local/desktop capabilities missing elsewhere. Exclude its duplicated GitHub, Slack, Notion, media, weather, and coding tools. |
| `vectorize-io/hindsight` | retain/recall/reflect, mental models, directives, knowledge pages | **Adopt** | Canonical long-term semantic memory and learned operating-model layer. |

### 6. Strands Labs and framework-adjacent repositories

Full evidence: [06-labs-framework-adjacent.md](research/06-labs-framework-adjacent.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `strands-labs/robots` | Robot/Simulation AgentTools, ROS/RTPS bridges, policy providers | **Adopt** | Canonical general robotics and embodied-action framework. |
| `strands-labs/strands-for-cosmos` | Cosmos reasoning, vision, embodied reasoning, world generation, training tools | **Adopt** | Advanced physical-world understanding and multimodal world-model pack, loaded on GPU-capable workers. |
| `strands-labs/ai-functions` | `ai_function`, `ClaudeAgent`, `KiroAgent`, `list_threads`, `send_message` | **Adopt** | Typed AI-executed functions and external coding-agent delegation. Omit its local Python executor and JSON memory because stronger canonical choices exist. |
| `strands-labs/robots-sim` | `IsaacSimulation` backend | **Conditional** | NVIDIA Isaac Sim plugin for robotics simulation and validation. |
| `strands-compose/sdk-python` | `node_as_async_tool`, `MaxToolCallsGuard`, `StopGuard`, `MultiAgentStopGuard`, `ToolNameSanitizer` | **Adopt** | Async graph composition and hard execution-loop guardrails. Omit its general tool loaders where native `load_tool` is sufficient. |
| `strands-compose/bedrock-agentcore` | `create_app`, local and AgentCore clients | **Reference** | Deployment/runtime support, not an agent-facing capability pack. |
| `strands-rl/strands-sglang` | `SGLangModel`, `LoopLimiter` | **Exclude** | vLLM is the selected self-hosted inference provider and Compose supplies stronger general loop guards. |
| `strands-rl/strands-env` | `Environment`, `AgentCoreCodeEnv`, `MCPAtlasEnv`, `Tau2BenchEnv` | **Adopt** | Training, evaluation, and environment rollouts—not default production tools. |
| `amazon-nova-api/strands-nova` | `NovaAPIModel` | **Conditional** | Managed Nova model provider for workloads that specifically benefit from Nova. |
| `agents-community/strands-vllm` | `VLLMModel`, validation hooks, token recorder | **Adopt** | Canonical high-throughput self-hosted model provider. |
| `cagataycali/strands-mlx` | `MLXModel`, `MLXVisionModel`, inference and training tools | **Adopt** | Apple-silicon edge/offline inference and fine-tuning profile; it complements rather than co-loads with server-side vLLM. |

### 7. Sessions, extensions, and skills

Full evidence: [07-sessions-extensions-skills.md](research/07-sessions-extensions-skills.md)

| Repository | Strongest non-redundant contribution | Decision | Super-agent role |
|---|---|---|---|
| `afarntrog/strands-agents-extensions` | `MessageRedactionPlugin`, `ModelFallbackPlugin`, `RetryPlugin`, `RateLimiterPlugin` | **Adopt** | Runtime privacy, resilience, and throttling. CostGuard replaces its overlapping budget feature; PostgreSQL replaces its SQLite manager in production. |
| `afarntrog/strands-sqlite-session-manager` | `SQLiteSessionManager` | **Conditional** | Offline/single-node profile only. Do not load alongside the production PostgreSQL manager. |
| `macuartin/strands-postgresql-session-manager` | `PostgresSessionManager` | **Adopt** | Canonical durable multi-instance production session store. |
| `lekhnath/strands-redis-session-manager` | `RedisSessionManager` | **Exclude** | Redundant session-store option with weaker durability than the selected PostgreSQL path. |
| `siddharthkrish/strands-supabase-session-manager` | `SupabaseSessionManager` | **Conditional** | Hosted PostgreSQL alternative when Supabase is already the platform of record. |
| `jeromevdl/strands-valkey-session-manager` | `ValkeySessionManager` | **Conditional** | AWS/ElastiCache-oriented low-latency alternative, selected only for that deployment profile. |
| `aws-samples/sample-strands-agents-agentskills` | `create_skill_agent_tool(...)` → `use_skill`; `skill-creator` | **Adopt** | `use_skill` is the canonical dynamic skill-subagent tool: each call loads one chosen skill into a fresh specialist agent, supports a dedicated model/tool set, and streams the subagent result. It complements native `AgentSkills`, which activates skills in the parent agent. |
| `hi-space/strands-agentskills` | duplicated skill loaders and skills | **Exclude** | Archived duplicate of the AWS sample. |
| `kyopark2014/strands-skills` | `docx`, `pptx`, `xlsx`, `graphify` | **Adopt** | On-demand office-document and graph-generation skills. Omit its memory, retrieval, browser, PDF, and skill-creator entries where canonical selections already exist. |
| `awslabs/hcls-agent-skills` | `clinical-data-standards`, `ehr-data-parsing`, `claims-analytics`, `pa-decision-automation`, `dicom-processing`, `genomic-variant-interpretation`, `multi-omics-integration`, `drug-repurposing`, `medical-device-software-compliance`, `translational-research` | **Adopt** | High-value healthcare/life-science domain pack. Load only the task-relevant skill and enforce PHI, clinical-review, regulatory, and validation controls. |

## Final recommended adoption set

The repository decisions yield:

- **45 Adopt** repositories or capability sources.
- **15 Conditional** domain, hardware, deployment-profile, or high-risk sources.
- **2 Reference** sources used for development or infrastructure patterns.
- **19 Exclude** sources removed because they are redundant, archived, broken, incomplete, or weaker than a selected implementation.

These are source-selection counts, not startup tool counts. The model should see roughly 13 control-plane tools at startup and retrieve/load the rest only when the current task and policy permit them.

## What makes this stronger than a giant static tool list

1. **Tool discovery instead of prompt bloat:** `retrieve`, `load_tool`, MCP, UTCP, StackOne, AgentSkills, `dynamic_package`, and `npm` make the installed Python/Node ecosystems and hundreds of remote capabilities reachable without publishing hundreds of schemas on every turn.
2. **Durable intelligence:** Hindsight provides recall, reflection, mental models, directives, and knowledge pages; PostgreSQL persists sessions; ContextOffloader protects the context window.
3. **Real execution breadth:** host files/shell, sandboxed code, persistent browser state, desktop control, Android, SaaS, SQL, cloud operations, multimodal generation, voice, robotics, and specialist healthcare workflows.
4. **Specialist delegation:** `use_agent`, skill-bound `use_skill`, `swarm`, workflows, graphs, agents-as-tools, AI Functions, async tasks, and external coding agents provide distinct specialist, collaborative, and deterministic execution modes without replacing the native Strands loop.
5. **Production controls:** human handoff, structured output, cost routing, redaction, retry/fallback, rate limits, maximum tool calls, stop guards, scoped credentials, and approval gates for mutations.
6. **Measurable quality:** Strands Evals and real acceptance flows can compare task completion, latency, cost, safety, and recovery against the competing products named in the objective.
