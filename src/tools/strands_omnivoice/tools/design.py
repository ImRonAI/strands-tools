"""Voice design — describe the speaker via attributes (gender, age, accent...)."""
from __future__ import annotations

from strands import tool

from .._common import ensure_parent, err, ok, resolve_path
from .._loader import get_model


@tool
def omnivoice_design(
    text: str,
    output: str,
    instruct: str,
    language: str = "",
    duration: float = 0.0,
    speed: float = 1.0,
    num_step: int = 32,
    guidance_scale: float = 2.0,
    model_id: str = "",
    device: str = "",
) -> dict:
    """Synthesize speech with a designed voice via comma-separated attributes.

    The ``instruct`` string is a comma-separated list of speaker attributes.
    Categories (mutually exclusive within each):
      - **Gender**: ``male``, ``female``
      - **Age**: ``child``, ``teenager``, ``young adult``, ``middle-aged``, ``elderly``
      - **Pitch**: ``very low pitch``, ``low pitch``, ``moderate pitch``, ``high pitch``, ``very high pitch``
      - **Style**: ``whisper``
      - **English accent** (English text only): ``american accent``, ``british accent``,
        ``australian accent``, ``canadian accent``, ``indian accent``,
        ``chinese accent``, ``korean accent``, ``portuguese accent``,
        ``russian accent``, ``japanese accent``
      - **Chinese dialect** (Chinese text only): ``四川话``, ``陕西话``, ``东北话``, etc.

    Examples:
        ``"female, young adult, high pitch, british accent"``
        ``"male, elderly, low pitch, whisper"``
        ``"女, 青年, 四川话"``

    Args:
        text: Target text.
        output: Path to the output WAV file.
        instruct: Voice-design instruction (see above).
        language: Optional language hint.
        duration: Fixed output duration (overrides speed).
        speed: Speech speed factor.
        num_step: Diffusion steps.
        guidance_scale: Classifier-free guidance scale.
        model_id: Override the cached model id.
        device: Override device.
    """
    if not text.strip():
        return err("`text` is empty")
    if not instruct.strip():
        return err("`instruct` is required for voice design (e.g. 'female, british accent')")
    out = ensure_parent(resolve_path(output))

    try:
        model = get_model(model_id=model_id or None, device=device or None)
    except Exception as e:  # noqa: BLE001
        return err(f"model load failed: {type(e).__name__}: {e}")

    try:
        import soundfile as sf

        audios = model.generate(
            text=text,
            instruct=instruct,
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
        text=f"🎨 designed voice ({instruct}) → {out}",
        data={
            "output": str(out),
            "instruct": instruct,
            "duration_s": float(len(audios[0]) / model.sampling_rate),
            "sampling_rate": int(model.sampling_rate),
            "mode": "design",
        },
    )
