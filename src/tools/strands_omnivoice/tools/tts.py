"""Auto-voice TTS — synthesize text without any voice prompt."""
from __future__ import annotations

from strands import tool

from .._common import ensure_parent, err, ok, resolve_path
from .._loader import get_model


@tool
def omnivoice_tts(
    text: str,
    output: str,
    language: str = "",
    duration: float = 0.0,
    speed: float = 1.0,
    num_step: int = 32,
    guidance_scale: float = 2.0,
    model_id: str = "",
    device: str = "",
) -> dict:
    """Synthesize speech from text in *auto-voice* mode (no reference, no instruct).

    The model picks a voice automatically. Use this for the simplest
    text-to-speech path. For voice cloning use ``omnivoice_clone``;
    for attribute-driven voice design use ``omnivoice_design``.

    Args:
        text: The text to synthesize. Supports inline tags such as
            ``[laughter]``, ``[sigh]``, pinyin (Chinese), and CMU phonemes.
        output: Path to write the resulting WAV file.
        language: Optional language hint (e.g. ``"English"`` or ``"en"``).
            Improves quality slightly. Empty = language-agnostic.
        duration: Fixed output duration in seconds (overrides ``speed``).
            ``0`` = let the model estimate.
        speed: Speech speed factor (>1 faster, <1 slower).
        num_step: Diffusion steps. Lower = faster, higher = better quality.
        guidance_scale: Classifier-free guidance scale.
        model_id: Override the cached model id (HF repo or local path).
        device: Override device (``cuda``/``mps``/``cpu``/``auto``).

    Returns:
        Tool result with the path of the generated WAV.
    """
    if not text.strip():
        return err("`text` is empty")
    out = ensure_parent(resolve_path(output))

    try:
        model = get_model(model_id=model_id or None, device=device or None)
    except Exception as e:  # noqa: BLE001
        return err(f"model load failed: {type(e).__name__}: {e}")

    try:
        import soundfile as sf

        audios = model.generate(
            text=text,
            language=language or None,
            duration=duration or None,
            speed=speed,
            num_step=num_step,
            guidance_scale=guidance_scale,
        )
        sf.write(str(out), audios[0], model.sampling_rate)
    except Exception as e:  # noqa: BLE001
        return err(f"generation failed: {type(e).__name__}: {e}")

    return ok(
        text=f"🔊 wrote {out} ({len(audios[0]) / model.sampling_rate:.2f}s @ {model.sampling_rate} Hz)",
        data={
            "output": str(out),
            "duration_s": float(len(audios[0]) / model.sampling_rate),
            "sampling_rate": int(model.sampling_rate),
            "mode": "auto",
        },
    )
