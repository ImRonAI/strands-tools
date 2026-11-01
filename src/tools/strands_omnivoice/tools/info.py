"""System and model introspection tools."""
from __future__ import annotations

from strands import tool

from .._common import err, ok
from .._loader import best_device, get_loaded_info


@tool
def omnivoice_sysinfo() -> dict:
    """Report device, dtype, OmniVoice version, and currently-loaded model state.

    Use this first to verify the host is ready before spending time on a heavy
    generate call.
    """
    info: dict = {
        "best_device": best_device(),
        "loaded": get_loaded_info(),
    }

    # Soft-import torch — info is still useful without it.
    try:
        import torch

        info["torch"] = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "mps_available": getattr(torch.backends, "mps", None) is not None
            and torch.backends.mps.is_available(),
        }
        if torch.cuda.is_available():
            info["torch"]["device_name"] = torch.cuda.get_device_name(0)
            info["torch"]["memory_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1e9, 1
            )
    except Exception as e:  # noqa: BLE001
        info["torch"] = {"error": str(e)}

    try:
        import omnivoice

        info["omnivoice_version"] = getattr(omnivoice, "__version__", "unknown")
    except Exception as e:  # noqa: BLE001
        return err(f"omnivoice not installed: {e}", data=info)

    return ok(text=f"OmniVoice ready · device={info['best_device']}", data=info)


@tool
def omnivoice_list_languages(filter: str = "") -> dict:
    """List supported language names (subset of 600+).

    OmniVoice supports 600+ languages — the full list lives in
    ``omnivoice.utils.lang_map.LANG_NAMES``. This tool exposes that list
    optionally filtered by a substring (case-insensitive).

    Args:
        filter: Substring to match against language names. Empty = return all.
    """
    try:
        from omnivoice.utils.lang_map import LANG_NAMES, lang_display_name
    except Exception as e:  # noqa: BLE001
        return err(f"omnivoice not installed: {e}")

    names = sorted({lang_display_name(n) for n in LANG_NAMES})
    if filter:
        f = filter.lower()
        names = [n for n in names if f in n.lower()]

    return ok(
        text=f"{len(names)} language(s) {'matching ' + repr(filter) if filter else 'total'}",
        data={"count": len(names), "languages": names},
    )
