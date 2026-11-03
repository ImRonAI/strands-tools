# pyright: strict
"""Grounded JSON/Dict Agent & Subagent Factory and Strands Tool (`agent_from_config`).

Supports creating Strands `Agent` instances, `_AgentAsTool` (`Agent.as_tool()`) subagent tools,
and `strands.multiagent.spec.Preset` specifications from JSON files, JSON strings, Python `dict`s,
or registered config names.

Grounded in:
1. `strands_harness.config.harness_agent_kwargs_from_config` + `strands_harness.agent.create_harness`
2. `strands.experimental.agent_config.AgentConfig` + `config_to_agent`
3. `strands.agent.Agent.as_tool()` (`_AgentAsTool`)
4. `strands.multiagent.spec.Preset` & `AgentSpec`
5. `agentskills.tool.agent_skill` (`use_skill` Pattern #3 isolated skill sub-agent tool)
6. `strands.models.gemini_interactions.GeminiInteractionsModel` + `ModelRouter`
   (`gemini-4-argon` -> `gemini-3.8-flash` -> `gemini-3.5-flash-lite`)
"""

from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal, TypeGuard, cast

from pydantic import BaseModel
from strands import Agent, tool
from strands.models import Model, ModelRouter
from strands.models.gemini_interactions import GeminiInteractionsModel
from strands.multiagent.spec import Preset
from strands_harness import defaults as harness_defaults
from strands_harness.models import build_gemini_fallback_router, resolve_model
from strands_harness.types.agent import Effort

ConfigDict = dict[str, object]
ConfigMapping = Mapping[str, object]
GeminiToolSpec = str | Mapping[str, object] | BaseModel
ModelFactory = Callable[[], Model | ModelRouter | object]


def is_config_mapping(val: object) -> TypeGuard[ConfigMapping]:
    """Narrow an arbitrary object to `Mapping[str, object]`."""
    return isinstance(val, Mapping)


def is_object_sequence(val: object) -> TypeGuard[Sequence[object]]:
    """Narrow an arbitrary object to a non-string `Sequence[object]`."""
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes))


def coerce_gemini_tools(raw: object) -> list[GeminiToolSpec] | None:
    """Coerce a raw gemini_tools sequence into a typed `list[GeminiToolSpec]`."""
    if not is_object_sequence(raw):
        return None
    result: list[GeminiToolSpec] = []
    for item in raw:
        if isinstance(item, (str, BaseModel)):
            result.append(item)
        elif is_config_mapping(item):
            result.append(dict(item))
    return result

# Registered named JSON/dict agent configurations for reuse across tools and formations
_REGISTERED_AGENT_CONFIGS: dict[str, tuple[ConfigDict, Path | None]] = {}
_FACTORY_TOOL_REGISTRY: dict[str, object] = {}


def register_factory_tools(tools: Mapping[str, object]) -> None:
    """Register tool objects by name for resolution in `agent_from_config` and `graph` nodes."""
    for name, tool_obj in tools.items():
        _FACTORY_TOOL_REGISTRY[str(name)] = tool_obj
    try:
        from agentskills.tool.agent_skill import register_available_tools

        register_available_tools(dict(tools))
    except Exception:
        pass


def get_factory_tool(name: str) -> object | None:
    """Return a registered tool object by name if present."""
    return _FACTORY_TOOL_REGISTRY.get(name.strip())

_HARNESS_SPECIFIC_KEYS: frozenset[str] = frozenset(
    {
        "skills",
        "workspace",
        "prompt_mode",
        "extra_prompt",
        "include_default_tools",
        "builtin_tools",
        "builtinTools",
        "mcp_servers",
        "mcpServers",
        "memory",
        "memoryStores",
        "subagent",
        "session",
        "plugins",
        "builtinPlugins",
        "interventions",
        "hooks",
        "context_manager",
        "contextManager",
        "conversation_manager",
        "max_Concurrency",
        "max_concurrency",
    }
)


def register_agent_config(
    name: str,
    config: str | Path | ConfigMapping,
    *,
    base_path: Path | None = None,
) -> ConfigDict:
    """Register a named JSON/dict agent configuration for use in subagents and multi-agent formations."""
    key = name.strip()
    if not key:
        raise ValueError("Agent config name must not be empty.")
    cfg_dict, resolved_base = load_agent_config_dict(config, base_path=base_path)
    cfg_dict.setdefault("name", key)
    _REGISTERED_AGENT_CONFIGS[key] = (dict(cfg_dict), resolved_base)
    return dict(cfg_dict)


