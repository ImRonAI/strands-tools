# pyright: strict
"""Universal 2D bounding-box object detection and identification tool.

Supports on-demand (`action="detect"`) and continuous background (`action="start"`)
object detection and identification across mobile, tablet, and laptop image/camera
sources. Uses native Google Gemini 2D bounding-box detection (`box_2d` normalized
`[ymin, xmin, ymax, xmax]` in `0..1000` + pixel `[x1, y1, x2, y2]`) via the
Gemini Interactions API by default, with optional local `ultralytics` YOLO `.pt`
model support when installed.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, TypeVar, cast

import google.genai as genai
from google.genai import errors as genai_errors
from google.genai._gaos.lib import compat_errors
import httpx
from PIL import Image, ImageDraw, ImageOps
import strands

_ToolFuncT = TypeVar("_ToolFuncT", bound=Callable[..., Any])


def tool(func: _ToolFuncT) -> _ToolFuncT:
    """Typed wrapper around `strands.tool`."""
    decorator = cast(Callable[[_ToolFuncT], _ToolFuncT], getattr(strands, "tool"))
    return decorator(func)

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_FALLBACK_CHAIN: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-4-argon",
    "gemini-3.5-flash-lite",
)

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
)

_BBOX_PALETTE: tuple[tuple[int, int, int], ...] = (
    (0, 200, 100),
    (255, 99, 71),
    (30, 144, 255),
    (255, 165, 0),
    (186, 85, 211),
    (0, 206, 209),
    (255, 20, 147),
    (50, 205, 50),
)

_DETECTION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "description": "Specific name or category of the detected object.",
            },
            "box_2d": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "2D bounding box [ymin, xmin, ymax, xmax] normalized to 0..1000.",
            },
            "confidence": {
                "type": "number",
                "description": "Detection confidence score between 0.0 and 1.0.",
            },
        },
        "required": ["label", "box_2d", "confidence"],
    },
}

# Global state for detection history and background worker
_detection_thread: threading.Thread | None = None
_detection_active: bool = False
_detection_lock = threading.Lock()
_detections_history: list[dict[str, Any]] = []
_object_counts: defaultdict[str, int] = defaultdict(int)


def _count_sort_key(item: tuple[str, int]) -> int:
    """Sort `(object_label, count)` pairs by count."""
    return item[1]


def _is_capacity_error(exc: Exception) -> bool:
    """Return True if an exception indicates Gemini rate-limit, quota, or capacity exhaustion."""
    if isinstance(exc, compat_errors.RateLimitError):
        return True
    if isinstance(exc, compat_errors.APIStatusError):
        status_code = getattr(exc, "status_code", None)
        if status_code in (429, 503):
            return True
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if code in (429, 503):
            return True
    msg = str(exc).lower()
    return any(keyword in msg for keyword in _CAPACITY_KEYWORDS)


def _get_genai_client() -> genai.Client:
    """Create a `google.genai.Client` using `GEMINI_API_KEY` or `GOOGLE_API_KEY` from the environment."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client()


