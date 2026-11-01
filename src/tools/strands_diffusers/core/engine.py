"""Pipeline engine — load once, cache, run. Auto device/dtype.

Wraps diffusers' `DiffusionPipeline.from_pretrained` (and any specific pipeline
class) as the universal loader. Pipelines are cached per (class, model) so repeat
runs are cheap, and a generic `load_object` lets you reach any diffusers class
(schedulers, VAEs, transformers) for low-level control — the equivalent of the
`call` layer in use_transformers.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# session-scoped cache of loaded objects (pipelines, models, schedulers)
_CACHE: Dict[str, Any] = {}


def select_device(device: Optional[str] = None) -> str:
    if device and device != "auto":
        return device
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def select_dtype(device: str):
    """Pick a sensible default dtype for diffusion on the device."""
    try:
        import torch
        if device == "cuda":
            return torch.bfloat16
        if device == "mps":
            return torch.float16
    except ImportError:
        pass
    return None  # float32 on cpu


def get_pipeline(pipeline_class: str, model: str,
                 device: Optional[str] = None, cache_key: Optional[str] = None,
                 dtype: Optional[str] = None, move_to_device: bool = True,
                 **from_pretrained_kwargs: Any):
    """Build (or fetch cached) a diffusers pipeline.

    Args:
        pipeline_class: diffusers pipeline class name, e.g. "StableDiffusionPipeline",
            "Cosmos3OmniPipeline", or "DiffusionPipeline" for auto-detection.
        model: HF repo id or local path.
        device: "cuda" / "mps" / "cpu" / "auto".
        cache_key: name to cache under (default derived from class+model).
        dtype: explicit torch dtype name ("bfloat16","float16","float32") or None.
        move_to_device: call .to(device) unless device_map was passed.
    """
    from . import registry

    key = cache_key or f"pipe::{pipeline_class}::{model}"
    if key in _CACHE:
        return _CACHE[key], key

    cls = registry.resolve_attr(pipeline_class)
    dev = select_device(device)
    kwargs = dict(from_pretrained_kwargs)

    # dtype: explicit name > device default. diffusers accepts torch_dtype.
    if "torch_dtype" not in kwargs and "dtype" not in kwargs:
        td = _resolve_dtype(dtype) if dtype else select_dtype(dev)
        if td is not None:
            kwargs["torch_dtype"] = td

    logger.info("Loading %s from %s on %s", pipeline_class, model, dev)
    pipe = cls.from_pretrained(model, **kwargs)

    # --- torchsde recursion guard ---------------------------------------
    # Some pipelines (e.g. StableAudioPipeline) ship with
    # CosineDPMSolverMultistepScheduler, which depends on torchsde. On several
    # torch builds torchsde's Brownian-interval tree hits a RecursionError,
    # crashing generation. Auto-swap to the non-SDE DPMSolverMultistepScheduler
    # (same family, deterministic, no torchsde) so the one-call path just works.
    # Opt out with STRANDS_DIFFUSERS_KEEP_SDE_SCHEDULER=1.
    if os.environ.get("STRANDS_DIFFUSERS_KEEP_SDE_SCHEDULER", "") not in ("1", "true", "True"):
        try:
            sched = getattr(pipe, "scheduler", None)
            if sched is not None and type(sched).__name__ == "CosineDPMSolverMultistepScheduler":
                from diffusers import DPMSolverMultistepScheduler
                pipe.scheduler = DPMSolverMultistepScheduler.from_config(sched.config)
                logger.info(
                    "Auto-swapped CosineDPMSolverMultistepScheduler -> "
                    "DPMSolverMultistepScheduler (avoids torchsde RecursionError). "
                    "Set STRANDS_DIFFUSERS_KEEP_SDE_SCHEDULER=1 to keep the original."
                )
        except Exception as e:
            logger.debug("Scheduler auto-swap skipped: %s", e)

    # move to device unless from_pretrained already placed it (device_map)
    if move_to_device and "device_map" not in kwargs and hasattr(pipe, "to"):
        try:
            pipe = pipe.to(dev)
        except Exception as e:
            logger.debug("Could not .to(%s): %s", dev, e)

    _CACHE[key] = pipe
    return pipe, key


def load_object(class_name: str, model_path: Optional[str] = None,
                device: Optional[str] = None, cache_key: Optional[str] = None,
                from_config: bool = False, **kwargs: Any):
    """Load any diffusers class via from_pretrained / from_config.

    For lower-level control than full pipelines — schedulers, VAEs, transformers,
    e.g. swap a pipeline's scheduler:
        load_object("UniPCMultistepScheduler", from_config=True, config=cached_cfg)
    """
    from . import registry

    key = cache_key or f"obj::{class_name}::{model_path or 'cfg'}"
    if key in _CACHE:
        return _CACHE[key], key

    cls = registry.resolve_attr(class_name)
    if from_config:
        obj = cls.from_config(**kwargs)
    else:
        dev = select_device(device)
        if class_name.endswith(("Model", "Transformer")) or class_name.startswith("Autoencoder"):
            if "torch_dtype" not in kwargs and "dtype" not in kwargs:
                td = select_dtype(dev)
                if td is not None:
                    kwargs["torch_dtype"] = td
        obj = cls.from_pretrained(model_path, **kwargs)

    _CACHE[key] = obj
    return obj, key


def _resolve_dtype(name: str):
    import torch
    return {
        "bfloat16": torch.bfloat16, "bf16": torch.bfloat16,
        "float16": torch.float16, "fp16": torch.float16, "half": torch.float16,
        "float32": torch.float32, "fp32": torch.float32, "float": torch.float32,
    }.get(str(name).lower())


def cache_list() -> Dict[str, str]:
    return {k: type(v).__name__ for k, v in _CACHE.items()}


def cache_clear(key: Optional[str] = None) -> int:
    if key:
        if key in _CACHE:
            del _CACHE[key]
            _free_memory()
            return 1
        return 0
    n = len(_CACHE)
    _CACHE.clear()
    _free_memory()
    return n


def cache_get(key: str) -> Optional[Any]:
    return _CACHE.get(key)


def _free_memory():
    try:
        import gc

        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
