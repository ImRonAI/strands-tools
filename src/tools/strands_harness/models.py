"""Model resolution from ``provider/name`` strings, with per-provider reasoning config.

Consumers pass a ready ``Model`` instance, a ``"provider/name"`` string, a bare Bedrock model
id, or ``None`` for the harness default. Every provider uses its real model ids directly. The
``effort`` level is mapped to each provider's own request fields here, so the caller sets one
value regardless of provider.

Prompt caching is requested via ``caching`` and reaches the provider one of two ways: the harness
configures Bedrock and Anthropic direct (cache points plus cached tool definitions), while OpenAI,
Gemini, bedrock-mantle, and litellm cache automatically server-side (Gemini on models 2.5 and
newer; litellm through its OpenAI-compatible backend). Only a pre-built ``Model`` or ``ModelRouter``
instance can't be honored (its provider is unknown), so a warning is logged.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NamedTuple

import pydantic
from strands.models import FallbackStrategy, Model, ModelRouter, RoutingCandidate, RoutingContext
from strands.models.gemini_interactions import GeminiInteractionsModel, _is_capacity_or_bandwidth_error
from strands.types.exceptions import ModelThrottledException

from strands_harness import defaults
from strands_harness.types.agent import Effort

logger = logging.getLogger(__name__)

_ANTHROPIC_MAX_TOKENS = 32_000
# Claude calls the search directly (not from code execution), so results come back as citations
# and the tool works on every Claude model, not only those with programmatic tool calling. The
# type is a dated version; the current ones are listed at
# https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
_ANTHROPIC_WEB_SEARCH = {"type": "web_search_20260318", "name": "web_search", "allowed_callers": ["direct"]}

# Claude's real max_tokens ceiling by tier, verified live against Bedrock Converse. Applied on
# Bedrock and Anthropic-direct only — other Bedrock-hosted model families aren't known to need
# this. Matched as a substring so any Bedrock region/vendor prefix in front of it doesn't matter.
_CLAUDE_MAX_TOKENS = {
    "claude-opus-": 128_000,
    "claude-sonnet-": 128_000,
    "claude-haiku-": 128_000,
    "claude-fable-": 128_000,
}
_CLAUDE_MAX_TOKENS_BY_VERSION = (
    ("claude-opus-4-5", 64_000),
    ("claude-opus-4.5", 64_000),
    ("claude-sonnet-4-5", 64_000),
    ("claude-sonnet-4.5", 64_000),
    ("claude-haiku-4-5", 64_000),
    ("claude-haiku-4.5", 64_000),
)


def _claude_max_tokens(model_id: str) -> int | None:
    pinned = next((tokens for needle, tokens in _CLAUDE_MAX_TOKENS_BY_VERSION if needle in model_id), None)
    if pinned is not None:
        return pinned
    return next((tokens for needle, tokens in _CLAUDE_MAX_TOKENS.items() if needle in model_id), None)


# Small, fast model per provider for the web_fetch summarizer. Keyed by the main agent's provider
# so the summarizer shares its credentials.
_WEB_FETCH_MODELS = {
    "bedrock": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "bedrock-mantle": "openai.gpt-5.6-luna",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5.6-luna",
    "google": "gemini-3.5-flash-lite",
}

# Providers whose endpoint can be repointed by an env var. A non-default endpoint publishes its
# own model list, so the vended small summarizer is not guaranteed to exist on it.
_CUSTOM_ENDPOINT_VARS = {
    "anthropic": "ANTHROPIC_BASE_URL",
    "openai": "OPENAI_BASE_URL",
}

_BEDROCK_REGION_PREFIXES = ("global.", "apac.", "us.", "eu.", "au.", "jp.")

# Small regional summarizer per Bedrock model family, keyed by family prefix. These ids are served
# regionally, so unlike the OpenAI-on-Bedrock case no inference-profile prefix is carried over.
_BEDROCK_WEB_FETCH_FAMILY_MODELS = {
    "amazon.": "amazon.nova-lite-v1:0",
    "meta.": "meta.llama3-2-3b-instruct-v1:0",
    "mistral.": "mistral.mistral-small-2402-v1:0",
}


# Reasoning levels each provider's API accepts. The harness validates against the resolved
# provider's set so an unsupported level fails here rather than as a request error.
_ANTHROPIC_LEVELS = ("low", "medium", "high", "xhigh", "max")
_OPENAI_LEVELS = ("minimal", "low", "medium", "high", "xhigh", "none")
_BEDROCK_GPT_LEVELS = ("none", "low", "medium", "high", "xhigh", "max")
_BEDROCK_GPT_OSS_LEVELS = ("low", "medium", "high")
_BEDROCK_QWEN_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
_BEDROCK_XAI_LEVELS = ("low", "medium", "high", "xhigh")
_BEDROCK_NOVA_LEVELS = ("low", "medium", "high")
_GOOGLE_LEVELS = ("minimal", "low", "medium", "high")
_GOOGLE_NO_MINIMAL_MODELS = frozenset({"gemini-4-argon", "gemini-3.8-flash", "gemini-3-pro-preview", "gemini-3.1-pro-preview"})


def _google_levels(model_id: str) -> tuple[str, ...]:
    """Return the supported `thinking_level` values for a Gemini model ID."""
    if model_id in _GOOGLE_NO_MINIMAL_MODELS:
        return ("low", "medium", "high")
    return _GOOGLE_LEVELS


class GeminiCapacityFallbackStrategy(FallbackStrategy):
    """Failover strategy that switches models exclusively on native Gemini bandwidth or capacity errors.

    Ordered candidate failover (`gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite`)
    triggers only when the preceding attempt failed with `ModelThrottledException` (or a rate-limit /
    capacity / 429 / 503 / `RESOURCE_EXHAUSTED` / `UNAVAILABLE` error). Non-capacity errors return
    `None` so they surface immediately without masking invalid arguments or authentication failures.
    """

    async def select(self, context: RoutingContext, **kwargs: Any) -> RoutingCandidate | None:
        if context.attempts:
            last_attempt = context.attempts[-1]
            exc = last_attempt.exception
            if exc is not None:
                is_throttled = isinstance(exc, ModelThrottledException) or _is_capacity_or_bandwidth_error(
                    message=str(exc)
                )
                if not is_throttled:
                    return None
        return await super().select(context, **kwargs)


_ADAPTIVE_THINKING_SINCE = {"opus": (4, 6), "sonnet": (4, 6), "haiku": (5, 5)}
_EXTENDED_THINKING_SINCE = {"opus": (4, 5), "sonnet": (4, 5), "haiku": (4, 5)}
_CLAUDE_ID = re.compile(
    r"claude-(?:(\d{1,2})(?:[-.](\d{1,2}))?-)?(opus|sonnet|haiku|fable|mythos)"
    r"(?:[-.](\d{1,2}))?(?:[-.](\d{1,2}))?(?!\d)"
)
_EXTENDED_THINKING_BUDGETS = {"low": 2_048, "medium": 8_192, "high": 16_384, "xhigh": 32_768, "max": 49_152}


def _claude_thinking_mode(model_id: str) -> str | None:
    match = _CLAUDE_ID.search(model_id)
    if match is None:
        return "adaptive"
    lead_major, lead_minor, family, major, minor = match.groups()
    if major is None and lead_major is None:
        takes_adaptive = family not in _EXTENDED_THINKING_SINCE or family in _ADAPTIVE_THINKING_SINCE
        return "adaptive" if takes_adaptive else "extended"
    version = (int(major), int(minor or 0)) if major is not None else (int(lead_major), int(lead_minor or 0))
    if family not in _EXTENDED_THINKING_SINCE:
        return "adaptive"
    if version >= _ADAPTIVE_THINKING_SINCE.get(family, (99, 99)):
        return "adaptive"
    return "extended" if version >= _EXTENDED_THINKING_SINCE[family] else None


def _claude_thinking(effort: str) -> dict[str, Any]:
    return {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": effort},
    }


def _claude_extended_thinking(effort: str, max_tokens: int) -> dict[str, Any]:
    return {"thinking": {"type": "enabled", "budget_tokens": min(_EXTENDED_THINKING_BUDGETS[effort], max_tokens - 1)}}


def _claude_thinking_block(model_id: str, effort: str, max_tokens: int) -> dict[str, Any]:
    if _claude_thinking_mode(model_id) == "extended":
        return _claude_extended_thinking(effort, max_tokens)
    return _claude_thinking(effort)


def _bedrock_family(model_id: str) -> str:
    prefix = next((prefix for prefix in _BEDROCK_REGION_PREFIXES if model_id.startswith(prefix)), "")
    return model_id[len(prefix) :]


def _bedrock_levels(model_id: str) -> tuple[str, ...]:
    family = _bedrock_family(model_id)
    if family.startswith("anthropic."):
        return _ANTHROPIC_LEVELS if _claude_thinking_mode(family) is not None else ()
    if family.startswith("amazon.nova-2"):
        return _BEDROCK_NOVA_LEVELS
    if family.startswith("openai.gpt-5.6-") or family == "openai.gpt-6-astra":
        return _BEDROCK_GPT_LEVELS
    if family.startswith("openai.gpt-oss-"):
        return _BEDROCK_GPT_OSS_LEVELS
    if family.startswith("qwen."):
        return _BEDROCK_QWEN_LEVELS
    if family.startswith("xai."):
        return _BEDROCK_XAI_LEVELS
    return ()


def _bedrock_effort(model_id: str, effort: Effort) -> str | None:
    levels = _bedrock_levels(model_id)
    if levels:
        return _effort(effort, "high", levels, f"Bedrock model {model_id}")
    _check_effort(effort)
    if effort in ("auto", "off"):
        return None
    raise ValueError(f"Effort {effort!r} is not supported by Bedrock model {model_id}. Pass 'auto' or 'off'.")


def _bedrock_thinking(model_id: str, effort: str | None) -> dict[str, Any] | None:
    if effort is None:
        return None
    family = _bedrock_family(model_id)
    if family.startswith("anthropic."):
        return _claude_thinking_block(family, effort, _claude_max_tokens(model_id) or _ANTHROPIC_MAX_TOKENS)
    if family.startswith("amazon.nova-2"):
        return {"reasoningConfig": {"type": "enabled", "maxReasoningEffort": effort}}
    if family.startswith("openai.gpt-5.6-") or family == "openai.gpt-6-astra":
        return {"reasoning": {"effort": effort}}
    if family.startswith("openai.gpt-oss-"):
        return {"reasoning_effort": effort}
    if family.startswith("qwen."):
        return {"reasoning_effort": effort}
    if family.startswith("xai."):
        return {"reasoning_effort": effort}
    return None


def _bedrock(model_id: str, effort: str | None, web_search: bool, caching: bool) -> Model:
    from strands.models import BedrockModel, CacheConfig

    thinking = _bedrock_thinking(model_id, effort)
    extra: dict[str, Any] = {} if thinking is None else {"additional_request_fields": thinking}
    max_tokens = _claude_max_tokens(model_id)
    if max_tokens is not None:
        extra["max_tokens"] = max_tokens
    if caching:
        # The SDK injects cache points for Anthropic model ids on Bedrock (a no-op for others).
        # Tools are stable across turns, so cache them too.
        extra["cache_config"] = CacheConfig(strategy="auto", tools_ttl=True)
    return BedrockModel(model_id=model_id, **extra)


def _anthropic(model_id: str, effort: str | None, web_search: bool, caching: bool) -> Model:
    from strands.models import CacheConfig
    from strands.models.anthropic import AnthropicModel

    max_tokens = _claude_max_tokens(model_id) or _ANTHROPIC_MAX_TOKENS
    extra: dict[str, Any] = {} if effort is None else {"params": _claude_thinking_block(model_id, effort, max_tokens)}
    if web_search:
        extra["anthropic_tools"] = [_ANTHROPIC_WEB_SEARCH]
    if caching:
        # Caches the tool definitions plus a cache point on the last user message; the system
        # prompt is cached automatically. Mirrors the Bedrock builder.
        extra["cache_config"] = CacheConfig(strategy="auto", tools_ttl=True)
    return AnthropicModel(model_id=model_id, max_tokens=max_tokens, **extra)


def _openai(model_id: str, effort: str | None, web_search: bool, caching: bool) -> Model:
    # ``caching`` is unused: OpenAI caches server-side with no opt-in.
    from strands.models.openai_responses import OpenAIResponsesModel

    params: dict[str, Any] = {}
    if effort is not None:
        params["reasoning"] = {"effort": effort}
    # The Responses API merges built-in tools carried in ``params`` with the agent's function tools.
    if web_search:
        params["tools"] = [{"type": "web_search"}]
    if params:
        return OpenAIResponsesModel(model_id=model_id, params=params)
    return OpenAIResponsesModel(model_id=model_id)


def _bedrock_mantle(model_id: str, effort: str | None, web_search: bool, caching: bool) -> Model:
    # ``caching`` is unused: Mantle caches server-side automatically.
    from strands.models.openai_responses import BedrockMantleConfig, OpenAIResponsesModel

    params: dict[str, Any] = {} if effort is None else {"reasoning": {"effort": effort}}
    if web_search:
        params["tools"] = [{"type": "web_search", "external_web_access": True}]
    if params:
        return OpenAIResponsesModel(
            model_id=model_id,
            bedrock_mantle_config=BedrockMantleConfig(),
            params=params,
        )
    return OpenAIResponsesModel(model_id=model_id, bedrock_mantle_config=BedrockMantleConfig())


def _gemini(
    model_id: str,
    effort: str | None,
    web_search: bool,
    caching: bool,
    *,
    gemini_tools: Sequence[str | Mapping[str, Any] | pydantic.BaseModel] | None = None,
    client_args: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> GeminiInteractionsModel:
    # ``caching`` is unused: Gemini caches implicitly server-side.
    merged_params: dict[str, Any] = dict(params or {})
    if effort is not None:
        effective_level = "low" if (effort == "minimal" and model_id in _GOOGLE_NO_MINIMAL_MODELS) else effort
        gen_cfg = dict(merged_params.get("generation_config") or {})
        gen_cfg.setdefault("thinking_level", effective_level)
        gen_cfg.setdefault("thinking_summaries", "auto")
        merged_params["generation_config"] = gen_cfg

    tools_list: list[str | Mapping[str, Any] | pydantic.BaseModel] = list(gemini_tools or [])
    if web_search:
        has_google_search = any(
            (t == "google_search")
            or (isinstance(t, Mapping) and t.get("type") == "google_search")
            or (isinstance(t, pydantic.BaseModel) and getattr(t, "type", None) == "google_search")
            for t in tools_list
        )
        if not has_google_search:
            tools_list.insert(0, {"type": "google_search"})

    config_kwargs: dict[str, Any] = {}
    if merged_params:
        config_kwargs["params"] = merged_params
    if tools_list:
        config_kwargs["gemini_tools"] = tools_list

    return GeminiInteractionsModel(
        model_id=model_id,
        client_args=client_args,
        **config_kwargs,
    )


def build_gemini_fallback_router(
    *,
    models: Sequence[str] = defaults.GEMINI_FALLBACK_MODELS,
    effort: Effort = "auto",
    web_search: bool = False,
    gemini_tools: Sequence[str | Mapping[str, Any] | pydantic.BaseModel] | None = None,
    client_args: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> ModelRouter:
    """Build a Strands `ModelRouter` configured for Gemini Interactions API capacity/bandwidth failover.

    Routes in order: `gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite` using
    `GeminiCapacityFallbackStrategy` so failover happens exclusively on native Gemini rate-limit,
    bandwidth, or capacity errors (`ModelThrottledException`).
    """
    _check_effort(effort)
    effective_client_args: dict[str, Any] | None = dict(client_args) if client_args else None
    if api_key is not None:
        effective_client_args = dict(effective_client_args or {})
        effective_client_args["api_key"] = api_key

    effective_params: dict[str, Any] | None = dict(params) if params else None
    if temperature is not None or max_output_tokens is not None:
        effective_params = dict(effective_params or {})
        gen_cfg = dict(effective_params.get("generation_config") or {})
        if temperature is not None:
            gen_cfg["temperature"] = temperature
        if max_output_tokens is not None:
            gen_cfg["max_output_tokens"] = max_output_tokens
        effective_params["generation_config"] = gen_cfg

    candidates: list[RoutingCandidate] = []
    for candidate_id in models:
        stripped_id = candidate_id.removeprefix("google/")
        levels = _google_levels(stripped_id)
        if effort == "off":
            resolved_level: str | None = None
        elif effort == "auto":
            resolved_level = "high"
        elif effort == "minimal" and stripped_id in _GOOGLE_NO_MINIMAL_MODELS:
            resolved_level = "low"
        else:
            resolved_level = _effort(effort, "high", levels, f"Gemini model {stripped_id}")

        model_instance = _gemini(
            stripped_id,
            resolved_level,
            web_search,
            caching=True,
            gemini_tools=gemini_tools,
            client_args=effective_client_args,
            params=effective_params,
        )
        candidates.append(
            RoutingCandidate(
                model=model_instance,
                name=stripped_id,
                description=f"Google Gemini Interactions API model {stripped_id}",
            )
        )
    return ModelRouter(candidates, strategy=GeminiCapacityFallbackStrategy())


def _ollama(model_id: str, effort: str | None, web_search: bool, caching: bool) -> Model:
    from strands.models.ollama import OllamaModel

    # OLLAMA_API_KEY mirrors the TS builder, which sends it as a bearer token (for proxied hosts).
    api_key = os.environ.get("OLLAMA_API_KEY")
    client_args = {"headers": {"Authorization": f"Bearer {api_key}"}} if api_key else None
    return OllamaModel(
        host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        ollama_client_args=client_args,
        model_id=model_id,
    )


def _litellm(model_id: str, effort: str | None, web_search: bool, caching: bool) -> Model:
    # ``caching`` is unused: LiteLLM caches server-side via its OpenAI-compatible backend.
    from strands.models.litellm import LiteLLMModel

    api_key = os.environ.get("LITELLM_API_KEY")
    api_base = os.environ.get("LITELLM_BASE_URL")
    client_args = {
        **({"api_key": api_key} if api_key else {}),
        **({"api_base": api_base} if api_base else {}),
    }
    return LiteLLMModel(client_args=client_args, model_id=model_id)


class Provider(NamedTuple):
    """How one model provider is built and what reasoning/search/caching it supports."""

    build: Callable[[str, str | None, bool, bool], Model]
    recommended_thinking: str | None
    thinking_levels: tuple[str, ...]
    web_search: bool
    caching: bool


_PROVIDERS = {
    "bedrock": Provider(_bedrock, "high", _ANTHROPIC_LEVELS, web_search=False, caching=True),
    "bedrock-mantle": Provider(_bedrock_mantle, "high", _OPENAI_LEVELS, web_search=True, caching=True),
    "anthropic": Provider(_anthropic, "high", _ANTHROPIC_LEVELS, web_search=True, caching=True),
    "openai": Provider(_openai, "high", _OPENAI_LEVELS, web_search=True, caching=True),
    "google": Provider(_gemini, "high", _GOOGLE_LEVELS, web_search=True, caching=True),
    "ollama": Provider(_ollama, None, (), web_search=False, caching=False),
    "litellm": Provider(_litellm, None, (), web_search=False, caching=True),
}


EFFORT_LEVELS: tuple[Effort, ...] = ("auto", "off", "minimal", "low", "medium", "high", "xhigh", "max")


def _check_effort(effort: object) -> None:
    if effort in EFFORT_LEVELS:
        return
    raise ValueError(f"Unknown effort {effort!r}. Choose one of: {', '.join(EFFORT_LEVELS)}.")


def _effort(
    effort: Effort,
    recommended: str | None,
    levels: tuple[str, ...],
    subject: str = "this provider",
) -> str | None:
    """Map ``effort`` onto the provider's ``levels``; ``"off"`` is ``None`` where the provider has no ``none``."""
    _check_effort(effort)
    if effort == "off":
        return "none" if "none" in levels else None
    if effort == "auto":
        return recommended
    if effort in levels:
        return effort
    supported = [level for level in levels if level != "none"]
    detail = (
        f"Supported levels: {', '.join(supported)} (or 'auto', 'off')."
        if supported
        else "It supports no reasoning levels; pass 'auto' or 'off'."
    )
    raise ValueError(f"Effort {effort!r} is not supported by {subject}. {detail}")


