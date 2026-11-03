# pyright: strict
"""Heterogeneous async streaming Strands graph tool with JSON/Dict Agent Config, Harness, & Skill Node support."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal, TypeVar, cast

from pydantic import BaseModel
from strands import Agent, tool
from strands.agent import AgentResult
from strands.models import Model, ModelRouter
from strands.multiagent import Swarm
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.multiagent.graph import Graph, GraphBuilder
from strands.types.content import Messages, SystemContentBlock
from strands.types.event_loop import Metrics, Usage
from strands.types.multiagent import MultiAgentInput
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec
from strands_harness import defaults as harness_defaults
from strands_harness.models import build_gemini_fallback_router, resolve_model

from .agent_factory import (
    ConfigDict,
    ConfigMapping,
    ModelFactory,
    build_agent_from_config,
    coerce_gemini_tools,
    get_agent_config,
    is_config_mapping,
    is_object_sequence,
    load_agent_config_dict,
    register_factory_tools,
    resolve_agent_tools,
)

_T = TypeVar("_T", bound=BaseModel)


class StubModel(Model):
    """Deterministic Strands `Model` implementation for offline/stub execution when no live API key is active."""

    def __init__(self, tag: str = "stub") -> None:
        self.tag = tag
        self._config: ConfigDict = {"model_id": tag}

    def update_config(self, **model_config: object) -> None:
        self._config.update(model_config)

    def get_config(self) -> ConfigDict:
        return dict(self._config)

    async def structured_output(
        self,
        output_model: type[_T],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: object,
    ) -> AsyncGenerator[dict[str, _T | object], None]:
        raise NotImplementedError("StubModel does not implement structured_output")
        yield {}

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        invocation_state: dict[str, object] | None = None,
        cancel_signal: threading.Event | None = None,
        **kwargs: object,
    ) -> AsyncIterable[StreamEvent]:
        _ = (tool_choice, system_prompt_content, invocation_state, cancel_signal, kwargs)
        tool_names = [str(spec.get("name", "")) for spec in (tool_specs or [])]
        sys_text = system_prompt or ""

        has_tool_result = any(
            "toolResult" in block
            for msg in messages
            for block in msg.get("content", [])
        )

        last_user_text = ""
        last_tool_result_text = ""
        for msg in reversed(messages):
            for block in msg.get("content", []):
                if not last_user_text and "text" in block and msg.get("role") == "user":
                    last_user_text = str(block["text"])
                if not last_tool_result_text and "toolResult" in block:
                    tr_obj: object = block["toolResult"]
                    if is_config_mapping(tr_obj):
                        tr_content = tr_obj.get("content", [])
                        if is_object_sequence(tr_content):
                            texts = [
                                str(c.get("text", c))
                                for c in tr_content
                                if is_config_mapping(c)
                            ]
                            last_tool_result_text = " ".join(texts).strip()

        # If this is an outer skill-routing node with `use_skill` available and no toolResult yet,
        # emit a real toolUse call to `use_skill` so the isolated skill sub-agent executes end-to-end.
        is_inner_skill_agent = "<skill " in sys_text or "## Assigned Tools" in sys_text
        if "use_skill" in tool_names and not has_tool_result and not is_inner_skill_agent:
            skill_match = re.search(r"skill[=:\s'\"]+([a-zA-Z0-9_-]+)", f"{sys_text}\n{last_user_text}", re.I)
            target_skill = skill_match.group(1) if skill_match else "file-processing"
            if _SKILLS_MAP and target_skill not in _SKILLS_MAP:
                target_skill = next(iter(_SKILLS_MAP.keys()))
            yield cast(StreamEvent, {"messageStart": {"role": "assistant"}})
            yield cast(
                StreamEvent,
                {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "toolUseId": "stub_call_use_skill_1",
                                "name": "use_skill",
                            }
                        }
                    }
                },
            )
            import json as _json

            tool_input_json = _json.dumps(
                {
                    "skill_name": target_skill,
                    "request": last_user_text or "Execute skill task.",
                }
            )
            yield cast(
                StreamEvent,
                {"contentBlockDelta": {"delta": {"toolUse": {"input": tool_input_json}}}},
            )
            yield cast(StreamEvent, {"contentBlockStop": {}})
            yield cast(StreamEvent, {"messageStop": {"stopReason": "tool_use"}})
            yield cast(
                StreamEvent,
                {
                    "metadata": {
                        "usage": {"inputTokens": 12, "outputTokens": 16, "totalTokens": 28},
                        "metrics": {"latencyMs": 1},
                    }
                },
            )
            return

        summary_tools = ", ".join(tool_names) if tool_names else "none"
        if last_tool_result_text:
            reply_text = f"[{self.tag}] Completed with tool result ({last_tool_result_text}) [tools: {summary_tools}]"
        else:
            reply_text = f"[{self.tag}] Executed task ({last_user_text}) [tools: {summary_tools}]"

        yield cast(StreamEvent, {"messageStart": {"role": "assistant"}})
        yield cast(StreamEvent, {"contentBlockStart": {"start": {}}})
        yield cast(StreamEvent, {"contentBlockDelta": {"delta": {"text": reply_text}}})
        yield cast(StreamEvent, {"contentBlockStop": {}})
        yield cast(StreamEvent, {"messageStop": {"stopReason": "end_turn"}})
        yield cast(
            StreamEvent,
            {
                "metadata": {
                    "usage": {"inputTokens": 10, "outputTokens": 14, "totalTokens": 24},
                    "metrics": {"latencyMs": 1},
                }
            },
        )


_DEFAULT_MODEL_FACTORIES: dict[str, ModelFactory] = {
    "stub": lambda: StubModel("stub"),
}
_MODEL_FACTORIES: dict[str, ModelFactory] = dict(_DEFAULT_MODEL_FACTORIES)
_SKILLS_MAP: dict[str, object] = {}
_SKILLS_RUNTIME: dict[str, object] = {"base_model": None}
_SKILLS_ADDITIONAL_TOOLS: list[object] = []


def get_model_factories() -> dict[str, ModelFactory]:
    """Return a copy of the active model factory registry (including built-in `'stub'`)."""
    return {**_DEFAULT_MODEL_FACTORIES, **_MODEL_FACTORIES}


def configure_models(factories: Mapping[str, ModelFactory]) -> None:
    """Register trusted model factory callables by model_id."""
    _MODEL_FACTORIES.clear()
    _MODEL_FACTORIES.update(_DEFAULT_MODEL_FACTORIES)
    _MODEL_FACTORIES.update(factories or {})


def configure_skills(
    skills: Iterable[object],
    *,
    base_agent_model: object = None,
    additional_tools: Sequence[object] | None = None,
) -> None:
    """Register discovered SkillProperties for skill-backed workflow/graph/swarm nodes and `use_skill`."""
    _SKILLS_MAP.clear()
    skill_list = list(skills or [])
    for s in skill_list:
        s_name = getattr(s, "name", None)
        if isinstance(s_name, str) and s_name:
            _SKILLS_MAP[s_name] = s
    _SKILLS_RUNTIME["base_model"] = base_agent_model
    _SKILLS_ADDITIONAL_TOOLS.clear()
    if additional_tools:
        _SKILLS_ADDITIONAL_TOOLS.extend(additional_tools)

    if skill_list:
        try:
            from agentskills.models import SkillProperties
            from agentskills.tool.agent_skill import (
                create_skill_agent_tool,
                register_available_tools,
            )

            first_path_attr = getattr(skill_list[0], "path", None)
            first_path = Path(str(first_path_attr)) if first_path_attr is not None else Path(".")
            skills_dir = first_path.parent if first_path.exists() else Path(".")
            typed_skills = [cast(SkillProperties, s) for s in skill_list]
            typed_base_model: Model | ModelRouter = (
                base_agent_model
                if isinstance(base_agent_model, (Model, ModelRouter))
                else StubModel("stub_skill")
            )
            use_skill_tool: object = create_skill_agent_tool(
                typed_skills,
                skills_dir=skills_dir,
                base_agent_model=typed_base_model,
                additional_tools=list(_SKILLS_ADDITIONAL_TOOLS),
            )
            register_available_tools({"use_skill": use_skill_tool})
            register_factory_tools({"use_skill": use_skill_tool})
        except Exception:
            pass


def ensure_default_skills_configured() -> None:
    """Discover and configure default workspace skills if `configure_skills` has not yet populated `_SKILLS_MAP`."""
    if _SKILLS_MAP:
        return
    repo_root = Path(__file__).resolve().parents[2]
    sample_skills_dir = (
        repo_root / "src" / "strands_tools" / "sessions_and_skills" / "sample_agent_skills" / "skills"
    )
    main_skills_dir = repo_root / "src" / "skills"
    try:
        from agentskills import discover_skills

        discovered: list[object] = []
        seen: set[str] = set()
        for folder in (sample_skills_dir, main_skills_dir):
            if folder.exists():
                for skill_obj in discover_skills(folder):
                    if skill_obj.name not in seen:
                        discovered.append(skill_obj)
                        seen.add(skill_obj.name)
        if discovered:
            configure_skills(discovered)
    except Exception:
        pass


_SUPPORTED_PROVIDER_PREFIXES = (
    "google/",
    "gemini/",
    "gemini-",
    "anthropic/",
    "openai/",
    "bedrock/",
    "bedrock-mantle/",
    "litellm/",
    "ollama/",
)


def _normalize_provider_spec(model_str: str) -> str:
    if model_str.startswith("gemini/"):
        return f"google/{model_str.split('/', 1)[1]}"
    if model_str.startswith("gemini-"):
        return f"google/{model_str}"
    return model_str


def _resolve_model(
    spec: ConfigMapping,
    parent_agent: Agent | None,
    *,
    fallback_model: object = None,
) -> object:
    raw_gemini_tools = spec.get("gemini_tools") or spec.get("geminiTools")
    gemini_tools = coerce_gemini_tools(raw_gemini_tools)
    factories = get_model_factories()
    model_id = spec.get("model_id")
    if model_id is not None:
        if isinstance(model_id, str) and model_id in factories:
            return factories[model_id]()
        if isinstance(model_id, str) and model_id.startswith(_SUPPORTED_PROVIDER_PREFIXES):
            target = _normalize_provider_spec(model_id)
            return resolve_model(target, harness_defaults.DEFAULT_MODEL, gemini_tools=gemini_tools)
        raise ValueError(f"Unknown model_id: {model_id}")
    if "model" in spec and spec["model"] is not None:
        raw_model = spec["model"]
        if isinstance(raw_model, str):
            if raw_model in factories:
                return factories[raw_model]()
            if raw_model.startswith(_SUPPORTED_PROVIDER_PREFIXES):
                target = _normalize_provider_spec(raw_model)
                return resolve_model(target, harness_defaults.DEFAULT_MODEL, gemini_tools=gemini_tools)
        if not is_config_mapping(raw_model):
            return raw_model
    if parent_agent is not None:
        return parent_agent.model
    if fallback_model is not None:
        return fallback_model
    return build_gemini_fallback_router(gemini_tools=gemini_tools)


def _extract_config_source(spec: ConfigMapping) -> str | Path | ConfigMapping | None:
    """Return the external/nested config reference if `spec` uses `config`, `config_path`, `config_name`, `agent`, or `harness`."""
    for key in ("config", "config_path", "config_name", "agent", "harness"):
        val = spec.get(key)
        if isinstance(val, (str, Path)) or is_config_mapping(val):
            return val
    return None


def _build_agent(
    spec: ConfigMapping | str | Path,
    parent_agent: Agent | None = None,
    *,
    for_swarm: bool = False,
    force_engine: Literal["auto", "harness", "sdk"] = "auto",
) -> Agent:
    """Build a fresh Strands `Agent` for a formation node from a node spec or JSON/dict agent config."""
    factories = get_model_factories()
    if isinstance(spec, (str, Path)):
        return build_agent_from_config(
            spec,
            parent_agent=parent_agent,
            engine=force_engine,
            session=False,
            for_swarm=for_swarm,
            model_factories=factories,
        )

    cfg_source = _extract_config_source(spec)
    if cfg_source is not None:
        cfg_dict, base_path = load_agent_config_dict(cfg_source)
        merged: ConfigDict = {**cfg_dict}
        for k in (
            "id",
            "name",
            "description",
            "system_prompt",
            "instructions",
            "prompt",
            "model_id",
            "model",
            "engine",
            "use_skill",
            "gemini_tools",
            "geminiTools",
            "builtin_tools",
            "builtinTools",
        ):
            if k in spec and spec[k] is not None:
                merged[k] = spec[k]
        if force_engine != "auto":
            merged["engine"] = force_engine
        extra_tools = spec.get("tools")
        extra_tools_seq: Sequence[object] | None = (
            extra_tools if is_object_sequence(extra_tools) else None
        )
        return build_agent_from_config(
            merged,
            parent_agent=parent_agent,
            engine=force_engine,
            session=False,
            extra_tools=extra_tools_seq,
            for_swarm=for_swarm,
            model_factories=factories,
            base_path=base_path,
        )

    raw_spec_tools = spec.get("tools")
    spec_tools_seq: Sequence[object] = (
        raw_spec_tools if is_object_sequence(raw_spec_tools) else ()
    )

    if (
        force_engine == "harness"
        or spec.get("engine") in ("harness", "create_harness", "sdk")
        or spec.get("use_skill")
        or spec.get("subagents")
        or spec.get("gemini_tools")
        or spec.get("geminiTools")
        or any(isinstance(t, str) or is_config_mapping(t) for t in spec_tools_seq)
    ):
        raw_mid = spec.get("model_id")
        if (
            raw_mid is not None
            and not (isinstance(raw_mid, str) and raw_mid in factories)
            and not (isinstance(raw_mid, str) and raw_mid.startswith(_SUPPORTED_PROVIDER_PREFIXES))
        ):
            raise ValueError(f"Unknown model_id: {raw_mid}")
        return build_agent_from_config(
            spec,
            parent_agent=parent_agent,
            engine=force_engine,
            session=False,
            for_swarm=for_swarm,
            model_factories=factories,
        )

    node_id = str(spec.get("id") or spec.get("name") or "agent")
    system_prompt = str(
        spec.get("system_prompt")
        or spec.get("instructions")
        or spec.get("prompt")
        or spec.get("description")
        or spec.get("goal")
        or ""
    )
    description = str(
        spec.get("description")
        or spec.get("goal")
        or (system_prompt.splitlines()[0] if system_prompt else f"Agent {node_id}")
    )
    model = _resolve_model(spec, parent_agent)
    resolved_tools = (
        resolve_agent_tools(spec_tools_seq, parent_agent=parent_agent, for_swarm=for_swarm)
        if raw_spec_tools is not None
        else None
    )
    kwargs: dict[str, object] = {
        "name": node_id,
        "description": description,
        "system_prompt": system_prompt,
        "callback_handler": None,
    }
    if model is not None:
        kwargs["model"] = model
        if isinstance(model, ModelRouter):
            kwargs["retry_strategy"] = None
    if resolved_tools is not None:
        kwargs["tools"] = resolved_tools
    agent_cls = cast(Callable[..., Agent], Agent)
    agent = agent_cls(**kwargs)
    setattr(agent, "_session_manager", None)
    return agent


def _build_skill_task_agent(
    task_spec: ConfigMapping,
    parent_agent: Agent | None = None,
    *,
    for_swarm: bool = False,
) -> Agent:
    """Build a fresh skill-pinned Strands `Agent` for a Graph, Swarm, or Workflow node."""
    ensure_default_skills_configured()
    skill_name = str(task_spec.get("skill") or task_spec.get("skill_name") or "")
    if skill_name not in _SKILLS_MAP:
        raise ValueError(f"Skill '{skill_name}' not found")
    skill = _SKILLS_MAP[skill_name]

    from agentskills.models import SkillProperties
    from agentskills.parser import load_instructions
    from agentskills.tool.agent_skill import _create_skill_agent

    typed_skill = cast(SkillProperties, skill)
    instructions = load_instructions(typed_skill.path)
    model = _resolve_model(
        task_spec,
        parent_agent,
        fallback_model=_SKILLS_RUNTIME.get("base_model"),
    )
    extra_tools: list[object] = list(_SKILLS_ADDITIONAL_TOOLS)
    raw_task_tools = task_spec.get("tools")
    if is_object_sequence(raw_task_tools):
        extra_tools.extend(
            resolve_agent_tools(
                raw_task_tools,
                parent_agent=parent_agent,
                for_swarm=for_swarm,
            )
        )
    if for_swarm:
        extra_tools = [
            t
            for t in extra_tools
            if getattr(t, "tool_name", getattr(t, "__name__", None)) != "handoff_to_agent"
        ]
    typed_model = model if isinstance(model, (Model, ModelRouter)) else None
    agent = _create_skill_agent(
        skill=typed_skill,
        instructions=instructions,
        model=typed_model,
        additional_tools=extra_tools if extra_tools else None,
    )
    node_name = task_spec.get("id") or task_spec.get("name") or task_spec.get("task_id")
    if node_name:
        agent.name = str(node_name)
    if not getattr(agent, "description", None):
        agent.description = str(getattr(typed_skill, "description", f"Skill agent for {skill_name}"))
    setattr(agent, "_session_manager", None)
    return agent


class SkillToolNode(MultiAgentBase):
    """Deterministic `MultiAgentBase` node executor that runs an isolated skill sub-agent directly."""

    def __init__(
        self,
        node_id: str,
        skill_spec: ConfigMapping,
        parent_agent: Agent | None = None,
    ) -> None:
        super().__init__()
        self.id = node_id
        self.name = node_id
        self._skill_spec: ConfigDict = dict(skill_spec)
        self._parent_agent = parent_agent

    @staticmethod
    def _input_to_text(task: MultiAgentInput) -> str:
        if isinstance(task, str):
            return task
        parts: list[str] = []
        for block in task:
            if "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts)

    async def invoke_async(
        self,
        task: MultiAgentInput,
        invocation_state: dict[str, object] | None = None,
        **kwargs: object,
    ) -> MultiAgentResult:
        final_result: MultiAgentResult | None = None
        async for event in self.stream_async(task, invocation_state=invocation_state, **kwargs):
            if "result" in event and isinstance(event["result"], MultiAgentResult):
                final_result = event["result"]
        if final_result is None:
            raise RuntimeError(f"SkillToolNode '{self.id}' did not produce a MultiAgentResult.")
        return final_result

    async def stream_async(
        self,
        task: MultiAgentInput,
        invocation_state: dict[str, object] | None = None,
        **kwargs: object,
    ) -> AsyncIterator[dict[str, object]]:
        _ = kwargs
        start_time = time.time()
        prompt_text = self._input_to_text(task)
        skill_agent = _build_skill_task_agent(self._skill_spec, parent_agent=self._parent_agent)

        agent_response: AgentResult | None = None
        async for raw_event in skill_agent.stream_async(prompt_text, invocation_state=invocation_state):
            event_obj: object = raw_event
            yield {
                "skill_name": str(self._skill_spec.get("skill", "")),
                "node_id": self.id,
                "event": event_obj,
            }
            if is_config_mapping(event_obj) and "result" in event_obj:
                res_val = event_obj["result"]
                if isinstance(res_val, AgentResult):
                    agent_response = res_val

        elapsed_ms = round((time.time() - start_time) * 1000)
        if agent_response is None:
            raise RuntimeError(f"SkillToolNode '{self.id}' skill agent did not produce an AgentResult.")

        response_metrics: object = getattr(agent_response, "metrics", None)
        usage: Usage = getattr(
            response_metrics,
            "accumulated_usage",
            Usage(inputTokens=0, outputTokens=0, totalTokens=0),
        )
        metrics: Metrics = getattr(
            response_metrics,
            "accumulated_metrics",
            Metrics(latencyMs=elapsed_ms),
        )
        node_res = NodeResult(
            result=agent_response,
            execution_time=elapsed_ms,
            status=Status.COMPLETED,
            accumulated_usage=usage,
            accumulated_metrics=metrics,
            execution_count=1,
        )
        multi_result = MultiAgentResult(
            status=Status.COMPLETED,
            results={self.id: node_res},
            accumulated_usage=usage,
            accumulated_metrics=metrics,
            execution_count=1,
            execution_time=elapsed_ms,
        )
        yield {"result": multi_result}


def _build_member_agent(
    member: ConfigMapping | str | Path,
    parent_agent: Agent | None = None,
    *,
    for_swarm: bool = False,
) -> Agent:
    """Build an `Agent` for a Swarm or Parallel member."""
    if isinstance(member, (str, Path)):
        return _build_agent(member, parent_agent=parent_agent, for_swarm=for_swarm)
    if "skill" in member:
        return _build_skill_task_agent(member, parent_agent=parent_agent, for_swarm=for_swarm)
    return _build_agent(member, parent_agent=parent_agent, for_swarm=for_swarm)


def _build_node_executor(node_spec: ConfigMapping, parent_agent: Agent | None = None) -> MultiAgentBase | Agent:
    node_type = str(node_spec.get("type", "agent"))
    node_id = str(node_spec.get("id") or node_spec.get("name") or "node")

    if node_type in ("create_harness", "harness"):
        harness_spec: ConfigDict = dict(node_spec)
        harness_ref = (
            node_spec.get("agent")
            or node_spec.get("harness")
            or node_spec.get("config_name")
            or node_spec.get("config")
        )
        if harness_ref is None and get_agent_config(node_id) is not None:
            harness_spec["config_name"] = node_id
        return _build_agent(harness_spec, parent_agent=parent_agent, force_engine="harness")

    if node_type in ("agent", "config"):
        if "skill" in node_spec:
            return _build_skill_task_agent(node_spec, parent_agent=parent_agent)
        return _build_agent(node_spec, parent_agent=parent_agent)

    if node_type == "skill":
        return _build_skill_task_agent(node_spec, parent_agent=parent_agent)

    if node_type == "skill_node":
        if "skill" not in node_spec:
            raise ValueError(f"Node '{node_id}' with type='skill_node' requires a 'skill' field.")
        return SkillToolNode(node_id=node_id, skill_spec=node_spec, parent_agent=parent_agent)

    if node_type == "use_skill":
        ensure_default_skills_configured()
        spec_with_use_skill: ConfigDict = dict(node_spec)
        spec_with_use_skill["use_skill"] = True
        target_skill = spec_with_use_skill.get("skill") or spec_with_use_skill.get("skill_name")
        if not spec_with_use_skill.get("system_prompt") and not spec_with_use_skill.get("prompt"):
            if isinstance(target_skill, str) and target_skill:
                spec_with_use_skill["system_prompt"] = (
                    f"You are a skill-routing specialist node for skill='{target_skill}'. "
                    f"Use the `use_skill` tool with skill_name='{target_skill}' to accomplish the task."
                )
            else:
                spec_with_use_skill["system_prompt"] = (
                    "You are a skill-routing specialist node. Use the `use_skill` tool to accomplish the task."
                )
        return _build_agent(spec_with_use_skill, parent_agent=parent_agent)

    if node_type == "swarm":
        raw_agents = node_spec.get("agents")
        agent_specs: Sequence[object] = (
            raw_agents if is_object_sequence(raw_agents) else ()
        )
        agents: list[Agent] = []
        for member in agent_specs:
            if isinstance(member, (str, Path)) or is_config_mapping(member):
                agents.append(
                    _build_member_agent(
                        member,
                        parent_agent=parent_agent,
                        for_swarm=True,
                    )
                )
        return Swarm(nodes=agents)

    if node_type == "workflow":
        builder = GraphBuilder()
        raw_tasks = node_spec.get("tasks")
        tasks: list[ConfigMapping] = [
            t
            for t in (raw_tasks if is_object_sequence(raw_tasks) else ())
            if is_config_mapping(t)
        ]
        for task in tasks:
            tid = str(task["task_id"])
            task_type = str(task.get("type", "agent"))
            if task_type == "skill_node":
                executor: MultiAgentBase | Agent = SkillToolNode(
                    node_id=tid, skill_spec=task, parent_agent=parent_agent
                )
            elif "skill" in task or task_type == "skill":
                executor = _build_skill_task_agent(task, parent_agent=parent_agent)
            else:
                task_agent_spec: ConfigDict = dict(task)
                task_agent_spec.setdefault("id", tid)
                if "system_prompt" not in task_agent_spec and "prompt" not in task_agent_spec:
                    task_agent_spec["system_prompt"] = task.get("description") or ""
                executor = _build_agent(task_agent_spec, parent_agent=parent_agent)
            builder.add_node(executor, tid)
        for task in tasks:
            tid = str(task["task_id"])
            raw_deps = task.get("dependencies")
            deps: Sequence[object] = (
                raw_deps if is_object_sequence(raw_deps) else ()
            )
            for dep in deps:
                builder.add_edge(str(dep), tid)
        return builder.build()

    if node_type == "parallel":
        builder = GraphBuilder()
        raw_members = node_spec.get("agents")
        members: Sequence[object] = (
            raw_members if is_object_sequence(raw_members) else ()
        )
        for idx, member in enumerate(members):
            if isinstance(member, (str, Path)):
                built_member = _build_member_agent(member, parent_agent=parent_agent)
                mid = built_member.name or f"parallel_{idx}"
                builder.add_node(built_member, mid)
            elif is_config_mapping(member):
                mid = str(member.get("id") or member.get("name") or f"parallel_{idx}")
                builder.add_node(_build_member_agent(member, parent_agent=parent_agent), mid)
        return builder.build()

    if node_type == "graph":
        return build_graph(dict(node_spec), parent_agent=parent_agent)

    raise ValueError(f"Unknown node type: {node_type}")


def build_graph(topology: ConfigMapping, parent_agent: Agent | None = None) -> Graph:
    """Compile a topology dictionary into a native Strands Graph containing Agent/Swarm/Graph/Harness/Skill nodes."""
    builder = GraphBuilder()
    raw_nodes = topology.get("nodes")
    nodes: Sequence[object] = (
        raw_nodes if is_object_sequence(raw_nodes) else ()
    )
    for idx, raw_node in enumerate(nodes):
        if not is_config_mapping(raw_node):
            continue
        node_id = str(raw_node.get("id") or raw_node.get("name") or f"node_{idx}")
        executor = _build_node_executor(raw_node, parent_agent=parent_agent)
        builder.add_node(executor, node_id)

    raw_edges = topology.get("edges")
    edges: Sequence[object] = (
        raw_edges if is_object_sequence(raw_edges) else ()
    )
    for edge in edges:
        if is_object_sequence(edge):
            if len(edge) >= 2:
                builder.add_edge(str(edge[0]), str(edge[1]))
        elif is_config_mapping(edge):
            src = edge.get("from") or edge.get("source")
            dst = edge.get("to") or edge.get("target")
            if src is not None and dst is not None:
                builder.add_edge(str(src), str(dst))
    if topology.get("entry_point"):
        builder.set_entry_point(str(topology["entry_point"]))
    raw_eps = topology.get("entry_points")
    if is_object_sequence(raw_eps):
        for ep in raw_eps:
            builder.set_entry_point(str(ep))
    max_execs = topology.get("max_node_executions")
    if isinstance(max_execs, (int, float, str)):
        builder.set_max_node_executions(int(max_execs))
    exec_timeout = topology.get("execution_timeout")
    if isinstance(exec_timeout, (int, float, str)):
        builder.set_execution_timeout(float(exec_timeout))
    node_timeout = topology.get("node_timeout")
    if isinstance(node_timeout, (int, float, str)):
        builder.set_node_timeout(float(node_timeout))
    if topology.get("reset_on_revisit") is not None:
        builder.reset_on_revisit(bool(topology["reset_on_revisit"]))
    return builder.build()


class GraphManager:
    """Isolated per-instance manager for named Strands graphs."""

    def __init__(self) -> None:
        self._graphs: dict[str, Graph] = {}
        self._topologies: dict[str, ConfigDict] = {}

    def register_compiled(
        self,
        graph_id: str,
        compiled: Graph,
        topology: ConfigMapping,
    ) -> None:
        """Store a pre-compiled `Graph` and its topology dictionary."""
        self._graphs[graph_id] = compiled
        self._topologies[graph_id] = dict(topology)

    def create(
        self,
        graph_id: str,
        topology: ConfigMapping,
        parent_agent: Agent | None = None,
    ) -> ConfigDict:
        if not graph_id:
            return {"status": "error", "content": [{"text": "graph_id is required"}]}
        if graph_id in self._graphs:
            return {"status": "error", "content": [{"text": f"Graph '{graph_id}' already exists"}]}
        try:
            compiled = build_graph(topology, parent_agent=parent_agent)
        except Exception as exc:
            return {"status": "error", "content": [{"text": f"Failed to build graph '{graph_id}': {exc}"}]}
        self._graphs[graph_id] = compiled
        self._topologies[graph_id] = dict(topology)
        return {
            "status": "success",
            "graph_id": graph_id,
            "nodes": list(compiled.nodes.keys()),
            "content": [{"text": f"Graph '{graph_id}' created with {len(compiled.nodes)} nodes."}],
        }

    def list(self) -> ConfigDict:
        ids = sorted(self._graphs.keys())
        text = f"Active graphs ({len(ids)}): {', '.join(ids)}" if ids else "No active graphs."
        return {"status": "success", "graphs": ids, "content": [{"text": text}]}

    def delete(self, graph_id: str) -> ConfigDict:
        if graph_id not in self._graphs:
            return {"status": "error", "content": [{"text": f"Graph '{graph_id}' not found"}]}
        del self._graphs[graph_id]
        self._topologies.pop(graph_id, None)
        return {"status": "success", "content": [{"text": f"Graph '{graph_id}' deleted."}]}

    def get(self, graph_id: str) -> Graph | None:
        return self._graphs.get(graph_id)


_DEFAULT_MANAGER = GraphManager()


@tool
async def graph(
    action: str,
    graph_id: str | None = None,
    topology: ConfigDict | None = None,
    task: str | None = None,
    agent: object | None = None,
) -> AsyncIterator[ConfigDict]:
    """Create, execute, list, inspect status, or delete heterogeneous Strands multi-agent graphs.

    Supports node types:
    - `agent` / `config`: Standard Strands Agent or registered agent config.
    - `create_harness` / `harness`: Agent built by `create_harness` (referenced by `agent`/`name` or inline).
    - `use_skill` / `skill` / `skill_node`: Agent backed by `use_skill` (Pattern #3 isolated skill sub-agent).
    - `swarm`: Handoff-based multi-agent team node.
    - `workflow`: Task-DAG sub-graph node.
    - `parallel`: Fan-out parallel execution node.
    - `graph`: Nested multi-agent graph node.

    Args:
        action: Action to perform ("create", "execute", "list", "delete", "status").
        graph_id: Unique identifier for the graph.
        topology: Graph topology dictionary containing `nodes` and optional `edges`.
        task: Task prompt to execute when action="execute".
        agent: Parent Strands Agent instance (injected automatically when available).
    """
    parent_agent = agent if isinstance(agent, Agent) else None
    if action == "create":
        yield _DEFAULT_MANAGER.create(graph_id or "", topology or {}, parent_agent=parent_agent)
        return
    if action == "list":
        yield _DEFAULT_MANAGER.list()
        return
    if action == "delete":
        yield _DEFAULT_MANAGER.delete(graph_id or "")
        return
    if action == "status":
        g = _DEFAULT_MANAGER.get(graph_id or "")
        if g is None:
            yield {"status": "error", "content": [{"text": f"Graph '{graph_id}' not found"}]}
            return
        yield {
            "status": "success",
            "graph_id": graph_id,
            "nodes": list(g.nodes.keys()),
            "content": [{"text": f"Graph '{graph_id}' has {len(g.nodes)} nodes: {', '.join(g.nodes)}"}],
        }
        return
    if action in ("execute", "run"):
        g = _DEFAULT_MANAGER.get(graph_id or "") if graph_id else None
        if g is None and topology is not None:
            try:
                g = build_graph(topology, parent_agent=parent_agent)
            except Exception as exc:
                yield {"status": "error", "content": [{"text": f"Failed to build graph: {exc}"}]}
                return
            if graph_id:
                _DEFAULT_MANAGER.register_compiled(graph_id, g, topology)
        if g is None:
            yield {"status": "error", "content": [{"text": f"Graph '{graph_id}' not found"}]}
            return
        final_result: MultiAgentResult | None = None
        async for raw_event in g.stream_async(task or ""):
            event_obj: object = raw_event
            if is_config_mapping(event_obj):
                if "result" in event_obj and isinstance(event_obj["result"], MultiAgentResult):
                    final_result = event_obj["result"]
                else:
                    ev_type = str(event_obj.get("type", "event"))
                    node_id = event_obj.get("node_id")
                    if node_id is not None:
                        yield {"type": ev_type, "node_id": str(node_id)}

        node_outputs: dict[str, str] = {}
        if final_result is not None:
            for nid, nres in final_result.results.items():
                node_outputs[nid] = str(nres.result).strip()

        summary_text = (
            "\n".join(f"[{nid}] {out}" for nid, out in node_outputs.items())
            if node_outputs
            else (str(final_result) if final_result is not None else f"Graph '{graph_id or 'inline'}' completed.")
        )
        yield {
            "status": "success",
            "graph_id": graph_id or "inline",
            "node_outputs": node_outputs,
            "content": [{"text": summary_text}],
        }
        return

    yield {"status": "error", "content": [{"text": f"Unknown action: {action}"}]}


__all__ = [
    "GraphManager",
    "SkillToolNode",
    "StubModel",
    "build_graph",
    "configure_models",
    "configure_skills",
    "ensure_default_skills_configured",
    "get_model_factories",
    "graph",
]
