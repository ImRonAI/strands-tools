"""strands-transformers type extensions.

The upstream Strands / harness-sdk message schema models text, image, video,
document, tool-use and tool-result content blocks - but has NO audio content
block. Audio-native conversational models (Qwen2-Audio, Qwen2.5-Omni) consume
audio *inside the conversation*, so we extend the taxonomy here with an
`audio` content block and route it through the model provider.
"""

from .audio import (
    AUDIO_FORMATS,
    AudioContent,
    AudioSource,
    extract_audio_payload,
    make_audio_block,
)

__all__ = [
    "AudioContent",
    "AudioSource",
    "make_audio_block",
    "extract_audio_payload",
    "AUDIO_FORMATS",
]
