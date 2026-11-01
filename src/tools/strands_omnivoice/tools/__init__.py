"""Strands OmniVoice tools — multilingual zero-shot TTS as agent capabilities.

Tool families:
  - Synthesis:        omnivoice_tts, omnivoice_clone, omnivoice_design, omnivoice_batch
  - ASR:              omnivoice_transcribe
  - Model lifecycle:  omnivoice_load_model, omnivoice_unload_model, omnivoice_download_model
  - System info:      omnivoice_sysinfo, omnivoice_list_languages
  - Audio utilities:  audio_probe, audio_play
  - Web UI:           omnivoice_demo_serve
"""
from .audio_utils import audio_play, audio_probe
from .batch import omnivoice_batch
from .clone import omnivoice_clone
from .demo_server import omnivoice_demo_serve
from .design import omnivoice_design
from .info import omnivoice_list_languages, omnivoice_sysinfo
from .model_lifecycle import (
    omnivoice_download_model,
    omnivoice_load_model,
    omnivoice_unload_model,
)
from .transcribe import omnivoice_transcribe
from .tts import omnivoice_tts

__all__ = [
    # synthesis
    "omnivoice_tts",
    "omnivoice_clone",
    "omnivoice_design",
    "omnivoice_batch",
    # ASR
    "omnivoice_transcribe",
    # lifecycle
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
]
