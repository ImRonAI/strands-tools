"""Native multimodal I/O - take images/video/audio/text/arrays in, get them out.

Inputs: file paths, URLs, base64 data URIs, raw bytes, numpy arrays, PIL images.
Outputs: any pipeline result serialized to JSON-safe form, with binary artifacts
(audio waveforms, generated images) written to disk and referenced by path.

The goal: an agent can pass "cat.jpg" or "https://.../clip.mp4" or a numpy robot
state array, and receive back text + paths to generated media, all natively.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_DIR = (
    Path(os.getenv("STRANDS_TRANSFORMERS_ARTIFACTS", tempfile.gettempdir()))
    / "strands_transformers"
)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


# ───────────────────────── INPUT COERCION ─────────────────────────


def coerce_input(value: Any, _depth: int = 0) -> Any:
    """Best-effort coercion of an input spec into something a pipeline accepts.

    Pipelines already accept paths/URLs/PIL/arrays natively, so mostly we just
    decode base64 data URIs and pass everything else through untouched.

    A depth guard prevents RecursionError on pathologically/maliciously nested
    structures (returns the value untouched past the cap).
    """
    if _depth > 32:
        return value
    if isinstance(value, str):
        if value.startswith("data:"):
            return _decode_data_uri(value)
        return value  # path / URL / text - pipelines handle these
    if isinstance(value, list):
        return [coerce_input(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        return {k: coerce_input(v, _depth + 1) for k, v in value.items()}
    return value


def _decode_data_uri(uri: str) -> Any:
    """Decode a data: URI into a PIL Image / bytes depending on mime."""
    header, _, b64 = uri.partition(",")
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception as e:
        raise ValueError(f"Malformed base64 in data URI: {e}") from None
    mime = header.split(";")[0].removeprefix("data:")
    if mime.startswith("image/"):
        from PIL import Image

        return Image.open(io.BytesIO(raw)).convert("RGB")
    return raw


def decode_wav(path: str):
    """Decode a WAV file to (float32 mono array, sampling_rate) using stdlib wave.

    Lets audio tasks (ASR) accept .wav file paths without requiring ffmpeg /
    torchcodec / soundfile - we hand the pipeline a pre-decoded array instead.
    Returns None if the file isn't a readable WAV.
    """
    import wave

    import numpy as np

    try:
        with wave.open(path, "rb") as w:
            n_channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            sr = w.getframerate()
            raw = w.readframes(w.getnframes())
    except Exception:
        return None

    # NB: per the WAV spec, 8-bit PCM is UNSIGNED (0..255, silence at 128);
    # 16/32-bit are signed. Decode each correctly to float32 in [-1, 1].
    if sampwidth == 1:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        dtype = {2: np.int16, 4: np.int32}.get(sampwidth)
        if dtype is None:
            return None
        arr = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        arr = arr / float(np.iinfo(dtype).max)
    if n_channels > 1:
        arr = arr.reshape(-1, n_channels).mean(axis=1)  # downmix to mono
    return arr, sr


def maybe_decode_audio_path(value: Any):
    """If `value` is a path to a .wav file, decode it to a pipeline-ready dict.

    Returns {"raw": ndarray, "sampling_rate": int} or None.
    """
    import os

    if isinstance(value, str) and value.lower().endswith(".wav") and os.path.exists(value):
        decoded = decode_wav(value)
        if decoded is not None:
            arr, sr = decoded
            return {"raw": arr, "sampling_rate": sr}
    return None


def load_array(spec: Any):
    """Load a numpy array from list, .npy path, or pass through ndarray.

    Useful for robot state / time-series inputs.
    """
    import numpy as np

    if isinstance(spec, np.ndarray):
        return spec
    if isinstance(spec, (list, tuple)):
        return np.asarray(spec)
    if isinstance(spec, str) and spec.endswith(".npy"):
        return np.load(spec)
    raise ValueError(f"Cannot load array from {type(spec).__name__}")


# ───────────────────────── OUTPUT SERIALIZATION ─────────────────────────


def serialize_output(result: Any, task: str = "", save_artifacts: bool = True) -> Dict[str, Any]:
    """Convert any pipeline/model output into a JSON-safe dict.

    Binary artifacts (audio, images) are written to ARTIFACT_DIR and referenced
    by path so the agent can hand them to the user or downstream tools.
    """
    artifacts: List[str] = []
    payload = _serialize(result, artifacts, save_artifacts)
    payload = _ensure_json_safe(payload)
    out: Dict[str, Any] = {"result": payload}
    if artifacts:
        out["artifacts"] = artifacts
    return out


def _ensure_json_safe(obj: Any) -> Any:
    """Final guarantee that the serialized payload is JSON-encodable.

    _serialize already converts known types; this is a cheap safety net that
    stringifies anything still non-encodable (so the tool never returns a result
    that breaks json.dumps downstream).
    """
    import json as _json

    try:
        _json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            return {str(k): _ensure_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_ensure_json_safe(v) for v in obj]
        return str(obj)[:500]


def _serialize(obj: Any, artifacts: List[str], save: bool, depth: int = 0) -> Any:
    if depth > 6:
        return str(obj)[:200]

    # Primitives
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Raw bytes → base64 (recoverable + JSON-safe, never a lossy repr string)
    if isinstance(obj, (bytes, bytearray)):
        import base64

        data = bytes(obj)
        return {
            "type": "bytes",
            "encoding": "base64",
            "size": len(data),
            "data": base64.b64encode(data).decode("ascii"),
        }

    # Audio dict from TTS pipelines: {"audio": ndarray, "sampling_rate": int}
    if isinstance(obj, dict) and "audio" in obj and "sampling_rate" in obj:
        if save:
            path = _save_audio(obj["audio"], obj["sampling_rate"])
            artifacts.append(path)
            return {"type": "audio", "path": path, "sampling_rate": obj["sampling_rate"]}
        return {"type": "audio", "sampling_rate": obj["sampling_rate"]}

    # PIL image
    try:
        from PIL import Image

        if isinstance(obj, Image.Image):
            if save:
                path = _save_image(obj)
                artifacts.append(path)
                return {"type": "image", "path": path, "size": list(obj.size)}
            return {"type": "image", "size": list(obj.size)}
    except ImportError:
        pass

    # numpy / torch tensors
    arr = _maybe_array(obj)
    if arr is not None:
        return arr

    # Mappings & sequences (cap breadth so a pathologically large pipeline result
    # can't produce an unbounded JSON payload; mirrors the list/set cap of 200).
    _MAX_ITEMS = 200
    if isinstance(obj, dict):
        items = list(obj.items())
        out = {str(k): _serialize(v, artifacts, save, depth + 1) for k, v in items[:_MAX_ITEMS]}
        if len(items) > _MAX_ITEMS:
            out["__truncated__"] = f"{len(items) - _MAX_ITEMS} more keys omitted"
        return out
    if isinstance(obj, (list, tuple)):
        return [_serialize(v, artifacts, save, depth + 1) for v in obj[:_MAX_ITEMS]]
    if isinstance(obj, (set, frozenset)):
        return [_serialize(v, artifacts, save, depth + 1) for v in list(obj)[:_MAX_ITEMS]]

    # Objects with __dict__ (e.g. ModelOutput) → try dict-like
    if hasattr(obj, "to_dict"):
        try:
            return _serialize(obj.to_dict(), artifacts, save, depth + 1)
        except Exception:
            pass
    if hasattr(obj, "keys"):
        try:
            return {str(k): _serialize(obj[k], artifacts, save, depth + 1) for k in obj.keys()}
        except Exception:
            pass

    return str(obj)[:50000]


def _maybe_array(obj: Any) -> Optional[Any]:
    """Convert numpy/torch arrays to nested lists, summarizing huge ones."""
    # torch tensor
    try:
        import torch

        if isinstance(obj, torch.Tensor):
            obj = obj.detach().cpu()
            # numpy has no bfloat16/float16-on-some-ops support → upcast first
            if obj.dtype in (torch.bfloat16, torch.float16):
                obj = obj.to(torch.float32)
            obj = obj.numpy()
    except ImportError:
        pass
    try:
        import numpy as np

        if isinstance(obj, (np.ndarray, np.generic)):
            a = np.asarray(obj)
            if a.size <= 256:
                return a.tolist()
            return {
                "type": "ndarray",
                "shape": list(a.shape),
                "dtype": str(a.dtype),
                "preview": a.flatten()[:16].tolist(),
            }
    except ImportError:
        pass
    return None


def _save_audio(audio, sampling_rate: int) -> str:
    import numpy as np

    a = np.asarray(audio)
    if a.ndim > 1:
        a = a.squeeze()
    path = ARTIFACT_DIR / f"audio_{int(time.time() * 1000)}.wav"
    try:
        import soundfile as sf

        sf.write(str(path), a, int(sampling_rate))
    except ImportError:
        _write_wav_stdlib(str(path), a, int(sampling_rate))
    return str(path)


def _write_wav_stdlib(path: str, audio, sampling_rate: int) -> None:
    """Write a WAV without soundfile, using the stdlib wave module."""
    import wave

    import numpy as np

    a = np.asarray(audio, dtype=np.float32)
    # Sanitize NaN/Inf (→ 0 / ±1) before the int16 cast, which is otherwise
    # undefined and emits "invalid value encountered in cast" + garbage samples.
    a = np.nan_to_num(a, nan=0.0, posinf=1.0, neginf=-1.0)
    a = np.clip(a, -1.0, 1.0)
    pcm = (a * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sampling_rate)
        w.writeframes(pcm.tobytes())


def _save_image(image) -> str:
    from PIL import Image

    path = ARTIFACT_DIR / f"image_{int(time.time() * 1000)}.png"
    # PNG can't store CMYK / float (F) / some int modes. Normalize so saving a
    # depth map / segmentation mask / odd-mode image never crashes.
    mode = getattr(image, "mode", "RGB")
    if mode not in ("RGB", "RGBA", "L", "LA", "P", "I", "1"):
        try:
            import numpy as np

            if mode == "F":
                # float map → normalize to 8-bit grayscale for a viewable PNG
                a = np.asarray(image, dtype=np.float32)
                rng = float(a.max() - a.min())
                a = ((a - a.min()) / rng * 255.0) if rng > 0 else np.zeros_like(a)
                image = Image.fromarray(a.astype("uint8"), mode="L")
            else:
                image = image.convert("RGB")
        except Exception:
            image = image.convert("RGB")
    image.save(str(path))
    return str(path)
