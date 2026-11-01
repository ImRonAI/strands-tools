"""Native multimodal I/O for diffusion — images / video / audio / actions out.

Inputs: file paths, URLs, base64 data URIs, PIL images, numpy arrays, video paths.
Outputs: diffusers pipeline results serialized to JSON-safe form, with binary
artifacts (generated images, videos, audio, and robot ACTION chunks) written to
disk and referenced by path.

The headline feature for Physical-AI / world-foundation models: a Cosmos-style
pipeline returns a `Cosmos3OmniPipelineOutput(video=..., sound=..., action=...)`.
We serialize the video to .mp4, the sound to .wav, and the **action** chunk to a
.json (the model-normalized action-space tensor) — so an agent gets back a path
to a playable world AND a usable robot action vector in one call.
"""

from __future__ import annotations

import base64
import io as _io
import itertools as _itertools
import os
import tempfile
import threading as _threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_DIR = Path(
    os.getenv("STRANDS_DIFFUSERS_ARTIFACTS", tempfile.gettempdir())
) / "strands_diffusers"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

_STAMP_LOCK = _threading.Lock()
_STAMP_COUNTER = _itertools.count()


def _stamp() -> str:
    """Monotonic, collision-free artifact stamp: <ms>_<counter>. Millisecond
    timestamps alone collide in tight loops / batched generation (num_images>1),
    silently overwriting artifacts — so append an atomic process-wide counter."""
    with _STAMP_LOCK:
        n = next(_STAMP_COUNTER)
    return f"{int(time.time() * 1000)}_{n}"


# ───────────────────────── INPUT COERCION ─────────────────────────

