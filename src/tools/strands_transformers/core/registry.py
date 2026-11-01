"""Dynamic task & model registry - 100% transformers coverage, zero hardcoding.

The single source of truth is transformers' own `SUPPORTED_TASKS` taxonomy, which
maps every task → AutoModel class → modality. We read it at runtime, so when
transformers adds a new task or model, strands-transformers supports it
automatically - no code change required.

This is the same philosophy as `use_aws` (wraps boto3 dynamically) and
`use_lerobot` (wraps lerobot dynamically): discover, don't hardcode.
"""

from __future__ import annotations

import importlib
import inspect
from functools import lru_cache
from typing import Any, Dict, List, Optional


@lru_cache(maxsize=1)
def supported_tasks() -> Dict[str, Dict[str, Any]]:
    """Return transformers' canonical task taxonomy as plain dicts.

    Each entry: {task: {"type": modality, "auto_models": [...], "default": str|None,
                        "pipeline_class": str}}
    """
    from transformers.pipelines import SUPPORTED_TASKS

    out: Dict[str, Dict[str, Any]] = {}
    for task, spec in SUPPORTED_TASKS.items():
        pt = spec.get("pt", ()) or ()
        auto_models = [c.__name__ for c in pt]
        default = None
        d = spec.get("default")
        if isinstance(d, dict):
            # default model may be nested under "model" -> {"pt": (name, rev)}
            m = d.get("model", d)
            if isinstance(m, dict):
                pt_def = m.get("pt")
                if isinstance(pt_def, (list, tuple)) and pt_def:
                    default = pt_def[0] if isinstance(pt_def[0], str) else pt_def[0][0]
            elif isinstance(m, str):
                default = m
        impl = spec.get("impl")
        out[task] = {
            "type": spec.get("type", "unknown"),
            "auto_models": auto_models,
            "default_model": default,
            "pipeline_class": impl.__name__ if impl else None,
        }
    return out


# Modality → which tasks belong to it (derived, not hardcoded)
def tasks_by_modality() -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for task, info in supported_tasks().items():
        groups.setdefault(info["type"], []).append(task)
    for v in groups.values():
        v.sort()
    return groups


def task_info(task: str) -> Optional[Dict[str, Any]]:
    return supported_tasks().get(task)


@lru_cache(maxsize=1)
def task_aliases() -> Dict[str, str]:
    """Official transformers pipeline task aliases (read at runtime, not hardcoded).

    e.g. sentiment-analysis → text-classification, ner → token-classification.
    """
    try:
        from transformers.pipelines import TASK_ALIASES

        return dict(TASK_ALIASES)
    except Exception:
        return {}


def resolve_task(task_or_alias: str) -> Optional[str]:
    """Resolve a task name, tolerating underscores/spaces vs hyphens and
    honoring transformers' own pipeline aliases (sentiment-analysis, ner, ...)."""
    tasks = supported_tasks()
    if task_or_alias in tasks:
        return task_or_alias
    norm = task_or_alias.replace("_", "-").replace(" ", "-").lower()
    if norm in tasks:
        return norm
    # transformers' own aliases (may themselves need normalization to canonical)
    aliases = task_aliases()
    target = aliases.get(task_or_alias) or aliases.get(norm)
    if target:
        if target in tasks:
            return target
        tnorm = target.replace("_", "-").lower()
        if tnorm in tasks:
            return tnorm
    return None


@lru_cache(maxsize=1)
def auto_model_classes() -> List[str]:
    """Every AutoModel* / AutoProcessor / AutoTokenizer entrypoint in transformers."""
    import transformers

    prefixes = (
        "AutoModel",
        "AutoProcessor",
        "AutoTokenizer",
        "AutoFeatureExtractor",
        "AutoImageProcessor",
        "AutoConfig",
        "AutoVideoProcessor",
        "AutoBackbone",
    )
    return sorted(n for n in dir(transformers) if n.startswith(prefixes))


def resolve_attr(dotted: str, root_module: str = "transformers") -> Any:
    """Resolve a dotted path against a root module.

    Examples:
        resolve_attr("AutoModelForImageTextToText")
        resolve_attr("pipeline")
        resolve_attr("AutoModelForCausalLM.from_pretrained")
        resolve_attr("models.qwen2.Qwen2ForCausalLM")
    """
    full = dotted if dotted.startswith(root_module + ".") else f"{root_module}.{dotted}"

    # Try as a module
    try:
        return importlib.import_module(full)
    except ImportError:
        pass

    # Fast path: attribute(s) directly on the root module. This is tried first
    # because frameworks like transformers use a lazy `__getattr__` that raises
    # AttributeError (not ImportError) when you attempt to import a non-module
    # attribute as a submodule - which would otherwise escape the loop below.
    try:
        root = importlib.import_module(root_module)
        obj = root
        for attr in dotted.split("."):
            obj = getattr(obj, attr)
        return obj
    except AttributeError:
        pass

    # Progressive: import deepest importable module, then getattr the rest.
    # Catch Exception (not just ImportError) so lazy-module AttributeErrors
    # during a submodule import attempt don't abort resolution.
    segments = full.split(".")
    for i in range(len(segments), 0, -1):
        try:
            mod = importlib.import_module(".".join(segments[:i]))
        except Exception:
            continue
        obj = mod
        try:
            for attr in segments[i:]:
                obj = getattr(obj, attr)
            return obj
        except AttributeError:
            break

    # Final fallback (raises a clear AttributeError if truly missing)
    root = importlib.import_module(root_module)
    obj = root
    for attr in dotted.split("."):
        obj = getattr(obj, attr)
    return obj


def describe(obj: Any, max_doc: int = 600) -> Dict[str, Any]:
    """Introspect any object: signature, params, methods, docstring."""
    info: Dict[str, Any] = {
        "kind": type(obj).__name__,
        "name": getattr(obj, "__name__", str(obj)[:80]),
    }
    if inspect.isclass(obj):
        info["methods"] = [
            m for m in dir(obj) if not m.startswith("_") and callable(getattr(obj, m, None))
        ][:40]
        for ctor in ("from_pretrained", "__init__"):
            fn = getattr(obj, ctor, None)
            if fn is not None:
                try:
                    info[f"{ctor}_params"] = _sig_params(fn)
                    if fn.__doc__:
                        info[f"{ctor}_doc"] = fn.__doc__[:max_doc]
                    break
                except (ValueError, TypeError):
                    continue
    elif callable(obj):
        try:
            info["params"] = _sig_params(obj)
        except (ValueError, TypeError):
            pass
        if obj.__doc__:
            info["doc"] = obj.__doc__[:max_doc]
    elif inspect.ismodule(obj):
        info["public"] = [n for n in dir(obj) if not n.startswith("_")][:50]
        if obj.__doc__:
            info["doc"] = obj.__doc__[:max_doc]
    else:
        info["value"] = str(obj)[:200]
    return info


def _sig_params(fn: Any) -> Dict[str, Dict[str, str]]:
    sig = inspect.signature(fn)
    return {
        name: {
            "default": ("REQUIRED" if p.default is inspect.Parameter.empty else str(p.default)),
            "annotation": (None if p.annotation is inspect.Parameter.empty else str(p.annotation)),
        }
        for name, p in sig.parameters.items()
        if name != "self"
    }
