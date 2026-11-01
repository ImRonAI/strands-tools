"""Model lifecycle tools: download / load / unload."""
from __future__ import annotations

from strands import tool

from .._common import err, ok
from .._loader import get_loaded_info, get_model, unload_model


@tool
def omnivoice_load_model(
    model_id: str = "",
    device: str = "",
    dtype: str = "",
    force: bool = False,
) -> dict:
    """Pre-load (or reload) the OmniVoice model into memory.

    Useful as a *warmup* tool — call this once early in the conversation
    so the first synthesis isn't bottlenecked by checkpoint download/load.

    Args:
        model_id: HF repo or local path. Empty = ``STRANDS_OMNIVOICE_MODEL`` or
            default ``k2-fsa/OmniVoice``.
        device: ``cuda`` / ``mps`` / ``cpu`` / ``auto``. Empty = auto.
        dtype: ``float16`` / ``float32`` / ``bfloat16`` / ``auto``. Empty = auto.
        force: If True, reload even if already cached.
    """
    try:
        model = get_model(
            model_id=model_id or None,
            device=device or None,
            dtype=dtype or None,
            force=force,
        )
    except Exception as e:  # noqa: BLE001
        return err(f"load failed: {type(e).__name__}: {e}")

    info = get_loaded_info()
    info["sampling_rate"] = int(model.sampling_rate)
    return ok(text=f"✅ OmniVoice loaded · {info['model_id']} on {info['device']}", data=info)


@tool
def omnivoice_unload_model() -> dict:
    """Drop the cached model and free GPU memory."""
    info_before = get_loaded_info()
    unload_model()
    return ok(
        text="🧹 model unloaded; GPU cache cleared (if applicable)",
        data={"unloaded": info_before},
    )


@tool
def omnivoice_download_model(model_id: str = "k2-fsa/OmniVoice") -> dict:
    """Snapshot-download the OmniVoice checkpoint via HuggingFace Hub.

    Lightweight — does NOT load weights into GPU memory. Useful for staging
    models on edge boxes or in CI before running heavy synthesis.

    Args:
        model_id: HF repo id (default: ``k2-fsa/OmniVoice``).
    """
    try:
        from huggingface_hub import snapshot_download
    except Exception as e:  # noqa: BLE001
        return err(f"huggingface_hub not available: {e}")

    try:
        path = snapshot_download(repo_id=model_id)
    except Exception as e:  # noqa: BLE001
        return err(f"download failed: {type(e).__name__}: {e}")

    return ok(text=f"📥 {model_id} cached at {path}", data={"model_id": model_id, "path": path})
