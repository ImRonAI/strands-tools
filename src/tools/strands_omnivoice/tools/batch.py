"""Batch synthesis — generate multiple WAVs in one call."""
from __future__ import annotations

import json
from pathlib import Path

from strands import tool

from .._common import ensure_parent, err, ok, resolve_path
from .._loader import get_model


@tool
def omnivoice_batch(
    items: list,
    output_dir: str,
    num_step: int = 32,
    guidance_scale: float = 2.0,
    model_id: str = "",
    device: str = "",
) -> dict:
    """Generate multiple TTS samples sequentially using a single loaded model.

    Each item in ``items`` is a dict with at least ``id`` and ``text``. Optional
    keys mirror :func:`omnivoice_tts` / :func:`omnivoice_clone` /
    :func:`omnivoice_design` parameters:

        {
            "id": "sample_001",            # required → output filename stem
            "text": "Hello world.",         # required
            "ref_audio": "/path/ref.wav",  # → cloning mode (optional)
            "ref_text": "...",              # optional reference transcript
            "instruct": "female, british accent",  # → design mode (optional)
            "language": "en",
            "duration": 0,
            "speed": 1.0
        }

    If ``ref_audio`` is set, the item runs in **clone** mode; if ``instruct``
    is set, **design** mode; otherwise **auto**.

    For very large jobs across multiple GPUs, prefer the upstream
    ``omnivoice-infer-batch`` CLI.

    Args:
        items: Sequence of dicts (or a JSON-string list/JSONL path).
        output_dir: Directory to write ``<id>.wav`` files into.
        num_step: Diffusion steps.
        guidance_scale: Classifier-free guidance scale.
        model_id: Override the cached model id.
        device: Override device.
    """
    # Accept JSON string or path-to-JSONL for convenience
    if isinstance(items, str):
        s = items.strip()
        if s.endswith(".jsonl") and Path(s).exists():
            items = [json.loads(line) for line in Path(s).read_text().splitlines() if line.strip()]
        else:
            try:
                items = json.loads(s)
            except json.JSONDecodeError as e:
                return err(f"`items` is a string but not valid JSON / .jsonl path: {e}")

    if not isinstance(items, list) or not items:
        return err("`items` must be a non-empty list of dicts")

    out_dir = resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        model = get_model(model_id=model_id or None, device=device or None)
    except Exception as e:  # noqa: BLE001
        return err(f"model load failed: {type(e).__name__}: {e}")

    import soundfile as sf

    written: list[dict] = []
    failed: list[dict] = []

    for i, raw in enumerate(items):
        if not isinstance(raw, dict):
            failed.append({"index": i, "error": "item is not a dict"})
            continue

        item_id = str(raw.get("id") or f"sample_{i:04d}")
        text = raw.get("text", "")
        if not text:
            failed.append({"index": i, "id": item_id, "error": "missing `text`"})
            continue

        out = ensure_parent(out_dir / f"{item_id}.wav")
        try:
            audios = model.generate(
                text=text,
                ref_audio=raw.get("ref_audio") or None,
                ref_text=raw.get("ref_text") or None,
                instruct=raw.get("instruct") or None,
                language=raw.get("language") or None,
                duration=raw.get("duration") or None,
                speed=raw.get("speed", 1.0),
                num_step=num_step,
                guidance_scale=guidance_scale,
            )
            sf.write(str(out), audios[0], model.sampling_rate)
            written.append(
                {
                    "id": item_id,
                    "output": str(out),
                    "duration_s": float(len(audios[0]) / model.sampling_rate),
                    "mode": (
                        "clone" if raw.get("ref_audio") else
                        "design" if raw.get("instruct") else "auto"
                    ),
                }
            )
        except Exception as e:  # noqa: BLE001
            failed.append({"index": i, "id": item_id, "error": f"{type(e).__name__}: {e}"})

    return ok(
        text=f"✅ wrote {len(written)} / {len(items)} samples to {out_dir}",
        data={"output_dir": str(out_dir), "written": written, "failed": failed},
    )
