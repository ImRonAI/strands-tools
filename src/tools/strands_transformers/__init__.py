"""Strands Transformers - the universal entrypoint to HuggingFace transformers.

100% transformers coverage with zero hardcoding: every task across every modality
(text, image, video, audio, robot-state) in and out, the same way `use_aws` wraps
boto3 and `use_lerobot` wraps lerobot.

Quick start:
    from strands import Agent
    from strands_transformers import use_transformers

    agent = Agent(tools=[use_transformers])
    agent("Transcribe recording.wav")            # ASR
    agent("Describe scene.jpg and plan a grasp") # image-text-to-text / VLA
    agent("Say 'hello' as audio")                # text-to-audio

    # Or use a local HF model as the agent's brain:
    from strands_transformers import TransformerModel
    model = TransformerModel(model_path="Qwen/Qwen3-1.7B")
    agent = Agent(model=model, tools=[use_transformers])
"""

try:
    # Written by setuptools-scm at build time (from the git tag).
    from strands_transformers._version import version as __version__
except Exception:
    try:
        # Installed-but-no-_version (rare) → ask importlib.metadata.
        from importlib.metadata import version as _pkg_version

        __version__ = _pkg_version("strands-transformers")
    except Exception:
        __version__ = "0.0.0+unknown"

from strands_transformers.core import engine, io, registry
from strands_transformers.tools.use_transformers import use_transformers


def __getattr__(name):
    # Lazy import the model provider (pulls in torch) only when requested.
    if name == "TransformerModel":
        from strands_transformers.models.transformers import TransformerModel

        return TransformerModel
    # Audio content-block helpers (our extension to the Strands taxonomy).
    if name in ("make_audio_block", "extract_audio_payload", "AudioContent"):
        from strands_transformers.types import audio as _audio

        return getattr(_audio, name)
    raise AttributeError(f"module 'strands_transformers' has no attribute '{name}'")


__all__ = [
    "use_transformers",
    "TransformerModel",
    "make_audio_block",
    "extract_audio_payload",
    "AudioContent",
    "registry",
    "engine",
    "io",
]
