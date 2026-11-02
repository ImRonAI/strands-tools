# pyright: strict
"""Native Gemini Interactions API & TwelveLabs video search tool for Strands Agent.

Provides three native modes for semantic video search across visual and audio modalities:
1. **In-Video Semantic Clip & Timestamp Search (Gemini Interactions API)**:
   When given `video_path`, `video_paths`, `video_url`, `video_urls`, `video_base64`, or a Gemini
   `files/...` `video_id`, searches inside the provided video(s) (`.mp4`, `.mov`, `.webm`, `.3gp`,
   YouTube URLs, HTTPS URLs, `gs://` URIs, Gemini Files API URIs, or base64 data) using
   `client.interactions.create` with `processing="agentic"` (default) or `"static"` and native
   JSON Schema structured output (`VideoSearchOutput`).
2. **External Web & YouTube Video Context Search (Gemini Interactions API + Google Search + Transcripts)**:
   When called with `query` alone (no local/remote video inputs and no TwelveLabs `index_id`),
   uses `client.interactions.create` with native `tools=[{"type": "google_search"}]` grounding
   and optional `youtube_transcript_api.YouTubeTranscriptApi().fetch(video_id)` caption enrichment
   to discover relevant videos, timestamped segments, and spoken transcript excerpts.
3. **Optional Lazy TwelveLabs Marengo Index Search**:
   When `index_id` (or `TWELVELABS_MARENGO_INDEX_ID`) and `TWELVELABS_API_KEY` are configured and
   no Gemini video inputs are passed, lazily imports `twelvelabs` and queries the Marengo index.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import logging
import mimetypes
import os
import re
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import parse_qs, urlparse

import google.genai as genai
import httpx
import pydantic
from strands.types.tools import ToolResult, ToolUse

logger = logging.getLogger(__name__)

DEFAULT_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-4-argon",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
)

_VIDEO_SEARCH_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_summary": {
            "type": "string",
            "description": "Brief synthesis of how the matched video segments answer or relate to the search query.",
        },
        "clips": {
            "type": "array",
            "description": "Matched video clips ordered from highest relevance score to lowest.",
            "items": {
                "type": "object",
                "properties": {
                    "video_id": {
                        "type": "string",
                        "description": "Identifier, filename, or URL of the video containing this segment.",
                    },
                    "start": {
                        "type": "number",
                        "description": "Start timestamp of the matched clip in seconds.",
                    },
                    "end": {
                        "type": "number",
                        "description": "End timestamp of the matched clip in seconds.",
                    },
                    "score": {
                        "type": "number",
                        "description": "Semantic relevance score between 0.0 and 1.0.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence tier: 'high', 'medium', or 'low'.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Concise description of visual scenes, actions, and audio context.",
                    },
                    "transcript_excerpt": {
                        "type": "string",
                        "description": "Spoken words, dialogue, or on-screen text appearing during this segment.",
                    },
                },
                "required": [
                    "video_id",
                    "start",
                    "end",
                    "score",
                    "confidence",
                    "summary",
                    "transcript_excerpt",
                ],
            },
        },
    },
    "required": ["clips", "overall_summary"],
}

INLINE_VIDEO_MAX_BYTES: int = 20 * 1024 * 1024  # 20 MB inline limit per Gemini docs

_THRESHOLD_SCORES: dict[str, float] = {
    "high": 0.8,
    "medium": 0.5,
    "low": 0.25,
    "none": 0.0,
}

_EXT_TO_VIDEO_MIME: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/mov",
    ".qt": "video/mov",
    ".webm": "video/webm",
    ".3gp": "video/3gpp",
    ".3gpp": "video/3gpp",
    ".mpeg": "video/mpeg",
    ".mpg": "video/ mpg".replace(" ", ""),
    ".avi": "video/avi",
    ".flv": "video/x-flv",
    ".wmv": "video/wmv",
    ".mkv": "video/mp4",
}

# Module-level SHA-256 cache for uploaded local video files -> (uri, mime_type, file_name)
_UPLOADED_VIDEO_CACHE: dict[str, tuple[str, str, str]] = {}

_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class VideoClipMatch(pydantic.BaseModel):
    """A single matched video segment with timestamps, relevance score, and multimodal context."""

    video_id: str = pydantic.Field(
        description="Identifier, filename, or URL of the video containing this segment."
    )
    start: float = pydantic.Field(
        description="Start timestamp of the matched clip in seconds from the beginning of the video."
    )
    end: float = pydantic.Field(
        description="End timestamp of the matched clip in seconds from the beginning of the video."
    )
    score: float = pydantic.Field(
        description="Semantic relevance score between 0.0 and 1.0 indicating how well the segment matches the query."
    )
    confidence: Literal["high", "medium", "low"] = pydantic.Field(
        description="Confidence tier: 'high' (>=0.8), 'medium' (0.5-0.79), or 'low' (<0.5)."
    )
    summary: str = pydantic.Field(
        description="Concise description of the visual scenes, actions, and audio context in this segment."
    )
    transcript_excerpt: str = pydantic.Field(
        description="Spoken words, dialogue, or on-screen text appearing during this segment (empty string if none)."
    )


class VideoSearchOutput(pydantic.BaseModel):
    """Structured output returned by Gemini Interactions API for semantic video search."""

    clips: list[VideoClipMatch] = pydantic.Field(
        description="Matched video clips ordered from highest relevance score to lowest."
    )
    overall_summary: str = pydantic.Field(
        description="Brief synthesis of how the matched video segments answer or relate to the search query."
    )


TOOL_SPEC: dict[str, Any] = {
    "name": "search_video",
    "description": """Search video content semantically for timestamped clips, visual scenes, and spoken audio.

