"""Transcribe a reference audio clip using OmniVoice's built-in ASR."""
from __future__ import annotations

from strands import tool

from .._common import err, ok, resolve_path
from .._loader import get_model


@tool
def omnivoice_transcribe(
    audio_path: str,
    asr_model_name: str = "openai/whisper-large-v3-turbo",
    model_id: str = "",
    device: str = "",
) -> dict:
    """Transcribe an audio file using OmniVoice's bundled Whisper ASR.

    Useful when preparing reference audio for voice cloning — instead of
    writing the transcript by hand, run this tool to get one. The ASR model
    is loaded lazily on the first call (cached on the OmniVoice instance).

    Args:
        audio_path: Path to the audio file.
        asr_model_name: HuggingFace ASR model id
            (default: ``openai/whisper-large-v3-turbo``).
        model_id: Override the cached OmniVoice TTS model id.
        device: Override device.
    """
    p = resolve_path(audio_path)
    if not p.exists():
        return err(f"audio not found: {p}")

    try:
        model = get_model(model_id=model_id or None, device=device or None)
    except Exception as e:  # noqa: BLE001
        return err(f"model load failed: {type(e).__name__}: {e}")

    # Lazy-load ASR pipeline if needed.
    if getattr(model, "_asr_pipe", None) is None:
        try:
            model.load_asr_model(model_name=asr_model_name)
        except Exception as e:  # noqa: BLE001
            return err(f"asr load failed: {type(e).__name__}: {e}")

    try:
        # Path-first: model.transcribe(str) calls the HF pipeline directly.
        try:
            text = model.transcribe(str(p))
        except Exception:
            # torchaudio/torchcodec issues → decode with soundfile and pass tensor tuple.
            import soundfile as sf

            waveform, sr = sf.read(str(p), dtype="float32", always_2d=False)
            text = model.transcribe((waveform, sr))
    except Exception as e:  # noqa: BLE001
        return err(f"transcription failed: {type(e).__name__}: {e}")

    text = str(text).strip()
    return ok(
        text=f"📝 {text}" if text else "📝 (empty transcript)",
        data={"audio": str(p), "transcript": text, "asr_model": asr_model_name},
    )
