# pyright: strict
"""Google Gemini Interactions API model provider.

Implements the Strands `Model` interface against the native Gemini Interactions API
(`client.aio.interactions.create`) in `google-genai>=2.0.0` for Gemini API Studio
(`GEMINI_API_KEY`). Does not use Gemini Live / bidi streaming.

Supports all 9 native Gemini Interactions API tool types:
1. `function` (`FunctionParam` — auto-mapped from Strands `tool_specs` and/or `gemini_tools`)
2. `google_search` (`GoogleSearchParam`)
3. `code_execution` (`CodeExecutionParam`)
4. `url_context` (`URLContextParam`)
5. `computer_use` (`ComputerUseParam`)
6. `file_search` (`FileSearchParam`)
7. `google_maps` (`GoogleMapsParam`)
8. `mcp_server` (`MCPServerParam`)
9. `retrieval` (`RetrievalParam`)

- Docs: https://ai.google.dev/gemini-api/docs/interactions
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import secrets
from collections.abc import AsyncGenerator, AsyncIterable, Mapping, Sequence
from typing import Any, Literal, TypeVar, cast

import pydantic
import google.genai as genai
from google.genai import errors as genai_errors
from google.genai._gaos.lib import compat_errors
from typing_extensions import Required, Unpack, override

from ..types.citations import WebLocation
from ..types.content import ContentBlock, ContentBlockStartToolUse, Messages, SystemContentBlock
from ..types.event_loop import StopReason, Usage
from ..types.exceptions import ContextWindowOverflowException, ModelThrottledException, ProviderTokenCountError
from ..types.streaming import CitationsDelta, StreamEvent
from ..types.tools import ToolChoice, ToolChoiceToolDict, ToolSpec
from ._defaults import resolve_config_metadata
from ._validation import validate_config_keys
from .model import BaseModelConfig, Model

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=pydantic.BaseModel)

NATIVE_INTERACTIONS_TOOL_TYPES: frozenset[str] = frozenset(
    {
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
)

_SHORTHAND_TOOL_TYPES: frozenset[str] = frozenset(
    {
        "google_search",
        "code_execution",
        "url_context",
        "computer_use",
        "google_maps",
    }
)

_VIDEO_MIME_TYPES: dict[str, str] = {
    "flv": "video/x-flv",
    "mkv": "video/x-matroska",
    "mov": "video/quicktime",
    "mpeg": "video/mpeg",
    "mpg": "video/mpeg",
    "mp4": "video/mp4",
    "three_gp": "video/3gpp",
    "webm": "video/webm",
    "wmv": "video/x-ms-wmv",
}

_AUDIO_MIME_TYPES: dict[str, str] = {
    "aac": "audio/aac",
    "flac": "audio/flac",
    "mp3": "audio/mp3",
    "m4a": "audio/mp4",
    "mpeg": "audio/mpeg",
    "mpga": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "pcm": "audio/pcm",
    "wav": "audio/wav",
    "webm": "audio/webm",
}

_CAPACITY_KEYWORDS: tuple[str, ...] = (
    "resource_exhausted",
    "rate_limit",
    "ratelimit",
    "quota",
    "too many requests",
    "too_many_requests",
    "unavailable",
    "overloaded",
    "capacity",
    "bandwidth",
    "server_overloaded",
)


def _get_field(obj: object, key: str) -> Any:
    """Safely read `key` from either a Mapping or an attribute-bearing object."""
    if isinstance(obj, Mapping):
        typed_map = cast(Mapping[str, Any], obj)
        return typed_map.get(key)
    return getattr(obj, key, None)


def _get_str(obj: object, key: str) -> str | None:
    """Read a non-empty string field `key` from `obj`, or return None."""
    val = _get_field(obj, key)
    return val if isinstance(val, str) and val else None


def _get_int(obj: object, key: str) -> int:
    """Read an integer field `key` from `obj`, defaulting to 0."""
    val = _get_field(obj, key)
    if isinstance(val, int):
        return val
    return 0


def _get_list(obj: object, key: str) -> list[Any]:
    """Read a sequence field `key` from `obj` as a list."""
    val = _get_field(obj, key)
    if isinstance(val, list):
        return cast(list[Any], val)
    return []


def _block_has_location_source(content: ContentBlock) -> bool:
    """Return True if a media content block uses a provider-specific `location` source."""
    for media_key in ("document", "image", "video"):
        if media_key in content:
            media_block = cast(Mapping[str, Any], content.get(media_key) or {})
            source = cast(Mapping[str, Any], media_block.get("source") or {})
            if "location" in source:
                return True
    return False


def normalize_gemini_interactions_tools(
    gemini_tools: Sequence[str | Mapping[str, object] | pydantic.BaseModel] | None,
) -> list[dict[str, object]]:
    """Normalize and validate native Gemini Interactions API tool specifications.

    Accepts:
    - Shorthand strings for zero-required-arg native tools:
      `"google_search"`, `"code_execution"`, `"url_context"`, `"computer_use"`, `"google_maps"`
    - Typed dictionaries matching any of the 9 native Interactions API tool schemas:
      `function`, `google_search`, `code_execution`, `url_context`, `computer_use`,
      `file_search`, `google_maps`, `mcp_server`, `retrieval`
    - `google.genai._gaos.types.interactions` Pydantic tool models (`GoogleSearch`, `CodeExecution`,
      `URLContext`, `ComputerUse`, `FileSearch`, `GoogleMaps`, `MCPServer`, `Retrieval`, `Function`)

    Args:
        gemini_tools: Sequence of tool configurations to normalize.

    Returns:
        List of Interactions API tool dictionaries ready for `client.aio.interactions.create`.

    Raises:
        ValueError: If any tool has an unknown or unsupported `type`.
    """
    if not gemini_tools:
        return []

    normalized: list[dict[str, object]] = []
    for item in gemini_tools:
        if isinstance(item, str):
            tool_type = item.strip()
            if tool_type not in _SHORTHAND_TOOL_TYPES:
                raise ValueError(
                    f"Unsupported shorthand Gemini Interactions tool {item!r}. "
                    f"Shorthand strings must be one of {sorted(_SHORTHAND_TOOL_TYPES)}; "
                    f"pass a dict for parameterized tools ({sorted(NATIVE_INTERACTIONS_TOOL_TYPES)})."
                )
            if tool_type == "computer_use":
                normalized.append({"type": "computer_use", "environment": "browser"})
            else:
                normalized.append({"type": tool_type})
            continue

        if isinstance(item, pydantic.BaseModel):
            dumped = item.model_dump(exclude_none=True, by_alias=True)
            tool_type_obj = dumped.get("type")
            if not isinstance(tool_type_obj, str) or tool_type_obj not in NATIVE_INTERACTIONS_TOOL_TYPES:
                raise ValueError(
                    f"Unsupported Gemini Interactions tool model type {tool_type_obj!r}. "
                    f"Must be one of {sorted(NATIVE_INTERACTIONS_TOOL_TYPES)}."
                )
            normalized.append(dumped)
            continue

        tool_dict = dict(item)
        tool_type_val = tool_dict.get("type")
        if not isinstance(tool_type_val, str) or tool_type_val not in NATIVE_INTERACTIONS_TOOL_TYPES:
            raise ValueError(
                f"Unsupported Gemini Interactions tool type {tool_type_val!r}. "
                f"Must be one of {sorted(NATIVE_INTERACTIONS_TOOL_TYPES)}."
            )
        if tool_type_val == "computer_use":
            tool_dict.setdefault("environment", "browser")
            if "excluded_predefined_functions" in tool_dict and "excludedPredefinedFunctions" not in tool_dict:
                tool_dict["excludedPredefinedFunctions"] = tool_dict.pop("excluded_predefined_functions")
        normalized.append(tool_dict)

    return normalized


def _is_capacity_or_bandwidth_error(
    *,
    status_code: int | None = None,
    status_text: str | None = None,
    message: str | None = None,
) -> bool:
    """Return True if an error from the Gemini API indicates bandwidth, rate-limit, or capacity exhaustion."""
    if status_code in (429, 503):
        return True
    combined = f"{status_text or ''} {message or ''}".lower()
    return any(keyword in combined for keyword in _CAPACITY_KEYWORDS)


class GeminiInteractionsModel(Model):
    """Google Gemini Interactions API model provider implementation.

    Uses `client.aio.interactions.create(...)` from `google-genai>=2.0.0` on regular Gemini API Studio.
    Stateless by default (`stateful=False`, `store=False`) so Strands' `ModelRouter` can seamlessly
    fail over across models (`gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite`)
    on multi-turn conversations while preserving `thought_signature`s.
    """

    class GeminiInteractionsConfig(BaseModelConfig, total=False):
        """Configuration options for Gemini Interactions API models.

        Attributes:
            model_id: Gemini model ID (e.g., `"gemini-4-argon"`, `"gemini-3.8-flash"`, `"gemini-3.5-flash-lite"`).
            params: Additional request or `generation_config` parameters (e.g., `temperature`, `max_output_tokens`,
                `thinking_level`, `thinking_summaries`, `top_p`, `stop_sequences`, `seed`, `service_tier`,
                `safety_settings`, `response_modalities`).
            gemini_tools: Native Gemini Interactions API tools (`google_search`, `code_execution`, `url_context`,
                `computer_use`, `file_search`, `google_maps`, `mcp_server`, `retrieval`, or `function`).
            stateful: Whether to enable server-side state via `store=True` and `previous_interaction_id`.
                Defaults to `False` so `ModelRouter` can route across fallback models seamlessly.
            use_native_token_count: Whether to use the native Gemini `count_tokens` API when estimating tokens.
        """

        model_id: Required[str]
        params: dict[str, object] | None
        gemini_tools: Sequence[str | Mapping[str, object] | pydantic.BaseModel] | None
        stateful: bool
        use_native_token_count: bool

    def __init__(
        self,
        *,
        client: genai.Client | None = None,
        client_args: dict[str, Any] | None = None,
        **model_config: Unpack[GeminiInteractionsConfig],
    ) -> None:
        """Initialize a GeminiInteractionsModel provider instance.

        Args:
            client: Pre-configured `google.genai.Client` instance to reuse across requests.
            client_args: Arguments passed to `google.genai.Client(**client_args)` when `client` is not provided.
                Defaults to reading `GEMINI_API_KEY` or `GOOGLE_API_KEY` from the environment.
            **model_config: Configuration options for the Gemini Interactions model.

        Raises:
            ValueError: If both `client` and non-empty `client_args` are provided, or if `gemini_tools` is invalid.
        """
        validate_config_keys(model_config, GeminiInteractionsModel.GeminiInteractionsConfig)
        self.config = GeminiInteractionsModel.GeminiInteractionsConfig(**model_config)

        if client is not None and client_args is not None and len(client_args) > 0:
            raise ValueError("Only one of 'client' or 'client_args' should be provided, not both.")

        self._custom_client = client
        self.client_args = dict(client_args or {})
        self._last_interaction_id: str | None = None

        if "gemini_tools" in self.config:
            normalize_gemini_interactions_tools(self.config["gemini_tools"])

        logger.debug("config=<%s> | initializing GeminiInteractionsModel", self.config)

    @property
    @override
    def stateful(self) -> bool:
        """Whether this model instance manages conversation state server-side via `previous_interaction_id`."""
        return bool(self.config.get("stateful", False))

    @property
    def last_interaction_id(self) -> str | None:
        """Return the ID of the most recently completed or created interaction, if any."""
        return self._last_interaction_id

    @override
    def update_config(self, **model_config: Unpack[GeminiInteractionsConfig]) -> None:  # type: ignore[override]
        """Update the Gemini Interactions model configuration with the provided arguments."""
        validate_config_keys(model_config, GeminiInteractionsModel.GeminiInteractionsConfig)
        if "gemini_tools" in model_config:
            normalize_gemini_interactions_tools(model_config["gemini_tools"])
        self.config.update(model_config)

    @override
    def get_config(self) -> GeminiInteractionsConfig:
        """Return the resolved Gemini Interactions model configuration."""
        return resolve_config_metadata(self.config, self.config["model_id"])

    def _get_client(self) -> genai.Client:
        """Return the configured `genai.Client` instance (resolving `GEMINI_API_KEY` / `GOOGLE_API_KEY` if needed)."""
        if self._custom_client is not None:
            return self._custom_client
        args = dict(self.client_args)
        if "api_key" not in args and not args.get("vertexai"):
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if api_key:
                args["api_key"] = api_key
        return genai.Client(**args)

    @staticmethod
    def _format_part(content: ContentBlock) -> dict[str, Any] | None:
        """Convert a Strands media/text `ContentBlock` into an Interactions API `PartParam` dictionary."""
        if "text" in content:
            return {"type": "text", "text": content["text"]}

        if "image" in content:
            img_bytes = content["image"].get("source", {}).get("bytes")
            if not img_bytes:
                return None
            fmt = content["image"].get("format", "png")
            mime_type = mimetypes.types_map.get(f".{fmt}", f"image/{fmt}")
            return {
                "type": "image",
                "data": base64.b64encode(img_bytes).decode("ascii"),
                "mime_type": mime_type,
            }

        if "audio" in content:
            aud_bytes = content["audio"].get("source", {}).get("bytes")
            if not aud_bytes:
                return None
            fmt = content["audio"].get("format", "mp3")
            mime_type = _AUDIO_MIME_TYPES.get(fmt, f"audio/{fmt}")
            return {
                "type": "audio",
                "data": base64.b64encode(aud_bytes).decode("ascii"),
                "mime_type": mime_type,
            }

        if "video" in content:
            vid_bytes = content["video"].get("source", {}).get("bytes")
            if not vid_bytes:
                return None
            fmt = content["video"].get("format", "mp4")
            mime_type = _VIDEO_MIME_TYPES.get(fmt, f"video/{fmt}")
            return {
                "type": "video",
                "data": base64.b64encode(vid_bytes).decode("ascii"),
                "mime_type": mime_type,
            }

        if "document" in content:
            doc_bytes = content["document"].get("source", {}).get("bytes")
            if not doc_bytes:
                return None
            fmt = content["document"].get("format", "pdf")
            mime_type = mimetypes.types_map.get(f".{fmt}", "application/pdf" if fmt == "pdf" else "application/octet-stream")
            return {
                "type": "document",
                "data": base64.b64encode(doc_bytes).decode("ascii"),
                "mime_type": mime_type,
            }

        return None

    def _format_tool_result_value(self, tool_result_content: Sequence[Mapping[str, Any]]) -> Any:
        """Format a Strands `ToolResult['content']` list into an Interactions API `FunctionResultStepParam['result']`."""
        if not tool_result_content:
            return ""

        if len(tool_result_content) == 1:
            single = tool_result_content[0]
            if "json" in single:
                return single["json"]
            if "text" in single and isinstance(single["text"], str):
                return single["text"]

        parts: list[dict[str, Any]] = []
        texts: list[str] = []
        has_media = False

        for item in tool_result_content:
            if "text" in item and isinstance(item["text"], str):
                texts.append(item["text"])
                parts.append({"type": "text", "text": item["text"]})
            elif "json" in item:
                serialized = json.dumps(item["json"])
                texts.append(serialized)
                parts.append({"type": "text", "text": serialized})
            elif "image" in item:
                has_media = True
                img_part = self._format_part(cast(ContentBlock, item))
                if img_part is not None:
                    parts.append(img_part)

        if has_media:
            return {"items": parts}
        return "\n".join(texts)

    def _format_request_steps(self, messages: Messages) -> list[dict[str, Any]]:
        """Convert Strands `Messages` into Gemini Interactions API `StepParam` dictionaries.

        Preserves:
        - `user_input` steps with text, image, audio, video, and document parts
        - `thought` steps with `signature` and `summary` (required by Gemini 3/4 models for multi-turn tool use)
        - `model_output` steps with assistant text parts
        - `function_call` steps with `id`, `name`, and `arguments`
        - `function_result` steps with `call_id`, `name`, `is_error`, and `result`
        """
        steps: list[dict[str, Any]] = []
        tool_use_id_to_name: dict[str, str] = {}

        for message in messages:
            role = message["role"]
            contents = message["content"]

            if role == "user":
                user_parts: list[dict[str, Any]] = []
                for content in contents:
                    if _block_has_location_source(content):
                        logger.warning("Location sources are not supported by Gemini Interactions | skipping block")
                        continue
                    if "cachePoint" in content:
                        continue

                    if "toolResult" in content:
                        if user_parts:
                            steps.append({"type": "user_input", "content": list(user_parts)})
                            user_parts.clear()

                        tool_result = content["toolResult"]
                        tool_use_id = tool_result["toolUseId"]
                        fn_name = tool_use_id_to_name.get(tool_use_id, tool_use_id)
                        raw_tr_content = cast(Sequence[Mapping[str, Any]], tool_result.get("content", []))
                        result_step: dict[str, Any] = {
                            "type": "function_result",
                            "call_id": tool_use_id,
                            "name": fn_name,
                            "result": self._format_tool_result_value(raw_tr_content),
                        }
                        if tool_result.get("status") == "error":
                            result_step["is_error"] = True
                        steps.append(result_step)
                        continue

                    part = self._format_part(content)
                    if part is not None:
                        user_parts.append(part)

                if user_parts:
                    steps.append({"type": "user_input", "content": user_parts})

            else:
                model_parts: list[dict[str, Any]] = []
                last_thought_signature: str | None = None

                for content in contents:
                    if _block_has_location_source(content) or "cachePoint" in content:
                        continue

                    if "reasoningContent" in content:
                        if model_parts:
                            steps.append({"type": "model_output", "content": list(model_parts)})
                            model_parts.clear()

                        reasoning_text = content["reasoningContent"].get("reasoningText", {})
                        summary_str = reasoning_text.get("text", "")
                        sig = reasoning_text.get("signature")
                        thought_step: dict[str, Any] = {"type": "thought"}
                        if sig:
                            thought_step["signature"] = sig
                            last_thought_signature = sig
                        if summary_str:
                            thought_step["summary"] = [{"type": "text", "text": summary_str}]
                        steps.append(thought_step)
                        continue

                    if "toolUse" in content:
                        if model_parts:
                            steps.append({"type": "model_output", "content": list(model_parts)})
                            model_parts.clear()

                        tool_use = content["toolUse"]
                        tool_use_id = tool_use["toolUseId"]
                        tool_name = tool_use["name"]
                        tool_use_id_to_name[tool_use_id] = tool_name

                        reasoning_sig = tool_use.get("reasoningSignature")
                        if reasoning_sig and reasoning_sig != last_thought_signature:
                            steps.append({"type": "thought", "signature": reasoning_sig})
                            last_thought_signature = reasoning_sig

                        raw_input: Any = tool_use.get("input")
                        arguments: dict[str, Any] = (
                            dict(cast(Mapping[str, Any], raw_input))
                            if isinstance(raw_input, Mapping)
                            else {"value": raw_input}
                        )
                        steps.append(
                            {
                                "type": "function_call",
                                "id": tool_use_id,
                                "name": tool_name,
                                "arguments": arguments,
                            }
                        )
                        continue

                    part = self._format_part(content)
                    if part is not None:
                        model_parts.append(part)

                if model_parts:
                    steps.append({"type": "model_output", "content": model_parts})

        return steps

    def _format_request_tools(
        self,
        tool_specs: list[ToolSpec] | None,
        extra_gemini_tools: Sequence[str | Mapping[str, object] | pydantic.BaseModel] | None = None,
    ) -> list[dict[str, object]] | None:
        """Combine Strands `tool_specs` (`function` tools) with all configured native Gemini Interactions tools."""
        tools: list[dict[str, object]] = []
        seen_function_names: set[str] = set()

        for spec in tool_specs or []:
            spec_dict = cast(Mapping[str, Any], spec)
            fn_name = str(spec_dict.get("name", ""))
            seen_function_names.add(fn_name)
            fn_tool: dict[str, Any] = {
                "type": "function",
                "name": fn_name,
                "description": str(spec_dict.get("description", "")),
            }
            input_schema = _get_field(spec_dict, "inputSchema")
            schema = _get_field(input_schema, "json")
            if schema is not None:
                fn_tool["parameters"] = schema
            tools.append(fn_tool)

        configured_gemini_tools = normalize_gemini_interactions_tools(self.config.get("gemini_tools"))
        runtime_gemini_tools = normalize_gemini_interactions_tools(extra_gemini_tools)

        for native_tool in [*configured_gemini_tools, *runtime_gemini_tools]:
            if native_tool.get("type") == "function":
                name = native_tool.get("name")
                if isinstance(name, str) and name in seen_function_names:
                    continue
                if isinstance(name, str):
                    seen_function_names.add(name)
            tools.append(native_tool)

        return tools if tools else None

    @staticmethod
    def _format_tool_choice(tool_choice: ToolChoice | None) -> Any:
        """Convert a Strands `ToolChoice` into an Interactions API `generation_config.tool_choice` value."""
        if tool_choice is None:
            return None
        if "auto" in tool_choice:
            return "auto"
        if "any" in tool_choice:
            return "any"
        if "tool" in tool_choice:
            tool_name = cast(ToolChoiceToolDict, tool_choice)["tool"]["name"]
            return {
                "allowed_tools": {
                    "mode": "any",
                    "tools": [tool_name],
                }
            }
        return None

    def _format_request(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        params: dict[str, object] | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        stream: bool = True,
        extra_gemini_tools: Sequence[str | Mapping[str, object] | pydantic.BaseModel] | None = None,
    ) -> dict[str, object]:
        """Build the keyword arguments dictionary for `client.aio.interactions.create(**request)`."""
        raw_params = dict(params or {})
        gen_config: dict[str, Any] = dict(raw_params.pop("generation_config", {}) or {})

        for gen_key in (
            "temperature",
            "top_p",
            "max_output_tokens",
            "stop_sequences",
            "seed",
            "thinking_level",
            "thinking_summaries",
            "tool_choice",
            "image_config",
            "speech_config",
            "transcription_config",
            "video_config",
        ):
            if gen_key in raw_params and gen_key not in gen_config:
                gen_config[gen_key] = raw_params.pop(gen_key)

        formatted_tc = self._format_tool_choice(tool_choice) if tool_specs else None
        if formatted_tc is not None and "tool_choice" not in gen_config:
            gen_config["tool_choice"] = formatted_tc

        # Default thinking_summaries to "auto" when thinking_level is set so thought summaries & signatures stream
        if "thinking_level" in gen_config and "thinking_summaries" not in gen_config:
            gen_config["thinking_summaries"] = "auto"

        steps = self._format_request_steps(messages)
        is_stateful = self.stateful

        request: dict[str, Any] = {
            "model": self.config["model_id"],
            "input": steps[-1:] if (is_stateful and self._last_interaction_id and steps) else steps,
            "stream": stream,
            "store": is_stateful,
        }

        if is_stateful and self._last_interaction_id:
            request["previous_interaction_id"] = self._last_interaction_id

        if system_prompt:
            request["system_instruction"] = system_prompt

        tools = self._format_request_tools(tool_specs, extra_gemini_tools=extra_gemini_tools)
        if tools is not None:
            request["tools"] = tools

        if gen_config:
            request["generation_config"] = gen_config

        for top_key in (
            "background",
            "cached_content",
            "continuation_token",
            "environment",
            "labels",
            "previous_interaction_id",
            "response_format",
            "response_mime_type",
            "response_modalities",
            "safety_settings",
            "service_tier",
            "store",
            "webhook_config",
        ):
            if top_key in raw_params:
                request[top_key] = raw_params[top_key]

        return request

    @staticmethod
    def _map_stop_reason(raw_reason: str | None, *, tool_used: bool) -> StopReason:
        """Map an Interactions API `stop_reason` / `status` to a Strands `StopReason`."""
        if tool_used:
            return "tool_use"
        if not raw_reason:
            return "end_turn"
        normalized = raw_reason.lower()
        if normalized in ("tool_use", "function_call", "requires_action"):
            return "tool_use"
        if normalized in ("max_tokens", "length", "max_output_tokens"):
            return "max_tokens"
        if normalized in ("safety", "blocklist", "prohibited_content", "spii", "image_safety"):
            return "guardrail_intervened"
        if normalized in ("recitation", "language"):
            return "content_filtered"
        return "end_turn"

    @staticmethod
    def _format_usage_metadata(usage: object) -> StreamEvent:
        """Convert an Interactions API `Usage` object into a Strands `MetadataEvent`."""
        input_tokens = _get_int(usage, "total_input_tokens")
        tool_use_tokens = _get_int(usage, "total_tool_use_tokens")
        output_tokens = _get_int(usage, "total_output_tokens")
        thought_tokens = _get_int(usage, "total_thought_tokens")
        total_tokens = _get_int(usage, "total_tokens")
        cached_tokens = _get_int(usage, "total_cached_tokens")

        combined_input = input_tokens + tool_use_tokens
        combined_output = output_tokens + thought_tokens
        if total_tokens == 0:
            total_tokens = combined_input + combined_output

        usage_data: Usage = {
            "inputTokens": combined_input,
            "outputTokens": combined_output,
            "totalTokens": total_tokens,
        }
        if cached_tokens > 0:
            usage_data["cacheReadInputTokens"] = cached_tokens

        return {
            "metadata": {
                "usage": usage_data,
                "metrics": {
                    "latencyMs": 0,
                },
            }
        }

    @staticmethod
    def _translate_exception(error: Exception) -> Exception:
        """Translate Gemini SDK / Interactions HTTP exceptions into Strands exceptions when applicable."""
        if isinstance(error, (ModelThrottledException, ContextWindowOverflowException)):
            return error

        if isinstance(error, compat_errors.RateLimitError):
            return ModelThrottledException(str(error))

        if isinstance(error, compat_errors.APIStatusError):
            status_code = getattr(error, "status_code", None)
            msg = str(error)
            if _is_capacity_or_bandwidth_error(status_code=status_code, message=msg):
                return ModelThrottledException(msg)
            if status_code == 400 and "exceeds the maximum number of tokens" in msg.lower():
                return ContextWindowOverflowException(msg)
            return error

        if isinstance(error, genai_errors.APIError):
            code = getattr(error, "code", None)
            status = getattr(error, "status", None)
            msg = getattr(error, "message", None) or str(error)
            if _is_capacity_or_bandwidth_error(status_code=code, status_text=status, message=msg):
                return ModelThrottledException(msg)
            if status == "INVALID_ARGUMENT" and "exceeds the maximum number of tokens" in msg.lower():
                return ContextWindowOverflowException(msg)
            return error

        return error

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream an interaction with the Gemini Interactions API.

        Args:
            messages: Conversation messages to process.
            tool_specs: Strands tool specifications to expose as `function` tools.
            system_prompt: System instruction string.
            tool_choice: Tool selection strategy.
            system_prompt_content: Optional structured system prompt blocks (if `system_prompt` is not set).
            **kwargs: Optional per-call `gemini_tools` override.

        Yields:
            Strands `StreamEvent` dictionaries.

        Raises:
            ModelThrottledException: On Gemini API rate limit, bandwidth, or capacity exhaustion (`429` / `503` /
                `RESOURCE_EXHAUSTED` / `UNAVAILABLE`), allowing `ModelRouter` to fail over to the next Gemini model.
            ContextWindowOverflowException: If the input exceeds the model's maximum context window.
        """
        effective_system_prompt = system_prompt
        if not effective_system_prompt and system_prompt_content:
            text_parts = [block["text"] for block in system_prompt_content if "text" in block]
            if text_parts:
                effective_system_prompt = "\n".join(text_parts)

        extra_tools = kwargs.get("gemini_tools")
        request = self._format_request(
            messages,
            tool_specs,
            effective_system_prompt,
            self.config.get("params"),
            tool_choice=tool_choice,
            stream=True,
            extra_gemini_tools=extra_tools,
        )

        client = self._get_client()

        try:
            response = await client.aio.interactions.create(**request)

            yield {"messageStart": {"role": "assistant"}}

            active_block_type: Literal["reasoning", "text", "tool"] | None = None
            tool_used = False
            tool_args_emitted = False
            pending_thought_signature: str | None = None
            stop_reason_raw: str | None = None
            usage_obj: Any = None

            if isinstance(response, AsyncIterable):
                async for event in response:
                    event_type = _get_str(event, "event_type")

                    if event_type in ("interaction.created", "interaction.updated", "interaction.status_update"):
                        interaction_obj = _get_field(event, "interaction")
                        if interaction_obj is not None:
                            int_id = _get_str(interaction_obj, "id")
                            if int_id:
                                self._last_interaction_id = int_id

                    elif event_type == "step.start":
                        step = _get_field(event, "step")
                        step_type = _get_str(step, "type")

                        if step_type == "thought":
                            if active_block_type is not None and active_block_type != "reasoning":
                                yield {"contentBlockStop": {}}
                                active_block_type = None
                            if active_block_type != "reasoning":
                                yield {"contentBlockStart": {"start": {}}}
                                active_block_type = "reasoning"

                            sig = _get_str(step, "signature")
                            if sig:
                                pending_thought_signature = sig
                                yield {
                                    "contentBlockDelta": {
                                        "delta": {
                                            "reasoningContent": {
                                                "signature": sig,
                                            }
                                        }
                                    }
                                }

                        elif step_type == "function_call":
                            if active_block_type is not None:
                                yield {"contentBlockStop": {}}
                                active_block_type = None

                            call_id = _get_str(step, "id") or f"tooluse_{secrets.token_urlsafe(16)}"
                            fn_name = _get_str(step, "name") or "function"

                            tool_start: ContentBlockStartToolUse = {
                                "name": fn_name,
                                "toolUseId": call_id,
                            }
                            if pending_thought_signature:
                                tool_start["reasoningSignature"] = pending_thought_signature

                            yield {"contentBlockStart": {"start": {"toolUse": tool_start}}}
                            active_block_type = "tool"
                            tool_used = True
                            tool_args_emitted = False

                            step_args = _get_field(step, "arguments")
                            if step_args:
                                serialized_args = (
                                    step_args if isinstance(step_args, str) else json.dumps(step_args)
                                )
                                yield {
                                    "contentBlockDelta": {
                                        "delta": {
                                            "toolUse": {
                                                "input": serialized_args,
                                            }
                                        }
                                    }
                                }
                                tool_args_emitted = True

                        elif step_type == "model_output":
                            if active_block_type is not None and active_block_type != "text":
                                yield {"contentBlockStop": {}}
                                active_block_type = None

                    elif event_type == "step.delta":
                        delta = _get_field(event, "delta")
                        delta_type = _get_str(delta, "type")

                        if delta_type == "thought_summary":
                            if active_block_type != "reasoning":
                                if active_block_type is not None:
                                    yield {"contentBlockStop": {}}
                                yield {"contentBlockStart": {"start": {}}}
                                active_block_type = "reasoning"

                            part = _get_field(delta, "part")
                            thought_text = _get_str(part, "text")
                            if thought_text:
                                yield {
                                    "contentBlockDelta": {
                                        "delta": {
                                            "reasoningContent": {
                                                "text": thought_text,
                                            }
                                        }
                                    }
                                }

                        elif delta_type == "thought_signature":
                            if active_block_type != "reasoning":
                                if active_block_type is not None:
                                    yield {"contentBlockStop": {}}
                                yield {"contentBlockStart": {"start": {}}}
                                active_block_type = "reasoning"

                            sig_val = _get_str(delta, "signature")
                            if sig_val:
                                pending_thought_signature = sig_val
                                yield {
                                    "contentBlockDelta": {
                                        "delta": {
                                            "reasoningContent": {
                                                "signature": sig_val,
                                            }
                                        }
                                    }
                                }

                        elif delta_type == "text":
                            if active_block_type != "text":
                                if active_block_type is not None:
                                    yield {"contentBlockStop": {}}
                                yield {"contentBlockStart": {"start": {}}}
                                active_block_type = "text"

                            text_val = _get_str(delta, "text")
                            if text_val:
                                yield {"contentBlockDelta": {"delta": {"text": text_val}}}

                        elif delta_type == "arguments_delta":
                            if active_block_type != "tool":
                                if active_block_type is not None:
                                    yield {"contentBlockStop": {}}
                                fallback_start: ContentBlockStartToolUse = {
                                    "name": "function",
                                    "toolUseId": f"tooluse_{secrets.token_urlsafe(16)}",
                                }
                                if pending_thought_signature:
                                    fallback_start["reasoningSignature"] = pending_thought_signature
                                yield {"contentBlockStart": {"start": {"toolUse": fallback_start}}}
                                active_block_type = "tool"
                                tool_used = True
                                tool_args_emitted = False

                            args_chunk = _get_str(delta, "arguments")
                            if args_chunk:
                                yield {
                                    "contentBlockDelta": {
                                        "delta": {
                                            "toolUse": {
                                                "input": args_chunk,
                                            }
                                        }
                                    }
                                }
                                tool_args_emitted = True

                        elif delta_type == "text_annotation_delta":
                            if active_block_type != "text":
                                if active_block_type is not None:
                                    yield {"contentBlockStop": {}}
                                yield {"contentBlockStart": {"start": {}}}
                                active_block_type = "text"

                            for ann in _get_list(delta, "annotations"):
                                source = _get_str(ann, "source")
                                if source:
                                    web_loc: WebLocation = {"url": source}
                                    citation_delta: CitationsDelta = {
                                        "location": {"web": web_loc},
                                        "sourceContent": [],
                                        "title": source,
                                    }
                                    yield {"contentBlockDelta": {"delta": {"citation": citation_delta}}}

                    elif event_type == "step.stop":
                        if active_block_type is not None:
                            if active_block_type == "tool" and not tool_args_emitted:
                                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}}
                                tool_args_emitted = True
                            yield {"contentBlockStop": {}}
                            active_block_type = None

                    elif event_type == "interaction.completed":
                        interaction_obj = _get_field(event, "interaction")
                        if interaction_obj is not None:
                            int_id = _get_str(interaction_obj, "id")
                            if int_id:
                                self._last_interaction_id = int_id
                            stop_reason_raw = (
                                _get_str(interaction_obj, "stop_reason")
                                or _get_str(interaction_obj, "status")
                            )
                            usage_obj = _get_field(interaction_obj, "usage")

                    elif event_type == "error":
                        err_obj = _get_field(event, "error")
                        err_code = _get_str(err_obj, "code") or ""
                        err_msg = _get_str(err_obj, "message") or "Gemini Interactions API stream error"
                        if _is_capacity_or_bandwidth_error(status_text=err_code, message=err_msg):
                            raise ModelThrottledException(err_msg)
                        if "exceeds the maximum number of tokens" in err_msg.lower():
                            raise ContextWindowOverflowException(err_msg)
                        raise RuntimeError(f"Gemini Interactions API stream error ({err_code}): {err_msg}")

            if active_block_type is not None:
                if active_block_type == "tool" and not tool_args_emitted:
                    yield {"contentBlockDelta": {"delta": {"toolUse": {"input": "{}"}}}}
                yield {"contentBlockStop": {}}

            yield {
                "messageStop": {
                    "stopReason": self._map_stop_reason(stop_reason_raw, tool_used=tool_used),
                }
            }

            if usage_obj is not None:
                yield self._format_usage_metadata(usage_obj)

        except Exception as error:
            raise self._translate_exception(error) from error

    @override
    async def structured_output(
        self,
        output_model: type[T],
        prompt: Messages,
        system_prompt: str | None = None,
        **kwargs: object,
    ) -> AsyncGenerator[dict[str, T | object], None]:
        """Get structured output from the Gemini Interactions API using `response_format` + `response_mime_type`."""
        params = {
            **(self.config.get("params") or {}),
            "response_mime_type": "application/json",
            "response_format": output_model.model_json_schema(),
        }
        request = self._format_request(prompt, None, system_prompt, params, stream=False)
        client = self._get_client()
        try:
            interaction = await client.aio.interactions.create(**request)
        except Exception as error:
            raise self._translate_exception(error) from error

        text_chunks: list[str] = []
        for step in _get_list(interaction, "steps"):
            step_type = _get_str(step, "type")
            if step_type == "model_output":
                for part in _get_list(step, "content"):
                    if _get_str(part, "type") == "text":
                        part_text = _get_str(part, "text")
                        if part_text:
                            text_chunks.append(part_text)

        raw_json = "".join(text_chunks).strip()
        yield {"output": output_model.model_validate_json(raw_json)}

    @override
    async def count_tokens(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
    ) -> int:
        """Estimate or count input tokens for the given messages."""
        if self.config.get("use_native_token_count") is not True:
            return await super().count_tokens(messages, tool_specs, system_prompt, system_prompt_content)

        try:
            text_parts: list[str] = []
            for msg in messages:
                for block in msg["content"]:
                    if "text" in block:
                        text_parts.append(block["text"])
            client = self._get_client().aio
            response = await client.models.count_tokens(
                model=self.config["model_id"],
                contents="\n".join(text_parts) if text_parts else "",
            )
            if response.total_tokens is None:
                raise ProviderTokenCountError("Gemini count_tokens returned None for total_tokens")
            extra = await super().count_tokens(
                messages=[],
                tool_specs=tool_specs,
                system_prompt=system_prompt,
                system_prompt_content=system_prompt_content,
            )
            return int(response.total_tokens) + extra
        except Exception as e:
            logger.debug(
                "model_id=<%s>, error=<%s> | native token counting failed, falling back to heuristic",
                self.config["model_id"],
                e,
            )
            return await super().count_tokens(messages, tool_specs, system_prompt, system_prompt_content)
