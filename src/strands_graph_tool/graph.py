"""Heterogeneous async streaming Strands graph tool with JSON/Dict Agent Config & Skill Node support."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from strands import Agent, tool
from strands.agent import AgentResult
from strands.models import ModelRouter
from strands.multiagent import Swarm
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.multiagent.graph import Graph, GraphBuilder
from strands.types.event_loop import Metrics, Usage
from strands.types.multiagent import MultiAgentInput
from strands_harness import defaults as harness_defaults
from strands_harness.models import build_gemini_fallback_router, resolve_model

from .agent_factory import (
    build_agent_from_config,
    load_agent_config_dict,
    resolve_agent_tools,
)

_MODEL_FACTORIES: dict[str, Callable[[], Any]] = {}
_SKILLS_MAP: dict[str, Any] = {}
_SKILLS_BASE_MODEL: Any = None
_SKILLS_ADDITIONAL_TOOLS: list[Any] = []


def configure_models(factories: dict[str, Callable[[], Any]]) -> None:
    """Register trusted model factory callables by model_id."""
    _MODEL_FACTORIES.clear()
    _MODEL_FACTORIES.update(factories or {})


def configure_skills(
    skills: Iterable[Any],
    *,
    base_agent_model: Any = None,
    additional_tools: list[Any] | None = None,
) -> None:
    """Register discovered SkillProperties for skill-backed workflow/graph/swarm nodes and `use_skill`."""
    global _SKILLS_BASE_MODEL, _SKILLS_ADDITIONAL_TOOLS
    _SKILLS_MAP.clear()
    skill_list = list(skills or [])
    for s in skill_list:
        _SKILLS_MAP[s.name] = s
    _SKILLS_BASE_MODEL = base_agent_model
    _SKILLS_ADDITIONAL_TOOLS = list(additional_tools or [])

    if skill_list:
        try:
            from agentskills.tool.agent_skill import (
                create_skill_agent_tool,
                register_available_tools,
            )

            first_path = Path(skill_list[0].path)
            skills_dir = first_path.parent if first_path.exists() else Path(".")
            use_skill_tool = create_skill_agent_tool(
                skill_list,
                skills_dir=skills_dir,
                base_agent_model=base_agent_model,
                additional_tools=_SKILLS_ADDITIONAL_TOOLS,
            )
            register_available_tools({"use_skill": use_skill_tool})
        except Exception:
            pass


def _resolve_model(
    spec: Mapping[str, Any],
    parent_agent: Agent | None,
    *,
    fallback_model: Any = None,
) -> Any:
    raw_gemini_tools = spec.get("gemini_tools") or spec.get("geminiTools")
    gemini_tools = raw_gemini_tools if isinstance(raw_gemini_tools, (list, tuple)) else None
    model_id = spec.get("model_id")
    if model_id is not None:
        if model_id in _MODEL_FACTORIES:
            return _MODEL_FACTORIES[model_id]()
        if isinstance(model_id, str) and model_id.startswith(("google/", "gemini/", "gemini-")):
            target = model_id if "/" in model_id else f"google/{model_id}"
            return resolve_model(target, harness_defaults.DEFAULT_MODEL, gemini_tools=gemini_tools)
        raise ValueError(f"Unknown model_id: {model_id}")
    if "model" in spec and spec["model"] is not None:
        raw_model = spec["model"]
        if isinstance(raw_model, str):
            if raw_model in _MODEL_FACTORIES:
                return _MODEL_FACTORIES[raw_model]()
            if raw_model.startswith(("google/", "gemini/", "gemini-")):
                target = raw_model if "/" in raw_model else f"google/{raw_model}"
                return resolve_model(target, harness_defaults.DEFAULT_MODEL, gemini_tools=gemini_tools)
        if not isinstance(raw_model, Mapping):
            return raw_model
    if parent_agent is not None:
        return parent_agent.model
    if fallback_model is not None:
        return fallback_model
    return build_gemini_fallback_router(gemini_tools=gemini_tools)


def _extract_config_source(spec: Mapping[str, Any]) -> str | Path | Mapping[str, Any] | None:
    """Return the external/nested config reference if `spec` uses `config`, `config_path`, or `config_name`."""
    for key in ("config", "config_path", "config_name"):
        val = spec.get(key)
        if val is not None:
            return val
    return None


def _build_agent(
    spec: dict[str, Any] | str | Path,
    parent_agent: Agent | None = None,
    *,
    for_swarm: bool = False,
) -> Agent:
    """Build a fresh Strands `Agent` for a formation node from a node spec or JSON/dict agent config."""
    if isinstance(spec, (str, Path)):
        return build_agent_from_config(
            spec,
            parent_agent=parent_agent,
            session=False,
            for_swarm=for_swarm,
            model_factories=_MODEL_FACTORIES,
        )

    cfg_source = _extract_config_source(spec)
    if cfg_source is not None:
        cfg_dict, base_path = load_agent_config_dict(cfg_source)
        merged: dict[str, Any] = {**cfg_dict}
        for k in (
            "id",
            "name",
            "description",
            "system_prompt",
            "prompt",
            "model_id",
            "model",
            "engine",
            "use_skill",
            "gemini_tools",
            "geminiTools",
        ):
            if k in spec and spec[k] is not None:
                merged[k] = spec[k]
        extra_tools = spec.get("tools")
        return build_agent_from_config(
            merged,
            parent_agent=parent_agent,
            session=False,
            extra_tools=extra_tools if isinstance(extra_tools, list) else None,
            for_swarm=for_swarm,
            model_factories=_MODEL_FACTORIES,
            base_path=base_path,
        )

    # Check if this node spec requests the harness engine or JSON/dict features (`subagents`, `use_skill`, etc.)
    if (
        spec.get("engine") in ("harness", "sdk")
        or spec.get("use_skill")
        or spec.get("subagents")
        or spec.get("gemini_tools")
        or spec.get("geminiTools")
        or any(isinstance(t, (str, Mapping)) for t in (spec.get("tools") or []))
    ):
        # Validate model_id eagerly if present
        raw_mid = spec.get("model_id")
        if (
            raw_mid is not None
            and raw_mid not in _MODEL_FACTORIES
            and not (isinstance(raw_mid, str) and raw_mid.startswith(("google/", "gemini/", "gemini-")))
        ):
            raise ValueError(f"Unknown model_id: {raw_mid}")
        return build_agent_from_config(
            spec,
            parent_agent=parent_agent,
            session=False,
            for_swarm=for_swarm,
            model_factories=_MODEL_FACTORIES,
        )

    node_id = str(spec.get("id") or spec.get("name") or "agent")
    system_prompt = str(spec.get("system_prompt") or spec.get("prompt") or spec.get("description") or spec.get("goal") or "")
    description = str(
        spec.get("description")
        or spec.get("goal")
        or (system_prompt.splitlines()[0][:200] if system_prompt else f"Agent {node_id}")
    )
    model = _resolve_model(spec, parent_agent)
    raw_tools = spec.get("tools")
    resolved_tools = (
        resolve_agent_tools(raw_tools, parent_agent=parent_agent, for_swarm=for_swarm)
        if raw_tools is not None
        else None
    )
    kwargs: dict[str, Any] = {
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
    agent = Agent(**kwargs)
    agent._session_manager = None
    return agent


def _build_skill_task_agent(
    task_spec: Mapping[str, Any],
    parent_agent: Agent | None = None,
    *,
    for_swarm: bool = False,
) -> Agent:
    """Build a fresh skill-pinned Strands `Agent` for a Graph, Swarm, or Workflow node."""
    skill_name = str(task_spec["skill"])
    if skill_name not in _SKILLS_MAP:
        raise ValueError(f"Skill '{skill_name}' not found")
    skill = _SKILLS_MAP[skill_name]

    from agentskills.parser import load_instructions
    from agentskills.tool.agent_skill import _create_skill_agent

    instructions = load_instructions(skill.path)
    model = _resolve_model(
        task_spec,
        parent_agent,
        fallback_model=_SKILLS_BASE_MODEL,
    )
    extra_tools = list(_SKILLS_ADDITIONAL_TOOLS)
    if task_spec.get("tools"):
        extra_tools.extend(
            resolve_agent_tools(
                task_spec["tools"],
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
    agent = _create_skill_agent(
        skill=skill,
        instructions=instructions,
        model=model,
        additional_tools=extra_tools if extra_tools else None,
    )
    node_name = task_spec.get("id") or task_spec.get("name") or task_spec.get("task_id")
    if node_name:
        agent.name = str(node_name)
    if not getattr(agent, "description", None):
        agent.description = str(getattr(skill, "description", f"Skill agent for {skill_name}"))
    agent._session_manager = None
    return agent


class SkillToolNode(MultiAgentBase):
    """Deterministic `MultiAgentBase` node executor that runs an isolated skill sub-agent directly.

    Allows placing a Pattern #3 skill execution directly as a singular node in a `Graph` or `Workflow`
    without requiring an outer LLM router turn to call `use_skill`.
    """

    def __init__(
        self,
        node_id: str,
        skill_spec: Mapping[str, Any],
        parent_agent: Agent | None = None,
    ) -> None:
        super().__init__()
        self.id = node_id
        self.name = node_id
        self._skill_spec = dict(skill_spec)
        self._parent_agent = parent_agent

    @staticmethod
    def _input_to_text(task: MultiAgentInput) -> str:
        if isinstance(task, str):
            return task
        parts: list[str] = []
        for block in task:
            if isinstance(block, Mapping) and "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts)

    async def invoke_async(
        self,
        task: MultiAgentInput,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
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
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        start_time = time.time()
        prompt_text = self._input_to_text(task)
        skill_agent = _build_skill_task_agent(self._skill_spec, parent_agent=self._parent_agent)

        agent_response: AgentResult | None = None
        async for event in skill_agent.stream_async(prompt_text, invocation_state=invocation_state):
            yield {
                "skill_name": str(self._skill_spec.get("skill", "")),
                "node_id": self.id,
                "event": event,
            }
            if isinstance(event, Mapping) and "result" in event:
                res = event["result"]
                if isinstance(res, AgentResult):
                    agent_response = res

        elapsed_ms = round((time.time() - start_time) * 1000)
        if agent_response is None:
            raise RuntimeError(f"SkillToolNode '{self.id}' skill agent did not produce an AgentResult.")

        response_metrics = getattr(agent_response, "metrics", None)
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
    member: dict[str, Any] | str | Path,
    parent_agent: Agent | None = None,
    *,
    for_swarm: bool = False,
) -> Agent:
    """Build an `Agent` for a Swarm or Parallel member (supporting skill agents, `use_skill`, and JSON/dict configs)."""
    if isinstance(member, (str, Path)):
        return _build_agent(member, parent_agent=parent_agent, for_swarm=for_swarm)
    if "skill" in member:
        return _build_skill_task_agent(member, parent_agent=parent_agent, for_swarm=for_swarm)
    return _build_agent(member, parent_agent=parent_agent, for_swarm=for_swarm)


def _build_node_executor(node_spec: dict[str, Any], parent_agent: Agent | None = None) -> Any:
    node_type = node_spec.get("type", "agent")
    node_id = str(node_spec.get("id") or node_spec.get("name") or "node")

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
        spec_with_use_skill = dict(node_spec)
        spec_with_use_skill["use_skill"] = True
        if not spec_with_use_skill.get("system_prompt") and not spec_with_use_skill.get("prompt"):
            spec_with_use_skill["system_prompt"] = (
                "You are a skill-routing specialist node. Use the `use_skill` tool to accomplish the task."
            )
        return _build_agent(spec_with_use_skill, parent_agent=parent_agent)

    if node_type == "swarm":
        agents = [
            _build_member_agent(member, parent_agent=parent_agent, for_swarm=True)
            for member in node_spec.get("agents", [])
        ]
        return Swarm(nodes=agents)

    if node_type == "workflow":
        builder = GraphBuilder()
        tasks = node_spec.get("tasks", [])
        for task in tasks:
            tid = str(task["task_id"])
            task_type = task.get("type", "agent")
            if task_type == "skill_node":
                executor: Any = SkillToolNode(node_id=tid, skill_spec=task, parent_agent=parent_agent)
            elif "skill" in task or task_type == "skill":
                executor = _build_skill_task_agent(task, parent_agent=parent_agent)
            else:
                task_agent_spec = dict(task)
                task_agent_spec.setdefault("id", tid)
                if "system_prompt" not in task_agent_spec and "prompt" not in task_agent_spec:
                    task_agent_spec["system_prompt"] = task.get("description") or ""
                executor = _build_agent(task_agent_spec, parent_agent=parent_agent)
            builder.add_node(executor, tid)
        for task in tasks:
            tid = str(task["task_id"])
            for dep in task.get("dependencies", []) or []:
                builder.add_edge(str(dep), tid)
        return builder.build()

    if node_type == "parallel":
        builder = GraphBuilder()
        for idx, member in enumerate(node_spec.get("agents", [])):
            if isinstance(member, (str, Path)):
                built_member = _build_member_agent(member, parent_agent=parent_agent)
                mid = built_member.name or f"parallel_{idx}"
                builder.add_node(built_member, mid)
            else:
                mid = str(member.get("id") or member.get("name") or f"parallel_{idx}")
                builder.add_node(_build_member_agent(member, parent_agent=parent_agent), mid)
        return builder.build()

    if node_type == "graph":
        return build_graph(node_spec, parent_agent=parent_agent)

    raise ValueError(f"Unknown node type: {node_type}")


def build_graph(topology: dict[str, Any], parent_agent: Agent | None = None) -> Graph:
    """Compile a topology dictionary into a native Strands Graph containing Agent/Swarm/Graph/Skill nodes."""
    builder = GraphBuilder()
    for idx, node_spec in enumerate(topology.get("nodes", [])):
        node_id = str(node_spec.get("id") or node_spec.get("name") or f"node_{idx}")
        executor = _build_node_executor(node_spec, parent_agent=parent_agent)
        builder.add_node(executor, node_id)
    for edge in topology.get("edges", []) or []:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            builder.add_edge(str(edge[0]), str(edge[1]))
        elif isinstance(edge, dict):
            src = edge.get("from") or edge.get("source")
            dst = edge.get("to") or edge.get("target")
            if src is not None and dst is not None:
                builder.add_edge(str(src), str(dst))
    if topology.get("entry_point"):
        builder.set_entry_point(str(topology["entry_point"]))
    for ep in topology.get("entry_points", []) or []:
        builder.set_entry_point(str(ep))
    if topology.get("max_node_executions") is not None:
        builder.set_max_node_executions(int(topology["max_node_executions"]))
    if topology.get("execution_timeout") is not None:
        builder.set_execution_timeout(float(topology["execution_timeout"]))
    if topology.get("node_timeout") is not None:
        builder.set_node_timeout(float(topology["node_timeout"]))
    if topology.get("reset_on_revisit") is not None:
        builder.reset_on_revisit(bool(topology["reset_on_revisit"]))
    return builder.build()


class GraphManager:
    """Isolated per-instance manager for named Strands graphs."""

    def __init__(self) -> None:
        self._graphs: dict[str, Graph] = {}
        self._topologies: dict[str, dict[str, Any]] = {}

    def create(
        self,
        graph_id: str,
        topology: dict[str, Any],
        parent_agent: Agent | None = None,
    ) -> dict[str, Any]:
        if not graph_id:
            return {"status": "error", "content": [{"text": "graph_id is required"}]}
        if graph_id in self._graphs:
            return {"status": "error", "content": [{"text": f"Graph '{graph_id}' already exists"}]}
        try:
            compiled = build_graph(topology, parent_agent=parent_agent)
        except Exception as exc:
            return {"status": "error", "content": [{"text": f"Failed to build graph '{graph_id}': {exc}"}]}
        self._graphs[graph_id] = compiled
        self._topologies[graph_id] = topology
        return {
            "status": "success",
            "content": [{"text": f"Graph '{graph_id}' created with {len(compiled.nodes)} nodes."}],
        }

    def list(self) -> dict[str, Any]:
        ids = sorted(self._graphs.keys())
        text = f"Active graphs ({len(ids)}): {', '.join(ids)}" if ids else "No active graphs."
        return {"status": "success", "content": [{"text": text}]}

    def delete(self, graph_id: str) -> dict[str, Any]:
        if graph_id not in self._graphs:
            return {"status": "error", "content": [{"text": f"Graph '{graph_id}' not found"}]}
        del self._graphs[graph_id]
        self._topologies.pop(graph_id, None)
        return {"status": "success", "content": [{"text": f"Graph '{graph_id}' deleted."}]}

    def get(self, graph_id: str) -> Graph | None:
        return self._graphs.get(graph_id)


_DEFAULT_MANAGER = GraphManager()


@tool(name="graph")
async def graph(
    action: str,
    graph_id: str | None = None,
    topology: dict[str, Any] | None = None,
    task: str | None = None,
    agent: Any | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Create, execute, list, or delete heterogeneous Strands multi-agent graphs.

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
                _DEFAULT_MANAGER._graphs[graph_id] = g
                _DEFAULT_MANAGER._topologies[graph_id] = topology
        if g is None:
            yield {"status": "error", "content": [{"text": f"Graph '{graph_id}' not found"}]}
            return
        final_result = None
        async for event in g.stream_async(task or ""):
            yield event
            if isinstance(event, dict) and "result" in event:
                final_result = event["result"]
        yield {
            "status": "success",
            "content": [{"text": str(final_result) if final_result is not None else f"Graph '{graph_id or 'inline'}' completed."}],
        }
        return

    yield {"status": "error", "content": [{"text": f"Unknown action: {action}"}]}


__all__ = [
    "GraphManager",
    "SkillToolNode",
    "build_graph",
    "configure_models",
    "configure_skills",
    "graph",
]