Supports three native execution modes:
1. In-Video Semantic Clip & Timestamp Search (Gemini Interactions API):
   Provide `video_path`, `video_paths`, `video_url`, `video_urls`, `video_base64`, or a Gemini `files/...`
   `video_id` to locate exact timestamped segments (`start`/`end` in seconds, `score` 0.0-1.0,
   `confidence`, `summary`, and `transcript_excerpt`) inside `.mp4`, `.mov`, `.webm`, `.3gp`,
   YouTube URLs, HTTPS URLs, `gs://` URIs, or Gemini Files API videos using `processing="agentic"`
   (or `"static"`).
2. External Web & YouTube Video Context Search (Gemini Interactions API + Google Search + YouTube Transcripts):
   Provide `query` alone to discover relevant web/YouTube videos, timestamped highlights, and caption
   excerpts grounded via Google Search.
3. TwelveLabs Marengo Index Search (Optional Lazy Integration):
   Provide `index_id` (or `TWELVELABS_MARENGO_INDEX_ID`) with `TWELVELABS_API_KEY` to search an existing
   TwelveLabs Marengo index.

Usage Examples:
1. Search inside a local video file (iOS/macOS .mov or .mp4, Android/Chrome .webm):
   search_video(query="product demo presentation", video_path="/path/to/demo.mp4")

2. Search inside a YouTube video URL:
   search_video(query="keynote announcement", video_url="https://www.youtube.com/watch?v=9hE5-98ZeCg")

3. Search across multiple videos grouped by video:
   search_video(
       query="pricing discussion",
       video_paths=["/path/to/call1.mp4", "/path/to/call2.mov"],
       group_by="video",
       threshold="high",
   )

4. Web / YouTube video discovery by query alone:
   search_video(query="people discussing AI agents", page_limit=5)

5. Search a TwelveLabs Marengo index:
   search_video(query="product features", index_id="your-index-id")""",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query for video content, scenes, or spoken topics",
                },
                "video_path": {
                    "type": "string",
                    "description": "Local file path to a video (.mp4, .mov, .webm, .3gp, .mpeg, .avi, .mkv) to search",
                },
                "video_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of local video file paths to search across multiple videos",
                },
                "video_url": {
                    "type": "string",
                    "description": (
                        "Video URL or URI to search (YouTube watch/short URL, HTTPS video URL, "
                        "gs:// URI, or Gemini Files API URI)"
                    ),
                },
                "video_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of video URLs or URIs to search across multiple videos",
                },
                "video_base64": {
                    "type": "string",
                    "description": "Base64-encoded video payload (or data:video/...;base64,... URI) for inline search",
                },
                "video_mime_type": {
                    "type": "string",
                    "description": "MIME type for video_base64 or video_url (default: 'video/mp4')",
                },
                "video_id": {
                    "type": "string",
                    "description": "Gemini Files API resource name ('files/...') or video identifier",
                },
                "processing": {
                    "type": "string",
                    "enum": ["agentic", "static"],
                    "description": (
                        "Gemini video processing mode: 'agentic' dynamically navigates video timeline/transcripts "
                        "on Gemini 3.5+/4 models; 'static' samples frames at 1 FPS. Default: 'agentic'"
                    ),
                },
                "model_id": {
                    "type": "string",
                    "description": (
                        "Optional Gemini model ID override. Defaults to failover chain: "
                        "gemini-3.8-flash -> gemini-4-argon -> gemini-3.5-flash-lite"
                    ),
                },
                "index_id": {
                    "type": "string",
                    "description": (
                        "Optional TwelveLabs Marengo index ID to search when using TwelveLabs. "
                        "Uses TWELVELABS_MARENGO_INDEX_ID env var if not provided"
                    ),
                },
                "search_options": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["visual", "audio"],
                    },
                    "description": "Search modalities to use. Default: ['visual', 'audio']",
                },
                "group_by": {
                    "type": "string",
                    "enum": ["video", "clip"],
                    "description": (
                        "How to group results. 'clip' returns individual segments, "
                        "'video' groups clips by video. Default: 'clip'"
                    ),
                },
                "threshold": {
                    "type": "string",
                    "enum": ["high", "medium", "low", "none"],
                    "description": "Minimum confidence threshold for results. Default: 'medium'",
                },
                "page_limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return. Default: 10",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["query"],
        }
    },
}


def _detect_video_mime_type(path_or_url: str, fallback: str = "video/mp4") -> str:
    """Resolve a Gemini-supported video MIME type from a file path or URL."""
    parsed = urlparse(path_or_url)
    ext = Path(parsed.path if parsed.scheme else path_or_url).suffix.lower()
    if ext in _EXT_TO_VIDEO_MIME:
        return _EXT_TO_VIDEO_MIME[ext]
    guessed, _ = mimetypes.guess_type(path_or_url)
    if guessed and guessed.startswith("video/"):
        if guessed == "video/quicktime":
            return "video/mov"
        return guessed
    return fallback


def _extract_youtube_video_id(url_or_id: str) -> str | None:
    """Extract an 11-character YouTube video ID from a URL or bare ID string, if valid."""
    candidate = url_or_id.strip()
    if _YOUTUBE_ID_RE.match(candidate):
        return candidate

    try:
        parsed = urlparse(candidate)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid if _YOUTUBE_ID_RE.match(vid) else None

    if host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            v_list = qs.get("v")
            if v_list and _YOUTUBE_ID_RE.match(v_list[0]):
                return v_list[0]
        for prefix in ("/shorts/", "/embed/", "/v/", "/live/"):
            if parsed.path.startswith(prefix):
                vid = parsed.path[len(prefix) :].split("/")[0]
                if _YOUTUBE_ID_RE.match(vid):
                    return vid
    return None


def _normalize_youtube_url(url: str) -> str | None:
    """Return a canonical `https://www.youtube.com/watch?v=<id>` URL if `url` is a YouTube link."""
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return None
    vid = _extract_youtube_video_id(url)
    if vid is not None:
        return f"https://www.youtube.com/watch?v={vid}"
    return None


def _get_gemini_client() -> genai.Client:
    """Create a configured `google.genai.Client` with fast retry failover and per-request timeout."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "Neither GEMINI_API_KEY nor GOOGLE_API_KEY environment variable is set. "
            "Set GEMINI_API_KEY for Gemini Interactions API video search (or TWELVELABS_API_KEY + "
            "TWELVELABS_MARENGO_INDEX_ID for TwelveLabs Marengo index search)."
        )
    client = genai.Client(
        api_key=api_key,
        http_options={
            "timeout": 30_000,
            "retry_options": {
                "attempts": 0,
            },
        },
    )
    sdk_cfg: Any = getattr(client.interactions, "sdk_configuration", None)
    retry_cfg: Any = getattr(sdk_cfg, "retry_config", None) if sdk_cfg is not None else None
    if retry_cfg is not None:
        retry_cfg.max_retries = 0
        retry_cfg.retry_connection_errors = False
    return client


