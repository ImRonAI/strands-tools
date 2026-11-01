"""Regression tests for the minimal async streaming graph tool.

Construction-only: no model or network calls. Executors are built and
inspected structurally, matching how the official strands_tools graph
tool is exercised without provider credentials.
"""

from __future__ import annotations

from strands import Agent
from strands.multiagent import Swarm
from strands.multiagent.graph import Graph

from strands_graph_tool import GraphManager, build_graph, graph


def nested_topology() -> dict:
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
    assert any(
        edge.from_node.node_id == "a" and edge.to_node.node_id == "b"
        for edge in flow.edges
    )


def test_parallel_agents_are_sibling_entry_nodes() -> None:
    g = build_graph(nested_topology())
    fan = g.nodes["fan"].executor
    assert set(fan.nodes) == {"p1", "p2"}
    assert not fan.edges


def test_parent_model_and_tools_inherit_like_the_official_tool() -> None:
    parent = Agent()
    g = build_graph({"nodes": [{"id": "solo", "system_prompt": "Solo."}]}, parent_agent=parent)
    assert g.nodes["solo"].executor.model is parent.model


def test_node_model_id_resolves_through_registered_factories() -> None:
    from strands.models.model import Model

    from strands_graph_tool import configure_models

    class StubModel(Model):
        def __init__(self, tag: str) -> None:
            self.tag = tag

        def update_config(self, **kwargs):  # pragma: no cover
            pass

        def get_config(self):  # pragma: no cover
            return {}

        async def structured_output(self, *a, **k):  # pragma: no cover
            raise NotImplementedError
            yield

        async def stream(self, *a, **k):  # pragma: no cover
            raise NotImplementedError
            yield

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
    assert g.nodes["inherit"].executor.model is parent.model
    assert g.nodes["override"].executor.model.tag == "alt"

    import pytest

    with pytest.raises(ValueError, match="Unknown model_id"):
        build_graph(
            {"nodes": [{"id": "bad", "system_prompt": "?", "model_id": "nope"}]},
            parent_agent=parent,
        )
    configure_models({})


def test_swarm_members_are_uniquely_named_agents() -> None:
    g = build_graph(nested_topology())
    team = g.nodes["team"].executor
    assert set(team.nodes) == {"r1", "r2"}
    assert all(type(node.executor) is Agent for node in team.nodes.values())


def test_unknown_node_type_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unknown node type"):
        build_graph({"nodes": [{"id": "bad", "type": "mesh", "system_prompt": "?"}]})


def test_tool_is_registered_with_official_name() -> None:
    assert graph.tool_name == "graph"


async def test_create_list_delete_stream_through_the_async_generator() -> None:
    events = [e async for e in graph._tool_func(action="create", graph_id="g1", topology=nested_topology())]
    assert events[-1]["status"] == "success"

    events = [e async for e in graph._tool_func(action="create", graph_id="g1", topology=nested_topology())]
    assert events[-1]["status"] == "error"  # duplicate id, official behavior

    events = [e async for e in graph._tool_func(action="list")]
    assert "g1" in events[-1]["content"][0]["text"]

    events = [e async for e in graph._tool_func(action="delete", graph_id="g1")]
    assert events[-1]["status"] == "success"

    events = [e async for e in graph._tool_func(action="delete", graph_id="g1")]
    assert events[-1]["status"] == "error"  # already gone


async def test_execute_without_create_is_an_error_result() -> None:
    events = [e async for e in graph._tool_func(action="execute", graph_id="missing", task="run")]
    assert events[-1]["status"] == "error"
    assert "not found" in events[-1]["content"][0]["text"]


async def test_unknown_action_is_an_error_result() -> None:
    events = [e async for e in graph._tool_func(action="pause")]
    assert events[-1]["status"] == "error"
    assert "Unknown action" in events[-1]["content"][0]["text"]


def test_workflow_task_with_skill_compiles_to_skill_agent_node() -> None:
    import sys
    from pathlib import Path

    import pytest

    pkg = Path(__file__).parent.parent / "src/strands_tools/sessions_and_skills/sample_agent_skills"
    sys.path.insert(0, str(pkg))
    from agentskills import discover_skills

    from strands_graph_tool import configure_skills

    skills_dir = Path(__file__).parent / "fixtures_skills"
    skill_dir = skills_dir / "wf-skill"
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: wf-skill\ndescription: Workflow test skill\n---\n# Body\n"
    )
    (skill_dir / "references" / "kb.md").write_text("knowledge")
    (skill_dir / "scripts" / "go.py").write_text("print('go')")

    class StubModel:
        config: dict = {}
        stateful = False

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
        prompt = flow.nodes["expert"].executor.system_prompt
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
