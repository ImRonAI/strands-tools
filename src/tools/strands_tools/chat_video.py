# pyright: strict
"""Gemini Interactions API & TwelveLabs multimodal video chat tool for Strands Agent.

Provides native multimodal video understanding and Q&A across mobile phones (iOS/Android),
tablets (iPadOS/Android), and laptops/desktops (macOS/Windows/Linux) using the Google
Gemini Interactions API (`client.interactions.create` in `google-genai>=2.0.0`), with an
optional lazy fallback to TwelveLabs Pegasus when `index_id` / TwelveLabs `video_id` is used.

Key Features:
1. Universal Device & Source Support:
   - Local video files (`video_path`): `.mp4`, `.mov` (iOS/iPadOS/macOS QuickTime), `.webm`
     (Android/Chrome MediaRecorder), `.3gp`/`.3gpp` (mobile), `.m4v`, `.mpeg`, `.mpg`, `.avi`,
     `.wmv`, `.flv`, `.mkv`
   - Remote & Cloud URLs (`video_url`): YouTube URLs (`youtube.com/watch?v=...`, `youtu.be/...`,
     `youtube.com/shorts/...`), HTTPS/pre-signed URLs, `gs://` Cloud Storage URIs, and Gemini
     Files API URIs (`files/...`)
   - Camera & Screen Recording Captures (`video_base64`): raw base64 or `data:video/...;base64,...`
     payloads streamed from mobile/tablet/web clients
   - Multi-turn Video Conversations (`previous_interaction_id`): follow-up questions on a video
     without re-uploading

2. Native Gemini Interactions API Video Controls:
   - `processing`: `"static"` (1 FPS frame + audio extraction, or custom `start_offset`,
     `end_offset`, and `fps` via `StaticMediaProcessingParam`) or `"agentic"` (dynamic timeline
     navigation for long-form videos using up to 88% fewer tokens)
   - `resolution`: `"low"` | `"medium"` | `"high"` | `"ultra_high"` token budget per frame
   - Automatic inline base64 (`< 20 MB` static) vs. Gemini Files API upload (`>= 20 MB` or
     `"agentic"`) with SHA-256 caching in `VIDEO_CACHE`
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import logging
import mimetypes
import os
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, cast

import google.genai as genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from strands.types.tools import ToolResult, ToolSpec, ToolUse

logger = logging.getLogger(__name__)

# Maximum inline video byte size (20 MB) before switching to Gemini Files API upload
_INLINE_VIDEO_MAX_BYTES: int = 20 * 1024 * 1024

# Default Gemini Interactions model failover chain for video understanding
_DEFAULT_GEMINI_VIDEO_MODELS: tuple[str, ...] = (
    "gemini-4-argon",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
)

# Supported Gemini Interactions API VideoContentMimeType values
# Verified against google.genai._gaos.types.interactions.videocontent.VideoContentMimeType
_EXTENSION_TO_VIDEO_MIME: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mkv": "video/mp4",
    ".mov": "video/mov",
    ".qt": "video/mov",
    ".webm": "video/webm",
    ".3gp": "video/3gpp",
    ".3gpp": "video/3gpp",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpg",
    ".avi": "video/avi",
    ".flv": "video/x-flv",
    ".wmv": "video/wmv",
}

_MIME_ALIASES: dict[str, str] = {
    "video/quicktime": "video/mov",
    "video/x-m4v": "video/mp4",
    "video/x-matroska": "video/mp4",
    "video/x-msvideo": "video/avi",
    "video/x-ms-wmv": "video/wmv",
    "video/3gp": "video/3gpp",
}

_VALID_RESOLUTIONS: frozenset[str] = frozenset({"low", "medium", "high", "ultra_high"})

_CAPACITY_KEYWORDS: tuple[str, ...] = (
    "resource_exhausted",
    "rate_limit",
    "ratelimit",
    "quota",
    "too many requests",
    "too_many_requests",
    "unavailable",
    "overloaded",
    "capacity",
    "bandwidth",
    "server_overloaded",
    "timed out",
    "timeout",
)

TOOL_SPEC: ToolSpec = {
    "name": "chat_video",
    "description": """Chat with and analyze video content from mobile phones, tablets, laptops, or URLs using the Google Gemini Interactions API (with optional TwelveLabs Pegasus fallback).