def _upload_and_wait_for_active(
    client: genai.Client,
    file_path: Path,
    mime_type: str,
) -> tuple[str, str, str]:
    """Upload a local video file via Gemini Files API (`client.files.upload`) and poll until `ACTIVE`."""
    file_bytes = file_path.read_bytes()
    sha256_hex = hashlib.sha256(file_bytes).hexdigest()

    cached = _UPLOADED_VIDEO_CACHE.get(sha256_hex)
    if cached is not None:
        _cached_uri, cached_mime, cached_name = cached
        try:
            existing = client.files.get(name=cached_name)
            state_name = getattr(existing.state, "name", str(existing.state or ""))
            if state_name == "ACTIVE" and existing.uri:
                return existing.uri, str(existing.mime_type or cached_mime), cached_name
        except Exception:
            _UPLOADED_VIDEO_CACHE.pop(sha256_hex, None)

    uploaded = client.files.upload(
        file=str(file_path),
        config={"mime_type": mime_type, "display_name": file_path.name},
    )
    file_name = str(uploaded.name or "")
    deadline = time.monotonic() + 120.0

    while True:
        state_obj = uploaded.state
        state_name = getattr(state_obj, "name", str(state_obj or ""))
        if state_name == "ACTIVE":
            break
        if state_name == "FAILED":
            raise RuntimeError(f"Gemini Files API processing failed for video '{file_path.name}'.")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for Gemini Files API to process '{file_path.name}'.")
        time.sleep(2.0)
        if file_name:
            uploaded = client.files.get(name=file_name)

    uri = str(uploaded.uri or "")
    resolved_mime = str(uploaded.mime_type or mime_type)
    if not uri:
        raise RuntimeError(f"Gemini Files API did not return a URI for uploaded file '{file_path.name}'.")

    _UPLOADED_VIDEO_CACHE[sha256_hex] = (uri, resolved_mime, file_name)
    return uri, resolved_mime, file_name


