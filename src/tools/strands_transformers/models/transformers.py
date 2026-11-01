"""HuggingFace Transformers model provider.

Direct integration with locally loaded transformers models, supporting
fine-tuned models with merged LoRA weights AND multimodal (vision-language)
models that consume image / video / document content blocks.

- Docs: https://huggingface.co/docs/transformers
"""

import io
import json
import logging
import re
import time
from threading import Thread
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import torch
from pydantic import BaseModel
from strands.models._validation import (
    validate_config_keys,
    warn_on_tool_choice_not_supported,
)
from strands.models.model import Model
from strands.types.content import ContentBlock, Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TextIteratorStreamer,
)
from typing_extensions import TypedDict, Unpack, override

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Pull a JSON object/array out of a model response.

    Handles reasoning models that prefix output with <think>...</think>, and
    JSON wrapped in markdown code fences. Falls back to the first balanced
    {...} or [...] span found in the text.

    The balanced-span scan is string-aware (braces/brackets inside JSON string
    literals do not affect nesting depth) and anchors on whichever delimiter --
    object or array -- appears first, so a top-level array of objects is not
    mistaken for its inner object.
    """
    # strip closed <think>...</think> reasoning blocks (Qwen3 etc.)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # for an unterminated <think> (no closing tag), drop the tag itself but keep
    # the trailing content (which usually contains the JSON answer)
    text = text.replace("<think>", "")

    # markdown code fences
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]

    text = text.strip()

    # already valid?
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # Balanced JSON span anchored at the first opening delimiter (object OR
    # array, whichever appears first). A naive brace counter mishandles two real
    # cases: a brace/bracket inside a string value (e.g. "echo }") prematurely
    # closes the span, and a top-level array of objects ([{...}]) is truncated
    # to its inner object. Track string/escape state and pick the earliest
    # delimiter to handle both.
    obj_start = text.find("{")
    arr_start = text.find("[")
    starts = [s for s in (obj_start, arr_start) if s != -1]
    if not starts:
        return text
    start = min(starts)
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


def _bytes_to_pil(data: Any) -> Optional[Any]:
    """Best-effort decode of image bytes (or a passthrough PIL/np image) to PIL.Image.

    Returns None if PIL is unavailable or the payload can't be decoded.
    """
    try:
        from PIL import Image
    except Exception:  # pragma: no cover - PIL should be present for VLMs
        return None

    # Already a PIL image (Image.isImageType removed in Pillow 12.x; use isinstance).
    # Normalize to RGB so grayscale/palette/RGBA/CMYK inputs match what vision
    # processors expect (the bytes-decode path already does .convert("RGB")).
    if isinstance(data, Image.Image):
        return data if data.mode == "RGB" else data.convert("RGB")

    # numpy array -> PIL
    try:
        import numpy as np

        if isinstance(data, np.ndarray):
            return Image.fromarray(data)
    except Exception:
        pass

    # raw bytes -> PIL
    if isinstance(data, (bytes, bytearray)):
        try:
            return Image.open(io.BytesIO(bytes(data))).convert("RGB")
        except Exception as e:
            logger.warning("failed to decode image bytes: %s", e)
            return None

    # data URI / file path string
    if isinstance(data, str):
        try:
            if data.startswith("data:"):
                import base64

                b64 = data.split(",", 1)[1]
                return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            return Image.open(data).convert("RGB")
        except Exception as e:
            logger.warning("failed to open image path/uri: %s", e)
            return None

    return None


def _normalize_video(payload: Any) -> Optional[Tuple[Any, Optional[float]]]:
    """Normalize a video payload into ((T, H, W, C) uint8 array, fps_or_None).

    Accepts: a list of frames (PIL/np), a 4D numpy array, or raw container
    bytes. fps is returned when it can be inferred from the container; None
    otherwise (the caller may then supply an explicit fps). Returns None if
    the payload cannot be decoded at all.
    """
    try:
        import numpy as np
    except Exception:
        return None

    # Already a 4D array (T, H, W, C)
    if isinstance(payload, np.ndarray):
        return (payload, None) if payload.ndim == 4 else None

    # A list/tuple of frames (PIL images or arrays)
    if isinstance(payload, (list, tuple)) and payload:
        frames = []
        for fr in payload:
            pil = _bytes_to_pil(fr)
            if pil is None:
                if isinstance(fr, np.ndarray):
                    frames.append(fr)
                continue
            frames.append(np.asarray(pil))
        if frames:
            try:
                return (np.stack(frames, axis=0), None)
            except Exception:
                return None
        return None

    # Raw container bytes -> decode frames + real fps via torchvision
    if isinstance(payload, (bytes, bytearray)):
        try:
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                tf.write(bytes(payload))
                path = tf.name
            try:
                from torchvision import io as tvio

                vframes, _, info = tvio.read_video(path, pts_unit="sec")
                arr = vframes.numpy()
                # A garbage/undecodable container can yield 0 frames; treat that
                # as undecodable rather than passing an empty "video" downstream.
                if arr.shape[0] == 0:
                    logger.warning("video decoded to 0 frames; treating as undecodable")
                    return None
                fps = info.get("video_fps") if isinstance(info, dict) else None
                return (arr, fps)
            except Exception as e:
                logger.warning("could not decode video bytes: %s", e)
                return None
        except Exception as e:
            logger.warning("video temp write failed: %s", e)
            return None

    return None


def _decode_audio(payload: Any, sampling_rate: Optional[int]) -> Optional[Tuple[Any, int]]:
    """Decode an audio payload to (mono float32 waveform, sampling_rate).

    Accepts a numpy waveform (used as-is), a (waveform, sr) tuple, or raw
    container bytes (wav via stdlib; mp3/flac/ogg via soundfile/torchaudio if
    present). Returns None if it cannot be decoded.
    """
    try:
        import numpy as np
    except Exception:
        return None

    # numpy waveform already
    if isinstance(payload, np.ndarray):
        wav = payload.astype("float32")
        if wav.ndim > 1:  # downmix to mono
            wav = wav.mean(axis=-1)
        return wav, int(sampling_rate or 16000)

    # (waveform, sr) tuple
    if isinstance(payload, tuple) and len(payload) == 2:
        return _decode_audio(payload[0], payload[1])

    # raw container bytes
    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
        # stdlib WAV (no ffmpeg needed). Reuse the package WAV decoder, which
        # correctly handles 8-bit (unsigned) / 16-bit / 32-bit PCM + downmix.
        try:
            import io as _io
            import os as _os
            import tempfile as _tf

            from strands_transformers.core.io import decode_wav as _decode_wav

            with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as _f:
                _f.write(data)
                _wp = _f.name
            try:
                decoded = _decode_wav(_wp)
            finally:
                _os.unlink(_wp)
            if decoded is not None:
                return decoded  # (mono float32 wav, sr)
        except Exception:
            pass
        # soundfile fallback (mp3/flac/ogg)
        try:
            import io as _io

            import soundfile as sf

            wav, sr = sf.read(_io.BytesIO(data), dtype="float32")
            if getattr(wav, "ndim", 1) > 1:
                wav = wav.mean(axis=1)
            return wav, sr
        except Exception as e:
            logger.warning("could not decode audio bytes: %s", e)
            return None

    # path string
    if isinstance(payload, str):
        try:
            import soundfile as sf

            wav, sr = sf.read(payload, dtype="float32")
            if getattr(wav, "ndim", 1) > 1:
                wav = wav.mean(axis=1)
            return wav, sr
        except Exception as e:
            logger.warning("could not read audio path %s: %s", payload, e)
            return None

    return None


def _document_to_text(doc: Dict[str, Any]) -> str:
    """Flatten a Strands DocumentContent block into plain text for the prompt."""
    name = doc.get("name", "document")
    fmt = doc.get("format", "txt")
    source = doc.get("source", {}) or {}
    raw = source.get("bytes") if isinstance(source, dict) else None

    # Text-y formats decode as UTF-8; binary formats (pdf/docx/xls/...) can't be
    # meaningfully flattened to text here, so emit a clear placeholder rather
    # than feeding mojibake to the model.
    _TEXT_FORMATS = {"txt", "md", "csv", "json", "html", "xml", "yaml", "yml", "tsv", "log"}
    text_body = ""
    if isinstance(raw, (bytes, bytearray)):
        data = bytes(raw)
        decoded = None
        if str(fmt).lower() in _TEXT_FORMATS:
            try:
                decoded = data.decode("utf-8")
            except UnicodeDecodeError:
                decoded = None
        else:
            # Unknown/binary format: only accept it if it's actually valid UTF-8.
            try:
                decoded = data.decode("utf-8")
            except UnicodeDecodeError:
                decoded = None
        text_body = (
            decoded
            if decoded is not None
            else (f"<{len(data)} bytes of binary {fmt} document; not decodable as text>")
        )
    elif isinstance(raw, str):
        text_body = raw
    elif isinstance(source, list):
        # DocumentSource may be a list of {text: ...} blocks
        text_body = "\n".join(b.get("text", "") for b in source if isinstance(b, dict))

    header = f"[Document: {name} ({fmt})]"
    return f"{header}\n{text_body}".strip()


T = TypeVar("T", bound=BaseModel)


class TransformerModel(Model):
    """HuggingFace Transformers model provider implementation.

    Loads models directly from HuggingFace transformers without requiring
    external servers or format conversion. Ideal for fine-tuned models with
    merged LoRA weights.

    Supports BOTH:
    - text-only causal LMs (AutoModelForCausalLM + AutoTokenizer)
    - multimodal vision-language models (AutoModelForImageTextToText +
      AutoProcessor) that consume image / video / document content blocks.

    The implementation handles:
    - Local model loading with device management
    - Automatic multimodal detection (processor with an image_processor)
    - Streaming responses with TextIteratorStreamer
    - Tool/function calling
    - Qwen3 thinking mode
    - Chat template formatting (tokenizer OR processor)
    - image / video / document content blocks, including media returned
      inside a toolResult

    Example:
        Text-only:
        >>> model = TransformerModel(model_path="Qwen/Qwen3-0.6B")

        Vision-language (multimodal auto-detected):
        >>> model = TransformerModel(model_path="HuggingFaceTB/SmolVLM-256M-Instruct")
        >>> # now an Agent(model=model) can be passed image content blocks
    """

    class TransformerConfig(TypedDict, total=False):
        """Configuration options for HuggingFace Transformers models.

        Attributes:
            model_path: Path to model directory or HuggingFace model ID.
            device: Device to use ("cpu", "cuda", "mps", or "auto").
                Default is "auto" which selects cuda if available, else cpu.
            params: Model parameters for generation:
                - max_tokens: Maximum number of tokens to generate
                - temperature: Sampling temperature (0.0 to 2.0)
                - top_p: Nucleus sampling parameter (0.0 to 1.0)
                - top_k: Top-k sampling (default: 20)
                - do_sample: Whether to use sampling (default: True)
                - repetition_penalty: Penalize repeat tokens (default: 1.0)
            enable_thinking: Enable Qwen3 thinking mode (default: True)
            trust_remote_code: Trust remote code when loading model (default: True)
            low_cpu_mem_usage: Use low CPU memory mode (default: False)
            multimodal: Force-enable/disable multimodal processor path.
                Default: auto-detected from the loaded processor.
        """

        model_path: str
        device: Optional[str]
        params: Optional[Dict[str, Any]]
        enable_thinking: bool
        trust_remote_code: bool
        low_cpu_mem_usage: bool
        multimodal: Optional[bool]
        video_fps: Optional[float]
        speak: Optional[bool]
        speaker: Optional[str]

    def __init__(
        self,
        model_path: str,
        device: Optional[str] = None,
        **model_config: Unpack[TransformerConfig],
    ) -> None:
        """Initialize transformers provider instance.

        Args:
            model_path: Path to model directory or HuggingFace model ID.
            device: Device to use ("cpu", "cuda", "mps", or "auto").
            **model_config: Configuration options for the transformers model.
        """
        validate_config_keys(model_config, self.TransformerConfig)

        # Set defaults
        if "model_path" not in model_config:
            model_config["model_path"] = model_path
        if "device" not in model_config:
            model_config["device"] = device or "auto"
        if "enable_thinking" not in model_config:
            model_config["enable_thinking"] = True
        if "trust_remote_code" not in model_config:
            model_config["trust_remote_code"] = True
        if "low_cpu_mem_usage" not in model_config:
            model_config["low_cpu_mem_usage"] = False

        self.config = dict(model_config)
        logger.debug("config=<%s> | initializing", self.config)

        # Determine device
        device_config = self.config["device"]
        if device_config == "auto":
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device_config

        logger.debug("device=<%s> | selected", self.device)

        # Multimodal state (resolved during load)
        self.processor = None
        self.is_multimodal = False
        self.has_audio_input = False

        # Load model and tokenizer/processor
        self._load_model()

    def _load_model(self) -> None:
        """Load model and tokenizer (and processor, if multimodal) from path."""
        model_path = self.config["model_path"]
        trust = self.config["trust_remote_code"]
        logger.debug("model_path=<%s> | loading", model_path)

        force_mm = self.config.get("multimodal")

        # ── Try the multimodal (processor) path first, unless explicitly disabled ──
        processor = None
        if force_mm is not False:
            try:
                from transformers import AutoProcessor

                processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=trust)
                # A genuine multimodal processor exposes an image_processor
                # (vision) or a feature_extractor (audio: Qwen2-Audio / Omni).
                has_image = getattr(processor, "image_processor", None) is not None
                has_audio = getattr(processor, "feature_extractor", None) is not None
                if force_mm or has_image or has_audio:
                    self.is_multimodal = True
                    self.has_audio_input = has_audio
            except Exception as e:
                logger.debug("AutoProcessor unavailable for %s: %s", model_path, e)
                processor = None
                # If the processor failed to load but the model's config is a
                # vision/multimodal architecture, don't silently degrade to the
                # text-only path (which then crashes cryptically in
                # AutoModelForCausalLM). Surface a clear, actionable error.
                if force_mm is not False:
                    try:
                        from transformers import AutoConfig

                        _cfg = AutoConfig.from_pretrained(model_path, trust_remote_code=trust)
                        _mt = str(getattr(_cfg, "model_type", "")).lower()
                        _archs = " ".join(getattr(_cfg, "architectures", None) or []).lower()
                        _looks_mm = any(
                            tok in (_mt + " " + _archs)
                            for tok in (
                                "vl",
                                "vision",
                                "image",
                                "idefics",
                                "smolvlm",
                                "llava",
                                "qwen2audio",
                                "qwen2_audio",
                                "omni",
                                "paligemma",
                                "molmo",
                                "blip",
                                "vit",
                            )
                        )
                        _msg = str(e).lower()
                        if _looks_mm and ("image processor" in _msg or "torchvision" in _msg):
                            raise RuntimeError(
                                f"'{model_path}' is a multimodal model but its processor "
                                f"could not be loaded ({e}). Install the vision deps: "
                                f"pip install 'strands-transformers[vision]'  (or: pip install torchvision)"
                            ) from e
                    except RuntimeError:
                        raise
                    except Exception:
                        pass

        if self.is_multimodal and processor is not None:
            self.processor = processor
            # Tokenizer lives on the processor for chat templating / counting
            self.tokenizer = getattr(processor, "tokenizer", None)
            if self.tokenizer is None:
                self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=trust)

            model_kwargs: Dict[str, Any] = {
                "trust_remote_code": trust,
                "low_cpu_mem_usage": self.config["low_cpu_mem_usage"],
            }
            if self.device == "cuda":
                model_kwargs["dtype"] = torch.bfloat16
                model_kwargs["device_map"] = "cuda"

            # Pick model class. Detect specific omni/audio architectures from the
            # config first (they need their own classes, not the generic vision
            # ones), then audio-only, then vision.
            self.model = None
            has_image = getattr(self.processor, "image_processor", None) is not None
            arch = ""
            try:
                from transformers import AutoConfig

                _cfg = AutoConfig.from_pretrained(model_path, trust_remote_code=trust)
                archs = getattr(_cfg, "architectures", None) or []
                arch = archs[0] if archs else getattr(_cfg, "model_type", "")
            except Exception:
                arch = ""
            arch_l = (arch or "").lower()

            if "omni" in arch_l:
                cls_candidates = (
                    "Qwen2_5OmniForConditionalGeneration",
                    "AutoModelForCausalLM",
                )
            elif (
                "qwen2audio" in arch_l
                or "qwen2_audio" in arch_l
                or (getattr(self, "has_audio_input", False) and not has_image)
            ):
                cls_candidates = (
                    "Qwen2AudioForConditionalGeneration",
                    "AutoModelForCausalLM",
                )
            else:
                cls_candidates = (
                    "AutoModelForImageTextToText",
                    "AutoModelForVision2Seq",
                )
            last_err = None
            for cls_name in cls_candidates:
                try:
                    import transformers as _tf

                    ModelCls = getattr(_tf, cls_name, None)
                    if ModelCls is None:
                        continue
                    self.model = ModelCls.from_pretrained(model_path, **model_kwargs)
                    logger.debug("loaded multimodal model via %s", cls_name)
                    break
                except Exception as e:
                    last_err = e
                    logger.debug("%s failed for %s: %s", cls_name, model_path, e)
                    continue

            if self.model is None:
                # Last resort: AutoModel. If even this fails, raise a clear,
                # actionable error instead of a cryptic deep-stack trace - the
                # usual cause is a missing extra (accelerate for device_map,
                # torchvision for vision processors).
                try:
                    from transformers import AutoModel

                    self.model = AutoModel.from_pretrained(model_path, **model_kwargs)
                except Exception as e:
                    err = last_err or e
                    hint = ""
                    msg = str(err).lower()
                    if "accelerate" in msg:
                        hint = " - install the missing extra: pip install accelerate"
                    elif "image processor" in msg or "torchvision" in msg:
                        hint = " - install vision deps: pip install torchvision"
                    raise RuntimeError(
                        f"Could not load multimodal model '{model_path}' "
                        f"(tried {', '.join(cls_candidates)}, AutoModel): {err}{hint}"
                    ) from err

            if self.device == "cuda" and "device_map" not in model_kwargs:
                self.model = self.model.to(self.device)

            logger.debug("multimodal model loaded successfully")
        else:
            # ── Text-only path (unchanged behaviour) ──
            self.is_multimodal = False
            self.processor = None
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=trust)

            model_kwargs = {
                "trust_remote_code": trust,
                "low_cpu_mem_usage": self.config["low_cpu_mem_usage"],
            }
            if self.device == "cuda":
                model_kwargs["dtype"] = torch.bfloat16

            self.model = AutoModelForCausalLM.from_pretrained(model_path, **model_kwargs)
            if self.device == "cuda":
                self.model = self.model.to(self.device)

            logger.debug("text model loaded successfully")

        # Set padding token
        if self.tokenizer is not None and self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Detect Qwen3 for thinking mode
        # Detect Qwen2.5-Omni: non-standard generate (returns (text, audio),
        # uses thinker_/talker_ kwargs, can emit speech). Needs its own path.
        self.is_omni = type(self.model).__name__.startswith("Qwen2_5Omni")
        # Speech-out config (only meaningful for Omni). Off by default so the
        # text streaming path stays fast; enable via config "speak": True.
        self.last_audio = None

        self.is_qwen3 = "qwen3" in model_path.lower() or (
            hasattr(self.model, "config")
            and getattr(self.model.config, "model_type", "") == "qwen3"
        )

    @override
    def update_config(self, **model_config: Unpack[TransformerConfig]) -> None:  # type: ignore[override]
        """Update the transformers model configuration with provided arguments."""
        validate_config_keys(model_config, self.TransformerConfig)

        if "model_path" in model_config and model_config["model_path"] != self.config.get(
            "model_path"
        ):
            self.config.update(model_config)
            self._load_model()
        else:
            self.config.update(model_config)

    @override
    def get_config(self) -> TransformerConfig:
        """Get the transformers model configuration."""
        return self.config  # type: ignore[return-value]

    # ──────────────────────────────────────────────────────────────────────
    # Multimodal content-block handling
    # ──────────────────────────────────────────────────────────────────────

    def _content_to_processor_parts(
        self, content: Union[ContentBlock, Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Any], List[Any], List[Any]]:
        """Convert a single Strands content block into processor chat parts.

        Returns (parts, images, videos, audios) where ``parts`` are the
        chat-template entries (e.g. {"type": "text"|"image"|"video"|"audio"})
        and the media lists hold decoded objects collected in order.

        Supports the full multimodal taxonomy plus our audio extension: text,
        image, video, audio, document, toolUse, and toolResult (whose content
        may itself carry image/video/audio).
        """
        parts: List[Dict[str, Any]] = []
        images: List[Any] = []
        videos: List[Any] = []
        audios: List[Any] = []

        # text
        if "text" in content:
            parts.append({"type": "text", "text": content["text"]})
            return parts, images, videos, audios

        # image (Strands ImageContent: {"format","source":{"bytes"}}; also tolerate
        # bare PIL/bytes or the run-path {"image": <PIL>})
        if "image" in content:
            img = content["image"]
            payload = img
            if isinstance(img, dict):
                src = img.get("source", img)
                payload = src.get("bytes", src) if isinstance(src, dict) else src
            pil = _bytes_to_pil(payload)
            if pil is not None:
                images.append(pil)
                parts.append({"type": "image"})
            else:
                parts.append({"type": "text", "text": "[unrenderable image]"})
            return parts, images, videos, audios

        # audio (our extension: {"audio": {"format","source":{"bytes","sampling_rate"}}})
        if "audio" in content:
            from strands_transformers.types.audio import extract_audio_payload

            payload, sr = extract_audio_payload(content)
            decoded = _decode_audio(payload, sr)
            if decoded is not None:
                audios.append(decoded)
                # Include both keys: 'type' (SmolVLM/Omni-style templates) and
                # 'audio_url' (Qwen2-Audio template triggers on this key).
                parts.append({"type": "audio", "audio_url": "audio"})
            else:
                parts.append({"type": "text", "text": "[unrenderable audio]"})
            return parts, images, videos, audios

        # video
        if "video" in content:
            vid = content["video"]
            explicit_fps = vid.get("fps") if isinstance(vid, dict) else None
            src = vid.get("source", vid) if isinstance(vid, dict) else vid
            payload = src.get("bytes", src) if isinstance(src, dict) else src
            norm = _normalize_video(payload)
            if norm is not None:
                arr, fps = norm
                videos.append((arr, explicit_fps if explicit_fps is not None else fps))
                parts.append({"type": "video"})
            else:
                parts.append({"type": "text", "text": "[unrenderable video]"})
            return parts, images, videos, audios

        # document -> flatten to text
        if "document" in content:
            parts.append({"type": "text", "text": _document_to_text(content["document"])})
            return parts, images, videos, audios

        # toolUse -> compact text marker
        if "toolUse" in content:
            tu = content["toolUse"]
            parts.append(
                {
                    "type": "text",
                    "text": "<tool_call>"
                    + json.dumps({"name": tu.get("name"), "arguments": tu.get("input")})
                    + "</tool_call>",
                }
            )
            return parts, images, videos, audios

        # toolResult -> fold text/json as text, and pull media into the turn
        if "toolResult" in content:
            tr = content["toolResult"]
            for c in tr.get("content", []):
                if "json" in c:
                    parts.append({"type": "text", "text": json.dumps(c["json"])})
                elif "text" in c:
                    parts.append({"type": "text", "text": c["text"]})
                elif "image" in c:
                    img = c["image"]
                    src = img.get("source", img) if isinstance(img, dict) else img
                    payload = src.get("bytes", src) if isinstance(src, dict) else src
                    pil = _bytes_to_pil(payload)
                    if pil is not None:
                        images.append(pil)
                        parts.append({"type": "image"})
                elif "video" in c:
                    vid = c["video"]
                    explicit_fps = vid.get("fps") if isinstance(vid, dict) else None
                    src = vid.get("source", vid) if isinstance(vid, dict) else vid
                    vpayload = src.get("bytes", src) if isinstance(src, dict) else src
                    vnorm = _normalize_video(vpayload)
                    if vnorm is not None:
                        arr, fps = vnorm
                        videos.append((arr, explicit_fps if explicit_fps is not None else fps))
                        parts.append({"type": "video"})
                elif "audio" in c:
                    from strands_transformers.types.audio import extract_audio_payload

                    apayload, asr = extract_audio_payload(c)
                    adec = _decode_audio(apayload, asr)
                    if adec is not None:
                        audios.append(adec)
                        parts.append({"type": "audio", "audio_url": "audio"})
            if not parts:
                parts.append({"type": "text", "text": "[empty tool result]"})
            return parts, images, videos, audios

        # unknown -> stringify
        parts.append({"type": "text", "text": str(content)})
        return parts, images, videos, audios

    def _build_multimodal_chat(
        self,
        messages: Messages,
        system_prompt: Optional[str],
        tool_specs: Optional[list[ToolSpec]],
    ) -> Tuple[List[Dict[str, Any]], List[Any], List[Any], List[Any]]:
        """Build processor chat messages + ordered media lists."""
        chat: List[Dict[str, Any]] = []
        images: List[Any] = []
        videos: List[Any] = []
        audios: List[Any] = []

        sys_text = system_prompt or ""
        if tool_specs:
            sys_text += self._tool_specs_to_text(tool_specs)
        if sys_text:
            chat.append({"role": "system", "content": [{"type": "text", "text": sys_text}]})

        for message in messages:
            role = message["role"]
            parts: List[Dict[str, Any]] = []
            for content in message["content"]:
                p, imgs, vids, auds = self._content_to_processor_parts(content)
                parts.extend(p)
                images.extend(imgs)
                videos.extend(vids)
                audios.extend(auds)
            if parts:
                chat.append({"role": role, "content": parts})

        return chat, images, videos, audios

    @staticmethod
    def _tool_specs_to_text(tool_specs: list[ToolSpec]) -> str:
        desc = "\n\n# Available Tools\n\nYou have access to the following tools:\n\n"
        for spec in tool_specs:
            desc += f"## {spec['name']}\n{spec['description']}\n\n"
            desc += f"Parameters: {json.dumps(spec['inputSchema']['json'], indent=2)}\n\n"
        desc += (
            "\nTo use a tool, output:\n"
            '<tool_call>{"name": "tool_name", "arguments": {"param": "value"}}</tool_call>\n\n'
            "You will receive the result in:\n"
            "<tool_response>result</tool_response>\n"
        )
        return desc

    def _to_model_device(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Move tensors to the model device and cast float tensors to model dtype."""
        target_dtype = getattr(self.model, "dtype", None)
        out: Dict[str, Any] = {}
        for k, v in inputs.items():
            if hasattr(v, "to"):
                v = v.to(self.model.device)
                if (
                    target_dtype is not None
                    and getattr(v, "is_floating_point", None)
                    and v.is_floating_point()
                ):
                    v = v.to(target_dtype)
            out[k] = v
        return out

    @staticmethod
    def _resample(wav, src_sr: int, dst_sr: int):
        """Linear-interp resample of a mono waveform (no scipy dependency)."""
        try:
            import numpy as np
        except Exception:
            return wav
        if not src_sr or src_sr == dst_sr:
            return wav
        wav = np.asarray(wav, dtype="float32")
        n_dst = int(round(len(wav) * float(dst_sr) / float(src_sr)))
        if n_dst <= 1 or len(wav) <= 1:
            return wav
        x_old = np.linspace(0.0, 1.0, num=len(wav), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
        return np.interp(x_new, x_old, wav).astype("float32")

    def _build_video_metadata(self, videos: List[Tuple[Any, Optional[float]]]):
        """Build per-video VideoMetadata so the processor gets real timestamps.

        Returns None if VideoMetadata is unavailable in this transformers
        version (the processor then falls back to its own default).
        """
        try:
            from transformers.video_utils import VideoMetadata
        except Exception:
            return None

        default_fps = float(self.config.get("video_fps", 24.0))
        meta = []
        for arr, fps in videos:
            try:
                n = int(arr.shape[0])
                h = int(arr.shape[1])
                w = int(arr.shape[2])
            except Exception:
                n, h, w = 0, 0, 0
            use_fps = float(fps) if fps else default_fps
            duration = (n / use_fps) if use_fps else float(n)
            meta.append(
                VideoMetadata(
                    total_num_frames=n,
                    fps=use_fps,
                    width=w,
                    height=h,
                    duration=duration,
                    video_backend="manual",
                    frames_indices=list(range(n)),
                )
            )
        return meta

    def _prepare_multimodal_inputs(
        self,
        messages: Messages,
        system_prompt: Optional[str],
        tool_specs: Optional[list[ToolSpec]],
    ) -> Tuple[Dict[str, Any], int]:
        """Tokenize via the processor; returns (model_inputs, input_token_length)."""
        chat, images, videos, audios = self._build_multimodal_chat(
            messages, system_prompt, tool_specs
        )

        prompt = self.processor.apply_chat_template(
            chat, tokenize=False, add_generation_prompt=True
        )

        proc_kwargs: Dict[str, Any] = {"text": prompt, "return_tensors": "pt"}
        if images:
            proc_kwargs["images"] = images
        if audios:
            # audios is a list of (waveform float32, sr) tuples. Resample to the
            # processor feature_extractor rate and pass raw waveforms.
            target_sr = getattr(
                getattr(self.processor, "feature_extractor", None),
                "sampling_rate",
                16000,
            )
            waves = [self._resample(w, sr, target_sr) for (w, sr) in audios]
            proc_kwargs["audio"] = waves
            proc_kwargs["sampling_rate"] = target_sr
        if videos:
            # videos is a list of (array(T,H,W,C), fps_or_None) tuples.
            arrays = [v[0] for v in videos]
            # Processors expect videos nested per batch sample:
            # [sample][video] where each video is a (T, H, W, C) array.
            proc_kwargs["videos"] = [arrays]
            # Provide real frame timestamps when the processor supports it
            # (e.g. SmolVLM), so it doesn't default to fps=24 with a warning.
            metadata = self._build_video_metadata(videos)
            if metadata is not None:
                proc_kwargs["video_metadata"] = [metadata]

        inputs = self.processor(**proc_kwargs)
        inputs = dict(inputs)  # BatchFeature -> plain dict
        inputs = self._to_model_device(inputs)

        input_length = inputs["input_ids"].shape[1] if "input_ids" in inputs else 0
        return inputs, input_length

    # ──────────────────────────────────────────────────────────────────────
    # Text-only formatting (unchanged)
    # ──────────────────────────────────────────────────────────────────────

    def _format_message_content(
        self, content: Union[ContentBlock, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Format a content block for transformers (legacy helper)."""
        if "text" in content:
            return {"type": "text", "text": content["text"]}
        if "image" in content:
            return {"type": "image", "image": content["image"]["source"]["bytes"]}
        if "toolUse" in content:
            return {
                "type": "tool_use",
                "name": content["toolUse"]["name"],
                "input": content["toolUse"]["input"],
                "id": content["toolUse"]["toolUseId"],
            }
        if "toolResult" in content:
            return {
                "type": "tool_result",
                "tool_use_id": content["toolResult"]["toolUseId"],
                "content": [
                    {"text": json.dumps(c["json"])} if "json" in c else c
                    for c in content["toolResult"]["content"]
                ],
            }
        raise TypeError(f"content_type=<{next(iter(content))}> | unsupported type")

    def _format_messages(
        self,
        messages: Messages,
        system_prompt: Optional[str] = None,
        tool_specs: Optional[list[ToolSpec]] = None,
    ) -> str:
        """Format messages for transformers using chat template (text path)."""
        chat_messages = []
        system_content = system_prompt or ""

        if tool_specs:
            system_content += self._tool_specs_to_text(tool_specs)

        if system_content:
            chat_messages.append({"role": "system", "content": system_content})

        for message in messages:
            role = message["role"]
            contents = message["content"]

            text_parts = []
            tool_uses = []
            tool_results = []

            for content in contents:
                if "text" in content:
                    text_parts.append(content["text"])
                elif "toolUse" in content:
                    tool_uses.append(content["toolUse"])
                elif "toolResult" in content:
                    tool_results.append(content["toolResult"])
                elif "document" in content:
                    text_parts.append(_document_to_text(content["document"]))

            if text_parts:
                chat_messages.append({"role": role, "content": " ".join(text_parts)})

            if tool_uses:
                for tool_use in tool_uses:
                    tool_text = f"<tool_call>{json.dumps({'name': tool_use['name'], 'arguments': tool_use['input']})}</tool_call>"
                    chat_messages.append({"role": "assistant", "content": tool_text})

            if tool_results:
                for tool_result in tool_results:
                    result_content = " ".join(
                        [
                            (json.dumps(c["json"]) if "json" in c else c.get("text", str(c)))
                            for c in tool_result["content"]
                        ]
                    )
                    result_text = f"<tool_response>{result_content}</tool_response>"
                    chat_messages.append({"role": "user", "content": result_text})

        if self.is_qwen3 and self.config.get("enable_thinking", True):
            formatted_prompt = self.tokenizer.apply_chat_template(
                chat_messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=True,
            )
        else:
            formatted_prompt = self.tokenizer.apply_chat_template(
                chat_messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        return formatted_prompt

    def _format_chunk(self, event: Dict[str, Any]) -> StreamEvent:
        """Format a generation event into a standardized message chunk."""
        match event["chunk_type"]:
            case "message_start":
                return {"messageStart": {"role": "assistant"}}

            case "content_start":
                if event.get("data_type") == "tool":
                    tool_name = event.get("tool_name", "unknown")
                    tool_use_id = event.get("tool_use_id", tool_name)
                    return {
                        "contentBlockStart": {
                            "start": {
                                "toolUse": {
                                    "name": tool_name,
                                    "toolUseId": tool_use_id,
                                }
                            }
                        }
                    }
                return {"contentBlockStart": {"start": {}}}

            case "content_delta":
                if event.get("data_type") == "thinking":
                    return {
                        "contentBlockDelta": {
                            "delta": {"reasoningContent": {"text": event["data"]}}
                        }
                    }
                if event.get("data_type") == "tool":
                    tool_arguments = event.get("tool_arguments", {})
                    return {
                        "contentBlockDelta": {
                            "delta": {"toolUse": {"input": json.dumps(tool_arguments)}}
                        }
                    }
                return {"contentBlockDelta": {"delta": {"text": event["data"]}}}

            case "content_stop":
                return {"contentBlockStop": {}}

            case "message_stop":
                return {"messageStop": {"stopReason": event.get("reason", "end_turn")}}

            case "metadata":
                return {
                    "metadata": {
                        "usage": {
                            "inputTokens": event.get("input_tokens", 0),
                            "outputTokens": event.get("output_tokens", 0),
                            "totalTokens": event.get("input_tokens", 0)
                            + event.get("output_tokens", 0),
                        },
                        "metrics": {
                            "latencyMs": event.get("latency_ms", 0),
                        },
                    },
                }

            case _:
                raise RuntimeError(f"chunk_type=<{event['chunk_type']}> | unknown type")

    async def _stream_omni(self, model_inputs, input_length, start_time):
        """Dedicated streaming path for Qwen2.5-Omni.

        Omni's generate() is non-standard: it returns (text_ids, audio_waveform)
        and uses thinker_/talker_ kwargs instead of max_new_tokens. It can also
        synthesize speech via its Talker. We run generate in a worker thread,
        decode the newly generated text, emit it as a content delta, and stash
        any speech waveform on ``self.last_audio`` (a (waveform, sr) tuple).
        """
        import asyncio

        import torch

        params = self.config.get("params", {})
        thinker_max = int(params.get("max_tokens", 256))
        speak = bool(self.config.get("speak", False))
        speaker = self.config.get("speaker", "Chelsie")
        talker_max = int(params.get("talker_max_tokens", 1024)) if speak else 1

        gen_kwargs = dict(model_inputs)
        gen_kwargs.update(
            return_audio=speak,
            thinker_max_new_tokens=thinker_max,
            talker_max_new_tokens=talker_max,
        )
        if speak:
            gen_kwargs["speaker"] = speaker

        result = {}

        def _run():
            try:
                with torch.no_grad():
                    out = self.model.generate(**gen_kwargs)
                result["out"] = out
            except Exception as e:  # surface generation errors to the stream
                result["err"] = e

        thread = Thread(target=_run)
        thread.start()
        while thread.is_alive():
            await asyncio.sleep(0.02)
        thread.join()

        yield self._format_chunk({"chunk_type": "message_start"})
        yield self._format_chunk({"chunk_type": "content_start"})

        if "err" in result:
            err_text = f"[omni generation error: {result['err']}]"
            yield self._format_chunk({"chunk_type": "content_delta", "data": err_text})
            yield self._format_chunk({"chunk_type": "content_stop"})
            yield self._format_chunk({"chunk_type": "message_stop", "reason": "end_turn"})
            return

        out = result["out"]
        audio = None
        if isinstance(out, (tuple, list)):
            text_ids = out[0]
            if len(out) > 1:
                audio = out[1]
        else:
            text_ids = out

        # Decode only the newly generated tokens (strip the prompt).
        seq = text_ids[0] if hasattr(text_ids, "__getitem__") else text_ids
        try:
            new_ids = seq[input_length:]
        except Exception:
            new_ids = seq
        text = self.tokenizer.decode(new_ids, skip_special_tokens=True).strip()
        if not text:
            # fall back to full decode if the slice came back empty
            text = self.tokenizer.decode(seq, skip_special_tokens=True).strip()

        # Stash synthesized speech for retrieval via get_last_audio().
        self.last_audio = None
        if audio is not None:
            try:
                wav = audio.detach().float().cpu().numpy().reshape(-1)
                if wav.size > 0:
                    self.last_audio = (wav, 24000)  # Talker output is 24 kHz
            except Exception as e:
                logger.warning("could not extract omni audio: %s", e)

        if text:
            yield self._format_chunk({"chunk_type": "content_delta", "data": text})
        output_tokens = len(new_ids) if hasattr(new_ids, "__len__") else 0

        yield self._format_chunk({"chunk_type": "content_stop"})
        yield self._format_chunk({"chunk_type": "message_stop", "reason": "end_turn"})

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        yield self._format_chunk(
            {
                "chunk_type": "metadata",
                "input_tokens": input_length,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
            }
        )

    def get_last_audio(self):
        """Return the most recent synthesized speech as (waveform, sr) or None.

        Populated after a generation when the model is Qwen2.5-Omni and
        config ``speak=True``. Lets callers save/play the agent's spoken reply.
        """
        return getattr(self, "last_audio", None)

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        *,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream conversation with the transformers model.

        Routes through the multimodal processor path when the model is a VLM
        and the conversation carries image/video content; otherwise uses the
        text-only tokenizer path.
        """
        warn_on_tool_choice_not_supported(tool_choice)

        start_time = time.perf_counter()

        # Decide path: multimodal model + any media present anywhere.
        # Omni always uses the processor path (its chat template / token layout
        # is required even for text-only turns).
        use_mm = self.is_omni or (self.is_multimodal and self._has_media(messages))

        logger.debug("formatting messages (multimodal=%s)", use_mm)

        if use_mm:
            model_inputs, input_length = self._prepare_multimodal_inputs(
                messages, system_prompt, tool_specs
            )
        else:
            formatted_prompt = self._format_messages(messages, system_prompt, tool_specs)
            logger.debug(
                "prompt=<%s>",
                (
                    formatted_prompt[:200] + "..."
                    if len(formatted_prompt) > 200
                    else formatted_prompt
                ),
            )
            inputs = self.tokenizer([formatted_prompt], return_tensors="pt")
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
            model_inputs = inputs
            input_length = inputs["input_ids"].shape[1]

        # ── Qwen2.5-Omni dedicated path (non-standard generate) ──
        if self.is_omni:
            async for ev in self._stream_omni(model_inputs, input_length, start_time):
                yield ev
            return

        # Generation parameters
        params = self.config.get("params", {})
        max_tokens = params.get("max_tokens", 300)
        temperature = params.get("temperature", 1)
        top_p = params.get("top_p", 0.9)
        top_k = params.get("top_k", 20)
        do_sample = params.get("do_sample", True)
        repetition_penalty = params.get("repetition_penalty", 1.0)

        logger.debug("generating with streaming")

        # Streamer uses the tokenizer (present in both paths)
        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        generation_kwargs = dict(
            max_new_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            do_sample=do_sample,
            repetition_penalty=repetition_penalty,
            pad_token_id=self.tokenizer.eos_token_id,
            streamer=streamer,
        )
        # Feed model inputs (input_ids/attention_mask [+ pixel_values, ...])
        generation_kwargs.update(model_inputs)

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        yield self._format_chunk({"chunk_type": "message_start"})
        yield self._format_chunk({"chunk_type": "content_start"})

        thinking_mode = False
        tool_call_mode = False
        tool_requested = False
        thinking_buffer = ""
        tool_call_buffer = ""
        output_buffer = ""

        for new_text in streamer:
            if "<tool_call>" in new_text:
                tool_call_mode = True
                tool_requested = True
                parts = new_text.split("<tool_call>", 1)
                if parts[0]:
                    yield self._format_chunk({"chunk_type": "content_delta", "data": parts[0]})
                    output_buffer += parts[0]
                yield self._format_chunk({"chunk_type": "content_stop"})
                if len(parts) > 1:
                    tool_call_buffer = parts[1]
                continue

            if tool_call_mode and "</tool_call>" in new_text:
                tool_call_mode = False
                parts = new_text.split("</tool_call>", 1)
                tool_call_buffer += parts[0]
                try:
                    tool_call_data = json.loads(tool_call_buffer)
                    tool_name = tool_call_data.get("name", "unknown")
                    tool_arguments = tool_call_data.get("arguments", {})
                    yield self._format_chunk(
                        {
                            "chunk_type": "content_start",
                            "data_type": "tool",
                            "tool_name": tool_name,
                            "tool_use_id": tool_name,
                        }
                    )
                    yield self._format_chunk(
                        {
                            "chunk_type": "content_delta",
                            "data_type": "tool",
                            "tool_arguments": tool_arguments,
                        }
                    )
                    yield self._format_chunk({"chunk_type": "content_stop", "data_type": "tool"})
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse tool call: {e}, buffer: {tool_call_buffer}")
                tool_call_buffer = ""
                if len(parts) > 1 and parts[1]:
                    yield self._format_chunk({"chunk_type": "content_start"})
                    yield self._format_chunk({"chunk_type": "content_delta", "data": parts[1]})
                    output_buffer += parts[1]
                continue

            if tool_call_mode:
                tool_call_buffer += new_text
                continue

            if self.is_qwen3 and self.config.get("enable_thinking", True):
                if "<think>" in new_text:
                    thinking_mode = True
                    parts = new_text.split("<think>", 1)
                    if parts[0]:
                        yield self._format_chunk({"chunk_type": "content_delta", "data": parts[0]})
                        output_buffer += parts[0]
                    if len(parts) > 1:
                        thinking_buffer = parts[1]
                    continue

                if thinking_mode and "</think>" in new_text:
                    thinking_mode = False
                    parts = new_text.split("</think>", 1)
                    thinking_buffer += parts[0]
                    if thinking_buffer:
                        yield self._format_chunk(
                            {
                                "chunk_type": "content_delta",
                                "data_type": "thinking",
                                "data": thinking_buffer,
                            }
                        )
                    thinking_buffer = ""
                    if len(parts) > 1 and parts[1]:
                        yield self._format_chunk({"chunk_type": "content_delta", "data": parts[1]})
                        output_buffer += parts[1]
                    continue

                if thinking_mode:
                    thinking_buffer += new_text
                    yield self._format_chunk(
                        {
                            "chunk_type": "content_delta",
                            "data_type": "thinking",
                            "data": new_text,
                        }
                    )
                else:
                    output_buffer += new_text
                    yield self._format_chunk({"chunk_type": "content_delta", "data": new_text})
            else:
                output_buffer += new_text
                yield self._format_chunk({"chunk_type": "content_delta", "data": new_text})

        thread.join()

        yield self._format_chunk({"chunk_type": "content_stop"})
        yield self._format_chunk(
            {
                "chunk_type": "message_stop",
                "reason": "tool_use" if tool_requested else "end_turn",
            }
        )

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        output_tokens = len(
            self.tokenizer.encode(output_buffer + thinking_buffer, add_special_tokens=False)
        )

        yield self._format_chunk(
            {
                "chunk_type": "metadata",
                "input_tokens": input_length,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
            }
        )

        logger.debug("finished streaming response from model")

    @staticmethod
    def _has_media(messages: Messages) -> bool:
        """Return True if any message carries image/video/audio (incl. tool results)."""
        for message in messages:
            for content in message.get("content", []):
                if "image" in content or "video" in content or "audio" in content:
                    return True
                if "toolResult" in content:
                    for c in content["toolResult"].get("content", []):
                        if "image" in c or "video" in c or "audio" in c:
                            return True
        return False

    @override
    async def structured_output(
        self,
        output_model: Type[T],
        prompt: Messages,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Dict[str, Union[T, Any]], None]:
        """Get structured output from the model (prompt-engineered JSON)."""
        schema = output_model.model_json_schema()
        json_instruction = f"\n\nPlease respond with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        augmented_system_prompt = (system_prompt or "") + json_instruction

        response_text = ""
        reasoning_text = ""
        async for event in self.stream(prompt, system_prompt=augmented_system_prompt, **kwargs):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    response_text += delta["text"]
                elif "reasoningContent" in delta:
                    # Thinking models (Qwen3) may emit JSON inside an (even
                    # unterminated) <think> block; keep it as a fallback source.
                    reasoning_text += delta["reasoningContent"].get("text", "")
            yield cast(Dict[str, Union[T, Any]], event)

        # Try the visible answer first, then fall back to reasoning content.
        for candidate in (response_text, response_text + "\n" + reasoning_text):
            try:
                data = json.loads(_extract_json(candidate))
                yield {"output": output_model(**data)}
                return
            except Exception:
                continue

        raise ValueError(
            "Failed to parse structured output. The model did not emit valid JSON "
            f"matching {output_model.__name__}. Try increasing max_tokens or "
            f"disabling thinking mode.\nResponse: {(response_text or reasoning_text)[:1000]}"
        )
