# pyright: strict
"""Cross-device photo, video, and screen capture tools (`take_photo` and `take_video`)."""

from __future__ import annotations

import base64
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Literal, Protocol, TypeVar, cast
import urllib.request

from PIL import Image, ImageGrab
import strands

_F = TypeVar("_F", bound=Callable[..., dict[str, object]])


class _ToolDecorator(Protocol):
    def __call__(self, __fn: _F) -> _F: ...


tool: _ToolDecorator = cast(_ToolDecorator, getattr(strands, "tool"))

ModeType = Literal["photo", "video"]
SourceType = Literal["user", "self", "environment", "forward", "screen"]


class _FrameProtocol(Protocol):
    @property
    def shape(self) -> tuple[int, ...]: ...


class _VideoCaptureProtocol(Protocol):
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, _FrameProtocol]: ...
    def release(self) -> None: ...
    def get(self, propId: int) -> float: ...


class _VideoWriterProtocol(Protocol):
    def isOpened(self) -> bool: ...
    def write(self, image: _FrameProtocol) -> None: ...
    def release(self) -> None: ...


class _CascadeProtocol(Protocol):
    def detectMultiScale(
        self, image: _FrameProtocol, scaleFactor: float, minNeighbors: int
    ) -> list[tuple[int, int, int, int]]: ...


class _Cv2DataProtocol(Protocol):
    @property
    def haarcascades(self) -> str: ...


class _Cv2Protocol(Protocol):
    COLOR_BGR2GRAY: int
    CAP_PROP_FRAME_WIDTH: int
    CAP_PROP_FRAME_HEIGHT: int
    data: _Cv2DataProtocol

    def VideoCapture(self, index: int) -> _VideoCaptureProtocol: ...
    def VideoWriter_fourcc(self, c1: str, c2: str, c3: str, c4: str) -> int: ...
    def VideoWriter(
        self, filename: str, fourcc: int, fps: float, frameSize: tuple[int, int]
    ) -> _VideoWriterProtocol: ...
    def cvtColor(self, src: _FrameProtocol, code: int) -> _FrameProtocol: ...
    def CascadeClassifier(self, filename: str) -> _CascadeProtocol: ...
    def rectangle(
        self,
        img: _FrameProtocol,
        pt1: tuple[int, int],
        pt2: tuple[int, int],
        color: tuple[int, int, int],
        thickness: int,
    ) -> None: ...
    def imwrite(self, filename: str, img: _FrameProtocol) -> bool: ...


def _load_cv2() -> _Cv2Protocol | None:
    try:
        return cast(_Cv2Protocol, importlib.import_module("cv2"))
    except ImportError:
        return None


def _web_constraints(mode: ModeType, source: SourceType) -> dict[str, object]:
    """Build W3C MediaDevices constraints for mobile, tablet, and browser clients."""
    if source == "screen":
        return {"displayMedia": True, "video": True, "audio": mode == "video"}
    facing = "user" if source in ("user", "self") else "environment"
    return {"video": {"facingMode": facing}, "audio": mode == "video"}


def _discover_cameras(max_check: int = 10) -> list[int]:
    """Discover available local camera indices via OpenCV, AVFoundation (macOS), or V4L2 (Linux)."""
    cv2 = _load_cv2()
    if cv2 is not None:
        found: list[int] = []
        for i in range(max_check):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                found.append(i)
                cap.release()
        if found:
            return found

    if sys.platform == "darwin" and shutil.which("ffmpeg"):
        try:
            proc = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
            )
            out = (proc.stderr or "") + (proc.stdout or "")
            cam_ids: list[int] = []
            in_video = False
            for line in out.splitlines():
                if "AVFoundation video devices:" in line:
                    in_video = True
                    continue
                if "AVFoundation audio devices:" in line:
                    break
                if in_video:
                    m = re.search(r"\[(\d+)\]\s+(.+)$", line)
                    if m and "capture screen" not in m.group(2).lower():
                        cam_ids.append(int(m.group(1)))
            if cam_ids:
                return cam_ids
        except Exception:
            pass

    if sys.platform.startswith("linux"):
        dev_cams = [
            int(p.name[5:])
            for p in sorted(Path("/dev").glob("video[0-9]*"))
            if p.name[5:].isdigit()
        ]
        if dev_cams:
            return dev_cams

    return []


def _image_resolution(filepath: Path) -> str:
    try:
        with Image.open(filepath) as img:
            return f"{img.width}x{img.height}"
    except Exception:
        return "unknown"