def _capture_camera_bytes(camera_id: int, save_path: Path) -> bytes:
    """Capture a single JPEG frame from `camera_id` using lazy `cv2` or `ffmpeg`."""
    try:
        cv2_mod: Any = importlib.import_module("cv2")
        cam: Any = cv2_mod.VideoCapture(camera_id)
        try:
            if cam.isOpened():
                ret, frame = cam.read()
                if ret and frame is not None:
                    ok, buffer = cv2_mod.imencode(".jpg", frame)
                    if ok:
                        return bytes(buffer.tobytes())
        finally:
            cam.release()
    except ImportError:
        pass

    tmp_frame = save_path / f"_camera_{camera_id}_{int(time.time() * 1000)}.jpg"
    try:
        if sys.platform == "darwin":
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "avfoundation",
                "-framerate",
                "30",
                "-i",
                str(camera_id),
                "-frames:v",
                "1",
                str(tmp_frame),
            ]
        elif sys.platform.startswith("linux"):
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "v4l2",
                "-i",
                f"/dev/video{camera_id}",
                "-frames:v",
                "1",
                str(tmp_frame),
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "dshow",
                "-i",
                f"video={camera_id}",
                "-frames:v",
                "1",
                str(tmp_frame),
            ]
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=15,
        )
        if tmp_frame.exists():
            return tmp_frame.read_bytes()
    except Exception as exc:
        raise RuntimeError(
            f"Could not capture frame from camera {camera_id} (provide image_path, image_url, or image_base64, "
            f"or ensure a camera and opencv-python/ffmpeg are available): {exc}"
        ) from exc
    finally:
        if tmp_frame.exists():
            try:
                tmp_frame.unlink()
            except OSError:
                pass

    raise RuntimeError(f"Camera {camera_id} produced no image frame.")