def coerce_input(value: Any) -> Any:
    """Coerce an input spec into something a diffusers pipeline accepts.

    - "data:..."         → PIL Image / bytes
    - "*.png|jpg|..."    → PIL Image (loaded via diffusers.utils.load_image)
    - "*.mp4|mov|..."    → list[PIL] frames (via diffusers.utils.load_video)
    - "http(s)://..."    → load_image / load_video by extension
    - lists / dicts      → coerced recursively
    - everything else     → passed through (text prompt, ints, etc.)
    """
    if isinstance(value, str):
        if value.startswith("data:"):
            return _decode_data_uri(value)
        if _looks_like(value, (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")):
            img = _load_image(value)
            if img is not None:
                return img
        if _looks_like(value, (".mp4", ".mov", ".avi", ".mkv", ".webm")):
            vid = _load_video(value)
            if vid is not None:
                return vid
        return value  # text prompt / repo id / path we don't special-case
    if isinstance(value, list):
        return [coerce_input(v) for v in value]
    if isinstance(value, dict):
        return {k: coerce_input(v) for k, v in value.items()}
    return value


def _looks_like(path: str, exts) -> bool:
    # Match the extension case-insensitively, but check existence on the ORIGINAL
    # path — lowercasing the whole path breaks case-sensitive filesystems
    # (e.g. a HF snapshot dir like ".../Cosmos3-Nano/...").
    is_url = path.startswith("http://") or path.startswith("https://")
    has_ext = path.split("?")[0].lower().endswith(tuple(exts))
    return has_ext and (is_url or os.path.exists(path))


def _load_image(spec: str):
    try:
        from diffusers.utils import load_image
        return load_image(spec)
    except Exception:
        try:
            from PIL import Image
            return Image.open(spec).convert("RGB")
        except Exception:
            return None


def _load_video(spec: str):
    try:
        from diffusers.utils import load_video
        return load_video(spec)
    except Exception:
        return None


def _decode_data_uri(uri: str) -> Any:
    header, _, b64 = uri.partition(",")
    raw = base64.b64decode(b64)
    mime = header.split(";")[0].removeprefix("data:")
    if mime.startswith("image/"):
        from PIL import Image
        return Image.open(_io.BytesIO(raw)).convert("RGB")
    return raw


def load_array(spec: Any):
    """Load a numpy array from list, .npy path, or pass through ndarray.

    Useful for raw robot action vectors fed to forward-dynamics WFM runs.
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

def serialize_output(result: Any, save_artifacts: bool = True,
                     fps: float = 24.0, audio_sample_rate: int = 16000) -> Dict[str, Any]:
    """Convert any diffusers pipeline/model output into a JSON-safe dict.

    Video → .mp4, images → .png, audio → .wav, action chunks → .json — all under
    ARTIFACT_DIR and referenced by path so the agent can hand them downstream.
    """
    artifacts: List[str] = []
    ctx = {"fps": fps, "audio_sample_rate": audio_sample_rate}
    payload = _serialize(result, artifacts, save_artifacts, ctx)
    payload = _ensure_json_safe(payload)
    out: Dict[str, Any] = {"result": payload}
    if artifacts:
        out["artifacts"] = artifacts
    return out


def _serialize(obj: Any, artifacts: List[str], save: bool, ctx: Dict[str, Any],
               depth: int = 0, field: str = "") -> Any:
    if depth > 6:
        return str(obj)[:200]

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # diffusers pipeline outputs are dataclass-like (ImagePipelineOutput,
    # Cosmos3OmniPipelineOutput, ...) — handle their known fields explicitly so
    # video/sound/action each go to the right serializer.
    handled = _maybe_pipeline_output(obj, artifacts, save, ctx, depth)
    if handled is not None:
        return handled

    # 3D mesh (ShapE / mesh-output pipelines) → .ply/.obj
    mesh = _maybe_mesh(obj, artifacts, save)
    if mesh is not None:
        return mesh

    # PIL image
    pil = _maybe_pil(obj, artifacts, save)
    if pil is not None:
        return pil

    # numpy / torch arrays
    arr = _maybe_array(obj, artifacts, save, ctx, field)
    if arr is not None:
        return arr

    if isinstance(obj, dict):
        return {str(k): _serialize(v, artifacts, save, ctx, depth + 1, str(k))
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        # A list of PIL images is a video/frame-set → save as mp4 if many.
        vid = _maybe_video_framelist(obj, artifacts, save, ctx, field)
        if vid is not None:
            return vid
        return [_serialize(v, artifacts, save, ctx, depth + 1, field) for v in obj[:200]]
    if isinstance(obj, (set, frozenset)):
        return [_serialize(v, artifacts, save, ctx, depth + 1) for v in list(obj)[:200]]

    if hasattr(obj, "to_dict"):
        try:
            return _serialize(obj.to_dict(), artifacts, save, ctx, depth + 1)
        except Exception:
            pass
    if hasattr(obj, "keys"):
        try:
            return {str(k): _serialize(obj[k], artifacts, save, ctx, depth + 1, str(k))
                    for k in obj.keys()}
        except Exception:
            pass

    return str(obj)[:50000]


def _maybe_pipeline_output(obj, artifacts, save, ctx, depth):
    """Serialize a diffusers *PipelineOutput dataclass field-by-field."""
    cls = type(obj).__name__
    if not cls.endswith("PipelineOutput") and not cls.endswith("Output"):
        return None
    # A mesh decoder output (verts/faces) is an *Output too — route to mesh export
    # before generic field-by-field serialization (else 3D data is lost).
    if hasattr(obj, "verts") and hasattr(obj, "faces"):
        return _maybe_mesh(obj, artifacts, save)
    # Gather public fields (dataclass-style or attrs).
    fields = {}
    if hasattr(obj, "__dataclass_fields__"):
        names = list(obj.__dataclass_fields__.keys())
    else:
        names = [n for n in dir(obj) if not n.startswith("_")
                 and not callable(getattr(obj, n, None))]
    for name in names:
        try:
            val = getattr(obj, name)
        except Exception:
            continue
        if val is None:
            fields[name] = None
            continue
        if name in ("video", "videos", "frames"):
            fields[name] = _serialize_video(val, artifacts, save, ctx)
        elif name in ("sound", "audio", "audios"):
            fields[name] = _serialize_audio(val, artifacts, save, ctx)
        elif name in ("action", "actions"):
            fields[name] = _serialize_action(val, artifacts, save)
        elif name in ("images", "image"):
            fields[name] = _serialize(val, artifacts, save, ctx, depth + 1, name)
        else:
            fields[name] = _serialize(val, artifacts, save, ctx, depth + 1, name)
    fields["__type__"] = cls
    return fields


def _serialize_video(val, artifacts, save, ctx):
    """Save video output (list[PIL] | ndarray[T,H,W,C] | tensor) → .mp4."""
    frames = _to_frame_list(val)
    if frames is None:
        return _serialize(val, artifacts, save, ctx, 5, "video")
    if not save:
        return {"type": "video", "num_frames": len(frames)}
    path = _save_video(frames, ctx.get("fps", 24.0))
    if path:
        artifacts.append(path)
        return {"type": "video", "path": path, "num_frames": len(frames)}
    return {"type": "video", "num_frames": len(frames)}


def _serialize_audio(val, artifacts, save, ctx):
    import numpy as np
    a = _tensor_to_numpy(val)
    if a is None:
        return _serialize(val, artifacts, save, ctx, 5, "audio")
    a = np.asarray(a)
    # Drop singleton batch dims but PRESERVE real channels (stereo). Audio has a
    # long time-axis and a small channel-axis (1/2/~8). We orient to channels-last
    # [N, C] for soundfile, keeping stereo intact instead of down-mixing to mono.
    while a.ndim > 2:
        # squeeze the first size-1 axis (typically batch)
        sq = next((i for i, s in enumerate(a.shape) if s == 1), None)
        if sq is None:
            break
        a = np.squeeze(a, axis=sq)
    channels = 1
    if a.ndim == 2:
        ch_axis = int(np.argmin(a.shape))      # shorter axis = channels
        if a.shape[ch_axis] == 1:
            a = a.reshape(-1)                  # genuinely mono
        else:
            if ch_axis == 0:                  # [C, N] -> [N, C]
                a = a.T
            channels = a.shape[1]
    if not save:
        return {"type": "audio", "samples": int(a.shape[0]), "channels": channels}
    path = _save_wav(a, int(ctx.get("audio_sample_rate", 16000)))
    artifacts.append(path)
    return {"type": "audio", "path": path, "samples": int(a.shape[0]),
            "channels": channels,
            "sampling_rate": int(ctx.get("audio_sample_rate", 16000))}


def _serialize_action(val, artifacts, save):
    """Serialize a robot ACTION chunk — the WFM payload agents care about.

    Cosmos returns action as list[torch.Tensor]; each tensor is a normalized
    action chunk [T, action_dim]. We emit full nested lists (small) + write a
    .json artifact so the agent can feed it straight to a robot controller.
    """
    import numpy as np

    def _one(t):
        a = _tensor_to_numpy(t)
        return np.asarray(a).tolist() if a is not None else None

    if isinstance(val, (list, tuple)):
        data = [_one(t) for t in val]
    else:
        data = _one(val)

    result = {"type": "action", "data": data}
    if isinstance(val, (list, tuple)) and val:
        first = _tensor_to_numpy(val[0])
        if first is not None:
            result["chunk_shape"] = list(np.asarray(first).shape)
            result["num_chunks"] = len(val)
    if save and data is not None:
        import json
        path = ARTIFACT_DIR / f"action_{_stamp()}.json"
        with open(path, "w") as f:
            json.dump(data, f)
        artifacts.append(str(path))
        result["path"] = str(path)
    return result


def _maybe_mesh(obj, artifacts, save):
    """A 3D mesh (ShapE MeshDecoderOutput / trimesh-like) → .ply (+ .obj).

    diffusers mesh outputs expose `verts` and `faces`; diffusers.utils ships
    export_to_ply / export_to_obj. Without this path a mesh would serialize to an
    opaque repr string (silent 3D data loss).
    """
    # NB: diffusers BaseOutput subclasses OrderedDict, so DON'T exclude dict here —
    # detect by the verts/faces attributes instead.
    if obj is None or isinstance(obj, (str, int, float, bool, list, tuple)):
        return None
    if not (hasattr(obj, "verts") and hasattr(obj, "faces")):
        return None
    nv = _safe_len(getattr(obj, "verts", None))
    nf = _safe_len(getattr(obj, "faces", None))
    info = {"type": "mesh", "num_verts": nv, "num_faces": nf}
    if save:
        path = _save_mesh(obj)
        if path:
            artifacts.append(path)
            info["path"] = path
    return info


def _safe_len(x):
    try:
        if x is None:
            return None
        if hasattr(x, "shape"):
            return int(x.shape[0])
        return len(x)
    except Exception:
        return None


def _save_mesh(mesh) -> Optional[str]:
    """Write a mesh → .ply via diffusers.utils.export_to_ply (obj fallback)."""
    ts = _stamp()
    try:
        from diffusers.utils import export_to_ply
        path = ARTIFACT_DIR / f"mesh_{ts}.ply"
        export_to_ply(mesh, str(path))
        return str(path)
    except Exception:
        pass
    try:
        from diffusers.utils import export_to_obj
        path = ARTIFACT_DIR / f"mesh_{ts}.obj"
        export_to_obj(mesh, str(path))
        return str(path)
    except Exception:
        pass
    # last resort: dump raw verts/faces as npz so data isn't lost
    try:
        import numpy as np
        path = ARTIFACT_DIR / f"mesh_{ts}.npz"
        v = _tensor_to_numpy(mesh.verts)
        fa = _tensor_to_numpy(mesh.faces)
        np.savez(str(path), verts=v, faces=fa)
        return str(path)
    except Exception:
        return None


def _maybe_pil(obj, artifacts, save):
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
    return None


def _maybe_video_framelist(obj, artifacts, save, ctx, field):
    """A long list of PIL frames (not in a known field) → treat as video."""
    try:
        from PIL import Image
    except ImportError:
        return None
    if (isinstance(obj, list) and len(obj) >= 8
            and all(isinstance(x, Image.Image) for x in obj[:8])):
        return _serialize_video(obj, artifacts, save, ctx)
    return None


def _maybe_array(obj, artifacts, save, ctx, field):
    a = _tensor_to_numpy(obj)
    if a is None:
        return None
    import numpy as np
    arr = np.asarray(a)
    # A 4D/5D array that looks like video frames → mp4
    if save and arr.ndim in (4, 5) and field in ("video", "videos", "frames"):
        return _serialize_video(arr, artifacts, save, ctx)
    if arr.size <= 256:
        return arr.tolist()
    return {
        "type": "ndarray",
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "preview": arr.flatten()[:16].tolist(),
    }


def _tensor_to_numpy(obj):
    try:
        import torch
        if isinstance(obj, torch.Tensor):
            obj = obj.detach().cpu()
            if obj.dtype in (torch.bfloat16, torch.float16):
                obj = obj.to(torch.float32)
            return obj.numpy()
    except ImportError:
        pass
    try:
        import numpy as np
        if isinstance(obj, (np.ndarray, np.generic)):
            return np.asarray(obj)
    except ImportError:
        pass
    return None


def _to_frame_list(val):
    """Normalize a video output to a list of HxWxC uint8 numpy frames."""
    import numpy as np

    try:
        from PIL import Image
    except ImportError:
        Image = None

    if isinstance(val, (list, tuple)):
        if Image and val and all(isinstance(x, Image.Image) for x in val):
            return [np.asarray(x.convert("RGB")) for x in val]
        # list of per-frame numpy arrays (a common pipeline return shape) → stack
        if val and all(isinstance(x, np.ndarray) for x in val):
            return _to_frame_list(np.stack(val))
        # list of per-frame torch tensors → stack via numpy
        a0 = _tensor_to_numpy(val[0]) if val else None
        if a0 is not None and not isinstance(val[0], np.ndarray):
            return _to_frame_list(np.stack([_tensor_to_numpy(x) for x in val]))
        # nested (batched) list of frames → take first sample
        if val and isinstance(val[0], (list, tuple)):
            return _to_frame_list(val[0])
    a = _tensor_to_numpy(val)
    if a is None:
        return None
    a = np.asarray(a)
    if a.ndim == 5:       # [B,T,H,W,C] or [B,T,C,H,W]
        a = a[0]
    if a.ndim == 4:
        # detect channel position
        if a.shape[1] in (1, 3, 4) and a.shape[-1] not in (1, 3, 4):
            a = np.transpose(a, (0, 2, 3, 1))  # [T,C,H,W] → [T,H,W,C]
        if a.dtype != np.uint8:
            a = np.clip(a, 0, 1) if a.max() <= 1.0 else np.clip(a, 0, 255) / 255.0
            a = (a * 255).astype(np.uint8) if a.max() <= 1.0 + 1e-6 else a.astype(np.uint8)
        return [a[i] for i in range(a.shape[0])]
    return None


# ───────────────────────── artifact writers ─────────────────────────

def _save_image(image) -> str:
    path = ARTIFACT_DIR / f"image_{_stamp()}.png"
    image.save(str(path))
    return str(path)


def _save_video(frames, fps: float) -> Optional[str]:
    """Write frames → mp4. Prefer diffusers.export_to_video, fall back to imageio."""
    path = ARTIFACT_DIR / f"video_{_stamp()}.mp4"
    try:
        from PIL import Image
        pil_frames = [Image.fromarray(f) for f in frames]
        from diffusers.utils import export_to_video
        export_to_video(pil_frames, str(path), fps=int(fps))
        return str(path)
    except Exception:
        pass
    try:
        import imageio.v3 as iio
        iio.imwrite(str(path), frames, fps=int(fps), codec="libx264")
        return str(path)
    except Exception:
        pass
    # last resort: dump frames as a gif (always available via PIL)
    try:
        from PIL import Image
        gif = ARTIFACT_DIR / f"video_{_stamp()}.gif"
        imgs = [Image.fromarray(f) for f in frames]
        imgs[0].save(str(gif), save_all=True, append_images=imgs[1:],
                     duration=int(1000 / max(fps, 1)), loop=0)
        return str(gif)
    except Exception:
        return None


def _save_wav(audio, sampling_rate: int) -> str:
    import numpy as np

    a = np.asarray(audio, dtype=np.float32)
    # squeeze only singleton dims; keep a real stereo channel axis as [N, C]
    while a.ndim > 2:
        sq = next((i for i, s in enumerate(a.shape) if s == 1), None)
        if sq is None:
            break
        a = np.squeeze(a, axis=sq)
    if a.ndim == 2:
        ch_axis = int(np.argmin(a.shape))
        if a.shape[ch_axis] == 1:
            a = a.reshape(-1)
        elif ch_axis == 0:
            a = a.T
    nch = 1 if a.ndim == 1 else a.shape[1]
    path = ARTIFACT_DIR / f"audio_{_stamp()}.wav"
    try:
        import soundfile as sf
        sf.write(str(path), a, int(sampling_rate))
        return str(path)
    except ImportError:
        pass
    import wave
    a = np.clip(a, -1.0, 1.0)
    pcm = (a * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(2)
        w.setframerate(int(sampling_rate))
        w.writeframes(pcm.tobytes())
    return str(path)


def _ensure_json_safe(obj: Any) -> Any:
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