def _split_provider(model: str) -> tuple[str, str]:
    """Split a ``"provider/name"`` string (or a bare Gemini / Bedrock id) into ``(provider, name)``."""
    provider_name, sep, name = model.partition("/")
    if not sep:
        if model.startswith("gemini-"):
            return "google", model
        return "bedrock", model
    return provider_name, name


def _require_or_warn(explicit: bool, error: str, warning: str) -> None:
    """Raise ``error`` when a feature was requested explicitly but can't be honored; otherwise
    (the feature is on only by default) log ``warning`` and let the caller build without it."""
    if explicit:
        raise ValueError(error)
    logger.warning(warning)


def _has_web_search(provider_name: str, name: str) -> bool:
    provider = _PROVIDERS.get(provider_name)
    if provider is None or not provider.web_search:
        return False
    # Bedrock Web Search is only served for Mantle's GPT-5/GPT-6 models; other families reject the tool (HTTP 400).
    return provider_name != "bedrock-mantle" or name.startswith(("openai.gpt-5.", "openai.gpt-6-", "openai.gpt-6."))


def supports_web_search(model: Model | ModelRouter | str | None) -> bool:
    """Whether native web search can be enabled for ``model``.

    A ``Model`` or ``ModelRouter`` instance has an unknown provider, so this is ``False``; the
    caller configures search on the instance directly. ``None`` resolves to the default model.
    """
    if isinstance(model, (Model, ModelRouter)):
        return False
    return _has_web_search(*_split_provider(model or defaults.DEFAULT_MODEL))


