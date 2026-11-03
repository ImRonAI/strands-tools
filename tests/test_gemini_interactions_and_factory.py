# pyright: strict
"""Comprehensive tests for the Gemini Interactions API Strands integration, all 9 native
Interactions API tools, the capacity/bandwidth failover chain
(`gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite`), Agent Factory,
and Perplexity MCP Server surgical extraction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import google.genai as genai
import pydantic
import pytest
from google.genai import errors as genai_errors
from strands import Agent
from strands.models import ModelRouter
from strands.models.gemini_interactions import (
    NATIVE_INTERACTIONS_TOOL_TYPES,
    GeminiInteractionsModel,
    normalize_gemini_interactions_tools,
)
from strands.types.content import Messages
from strands.types.exceptions import ContextWindowOverflowException, ModelThrottledException
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec
from strands_graph_tool import build_agent_from_config, build_graph
from strands_harness import (
    GeminiCapacityFallbackStrategy,
    build_gemini_fallback_router,
    create_harness,
)
from strands_harness.defaults import DEFAULT_MODEL, GEMINI_FALLBACK_MODELS
from strands_harness.models import resolve_model

from agentskills import get_gemini_agent_model

REPO_ROOT = Path(__file__).resolve().parent.parent


def _format_model_request(
    model: GeminiInteractionsModel,
    *,
    messages: Messages,
    tool_specs: list[ToolSpec] | None = None,
    system_prompt: str | None = None,
    params: dict[str, object] | None = None,
    tool_choice: Mapping[str, object] | None = None,
) -> dict[str, object]:
    formatter = cast(
        Callable[..., dict[str, object]],
        getattr(model, "_format_request"),
    )
    return formatter(
        messages=messages,
        tool_specs=tool_specs,
        system_prompt=system_prompt,
        params=params,
        tool_choice=tool_choice,
    )


def _translate_model_exception(model: GeminiInteractionsModel, err: Exception) -> Exception:
    translator = cast(
        Callable[[Exception], Exception],
        getattr(model, "_translate_exception"),
    )
    return translator(err)


# ---------------------------------------------------------------------------
# 1. Perplexity Surgical Extraction Verification
# ---------------------------------------------------------------------------


def test_perplexity_extracted_to_perp_mcp_server_directory() -> None:
    perp_dir = REPO_ROOT / "Perp MCP Server"
    if perp_dir.exists():
        assert perp_dir.is_dir()
        assert (perp_dir / "strands_perplexity" / "mcp.py").is_file()
        assert (perp_dir / "strands_perplexity" / "agent.py").is_file()
        assert (perp_dir / "tests" / "test_strands_perplexity.py").is_file()
        assert (perp_dir / "openapi_specs" / "agenticResearch.yml").is_file()

    # Must no longer live in active src/tools or src/openapi_specs
    assert not (REPO_ROOT / "src" / "tools" / "strands_perplexity").exists()
    assert not (REPO_ROOT / "src" / "openapi_specs").exists()
    assert not (REPO_ROOT / "tests" / "test_strands_perplexity.py").exists()

    server_py = (REPO_ROOT / "packages" / "server" / "src" / "strands_server" / "server.py").read_text(
        encoding="utf-8"
    )
    assert "strands_perplexity" not in server_py
    assert "build_perplexity_server" not in server_py


# ---------------------------------------------------------------------------
# 2. All 9 Native Gemini Interactions API Tools Verification
# ---------------------------------------------------------------------------


def test_all_nine_native_interactions_api_tools_normalize_and_validate() -> None:
    expected_types = {
        "function",
        "google_search",
        "code_execution",
        "url_context",
        "computer_use",
        "file_search",
        "google_maps",
        "mcp_server",
        "retrieval",
    }
    assert NATIVE_INTERACTIONS_TOOL_TYPES == expected_types

    strands_tool_specs: list[ToolSpec] = [
        {
            "name": "calculate_roi",
            "description": "Calculate ROI from revenue and cost.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "revenue": {"type": "number"},
                        "cost": {"type": "number"},
                    },
                    "required": ["revenue", "cost"],
                }
            },
        }
    ]

    gemini_tools_config: list[str | Mapping[str, object]] = [
        "google_search",
        "code_execution",
        "url_context",
        {
            "type": "computer_use",
            "environment": "browser",
            "excludedPredefinedFunctions": ["drag_and_drop"],
        },
        {
            "type": "file_search",
            "file_search_store_names": ["fileSearchStores/store-alpha"],
            "top_k": 5,
            "metadata_filter": "tier=gold",
        },
        {
            "type": "google_maps",
            "enable_widget": True,
            "latitude": 37.7749,
            "longitude": -122.4194,
        },
        {
            "type": "mcp_server",
            "name": "brand_mcp",
            "url": "https://mcp.example.com/sse",
            "headers": {"Authorization": "Bearer secret"},
            "allowed_tools": [{"mode": "auto", "tools": ["lookup_brand"]}],
        },
        {
            "type": "retrieval",
            "search_types": ["vertex_ai_search"],
            "vertex_ai_search_config": {
                "datastores": ["projects/demo/locations/global/collections/default_collection/dataStores/ds1"],
                "engine": "projects/demo/locations/global/collections/default_collection/engines/eng1",
            },
        },
    ]

    model = GeminiInteractionsModel(
        model_id="gemini-4-argon",
        gemini_tools=gemini_tools_config,
    )
    request = _format_model_request(
        model,
        messages=[{"role": "user", "content": [{"text": "Run all tools."}]}],
        tool_specs=strands_tool_specs,
        system_prompt="You are a branding strategist.",
        tool_choice={"auto": {}},
    )

    tools_out = cast(list[dict[str, object]], request["tools"])
    assert len(tools_out) == 9
    observed_types = {cast(str, t["type"]) for t in tools_out}
    assert observed_types == expected_types

    fn_tool = next(t for t in tools_out if t["type"] == "function")
    assert fn_tool["name"] == "calculate_roi"
    fn_params = cast(Mapping[str, object], fn_tool["parameters"])
    assert fn_params["required"] == ["revenue", "cost"]

    cu_tool = next(t for t in tools_out if t["type"] == "computer_use")
    assert cu_tool["environment"] == "browser"
    assert cu_tool["excludedPredefinedFunctions"] == ["drag_and_drop"]

    fs_tool = next(t for t in tools_out if t["type"] == "file_search")
    assert fs_tool["file_search_store_names"] == ["fileSearchStores/store-alpha"]
    assert fs_tool["top_k"] == 5

    maps_tool = next(t for t in tools_out if t["type"] == "google_maps")
    assert maps_tool["enable_widget"] is True

    mcp_tool = next(t for t in tools_out if t["type"] == "mcp_server")
    assert mcp_tool["name"] == "brand_mcp"
    assert mcp_tool["url"] == "https://mcp.example.com/sse"

    ret_tool = next(t for t in tools_out if t["type"] == "retrieval")
    assert ret_tool["search_types"] == ["vertex_ai_search"]


def test_invalid_interactions_tool_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported shorthand Gemini Interactions tool"):
        normalize_gemini_interactions_tools(["not_a_gemini_tool"])
    with pytest.raises(ValueError, match="Unsupported Gemini Interactions tool type"):
        normalize_gemini_interactions_tools([{"type": "not_a_gemini_tool"}])


# ---------------------------------------------------------------------------
# 3. Stateless Multi-Turn Steps Replay & Tool Choice Formatting
# ---------------------------------------------------------------------------


def test_multiturn_stateless_steps_formatting_preserves_thought_signatures_and_tool_calls() -> None:
    model = GeminiInteractionsModel(
        model_id="gemini-3.8-flash",
        params={"temperature": 0.2, "max_output_tokens": 2048, "thinking_level": "high"},
    )
    messages: Messages = [
        {"role": "user", "content": [{"text": "Compute 6 * 7."}]},
        {
            "role": "assistant",
            "content": [
                {
                    "reasoningContent": {
                        "reasoningText": {
                            "text": "I should call the multiply tool.",
                            "signature": "sig-abc-123",
                        }
                    }
                },
                {
                    "toolUse": {
                        "toolUseId": "call_1",
                        "name": "multiply",
                        "input": {"a": 6, "b": 7},
                    }
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "call_1",
                        "status": "success",
                        "content": [{"json": {"product": 42}}],
                    }
                }
            ],
        },
    ]

    multiply_spec: list[ToolSpec] = [
        {
            "name": "multiply",
            "description": "Multiply two numbers.",
            "inputSchema": {"json": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}}},
        }
    ]

    request = _format_model_request(
        model,
        messages=messages,
        tool_specs=multiply_spec,
        system_prompt="Be concise.",
        params=model.get_config().get("params"),
        tool_choice={"tool": {"name": "multiply"}},
    )

    assert request["model"] == "gemini-3.8-flash"
    assert request["store"] is False
    assert request["system_instruction"] == "Be concise."
    steps = cast(list[dict[str, object]], request["input"])
    assert len(steps) == 4
    assert steps[0]["type"] == "user_input"
    assert steps[1]["type"] == "thought"
    assert steps[1]["signature"] == "sig-abc-123"
    assert steps[2]["type"] == "function_call"
    assert steps[2]["id"] == "call_1"
    assert steps[3]["type"] == "function_result"
    assert steps[3]["call_id"] == "call_1"
    assert steps[3]["result"] == {"product": 42}

    gen_cfg = cast(Mapping[str, object], request["generation_config"])
    assert gen_cfg["temperature"] == 0.2
    assert gen_cfg["max_output_tokens"] == 2048
    assert gen_cfg["thinking_level"] == "high"
    assert gen_cfg["tool_choice"] == {"allowed_tools": {"mode": "any", "tools": ["multiply"]}}


# ---------------------------------------------------------------------------
# 4. Streaming SSE Events & Structured Output
# ---------------------------------------------------------------------------


class _FakeInteractionsResource:
    def __init__(self, handler: Callable[..., Awaitable[object]]) -> None:
        self._handler = handler

    async def create(self, **kwargs: object) -> object:
        return await self._handler(**kwargs)


class _FakeClient:
    def __init__(self, handler: Callable[..., Awaitable[object]]) -> None:
        self.aio = SimpleNamespace(interactions=_FakeInteractionsResource(handler))


def _delta_dict(ev: StreamEvent) -> Mapping[str, object]:
    cbd = ev.get("contentBlockDelta")
    if isinstance(cbd, Mapping):
        delta = cbd.get("delta")
        if isinstance(delta, Mapping):
            return cast(Mapping[str, object], delta)
    return {}


async def test_gemini_interactions_stream_translates_sse_events_to_strands_events() -> None:
    sse_events: list[SimpleNamespace] = [
        SimpleNamespace(
            event_type="interaction.created",
            interaction=SimpleNamespace(id="inter_001"),
        ),
        SimpleNamespace(
            event_type="step.start",
            step=SimpleNamespace(type="thought"),
        ),
        SimpleNamespace(
            event_type="step.delta",
            delta=SimpleNamespace(
                type="thought_summary",
                part=SimpleNamespace(type="text", text="Thinking through the problem..."),
            ),
        ),
        SimpleNamespace(
            event_type="step.delta",
            delta=SimpleNamespace(
                type="thought_signature",
                signature="sig-xyz",
            ),
        ),
        SimpleNamespace(event_type="step.stop"),
        SimpleNamespace(
            event_type="step.start",
            step=SimpleNamespace(type="model_output"),
        ),
        SimpleNamespace(
            event_type="step.delta",
            delta=SimpleNamespace(
                type="text",
                text="Here is the grounded answer.",
            ),
        ),
        SimpleNamespace(
            event_type="step.delta",
            delta=SimpleNamespace(
                type="text_annotation_delta",
                annotations=[
                    SimpleNamespace(
                        start_index=0,
                        end_index=28,
                        source="https://ai.google.dev/gemini-api/docs/interactions",
                        title="Gemini Interactions API",
                    )
                ],
            ),
        ),
        SimpleNamespace(event_type="step.stop"),
        SimpleNamespace(
            event_type="step.start",
            step=SimpleNamespace(
                type="function_call",
                id="fc_101",
                name="lookup_brand",
                arguments=None,
            ),
        ),
        SimpleNamespace(
            event_type="step.delta",
            delta=SimpleNamespace(
                type="arguments_delta",
                arguments='{"brand": "Acme"}',
            ),
        ),
        SimpleNamespace(event_type="step.stop"),
        SimpleNamespace(
            event_type="interaction.completed",
            interaction=SimpleNamespace(
                id="inter_001",
                status="completed",
                usage=SimpleNamespace(
                    total_input_tokens=120,
                    total_output_tokens=45,
                    total_tokens=165,
                    total_cached_tokens=20,
                ),
            ),
        ),
    ]

    async def _fake_create(**kwargs: object) -> AsyncIterator[SimpleNamespace]:
        assert kwargs["model"] == "gemini-4-argon"
        assert kwargs["stream"] is True

        async def _gen() -> AsyncIterator[SimpleNamespace]:
            for item in sse_events:
                yield item

        return _gen()

    model = GeminiInteractionsModel(
        model_id="gemini-4-argon",
        client=cast(genai.Client, _FakeClient(_fake_create)),
    )

    events = [
        ev
        async for ev in model.stream(
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )
    ]

    assert events[0] == {"messageStart": {"role": "assistant"}}
    assert any(
        cast(Mapping[str, object], _delta_dict(ev).get("reasoningContent") or {}).get("text")
        == "Thinking through the problem..."
        for ev in events
    )
    assert any(
        cast(Mapping[str, object], _delta_dict(ev).get("reasoningContent") or {}).get("signature") == "sig-xyz"
        for ev in events
    )
    assert any(_delta_dict(ev).get("text") == "Here is the grounded answer." for ev in events)
    assert any("citation" in _delta_dict(ev) for ev in events)
    assert any(
        cast(
            Mapping[str, object],
            cast(Mapping[str, object], (ev.get("contentBlockStart") or {}).get("start") or {}).get("toolUse") or {},
        ).get("name")
        == "lookup_brand"
        for ev in events
    )
    assert any(
        cast(Mapping[str, object], _delta_dict(ev).get("toolUse") or {}).get("input") == '{"brand": "Acme"}'
        for ev in events
    )
    assert {"messageStop": {"stopReason": "tool_use"}} in events
    metadata_events = [ev for ev in events if "metadata" in ev]
    assert len(metadata_events) == 1
    meta_dict = cast(Mapping[str, object], metadata_events[0].get("metadata") or {})
    usage = cast(Mapping[str, object], meta_dict.get("usage") or {})
    assert usage.get("inputTokens") == 120
    assert usage.get("outputTokens") == 45
    assert usage.get("cacheReadInputTokens") == 20


async def test_gemini_interactions_structured_output_parses_pydantic_model() -> None:
    class BrandVerdict(pydantic.BaseModel):
        brand_name: str
        score: int

    async def _fake_create(**kwargs: object) -> SimpleNamespace:
        assert kwargs["stream"] is False
        assert kwargs["response_mime_type"] == "application/json"
        assert "response_format" in kwargs
        return SimpleNamespace(
            steps=[
                SimpleNamespace(
                    type="model_output",
                    content=[SimpleNamespace(type="text", text='{"brand_name": "Nova", "score": 95}')],
                )
            ]
        )

    model = GeminiInteractionsModel(
        model_id="gemini-3.8-flash",
        client=cast(genai.Client, _FakeClient(_fake_create)),
    )
    events = [
        ev
        async for ev in model.structured_output(
            BrandVerdict,
            [{"role": "user", "content": [{"text": "Score Nova."}]}],
        )
    ]
    assert len(events) == 1
    output = events[0]["output"]
    assert isinstance(output, BrandVerdict)
    assert output.brand_name == "Nova"
    assert output.score == 95


# ---------------------------------------------------------------------------
# 5. Failover Chain (`gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite`)
# ---------------------------------------------------------------------------


def test_default_model_and_fallback_order_constants() -> None:
    assert DEFAULT_MODEL == "google/gemini-4-argon"
    assert GEMINI_FALLBACK_MODELS == (
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    )


async def test_model_router_fails_over_on_bandwidth_or_capacity_errors_in_exact_order() -> None:
    attempted_models: list[str] = []

    def _make_client_for(expected_model: str, *, fail_status: int | None = None) -> _FakeClient:
        async def _handler(**kwargs: object) -> AsyncIterator[SimpleNamespace]:
            model_arg = kwargs.get("model")
            assert isinstance(model_arg, str)
            attempted_models.append(model_arg)
            if fail_status is not None:
                raise genai_errors.APIError(
                    fail_status,
                    {
                        "error": {
                            "code": fail_status,
                            "status": "RESOURCE_EXHAUSTED" if fail_status == 429 else "UNAVAILABLE",
                            "message": f"Model {expected_model} capacity/bandwidth exhausted ({fail_status})",
                        }
                    },
                )

            async def _gen() -> AsyncIterator[SimpleNamespace]:
                yield SimpleNamespace(
                    event_type="interaction.created",
                    interaction=SimpleNamespace(id=f"id_{expected_model}"),
                )
                yield SimpleNamespace(
                    event_type="step.start",
                    step=SimpleNamespace(type="model_output"),
                )
                yield SimpleNamespace(
                    event_type="step.delta",
                    delta=SimpleNamespace(
                        type="text",
                        text=f"Answered by {expected_model}",
                    ),
                )
                yield SimpleNamespace(event_type="step.stop")
                yield SimpleNamespace(
                    event_type="interaction.completed",
                    interaction=SimpleNamespace(id=f"id_{expected_model}", status="completed", usage=None),
                )

            return _gen()

        return _FakeClient(_handler)

    router = build_gemini_fallback_router()
    assert [c.name for c in router.candidates] == [
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]
    assert isinstance(getattr(router, "_strategy"), GeminiCapacityFallbackStrategy)

    # Inject fake clients: gemini-4-argon -> 429 RESOURCE_EXHAUSTED, gemini-3.8-flash -> 503 UNAVAILABLE,
    # gemini-3.5-flash-lite -> succeeds!
    setattr(router.candidates[0].model, "_custom_client", _make_client_for("gemini-4-argon", fail_status=429))
    setattr(router.candidates[1].model, "_custom_client", _make_client_for("gemini-3.8-flash", fail_status=503))
    setattr(router.candidates[2].model, "_custom_client", _make_client_for("gemini-3.5-flash-lite", fail_status=None))

    agent = Agent(model=router, retry_strategy=None, callback_handler=None)
    result = await agent.invoke_async("Test failover chain.")

    assert attempted_models == [
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]
    assert "Answered by gemini-3.5-flash-lite" in str(result)


async def test_model_router_does_not_fail_over_on_non_capacity_error() -> None:
    attempted_models: list[str] = []

    async def _bad_request_handler(**kwargs: object) -> AsyncIterator[SimpleNamespace]:
        model_arg = kwargs.get("model")
        assert isinstance(model_arg, str)
        attempted_models.append(model_arg)
        raise ValueError("Invalid tool schema in caller request")

    router = build_gemini_fallback_router()
    setattr(router.candidates[0].model, "_custom_client", _FakeClient(_bad_request_handler))

    agent = Agent(model=router, retry_strategy=None, callback_handler=None)
    with pytest.raises(ValueError, match="Invalid tool schema"):
        await agent.invoke_async("Should fail immediately without trying fallback models.")

    assert attempted_models == ["gemini-4-argon"]


def test_context_window_overflow_is_mapped_cleanly() -> None:
    model = GeminiInteractionsModel(model_id="gemini-4-argon")
    err = genai_errors.APIError(
        400,
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "Request input exceeds the maximum number of tokens allowed.",
            }
        },
    )
    mapped = _translate_model_exception(model, err)
    assert isinstance(mapped, ContextWindowOverflowException)

    throttled_err = genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded for metric.",
            }
        },
    )
    mapped_throttled = _translate_model_exception(model, throttled_err)
    assert isinstance(mapped_throttled, ModelThrottledException)


# ---------------------------------------------------------------------------
# 6. Agent Factory, Harness, Graph, and AgentSkills Integration
# ---------------------------------------------------------------------------


def test_create_harness_defaults_to_gemini_fallback_router_with_gemini_tools() -> None:
    agent = create_harness(
        instructions="Test harness agent.",
        gemini_tools=["google_search", "code_execution", "url_context"],
        builtin_tools=[],
        session=False,
        memory=False,
        skills=False,
    )
    router = getattr(agent, "_model_router")
    assert isinstance(router, ModelRouter)
    assert isinstance(agent.model, GeminiInteractionsModel)
    assert agent.model.get_config()["model_id"] == "gemini-4-argon"
    assert [c.name for c in router.candidates] == [
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]
    for candidate in router.candidates:
        assert isinstance(candidate.model, GeminiInteractionsModel)
        cfg_tools = candidate.model.get_config().get("gemini_tools")
        assert cfg_tools == ["google_search", "code_execution", "url_context"]


def test_resolve_model_supports_explicit_gemini_models_and_default_router() -> None:
    router = resolve_model(None, DEFAULT_MODEL)
    assert isinstance(router, ModelRouter)
    assert [c.name for c in router.candidates] == [
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]

    flash_model = resolve_model(
        "google/gemini-3.8-flash",
        DEFAULT_MODEL,
        gemini_tools=["google_search", "google_maps"],
    )
    assert isinstance(flash_model, GeminiInteractionsModel)
    assert flash_model.get_config()["model_id"] == "gemini-3.8-flash"
    assert flash_model.get_config().get("gemini_tools") == ["google_search", "google_maps"]


def test_build_agent_from_config_sdk_and_harness_engines_wire_gemini_and_tools() -> None:
    sdk_agent = build_agent_from_config(
        {
            "name": "brand_strategist",
            "system_prompt": "Analyze brand positioning.",
            "gemini_tools": ["google_search", "url_context", "code_execution"],
        }
    )
    sdk_router = getattr(sdk_agent, "_model_router")
    assert isinstance(sdk_router, ModelRouter)
    assert [c.name for c in sdk_router.candidates] == [
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]

    harness_agent = build_agent_from_config(
        {
            "name": "harness_strategist",
            "engine": "harness",
            "model": "google/gemini-3.8-flash",
            "system_prompt": "Execute brand research.",
            "include_default_tools": False,
            "skills": False,
            "gemini_tools": ["google_search", "google_maps"],
        }
    )
    assert isinstance(harness_agent.model, GeminiInteractionsModel)
    assert harness_agent.model.get_config()["model_id"] == "gemini-3.8-flash"
    assert harness_agent.model.get_config().get("gemini_tools") == ["google_search", "google_maps"]


def test_build_graph_nodes_default_to_gemini_router_and_accept_gemini_model_ids() -> None:
    g = build_graph(
        {
            "nodes": [
                {"id": "primary", "system_prompt": "Primary node."},
                {
                    "id": "fast",
                    "system_prompt": "Fast node.",
                    "model_id": "google/gemini-3.8-flash",
                    "gemini_tools": ["google_search"],
                },
            ],
            "edges": [{"from": "primary", "to": "fast"}],
        }
    )
    primary_exec = g.nodes["primary"].executor
    fast_exec = g.nodes["fast"].executor
    assert isinstance(primary_exec, Agent)
    assert isinstance(getattr(primary_exec, "_model_router"), ModelRouter)
    assert isinstance(primary_exec.model, GeminiInteractionsModel)
    assert primary_exec.model.get_config()["model_id"] == "gemini-4-argon"
    assert isinstance(fast_exec, Agent)
    assert isinstance(fast_exec.model, GeminiInteractionsModel)
    assert fast_exec.model.get_config()["model_id"] == "gemini-3.8-flash"


def test_agentskills_get_gemini_agent_model_returns_router_by_default() -> None:
    default_skill_model = get_gemini_agent_model(web_search=True)
    assert isinstance(default_skill_model, ModelRouter)
    assert [c.name for c in default_skill_model.candidates] == [
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    ]

    single_skill_model = get_gemini_agent_model("gemini-3.8-flash", web_search=True)
    assert isinstance(single_skill_model, GeminiInteractionsModel)
    assert single_skill_model.get_config()["model_id"] == "gemini-3.8-flash"
    assert single_skill_model.get_config().get("gemini_tools") == ["google_search"]