Key Features:
1. Multimodal Video & Audio Understanding:
   - Natural language Q&A, summarization, timestamped event detection (`MM:SS`), OCR, action recognition, and audio/dialogue transcription
   - Works across mobile/tablet camera uploads (`.mov`, `.mp4`, `.3gp`, `.webm`), desktop screen recordings, base64/data-URL captures, YouTube URLs, Cloud Storage (`gs://`), HTTPS URLs, and Gemini Files API (`files/...`)
   - Supports multi-turn follow-up questions via `previous_interaction_id`

2. Native Gemini Video Processing Controls:
   - `processing`: `"static"` (default 1 FPS sampling, customizable with `start_offset`, `end_offset`, and `fps`) or `"agentic"` (dynamic timeline inspection for long videos)
   - `resolution`: `"low"`, `"medium"`, `"high"`, or `"ultra_high"` frame token budget
   - `engine_options`: `["visual", "audio"]` (default both, or focus on visual-only / audio-only)

Usage Examples:
1. Local video file (mobile `.mov`, `.mp4`, `.webm`, etc.):
   chat_video(prompt="Summarize key events with MM:SS timestamps", video_path="/path/to/video.mp4")

2. YouTube or remote video URL:
   chat_video(prompt="What are the main arguments presented?", video_url="https://www.youtube.com/watch?v=9hE5-98ZeCg")

3. Long-form video with agentic processing or custom clipping:
   chat_video(
       prompt="Find where the speaker demos the mobile app",
       video_path="/path/to/lecture.mov",
       processing="agentic",
       resolution="high"
   )

4. Clipped segment with custom FPS:
   chat_video(
       prompt="Describe the rapid motion in this clip",
       video_path="/path/to/sports.mp4",
       start_offset="10s",
       end_offset="25s",
       fps=2.0
   )