def _ingest_media_data(
    media_data: str,
    mode: ModeType,
    source: SourceType,
    save_dir: Path,
) -> dict[str, object]:
    """Decode client-supplied media_data (data URL, FileUpload JSON, HTTP URL, file path, or base64)."""
    raw_input = media_data.strip()
    mime_hint = ""

    if raw_input.startswith("{") and raw_input.endswith("}"):
        try:
            parsed_obj: object = json.loads(raw_input)
            if isinstance(parsed_obj, dict):
                parsed_dict = cast(dict[str, object], parsed_obj)
                data_val = parsed_dict.get("data")
                type_val = parsed_dict.get("type")
                if isinstance(type_val, str):
                    mime_hint = type_val.lower()
                if isinstance(data_val, str):
                    raw_input = data_val.strip()
        except Exception:
            pass

    if raw_input.startswith("data:"):
        header, _, b64_payload = raw_input.partition(",")
        if ";" in header and ":" in header:
            mime_hint = header.split(":", 1)[1].split(";", 1)[0].lower()
        raw_bytes = base64.b64decode(b64_payload)
    elif raw_input.startswith(("http://", "https://")):
        with urllib.request.urlopen(raw_input, timeout=15.0) as resp:
            raw_bytes = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if isinstance(ctype, str):
                mime_hint = ctype.split(";", 1)[0].lower()
    elif len(raw_input) < 1024 and Path(raw_input).expanduser().is_file():
        src_file = Path(raw_input).expanduser()
        raw_bytes = src_file.read_bytes()
        mime_hint = src_file.suffix.lower()
    else:
        padded = raw_input + "=" * ((4 - len(raw_input) % 4) % 4)
        raw_bytes = base64.b64decode(padded)

    if mode == "photo":
        if raw_bytes.startswith(b"\x89PNG") or "png" in mime_hint:
            ext = ".png"
        elif raw_bytes.startswith(b"RIFF") and b"WEBP" in raw_bytes[:16]:
            ext = ".webp"
        else:
            ext = ".jpg"
    else:
        if "webm" in mime_hint or raw_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            ext = ".webm"
        elif "quicktime" in mime_hint or mime_hint.endswith(".mov"):
            ext = ".mov"
        else:
            ext = ".mp4"

    timestamp = int(time.time() * 1000)
    filepath = save_dir / f"{mode}-{timestamp}-{source}{ext}"
    filepath.write_bytes(raw_bytes)
    resolution = _image_resolution(filepath) if mode == "photo" else "video"
    constraints = _web_constraints(mode, source)
    summary = (
        f"Saved client {mode} ({source}): {filepath} "
        f"({len(raw_bytes):,} bytes, resolution={resolution})"
    )
    meta: dict[str, object] = {
        "status": "success",
        "mode": mode,
        "source": source,
        "filepath": str(filepath),
        "file_size": len(raw_bytes),
        "resolution": resolution,
        "web_constraints": constraints,
    }
    return {
        **meta,
        "content": [{"text": summary}, {"json": meta}],
    }


