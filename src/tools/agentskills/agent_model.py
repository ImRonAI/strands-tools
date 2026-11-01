# pyright: strict
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from strands.models import BedrockModel, ModelRouter
from strands.models.gemini_interactions import GeminiInteractionsModel
from strands_harness.models import build_gemini_fallback_router
from strands_harness.types.agent import Effort

_EFFORT_TO_THINKING_LEVEL: dict[str, str] = {
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def get_bedrock_agent_model(
    model_id: str = "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    temperature: float = 1,
    max_tokens: int = 24000,
    thinking: bool = False,
    budget_tokens: int | None = None,
) -> BedrockModel:
    additional_request_fields: dict[str, Any] = {}

    if thinking:
        additional_request_fields["thinking"] = {
            "type": "enabled",
            "budget_tokens": budget_tokens if budget_tokens else 1024,
        }
        additional_request_fields["anthropic_beta"] = [
            "interleaved-thinking-2025-05-14",
            "fine-grained-tool-streaming-2025-05-14",
        ]

    agent_model = BedrockModel(
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        cache_tools="default",
        additional_request_fields=additional_request_fields if additional_request_fields else None,
    )
    return agent_model


def get_gemini_agent_model(
    model: str | None = None,
    *,
    effort: Effort = "auto",
    web_search: bool = False,
    gemini_tools: Sequence[Any] | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    api_key: str | None = None,
) -> GeminiInteractionsModel | ModelRouter:
    """Build the default Gemini Interactions API model or failover ModelRouter for AgentSkills sub-agents.

    When `model` is omitted or `"gemini-4-argon"` / `"google/gemini-4-argon"`, returns a Strands
    `ModelRouter` configured with the ordered capacity/bandwidth failover chain:
    `gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite`.
    """
    normalized = (model or "").strip()
    if not normalized or normalized in ("gemini-4-argon", "google/gemini-4-argon", "gemini/gemini-4-argon"):
        return build_gemini_fallback_router(
            effort=effort,
            web_search=web_search,
            gemini_tools=gemini_tools,
            api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    clean_id = (
        normalized.split("/", 1)[1]
        if normalized.startswith(("google/", "gemini/"))
        else normalized
    )
    params: dict[str, Any] = {}
    if effort != "auto" and effort in _EFFORT_TO_THINKING_LEVEL:
        params["thinking_level"] = _EFFORT_TO_THINKING_LEVEL[effort]
    if temperature is not None:
        params["temperature"] = temperature
    if max_output_tokens is not None:
        params["max_output_tokens"] = max_output_tokens

    tools_list: list[Any] = list(gemini_tools) if gemini_tools else []
    if web_search:
        tools_list.append("google_search")

    client_args: dict[str, Any] | None = {"api_key": api_key} if api_key else None
    return GeminiInteractionsModel(
        model_id=clean_id,
        params=params or None,
        gemini_tools=tools_list or None,
        client_args=client_args,
    )


