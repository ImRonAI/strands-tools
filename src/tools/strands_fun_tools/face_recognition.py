# pyright: strict
"""Universal Face Recognition, Biometric Passkey (WebAuthn Face ID / Windows Hello / Android Biometric),
and Camera-Frame Face Verification & Authorization tool across Mobile, Tablets, and Laptops.

Supports:
1. W3C WebAuthn Platform Passkey Biometric Authorization (`challenge`, `register_passkey`,
   `authenticate_passkey`, `list_passkeys`, `delete_passkey`, `verify_token`) using native
   `cryptography` (EC P-256 / RSA / Ed25519) + `PyJWT` (`HS256` Bearer tokens).
2. Camera-Frame Face Enrollment, Search, Comparison & Authorization (`capture`, `index_face`,
   `search_faces`, `compare_faces`, `verify_face`, `list_faces`, `delete_face`,
   `create_collection`, `list_collections`) across universal image inputs (`image_base64`,
   `image_path`, `image_url`, or local camera fallback) with dual native provider support:
   - Gemini Vision (`google.genai.Client().interactions.create` with `gemini-3.8-flash` ->
     `gemini-4-argon` -> `gemini-3.5-flash-lite`) by default.
   - AWS Rekognition (`boto3.client("rekognition")`) when `provider="rekognition"` or AWS
     credentials + `collection_id` are configured.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
import hashlib
import importlib
import io
import json
import os
import platform
import secrets
import shutil
import subprocess
import tempfile
import time
from typing import Protocol, cast
import uuid
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)
from PIL import Image


class _ToolDecoratorProtocol(Protocol):
    def __call__[F: Callable[..., object]](self, func: F, /) -> F: ...


class _BufferProtocol(Protocol):
    def tobytes(self) -> bytes: ...


class _VideoCaptureProtocol(Protocol):
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, object]: ...
    def release(self) -> None: ...


class _Cv2Protocol(Protocol):
    def VideoCapture(self, index: int) -> _VideoCaptureProtocol: ...
    def imencode(self, ext: str, img: object) -> tuple[bool, _BufferProtocol]: ...


class _RekognitionClientProtocol(Protocol):
    def create_collection(self, *, CollectionId: str) -> dict[str, object]: ...
    def list_collections(self) -> dict[str, object]: ...
    def index_faces(
        self,
        *,
        CollectionId: str,
        Image: dict[str, bytes],
        ExternalImageId: str,
        DetectionAttributes: list[str],
    ) -> dict[str, object]: ...
    def search_faces_by_image(
        self,
        *,
        CollectionId: str,
        Image: dict[str, bytes],
        FaceMatchThreshold: float,
        MaxFaces: int,
    ) -> dict[str, object]: ...
    def compare_faces(
        self,
        *,
        SourceImage: dict[str, bytes],
        TargetImage: dict[str, bytes],
        SimilarityThreshold: float,
    ) -> dict[str, object]: ...
    def list_faces(
        self, *, CollectionId: str, MaxResults: int
    ) -> dict[str, object]: ...
    def delete_faces(
        self, *, CollectionId: str, FaceIds: list[str]
    ) -> dict[str, object]: ...


class _Boto3Protocol(Protocol):
    def client(self, service_name: str) -> _RekognitionClientProtocol: ...


class _InteractionProtocol(Protocol):
    @property
    def output_text(self) -> str | None: ...
    @property
    def steps(self) -> list[object] | None: ...


class _InteractionsResourceProtocol(Protocol):
    def create(
        self,
        *,
        model: str,
        input: list[dict[str, object]],
        response_format: dict[str, object],
    ) -> _InteractionProtocol: ...


class _GenaiClientProtocol(Protocol):
    @property
    def interactions(self) -> _InteractionsResourceProtocol: ...


class _GenaiModuleProtocol(Protocol):
    def Client(self, *, api_key: str) -> _GenaiClientProtocol: ...


_strands_module = importlib.import_module("strands")
tool: _ToolDecoratorProtocol = cast(
    _ToolDecoratorProtocol, getattr(_strands_module, "tool")
)

DEFAULT_GEMINI_MODELS: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-4-argon",
    "gemini-3.5-flash-lite",
)

CHALLENGE_TTL_SECONDS = 300
DEFAULT_JWT_EXPIRES_SECONDS = 3600

_MEMORY_CHALLENGES: dict[str, dict[str, object]] = {}


def _as_float(val: object, default: float = 0.0) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return default
    return default


def _as_int(val: object, default: int = 0) -> int:
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def _resolve_save_dir(save_dir: str | None = None) -> Path:
    raw = (
        save_dir
        or os.environ.get("STRANDS_FACE_AUTH_DIR")
        or os.path.join(os.path.expanduser("~"), ".strands", "face_auth")
    )
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _b64url_decode(data: str) -> bytes:
    cleaned = data.strip()
    if "," in cleaned and cleaned.startswith("data:"):
        cleaned = cleaned.split(",", 1)[1]
    cleaned = cleaned.replace("-", "+").replace("_", "/")
    pad = (-len(cleaned)) % 4
    if pad:
        cleaned += "=" * pad
    return base64.b64decode(cleaned)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _get_jwt_secret(base_dir: Path) -> str:
    env_secret = (
        os.environ.get("STRANDS_FACE_JWT_SECRET")
        or os.environ.get("JWT_SIGNING_KEY")
        or os.environ.get("STRANDS_ACCESS_TOKEN")
    )
    if env_secret:
        if len(env_secret.encode("utf-8")) < 32:
            return hashlib.sha256(env_secret.encode("utf-8")).hexdigest()
        return env_secret
    secret_file = base_dir / "jwt_secret.key"
    if secret_file.exists():
        stored = secret_file.read_text(encoding="utf-8").strip()
        if len(stored.encode("utf-8")) >= 32:
            return stored
    generated = secrets.token_urlsafe(32)
    secret_file.write_text(generated, encoding="utf-8")
    try:
        os.chmod(secret_file, 0o600)
    except OSError:
        pass
    return generated


def _mint_face_jwt(
    base_dir: Path,
    subject: str,
    amr: list[str],
    extra_claims: dict[str, object] | None = None,
    expires_in: int = DEFAULT_JWT_EXPIRES_SECONDS,
) -> dict[str, object]:
    now = int(time.time())
    jti = secrets.token_urlsafe(16)
    claims: dict[str, object] = {
        "iss": "strands-face-recognition",
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
        "jti": jti,
        "amr": amr,
        "scope": "face_verified",
    }
    if extra_claims:
        claims.update(extra_claims)
    secret = _get_jwt_secret(base_dir)
    token = jwt.encode(claims, secret, algorithm="HS256")
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "sub": subject,
        "amr": amr,
        "scope": "face_verified",
        "jti": jti,
        "claims": claims,
    }


def _verify_face_jwt(base_dir: Path, token: str) -> dict[str, object]:
    cleaned = token.strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    secret = _get_jwt_secret(base_dir)
    decoded: dict[str, object] = jwt.decode(
        cleaned,
        secret,
        algorithms=["HS256"],
        options={"require": ["exp", "iat", "sub"]},
    )
    return decoded


def _challenges_file(base_dir: Path) -> Path:
    return base_dir / "challenges.json"


def _load_challenges(base_dir: Path) -> dict[str, dict[str, object]]:
    now = time.time()
    merged: dict[str, dict[str, object]] = {}
    path = _challenges_file(base_dir)
    if path.exists():
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw_dict = cast(dict[str, object], raw)
                for k, v in raw_dict.items():
                    if isinstance(v, dict):
                        entry = cast(dict[str, object], v)
                        if _as_float(entry.get("expires_at"), 0.0) > now:
                            merged[str(k)] = entry
        except Exception:
            pass
    for k, v in list(_MEMORY_CHALLENGES.items()):
        if _as_float(v.get("expires_at"), 0.0) > now:
            merged[k] = v
        else:
            _MEMORY_CHALLENGES.pop(k, None)
    return merged


def _save_challenges(base_dir: Path, challenges: dict[str, dict[str, object]]) -> None:
    _MEMORY_CHALLENGES.clear()
    _MEMORY_CHALLENGES.update(challenges)
    path = _challenges_file(base_dir)
    path.write_text(json.dumps(challenges, indent=2), encoding="utf-8")


def _consume_challenge(
    base_dir: Path, client_challenge_b64: str
) -> dict[str, object] | None:
    challenges = _load_challenges(base_dir)
    cand_norm = client_challenge_b64.strip().rstrip("=")
    decoded_str: str | None = None
    try:
        decoded_str = (
            _b64url_decode(cand_norm).decode("utf-8", errors="strict").rstrip("=")
        )
    except Exception:
        decoded_str = None

    matched_key: str | None = None
    for stored_key in challenges:
        key_norm = stored_key.strip().rstrip("=")
        if cand_norm == key_norm or (
            decoded_str is not None and decoded_str == key_norm
        ):
            matched_key = stored_key
            break

    if matched_key is None:
        return None

    entry = challenges.pop(matched_key)
    _save_challenges(base_dir, challenges)
    return entry


def _passkeys_file(base_dir: Path) -> Path:
    return base_dir / "passkeys.json"


def _load_passkeys(base_dir: Path) -> dict[str, dict[str, object]]:
    path = _passkeys_file(base_dir)
    if not path.exists():
        return {}
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            result: dict[str, dict[str, object]] = {}
            raw_dict = cast(dict[str, object], raw)
            for k, v in raw_dict.items():
                if isinstance(v, dict):
                    result[str(k)] = cast(dict[str, object], v)
            return result
    except Exception:
        pass
    return {}


def _save_passkeys(base_dir: Path, passkeys: dict[str, dict[str, object]]) -> None:
    path = _passkeys_file(base_dir)
    path.write_text(json.dumps(passkeys, indent=2), encoding="utf-8")


def _parse_authenticator_data(auth_data: bytes) -> dict[str, object]:
    if len(auth_data) < 37:
        raise ValueError(
            f"Invalid authenticatorData length {len(auth_data)} (must be >= 37 bytes)."
        )
    rp_id_hash = auth_data[:32]
    flags = auth_data[32]
    sign_count = int.from_bytes(auth_data[33:37], byteorder="big", signed=False)
    up = bool(flags & 0x01)
    uv = bool(flags & 0x04)
    be = bool(flags & 0x08)
    bs = bool(flags & 0x10)
    at = bool(flags & 0x40)
    ed = bool(flags & 0x80)
    return {
        "rp_id_hash": rp_id_hash,
        "flags": flags,
        "user_present": up,
        "user_verified": uv,
        "backup_eligible": be,
        "backup_state": bs,
        "attested_credential_data": at,
        "extension_data": ed,
        "sign_count": sign_count,
    }


def _normalize_image_bytes(raw_bytes: bytes) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(raw_bytes)) as img:
        rgb = img.convert("RGB")
        width, height = rgb.size
        out = io.BytesIO()
        rgb.save(out, format="JPEG", quality=92)
        return out.getvalue(), width, height


def _capture_camera_bytes(camera_id: int = 0) -> bytes:
    # 1. Try OpenCV lazily if installed and functional
    try:
        cv2 = cast(_Cv2Protocol, importlib.import_module("cv2"))
        cam = cv2.VideoCapture(camera_id)
        if cam.isOpened():
            try:
                ret, frame = cam.read()
                if ret and frame is not None:
                    ok, buffer = cv2.imencode(".jpg", frame)
                    if ok:
                        return buffer.tobytes()
            finally:
                cam.release()
    except Exception:
        pass

    # 2. Fallback to ffmpeg on macOS / Linux if available
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            sys_name = platform.system().lower()
            if sys_name == "darwin":
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-f",
                    "avfoundation",
                    "-framerate",
                    "30",
                    "-i",
                    f"{camera_id}:none",
                    "-frames:v",
                    "1",
                    tmp_path,
                ]
            else:
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-f",
                    "v4l2",
                    "-i",
                    f"/dev/video{camera_id}",
                    "-frames:v",
                    "1",
                    tmp_path,
                ]
            proc = subprocess.run(cmd, capture_output=True, timeout=10, check=False)
            if (
                proc.returncode == 0
                and os.path.exists(tmp_path)
                and os.path.getsize(tmp_path) > 0
            ):
                return Path(tmp_path).read_bytes()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    raise RuntimeError(
        "Could not capture image from local camera. Pass `image_base64`, `image_path`, or `image_url` "
        "from your mobile/tablet/laptop client, or ensure a local camera is connected."
    )


def _resolve_image_input(
    image_base64: str | None = None,
    image_path: str | None = None,
    image_url: str | None = None,
    camera_id: int = 0,
    allow_camera_fallback: bool = True,
) -> tuple[bytes, int, int, str]:
    raw_bytes: bytes | None = None
    source = "unknown"

    if image_base64:
        raw_bytes = _b64url_decode(image_base64)
        source = "image_base64"
    elif image_path:
        p = Path(image_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Image file not found: {p}")
        raw_bytes = p.read_bytes()
        source = f"file:{p}"
    elif image_url:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
            raw_bytes = resp.content
        source = f"url:{image_url}"
    elif allow_camera_fallback:
        raw_bytes = _capture_camera_bytes(camera_id=camera_id)
        source = f"camera:{camera_id}"
    else:
        raise ValueError(
            "An image input is required (`image_base64`, `image_path`, or `image_url`)."
        )

    jpg_bytes, width, height = _normalize_image_bytes(raw_bytes)
    return jpg_bytes, width, height, source


def _collection_dir(base_dir: Path, collection_id: str | None) -> Path:
    cid = (collection_id or "default").strip() or "default"
    safe_cid = (
        "".join(c for c in cid if c.isalnum() or c in ("-", "_", ".")) or "default"
    )
    cdir = base_dir / "collections" / safe_cid
    cdir.mkdir(parents=True, exist_ok=True)
    return cdir


def _load_collection_faces(cdir: Path) -> list[dict[str, object]]:
    meta_file = cdir / "faces.json"
    if not meta_file.exists():
        return []
    try:
        raw: object = json.loads(meta_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            result: list[dict[str, object]] = []
            for item in cast(list[object], raw):
                if isinstance(item, dict):
                    result.append(cast(dict[str, object], item))
            return result
    except Exception:
        pass
    return []


def _save_collection_faces(cdir: Path, faces: list[dict[str, object]]) -> None:
    meta_file = cdir / "faces.json"
    meta_file.write_text(json.dumps(faces, indent=2), encoding="utf-8")


def _use_rekognition(provider: str, collection_id: str | None) -> bool:
    prov = provider.strip().lower()
    if prov == "rekognition":
        return True
    if prov == "gemini":
        return False
    return bool(collection_id and os.environ.get("AWS_ACCESS_KEY_ID"))


def _gemini_compare_faces(
    query_jpg: bytes,
    candidates: list[dict[str, object]],
    similarity_threshold: float,
) -> dict[str, object]:
    genai_mod = cast(_GenaiModuleProtocol, importlib.import_module("google.genai"))

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required for Gemini face verification."
        )

    client = genai_mod.Client(api_key=api_key)
    content_blocks: list[dict[str, object]] = [
        {
            "type": "text",
            "text": (
                "You are a biometric face verification and liveness analysis engine.\n"
                "Image 1 is the QUERY face image captured from a user's camera.\n"
                "Following Image 1 are the ENROLLED reference face images, each labeled with its "
                "`face_id` and `external_image_id`.\n"
                "Tasks:\n"
                "1. Check that Image 1 contains a real, clear human face and passes passive visual "
                "liveness checks (not a flat printed cutout, cartoon, or obvious spoof screen with moiré/bezels).\n"
                "2. Compare the facial geometry, landmarks, ocular spacing, nasal bridge, jawline, and "
                "craniofacial structure of Image 1 against each enrolled reference face.\n"
                "3. Determine the highest-similarity reference face (0.0 to 100.0 scale) and whether "
                f"`similarity >= {similarity_threshold:.1f}` and `liveness_check_passed` is true."
            ),
        },
        {
            "type": "text",
            "text": "Image 1 (QUERY face image):",
        },
        {
            "type": "image",
            "data": base64.b64encode(query_jpg).decode("ascii"),
            "mime_type": "image/jpeg",
        },
    ]

    for idx, cand in enumerate(candidates, start=1):
        face_id = str(cand.get("face_id", f"face_{idx}"))
        ext_id = str(cand.get("external_image_id", face_id))
        img_bytes = cast(bytes, cand["image_bytes"])
        content_blocks.append(
            {
                "type": "text",
                "text": f"Reference Face #{idx}: face_id={face_id!r}, external_image_id={ext_id!r}",
            }
        )
        content_blocks.append(
            {
                "type": "image",
                "data": base64.b64encode(img_bytes).decode("ascii"),
                "mime_type": "image/jpeg",
            }
        )

    schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "matched": {"type": "boolean"},
            "similarity": {"type": "number"},
            "face_id": {"type": "string"},
            "external_image_id": {"type": "string"},
            "liveness_check_passed": {"type": "boolean"},
            "reasoning": {"type": "string"},
        },
        "required": [
            "matched",
            "similarity",
            "face_id",
            "external_image_id",
            "liveness_check_passed",
            "reasoning",
        ],
    }

    last_err: Exception | None = None
    for model_id in DEFAULT_GEMINI_MODELS:
        try:
            interaction = client.interactions.create(
                model=model_id,
                input=content_blocks,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
            )
            raw_text = str(interaction.output_text or "").strip()
            if not raw_text:
                steps = interaction.steps
                if isinstance(steps, list):
                    for step in reversed(steps):
                        scontent = getattr(step, "content", None)
                        if isinstance(scontent, list):
                            for part in cast(list[object], scontent):
                                ptext = getattr(part, "text", None)
                                if isinstance(ptext, str) and ptext.strip():
                                    raw_text = ptext.strip()
                                    break
                        if raw_text:
                            break
            parsed = cast(dict[str, object], json.loads(raw_text))
            parsed["model"] = model_id
            return parsed
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(
        f"Gemini face verification failed across all models: {last_err}"
    )


def _run_rekognition(
    action: str,
    collection_id: str | None,
    external_image_id: str | None,
    face_id: str | None,
    similarity_threshold: float,
    max_faces: int,
    image_base64: str | None,
    image_path: str | None,
    image_url: str | None,
    target_image_base64: str | None,
    target_image_path: str | None,
    camera_id: int,
    issue_token: bool,
    base_dir: Path,
) -> dict[str, object]:
    boto3 = cast(_Boto3Protocol, importlib.import_module("boto3"))
    rekognition = boto3.client("rekognition")

    if action == "create_collection":
        if not collection_id:
            return {
                "status": "error",
                "content": [
                    {"text": "collection_id is required for create_collection."}
                ],
            }
        resp = rekognition.create_collection(CollectionId=collection_id)
        payload: dict[str, object] = {
            "action": "create_collection",
            "provider": "rekognition",
            "collection_id": collection_id,
            "collection_arn": resp.get("CollectionArn"),
            "status_code": resp.get("StatusCode"),
        }
        return {
            "status": "success",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    if action == "list_collections":
        resp = rekognition.list_collections()
        collections = cast(list[str], resp.get("CollectionIds", []))
        payload = {
            "action": "list_collections",
            "provider": "rekognition",
            "collections": collections,
        }
        return {
            "status": "success",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    if action == "index_face":
        if not collection_id:
            return {
                "status": "error",
                "content": [
                    {"text": "collection_id is required for Rekognition index_face."}
                ],
            }
        image_bytes, width, height, source = _resolve_image_input(
            image_base64=image_base64,
            image_path=image_path,
            image_url=image_url,
            camera_id=camera_id,
        )
        ext_id = external_image_id or f"face_{int(time.time())}"
        resp = rekognition.index_faces(
            CollectionId=collection_id,
            Image={"Bytes": image_bytes},
            ExternalImageId=ext_id,
            DetectionAttributes=["ALL"],
        )
        records = cast(list[dict[str, object]], resp.get("FaceRecords", []))
        indexed_ids: list[str] = []
        for r in records:
            face_dict = cast(dict[str, object], r.get("Face", {}))
            indexed_ids.append(str(face_dict.get("FaceId", "")))
        payload = {
            "action": "index_face",
            "provider": "rekognition",
            "collection_id": collection_id,
            "external_image_id": ext_id,
            "face_ids": indexed_ids,
            "faces_indexed": len(records),
            "source": source,
            "width": width,
            "height": height,
        }
        return {
            "status": "success",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    if action in ("search_faces", "verify_face"):
        if not collection_id:
            return {
                "status": "error",
                "content": [
                    {"text": f"collection_id is required for Rekognition {action}."}
                ],
            }
        image_bytes, _, _, source = _resolve_image_input(
            image_base64=image_base64,
            image_path=image_path,
            image_url=image_url,
            camera_id=camera_id,
        )
        resp = rekognition.search_faces_by_image(
            CollectionId=collection_id,
            Image={"Bytes": image_bytes},
            FaceMatchThreshold=similarity_threshold,
            MaxFaces=max_faces,
        )
        matches_raw = cast(list[dict[str, object]], resp.get("FaceMatches", []))
        matches: list[dict[str, object]] = []
        for m in matches_raw:
            face_obj = cast(dict[str, object], m.get("Face", {}))
            matches.append(
                {
                    "face_id": face_obj.get("FaceId"),
                    "external_image_id": face_obj.get("ExternalImageId", "Unknown"),
                    "similarity": _as_float(m.get("Similarity"), 0.0),
                }
            )
        top_sim = _as_float(matches[0].get("similarity"), 0.0) if matches else 0.0
        matched = len(matches) > 0 and top_sim >= similarity_threshold
        payload = {
            "action": action,
            "provider": "rekognition",
            "collection_id": collection_id,
            "matched": matched,
            "matches": matches,
            "source": source,
        }
        if matched and (action == "verify_face" or issue_token):
            top = matches[0]
            subj = str(
                top.get("external_image_id") or top.get("face_id") or "verified_user"
            )
            payload["auth"] = _mint_face_jwt(
                base_dir=base_dir,
                subject=subj,
                amr=["face", "rekognition"],
                extra_claims={
                    "face_id": top.get("face_id"),
                    "similarity": top.get("similarity"),
                    "collection_id": collection_id,
                },
            )
        return {
            "status": "success" if (matched or action == "search_faces") else "error",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    if action == "compare_faces":
        src_bytes, _, _, src_source = _resolve_image_input(
            image_base64=image_base64,
            image_path=image_path,
            image_url=image_url,
            camera_id=camera_id,
        )
        tgt_bytes, _, _, tgt_source = _resolve_image_input(
            image_base64=target_image_base64,
            image_path=target_image_path,
            image_url=None,
            camera_id=camera_id,
            allow_camera_fallback=False,
        )
        resp = rekognition.compare_faces(
            SourceImage={"Bytes": src_bytes},
            TargetImage={"Bytes": tgt_bytes},
            SimilarityThreshold=similarity_threshold,
        )
        face_matches = cast(list[dict[str, object]], resp.get("FaceMatches", []))
        top_sim = (
            _as_float(face_matches[0].get("Similarity"), 0.0) if face_matches else 0.0
        )
        matched = top_sim >= similarity_threshold
        payload = {
            "action": "compare_faces",
            "provider": "rekognition",
            "matched": matched,
            "similarity": top_sim,
            "source": src_source,
            "target_source": tgt_source,
        }
        if matched and issue_token:
            payload["auth"] = _mint_face_jwt(
                base_dir=base_dir,
                subject=external_image_id or "compared_user",
                amr=["face", "rekognition"],
                extra_claims={"similarity": top_sim},
            )
        return {
            "status": "success",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    if action == "list_faces":
        if not collection_id:
            return {
                "status": "error",
                "content": [
                    {"text": "collection_id is required for Rekognition list_faces."}
                ],
            }
        resp = rekognition.list_faces(
            CollectionId=collection_id, MaxResults=max_faces
        )
        faces = cast(list[dict[str, object]], resp.get("Faces", []))
        payload = {
            "action": "list_faces",
            "provider": "rekognition",
            "collection_id": collection_id,
            "faces": [
                {
                    "face_id": f.get("FaceId"),
                    "external_image_id": f.get("ExternalImageId"),
                }
                for f in faces
            ],
        }
        return {
            "status": "success",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    if action == "delete_face":
        if not collection_id or not face_id:
            return {
                "status": "error",
                "content": [
                    {
                        "text": "collection_id and face_id are required for Rekognition delete_face."
                    }
                ],
            }
        rekognition.delete_faces(CollectionId=collection_id, FaceIds=[face_id])
        payload = {
            "action": "delete_face",
            "provider": "rekognition",
            "collection_id": collection_id,
            "deleted_face_id": face_id,
        }
        return {
            "status": "success",
            "content": [{"text": json.dumps(payload, indent=2)}],
        }

    return {
        "status": "error",
        "content": [{"text": f"Unsupported Rekognition action: {action}"}],
    }


@tool
def face_recognition(
    action: str,
    collection_id: str | None = None,
    external_image_id: str | None = None,
    face_id: str | None = None,
    similarity_threshold: float = 90.0,
    max_faces: int = 10,
    image_base64: str | None = None,
    image_path: str | None = None,
    image_url: str | None = None,
    target_image_base64: str | None = None,
    target_image_path: str | None = None,
    camera_id: int = 0,
    provider: str = "auto",
    save_dir: str | None = None,
    issue_token: bool = False,
    token: str | None = None,
    user_id: str | None = None,
    rp_id: str = "localhost",
    rp_name: str = "Strands Agent Factory",
    credential_id: str | None = None,
    public_key_spki_b64: str | None = None,
    client_data_json_b64: str | None = None,
    authenticator_data_b64: str | None = None,
    signature_b64: str | None = None,
    alg: int = -7,
) -> dict[str, object]:
    """Universal Face Recognition, Biometric Passkey (WebAuthn Face ID / Windows Hello / Android Biometric),
    and Camera-Frame Face Authorization tool across Mobile, Tablets, and Laptops.

    Args:
        action: One of:
            - Passkey / Biometric Hardware Face Auth (W3C WebAuthn Platform Authenticator):
              "challenge", "register_passkey", "authenticate_passkey", "list_passkeys",
              "delete_passkey", "verify_token"
            - Camera-Frame Face Enrollment, Search, Comparison & Verification:
              "capture", "index_face", "search_faces", "compare_faces", "verify_face",
              "list_faces", "delete_face", "create_collection", "list_collections"
        collection_id: Face collection identifier (defaults to "default" for local/Gemini store).
        external_image_id: User or external identifier associated with an enrolled face.
        face_id: Specific face ID for `delete_face` or single-face lookup.
        similarity_threshold: Minimum similarity score (0-100, default 90.0) to accept a match.
        max_faces: Maximum number of matching faces to return (default 10).
        image_base64: Base64 or `data:image/...;base64,...` encoded image from a mobile/tablet/laptop camera.
        image_path: Local file path to an image.
        image_url: HTTP/HTTPS URL of an image.
        target_image_base64: Second image (base64 or data URI) for `compare_faces`.
        target_image_path: Second image file path for `compare_faces`.
        camera_id: Local camera device index (default 0) when no image parameter is provided.
        provider: "auto" (default), "gemini", or "rekognition".
        save_dir: Directory for storing passkeys, challenges, face collections, and JWT secret.
        issue_token: When True, mints a signed Bearer JWT on successful `search_faces`/`compare_faces`.
        token: Bearer JWT string to verify when `action="verify_token"`.
        user_id: User identifier for WebAuthn passkey registration/challenge.
        rp_id: WebAuthn Relying Party ID (domain, e.g., "localhost" or "app.example.com").
        rp_name: WebAuthn Relying Party display name.
        credential_id: WebAuthn passkey credential ID (base64url string).
        public_key_spki_b64: Base64/base64url SPKI DER public key from `AuthenticatorAttestationResponse.getPublicKey()`.
        client_data_json_b64: Base64/base64url `clientDataJSON` from WebAuthn response.
        authenticator_data_b64: Base64/base64url `authenticatorData` from WebAuthn response.
        signature_b64: Base64/base64url cryptographic assertion signature from `AuthenticatorAssertionResponse.signature`.
        alg: COSE algorithm identifier (-7 for ES256 P-256, -257 for RS256, -8 for EdDSA).

    Returns:
        Dict with `status` ("success" or "error") and `content` list containing JSON payload.
    """
    try:
        base_dir = _resolve_save_dir(save_dir)
        act = action.strip().lower()

        # =====================================================================
        # 1. W3C WebAuthn Platform Passkey (Face ID / Windows Hello / Android)
        # =====================================================================
        if act == "challenge":
            challenge_str = secrets.token_urlsafe(32)
            now = time.time()
            expires_at = now + CHALLENGE_TTL_SECONDS
            uid = user_id or external_image_id or "strands_user"
            challenges = _load_challenges(base_dir)
            challenges[challenge_str] = {
                "challenge": challenge_str,
                "user_id": uid,
                "rp_id": rp_id,
                "created_at": now,
                "expires_at": expires_at,
            }
            _save_challenges(base_dir, challenges)

            passkeys = _load_passkeys(base_dir)
            allow_credentials = [
                {"type": "public-key", "id": cid, "transports": ["internal", "hybrid"]}
                for cid, meta in passkeys.items()
                if meta.get("rp_id") == rp_id
                and (not user_id or meta.get("user_id") == uid)
            ]

            payload: dict[str, object] = {
                "action": "challenge",
                "challenge": challenge_str,
                "rp_id": rp_id,
                "user_id": uid,
                "expires_in": CHALLENGE_TTL_SECONDS,
                "creation_options": {
                    "publicKey": {
                        "challenge": challenge_str,
                        "rp": {"name": rp_name, "id": rp_id},
                        "user": {
                            "id": _b64url_encode(uid.encode("utf-8")),
                            "name": uid,
                            "displayName": uid,
                        },
                        "pubKeyCredParams": [
                            {"type": "public-key", "alg": -7},
                            {"type": "public-key", "alg": -257},
                            {"type": "public-key", "alg": -8},
                        ],
                        "authenticatorSelection": {
                            "authenticatorAttachment": "platform",
                            "userVerification": "required",
                            "residentKey": "preferred",
                        },
                        "timeout": 60000,
                        "attestation": "none",
                    }
                },
                "request_options": {
                    "publicKey": {
                        "challenge": challenge_str,
                        "rpId": rp_id,
                        "allowCredentials": allow_credentials,
                        "userVerification": "required",
                        "timeout": 60000,
                    }
                },
            }
            return {
                "status": "success",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        if act == "register_passkey":
            if (
                not credential_id
                or not public_key_spki_b64
                or not client_data_json_b64
                or not authenticator_data_b64
            ):
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": (
                                "credential_id, public_key_spki_b64, client_data_json_b64, and "
                                "authenticator_data_b64 are required for register_passkey."
                            )
                        }
                    ],
                }

            client_data_bytes = _b64url_decode(client_data_json_b64)
            client_data = cast(
                dict[str, object], json.loads(client_data_bytes.decode("utf-8"))
            )
            if client_data.get("type") != "webauthn.create":
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Invalid clientDataJSON.type: expected 'webauthn.create', got {client_data.get('type')!r}."
                        }
                    ],
                }

            challenge_entry = _consume_challenge(
                base_dir, str(client_data.get("challenge", ""))
            )
            if challenge_entry is None:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "Invalid, expired, or already-used WebAuthn challenge."
                        }
                    ],
                }

            expected_rp_id = str(challenge_entry.get("rp_id") or rp_id)
            auth_data_bytes = _b64url_decode(authenticator_data_b64)
            parsed_auth = _parse_authenticator_data(auth_data_bytes)
            expected_rp_hash = hashlib.sha256(expected_rp_id.encode("utf-8")).digest()
            if parsed_auth["rp_id_hash"] != expected_rp_hash:
                return {
                    "status": "error",
                    "content": [
                        {"text": f"RP ID hash mismatch for rp_id={expected_rp_id!r}."}
                    ],
                }

            if not parsed_auth["user_present"] or not parsed_auth["user_verified"]:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": (
                                "Biometric User Verification (UV=0x04) and User Presence (UP=0x01) "
                                "flags are required for hardware Face ID / Windows Hello / Android Biometric."
                            )
                        }
                    ],
                }

            spki_der = _b64url_decode(public_key_spki_b64)
            pub_key = load_der_public_key(spki_der)
            if not isinstance(
                pub_key,
                (
                    ec.EllipticCurvePublicKey,
                    rsa.RSAPublicKey,
                    ed25519.Ed25519PublicKey,
                ),
            ):
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Unsupported public key type: {type(pub_key).__name__}"
                        }
                    ],
                }
            normalized_spki_b64 = _b64url_encode(
                pub_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
            )

            uid = (
                user_id
                or external_image_id
                or str(challenge_entry.get("user_id", "strands_user"))
            )
            passkeys = _load_passkeys(base_dir)
            now = time.time()
            sign_count_val = _as_int(parsed_auth.get("sign_count"), 0)
            passkeys[credential_id] = {
                "credential_id": credential_id,
                "user_id": uid,
                "rp_id": expected_rp_id,
                "alg": alg,
                "key_type": type(pub_key).__name__,
                "public_key_spki_b64": normalized_spki_b64,
                "sign_count": sign_count_val,
                "backup_eligible": bool(parsed_auth["backup_eligible"]),
                "backup_state": bool(parsed_auth["backup_state"]),
                "created_at": now,
                "last_used_at": now,
            }
            _save_passkeys(base_dir, passkeys)

            auth_token = _mint_face_jwt(
                base_dir=base_dir,
                subject=uid,
                amr=["face", "pop", "hwk"],
                extra_claims={
                    "credential_id": credential_id,
                    "rp_id": expected_rp_id,
                    "uv": True,
                },
            )
            payload = {
                "action": "register_passkey",
                "registered": True,
                "credential_id": credential_id,
                "user_id": uid,
                "rp_id": expected_rp_id,
                "key_type": type(pub_key).__name__,
                "sign_count": sign_count_val,
                "auth": auth_token,
            }
            return {
                "status": "success",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        if act == "authenticate_passkey":
            if (
                not credential_id
                or not client_data_json_b64
                or not authenticator_data_b64
                or not signature_b64
            ):
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": (
                                "credential_id, client_data_json_b64, authenticator_data_b64, and "
                                "signature_b64 are required for authenticate_passkey."
                            )
                        }
                    ],
                }

            passkeys = _load_passkeys(base_dir)
            stored = passkeys.get(credential_id)
            if stored is None:
                return {
                    "status": "error",
                    "content": [
                        {"text": f"Unknown passkey credential_id: {credential_id!r}"}
                    ],
                }

            client_data_bytes = _b64url_decode(client_data_json_b64)
            client_data = cast(
                dict[str, object], json.loads(client_data_bytes.decode("utf-8"))
            )
            if client_data.get("type") != "webauthn.get":
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Invalid clientDataJSON.type: expected 'webauthn.get', got {client_data.get('type')!r}."
                        }
                    ],
                }

            challenge_entry = _consume_challenge(
                base_dir, str(client_data.get("challenge", ""))
            )
            if challenge_entry is None:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "Invalid, expired, or already-used WebAuthn challenge."
                        }
                    ],
                }

            expected_rp_id = str(stored.get("rp_id") or rp_id)
            auth_data_bytes = _b64url_decode(authenticator_data_b64)
            parsed_auth = _parse_authenticator_data(auth_data_bytes)
            expected_rp_hash = hashlib.sha256(expected_rp_id.encode("utf-8")).digest()
            if parsed_auth["rp_id_hash"] != expected_rp_hash:
                return {
                    "status": "error",
                    "content": [
                        {"text": f"RP ID hash mismatch for rp_id={expected_rp_id!r}."}
                    ],
                }

            if not parsed_auth["user_present"] or not parsed_auth["user_verified"]:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": (
                                "Biometric User Verification (UV=0x04) and User Presence (UP=0x01) "
                                "flags are required."
                            )
                        }
                    ],
                }

            prev_count = _as_int(stored.get("sign_count"), 0)
            new_count = _as_int(parsed_auth.get("sign_count"), 0)
            if (prev_count > 0 or new_count > 0) and new_count <= prev_count:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": (
                                f"Passkey sign_count replay detected: received {new_count} <= stored {prev_count}."
                            )
                        }
                    ],
                }

            spki_der = _b64url_decode(str(stored["public_key_spki_b64"]))
            pub_key = load_der_public_key(spki_der)
            sig_bytes = _b64url_decode(signature_b64)
            signed_payload = (
                auth_data_bytes + hashlib.sha256(client_data_bytes).digest()
            )

            if isinstance(pub_key, ec.EllipticCurvePublicKey):
                if len(sig_bytes) == 64 and sig_bytes[0] != 0x30:
                    r_int = int.from_bytes(
                        sig_bytes[:32], byteorder="big", signed=False
                    )
                    s_int = int.from_bytes(
                        sig_bytes[32:], byteorder="big", signed=False
                    )
                    sig_bytes = encode_dss_signature(r_int, s_int)
                pub_key.verify(sig_bytes, signed_payload, ec.ECDSA(hashes.SHA256()))
            elif isinstance(pub_key, rsa.RSAPublicKey):
                pub_key.verify(
                    sig_bytes, signed_payload, padding.PKCS1v15(), hashes.SHA256()
                )
            elif isinstance(pub_key, ed25519.Ed25519PublicKey):
                pub_key.verify(sig_bytes, signed_payload)
            else:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Unsupported public key type: {type(pub_key).__name__}"
                        }
                    ],
                }

            stored["sign_count"] = new_count
            stored["last_used_at"] = time.time()
            passkeys[credential_id] = stored
            _save_passkeys(base_dir, passkeys)

            uid = str(stored.get("user_id", "strands_user"))
            auth_token = _mint_face_jwt(
                base_dir=base_dir,
                subject=uid,
                amr=["face", "pop", "hwk"],
                extra_claims={
                    "credential_id": credential_id,
                    "rp_id": expected_rp_id,
                    "sign_count": new_count,
                    "uv": True,
                },
            )
            payload = {
                "action": "authenticate_passkey",
                "authenticated": True,
                "credential_id": credential_id,
                "user_id": uid,
                "rp_id": expected_rp_id,
                "sign_count": new_count,
                "auth": auth_token,
            }
            return {
                "status": "success",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        if act == "list_passkeys":
            passkeys = _load_passkeys(base_dir)
            items = [
                {
                    "credential_id": cid,
                    "user_id": meta.get("user_id"),
                    "rp_id": meta.get("rp_id"),
                    "alg": meta.get("alg"),
                    "key_type": meta.get("key_type"),
                    "sign_count": meta.get("sign_count"),
                    "created_at": meta.get("created_at"),
                    "last_used_at": meta.get("last_used_at"),
                }
                for cid, meta in passkeys.items()
                if not user_id or meta.get("user_id") == user_id
            ]
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "list_passkeys",
                                "count": len(items),
                                "passkeys": items,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if act == "delete_passkey":
            if not credential_id:
                return {
                    "status": "error",
                    "content": [
                        {"text": "credential_id is required for delete_passkey."}
                    ],
                }
            passkeys = _load_passkeys(base_dir)
            removed = passkeys.pop(credential_id, None)
            if removed is None:
                return {
                    "status": "error",
                    "content": [{"text": f"Passkey {credential_id!r} not found."}],
                }
            _save_passkeys(base_dir, passkeys)
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "delete_passkey",
                                "deleted": True,
                                "credential_id": credential_id,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if act == "verify_token":
            if not token:
                return {
                    "status": "error",
                    "content": [{"text": "token is required for verify_token."}],
                }
            claims = _verify_face_jwt(base_dir, token)
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "verify_token",
                                "valid": True,
                                "claims": claims,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        # =====================================================================
        # 2. Camera-Frame Capture, Enrollment, Search, Compare & Verify
        # =====================================================================
        if act == "capture":
            jpg_bytes, width, height, source = _resolve_image_input(
                image_base64=image_base64,
                image_path=image_path,
                image_url=image_url,
                camera_id=camera_id,
            )
            captures_dir = base_dir / "captures"
            captures_dir.mkdir(parents=True, exist_ok=True)
            out_file = captures_dir / f"capture_{int(time.time() * 1000)}.jpg"
            out_file.write_bytes(jpg_bytes)
            payload = {
                "action": "capture",
                "status": "captured",
                "source": source,
                "width": width,
                "height": height,
                "size_bytes": len(jpg_bytes),
                "saved_path": str(out_file),
                "image_base64": base64.b64encode(jpg_bytes).decode("ascii"),
            }
            return {
                "status": "success",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        if _use_rekognition(provider, collection_id):
            return _run_rekognition(
                action=act,
                collection_id=collection_id,
                external_image_id=external_image_id,
                face_id=face_id,
                similarity_threshold=similarity_threshold,
                max_faces=max_faces,
                image_base64=image_base64,
                image_path=image_path,
                image_url=image_url,
                target_image_base64=target_image_base64,
                target_image_path=target_image_path,
                camera_id=camera_id,
                issue_token=issue_token,
                base_dir=base_dir,
            )

        # Local + Gemini Vision Face Collection Store
        if act == "create_collection":
            cid = (collection_id or "default").strip() or "default"
            cdir = _collection_dir(base_dir, cid)
            faces = _load_collection_faces(cdir)
            _save_collection_faces(cdir, faces)
            payload = {
                "action": "create_collection",
                "provider": "gemini",
                "collection_id": cid,
                "path": str(cdir),
                "face_count": len(faces),
            }
            return {
                "status": "success",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        if act == "list_collections":
            cols_root = base_dir / "collections"
            cols_root.mkdir(parents=True, exist_ok=True)
            names = sorted(p.name for p in cols_root.iterdir() if p.is_dir())
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "list_collections",
                                "provider": "gemini",
                                "collections": names,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if act == "index_face":
            cid = (collection_id or "default").strip() or "default"
            cdir = _collection_dir(base_dir, cid)
            jpg_bytes, width, height, source = _resolve_image_input(
                image_base64=image_base64,
                image_path=image_path,
                image_url=image_url,
                camera_id=camera_id,
            )
            new_face_id = face_id or str(uuid.uuid4())
            ext_id = external_image_id or user_id or f"face_{int(time.time())}"
            img_file = cdir / f"{new_face_id}.jpg"
            img_file.write_bytes(jpg_bytes)

            faces = _load_collection_faces(cdir)
            faces = [f for f in faces if f.get("face_id") != new_face_id]
            record: dict[str, object] = {
                "face_id": new_face_id,
                "external_image_id": ext_id,
                "collection_id": cid,
                "image_file": img_file.name,
                "width": width,
                "height": height,
                "sha256": hashlib.sha256(jpg_bytes).hexdigest(),
                "source": source,
                "created_at": time.time(),
            }
            faces.append(record)
            _save_collection_faces(cdir, faces)
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "index_face",
                                "provider": "gemini",
                                "collection_id": cid,
                                "face_id": new_face_id,
                                "external_image_id": ext_id,
                                "width": width,
                                "height": height,
                                "source": source,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if act == "list_faces":
            cid = (collection_id or "default").strip() or "default"
            cdir = _collection_dir(base_dir, cid)
            faces = _load_collection_faces(cdir)[:max_faces]
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "list_faces",
                                "provider": "gemini",
                                "collection_id": cid,
                                "count": len(faces),
                                "faces": faces,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if act == "delete_face":
            if not face_id:
                return {
                    "status": "error",
                    "content": [{"text": "face_id is required for delete_face."}],
                }
            cid = (collection_id or "default").strip() or "default"
            cdir = _collection_dir(base_dir, cid)
            faces = _load_collection_faces(cdir)
            remaining = [f for f in faces if f.get("face_id") != face_id]
            if len(remaining) == len(faces):
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"face_id {face_id!r} not found in collection {cid!r}."
                        }
                    ],
                }
            _save_collection_faces(cdir, remaining)
            img_file = cdir / f"{face_id}.jpg"
            if img_file.exists():
                try:
                    img_file.unlink()
                except OSError:
                    pass
            return {
                "status": "success",
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "action": "delete_face",
                                "provider": "gemini",
                                "collection_id": cid,
                                "deleted_face_id": face_id,
                            },
                            indent=2,
                        )
                    }
                ],
            }

        if act in ("search_faces", "verify_face"):
            cid = (collection_id or "default").strip() or "default"
            cdir = _collection_dir(base_dir, cid)
            faces = _load_collection_faces(cdir)
            if face_id:
                faces = [f for f in faces if f.get("face_id") == face_id]
            if external_image_id:
                faces = [
                    f for f in faces if f.get("external_image_id") == external_image_id
                ]
            if not faces:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": (
                                f"No enrolled faces found in collection {cid!r}. "
                                "Enroll a face first with action='index_face'."
                            )
                        }
                    ],
                }

            query_jpg, _, _, source = _resolve_image_input(
                image_base64=image_base64,
                image_path=image_path,
                image_url=image_url,
                camera_id=camera_id,
            )

            candidates: list[dict[str, object]] = []
            for f in faces[:max_faces]:
                img_path = cdir / str(f.get("image_file", f"{f.get('face_id')}.jpg"))
                if img_path.exists():
                    candidates.append(
                        {
                            "face_id": f.get("face_id"),
                            "external_image_id": f.get("external_image_id"),
                            "image_bytes": img_path.read_bytes(),
                        }
                    )

            result = _gemini_compare_faces(
                query_jpg=query_jpg,
                candidates=candidates,
                similarity_threshold=similarity_threshold,
            )
            similarity = _as_float(result.get("similarity"), 0.0)
            liveness_ok = bool(result.get("liveness_check_passed", False))
            matched = (
                bool(result.get("matched", False))
                and similarity >= similarity_threshold
                and liveness_ok
            )

            payload = {
                "action": act,
                "provider": "gemini",
                "model": result.get("model"),
                "collection_id": cid,
                "matched": matched,
                "similarity": similarity,
                "face_id": result.get("face_id"),
                "external_image_id": result.get("external_image_id"),
                "liveness_check_passed": liveness_ok,
                "reasoning": result.get("reasoning"),
                "source": source,
            }
            if matched and (act == "verify_face" or issue_token):
                subj = str(
                    result.get("external_image_id")
                    or result.get("face_id")
                    or user_id
                    or "verified_user"
                )
                payload["auth"] = _mint_face_jwt(
                    base_dir=base_dir,
                    subject=subj,
                    amr=["face"],
                    extra_claims={
                        "face_id": result.get("face_id"),
                        "collection_id": cid,
                        "similarity": similarity,
                        "liveness_check_passed": liveness_ok,
                    },
                )
            return {
                "status": "success" if (matched or act == "search_faces") else "error",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        if act == "compare_faces":
            src_jpg, _, _, src_source = _resolve_image_input(
                image_base64=image_base64,
                image_path=image_path,
                image_url=image_url,
                camera_id=camera_id,
            )
            tgt_jpg, _, _, tgt_source = _resolve_image_input(
                image_base64=target_image_base64,
                image_path=target_image_path,
                image_url=None,
                camera_id=camera_id,
                allow_camera_fallback=False,
            )
            result = _gemini_compare_faces(
                query_jpg=src_jpg,
                candidates=[
                    {
                        "face_id": face_id or "target_face",
                        "external_image_id": external_image_id
                        or user_id
                        or "target_user",
                        "image_bytes": tgt_jpg,
                    }
                ],
                similarity_threshold=similarity_threshold,
            )
            similarity = _as_float(result.get("similarity"), 0.0)
            liveness_ok = bool(result.get("liveness_check_passed", False))
            matched = (
                bool(result.get("matched", False))
                and similarity >= similarity_threshold
                and liveness_ok
            )
            payload = {
                "action": "compare_faces",
                "provider": "gemini",
                "model": result.get("model"),
                "matched": matched,
                "similarity": similarity,
                "liveness_check_passed": liveness_ok,
                "reasoning": result.get("reasoning"),
                "source": src_source,
                "target_source": tgt_source,
            }
            if matched and issue_token:
                subj = external_image_id or user_id or "compared_user"
                payload["auth"] = _mint_face_jwt(
                    base_dir=base_dir,
                    subject=subj,
                    amr=["face"],
                    extra_claims={
                        "similarity": similarity,
                        "liveness_check_passed": liveness_ok,
                    },
                )
            return {
                "status": "success",
                "content": [{"text": json.dumps(payload, indent=2)}],
            }

        return {
            "status": "error",
            "content": [{"text": f"Unknown action: {action!r}"}],
        }

    except Exception as exc:
        return {
            "status": "error",
            "content": [{"text": f"Error in face_recognition ({action}): {exc}"}],
        }