5. Multi-turn follow-up question:
   chat_video(prompt="What did they say right after that?", previous_interaction_id="interaction_abc123")""",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Natural language question or instruction about the video",
                },
                "video_path": {
                    "type": "string",
                    "description": (
                        "Local file path to a video (.mp4, .mov, .webm, .3gp, .m4v, .mpeg, .mpg, .avi, .wmv, .flv, .mkv)"
                    ),
                },
                "video_url": {
                    "type": "string",
                    "description": (
                        "YouTube URL (youtube.com/watch?v=..., youtu.be/..., youtube.com/shorts/...), "
                        "HTTPS URL, gs:// URI, or Gemini Files API URI"
                    ),
                },
                "video_base64": {
                    "type": "string",
                    "description": (
                        "Base64-encoded video bytes or data URL (data:video/mp4;base64,...) from a mobile, "
                        "tablet, or laptop camera/screen capture"
                    ),
                },
                "video_id": {
                    "type": "string",
                    "description": (
                        "Gemini Files API resource name (e.g. 'files/abc123') or an indexed TwelveLabs video ID"
                    ),
                },
                "mime_type": {
                    "type": "string",
                    "description": (
                        "Optional explicit video MIME type (e.g. 'video/mp4', 'video/mov', 'video/webm', 'video/3gpp'). "
                        "Automatically inferred from file extension or data URL when omitted."
                    ),
                },
                "processing": {
                    "type": "string",
                    "enum": ["static", "agentic"],
                    "description": (
                        "Gemini video processing mode: 'static' (default frame + audio sampling, supports "
                        "start_offset/end_offset/fps) or 'agentic' (dynamic timeline navigation for long videos)"
                    ),
                },
                "resolution": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "ultra_high"],
                    "description": "Per-frame token resolution ('low', 'medium', 'high', or 'ultra_high')",
                },
                "start_offset": {
                    "type": "string",
                    "description": "Optional clip start offset in seconds with 's' suffix (e.g. '10s' or '12.5s')",
                },
                "end_offset": {
                    "type": "string",
                    "description": "Optional clip end offset in seconds with 's' suffix (e.g. '60s')",
                },
                "fps": {
                    "type": "number",
                    "description": "Optional custom frame-rate sampling density in frames per second (e.g. 0.5, 1.0, 2.0)",
                    "minimum": 0.01,
                    "maximum": 24.0,
                },
                "previous_interaction_id": {
                    "type": "string",
                    "description": "Optional Gemini interaction ID from a previous turn for multi-turn video chat",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Optional Gemini model ID (defaults to 'gemini-3.8-flash' with automatic failover to "
                        "'gemini-4-argon' and 'gemini-3.5-flash-lite')"
                    ),
                },
                "system_instruction": {
                    "type": "string",
                    "description": "Optional system instruction to guide video analysis format and persona",
                },
                "temperature": {
                    "type": "number",
                    "description": "Controls randomness in responses (0.0-2.0). Default: 0.7",
                    "minimum": 0.0,
                    "maximum": 2.0,
                },
                "max_output_tokens": {
                    "type": "integer",
                    "description": "Optional maximum number of output tokens to generate",
                    "minimum": 1,
                },
                "engine_options": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["visual", "audio"],
                    },
                    "description": "Analysis modes to use. Default: ['visual', 'audio']",
                },
                "index_id": {
                    "type": "string",
                    "description": (
                        "Optional TwelveLabs index ID when using TwelveLabs Pegasus fallback "
                        "(or set TWELVELABS_PEGASUS_INDEX_ID env var)"
                    ),
                },
            },
            "required": ["prompt"],
        }
    },
}

# Cache for uploaded videos (SHA-256 -> Gemini file URI or TwelveLabs video_id) to avoid re-uploading
VIDEO_CACHE: Dict[str, str] = {}
_VIDEO_MIME_CACHE: Dict[str, str] = {}


def get_video_hash(video_path: str) -> str:
    """Calculate SHA256 hash of a video file.

    Args:
        video_path: Path to the video file.

    Returns:
        Hexadecimal hash string.
    """
    sha256_hash = hashlib.sha256()
    with open(video_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _normalize_mime_type(mime_type: str | None, path_or_url: str | None = None) -> str:
    """Normalize a video MIME type to a valid Gemini `VideoContentMimeType` string."""
    if mime_type:
        cleaned = mime_type.strip().lower().split(";")[0].strip()
        if cleaned in _MIME_ALIASES:
            return _MIME_ALIASES[cleaned]
        if cleaned.startswith("video/"):
            return cleaned

    if path_or_url:
        clean_target = path_or_url.split("?")[0].split("#")[0]
        ext = Path(clean_target).suffix.lower()
        if ext in _EXTENSION_TO_VIDEO_MIME:
            return _EXTENSION_TO_VIDEO_MIME[ext]
        guessed, _ = mimetypes.guess_type(clean_target)
        if guessed:
            guessed_clean = guessed.lower()
            if guessed_clean in _MIME_ALIASES:
                return _MIME_ALIASES[guessed_clean]
            if guessed_clean.startswith("video/"):
                return guessed_clean

    return "video/mp4"


def _normalize_offset(offset: str | int | float | None) -> str | None:
    """Normalize a clip offset to a seconds string ending with `'s'` (e.g. `'10.5s'`)."""
    if offset is None:
        return None
    if isinstance(offset, (int, float)):
        return f"{offset}s"
    raw = str(offset).strip()
    if not raw:
        return None
    if raw.endswith("s"):
        return raw
    # Support MM:SS or HH:MM:SS timestamps by converting to seconds
    if ":" in raw:
        parts = raw.split(":")
        try:
            if len(parts) == 2:
                total_sec = float(parts[0]) * 60.0 + float(parts[1])
                return f"{total_sec:g}s"
            if len(parts) == 3:
                total_sec = float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
                return f"{total_sec:g}s"
        except ValueError:
            pass
    return f"{raw}s"


def _is_youtube_url(url: str) -> bool:
    """Return True if `url` points to YouTube."""
    lowered = url.lower()
    return any(
        host in lowered
        for host in (
            "youtube.com/watch",
            "youtu.be/",
            "youtube.com/shorts/",
            "youtube.com/embed/",
            "youtube.com/live/",
            "m.youtube.com/watch",
        )
    )


def _is_gemini_file_reference(value: str) -> bool:
    """Return True if `value` is a Gemini Files API resource name or URI."""
    stripped = value.strip()
    return stripped.startswith("files/") or "generativelanguage.googleapis.com/" in stripped


def _build_processing_param(
    processing: str | None,
    start_offset: str | None,
    end_offset: str | None,
    fps: float | None,
) -> Any:
    """Build the `VideoContentParam['processing']` value for the Gemini Interactions API."""
    mode = (processing or "").strip().lower()
    norm_start = _normalize_offset(start_offset)
    norm_end = _normalize_offset(end_offset)

    if mode == "agentic" and norm_start is None and norm_end is None and fps is None:
        return "agentic"

    if norm_start is not None or norm_end is not None or fps is not None:
        static_cfg: dict[str, Any] = {"type": "static"}
        if norm_start is not None:
            static_cfg["start_offset"] = norm_start
        if norm_end is not None:
            static_cfg["end_offset"] = norm_end
        if fps is not None:
            static_cfg["fps"] = float(fps)
        return static_cfg

    if mode == "static":
        return "static"

    return None


def _get_gemini_client() -> genai.Client:
    """Return a configured `google.genai.Client` using `GEMINI_API_KEY` or `GOOGLE_API_KEY`."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "Neither GEMINI_API_KEY nor GOOGLE_API_KEY environment variable is set. "
            "Please set GEMINI_API_KEY to use Gemini video understanding."
        )
    return genai.Client(
        api_key=api_key,
        http_options={
            "timeout": 30_000,
            "retry_options": {
                "attempts": 0,
            },
        },
    )


