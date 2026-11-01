# Facilitator Guidelines

Work here and inherit root/app guidance. Configure native AI SDK `ToolLoopAgent`, not a handcrafted planning/tool loop. Source: https://ai-sdk.dev/docs/agents/building-agents; pinned snapshot `docs/reference/ai-sdk/agents.md` and installed package declarations.

Expose only model-visible tools from the canonical compact server catalog; keep actual tool UI metadata/results intact. Use existing compatible-provider factories for Telnyx inference, with the user's configured available/capable model. Do not write a new model provider or hard-code an old model example.

ToolLoopAgent owns iteration/stop conditions and supported lifecycle callbacks. Application code may configure documented callbacks; it must not manually reproduce the SDK execution graph. Each user/run gets an appropriately scoped connection and context, not another user's cached authenticated toolset. Native server refusals remain refusals.

Telnyx AI Assistants remain native voice/meeting/agent product operations. Assistant Chat's documented text/delta/done/error output is not automatically a widget stream. For an application already carrying its own agent, do not launch a second facilitator. Research TestModel/MockLanguageModel fixtures establish mechanics, not real-model quality or live delivery.

## Assigned directory
Project target: `packages/app/src/agent`. Change into this directory before development. This copy is a planning template; the project scaffold is not installed until the worker applies it.