def _capture_screen(
    mode: ModeType,
    save_dir: Path,
    delay: float,
    duration: float,
) -> dict[str, object]:
    """Capture a local screenshot (`mode='photo'`) or screen recording (`mode='video'`)."""
    if delay > 0:
        time.sleep(delay)
    timestamp = int(time.time() * 1000)
    constraints = _web_constraints(mode, "screen")

    if mode == "photo":
        filepath = save_dir / f"photo-{timestamp}-screen.png"
        try:
            img = ImageGrab.grab()
            img.save(filepath)
        except Exception:
            if sys.platform == "darwin" and Path("/usr/sbin/screencapture").exists():
                subprocess.run(
                    ["/usr/sbin/screencapture", "-x", str(filepath)],
                    capture_output=True,
                    timeout=5.0,
                    check=False,
                )
            elif sys.platform.startswith("linux") and shutil.which("ffmpeg") and os.environ.get("DISPLAY"):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "x11grab",
                        "-i",
                        os.environ.get("DISPLAY", ":0.0"),
                        "-frames:v",
                        "1",
                        "-update",
                        "1",
                        str(filepath),
                    ],
                    capture_output=True,
                    timeout=5.0,
                    check=False,
                )

        if filepath.exists() and filepath.stat().st_size > 0:
            res = _image_resolution(filepath)
            fsize = filepath.stat().st_size
            meta: dict[str, object] = {
                "status": "success",
                "mode": "photo",
                "source": "screen",
                "filepath": str(filepath),
                "file_size": fsize,
                "resolution": res,
                "web_constraints": constraints,
            }
            return {
                **meta,
                "content": [
                    {"text": f"Captured screen photo: {filepath} ({res}, {fsize:,} bytes)"},
                    {"json": meta},
                ],
            }
    else:
        ext = ".mov" if sys.platform == "darwin" else ".mp4"
        filepath = save_dir / f"video-{timestamp}-screen{ext}"
        dur_sec = max(1, int(round(duration)))
        if sys.platform == "darwin" and Path("/usr/sbin/screencapture").exists():
            subprocess.run(
                ["/usr/sbin/screencapture", "-x", "-v", "-V", str(dur_sec), str(filepath)],
                capture_output=True,
                timeout=float(dur_sec) + 5.0,
                check=False,
            )
        elif sys.platform.startswith("linux") and shutil.which("ffmpeg") and os.environ.get("DISPLAY"):
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "x11grab",
                    "-framerate",
                    "30",
                    "-i",
                    os.environ.get("DISPLAY", ":0.0"),
                    "-t",
                    str(dur_sec),
                    "-pix_fmt",
                    "yuv420p",
                    str(filepath),
                ],
                capture_output=True,
                timeout=float(dur_sec) + 8.0,
                check=False,
            )
        elif sys.platform == "win32" and shutil.which("ffmpeg"):
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "gdigrab",
                    "-framerate",
                    "30",
                    "-i",
                    "desktop",
                    "-t",
                    str(dur_sec),
                    "-pix_fmt",
                    "yuv420p",
                    str(filepath),
                ],
                capture_output=True,
                timeout=float(dur_sec) + 8.0,
                check=False,
            )

        if filepath.exists() and filepath.stat().st_size > 0:
            fsize = filepath.stat().st_size
            meta = {
                "status": "success",
                "mode": "video",
                "source": "screen",
                "filepath": str(filepath),
                "file_size": fsize,
                "duration": duration,
                "resolution": "screen",
                "web_constraints": constraints,
            }
            return {
                **meta,
                "content": [
                    {"text": f"Captured screen video ({duration}s): {filepath} ({fsize:,} bytes)"},
                    {"json": meta},
                ],
            }

    meta_req: dict[str, object] = {
        "status": "client_capture_required",
        "mode": mode,
        "source": "screen",
        "web_constraints": constraints,
        "message": (
            "Local screen capture is unavailable or requires display permission. "
            "Capture on the client via navigator.mediaDevices.getDisplayMedia and pass `media_data`."
        ),
    }
    return {
        **meta_req,
        "content": [
            {"text": str(meta_req["message"])},
            {"json": meta_req},
        ],
    }


