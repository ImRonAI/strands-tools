"""Strands OmniVoice — multilingual zero-shot TTS for Strands Agents.

Wraps `OmniVoice <https://github.com/k2-fsa/OmniVoice>`_ — a 600+ language
zero-shot TTS model — as a set of @tool functions plus a model loader.

Quick start:

    from strands import Agent
    from strands_omnivoice import (
        omnivoice_tts, omnivoice_clone, omnivoice_design,
        omnivoice_sysinfo, audio_play,
    )

    agent = Agent(tools=[
        omnivoice_tts, omnivoice_clone, omnivoice_design,
        omnivoice_sysinfo, audio_play,
    ])
    agent("Synthesize 'Hello world.' to /tmp/hello.wav and play it.")
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("strands-omnivoice")
except PackageNotFoundError:
    __version__ = "0.1.0"

# Exposed loader API for advanced users
from ._loader import best_device, get_loaded_info, get_model, unload_model
from .tools import (
    audio_play,
    audio_probe,
    omnivoice_batch,
    omnivoice_clone,
    omnivoice_demo_serve,
    omnivoice_design,
    omnivoice_download_model,
    omnivoice_list_languages,
    omnivoice_load_model,
    omnivoice_sysinfo,
    omnivoice_transcribe,
    omnivoice_tts,
    omnivoice_unload_model,
)

__all__ = [
    "__version__",
    # synthesis
    "omnivoice_tts",
    "omnivoice_clone",
    "omnivoice_design",
    "omnivoice_batch",
    # ASR
    "omnivoice_transcribe",
    # model lifecycle
    "omnivoice_load_model",
    "omnivoice_unload_model",
    "omnivoice_download_model",
    # info
    "omnivoice_sysinfo",
    "omnivoice_list_languages",
    # audio utilities
    "audio_probe",
    "audio_play",
    # web UI
    "omnivoice_demo_serve",
    # loader API
    "get_model",
    "get_loaded_info",
    "unload_model",
    "best_device",
]
