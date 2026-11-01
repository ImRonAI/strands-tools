"""Core primitives: registry (task taxonomy), engine (load/cache/run), io (multimodal)."""

from . import engine, io, registry

__all__ = ["registry", "engine", "io"]
