"""Audio content block - a local extension to the Strands content taxonomy.

The Strands `ContentBlock` (and the harness-sdk WIT `content-block` variant)
do not define an audio arm. Audio-native models (Qwen2-Audio, Qwen2.5-Omni)
take audio *within* the conversation, so we add a compatible `audio` block
shaped exactly like the existing media blocks (`image`, `video`):

    {"audio": {"format": "wav", "source": {"bytes": <wav bytes | np waveform>}}}

`source.bytes` may hold:
  - raw container bytes (wav/mp3/flac/ogg ...) - decoded by the provider
  - a float32/float64 numpy waveform (mono) - used as-is
  - a (waveform, sampling_rate) tuple

This mirrors `strands.types.media.ImageContent` / `VideoContent` so the same
content-block plumbing the SDK already understands carries audio too.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

try:
    from typing import TypedDict
except Exception:  # pragma: no cover
    TypedDict = dict  # type: ignore

# Formats the provider knows how to decode (via stdlib wave or torchaudio/sf).
AUDIO_FORMATS = ("wav", "mp3", "flac", "ogg", "m4a", "aac", "webm", "pcm")


class AudioSource(TypedDict, total=False):
    """Source of audio bytes (mirrors ImageSource/VideoSource)."""

    bytes: Any  # raw container bytes, np waveform, or (waveform, sr) tuple
    sampling_rate: int  # optional; required when bytes is a raw waveform


class AudioContent(TypedDict, total=False):
    """An audio clip to include in a message (mirrors ImageContent)."""

    format: str
    source: AudioSource


def make_audio_block(
    data: Any,
    fmt: str = "wav",
    sampling_rate: Optional[int] = None,
) -> dict:
    """Build an `audio` content block for a Strands message.

    Args:
        data: wav/container bytes, a mono numpy waveform, or (waveform, sr).
        fmt: container format hint (default "wav").
        sampling_rate: sample rate when ``data`` is a raw waveform.

    Returns:
        ``{"audio": {"format": fmt, "source": {"bytes": data, ...}}}``
    """
    source: AudioSource = {"bytes": data}
    if sampling_rate is not None:
        source["sampling_rate"] = sampling_rate
    return {"audio": {"format": fmt, "source": source}}


def extract_audio_payload(block: dict) -> Tuple[Any, Optional[int]]:
    """Pull (payload, sampling_rate) out of an `audio` content block.

    Accepts the full block ``{"audio": {...}}`` or the inner audio dict, and
    tolerates a bare payload (bytes/np array/tuple).

    Returns:
        (payload, sampling_rate_or_None) where payload is bytes, a numpy
        waveform, or a (waveform, sr) tuple.
    """
    audio = block.get("audio", block) if isinstance(block, dict) else block

    if isinstance(audio, dict):
        src = audio.get("source", audio)
        if isinstance(src, dict):
            payload = src.get("bytes", src)
            sr = src.get("sampling_rate")
            if isinstance(payload, tuple) and len(payload) == 2:
                return payload[0], payload[1]
            return payload, sr
        return src, None

    if isinstance(audio, tuple) and len(audio) == 2:
        return audio[0], audio[1]
    return audio, None