def _load_image(
    *,
    image_path: str | None,
    image_url: str | None,
    image_base64: str | None,
    camera_id: int,
    save_path: Path,
) -> tuple[Image.Image, bytes, str]:
    """Load and normalize an image from path, URL, base64/data-URI, or camera into an upright RGB `PIL.Image`."""
    raw_bytes: bytes
    source_desc: str

    if image_path:
        resolved = Path(image_path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Image file not found: {resolved}")
        raw_bytes = resolved.read_bytes()
        source_desc = str(resolved)
    elif image_url:
        with httpx.Client(follow_redirects=True, timeout=30.0) as http_client:
            response = http_client.get(image_url)
            response.raise_for_status()
            raw_bytes = response.content
        source_desc = image_url
    elif image_base64:
        cleaned = image_base64.strip()
        if cleaned.startswith("data:") and "," in cleaned:
            cleaned = cleaned.split(",", 1)[1].strip()
        raw_bytes = base64.b64decode(cleaned)
        source_desc = "base64_input"
    else:
        raw_bytes = _capture_camera_bytes(camera_id, save_path)
        source_desc = f"camera:{camera_id}"

    with Image.open(io.BytesIO(raw_bytes)) as opened_img:
        transposed = ImageOps.exif_transpose(opened_img)
        rgb_img = transposed.convert("RGB")

    jpeg_buf = io.BytesIO()
    rgb_img.save(jpeg_buf, format="JPEG", quality=92)
    return rgb_img, jpeg_buf.getvalue(), source_desc


def _build_detection_prompt(
    prompt: str | None,
    target_objects: Sequence[str] | None,
    confidence: float,
) -> str:
    """Build the Gemini 2D bounding-box detection prompt."""
    cleaned_targets = [t.strip() for t in (target_objects or []) if t and t.strip()]
    if prompt and prompt.strip():
        focus_instruction = prompt.strip()
    elif cleaned_targets:
        focus_instruction = (
            f"Detect and identify all instances of these target objects: {', '.join(cleaned_targets)}."
        )
    else:
        focus_instruction = (
            "Detect and identify all prominent objects in the image with specific, accurate labels."
        )

    if cleaned_targets and prompt and prompt.strip():
        focus_instruction += f" Focus specifically on: {', '.join(cleaned_targets)}."

    return (
        f"{focus_instruction} "
        "For every detected object, return its specific `label`, its `box_2d` as "
        "[ymin, xmin, ymax, xmax] normalized to 0..1000, and its `confidence` score between 0.0 and 1.0. "
        f"Only include objects with confidence >= {confidence:.2f}."
    )


def _extract_interaction_text(interaction: object) -> str:
    """Extract the JSON text response from a Gemini `Interaction` object."""
    output_text = getattr(interaction, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    steps = getattr(interaction, "steps", None)
    if isinstance(steps, list):
        chunks: list[str] = []
        for step in cast(list[Any], steps):
            if getattr(step, "type", None) == "model_output":
                content = getattr(step, "content", None)
                if isinstance(content, list):
                    for part in cast(list[Any], content):
                        if getattr(part, "type", None) == "text":
                            txt = getattr(part, "text", None)
                            if isinstance(txt, str) and txt:
                                chunks.append(txt)
        if chunks:
            return "".join(chunks).strip()
    return "[]"


def _normalize_detection_record(
    *,
    label: str,
    ymin: int,
    xmin: int,
    ymax: int,
    xmax: int,
    conf: float,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Convert normalized `0..1000` `[ymin, xmin, ymax, xmax]` coordinates into the standard detection dict."""
    clamped_ymin = max(0, min(1000, ymin))
    clamped_xmin = max(0, min(1000, xmin))
    clamped_ymax = max(0, min(1000, ymax))
    clamped_xmax = max(0, min(1000, xmax))

    if clamped_ymin > clamped_ymax:
        clamped_ymin, clamped_ymax = clamped_ymax, clamped_ymin
    if clamped_xmin > clamped_xmax:
        clamped_xmin, clamped_xmax = clamped_xmax, clamped_xmin

    x1 = max(0, min(width, int(round((clamped_xmin / 1000.0) * width))))
    y1 = max(0, min(height, int(round((clamped_ymin / 1000.0) * height))))
    x2 = max(0, min(width, int(round((clamped_xmax / 1000.0) * width))))
    y2 = max(0, min(height, int(round((clamped_ymax / 1000.0) * height))))

    clean_label = label.strip() or "object"
    rounded_conf = round(max(0.0, min(1.0, conf)), 3)
    return {
        "object": clean_label,
        "label": clean_label,
        "confidence": rounded_conf,
        "box_2d": [clamped_ymin, clamped_xmin, clamped_ymax, clamped_xmax],
        "bbox_pixels": [x1, y1, x2, y2],
        "bbox": [x1, y1, x2, y2],
    }


def _detect_with_gemini(
    *,
    rgb_img: Image.Image,
    jpeg_bytes: bytes,
    model_name: str,
    confidence: float,
    prompt: str | None,
    target_objects: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], str]:
    """Run 2D bounding-box object detection via `google.genai.Client().interactions.create` with failover."""
    clean_model = model_name.strip()
    if clean_model.startswith(("google/", "gemini/")):
        clean_model = clean_model.split("/", 1)[1]
    if not clean_model or clean_model.endswith(".pt"):
        clean_model = DEFAULT_GEMINI_MODEL

    candidate_models: list[str] = [clean_model]
    for fallback_model in GEMINI_FALLBACK_CHAIN:
        if fallback_model not in candidate_models:
            candidate_models.append(fallback_model)

    prompt_text = _build_detection_prompt(prompt, target_objects, confidence)
    img_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    client = _get_genai_client()

    last_error: Exception | None = None
    raw_json_text = "[]"
    used_model = clean_model

    for candidate in candidate_models:
        try:
            interaction = client.interactions.create(
                model=candidate,
                input=[
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "image",
                                "data": img_b64,
                                "mime_type": "image/jpeg",
                            },
                            {
                                "type": "text",
                                "text": prompt_text,
                            },
                        ],
                    }
                ],
                generation_config={"thinking_level": "low"},
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": _DETECTION_RESPONSE_SCHEMA,
                },
                store=False,
            )
            raw_json_text = _extract_interaction_text(interaction)
            used_model = candidate
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if _is_capacity_error(exc) and candidate != candidate_models[-1]:
                continue
            # If a model does not support thinking_level="low", retry once without generation_config
            if "thinking_level" in str(exc).lower() or "thinking level" in str(exc).lower():
                try:
                    interaction = client.interactions.create(
                        model=candidate,
                        input=[
                            {
                                "type": "user_input",
                                "content": [
                                    {
                                        "type": "image",
                                        "data": img_b64,
                                        "mime_type": "image/jpeg",
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt_text,
                                    },
                                ],
                            }
                        ],
                        response_format={
                            "type": "text",
                            "mime_type": "application/json",
                            "schema": _DETECTION_RESPONSE_SCHEMA,
                        },
                        store=False,
                    )
                    raw_json_text = _extract_interaction_text(interaction)
                    used_model = candidate
                    last_error = None
                    break
                except Exception as retry_exc:
                    last_error = retry_exc
                    if _is_capacity_error(retry_exc) and candidate != candidate_models[-1]:
                        continue
                    raise
            raise

    if last_error is not None:
        raise last_error

    parsed: Any = json.loads(raw_json_text)
    items_list: list[Any] = []
    if isinstance(parsed, list):
        items_list = cast(list[Any], parsed)
    elif isinstance(parsed, Mapping):
        mapped = cast(Mapping[str, Any], parsed)
        for key in ("objects", "detections", "items"):
            val = mapped.get(key)
            if isinstance(val, list):
                items_list = cast(list[Any], val)
                break

    width, height = rgb_img.size
    target_set = {t.strip().lower() for t in (target_objects or []) if t and t.strip()}
    detected_objects: list[dict[str, Any]] = []

    for item in items_list:
        if not isinstance(item, Mapping):
            continue
        item_map = cast(Mapping[str, Any], item)
        raw_label = item_map.get("label") or item_map.get("object")
        if not isinstance(raw_label, str) or not raw_label.strip():
            continue

        raw_box = item_map.get("box_2d")
        if not isinstance(raw_box, Sequence) or isinstance(raw_box, (str, bytes)):
            continue
        box_seq = list(cast(Sequence[Any], raw_box))
        if len(box_seq) != 4:
            continue

        try:
            ymin = int(round(float(box_seq[0])))
            xmin = int(round(float(box_seq[1])))
            ymax = int(round(float(box_seq[2])))
            xmax = int(round(float(box_seq[3])))
        except (TypeError, ValueError):
            continue

        raw_conf = item_map.get("confidence", 1.0)
        try:
            conf_val = float(raw_conf)
        except (TypeError, ValueError):
            conf_val = 1.0

        if conf_val < confidence:
            continue

        if target_set and raw_label.strip().lower() not in target_set:
            if not any(t in raw_label.strip().lower() for t in target_set):
                continue

        detected_objects.append(
            _normalize_detection_record(
                label=raw_label,
                ymin=ymin,
                xmin=xmin,
                ymax=ymax,
                xmax=xmax,
                conf=conf_val,
                width=width,
                height=height,
            )
        )

    return detected_objects, used_model


def _detect_with_ultralytics(
    *,
    rgb_img: Image.Image,
    model_name: str,
    confidence: float,
    target_objects: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], str] | None:
    """Run local `ultralytics.YOLO` detection if `ultralytics` is installed, or return None to fall back."""
    try:
        ultralytics_mod: Any = importlib.import_module("ultralytics")
    except ImportError:
        return None

    yolo_model: Any = ultralytics_mod.YOLO(model_name)
    results: Any = yolo_model(rgb_img, conf=confidence, verbose=False)
    width, height = rgb_img.size
    target_set = {t.strip().lower() for t in (target_objects or []) if t and t.strip()}
    detected_objects: list[dict[str, Any]] = []

    for result in cast(Sequence[Any], results):
        boxes: Any = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in cast(Sequence[Any], boxes):
            cls_id = int(box.cls[0])
            conf_val = float(box.conf[0])
            if conf_val < confidence:
                continue
            names_map: Any = yolo_model.names
            label = str(names_map[cls_id])
            if target_set and label.lower() not in target_set:
                if not any(t in label.lower() for t in target_set):
                    continue

            xyxy = [float(v) for v in box.xyxy[0].tolist()]
            if len(xyxy) != 4:
                continue
            x1_px, y1_px, x2_px, y2_px = xyxy
            ymin = int(round((y1_px / max(1, height)) * 1000.0))
            xmin = int(round((x1_px / max(1, width)) * 1000.0))
            ymax = int(round((y2_px / max(1, height)) * 1000.0))
            xmax = int(round((x2_px / max(1, width)) * 1000.0))

            detected_objects.append(
                _normalize_detection_record(
                    label=label,
                    ymin=ymin,
                    xmin=xmin,
                    ymax=ymax,
                    xmax=xmax,
                    conf=conf_val,
                    width=width,
                    height=height,
                )
            )

    return detected_objects, model_name


def _detect_objects_in_image(
    *,
    rgb_img: Image.Image,
    jpeg_bytes: bytes,
    model_name: str,
    confidence: float,
    prompt: str | None,
    target_objects: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], str]:
    """Detect objects using local `.pt` YOLO if requested and installed, otherwise Gemini 2D bbox detection."""
    if model_name.strip().endswith(".pt"):
        local_result = _detect_with_ultralytics(
            rgb_img=rgb_img,
            model_name=model_name.strip(),
            confidence=confidence,
            target_objects=target_objects,
        )
        if local_result is not None:
            return local_result

    return _detect_with_gemini(
        rgb_img=rgb_img,
        jpeg_bytes=jpeg_bytes,
        model_name=model_name,
        confidence=confidence,
        prompt=prompt,
        target_objects=target_objects,
    )


def _render_annotated_image(
    rgb_img: Image.Image,
    detected_objects: Sequence[Mapping[str, Any]],
    save_path: Path,
) -> str:
    """Render 2D bounding boxes and `label (conf)` badges onto a copy of `rgb_img` and save to disk."""
    canvas = rgb_img.copy()
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size

    for idx, obj in enumerate(detected_objects):
        color = _BBOX_PALETTE[idx % len(_BBOX_PALETTE)]
        bbox = obj.get("bbox_pixels") or obj.get("bbox")
        if not isinstance(bbox, list):
            continue
        coords = cast(list[int], bbox)
        if len(coords) != 4:
            continue
        x1, y1, x2, y2 = coords[0], coords[1], coords[2], coords[3]

        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

        label = str(obj.get("label") or obj.get("object") or "object")
        conf = float(obj.get("confidence", 0.0))
        badge_text = f"{label} ({conf:.2f})"

        tx = max(0, min(width - 10, x1 + 4))
        ty = max(0, y1 - 18 if y1 >= 18 else y1 + 2)
        text_box = draw.textbbox((tx, ty), badge_text)
        pad_x1 = max(0, int(text_box[0]) - 3)
        pad_y1 = max(0, int(text_box[1]) - 2)
        pad_x2 = min(width, int(text_box[2]) + 3)
        pad_y2 = min(height, int(text_box[3]) + 2)
        draw.rectangle([pad_x1, pad_y1, pad_x2, pad_y2], fill=color)
        draw.text((tx, ty), badge_text, fill=(255, 255, 255))

    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    annotated_path = (save_path / f"annotated_{timestamp_slug}.jpg").resolve()
    canvas.save(annotated_path, format="JPEG", quality=92)
    return str(annotated_path)


def _record_detection_entry(
    *,
    detected_objects: list[dict[str, Any]],
    source: str,
    camera_id: int,
    model_used: str,
    save_path: Path,
    annotated_image_path: str | None = None,
) -> dict[str, Any]:
    """Record a detection result in `_detections_history`, `_object_counts`, and `detections.jsonl`."""
    entry: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "camera_id": camera_id,
        "model": model_used,
        "objects": detected_objects,
        "count": len(detected_objects),
    }
    if annotated_image_path:
        entry["annotated_image_path"] = annotated_image_path

    with _detection_lock:
        for obj in detected_objects:
            label = str(obj.get("label") or obj.get("object") or "object")
            _object_counts[label] += 1
        _detections_history.append(entry)
        detections_file = save_path / "detections.jsonl"
        with open(detections_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    return entry


def _detection_worker(
    model_name: str,
    camera_id: int,
    confidence: float,
    save_dir: Path,
    interval: float,
    image_path: str | None = None,
    image_url: str | None = None,
    image_base64: str | None = None,
    prompt: str | None = None,
    target_objects: Sequence[str] | None = None,
    annotate: bool = False,
) -> None:
    """Background worker thread for continuous object detection."""
    global _detection_active

    try:
        while _detection_active:
            start_time = time.time()
            try:
                rgb_img, jpeg_bytes, source_desc = _load_image(
                    image_path=image_path,
                    image_url=image_url,
                    image_base64=image_base64,
                    camera_id=camera_id,
                    save_path=save_dir,
                )
                detected_objects, used_model = _detect_objects_in_image(
                    rgb_img=rgb_img,
                    jpeg_bytes=jpeg_bytes,
                    model_name=model_name,
                    confidence=confidence,
                    prompt=prompt,
                    target_objects=target_objects,
                )
                if detected_objects:
                    annotated_path = (
                        _render_annotated_image(rgb_img, detected_objects, save_dir)
                        if annotate
                        else None
                    )
                    _record_detection_entry(
                        detected_objects=detected_objects,
                        source=source_desc,
                        camera_id=camera_id,
                        model_used=used_model,
                        save_path=save_dir,
                        annotated_image_path=annotated_path,
                    )
            except Exception as frame_exc:
                if not _detection_active:
                    break
                print(f"❌ Detection iteration error: {frame_exc}")

            elapsed = time.time() - start_time
            if elapsed < interval and _detection_active:
                time.sleep(max(0.05, interval - elapsed))
    finally:
        _detection_active = False


@tool
def yolo_vision(
    action: str = "detect",
    model: str = DEFAULT_GEMINI_MODEL,
    image_path: str | None = None,
    image_url: str | None = None,
    image_base64: str | None = None,
    camera_id: int = 0,
    confidence: float = 0.5,
    prompt: str | None = None,
    target_objects: list[str] | None = None,
    annotate: bool = True,
    save_dir: str = "./.yolo_detections",
    interval: float = 1.0,
    limit: int = 50,
) -> dict[str, Any]:
    """2D bounding-box object detection and identification across mobile, tablet, and laptop sources.

    Args:
        action: Action to perform:
            - "detect": Run immediate 2D bounding-box detection and object identification on an image or camera frame
            - "start": Begin continuous background detection
            - "stop": Stop continuous background detection
            - "status": Check background detector status and summary statistics
            - "get_detections": Retrieve recent detection log entries
            - "list_objects": List all unique detected objects with cumulative counts
            - "clear": Clear detection history and log file
        model: Detection model ID. Defaults to `"gemini-3.8-flash"` (with automatic failover to
            `"gemini-4-argon"` and `"gemini-3.5-flash-lite"`). If a `.pt` filename is provided and
            `ultralytics` is installed, uses local YOLO; otherwise seamlessly falls back to `"gemini-3.8-flash"`.
        image_path: Optional path to a local image file.
        image_url: Optional HTTP/HTTPS URL of an image to inspect.
        image_base64: Optional base64-encoded image string or `data:image/...;base64,...` data URI
            captured from a mobile, tablet, or laptop camera/screen.
        camera_id: Local camera device ID used when no `image_path`, `image_url`, or `image_base64` is given.
        confidence: Minimum detection confidence threshold (`0.0` to `1.0`).
        prompt: Optional natural-language instruction for custom object identification or filtering.
        target_objects: Optional list of specific object classes or items to detect.
        annotate: Whether to render 2D bounding boxes and `"label (conf)"` badges onto an output image
            saved under `save_dir`.
        save_dir: Directory to store annotated images and `detections.jsonl`.
        interval: Seconds between background detections when `action="start"`.
        limit: Maximum number of recent detection entries returned by `action="get_detections"`.

    Returns:
        Dict with `status`, `content`, and structured detection metadata (`objects`, `count`,
        `annotated_image_path`, `image_size`, `model`).
    """
    global _detection_thread, _detection_active

    try:
        save_path = Path(save_dir).expanduser().resolve()
        try:
            save_path.mkdir(parents=True, exist_ok=True)
            if not os.access(save_path, os.W_OK):
                raise PermissionError("Directory not writable")
        except OSError:
            import tempfile

            save_path = (Path(tempfile.gettempdir()) / "yolo_detections").resolve()
            save_path.mkdir(parents=True, exist_ok=True)

        if action == "detect":
            rgb_img, jpeg_bytes, source_desc = _load_image(
                image_path=image_path,
                image_url=image_url,
                image_base64=image_base64,
                camera_id=camera_id,
                save_path=save_path,
            )
            width, height = rgb_img.size
            detected_objects, used_model = _detect_objects_in_image(
                rgb_img=rgb_img,
                jpeg_bytes=jpeg_bytes,
                model_name=model,
                confidence=confidence,
                prompt=prompt,
                target_objects=target_objects,
            )

            annotated_image_path: str | None = None
            if annotate:
                annotated_image_path = _render_annotated_image(
                    rgb_img, detected_objects, save_path
                )

            _record_detection_entry(
                detected_objects=detected_objects,
                source=source_desc,
                camera_id=camera_id,
                model_used=used_model,
                save_path=save_path,
                annotated_image_path=annotated_image_path,
            )

            lines = [
                f"🔍 **2D Object Detection Complete** ({len(detected_objects)} objects found)",
                f"🧠 Model: `{used_model}`",
                f"📐 Image size: {width}x{height}px",
                f"📷 Source: `{source_desc}`",
            ]
            if annotated_image_path:
                lines.append(f"🖼️ Annotated image: `{annotated_image_path}`")

            if detected_objects:
                lines.append("")
                lines.append("**Detected Objects:**")
                for obj in detected_objects:
                    lines.append(
                        f"• **{obj['label']}** ({obj['confidence']:.2f}) — "
                        f"box_2d={obj['box_2d']}, bbox_pixels={obj['bbox_pixels']}"
                    )
            else:
                lines.append("📭 No objects met the confidence threshold.")

            return {
                "status": "success",
                "content": [{"text": "\n".join(lines)}],
                "objects": detected_objects,
                "count": len(detected_objects),
                "model": used_model,
                "image_size": {"width": width, "height": height},
                "annotated_image_path": annotated_image_path,
            }

        if action == "start":
            if _detection_active:
                return {
                    "status": "error",
                    "content": [{"text": "❌ YOLO detection already running"}],
                }

            _detection_active = True
            _detection_thread = threading.Thread(
                target=_detection_worker,
                args=(
                    model,
                    camera_id,
                    confidence,
                    save_path,
                    interval,
                    image_path,
                    image_url,
                    image_base64,
                    prompt,
                    target_objects,
                    annotate,
                ),
                daemon=True,
            )
            _detection_thread.start()

            result_info = [
                "✅ **YOLO Detection Started**",
                f"🧠 Model: {model}",
                f"📹 Camera: {camera_id}",
                f"🎯 Confidence: {confidence}",
                f"⏱️  Interval: {interval}s",
                f"💾 Save dir: `{save_path}`",
            ]
            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        if action == "stop":
            if not _detection_active:
                return {
                    "status": "error",
                    "content": [{"text": "❌ YOLO detection not running"}],
                }

            _detection_active = False
            if _detection_thread is not None:
                _detection_thread.join(timeout=5)

            with _detection_lock:
                total_logged = len(_detections_history)
                unique_seen = len(_object_counts)

            result_info = [
                "🛑 **YOLO Detection Stopped**",
                f"📊 Total detections logged: {total_logged}",
                f"🔍 Unique objects seen: {unique_seen}",
            ]
            return {"status": "success", "content": [{"text": "\n".join(result_info)}]}

        if action == "status":
            with _detection_lock:
                total_detections = len(_detections_history)
                unique_objects = len(_object_counts)
                recent_objects: list[str] = []
                if _detections_history:
                    last_detection = _detections_history[-1]
                    raw_objs = last_detection.get("objects", [])
                    if isinstance(raw_objs, list):
                        for item in cast(list[Any], raw_objs):
                            if isinstance(item, Mapping):
                                obj_name = cast(Mapping[str, Any], item).get("object")
                                if isinstance(obj_name, str):
                                    recent_objects.append(obj_name)

            status_icon = "🟢" if _detection_active else "🔴"
            result_info = [
                f"{status_icon} **YOLO Detection Status**",
                f"Running: {'✅ Yes' if _detection_active else '❌ No'}",
                f"📊 Total detections: {total_detections}",
                f"🔍 Unique objects: {unique_objects}",
                f"💾 Save directory: `{save_path}`",
            ]
            if recent_objects:
                result_info.append(f"🕐 Last seen: {', '.join(sorted(set(recent_objects)))}")

            return {
                "status": "success",
                "content": [{"text": "\n".join(result_info)}],
                "running": _detection_active,
                "total_detections": total_detections,
                "unique_objects": unique_objects,
            }

        if action == "get_detections":
            with _detection_lock:
                recent = list(_detections_history[-limit:]) if _detections_history else []

            if not recent:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No detections logged yet"}],
                    "detections": [],
                }

            result_info = [f"🔍 **Recent {len(recent)} Detections:**", ""]
            for entry in recent[-10:]:
                timestamp_raw = str(entry.get("timestamp", ""))
                try:
                    timestamp = datetime.fromisoformat(timestamp_raw).strftime("%H:%M:%S")
                except ValueError:
                    timestamp = timestamp_raw
                entry_objs = cast(list[dict[str, Any]], entry.get("objects", []))
                objects_str = ", ".join(
                    f"{obj['object']}({float(obj['confidence']):.2f})"
                    for obj in entry_objs
                )
                result_info.append(f"🕐 **{timestamp}**: {objects_str}")

            result_info.extend(
                [
                    "",
                    f"📊 Total entries: {len(recent)}",
                    f"📁 Full log: `{save_path}/detections.jsonl`",
                ]
            )
            return {
                "status": "success",
                "content": [{"text": "\n".join(result_info)}],
                "detections": recent,
            }

        if action == "list_objects":
            with _detection_lock:
                object_list: list[tuple[str, int]] = sorted(
                    _object_counts.items(), key=_count_sort_key, reverse=True
                )

            if not object_list:
                return {
                    "status": "success",
                    "content": [{"text": "📭 No objects detected yet"}],
                    "object_counts": {},
                }

            result_info = [
                f"🏆 **All Detected Objects ({len(object_list)} unique):**",
                "",
            ]
            for obj_name, count in object_list:
                result_info.append(f"• **{obj_name}**: {count} times")

            return {
                "status": "success",
                "content": [{"text": "\n".join(result_info)}],
                "object_counts": dict(object_list),
            }

        if action == "clear":
            with _detection_lock:
                _detections_history.clear()
                _object_counts.clear()

            detections_file = save_path / "detections.jsonl"
            if detections_file.exists():
                detections_file.unlink()

            return {
                "status": "success",
                "content": [{"text": "✅ Detection history cleared"}],
            }

        return {
            "status": "error",
            "content": [{"text": f"❌ Unknown action: {action}"}],
        }

    except Exception as exc:
        return {"status": "error", "content": [{"text": f"❌ Error: {exc}"}]}