def _upload_and_wait_gemini_file(
    client: genai.Client,
    file_path: str,
    mime_type: str,
    cache_key: str | None = None,
) -> tuple[str, str]:
    """Upload a video file via the Gemini Files API and poll until its state is `ACTIVE`."""
    if cache_key and cache_key in VIDEO_CACHE:
        cached_uri = VIDEO_CACHE[cache_key]
        cached_mime = _VIDEO_MIME_CACHE.get(cache_key, mime_type)
        return cached_uri, cached_mime

    upload_config = genai_types.UploadFileConfig(
        mime_type=mime_type,
        display_name=Path(file_path).name,
    )
    uploaded = client.files.upload(file=file_path, config=upload_config)

    file_name = uploaded.name
    if file_name:
        deadline = time.monotonic() + 300.0
        while uploaded.state and uploaded.state.name == "PROCESSING":
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for Gemini File {file_name} to finish processing.")
            time.sleep(2.0)
            uploaded = client.files.get(name=file_name)

        if uploaded.state and uploaded.state.name == "FAILED":
            err_detail = getattr(uploaded, "error", None)
            raise RuntimeError(f"Gemini video file processing failed for {file_name}: {err_detail or 'FAILED'}")

    uri = uploaded.uri or uploaded.name
    if not uri:
        raise RuntimeError("Gemini Files API upload did not return a valid file URI.")

    resolved_mime = _normalize_mime_type(uploaded.mime_type or mime_type, file_path)
    if cache_key:
        VIDEO_CACHE[cache_key] = uri
        _VIDEO_MIME_CACHE[cache_key] = resolved_mime

    return uri, resolved_mime


