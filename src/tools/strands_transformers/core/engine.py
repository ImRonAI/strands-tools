"""Pipeline & model engine - load once, cache, run. Auto device/dtype.

Wraps transformers.pipeline() as the universal native-I/O runner, plus a generic
loader for raw AutoModel/AutoProcessor access when you need lower-level control
(e.g. robot VLA models that output action tensors).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# session-scoped cache of loaded objects (pipelines, models, processors)
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
    """Pick a sensible default dtype for the device (handles cuda:N / mps)."""
    try:
        import torch

        dev = str(device)
        if dev.startswith("cuda"):
            return torch.bfloat16
        if dev.startswith("mps"):
            return torch.float16
    except ImportError:
        pass
    return None  # let transformers decide (float32 on cpu)


def get_pipeline(
    task: str,
    model: Optional[str] = None,
    device: Optional[str] = None,
    cache_key: Optional[str] = None,
    **pipeline_kwargs: Any,
):
    """Build (or fetch cached) a transformers pipeline for a task.

    pipeline() natively accepts paths/URLs/PIL/arrays as input and handles
    tokenization, image processing, feature extraction, etc. automatically.
    """
    from . import compat

    compat.apply()
    from transformers import pipeline

    key = cache_key or f"pipe::{task}::{model or 'default'}"
    if key in _CACHE:
        return _CACHE[key], key

    dev = select_device(device)
    kwargs: Dict[str, Any] = {"task": task}
    if model:
        kwargs["model"] = model
    # device handling: pipeline takes device int/str or device_map.
    # Honor explicit cuda:N (e.g. multi-GPU) instead of silently falling to CPU.
    if dev == "cuda":
        kwargs["device"] = 0
    elif dev.startswith("cuda:"):
        kwargs["device"] = dev  # transformers parses "cuda:1"
    elif dev.startswith("mps"):
        kwargs["device"] = "mps"
    else:
        kwargs["device"] = -1
    # Tasks whose post-processing produces images/dense maps/audio need float32 -
    # half precision (bf16/fp16) breaks PIL/numpy conversion ("unsupported
    # ScalarType BFloat16") and audio synthesis (speaker-embedding/vocoder matmuls
    # mix Float x BFloat16). Skip the half-precision default for those; callers
    # can still override via pipeline_kwargs.
    _FLOAT32_TASKS = {
        "depth-estimation",
        "image-segmentation",
        "image-to-image",
        "semantic-segmentation",
        "instance-segmentation",
        "mask-generation",
        "text-to-speech",
        "text-to-audio",
    }
    dtype = None if task in _FLOAT32_TASKS else select_dtype(dev)
    if dtype is not None:
        kwargs["dtype"] = dtype
    kwargs.update(pipeline_kwargs)

    logger.info("Loading pipeline task=%s model=%s device=%s", task, model, dev)
    pipe = pipeline(**kwargs)
    _CACHE[key] = pipe
    return pipe, key


def load_object(
    auto_class: str,
    model_path: str,
    device: Optional[str] = None,
    cache_key: Optional[str] = None,
    **from_pretrained_kwargs: Any,
):
    """Load any AutoModel*/AutoProcessor/AutoTokenizer via from_pretrained.

    For lower-level control than pipelines - e.g. VLA / robot-action models where
    you feed processor(images, text, state) and call model.generate / model(**).
    """
    from . import compat, registry

    compat.apply(force=True)
    key = cache_key or f"obj::{auto_class}::{model_path}"
    if key in _CACHE:
        return _CACHE[key], key

    cls = registry.resolve_attr(auto_class)
    dev = select_device(device)
    kwargs = dict(from_pretrained_kwargs)
    # only models (not processors/tokenizers) take dtype/device_map
    if auto_class.startswith("AutoModel") or auto_class.startswith("AutoBackbone"):
        dtype = select_dtype(dev)
        if dtype is not None and "dtype" not in kwargs and "torch_dtype" not in kwargs:
            kwargs["dtype"] = dtype
        if "trust_remote_code" not in kwargs:
            kwargs["trust_remote_code"] = True

    logger.info("Loading %s from %s on %s", auto_class, model_path, dev)
    obj = cls.from_pretrained(model_path, **kwargs)

    if hasattr(obj, "to") and (
        auto_class.startswith("AutoModel") or auto_class.startswith("AutoBackbone")
    ):
        try:
            obj = obj.to(dev)
        except Exception as e:  # some models pinned via device_map
            logger.debug("Could not .to(%s): %s", dev, e)

    _CACHE[key] = obj
    return obj, key


def cache_list() -> Dict[str, str]:
    return {k: type(v).__name__ for k, v in _CACHE.items()}


def cache_clear(key: Optional[str] = None) -> int:
    global _CACHE
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