def _prepare_gemini_video_parts(
    client: genai.Client,
    *,
    video_paths: Sequence[str],
    video_urls: Sequence[str],
    video_base64: str | None,
    video_mime_type: str,
    video_id: str | None,
    requested_processing: Literal["agentic", "static"],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Build Gemini Interactions API `video` content parts, video labels, and optional transcript notes."""
    video_parts: list[dict[str, Any]] = []
    video_labels: list[str] = []
    transcript_sections: list[str] = []

    # 1. Handle Gemini Files API `files/...` or file/URL passed via `video_id`
    if video_id:
        vid_clean = video_id.strip()
        if vid_clean.startswith("files/"):
            file_obj = client.files.get(name=vid_clean)
            deadline = time.monotonic() + 60.0
            while getattr(file_obj.state, "name", str(file_obj.state or "")) == "PROCESSING":
                if time.monotonic() >= deadline:
                    break
                time.sleep(2.0)
                file_obj = client.files.get(name=vid_clean)
            if not file_obj.uri:
                raise ValueError(f"Gemini file '{vid_clean}' does not have an active URI.")
            video_parts.append(
                {
                    "type": "video",
                    "uri": file_obj.uri,
                    "mime_type": str(file_obj.mime_type or video_mime_type),
                    "processing": requested_processing,
                }
            )
            video_labels.append(vid_clean)
        elif vid_clean.startswith(("http://", "https://", "gs://")):
            video_urls = [*video_urls, vid_clean]
        elif Path(vid_clean).expanduser().exists():
            video_paths = [*video_paths, vid_clean]

    # 2. Handle local file paths (`video_path` / `video_paths`)
    for raw_path in video_paths:
        resolved_path = Path(raw_path).expanduser().resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"Video file not found: {raw_path}")
        mime = _detect_video_mime_type(str(resolved_path), fallback=video_mime_type)
        label = resolved_path.name
        try:
            uri, uploaded_mime, _ = _upload_and_wait_for_active(client, resolved_path, mime)
            video_parts.append(
                {
                    "type": "video",
                    "uri": uri,
                    "mime_type": uploaded_mime,
                    "processing": requested_processing,
                }
            )
        except Exception as upload_exc:
            file_size = resolved_path.stat().st_size
            if file_size <= INLINE_VIDEO_MAX_BYTES:
                logger.debug(
                    "path=<%s>, error=<%s> | falling back to inline base64 static video input",
                    resolved_path,
                    upload_exc,
                )
                b64_data = base64.b64encode(resolved_path.read_bytes()).decode("ascii")
                video_parts.append(
                    {
                        "type": "video",
                        "data": b64_data,
                        "mime_type": mime,
                        "processing": "static",
                    }
                )
            else:
                raise
        video_labels.append(label)

    # 3. Handle URLs and URIs (`video_url` / `video_urls`)
    for raw_url in video_urls:
        url_clean = raw_url.strip()
        if not url_clean:
            continue

        yt_canonical = _normalize_youtube_url(url_clean)
        if yt_canonical is not None:
            video_parts.append(
                {
                    "type": "video",
                    "uri": yt_canonical,
                    "processing": requested_processing,
                    "resolution": "low",
                }
            )
            video_labels.append(yt_canonical)
            continue

        if url_clean.startswith("files/"):
            file_obj = client.files.get(name=url_clean)
            if not file_obj.uri:
                raise ValueError(f"Gemini file '{url_clean}' does not have an active URI.")
            video_parts.append(
                {
                    "type": "video",
                    "uri": file_obj.uri,
                    "mime_type": str(file_obj.mime_type or video_mime_type),
                    "processing": requested_processing,
                }
            )
            video_labels.append(url_clean)
            continue

        if url_clean.startswith("gs://") or "generativelanguage.googleapis.com" in url_clean:
            mime = _detect_video_mime_type(url_clean, fallback=video_mime_type)
            video_parts.append(
                {
                    "type": "video",
                    "uri": url_clean,
                    "mime_type": mime,
                    "processing": requested_processing,
                }
            )
            video_labels.append(url_clean)
            continue

        if url_clean.startswith(("http://", "https://")):
            mime = _detect_video_mime_type(url_clean, fallback=video_mime_type)
            # Download external HTTPS video and either inline (<20 MB) or upload via Files API
            with httpx.Client(follow_redirects=True, timeout=30.0) as http_client:
                resp = http_client.get(url_clean)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "").split(";")[0].strip()
                if content_type.startswith("video/"):
                    mime = "video/mov" if content_type == "video/quicktime" else content_type
                raw_bytes = resp.content

            if len(raw_bytes) <= INLINE_VIDEO_MAX_BYTES and requested_processing == "static":
                video_parts.append(
                    {
                        "type": "video",
                        "data": base64.b64encode(raw_bytes).decode("ascii"),
                        "mime_type": mime,
                        "processing": "static",
                    }
                )
            else:
                suffix = Path(urlparse(url_clean).path).suffix or ".mp4"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(raw_bytes)
                    tmp_path = Path(tmp.name)
                try:
                    uri, uploaded_mime, _ = _upload_and_wait_for_active(client, tmp_path, mime)
                    video_parts.append(
                        {
                            "type": "video",
                            "uri": uri,
                            "mime_type": uploaded_mime,
                            "processing": requested_processing,
                        }
                    )
                finally:
                    tmp_path.unlink(missing_ok=True)
            video_labels.append(url_clean)
            continue

        raise ValueError(f"Unsupported video URL or URI: {url_clean}")

    # 4. Handle inline base64 (`video_base64`)
    if video_base64:
        b64_clean = video_base64.strip()
        mime = video_mime_type
        if b64_clean.startswith("data:"):
            header, _, payload = b64_clean.partition(",")
            b64_clean = payload.strip()
            mime_part = header[5:].split(";")[0].strip()
            if mime_part.startswith("video/"):
                mime = "video/mov" if mime_part == "video/quicktime" else mime_part

        raw_bytes = base64.b64decode(b64_clean)
        label = video_id or "inline_video"
        if len(raw_bytes) <= INLINE_VIDEO_MAX_BYTES:
            # Inline base64 video uses static processing per Gemini API specification
            video_parts.append(
                {
                    "type": "video",
                    "data": base64.b64encode(raw_bytes).decode("ascii"),
                    "mime_type": mime,
                    "processing": "static",
                }
            )
        else:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = Path(tmp.name)
            try:
                uri, uploaded_mime, _ = _upload_and_wait_for_active(client, tmp_path, mime)
                video_parts.append(
                    {
                        "type": "video",
                        "uri": uri,
                        "mime_type": uploaded_mime,
                        "processing": requested_processing,
                    }
                )
            finally:
                tmp_path.unlink(missing_ok=True)
        video_labels.append(label)

    return video_parts, video_labels, transcript_sections


def _run_interaction_with_failover(
    client: genai.Client,
    *,
    model_chain: Sequence[str],
    input_payload: Any,
    system_instruction: str,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[VideoSearchOutput, str]:
    """Call `client.interactions.create` across `model_chain` with structured output `VideoSearchOutput`."""
    last_error: Exception | None = None

    for candidate_model in model_chain:
        tool_variants: list[list[dict[str, Any]] | None] = [tools, None] if tools else [None]
        for active_tools in tool_variants:
            try:
                request_kwargs: dict[str, Any] = {
                    "model": candidate_model,
                    "input": input_payload,
                    "system_instruction": system_instruction,
                    "generation_config": {
                        "temperature": 0.1,
                        "thinking_level": "low",
                    },
                    "response_format": {
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": _VIDEO_SEARCH_RESPONSE_SCHEMA,
                    },
                    "store": False,
                    "timeout": 10.0 if active_tools else 22.0,
                }
                if active_tools:
                    request_kwargs["tools"] = active_tools

                interaction = client.interactions.create(**request_kwargs)
                output_text = str(getattr(interaction, "output_text", "") or "").strip()
                if not output_text:
                    # Reconstruct from model_output steps if output_text was not populated
                    chunks: list[str] = []
                    raw_steps = cast(Sequence[object], getattr(interaction, "steps", None) or ())
                    for step in raw_steps:
                        if getattr(step, "type", None) == "model_output":
                            raw_items = cast(Sequence[object], getattr(step, "content", None) or ())
                            for item in raw_items:
                                if getattr(item, "type", None) == "text":
                                    txt = getattr(item, "text", None)
                                    if isinstance(txt, str):
                                        chunks.append(txt)
                    output_text = "".join(chunks).strip()

                parsed = VideoSearchOutput.model_validate_json(output_text)
                return parsed, candidate_model
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "model=<%s>, tools=<%s>, error=<%s> | Gemini Interactions video search attempt failed",
                    candidate_model,
                    bool(active_tools),
                    exc,
                )
                continue

    raise RuntimeError(f"All Gemini models failed for video search: {last_error}") from last_error


def _normalize_and_filter_clips(
    clips: Sequence[VideoClipMatch],
    *,
    threshold: str,
    page_limit: int,
) -> list[VideoClipMatch]:
    """Normalize clip confidence/scores, filter by `threshold`, sort by descending score, and apply `page_limit`."""
    min_score = _THRESHOLD_SCORES.get(threshold, 0.5)
    filtered: list[VideoClipMatch] = []

    for clip in clips:
        clamped_score = max(0.0, min(1.0, float(clip.score)))
        if clamped_score < min_score:
            continue
        computed_conf: Literal["high", "medium", "low"] = (
            "high" if clamped_score >= 0.8 else ("medium" if clamped_score >= 0.5 else "low")
        )
        start_s = max(0.0, float(clip.start))
        end_s = max(start_s, float(clip.end))
        filtered.append(
            VideoClipMatch(
                video_id=clip.video_id,
                start=round(start_s, 2),
                end=round(end_s, 2),
                score=round(clamped_score, 3),
                confidence=computed_conf,
                summary=clip.summary.strip(),
                transcript_excerpt=clip.transcript_excerpt.strip(),
            )
        )

    filtered.sort(key=lambda c: c.score, reverse=True)
    return filtered[:page_limit]


def _format_gemini_search_results(
    clips: Sequence[VideoClipMatch],
    *,
    overall_summary: str,
    group_by: str,
) -> str:
    """Format `VideoClipMatch` results for human-readable display."""
    if not clips:
        base = "No results found matching the search criteria."
        if overall_summary:
            return f"{base}\n\nSummary: {overall_summary}"
        return base

    formatted: list[str] = [f"Found {len(clips)} matching results"]
    if overall_summary:
        formatted.append(f"Overview: {overall_summary}")

    if group_by == "video":
        grouped: dict[str, list[VideoClipMatch]] = {}
        for clip in clips:
            grouped.setdefault(clip.video_id, []).append(clip)

        for idx, (vid_id, vid_clips) in enumerate(grouped.items(), 1):
            formatted.append(f"\n{idx}. Video ID: {vid_id}")
            formatted.append(f"   Found {len(vid_clips)} clips:")
            for j, clip in enumerate(vid_clips, 1):
                formatted.append(
                    f"   {j}. Score: {clip.score:.3f} | "
                    f"{clip.start:.1f}s-{clip.end:.1f}s | "
                    f"Confidence: {clip.confidence}"
                )
                if clip.summary:
                    formatted.append(f"      Summary: {clip.summary}")
                if clip.transcript_excerpt:
                    formatted.append(f'      Transcript: "{clip.transcript_excerpt}"')
    else:
        for idx, clip in enumerate(clips, 1):
            formatted.append(f"\n{idx}. Video: {clip.video_id}")
            formatted.append(f"   Score: {clip.score:.3f}")
            formatted.append(f"   Time: {clip.start:.1f}s - {clip.end:.1f}s")
            formatted.append(f"   Confidence: {clip.confidence}")
            if clip.summary:
                formatted.append(f"   Summary: {clip.summary}")
            if clip.transcript_excerpt:
                formatted.append(f'   Transcript: "{clip.transcript_excerpt}"')

    return "\n".join(formatted)


def format_search_results(results: Sequence[Any], group_by: str, total_count: int) -> str:
    """Format TwelveLabs Marengo search results for display.

    Args:
        results: Sequence of search result objects from TwelveLabs.
        group_by: How results are grouped (`'video'` or `'clip'`).
        total_count: Total number of results found in the pool.

    Returns:
        Formatted string containing search results.
    """
    if not results:
        return "No results found matching the search criteria."

    formatted = [f"Found {total_count} total results\n"]

    if group_by == "video":
        for i, video in enumerate(results, 1):
            vid_id = getattr(video, "id", "unknown")
            formatted.append(f"\n{i}. Video ID: {vid_id}")
            raw_video_clips = getattr(video, "clips", None)
            if isinstance(raw_video_clips, Sequence) and not isinstance(raw_video_clips, (str, bytes)):
                video_clips = cast(Sequence[object], raw_video_clips)
                if len(video_clips) > 0:
                    formatted.append(f"   Found {len(video_clips)} clips:")
                    for j, clip in enumerate(list(video_clips)[:3], 1):
                        c_score = float(getattr(clip, "score", 0.0))
                        c_start = float(getattr(clip, "start", 0.0))
                        c_end = float(getattr(clip, "end", 0.0))
                        c_conf = getattr(clip, "confidence", "medium")
                        formatted.append(
                            f"   {j}. Score: {c_score:.3f} | "
                            f"{c_start:.1f}s-{c_end:.1f}s | "
                            f"Confidence: {c_conf}"
                        )
                    if len(video_clips) > 3:
                        formatted.append(f"   ... and {len(video_clips) - 3} more clips")
    else:
        for i, clip in enumerate(results, 1):
            c_vid = getattr(clip, "video_id", "unknown")
            c_score = float(getattr(clip, "score", 0.0))
            c_start = float(getattr(clip, "start", 0.0))
            c_end = float(getattr(clip, "end", 0.0))
            c_conf = getattr(clip, "confidence", "medium")
            formatted.append(f"\n{i}. Video: {c_vid}")
            formatted.append(f"   Score: {c_score:.3f}")
            formatted.append(f"   Time: {c_start:.1f}s - {c_end:.1f}s")
            formatted.append(f"   Confidence: {c_conf}")

    return "\n".join(formatted)


def _search_twelvelabs_index(
    *,
    tool_use_id: str,
    query: str,
    index_id: str,
    api_key: str,
    search_options: list[str],
    group_by: str,
    threshold: str,
    page_limit: int,
) -> ToolResult:
    """Execute Mode 3: Lazy TwelveLabs Marengo index search when `index_id` and `TWELVELABS_API_KEY` are set."""
    try:
        twelvelabs_mod = importlib.import_module("twelvelabs")
        twelvelabs_cls = getattr(twelvelabs_mod, "TwelveLabs")
    except ImportError as exc:
        raise ImportError(
            "TwelveLabs index_id was provided, but the 'twelvelabs' package is not installed. "
            "Install it with `pip install twelvelabs` or pass `video_path`/`video_url` to use "
            "native Gemini Interactions API video search."
        ) from exc

    with twelvelabs_cls(api_key) as client:
        search_result = client.search.query(
            index_id=index_id,
            query_text=query,
            options=search_options,
            group_by=group_by,
            threshold=threshold,
            page_limit=page_limit,
        )

        total_count = 0
        pool = getattr(search_result, "pool", None)
        if pool is not None and hasattr(pool, "total_count"):
            total_count = int(getattr(pool, "total_count", 0))

        raw_data = getattr(search_result, "data", None)
        results_list = list(raw_data) if raw_data is not None else []
        formatted_results = format_search_results(results_list, group_by, total_count)

        summary_parts = [
            f'Video Search Results for: "{query}"',
            "Mode: TwelveLabs Marengo Index Search",
            f"Index: {index_id}",
            f"Search options: {', '.join(search_options)}",
            f"Confidence threshold: {threshold}",
            "",
            formatted_results,
        ]

        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": "\n".join(summary_parts)}],
        }


def search_video(tool: ToolUse, **kwargs: Any) -> ToolResult:
    """Search video content using the Gemini Interactions API (in-video or web/YouTube) or TwelveLabs Marengo.

    Args:
        tool: Tool use payload containing input parameters:
            - `query` (str): Natural language search query.
            - `video_path` / `video_paths` (str | list[str], optional): Local video file(s) to search.
            - `video_url` / `video_urls` (str | list[str], optional): YouTube URL(s), HTTPS URL(s), `gs://` URI(s),
              or Gemini Files API URI(s) to search.
            - `video_base64` (str, optional): Inline base64-encoded video content (`< 20 MB`).
            - `video_mime_type` (str, optional): Video MIME type (default `'video/mp4'`).
            - `video_id` (str, optional): Gemini Files API resource name (`'files/...'`) or video identifier.
            - `processing` (`'agentic'` | `'static'`, optional): Gemini video processing mode (default `'agentic'`).
            - `model_id` (str, optional): Gemini model ID override.
            - `index_id` (str, optional): TwelveLabs Marengo index ID.
            - `search_options` (list[str], optional): Modalities `['visual', 'audio']` (default both).
            - `group_by` (`'clip'` | `'video'`, optional): Grouping mode (default `'clip'`).
            - `threshold` (`'high'` | `'medium'` | `'low'` | `'none'`, optional): Confidence filter (default `'medium'`).
            - `page_limit` (int, optional): Maximum results to return (default `10`).
        **kwargs: Additional keyword arguments ignored by the tool.

    Returns:
        Strands `ToolResult` containing human-readable timestamped search results and structured JSON output.
    """
    del kwargs
    tool_use_id = str(tool.get("toolUseId", "tooluse_search_video"))
    raw_input = tool.get("input")
    tool_input: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw_input) if isinstance(raw_input, Mapping) else {}
    )

    try:
        query = str(tool_input.get("query", "")).strip()
        if not query:
            raise ValueError("Parameter 'query' is required and cannot be empty.")

        raw_options = tool_input.get("search_options")
        if isinstance(raw_options, Sequence) and not isinstance(raw_options, (str, bytes)):
            typed_options = cast(Sequence[object], raw_options)
            search_options = [str(opt) for opt in typed_options if str(opt) in ("visual", "audio")]
        else:
            search_options = ["visual", "audio"]
        if not search_options:
            search_options = ["visual", "audio"]

        group_by = str(tool_input.get("group_by") or "clip")
        if group_by not in ("clip", "video"):
            group_by = "clip"

        threshold = str(tool_input.get("threshold") or "medium")
        if threshold not in _THRESHOLD_SCORES:
            threshold = "medium"

        raw_limit = tool_input.get("page_limit", 10)
        page_limit = max(1, min(100, int(raw_limit))) if isinstance(raw_limit, (int, float, str)) else 10

        raw_processing = str(tool_input.get("processing") or "agentic").lower()
        requested_processing: Literal["agentic", "static"] = (
            "static" if raw_processing == "static" else "agentic"
        )

        video_mime_type = str(tool_input.get("video_mime_type") or "video/mp4").strip()
        video_id_param = str(tool_input.get("video_id") or "").strip() or None
        video_base64 = str(tool_input.get("video_base64") or "").strip() or None

        video_paths: list[str] = []
        single_path = tool_input.get("video_path")
        if isinstance(single_path, str) and single_path.strip():
            video_paths.append(single_path.strip())
        multi_paths = tool_input.get("video_paths")
        if isinstance(multi_paths, Sequence) and not isinstance(multi_paths, (str, bytes)):
            for p in cast(Sequence[object], multi_paths):
                if isinstance(p, str) and p.strip():
                    video_paths.append(p.strip())

        video_urls: list[str] = []
        single_url = tool_input.get("video_url")
        if isinstance(single_url, str) and single_url.strip():
            video_urls.append(single_url.strip())
        multi_urls = tool_input.get("video_urls")
        if isinstance(multi_urls, Sequence) and not isinstance(multi_urls, (str, bytes)):
            for u in cast(Sequence[object], multi_urls):
                if isinstance(u, str) and u.strip():
                    video_urls.append(u.strip())

        model_override = str(tool_input.get("model_id") or "").strip()
        model_chain: tuple[str, ...] = (
            (model_override, *[m for m in DEFAULT_MODEL_CHAIN if m != model_override])
            if model_override
            else DEFAULT_MODEL_CHAIN
        )

        has_gemini_video_input = bool(
            video_paths
            or video_urls
            or video_base64
            or (
                video_id_param
                and (
                    video_id_param.startswith(("files/", "http://", "https://", "gs://"))
                    or Path(video_id_param).expanduser().exists()
                )
            )
        )

        explicit_index_id = str(tool_input.get("index_id") or "").strip()
        env_index_id = os.getenv("TWELVELABS_MARENGO_INDEX_ID", "").strip()
        twelvelabs_api_key = os.getenv("TWELVELABS_API_KEY", "").strip()
        effective_index_id = explicit_index_id or env_index_id

        # Mode 3: Optional Lazy TwelveLabs Marengo Index Search
        if not has_gemini_video_input and effective_index_id and twelvelabs_api_key:
            return _search_twelvelabs_index(
                tool_use_id=tool_use_id,
                query=query,
                index_id=effective_index_id,
                api_key=twelvelabs_api_key,
                search_options=search_options,
                group_by=group_by,
                threshold=threshold,
                page_limit=page_limit,
            )

        if not has_gemini_video_input and explicit_index_id and not twelvelabs_api_key:
            raise ValueError(
                "TWELVELABS_API_KEY environment variable not set for TwelveLabs index_id search. "
                "Set TWELVELABS_API_KEY or pass `video_path`/`video_url` to search with Gemini Interactions API."
            )

        client = _get_gemini_client()
        modality_desc = " and ".join(search_options)

        # Mode 1: In-Video Semantic Clip & Timestamp Search via Gemini Interactions API
        if has_gemini_video_input:
            video_parts, video_labels, transcript_notes = _prepare_gemini_video_parts(
                client,
                video_paths=video_paths,
                video_urls=video_urls,
                video_base64=video_base64,
                video_mime_type=video_mime_type,
                video_id=video_id_param,
                requested_processing=requested_processing,
            )

            labels_listing = ", ".join(f"Video #{i + 1}: {lbl!r}" for i, lbl in enumerate(video_labels))
            prompt_lines = [
                f'Search the provided video(s) ({labels_listing}) for segments matching query: "{query}".',
                f"Modalities to analyze: {modality_desc}.",
                f"Return up to {page_limit} matching clips with exact start and end timestamps in seconds, "
                "relevance score (0.0 to 1.0), confidence ('high', 'medium', 'low'), visual/audio summary, "
                "and spoken or on-screen transcript_excerpt.",
                "Use the corresponding video label as `video_id` for each clip.",
            ]
            if transcript_notes:
                prompt_lines.append("\n" + "\n\n".join(transcript_notes))

            input_blocks: list[dict[str, Any]] = [
                *video_parts,
                {"type": "text", "text": "\n".join(prompt_lines)},
            ]
            system_instruction = (
                "You are a precision multimodal video search engine. Inspect the video timeline across the requested "
                f"modalities ({modality_desc}), identify every segment that matches the user's query, and return "
                "accurate start/end timestamps in seconds, calibrated relevance scores (0.0-1.0), concise visual/audio "
                "summaries, and verbatim transcript excerpts."
            )

            search_output, used_model = _run_interaction_with_failover(
                client,
                model_chain=model_chain,
                input_payload=input_blocks,
                system_instruction=system_instruction,
            )
            clips = _normalize_and_filter_clips(
                search_output.clips,
                threshold=threshold,
                page_limit=page_limit,
            )

            formatted_text = _format_gemini_search_results(
                clips,
                overall_summary=search_output.overall_summary,
                group_by=group_by,
            )
            header_parts = [
                f'Video Search Results for: "{query}"',
                f"Mode: Gemini Interactions In-Video Search (model={used_model}, processing={requested_processing})",
                f"Videos searched: {', '.join(video_labels)}",
                f"Search options: {', '.join(search_options)}",
                f"Confidence threshold: {threshold}",
                "",
                formatted_text,
            ]
            structured_payload: dict[str, Any] = {
                "mode": "gemini_in_video_search",
                "query": query,
                "model": used_model,
                "processing": requested_processing,
                "videos": video_labels,
                "search_options": search_options,
                "group_by": group_by,
                "threshold": threshold,
                "total_count": len(clips),
                "overall_summary": search_output.overall_summary,
                "clips": [c.model_dump() for c in clips],
            }
            return {
                "toolUseId": tool_use_id,
                "status": "success",
                "content": [
                    {"text": "\n".join(header_parts)},
                    {"json": structured_payload},
                ],
            }

        # Mode 2: External Web / YouTube Video Context Search via Gemini Interactions API + Google Search
        web_prompt = (
            f'Find relevant YouTube and web videos and specific timestamped segments matching: "{query}".\n'
            f"Focus on {modality_desc} content. Return up to {page_limit} results. "
            "For each result, set `video_id` to the full YouTube watch URL (e.g. https://www.youtube.com/watch?v=...) "
            "or direct video URL, provide `start` and `end` timestamps in seconds for the relevant segment "
            "(or 0.0 to 60.0 if the entire video is relevant), a calibrated `score` (0.0 to 1.0), `confidence` "
            "('high', 'medium', 'low'), a detailed `summary` of what is shown and discussed, and any known "
            "`transcript_excerpt` or key quote."
        )
        system_instruction = (
            "You are a video search engine grounded with Google Search. Discover real, verifiable YouTube and web "
            "videos matching the user's query, extract key timestamped segments and spoken quotes, and return them "
            "in the requested JSON schema."
        )

        search_output, used_model = _run_interaction_with_failover(
            client,
            model_chain=model_chain,
            input_payload=[{"type": "text", "text": web_prompt}],
            system_instruction=system_instruction,
            tools=[{"type": "google_search"}],
        )
        clips = _normalize_and_filter_clips(
            search_output.clips,
            threshold=threshold,
            page_limit=page_limit,
        )

        formatted_text = _format_gemini_search_results(
            clips,
            overall_summary=search_output.overall_summary,
            group_by=group_by,
        )
        header_parts = [
            f'Video Search Results for: "{query}"',
            f"Mode: Gemini Interactions Web & YouTube Video Search (model={used_model})",
            f"Search options: {', '.join(search_options)}",
            f"Confidence threshold: {threshold}",
            "",
            formatted_text,
        ]
        structured_payload = {
            "mode": "gemini_web_video_search",
            "query": query,
            "model": used_model,
            "search_options": search_options,
            "group_by": group_by,
            "threshold": threshold,
            "total_count": len(clips),
            "overall_summary": search_output.overall_summary,
            "clips": [c.model_dump() for c in clips],
        }
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [
                {"text": "\n".join(header_parts)},
                {"json": structured_payload},
            ],
        }

    except Exception as exc:
        error_message = f"Error searching videos: {exc!s}"
        lower_err = str(exc).lower()
        if "api_key" in lower_err:
            error_message += (
                "\n\nMake sure GEMINI_API_KEY (or GOOGLE_API_KEY) is set for Gemini video search, "
                "or TWELVELABS_API_KEY + TWELVELABS_MARENGO_INDEX_ID for TwelveLabs index search."
            )
        elif "index" in lower_err:
            error_message += "\n\nMake sure the index_id is valid and you have access to it."
        elif "throttl" in lower_err or "rate" in lower_err or "quota" in lower_err:
            error_message += "\n\nAPI rate limit exceeded. Please try again later."

        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": error_message}],
        }
