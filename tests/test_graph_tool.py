# pyright: strict
"""Regression tests for the minimal async streaming graph tool.

Construction-only: no model or network calls. Executors are built and
inspected structurally, matching how the official strands_tools graph
tool is exercised without provider credentials.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast

import pytest
from strands import Agent
from strands.models.model import Model
from strands.multiagent import Swarm
from strands.multiagent.graph import Graph
from strands.types.content import Messages, SystemContentBlock
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolResult, ToolSpec

from strands_graph_tool import GraphManager, build_graph, configure_models, configure_skills, graph


def nested_topology() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "planner", "system_prompt": "Plan."},
            {
                "id": "team",
                "type": "swarm",
                "agents": [
                    {"id": "r1", "system_prompt": "Research."},
                    {"id": "r2", "system_prompt": "Review."},
                ],
            },
            {
                "id": "flow",
                "type": "workflow",
                "tasks": [
                    {"task_id": "a", "description": "Collect."},
                    {"task_id": "b", "description": "Analyze.", "dependencies": ["a"]},
                ],
            },
            {
                "id": "fan",
                "type": "parallel",
                "agents": [
                    {"id": "p1", "system_prompt": "One."},
                    {"id": "p2", "system_prompt": "Two."},
                ],
            },
            {
                "id": "inner",
                "type": "graph",
                "nodes": [{"id": "x", "system_prompt": "X."}],
            },
        ],
        "edges": [
            {"from": "planner", "to": "team"},
            {"from": "team", "to": "flow"},
            {"from": "flow", "to": "fan"},
            {"from": "fan", "to": "inner"},
        ],
    }


def test_nested_formations_compile_to_native_executors() -> None:
    g = build_graph(nested_topology())
    assert isinstance(g, Graph)
    assert type(g.nodes["planner"].executor) is Agent
    assert isinstance(g.nodes["team"].executor, Swarm)
    assert isinstance(g.nodes["flow"].executor, Graph)
    assert isinstance(g.nodes["fan"].executor, Graph)
    assert isinstance(g.nodes["inner"].executor, Graph)


def test_workflow_dependencies_become_nested_graph_edges() -> None:
    g = build_graph(nested_topology())
    flow = g.nodes["flow"].executor
    assert isinstance(flow, Graph)
    assert any(
        edge.from_node.node_id == "a" and edge.to_node.node_id == "b"
        for edge in flow.edges
    )


def test_parallel_agents_are_sibling_entry_nodes() -> None:
    g = build_graph(nested_topology())
    fan = g.nodes["fan"].executor
    assert isinstance(fan, Graph)
    assert set(fan.nodes) == {"p1", "p2"}
    assert not fan.edges


def test_parent_model_and_tools_inherit_like_the_official_tool() -> None:
    parent = Agent()
    g = build_graph({"nodes": [{"id": "solo", "system_prompt": "Solo."}]}, parent_agent=parent)
    solo_exec = g.nodes["solo"].executor
    assert isinstance(solo_exec, Agent)
    assert solo_exec.model is parent.model


def test_node_model_id_resolves_through_registered_factories() -> None:
    class StubModel(Model):
        def __init__(self, tag: str) -> None:
            self.tag = tag

        def update_config(self, **model_config: object) -> None:  # pragma: no cover
            del model_config

        def get_config(self) -> dict[str, object]:  # pragma: no cover
            return {}

        async def structured_output(
            self,
            output_model: object,
            prompt: Messages,
            system_prompt: str | None = None,
            **kwargs: object,
        ) -> AsyncGenerator[dict[str, object], None]:  # pragma: no cover
            del output_model, prompt, system_prompt, kwargs
            if False:
                yield {}
            raise NotImplementedError

        async def stream(
            self,
            messages: Messages,
            tool_specs: list[ToolSpec] | None = None,
            system_prompt: str | None = None,
            *,
            tool_choice: ToolChoice | None = None,
            system_prompt_content: list[SystemContentBlock] | None = None,
            **kwargs: object,
        ) -> AsyncGenerator[StreamEvent, None]:  # pragma: no cover
            del messages, tool_specs, system_prompt, tool_choice, system_prompt_content, kwargs
            if False:
                yield {}
            raise NotImplementedError

    configure_models({"alt/model": lambda: StubModel("alt")})
    parent = Agent()
    g = build_graph(
        {
            "nodes": [
                {"id": "inherit", "system_prompt": "I."},
                {"id": "override", "system_prompt": "O.", "model_id": "alt/model"},
            ]
        },
        parent_agent=parent,
    )
    inherit_exec = g.nodes["inherit"].executor
    override_exec = g.nodes["override"].executor
    assert isinstance(inherit_exec, Agent)
    assert isinstance(override_exec, Agent)
    assert inherit_exec.model is parent.model
    assert isinstance(override_exec.model, StubModel)
    assert override_exec.model.tag == "alt"

    with pytest.raises(ValueError, match="Unknown model_id"):
        build_graph(
            {"nodes": [{"id": "bad", "system_prompt": "?", "model_id": "nope"}]},
            parent_agent=parent,
        )
    configure_models({})


def test_swarm_members_are_uniquely_named_agents() -> None:
    g = build_graph(nested_topology())
    team = g.nodes["team"].executor
    assert isinstance(team, Swarm)
    assert set(team.nodes) == {"r1", "r2"}
    assert all(type(node.executor) is Agent for node in team.nodes.values())


def test_unknown_node_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown node type"):
        build_graph({"nodes": [{"id": "bad", "type": "mesh", "system_prompt": "?"}]})


def test_tool_is_registered_with_official_name() -> None:
    assert graph.tool_name == "graph"


async def _collect_graph_events(**kwargs: object) -> list[ToolResult]:
    tool_fn = cast(
        object,
        getattr(graph, "_tool_func"),
    )
    gen = cast(AsyncGenerator[ToolResult, None], getattr(tool_fn, "__call__")(**kwargs))
    return [e async for e in gen]


async def test_create_list_delete_stream_through_the_async_generator() -> None:
    events = await _collect_graph_events(action="create", graph_id="g1", topology=nested_topology())
    assert events[-1]["status"] == "success"

    events = await _collect_graph_events(action="create", graph_id="g1", topology=nested_topology())
    assert events[-1]["status"] == "error"  # duplicate id, official behavior

    events = await _collect_graph_events(action="list")
    assert "g1" in events[-1]["content"][0].get("text", "")

    events = await _collect_graph_events(action="delete", graph_id="g1")
    assert events[-1]["status"] == "success"

    events = await _collect_graph_events(action="delete", graph_id="g1")
    assert events[-1]["status"] == "error"  # already gone


async def test_execute_without_create_is_an_error_result() -> None:
    events = await _collect_graph_events(action="execute", graph_id="missing", task="run")
    assert events[-1]["status"] == "error"
    assert "not found" in events[-1]["content"][0].get("text", "")


async def test_unknown_action_is_an_error_result() -> None:
    events = await _collect_graph_events(action="pause")
    assert events[-1]["status"] == "error"
    assert "Unknown action" in events[-1]["content"][0].get("text", "")


def test_workflow_task_with_skill_compiles_to_skill_agent_node() -> None:
    import sys
    from pathlib import Path

    pkg = Path(__file__).parent.parent / "src/strands_tools/sessions_and_skills/sample_agent_skills"
    sys.path.insert(0, str(pkg))
    from agentskills import discover_skills

    skills_dir = Path(__file__).parent / "fixtures_skills"
    skill_dir = skills_dir / "wf-skill"
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: wf-skill\ndescription: Workflow test skill\n---\n# Body\n"
    )
    (skill_dir / "references" / "kb.md").write_text("knowledge")
    (skill_dir / "scripts" / "go.py").write_text("print('go')")

    class StubModel(Model):
        config: dict[str, object] = {}

        def update_config(self, **model_config: object) -> None:
            del model_config

        def get_config(self) -> dict[str, object]:
            return {}

        async def structured_output(
            self,
            output_model: object,
            prompt: Messages,
            system_prompt: str | None = None,
            **kwargs: object,
        ) -> AsyncGenerator[dict[str, object], None]:
            del output_model, prompt, system_prompt, kwargs
            if False:
                yield {}
            raise NotImplementedError

        async def stream(
            self,
            messages: Messages,
            tool_specs: list[ToolSpec] | None = None,
            system_prompt: str | None = None,
            *,
            tool_choice: ToolChoice | None = None,
            system_prompt_content: list[SystemContentBlock] | None = None,
            **kwargs: object,
        ) -> AsyncGenerator[StreamEvent, None]:
            del messages, tool_specs, system_prompt, tool_choice, system_prompt_content, kwargs
            if False:
                yield {}
            raise NotImplementedError

    configure_skills(discover_skills(str(skills_dir)), base_agent_model=StubModel())
    try:
        g = build_graph(
            {
                "nodes": [
                    {
                        "id": "flow",
                        "type": "workflow",
                        "tasks": [
                            {"task_id": "collect", "description": "Collect."},
                            {"task_id": "expert", "skill": "wf-skill", "dependencies": ["collect"]},
                        ],
                    }
                ]
            }
        )
        flow = g.nodes["flow"].executor
        assert isinstance(flow, Graph)
        expert_exec = flow.nodes["expert"].executor
        assert isinstance(expert_exec, Agent)
        prompt = expert_exec.system_prompt or ""
        assert str(skill_dir / "scripts" / "go.py") in prompt
        assert str(skill_dir / "references" / "kb.md") in prompt
        assert any(
            e.from_node.node_id == "collect" and e.to_node.node_id == "expert"
            for e in flow.edges
        )

        with pytest.raises(Exception, match="not found"):
            build_graph(
                {
                    "nodes": [
                        {
                            "id": "flow2",
                            "type": "workflow",
                            "tasks": [{"task_id": "bad", "skill": "no-such-skill"}],
                        }
                    ]
                }
            )
    finally:
        configure_skills([])


def test_manager_state_is_isolated_per_graph_id() -> None:
    manager = GraphManager()
    assert manager.create("a", {"nodes": [{"id": "n", "system_prompt": "N."}]})["status"] == "success"
    assert manager.create("a", {"nodes": [{"id": "n", "system_prompt": "N."}]})["status"] == "error"
    assert manager.delete("a")["status"] == "success"
    assert manager.delete("a")["status"] == "error"