def _resolve_gemini_video_part(
    client: genai.Client,
    *,
    video_path: str | None,
    video_url: str | None,
    video_base64: str | None,
    video_id: str | None,
    mime_type: str | None,
    processing: str | None,
    resolution: str | None,
    start_offset: str | None,
    end_offset: str | None,
    fps: float | None,
) -> dict[str, Any] | None:
    """Construct a `VideoContentParam` dictionary from the provided video source and processing options."""
    proc_param = _build_processing_param(processing, start_offset, end_offset, fps)
    use_agentic = proc_param == "agentic"
    res_param = resolution if (resolution and resolution in _VALID_RESOLUTIONS) else None

    def _attach_options(part: dict[str, Any]) -> dict[str, Any]:
        if proc_param is not None:
            part["processing"] = proc_param
        if res_param is not None:
            part["resolution"] = res_param
        return part

    # 1. If video_url is actually a data:video/...;base64,... URL, treat it as video_base64
    if video_url and video_url.strip().startswith("data:"):
        video_base64 = video_url.strip()
        video_url = None

    # 2. Local file path (mobile/tablet/laptop video file)
    if video_path:
        expanded_path = os.path.expanduser(video_path.strip())
        if not os.path.exists(expanded_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        resolved_mime = _normalize_mime_type(mime_type, expanded_path)
        file_size = os.path.getsize(expanded_path)
        video_hash = get_video_hash(expanded_path)

        # Reuse cached Gemini file URI if already uploaded
        if video_hash in VIDEO_CACHE and _is_gemini_file_reference(VIDEO_CACHE[video_hash]):
            return _attach_options(
                {
                    "type": "video",
                    "uri": VIDEO_CACHE[video_hash],
                    "mime_type": _VIDEO_MIME_CACHE.get(video_hash, resolved_mime),
                }
            )

        # Upload via Files API if > 20 MB or agentic processing is requested
        if file_size > _INLINE_VIDEO_MAX_BYTES or use_agentic:
            uri, uploaded_mime = _upload_and_wait_gemini_file(
                client,
                expanded_path,
                resolved_mime,
                cache_key=video_hash,
            )
            return _attach_options(
                {
                    "type": "video",
                    "uri": uri,
                    "mime_type": uploaded_mime,
                }
            )

        # Inline base64 for smaller videos (<= 20 MB)
        with open(expanded_path, "rb") as f:
            raw_bytes = f.read()
        return _attach_options(
            {
                "type": "video",
                "data": base64.b64encode(raw_bytes).decode("ascii"),
                "mime_type": resolved_mime,
            }
        )

    # 3. Base64 or data URL payload (e.g. from mobile/tablet/web camera or screen capture)
    if video_base64:
        raw_b64 = video_base64.strip()
        inferred_mime = mime_type
        if raw_b64.startswith("data:"):
            header, _, payload = raw_b64.partition(",")
            raw_b64 = payload.strip()
            header_mime = header[5:].split(";")[0].strip()
            if header_mime and not inferred_mime:
                inferred_mime = header_mime

        resolved_mime = _normalize_mime_type(inferred_mime)
        decoded_bytes = base64.b64decode(raw_b64)
        payload_hash = hashlib.sha256(decoded_bytes).hexdigest()

        if payload_hash in VIDEO_CACHE and _is_gemini_file_reference(VIDEO_CACHE[payload_hash]):
            return _attach_options(
                {
                    "type": "video",
                    "uri": VIDEO_CACHE[payload_hash],
                    "mime_type": _VIDEO_MIME_CACHE.get(payload_hash, resolved_mime),
                }
            )

        if len(decoded_bytes) > _INLINE_VIDEO_MAX_BYTES or use_agentic:
            ext = ".mp4"
            for candidate_ext, candidate_mime in _EXTENSION_TO_VIDEO_MIME.items():
                if candidate_mime == resolved_mime:
                    ext = candidate_ext
                    break
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(decoded_bytes)
                tmp_path = tmp_file.name
            try:
                uri, uploaded_mime = _upload_and_wait_gemini_file(
                    client,
                    tmp_path,
                    resolved_mime,
                    cache_key=payload_hash,
                )
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return _attach_options(
                {
                    "type": "video",
                    "uri": uri,
                    "mime_type": uploaded_mime,
                }
            )

        return _attach_options(
            {
                "type": "video",
                "data": base64.b64encode(decoded_bytes).decode("ascii"),
                "mime_type": resolved_mime,
            }
        )

    # 4. URL or URI (YouTube, gs://, https://, or files/...)
    if video_url:
        cleaned_url = video_url.strip()
        if _is_youtube_url(cleaned_url):
            yt_part: dict[str, Any] = {"type": "video", "uri": cleaned_url}
            if mime_type:
                yt_part["mime_type"] = _normalize_mime_type(mime_type)
            return _attach_options(yt_part)

        if cleaned_url.startswith("files/"):
            file_info = client.files.get(name=cleaned_url)
            resolved_uri = file_info.uri or cleaned_url
            resolved_mime = _normalize_mime_type(mime_type or file_info.mime_type, cleaned_url)
            return _attach_options(
                {
                    "type": "video",
                    "uri": resolved_uri,
                    "mime_type": resolved_mime,
                }
            )

        resolved_mime = _normalize_mime_type(mime_type, cleaned_url)
        return _attach_options(
            {
                "type": "video",
                "uri": cleaned_url,
                "mime_type": resolved_mime,
            }
        )

    # 5. Gemini Files API ID passed via video_id
    if video_id and _is_gemini_file_reference(video_id):
        cleaned_id = video_id.strip()
        if cleaned_id.startswith("files/"):
            file_info = client.files.get(name=cleaned_id)
            resolved_uri = file_info.uri or cleaned_id
            resolved_mime = _normalize_mime_type(mime_type or file_info.mime_type, cleaned_id)
        else:
            resolved_uri = cleaned_id
            resolved_mime = _normalize_mime_type(mime_type, cleaned_id)
        return _attach_options(
            {
                "type": "video",
                "uri": resolved_uri,
                "mime_type": resolved_mime,
            }
        )

    return None


def _is_retryable_capacity_error(exc: Exception) -> bool:
    """Return True if an exception indicates a model capacity/rate-limit error eligible for failover."""
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if code in (429, 503):
            return True
    msg = str(exc).lower()
    return any(keyword in msg for keyword in _CAPACITY_KEYWORDS)


def upload_and_index_video(video_path: str, index_id: str, api_key: str) -> str:
    """Upload a video file to TwelveLabs and wait for indexing (lazy-imported fallback).

    Args:
        video_path: Path to the video file.
        index_id: TwelveLabs index ID.
        api_key: TwelveLabs API key.

    Returns:
        `video_id` of the uploaded video.

    Raises:
        FileNotFoundError: If video file doesn't exist.
        RuntimeError: If video indexing fails or `twelvelabs` is not installed.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    video_hash = get_video_hash(video_path)
    if video_hash in VIDEO_CACHE and not _is_gemini_file_reference(VIDEO_CACHE[video_hash]):
        return VIDEO_CACHE[video_hash]

    try:
        twelvelabs_mod = importlib.import_module("twelvelabs")
        twelvelabs_cls = getattr(twelvelabs_mod, "TwelveLabs")
    except ImportError as exc:
        raise RuntimeError(
            "The 'twelvelabs' package is required for TwelveLabs index/video_id workflows. "
            "Install it with `pip install twelvelabs` or use Gemini video inputs (video_path, video_url, video_base64)."
        ) from exc

    with twelvelabs_cls(api_key) as client:
        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()

        task = client.task.create(index_id=index_id, file=video_bytes)
        task.wait_for_done(sleep_interval=5)

        if task.status != "ready":
            raise RuntimeError(f"Video indexing failed with status: {task.status}")

        video_id = str(task.video_id)
        VIDEO_CACHE[video_hash] = video_id
        return video_id


def _chat_video_twelvelabs(
    *,
    tool_use_id: str,
    prompt: str,
    video_id: str | None,
    video_path: str | None,
    index_id: str | None,
    temperature: float,
    engine_options: Sequence[str],
    api_key: str,
) -> ToolResult:
    """Execute TwelveLabs Pegasus video analysis when a TwelveLabs `video_id` or `index_id` is used."""
    try:
        twelvelabs_mod = importlib.import_module("twelvelabs")
        twelvelabs_cls = getattr(twelvelabs_mod, "TwelveLabs")
    except ImportError as exc:
        raise RuntimeError(
            "The 'twelvelabs' package is not installed. Use Gemini video understanding "
            "(GEMINI_API_KEY + video_path/video_url/video_base64) or install `twelvelabs`."
        ) from exc

    upload_note = ""
    resolved_video_id = video_id
    if video_path and not resolved_video_id:
        eff_index_id = index_id or os.getenv("TWELVELABS_PEGASUS_INDEX_ID")
        if not eff_index_id:
            raise ValueError(
                "index_id is required for TwelveLabs video uploads. "
                "Provide it in the request or set TWELVELABS_PEGASUS_INDEX_ID environment variable."
            )
        resolved_video_id = upload_and_index_video(video_path, eff_index_id, api_key)
        upload_note = f"Video uploaded successfully. Video ID: {resolved_video_id}\n\n"

    with twelvelabs_cls(api_key) as client:
        response = client.analyze(
            video_id=resolved_video_id,
            prompt=prompt,
            temperature=temperature,
        )
        response_text = str(response.data) if hasattr(response, "data") else str(response)
        full_response = upload_note + response_text
        metadata_parts = [
            "\n\n---",
            f"Video ID: {resolved_video_id}",
            f"Temperature: {temperature}",
            f"Engine options: {', '.join(engine_options)}",
        ]
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": full_response + "\n".join(metadata_parts)}],
        }


def _apply_engine_options_to_prompt(prompt: str, engine_options: Sequence[str]) -> str:
    """Augment the user prompt when the caller restricts analysis to visual-only or audio-only."""
    opts = {opt.lower().strip() for opt in engine_options if opt.strip()}
    if opts == {"audio"}:
        return f"[Focus specifically on the audio, speech, dialogue, and sound effects in the video.]\n{prompt}"
    if opts == {"visual"}:
        return f"[Focus specifically on the visual scenes, actions, objects, and on-screen text in the video.]\n{prompt}"
    return prompt


def chat_video(tool: ToolUse, **kwargs: Any) -> ToolResult:
    """Chat with video content using the Google Gemini Interactions API (or TwelveLabs fallback).

    Supports local video files (`.mp4`, `.mov`, `.webm`, `.3gp`, etc.), YouTube/HTTPS/`gs://` URLs,
    base64/data-URL captures from mobile/tablet/laptop devices, Gemini Files API URIs (`files/...`),
    and multi-turn follow-ups via `previous_interaction_id`.

    Args:
        tool: Tool use dictionary containing `toolUseId` and `input` parameters.
        **kwargs: Additional keyword arguments passed by the framework.

    Returns:
        Strands `ToolResult` dictionary with `toolUseId`, `status`, and `content`.
    """
    del kwargs
    tool_use_id = str(tool.get("toolUseId", "tooluse_chat_video"))
    raw_input = tool.get("input")
    tool_input: Mapping[str, Any] = cast(Mapping[str, Any], raw_input) if isinstance(raw_input, Mapping) else {}

    try:
        prompt_raw = tool_input.get("prompt")
        if not isinstance(prompt_raw, str) or not prompt_raw.strip():
            raise ValueError("A non-empty 'prompt' string is required.")
        prompt = prompt_raw.strip()

        video_path = tool_input.get("video_path") if isinstance(tool_input.get("video_path"), str) else None
        video_url = tool_input.get("video_url") if isinstance(tool_input.get("video_url"), str) else None
        video_base64 = tool_input.get("video_base64") if isinstance(tool_input.get("video_base64"), str) else None
        video_id = tool_input.get("video_id") if isinstance(tool_input.get("video_id"), str) else None
        index_id = tool_input.get("index_id") if isinstance(tool_input.get("index_id"), str) else None
        mime_type = tool_input.get("mime_type") if isinstance(tool_input.get("mime_type"), str) else None
        processing = tool_input.get("processing") if isinstance(tool_input.get("processing"), str) else None
        resolution = tool_input.get("resolution") if isinstance(tool_input.get("resolution"), str) else None
        start_offset = (
            str(tool_input["start_offset"])
            if tool_input.get("start_offset") is not None
            else None
        )
        end_offset = (
            str(tool_input["end_offset"])
            if tool_input.get("end_offset") is not None
            else None
        )
        fps_raw = tool_input.get("fps")
        fps: float | None = float(fps_raw) if isinstance(fps_raw, (int, float)) else None

        previous_interaction_id = (
            tool_input.get("previous_interaction_id")
            if isinstance(tool_input.get("previous_interaction_id"), str)
            else None
        )
        requested_model = tool_input.get("model") if isinstance(tool_input.get("model"), str) else None
        system_instruction = (
            tool_input.get("system_instruction")
            if isinstance(tool_input.get("system_instruction"), str)
            else None
        )

        temp_raw = tool_input.get("temperature", 0.7)
        temperature: float = float(temp_raw) if isinstance(temp_raw, (int, float)) else 0.7

        max_tokens_raw = tool_input.get("max_output_tokens")
        max_output_tokens: int | None = int(max_tokens_raw) if isinstance(max_tokens_raw, int) else None

        raw_engine_opts = tool_input.get("engine_options")
        if isinstance(raw_engine_opts, list):
            engine_options: list[str] = [
                str(item) for item in cast(list[Any], raw_engine_opts) if isinstance(item, str)
            ]
        else:
            engine_options = ["visual", "audio"]

        if not any((video_path, video_url, video_base64, video_id, previous_interaction_id)):
            raise ValueError(
                "At least one of 'video_path', 'video_url', 'video_base64', 'video_id', or "
                "'previous_interaction_id' must be provided."
            )

        # Route to TwelveLabs fallback ONLY when a non-Gemini `video_id` is passed (or `index_id` is explicitly
        # provided without Gemini API keys).
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        twelvelabs_key = os.environ.get("TWELVELABS_API_KEY")
        is_twelvelabs_video_id = bool(video_id and not _is_gemini_file_reference(video_id))

        if is_twelvelabs_video_id or (index_id and twelvelabs_key and not gemini_key):
            if not twelvelabs_key:
                raise ValueError(
                    "TWELVELABS_API_KEY environment variable not set for TwelveLabs video_id. "
                    "Provide a Gemini video source (video_path, video_url, video_base64, or 'files/...' video_id) "
                    "or set TWELVELABS_API_KEY."
                )
            return _chat_video_twelvelabs(
                tool_use_id=tool_use_id,
                prompt=prompt,
                video_id=video_id,
                video_path=video_path,
                index_id=index_id,
                temperature=temperature,
                engine_options=engine_options,
                api_key=twelvelabs_key,
            )

        client = _get_gemini_client()
        video_part = _resolve_gemini_video_part(
            client,
            video_path=video_path,
            video_url=video_url,
            video_base64=video_base64,
            video_id=video_id,
            mime_type=mime_type,
            processing=processing,
            resolution=resolution,
            start_offset=start_offset,
            end_offset=end_offset,
            fps=fps,
        )

        effective_prompt = _apply_engine_options_to_prompt(prompt, engine_options)
        text_part: dict[str, Any] = {"type": "text", "text": effective_prompt}

        # Official Gemini video-understanding best practice: place the video part BEFORE the text prompt
        input_parts: list[dict[str, Any]] = [video_part, text_part] if video_part is not None else [text_part]

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "thinking_level": "low",
        }
        if max_output_tokens is not None:
            generation_config["max_output_tokens"] = max_output_tokens

        candidate_models: list[str] = []
        if requested_model and requested_model.strip():
            candidate_models.append(requested_model.strip())
        for default_model in _DEFAULT_GEMINI_VIDEO_MODELS:
            if default_model not in candidate_models:
                candidate_models.append(default_model)

        last_error: Exception | None = None
        interaction: Any = None
        used_model = candidate_models[0]

        for model_id in candidate_models:
            used_model = model_id
            req_kwargs: dict[str, Any] = {
                "model": model_id,
                "input": input_parts,
                "generation_config": generation_config,
                "store": True,
                "timeout": 25.0,
            }
            if previous_interaction_id:
                req_kwargs["previous_interaction_id"] = previous_interaction_id
            if system_instruction:
                req_kwargs["system_instruction"] = system_instruction

            try:
                interaction = client.interactions.create(**req_kwargs)
                break
            except Exception as exc:
                last_error = exc
                if _is_retryable_capacity_error(exc) and model_id != candidate_models[-1]:
                    logger.warning(
                        "Model %s encountered capacity/rate-limit error (%s); failing over to next model",
                        model_id,
                        exc,
                    )
                    continue
                raise

        if interaction is None:
            raise RuntimeError(f"Video interaction failed across all candidate models: {last_error}")

        # Poll if interaction is still in_progress (e.g., long agentic video inspection)
        status = getattr(interaction, "status", None)
        interaction_id = getattr(interaction, "id", None)
        if status == "in_progress" and isinstance(interaction_id, str) and interaction_id:
            poll_deadline = time.monotonic() + 300.0
            while getattr(interaction, "status", None) == "in_progress":
                if time.monotonic() >= poll_deadline:
                    break
                time.sleep(2.0)
                interaction = client.interactions.get(interaction_id)

        output_text = getattr(interaction, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            # Fallback to extracting text from steps if output_text was empty
            extracted: list[str] = []
            steps = getattr(interaction, "steps", None)
            if isinstance(steps, list):
                for step in cast(list[Any], steps):
                    if getattr(step, "type", None) == "model_output":
                        content_list = getattr(step, "content", None)
                        if isinstance(content_list, list):
                            for item in cast(list[Any], content_list):
                                txt = getattr(item, "text", None)
                                if isinstance(txt, str) and txt:
                                    extracted.append(txt)
            output_text = "\n".join(extracted).strip() or "No text output generated by the model."

        final_interaction_id = str(getattr(interaction, "id", "") or "")
        effective_proc = (
            video_part.get("processing", "static")
            if isinstance(video_part, dict)
            else "multi-turn"
        )
        metadata_lines = [
            "\n\n---",
            f"Model: {used_model}",
            f"Processing: {effective_proc}",
            f"Temperature: {temperature}",
            f"Engine options: {', '.join(engine_options)}",
        ]
        if resolution:
            metadata_lines.append(f"Resolution: {resolution}")
        if final_interaction_id:
            metadata_lines.append(f"Interaction ID: {final_interaction_id}")

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [
                {
                    "text": output_text + "\n".join(metadata_lines),
                }
            ],
        }

    except FileNotFoundError as e:
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": f"File error: {e!s}"}],
        }

    except Exception as e:
        error_message = f"Error chatting with video: {e!s}"
        lower_err = str(e).lower()
        if "api_key" in lower_err or "gemini_api_key" in lower_err:
            error_message += "\n\nMake sure GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable is set."
        elif "not found" in lower_err:
            error_message += "\n\nThe specified video resource was not found. Verify the path, URL, or file ID."
        elif "throttl" in lower_err or "rate" in lower_err or "quota" in lower_err:
            error_message += "\n\nAPI rate limit or quota exceeded. Please try again later."

        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": error_message}],
        }