def supports_thinking(model: Model | str | None) -> bool:
    if isinstance(model, Model):
        return True
    provider_name, name = _split_provider(model or defaults.DEFAULT_MODEL)
    if provider_name == "bedrock":
        return bool(_bedrock_levels(name))
    if provider_name == "anthropic":
        return _claude_thinking_mode(name) is not None
    if provider_name == "google":
        return bool(_google_levels(name))
    provider = _PROVIDERS.get(provider_name)
    return provider is not None and bool(provider.thinking_levels)


def _supports_media(model: Model | ModelRouter | str | None) -> bool:
    """Whether ``model`` accepts image and document blocks in a tool result."""
    from strands.models import BedrockModel

    if isinstance(model, ModelRouter):
        return all(_supports_media(candidate.model) for candidate in model.candidates)
    if isinstance(model, BedrockModel):
        model_id = (model.get_config() or {}).get("model_id")
        return _supports_media(model_id) if isinstance(model_id, str) else True
    if isinstance(model, Model):
        return True
    provider_name, name = _split_provider(model or defaults.DEFAULT_MODEL)
    if provider_name == "bedrock":
        return not _bedrock_family(name).startswith("openai.")
    return True


def resolve_model(
    model: Model | ModelRouter | str | None,
    default: str,
    effort: Effort = "auto",
    web_search: bool = False,
    caching: bool = False,
    caching_explicit: bool = False,
    *,
    gemini_tools: Sequence[str | Mapping[str, Any] | pydantic.BaseModel] | None = None,
) -> Model | ModelRouter:
    """Resolve the ``model`` argument into a model or router instance.

    When ``model`` is ``None`` (or ``"google/gemini-4-argon"`` / ``"gemini-4-argon"`` when ``default``
    is ``defaults.DEFAULT_MODEL``), returns the 3-model ``ModelRouter`` (`gemini-4-argon` ->
    `gemini-3.8-flash` -> `gemini-3.5-flash-lite`) with ``GeminiCapacityFallbackStrategy`` so native
    Gemini bandwidth/capacity errors automatically fail over across the chain.
    """
    _check_effort(effort)
    if isinstance(model, (Model, ModelRouter)):
        instance = "a pre-built Model instance or ModelRouter"
        if effort != "auto":
            logger.warning("effort=%r not applied to %s; configure reasoning on the instance", effort, instance)
        if caching:
            logger.warning("prompt caching not applied to %s; configure it on the instance", instance)
        return model

    use_default_router = model is None and default == defaults.DEFAULT_MODEL
    if model is None:
        model = default

    provider_name, name = _split_provider(model)

    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unknown model provider {provider_name!r} in {model!r}. Supported providers: {supported}. "
            "Pass a strands.models.Model instance for anything else."
        )

    if caching and not provider.caching:
        supported = ", ".join(p for p, cfg in _PROVIDERS.items() if cfg.caching)
        _require_or_warn(
            caching_explicit,
            f"Provider {provider_name!r} does not support prompt caching. "
            f"Providers with caching: {supported}. Pass caching=False, "
            "or switch to a supported provider.",
            f"provider=<{provider_name}> | prompt caching not supported by this provider; continuing without it",
        )
    unsupported_caching = provider_name == "bedrock" and _bedrock_family(name).startswith("anthropic.claude-3-haiku-")
    if caching and unsupported_caching:
        _require_or_warn(
            caching_explicit,
            f"Model {provider_name}/{name} does not support prompt caching. Pass caching=False.",
            f"model=<{provider_name}/{name}> | prompt caching not supported by this model; continuing without it",
        )

    native_search = web_search and _has_web_search(provider_name, name)

    if provider_name == "google":
        levels = _google_levels(name)
        level = _effort(effort, provider.recommended_thinking, levels, f"Gemini model {name}")
        if use_default_router or (name == "gemini-4-argon" and default == defaults.DEFAULT_MODEL):
            return build_gemini_fallback_router(
                effort=effort,
                web_search=native_search,
                gemini_tools=gemini_tools,
            )
        return _gemini(
            name,
            level,
            native_search,
            caching and provider.caching,
            gemini_tools=gemini_tools,
        )

    levels = provider.thinking_levels
    recommended = provider.recommended_thinking
    subject = "this provider"
    if provider_name == "anthropic" and _claude_thinking_mode(name) is None:
        levels, recommended, subject = (), None, f"model {name}"
    if provider_name == "bedrock":
        level = _bedrock_effort(name, effort)
    else:
        level = _effort(effort, recommended, levels, subject)
    return provider.build(name, level, native_search, caching and provider.caching and not unsupported_caching)


