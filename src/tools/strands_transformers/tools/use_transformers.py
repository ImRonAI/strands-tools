"""use_transformers - THE universal entrypoint to all of HuggingFace transformers.

Like `use_aws` wraps boto3 and `use_lerobot` wraps lerobot, this wraps the entire
transformers library with ZERO hardcoded operations. It is the single tool an
agent needs to run any of transformers' tasks across every modality:

    image / video / audio / text / robot-state  IN
    text / audio / image / labels / actions      OUT   - natively.

It has two layers:

1. RUN (high-level): use transformers.pipeline() - the native multimodal runner.
   Input can be a file path, URL, base64 data-URI, raw text, or numpy array.
   Output (audio, images) is auto-saved to disk and returned by path.

       use_transformers(action="run", task="image-text-to-text",
                        model="allenai/MolmoAct2-SO100_101",
                        inputs={"images": "scene.jpg", "text": "pick the cube"})

       use_transformers(action="run", task="automatic-speech-recognition",
                        inputs="recording.wav")

       use_transformers(action="run", task="text-to-audio", model="suno/bark-small",
                        inputs="Hello from Strands!")

2. CALL (low-level): dynamically resolve & call ANY transformers class / function /
   method - AutoModelForImageTextToText, AutoProcessor, model.generate, etc. For
   VLA / robot-action models that need processor(images, text, state) → model(**).

       use_transformers(action="call", target="AutoProcessor.from_pretrained",
                        parameters={"pretrained_model_name_or_path": "model_id"},
                        cache_key="proc")
       use_transformers(action="call", target="cached:model.generate",
                        parameters={...})

Discovery (so the agent never guesses):
       use_transformers(action="tasks")                 # all tasks + modality + models
       use_transformers(action="modalities")            # tasks grouped by modality
       use_transformers(action="task_info", task="...") # auto-model, default, io type
       use_transformers(action="classes")               # all Auto* entrypoints
       use_transformers(action="inspect", target="...") # signature + docs of anything
       use_transformers(action="cache")                 # list cached objects
       use_transformers(action="clear_cache")           # free memory
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import traceback
from typing import Any, Dict, Optional

from strands import tool

from strands_transformers.core import engine, io, registry

logger = logging.getLogger(__name__)


def _apply_compat() -> None:
    """Apply backward-compat shims for legacy trust_remote_code models."""
    try:
        from strands_transformers.core import compat

        compat.apply()
    except Exception as e:  # pragma: no cover
        logger.debug("compat.apply skipped: %s", e)


def _ensure(package: str) -> None:
    import importlib

    try:
        importlib.import_module(package)
    except ImportError:
        logger.info("Installing %s ...", package)
        subprocess.run([sys.executable, "-m", "pip", "install", package], check=True, timeout=600)


def _ok(text: str, **extra: Any) -> Dict[str, Any]:
    payload = {"status": "success", "content": [{"text": text}]}
    payload.update(extra)
    return payload


def _err(text: str) -> Dict[str, Any]:
    return {"status": "error", "content": [{"text": text}]}


@tool
def use_transformers(
    action: str = "tasks",
    task: Optional[str] = None,
    model: Optional[str] = None,
    inputs: Any = None,
    target: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    cache_key: Optional[str] = None,
    device: Optional[str] = None,
    save_artifacts: bool = True,
    label: str = "",
) -> Dict[str, Any]:
    """Universal access to ALL transformers functionality - no hardcoding.

    Args:
        action: What to do:
            run          - run a transformers pipeline for `task` on `inputs` (native multimodal)
            call         - dynamically call any transformers class/function/method via `target`
            tasks        - list every supported task with modality + auto-model + default model
            modalities   - list tasks grouped by modality (text/image/audio/video/multimodal)
            task_info    - details for one `task` (modality, auto-models, default model)
            classes      - list every Auto* entrypoint (AutoModelForImageTextToText, ...)
            inspect      - signature + docstring of any `target`
            cache        - list cached pipelines/models
            clear_cache  - free a `cache_key` (or everything)
            compat       - apply legacy-model shims (for old trust_remote_code models like
                           OpenVLA); optional parameters={"timm_version": "0.9.16"}
        task: A transformers task name (e.g. "image-text-to-text", "automatic-speech-recognition").
        model: HF model id or local path. If omitted, the task's default model is used.
        inputs: The data to run on - file path / URL / base64 / text / dict / numpy list.
                For multimodal tasks pass a dict, e.g. {"images": "x.jpg", "text": "..."}.
        target: For action="call"/"inspect": dotted path into transformers, e.g.
                "pipeline", "AutoModelForCausalLM.from_pretrained", "cached:key.method".
        parameters: kwargs for the call / pipeline.
        cache_key: name to cache (or fetch) a loaded object under.
        device: "cuda" / "mps" / "cpu" / "auto" (default auto-detect).
        save_artifacts: write generated audio/images to disk and return paths.
        label: human-readable description for logging.

    Returns:
        Dict with status + content; "run"/"call" also include "data" (JSON-safe result)
        and optionally "artifacts" (paths to generated media).
    """
    # Copy so popping pipeline_kwargs never mutates the caller's dict.
    params = dict(parameters) if parameters else {}
    try:
        # ───────── discovery ─────────
        if action == "tasks":
            tasks = registry.supported_tasks()
            lines = [f"🤗 transformers supports {len(tasks)} tasks (100% coverage):\n"]
            for t in sorted(tasks):
                info = tasks[t]
                am = ", ".join(info["auto_models"]) or "-"
                lines.append(f"  • {t}  [{info['type']}]")
                lines.append(f"      auto: {am}")
                if info["default_model"]:
                    lines.append(f"      default: {info['default_model']}")
            lines.append('\n💡 run:  use_transformers(action="run", task="<task>", inputs=...)')
            return _ok("\n".join(lines), data=tasks)

        if action == "modalities":
            groups = registry.tasks_by_modality()
            lines = ["🎛️  Tasks by modality:\n"]
            for mod in sorted(groups):
                lines.append(f"  {mod}:")
                for t in groups[mod]:
                    lines.append(f"      • {t}")
            return _ok("\n".join(lines), data=groups)

        if action == "task_info":
            if not task:
                return _err("Provide `task`.")
            resolved = registry.resolve_task(task)
            if not resolved:
                return _err(f"Unknown task '{task}'. Use action='tasks' to list all.")
            info = registry.task_info(resolved)
            return _ok(
                f"🔍 {resolved}\n{json.dumps(info, indent=2)}", data={"task": resolved, **info}
            )

        if action == "classes":
            classes = registry.auto_model_classes()
            return _ok("🏗️  Auto* entrypoints:\n  " + "\n  ".join(classes), data=classes)

        if action == "inspect":
            if not target:
                return _err("Provide `target` (e.g. 'pipeline' or 'AutoModelForCausalLM').")
            obj = _resolve_target(target)
            info = registry.describe(obj)
            return _ok(f"🔍 {target}\n{json.dumps(info, indent=2, default=str)}", data=info)

        if action == "cache":
            c = engine.cache_list()
            if not c:
                return _ok("📦 cache empty")
            return _ok("📦 cached:\n" + "\n".join(f"  • {k}: {v}" for k, v in c.items()), data=c)

        if action == "clear_cache":
            n = engine.cache_clear(cache_key)
            return _ok(f"🧹 cleared {n} object(s)")

        if action == "compat":
            # Apply backward-compat shims for legacy trust_remote_code models
            # (e.g. OpenVLA): tokenizer symbol moves, AutoModelForVision2Seq
            # alias, tie_weights kwarg tolerance. Optionally spoof a timm version
            # for models with hard timm pins (pass parameters={"timm_version": "0.9.16"}).
            from strands_transformers.core import compat

            compat.apply(force=True)
            timm_version = (params or {}).get("timm_version")
            note = ""
            if timm_version:
                # Set persistently (not via the restoring context manager) so the
                # spoof stays in effect for subsequent load calls in this session.
                try:
                    import timm

                    timm.__version__ = timm_version
                    note = f" + spoofed timm.__version__={timm_version}"
                except ImportError:
                    note = " (timm not installed; spoof skipped)"
            return _ok(
                "🩹 compat shims applied (tokenization_utils symbols, "
                f"AutoModelForVision2Seq alias, tie_weights tolerance){note}"
            )

        # ───────── run (pipeline) ─────────
        if action == "run":
            if not task:
                return _err("Provide `task`. Use action='tasks' to list options.")
            resolved = registry.resolve_task(task)
            if not resolved:
                return _err(f"Unknown task '{task}'. Use action='tasks' to list all.")
            _ensure("transformers")
            # `pipeline_kwargs` configures pipeline construction (e.g. dtype,
            # device_map); everything else in `parameters` is passed at call time.
            pipeline_kwargs = params.pop("pipeline_kwargs", {}) if isinstance(params, dict) else {}
            pipe, key = engine.get_pipeline(
                resolved, model=model, device=device, cache_key=cache_key, **pipeline_kwargs
            )
            call_args, call_kwargs = _prepare_run_inputs(inputs, params, resolved)
            if label:
                logger.info("run %s (%s): %s", resolved, model or "default", label)
            result = pipe(*call_args, **call_kwargs)
            out = io.serialize_output(result, task=resolved, save_artifacts=save_artifacts)
            text = _summarize_run(resolved, out, key)
            return _ok(text, data=out.get("result"), artifacts=out.get("artifacts", []))

        # ───────── call (dynamic) ─────────
        if action == "call":
            if not target:
                return _err(
                    "Provide `target` (e.g. 'AutoModelForImageTextToText.from_pretrained')."
                )
            _ensure("transformers")
            _apply_compat()
            # AutoX.from_pretrained gets the engine's smart device/dtype defaults
            # (auto cuda/mps/cpu + bf16, trust_remote_code) via load_object -
            # explicit user params always win. Other targets stay fully raw.
            if (
                not target.startswith("cached:")
                and target.endswith(".from_pretrained")
                and params.get("pretrained_model_name_or_path") is not None
            ):
                auto_class = target[: -len(".from_pretrained")]
                model_path = params["pretrained_model_name_or_path"]
                extra = {
                    k: _coerce_param(v)
                    for k, v in params.items()
                    if k != "pretrained_model_name_or_path"
                }
                obj_loaded, _ = engine.load_object(
                    auto_class, model_path, cache_key=cache_key, **extra
                )
                if cache_key:
                    return _ok(
                        f"✅ {target}() → cached as '{cache_key}' ({type(obj_loaded).__name__})",
                        data={"cached": cache_key, "type": type(obj_loaded).__name__},
                    )
                out = io.serialize_output(obj_loaded, save_artifacts=save_artifacts)
                return _ok(
                    f"✅ {target}() → {type(obj_loaded).__name__}",
                    data=out.get("result"),
                    artifacts=out.get("artifacts", []),
                )

            obj = _resolve_target(target)
            if not callable(obj):
                return _ok(f"📋 {target} = {str(obj)[:500]}", data=str(obj)[:2000])
            coerced = {k: _coerce_param(v) for k, v in params.items()}
            # Support unpacking a cached mapping into kwargs via the "**" key,
            # e.g. {"**": "cached:batch"} → model.predict_action(**batch). This
            # makes the common `model(**processor_output)` pattern first-class.
            unpacked = coerced.pop("**", None)
            if unpacked is not None:
                try:
                    coerced = {**dict(unpacked), **coerced}
                except (TypeError, ValueError) as ue:
                    return _err(f"❌ '**' value is not a mapping: {ue}")
            result = obj(**coerced)
            if cache_key:
                engine._CACHE[cache_key] = result  # cache raw object (model/processor)
                return _ok(
                    f"✅ {target}() → cached as '{cache_key}' ({type(result).__name__})",
                    data={"cached": cache_key, "type": type(result).__name__},
                )
            out = io.serialize_output(result, save_artifacts=save_artifacts)
            preview = json.dumps(out.get("result"), indent=2, default=str)
            if len(preview) > 2000:
                preview = preview[:2000] + " …"
            arts = out.get("artifacts", [])
            head = f"✅ {target}() → {type(result).__name__}"
            if arts:
                head += "\n📎 artifacts:\n" + "\n".join(f"  • {a}" for a in arts)
            return _ok(f"{head}\n{preview}", data=out.get("result"), artifacts=arts)

        return _err(
            f"Unknown action '{action}'. Try: tasks, modalities, task_info, "
            f"classes, inspect, run, call, cache, clear_cache."
        )

    except TypeError as e:
        # surface expected signature on bad params
        hint = ""
        try:
            if target:
                hint = "\n\nExpected:\n" + json.dumps(
                    registry.describe(_resolve_target(target)), indent=2, default=str
                )
        except Exception:
            pass
        return _err(f"❌ TypeError: {e}{hint}")
    except (AttributeError, ImportError, ValueError, KeyError, FileNotFoundError, OSError) as e:
        # Benign user-input errors (bad target/task/params) - return cleanly
        # without spamming a full traceback to the logs.
        logger.debug("use_transformers(%s) input error: %s", action, e)
        return _err(f"❌ {type(e).__name__}: {e}")
    except Exception as e:
        # Genuinely unexpected - keep the full traceback for debugging.
        logger.error("use_transformers(%s) failed: %s", action, e, exc_info=True)
        return _err(f"❌ {type(e).__name__}: {e}\n\n{traceback.format_exc()[-800:]}")


def _resolve_target(target: str) -> Any:
    """Resolve a target which may reference a cached object."""
    if target.startswith("cached:"):
        ref = target[len("cached:") :]
        head, _, tail = ref.partition(".")
        obj = engine.cache_get(head)
        if obj is None:
            raise ValueError(f"No cached object '{head}'. Use action='cache' to list.")
        for attr in filter(None, tail.split(".")):
            obj = getattr(obj, attr)
        return obj
    try:
        return registry.resolve_attr(target)
    except AttributeError:
        # A legacy alias (e.g. AutoModelForVision2Seq) may have been clobbered by
        # a model's remote code re-importing transformers. Re-assert and retry.
        try:
            from strands_transformers.core import compat

            compat.apply(force=True)
        except Exception:
            pass
        return registry.resolve_attr(target)


def _coerce_param(value: Any) -> Any:
    """Coerce a single parameter value.

    Resolves "cached:key[.attr]" strings to live cached objects (so VLA models
    can receive e.g. processor=cached:proc), then applies multimodal input
    coercion (base64/data-uri → PIL/bytes) to everything else.
    """
    if isinstance(value, str) and value.startswith("cached:"):
        return _resolve_target(value)
    if isinstance(value, list):
        return [_coerce_param(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce_param(v) for k, v in value.items()}
    return io.coerce_input(value)


def _prepare_run_inputs(inputs: Any, params: Dict[str, Any], task: str = ""):
    """Map `inputs` + `parameters` onto a pipeline call.

    Pipelines accept either a positional input (text/path/url/image) or, for
    multimodal tasks, keyword inputs (images=, text=, audio=, ...). We coerce
    base64/data-uris and pass everything else through natively.

    For audio tasks (ASR, audio-classification) a `.wav` path is pre-decoded with
    the stdlib wave reader into a {"raw", "sampling_rate"} dict, so transcription
    works without ffmpeg / torchcodec / soundfile installed.
    """
    kwargs = {k: io.coerce_input(v) for k, v in params.items()}

    # Pre-decode WAV paths for audio-INPUT tasks → positional {"raw","sampling_rate"}.
    # Exclude generative audio-OUTPUT tasks (text-to-audio/-speech) whose input is text.
    _audio_input_task = ("audio" in task or "speech" in task) and not task.startswith("text-to-")
    if _audio_input_task:
        decoded = io.maybe_decode_audio_path(inputs)
        if decoded is not None:
            return [decoded], kwargs

    # video-classification wants a single (T, H, W, C) array, not a list of
    # frames - stack a frame list so callers can pass either.
    if task == "video-classification" and isinstance(inputs, (list, tuple)) and inputs:
        try:
            import numpy as np

            frames = [np.asarray(io.coerce_input(f)) for f in inputs]
            if frames and frames[0].ndim == 3:
                return [np.stack(frames, axis=0)], kwargs
        except Exception:
            pass

    if inputs is None:
        return [], kwargs
    if isinstance(inputs, dict):
        # An explicit raw-audio dict is a positional input, not kwargs.
        if "raw" in inputs and "sampling_rate" in inputs:
            return [{k: io.coerce_input(v) for k, v in inputs.items()}], kwargs
        merged = {k: io.coerce_input(v) for k, v in inputs.items()}
        # image-text-to-text chat models require images INSIDE the chat content,
        # not as a separate `images` arg. If the caller passed both chat `text`
        # and a separate `images`, fold the image(s) into the first user message
        # so the agent doesn't need to know the exact chat schema.
        if task == "image-text-to-text":
            merged = _embed_images_in_chat(merged)
        merged.update(kwargs)
        return [], merged
    return [io.coerce_input(inputs)], kwargs


def _embed_images_in_chat(merged: Dict[str, Any]) -> Dict[str, Any]:
    """Fold a separate `images` value into chat `text` message content.

    Turns {"text": [chat...], "images": img} into a valid image-text-to-text
    call where each image is a content block in the first user message. No-op if
    there's no separate images arg or text isn't a chat list.
    """
    text = merged.get("text")
    images = merged.get("images")
    if images is None or not isinstance(text, list):
        return merged

    imgs = images if isinstance(images, list) else [images]
    image_blocks = [{"type": "image", "image": im} for im in imgs]

    for msg in text:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                # prepend images if none already present
                if not any(isinstance(b, dict) and b.get("type") == "image" for b in content):
                    msg["content"] = image_blocks + content
            elif isinstance(content, str):
                msg["content"] = image_blocks + [{"type": "text", "text": content}]
            break
    merged.pop("images", None)
    return merged


def _summarize_run(task: str, out: Dict[str, Any], key: str) -> str:
    arts = out.get("artifacts", [])
    head = f"✅ {task} ({key})"
    if arts:
        head += "\n📎 artifacts:\n" + "\n".join(f"  • {a}" for a in arts)
    preview = json.dumps(out.get("result"), indent=2, default=str)
    if len(preview) > 2000:
        preview = preview[:2000] + " …"
    return f"{head}\n{preview}"


__all__ = ["use_transformers"]