def get_agent_config(name: str) -> ConfigDict | None:
    """Retrieve a copy of a registered agent configuration by name."""
    entry = _REGISTERED_AGENT_CONFIGS.get(name.strip())
    if entry is None:
        return None
    return dict(entry[0])


def list_agent_configs() -> dict[str, ConfigDict]:
    """Return a mapping of all registered agent configuration names to their config dicts."""
    return {k: dict(v[0]) for k, v in _REGISTERED_AGENT_CONFIGS.items()}


def clear_agent_configs() -> None:
    """Clear all registered agent configurations."""
    _REGISTERED_AGENT_CONFIGS.clear()


def load_agent_config_dict(
    config: str | Path | ConfigMapping,
    *,
    base_path: Path | None = None,
) -> tuple[ConfigDict, Path | None]:
    """Load an agent configuration dictionary from a dict, JSON string, JSON file path, or registered name."""
    if isinstance(config, Mapping):
        return {str(k): v for k, v in config.items()}, base_path

    if isinstance(config, Path):
        resolved_path = config.expanduser().resolve()
        raw: object = json.loads(resolved_path.read_text(encoding="utf-8"))
        if not is_config_mapping(raw):
            raise ValueError(f"Agent config file '{resolved_path}' must contain a JSON object.")
        return {str(k): v for k, v in raw.items()}, resolved_path.parent

    text = config.strip()
    if not text:
        raise ValueError("Agent config string must not be empty.")

    # 1. Check registered config name first
    if text in _REGISTERED_AGENT_CONFIGS:
        reg_dict, reg_base = _REGISTERED_AGENT_CONFIGS[text]
        return dict(reg_dict), base_path or reg_base

    # 2. Check inline JSON object string
    if text.startswith("{") and text.endswith("}"):
        parsed: object = json.loads(text)
        if not is_config_mapping(parsed):
            raise ValueError("Inline JSON agent config must decode to a JSON object.")
        return {str(k): v for k, v in parsed.items()}, base_path

    # 3. Load from filesystem path
    candidate = Path(text).expanduser()
    if not candidate.is_absolute() and base_path is not None:
        candidate = (base_path / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.exists():
        raise FileNotFoundError(
            f"Agent config '{text}' is neither a registered config name nor an existing JSON file ({candidate})."
        )
    loaded: object = json.loads(candidate.read_text(encoding="utf-8"))
    if not is_config_mapping(loaded):
        raise ValueError(f"Agent config file '{candidate}' must contain a JSON object.")
    return {str(k): v for k, v in loaded.items()}, candidate.parent


def _resolve_single_tool(
    item: object,
    *,
    parent_agent: Agent | None = None,
    base_path: Path | None = None,
) -> object | None:
    """Resolve a single tool specification (object, name, module:attr, path, or nested subagent config)."""
    if item is None:
        return None

    # Nested subagent config dict -> build subagent tool via Agent.as_tool()
    if is_config_mapping(item):
        nested_raw = (
            item.get("config")
            or item.get("config_path")
            or item.get("config_name")
            or item
        )
        nested_cfg: str | Path | ConfigMapping = (
            nested_raw
            if isinstance(nested_raw, (str, Path)) or is_config_mapping(nested_raw)
            else item
        )
        tool_name = item.get("tool_name") or item.get("name")
        tool_desc = item.get("description")
        preserve_ctx = bool(item.get("preserve_context", False))
        return build_subagent_tool_from_config(
            nested_cfg,
            parent_agent=parent_agent,
            name=str(tool_name) if tool_name else None,
            description=str(tool_desc) if tool_desc else None,
            preserve_context=preserve_ctx,
            base_path=base_path,
        )

    if not isinstance(item, str):
        return item

    name = item.strip()
    if not name:
        return None

    # 1. Check parent_agent's tool_registry
    if parent_agent is not None:
        registry_obj: object = getattr(parent_agent, "tool_registry", None)
        reg_map: object = getattr(registry_obj, "registry", None)
        if is_config_mapping(reg_map):
            if name in reg_map:
                return reg_map[name]

    # 2. Ensure default skills/use_skill are registered if needed, then check AgentSkills tool registry
    if name == "use_skill":
        try:
            from .graph import ensure_default_skills_configured

            ensure_default_skills_configured()
        except Exception:
            pass

    found_tool = get_factory_tool(name)
    if found_tool is not None:
        return found_tool

    # 3. Check registered subagent configs by name
    if name in _REGISTERED_AGENT_CONFIGS:
        return build_subagent_tool_from_config(
            name,
            parent_agent=parent_agent,
            base_path=base_path,
        )

    # 4. Check strands_tools:<name> convention
    if name.startswith("strands_tools:"):
        short_name = name.split(":", 1)[1].strip()
        try:
            mod = importlib.import_module(f"strands_tools.{short_name}")
            return getattr(mod, short_name, mod)
        except Exception:
            pass

    # 5. Check direct module in strands_tools.<name>
    try:
        mod = importlib.import_module(f"strands_tools.{name}")
        candidate_attr: object = getattr(mod, name, None)
        if candidate_attr is not None:
            return candidate_attr
    except Exception:
        pass

    # 6. Check module:attr reference
    if ":" in name and not Path(name).exists():
        mod_name, attr_name = name.split(":", 1)
        try:
            mod = importlib.import_module(mod_name.strip())
            return getattr(mod, attr_name.strip())
        except Exception:
            pass

    # 7. Check Python file path
    candidate = Path(name).expanduser()
    if not candidate.is_absolute() and base_path is not None:
        candidate = (base_path / candidate).resolve()
    if candidate.exists() and candidate.suffix == ".py":
        from strands.tools.loader import load_tools_from_file_path

        loaded_tools = load_tools_from_file_path(str(candidate))
        return loaded_tools[0] if loaded_tools else None

    raise ValueError(f"Unknown or unresolvable tool '{name}' in agent configuration.")


def _resolve_gemini_or_configured_model(
    cfg_dict: ConfigMapping,
    *,
    parent_agent: Agent | None,
    model_factories: Mapping[str, ModelFactory] | None,
    gemini_tools: Sequence[GeminiToolSpec] | None,
    effort: Effort,
) -> object:
    """Resolve the model for an agent configuration, defaulting to the Gemini failover ModelRouter."""
    model_id_key = cfg_dict.get("model_id")
    if isinstance(model_id_key, str) and model_id_key.strip():
        mid = model_id_key.strip()
        if model_factories and mid in model_factories:
            return model_factories[mid]()
        if mid.startswith(("google/", "gemini/", "gemini-")):
            spec = mid if "/" in mid else f"google/{mid}"
            return resolve_model(
                spec,
                harness_defaults.DEFAULT_MODEL,
                effort=effort,
                gemini_tools=gemini_tools,
            )
        raise ValueError(f"Unknown model_id: {mid}")

    if "model" in cfg_dict and cfg_dict["model"] is not None:
        raw_model = cfg_dict["model"]
        if isinstance(raw_model, str):
            m_str = raw_model.strip()
            if model_factories and m_str in model_factories:
                return model_factories[m_str]()
            if m_str.startswith(("google/", "gemini/", "gemini-")):
                spec = m_str if "/" in m_str else f"google/{m_str}"
                return resolve_model(
                    spec,
                    harness_defaults.DEFAULT_MODEL,
                    effort=effort,
                    gemini_tools=gemini_tools,
                )
            if "/" in m_str or ":" in m_str:
                return resolve_model(
                    m_str,
                    harness_defaults.DEFAULT_MODEL,
                    effort=effort,
                    gemini_tools=gemini_tools,
                )
            return m_str
        if is_config_mapping(raw_model):
            nested_id = str(raw_model.get("model_id") or raw_model.get("model") or "gemini-4-argon")
            clean_id = nested_id.split("/", 1)[1] if "/" in nested_id else nested_id
            nested_tools = coerce_gemini_tools(raw_model.get("gemini_tools")) or (
                list(gemini_tools) if gemini_tools is not None else None
            )
            nested_params = raw_model.get("params")
            return GeminiInteractionsModel(
                model_id=clean_id,
                params=(
                    {str(k): v for k, v in nested_params.items()}
                    if is_config_mapping(nested_params)
                    else None
                ),
                gemini_tools=nested_tools,
            )
        return raw_model

    if parent_agent is not None and getattr(parent_agent, "model", None) is not None:
        return parent_agent.model

    return build_gemini_fallback_router(
        effort=effort,
        gemini_tools=gemini_tools,
    )


def resolve_agent_tools(
    raw_tools: Sequence[object] | None,
    *,
    parent_agent: Agent | None = None,
    base_path: Path | None = None,
    use_skill: bool = False,
    subagents: Sequence[object] | None = None,
    for_swarm: bool = False,
) -> list[object]:
    """Resolve and deduplicate a list of tools (including `use_skill` and nested JSON/dict subagents)."""
    items: list[object] = list(raw_tools or [])
    if use_skill:
        items.append("use_skill")
    if subagents:
        for sub in subagents:
            if is_config_mapping(sub):
                items.append(sub)
            else:
                items.append({"config": sub})

    resolved: list[object] = []
    seen_keys: set[str] = set()
    for item in items:
        tool_obj = _resolve_single_tool(item, parent_agent=parent_agent, base_path=base_path)
        if tool_obj is None:
            continue
        t_name = str(getattr(tool_obj, "tool_name", getattr(tool_obj, "__name__", id(tool_obj))))
        # Swarm._inject_swarm_tools raises ValueError if a node already has `handoff_to_agent`
        if for_swarm and t_name == "handoff_to_agent":
            continue
        if t_name not in seen_keys:
            seen_keys.add(t_name)
            resolved.append(tool_obj)
    return resolved


def _tool_display_name(item: object) -> str:
    return str(getattr(item, "tool_name", getattr(item, "__name__", str(item))))


def _detect_engine(
    cfg: ConfigMapping,
    engine: Literal["auto", "harness", "sdk"],
) -> Literal["harness", "sdk"]:
    if engine in ("harness", "sdk"):
        return engine
    cfg_engine = cfg.get("engine")
    if cfg_engine in ("harness", "create_harness"):
        return "harness"
    if cfg_engine == "sdk":
        return "sdk"
    if any(k in cfg for k in _HARNESS_SPECIFIC_KEYS):
        return "harness"
    if is_config_mapping(cfg.get("model")):
        return "harness"
    return "sdk"


def build_agent_from_config(
    config: str | Path | ConfigMapping,
    *,
    parent_agent: Agent | None = None,
    engine: Literal["auto", "harness", "sdk"] = "auto",
    session: bool = False,
    extra_tools: Sequence[object] | None = None,
    for_swarm: bool = False,
    model_factories: Mapping[str, ModelFactory] | None = None,
    base_path: Path | None = None,
    **overrides: object,
) -> Agent:
    """Build a fresh Strands `Agent` from a JSON file path, JSON string, Python dict, or registered config name.

    Guarantees:
    - Unique `Agent` instance per call (satisfies `Graph._validate_node_executor` & `Swarm._validate_swarm`).
    - `_session_manager` is `None` when `session=False` (satisfies `_AgentAsTool`, `Graph`, and `Swarm`).
    - `agent.name` and `agent.description` are always populated (satisfies `Agent.as_tool()` and `Swarm`).
    - Resolves string tool names (including `"use_skill"`), `"module:attr"` refs, and nested subagent configs.
    """
    cfg_dict, resolved_base = load_agent_config_dict(config, base_path=base_path)
    if overrides:
        cfg_dict.update(overrides)

    effective_factories = model_factories
    if effective_factories is None:
        try:
            from .graph import get_model_factories

            effective_factories = get_model_factories()
        except Exception:
            effective_factories = None

    chosen_engine = _detect_engine(cfg_dict, engine)

    node_name = str(cfg_dict.get("id") or cfg_dict.get("name") or "configured_agent")
    system_prompt = str(
        cfg_dict.get("system_prompt")
        or cfg_dict.get("instructions")
        or cfg_dict.get("prompt")
        or cfg_dict.get("description")
        or cfg_dict.get("goal")
        or ""
    )
    description = str(
        cfg_dict.get("description")
        or cfg_dict.get("goal")
        or (system_prompt.splitlines()[0] if system_prompt else f"Specialized agent {node_name}")
    )

    raw_cfg_tools = cfg_dict.get("tools")
    combined_raw_tools: list[object] = list(raw_cfg_tools) if is_object_sequence(raw_cfg_tools) else []
    if extra_tools:
        combined_raw_tools.extend(extra_tools)

    raw_subagents = cfg_dict.get("subagents")
    subagents_seq: Sequence[object] | None = raw_subagents if is_object_sequence(raw_subagents) else None

    resolved_tools = resolve_agent_tools(
        combined_raw_tools,
        parent_agent=parent_agent,
        base_path=resolved_base,
        use_skill=bool(cfg_dict.get("use_skill", False)),
        subagents=subagents_seq,
        for_swarm=for_swarm,
    )

    raw_gemini_tools = cfg_dict.get("gemini_tools") or cfg_dict.get("geminiTools")
    gemini_tools = coerce_gemini_tools(raw_gemini_tools)
    raw_effort = cfg_dict.get("effort")
    effort_val: Effort = (
        raw_effort
        if raw_effort in ("auto", "off", "minimal", "low", "medium", "high", "xhigh", "max")
        else harness_defaults.DEFAULT_EFFORT
    )

    explicit_model = _resolve_gemini_or_configured_model(
        cfg_dict,
        parent_agent=parent_agent,
        model_factories=effective_factories,
        gemini_tools=gemini_tools,
        effort=effort_val,
    )

    if chosen_engine == "harness":
        from strands_harness.agent import create_harness
        from strands_harness.config import DEFAULT_HARNESS_AGENT_CONFIG, harness_agent_kwargs_from_config

        harness_cfg: dict[str, object] = {}
        key_aliases = {
            "system_prompt": "instructions",
            "builtin_tools": "builtinTools",
            "context_manager": "contextManager",
            "mcp_servers": "mcpServers",
            "memory_stores": "memoryStores",
            "builtin_plugins": "builtinPlugins",
            "agent_config": "agentConfig",
        }
        for k, v in cfg_dict.items():
            if v is None:
                continue
            mapped_key = key_aliases.get(k, k)
            if mapped_key in ("tools", "subagents", "model"):
                continue
            if mapped_key in DEFAULT_HARNESS_AGENT_CONFIG:
                harness_cfg[mapped_key] = v

        if "instructions" not in harness_cfg and system_prompt:
            harness_cfg["instructions"] = system_prompt
        harness_cfg["name"] = node_name
        harness_cfg["description"] = description

        harness_kwargs: dict[str, object] = dict(
            harness_agent_kwargs_from_config(
                harness_cfg,
                base_dir=resolved_base or Path("."),
            )
        )
        if explicit_model is not None:
            harness_kwargs["model"] = explicit_model
        if gemini_tools is not None:
            harness_kwargs["gemini_tools"] = gemini_tools
        if resolved_tools:
            harness_kwargs["tools"] = resolved_tools
        if not session:
            harness_kwargs["session"] = False
            harness_kwargs.setdefault("memory", False)
        if cfg_dict.get("include_default_tools") is False and "builtin_tools" not in harness_kwargs:
            harness_kwargs["builtin_tools"] = []
        if isinstance(explicit_model, Model) and not isinstance(
            explicit_model, GeminiInteractionsModel
        ):
            # A custom Model instance (e.g. StubModel) does not have native provider web_search
            if "builtin_tools" not in harness_kwargs:
                harness_kwargs["builtin_tools"] = {"web_search": False}
        harness_kwargs.pop("agent_config", None)
        harness_kwargs.setdefault("callback_handler", None)
        harness_kwargs["name"] = node_name
        harness_kwargs["description"] = description

        create_harness_fn = cast(Callable[..., Agent], create_harness)
        agent = create_harness_fn(**harness_kwargs)
        agent.name = node_name
        agent.description = description
        if not session:
            setattr(agent, "_session_manager", None)
        return agent

    # SDK engine (`Agent` / `AgentConfig`)
    agent_kwargs: dict[str, object] = {
        "name": node_name,
        "description": description,
        "system_prompt": system_prompt,
        "callback_handler": None,
    }
    if explicit_model is not None:
        agent_kwargs["model"] = explicit_model
        if isinstance(explicit_model, ModelRouter):
            agent_kwargs["retry_strategy"] = None
    if resolved_tools:
        agent_kwargs["tools"] = resolved_tools

    agent_cls = cast(Callable[..., Agent], Agent)
    agent = agent_cls(**agent_kwargs)
    if not session:
        setattr(agent, "_session_manager", None)
    return agent


def build_subagent_tool_from_config(
    config: str | Path | ConfigMapping,
    *,
    parent_agent: Agent | None = None,
    name: str | None = None,
    description: str | None = None,
    preserve_context: bool = False,
    engine: Literal["auto", "harness", "sdk"] = "auto",
    extra_tools: Sequence[object] | None = None,
    model_factories: Mapping[str, ModelFactory] | None = None,
    base_path: Path | None = None,
) -> object:
    """Build a Strands subagent from a JSON/dict config and wrap it as an `AgentTool` via `Agent.as_tool()`."""
    sub_agent = build_agent_from_config(
        config,
        parent_agent=parent_agent,
        engine=engine,
        session=False,
        extra_tools=extra_tools,
        model_factories=model_factories,
        base_path=base_path,
    )
    tool_name = name or sub_agent.name or "configured_subagent"
    tool_desc = description or sub_agent.description or f"Subagent {tool_name}"
    return sub_agent.as_tool(
        name=tool_name,
        description=tool_desc,
        preserve_context=preserve_context,
    )


def config_to_preset(
    config: str | Path | ConfigMapping,
    *,
    base_path: Path | None = None,
) -> Preset:
    """Convert a JSON file or dict config into a `strands.multiagent.spec.Preset` for `CreateSubagent`/`CreateSwarm`."""
    cfg_dict, _ = load_agent_config_dict(config, base_path=base_path)
    name = str(cfg_dict.get("name") or cfg_dict.get("id") or "preset_agent")
    system_prompt = str(cfg_dict.get("system_prompt") or cfg_dict.get("prompt") or "")
    description = str(
        cfg_dict.get("description")
        or (system_prompt.splitlines()[0] if system_prompt else f"Preset agent {name}")
    )
    raw_tools_val = cfg_dict.get("tools")
    raw_tools_list: list[object] = list(raw_tools_val) if is_object_sequence(raw_tools_val) else []
    tool_names = [_tool_display_name(t) for t in raw_tools_list]
    if cfg_dict.get("use_skill"):
        if "use_skill" not in tool_names:
            tool_names.append("use_skill")
    model_val = cfg_dict.get("model") or cfg_dict.get("model_id")
    if is_config_mapping(model_val):
        model_val = model_val.get("model_id")
    return Preset(
        instructions=system_prompt or None,
        description=description,
        tools=tool_names,
        model=str(model_val) if isinstance(model_val, str) else None,
    )


@tool
async def agent_from_config(
    action: str = "invoke",
    config: ConfigDict | str | None = None,
    config_path: str | None = None,
    config_name: str | None = None,
    task: str | None = None,
    engine: str = "auto",
    extra_tools: list[str] | None = None,
    preserve_context: bool = False,
    agent: object | None = None,
) -> AsyncIterator[ConfigDict]:
    """Create, register, inspect, or invoke Strands agents and subagents defined via JSON files or Python dicts.

    Supports both `strands_harness` (`create_harness` + `harness_agent_kwargs_from_config`) and Strands SDK
    (`AgentConfig` / `Agent` + `Agent.as_tool()`), as well as attaching `use_skill` (Pattern #3) or registering
    agents for multi-agent `Graph`, `Swarm`, and `Workflow` formations.

    Args:
        action: Action to perform ("invoke", "register_tool", "register_config", "list", "inspect").
        config: Agent configuration dictionary or inline JSON string.
        config_path: Path to a JSON configuration file on disk.
        config_name: Name for registering or referencing a stored agent configuration.
        task: Task prompt to execute when action="invoke".
        engine: Configuration engine to use ("auto", "harness", or "sdk").
        extra_tools: Optional list of additional tool names (e.g. ["use_skill", "calculator"]) to attach.
        preserve_context: Whether `register_tool` preserves subagent conversation history across calls.
        agent: Parent Strands Agent instance (injected automatically by Strands when called inside an Agent).
    """
    parent_agent = agent if isinstance(agent, Agent) else None
    effective_engine: Literal["auto", "harness", "sdk"] = (
        "harness" if engine == "harness" else ("sdk" if engine == "sdk" else "auto")
    )

    if action == "list":
        configs = list_agent_configs()
        summary: list[ConfigDict] = []
        for k, v in sorted(configs.items()):
            raw_v_tools = v.get("tools")
            v_tools: list[object] = list(raw_v_tools) if is_object_sequence(raw_v_tools) else []
            summary.append(
                {
                    "name": k,
                    "description": v.get("description", ""),
                    "engine": _detect_engine(v, "auto"),
                    "tools": [_tool_display_name(t) for t in v_tools],
                    "use_skill": bool(v.get("use_skill", False)),
                }
            )
        yield {
            "status": "success",
            "content": [{"text": json.dumps({"registered_configs": summary}, indent=2)}],
        }
        return

    target_source: str | Path | ConfigMapping | None = config or config_path or config_name
    if target_source is None:
        yield {
            "status": "error",
            "content": [{"text": "One of `config`, `config_path`, or `config_name` is required."}],
        }
        return

    try:
        from .graph import get_model_factories

        factories = get_model_factories()

        if action == "register_config":
            cfg_dict, resolved_base = load_agent_config_dict(target_source)
            reg_name = str(config_name or cfg_dict.get("name") or cfg_dict.get("id") or "")
            if not reg_name:
                yield {
                    "status": "error",
                    "content": [{"text": "`config_name` or `config['name']` is required for register_config."}],
                }
                return
            saved = register_agent_config(reg_name, cfg_dict, base_path=resolved_base)
            yield {
                "status": "success",
                "content": [
                    {
                        "text": f"Registered agent config '{reg_name}' (engine={_detect_engine(saved, effective_engine)})."
                    }
                ],
            }
            return

        if action == "inspect":
            cfg_dict, resolved_base = load_agent_config_dict(target_source)
            built = build_agent_from_config(
                cfg_dict,
                parent_agent=parent_agent,
                engine=effective_engine,
                session=False,
                extra_tools=extra_tools,
                model_factories=factories,
                base_path=resolved_base,
            )
            preset = config_to_preset(cfg_dict, base_path=resolved_base)
            info: ConfigDict = {
                "name": built.name,
                "description": built.description,
                "engine": _detect_engine(cfg_dict, effective_engine),
                "tool_names": list(built.tool_names),
                "preset": {
                    "name": built.name,
                    "description": preset.description,
                    "instructions": preset.instructions,
                    "tools": list(preset.tools) if preset.tools is not None else None,
                    "model": str(preset.model) if preset.model is not None else None,
                },
            }
            yield {
                "status": "success",
                "content": [{"text": json.dumps(info, indent=2)}],
            }
            return

        if action == "register_tool":
            cfg_dict, resolved_base = load_agent_config_dict(target_source)
            reg_name = str(config_name or cfg_dict.get("name") or cfg_dict.get("id") or "configured_subagent")
            register_agent_config(reg_name, cfg_dict, base_path=resolved_base)
            sub_tool = build_subagent_tool_from_config(
                cfg_dict,
                parent_agent=parent_agent,
                name=reg_name,
                preserve_context=preserve_context,
                engine=effective_engine,
                extra_tools=extra_tools,
                model_factories=factories,
                base_path=resolved_base,
            )
            register_factory_tools({reg_name: sub_tool})
            if parent_agent is not None and hasattr(parent_agent, "tool_registry"):
                parent_agent.tool_registry.process_tools([sub_tool])

            yield {
                "status": "success",
                "content": [
                    {
                        "text": f"Registered subagent tool '{reg_name}' via Agent.as_tool() and stored config '{reg_name}'."
                    }
                ],
            }
            return

        if action == "invoke":
            if not task:
                yield {
                    "status": "error",
                    "content": [{"text": "`task` is required when action='invoke'."}],
                }
                return
            sub_agent = build_agent_from_config(
                target_source,
                parent_agent=parent_agent,
                engine=effective_engine,
                session=False,
                extra_tools=extra_tools,
                model_factories=factories,
            )
            final_result: object = None
            async for raw_event in sub_agent.stream_async(task):
                event_obj: object = raw_event
                yield {
                    "subagent": sub_agent.name,
                    "event": str(event_obj),
                }
                if is_config_mapping(event_obj) and "result" in event_obj:
                    final_result = event_obj["result"]
            yield {
                "status": "success",
                "content": [
                    {
                        "text": str(final_result)
                        if final_result is not None
                        else f"Subagent '{sub_agent.name}' completed."
                    }
                ],
            }
            return

        yield {"status": "error", "content": [{"text": f"Unknown action: {action}"}]}
    except Exception as exc:
        yield {
            "status": "error",
            "content": [{"text": f"agent_from_config ({action}) failed: {exc}"}],
        }


__all__ = [
    "ConfigDict",
    "ConfigMapping",
    "GeminiToolSpec",
    "ModelFactory",
    "agent_from_config",
    "build_agent_from_config",
    "build_subagent_tool_from_config",
    "clear_agent_configs",
    "coerce_gemini_tools",
    "config_to_preset",
    "get_agent_config",
    "is_config_mapping",
    "is_object_sequence",
    "list_agent_configs",
    "load_agent_config_dict",
    "register_agent_config",
    "resolve_agent_tools",
]