def _capture_camera_one(
    camera_id: int,
    mode: ModeType,
    source: SourceType,
    save_dir: Path,
    detect_faces: bool,
    delay: float,
    duration: float,
) -> dict[str, object]:
    """Capture a single photo or video from a specific local camera via OpenCV or FFmpeg."""
    if delay > 0:
        time.sleep(delay)

    timestamp = int(time.time() * 1000)
    cv2 = _load_cv2()

    if mode == "photo":
        filepath = save_dir / f"photo-{timestamp}-cam{camera_id}-{source}.jpg"
        faces_found = 0

        if cv2 is not None:
            cam = cv2.VideoCapture(camera_id)
            if cam.isOpened():
                ret, frame = cam.read()
                cam.release()
                if ret:
                    if detect_faces:
                        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                        face_cascade = cv2.CascadeClassifier(cascade_path)
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                        faces_found = len(faces)
                        for x, y, w, h in faces:
                            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
                    cv2.imwrite(str(filepath), frame)

        if (not filepath.exists() or filepath.stat().st_size == 0) and shutil.which("ffmpeg"):
            cmd: list[str] = []
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
                    "-update",
                    "1",
                    str(filepath),
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
                    "-update",
                    "1",
                    str(filepath),
                ]
            if cmd:
                subprocess.run(cmd, capture_output=True, timeout=8.0, check=False)

        if filepath.exists() and filepath.stat().st_size > 0:
            res = _image_resolution(filepath)
            fsize = filepath.stat().st_size
            return {
                "camera_id": camera_id,
                "status": "success",
                "mode": "photo",
                "source": source,
                "filepath": str(filepath),
                "resolution": res,
                "faces_found": faces_found,
                "file_size": fsize,
            }
        return {
            "camera_id": camera_id,
            "status": "error",
            "mode": "photo",
            "source": source,
            "message": f"Camera {camera_id} could not capture photo locally",
        }

    # mode == "video"
    filepath = save_dir / f"video-{timestamp}-cam{camera_id}-{source}.mp4"
    dur = max(0.5, float(duration))

    if shutil.which("ffmpeg"):
        vcmd: list[str] = []
        if sys.platform == "darwin":
            vcmd = [
                "ffmpeg",
                "-y",
                "-f",
                "avfoundation",
                "-framerate",
                "30",
                "-i",
                str(camera_id),
                "-t",
                f"{dur:.2f}",
                "-pix_fmt",
                "yuv420p",
                str(filepath),
            ]
        elif sys.platform.startswith("linux"):
            vcmd = [
                "ffmpeg",
                "-y",
                "-f",
                "v4l2",
                "-framerate",
                "30",
                "-i",
                f"/dev/video{camera_id}",
                "-t",
                f"{dur:.2f}",
                "-pix_fmt",
                "yuv420p",
                str(filepath),
            ]
        if vcmd:
            subprocess.run(vcmd, capture_output=True, timeout=dur + 10.0, check=False)

    if (not filepath.exists() or filepath.stat().st_size == 0) and cv2 is not None:
        cam = cv2.VideoCapture(camera_id)
        if cam.isOpened():
            w = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
            h = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
            fourcc = cv2.VideoWriter_fourcc("m", "p", "4", "v")
            writer = cv2.VideoWriter(str(filepath), fourcc, 20.0, (w, h))
            deadline = time.time() + dur
            while time.time() < deadline:
                ret, frame = cam.read()
                if not ret:
                    break
                writer.write(frame)
            writer.release()
            cam.release()

    if filepath.exists() and filepath.stat().st_size > 0:
        fsize = filepath.stat().st_size
        return {
            "camera_id": camera_id,
            "status": "success",
            "mode": "video",
            "source": source,
            "filepath": str(filepath),
            "duration": dur,
            "resolution": "video",
            "file_size": fsize,
        }
    return {
        "camera_id": camera_id,
        "status": "error",
        "mode": "video",
        "source": source,
        "message": f"Camera {camera_id} could not record video locally",
    }


