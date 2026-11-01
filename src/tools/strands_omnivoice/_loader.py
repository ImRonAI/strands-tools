"""Singleton loader for the OmniVoice model.

Multiple tools can call ``get_model()`` and share the same loaded checkpoint —
loading is heavy (model ~hundreds of MB, tokenizers, audio codec), so caching
is essential for agent workflows that mix tools.

Behaviour:
- First call loads the model with auto-detected device (cuda > mps > cpu).
- Subsequent calls return the cached instance.
- Reload by passing ``force=True`` or calling :func:`unload_model`.
- Override device/dtype via env vars or kwargs.

Env vars:
    STRANDS_OMNIVOICE_MODEL    default model id (default: k2-fsa/OmniVoice)
    STRANDS_OMNIVOICE_DEVICE   override device (cuda|mps|cpu|auto)
    STRANDS_OMNIVOICE_DTYPE    override dtype  (float16|float32|bfloat16|auto)
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "model": None,
    "model_id": None,
    "device": None,
    "dtype": None,
}

DEFAULT_MODEL_ID = os.getenv("STRANDS_OMNIVOICE_MODEL", "k2-fsa/OmniVoice")


def best_device() -> str:
    """Auto-detect: cuda > mps > cpu."""
    override = os.getenv("STRANDS_OMNIVOICE_DEVICE", "").lower()
    if override and override != "auto":
        return override
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def _resolve_dtype(device: str, dtype_arg: Optional[str]):
    """Pick a sensible torch dtype for the device."""
    import torch

    name = (dtype_arg or os.getenv("STRANDS_OMNIVOICE_DTYPE", "auto")).lower()
    mapping = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "half": torch.float16,
        "float32": torch.float32,
        "fp32": torch.float32,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
    }
    if name in mapping:
        return mapping[name]
    # auto
    if device == "cpu":
        return torch.float32
    return torch.float16


def get_model(
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    dtype: Optional[str] = None,
    force: bool = False,
):
    """Return a cached :class:`omnivoice.OmniVoice` instance.

    Args:
        model_id: HuggingFace repo id or local path. Defaults to
            ``STRANDS_OMNIVOICE_MODEL`` or ``k2-fsa/OmniVoice``.
        device: One of ``cuda``, ``mps``, ``cpu``, ``auto``. Auto-detect default.
        dtype: One of ``float16``, ``float32``, ``bfloat16``, ``auto``.
        force: If True, reload even if a cached instance exists.

    Returns:
        Loaded ``OmniVoice`` model.
    """
    target_id = model_id or DEFAULT_MODEL_ID
    target_device = (device or best_device()).lower()

    with _LOCK:
        # Reuse if same key and not forced
        if (
            not force
            and _STATE["model"] is not None
            and _STATE["model_id"] == target_id
            and _STATE["device"] == target_device
        ):
            return _STATE["model"]

        # Lazy import — keeps import cheap until first use
        from omnivoice import OmniVoice

        torch_dtype = _resolve_dtype(target_device, dtype)
        logger.info(
            "Loading OmniVoice id=%s device=%s dtype=%s", target_id, target_device, torch_dtype
        )

        model = OmniVoice.from_pretrained(
            target_id, device_map=target_device, dtype=torch_dtype
        )

        _STATE["model"] = model
        _STATE["model_id"] = target_id
        _STATE["device"] = target_device
        _STATE["dtype"] = str(torch_dtype)
        return model


def get_loaded_info() -> dict:
    """Inspect what's currently cached (or empty if nothing loaded)."""
    return {
        "loaded": _STATE["model"] is not None,
        "model_id": _STATE["model_id"],
        "device": _STATE["device"],
        "dtype": _STATE["dtype"],
        "sampling_rate": getattr(_STATE["model"], "sampling_rate", None),
    }


def unload_model() -> None:
    """Drop cached model and free GPU memory."""
    with _LOCK:
        _STATE["model"] = None
        _STATE["model_id"] = None
        _STATE["device"] = None
        _STATE["dtype"] = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass
