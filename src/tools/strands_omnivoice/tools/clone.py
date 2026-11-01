"""Voice cloning — clone a speaker from a 3-10s reference audio clip."""
from __future__ import annotations

from strands import tool

from .._common import ensure_parent, err, ok, resolve_path
from .._loader import get_model


@tool
def omnivoice_clone(
    text: str,
    output: str,
    ref_audio: str,
    ref_text: str = "",
    language: str = "",
    duration: float = 0.0,
    speed: float = 1.0,
    num_step: int = 32,
    guidance_scale: float = 2.0,
    model_id: str = "",
    device: str = "",
) -> dict:
    """Clone a speaker's voice from a short reference clip and synthesize ``text``.

    Best results with **3–10 seconds** of clean reference audio. Longer clips
    slow inference and may degrade quality. For best pronunciation, use a
    reference in the **same language** as the target text — cross-lingual
    cloning will carry the reference language's accent.

    If ``ref_text`` is empty, OmniVoice auto-transcribes the reference using
    Whisper.

    Args:
        text: Target text to synthesize.
        output: Path to write the resulting WAV file.
        ref_audio: Path to the reference audio (any common format).
        ref_text: Transcript of the reference audio. Empty = auto-Whisper.
        language: Optional language hint (``"English"`` / ``"en"`` / ...).
        duration: Fixed output duration in seconds (overrides ``speed``).
        speed: Speech speed factor.
        num_step: Diffusion steps.
        guidance_scale: Classifier-free guidance scale.
        model_id: Override the cached model id.
        device: Override device.
    """
    if not text.strip():
        return err("`text` is empty")
    if not ref_audio:
        return err("`ref_audio` is required for voice cloning")

    ref = resolve_path(ref_audio)
    if not ref.exists():
        return err(f"ref_audio not found: {ref}")
    out = ensure_parent(resolve_path(output))

    try:
        model = get_model(model_id=model_id or None, device=device or None)
    except Exception as e:  # noqa: BLE001
        return err(f"model load failed: {type(e).__name__}: {e}")

    try:
        import soundfile as sf

        audios = model.generate(
            text=text,
            ref_audio=str(ref),
            ref_text=ref_text or None,
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
        text=f"🎙️ cloned voice → {out} ({len(audios[0]) / model.sampling_rate:.2f}s)",
        data={
            "output": str(out),
            "ref_audio": str(ref),
            "auto_transcribed": not bool(ref_text),
            "duration_s": float(len(audios[0]) / model.sampling_rate),
            "sampling_rate": int(model.sampling_rate),
            "mode": "clone",
        },
    )