def _bedrock_web_fetch_model(name: str) -> str | None:
    """Small Bedrock summarizer id for a Bedrock main model ``name``, or ``None`` if the family is
    unidentifiable."""
    family = _bedrock_family(name)
    if family.startswith("anthropic."):
        return _WEB_FETCH_MODELS["bedrock"]
    if family.startswith("openai."):
        prefix = name[: len(name) - len(family)]
        return f"{prefix}openai.{_WEB_FETCH_MODELS['openai']}"
    return next(
        (small for fam_prefix, small in _BEDROCK_WEB_FETCH_FAMILY_MODELS.items() if family.startswith(fam_prefix)),
        None,
    )


def resolve_web_fetch_model(
    main_model: Model | ModelRouter | str | None,
    web_fetch_model: Model | ModelRouter | str | None,
) -> Model:
    """Resolve the model the web_fetch summarizer runs on."""
    if isinstance(web_fetch_model, ModelRouter):
        return web_fetch_model.default_model
    if isinstance(web_fetch_model, Model):
        return web_fetch_model
    if web_fetch_model is not None:
        return _concrete_model(resolve_model(web_fetch_model, web_fetch_model, effort="off"))

    if isinstance(main_model, ModelRouter):
        return main_model.default_model
    if isinstance(main_model, Model):
        return main_model
    main = main_model if main_model is not None else defaults.DEFAULT_MODEL
    provider_name, name = _split_provider(main)
    if provider_name == "bedrock":
        small = _bedrock_web_fetch_model(name)
        if small is None:
            logger.warning(
                f"model=<{main}> | could not identify the Bedrock model family for the web_fetch "
                "summarizer; reusing the main model. Set builtin_tools={'web_fetch': {'model': ...}} to choose a "
                "smaller one."
            )
            return _concrete_model(resolve_model(main, main, effort="off"))
    elif (base_url_var := _CUSTOM_ENDPOINT_VARS.get(provider_name)) and os.environ.get(base_url_var):
        logger.warning(
            f"model=<{main}> | {base_url_var} points provider <{provider_name}> at a non-default "
            "endpoint, which serves its own model list, so the vended summarizer may not exist "
            "there; reusing the main model. Pass web_fetch_model to choose a smaller one."
        )
        return _concrete_model(resolve_model(main, main, effort="off"))
    else:
        small = _WEB_FETCH_MODELS.get(provider_name)
    if small is None:
        if provider_name in ("ollama", "litellm"):
            logger.warning(
                f"model=<{main}> | no separate web_fetch summarizer is configured for provider "
                f"<{provider_name}>; reusing the main model. Set builtin_tools={{'web_fetch': {{'model': ...}}}} "
                "to choose another model."
            )
            return _concrete_model(resolve_model(main, main, effort="off"))
        raise ValueError(
            f"No default web_fetch model for provider {provider_name!r}. "
            "Set builtin_tools={'web_fetch': {'model': ...}} explicitly, or disable web_fetch via builtin_tools."
        )
    return _concrete_model(resolve_model(f"{provider_name}/{small}", small, effort="off"))


def _concrete_model(model: Model | ModelRouter) -> Model:
    return model.default_model if isinstance(model, ModelRouter) else model