@tool
def take_photo(
    mode: ModeType = "photo",
    source: SourceType = "user",
    camera_ids: list[int] | None = None,
    num_photos: int = 1,
    delay: float = 0.0,
    duration: float = 5.0,
    detect_faces: bool = False,
    save_path: str | None = None,
    discover: bool = False,
    media_data: str | None = None,
) -> dict[str, object]:
    """Capture a photo or video from a self-facing camera, forward/environment camera, or screen across devices.

    Args:
        mode: Capture mode - "photo" for still image/screenshot or "video" for camera/screen recording.
        source: Capture source - "user"/"self" (front camera), "environment"/"forward" (rear/world camera), or "screen".
        camera_ids: Optional explicit list of local camera indices (e.g. [0, 1]). Overrides `source` camera selection.
        num_photos: Number of photos to capture per camera when `mode="photo"`.
        delay: Warmup/countdown delay in seconds before capturing.
        duration: Recording duration in seconds when `mode="video"`.
        detect_faces: Run Haar-cascade face detection on captured photos when OpenCV is installed.
        save_path: Directory to save captured media files (defaults to current working directory).
        discover: If True, discover available cameras and return W3C client capture constraints without capturing.
        media_data: Optional client-captured payload (base64, data:<mime>;base64,..., FileUpload JSON, or URL) from mobile/tablet/laptop.

    Returns:
        Dict with capture status, saved filepath, metadata, web_constraints, and Strands content blocks.
    """
    try:
        constraints = _web_constraints(mode, source)

        if discover:
            cameras = _discover_cameras()
            info = {
                "status": "success",
                "cameras": cameras,
                "modes": ["photo", "video"],
                "sources": ["user", "self", "environment", "forward", "screen"],
                "web_constraints": constraints,
            }
            text = (
                f"Found {len(cameras)} local camera(s): {cameras}\n"
                f"Mode: {mode}, Source: {source}, Web constraints: {json.dumps(constraints)}"
            )
            return {**info, "content": [{"text": text}, {"json": info}]}

        save_dir = Path(save_path).expanduser() if save_path else Path.cwd()
        save_dir.mkdir(parents=True, exist_ok=True)

        if media_data is not None and media_data.strip():
            return _ingest_media_data(media_data, mode, source, save_dir)

        if source == "screen":
            return _capture_screen(mode, save_dir, delay, duration)

        available = _discover_cameras()
        if camera_ids is not None:
            target_cameras = camera_ids
        elif source in ("environment", "forward"):
            target_cameras = [1 if 1 in available else (available[0] if available else 1)]
        else:
            target_cameras = [0 if 0 in available else (available[0] if available else 0)]

        count = max(1, num_photos) if mode == "photo" else 1
        all_results: list[dict[str, object]] = []

        if len(target_cameras) > 1:
            with ThreadPoolExecutor(max_workers=len(target_cameras)) as executor:
                futures = [
                    executor.submit(
                        _capture_camera_one,
                        cam_id,
                        mode,
                        source,
                        save_dir,
                        detect_faces,
                        delay,
                        duration,
                    )
                    for cam_id in target_cameras
                    for _ in range(count)
                ]
                for future in as_completed(futures):
                    all_results.append(future.result())
        else:
            cam_id = target_cameras[0]
            for _ in range(count):
                all_results.append(
                    _capture_camera_one(
                        cam_id, mode, source, save_dir, detect_faces, delay, duration
                    )
                )

        succeeded = [r for r in all_results if r.get("status") == "success"]
        if not succeeded:
            req_payload: dict[str, object] = {
                "status": "client_capture_required",
                "mode": mode,
                "source": source,
                "camera_ids": target_cameras,
                "available_cameras": available,
                "web_constraints": constraints,
                "results": all_results,
                "message": (
                    f"No local camera could capture {mode} for source={source!r}. "
                    "Capture on client via navigator.mediaDevices.getUserMedia(web_constraints) "
                    "and pass `media_data`."
                ),
            }
            return {
                **req_payload,
                "content": [{"text": str(req_payload["message"])}, {"json": req_payload}],
            }

        primary = succeeded[0]
        lines = [
            f"Captured {len(succeeded)}/{len(all_results)} {mode}(s) (source={source}):",
        ]
        for r in all_results:
            if r.get("status") == "success":
                lines.append(
                    f"- Camera {r.get('camera_id')}: {r.get('filepath')} "
                    f"({r.get('resolution')}, {r.get('file_size')} bytes)"
                )
            else:
                lines.append(f"- Camera {r.get('camera_id')}: {r.get('message')}")

        out_meta: dict[str, object] = {
            "status": "success",
            "mode": mode,
            "source": source,
            "filepath": primary.get("filepath", ""),
            "file_size": primary.get("file_size", 0),
            "resolution": primary.get("resolution", "unknown"),
            "results": all_results,
            "web_constraints": constraints,
        }
        return {
            **out_meta,
            "content": [{"text": "\n".join(lines)}, {"json": out_meta}],
        }
    except Exception as exc:
        return {
            "status": "error",
            "mode": mode,
            "source": source,
            "content": [{"text": f"Error in take_photo: {exc}"}],
        }


@tool
def take_video(
    source: SourceType = "user",
    camera_ids: list[int] | None = None,
    delay: float = 0.0,
    duration: float = 5.0,
    save_path: str | None = None,
    discover: bool = False,
    media_data: str | None = None,
) -> dict[str, object]:
    """Record a video from a self-facing camera, forward/environment camera, or screen across devices.

    Args:
        source: Capture source - "user"/"self" (front camera), "environment"/"forward" (rear/world camera), or "screen".
        camera_ids: Optional explicit list of local camera indices (e.g. [0, 1]).
        delay: Warmup/countdown delay in seconds before recording starts.
        duration: Recording duration in seconds (default 5.0).
        save_path: Directory to save recorded video files (defaults to current working directory).
        discover: If True, discover available cameras and return W3C client capture constraints without recording.
        media_data: Optional client-recorded video payload (base64, data:<mime>;base64,..., FileUpload JSON, or URL).

    Returns:
        Dict with recording status, saved filepath, metadata, web_constraints, and Strands content blocks.
    """
    return take_photo(
        mode="video",
        source=source,
        camera_ids=camera_ids,
        delay=delay,
        duration=duration,
        save_path=save_path,
        discover=discover,
        media_data=media_data,
    )
