"""use_diffusers — THE universal entrypoint to all of HuggingFace diffusers.

Like `use_aws` wraps boto3, `use_lerobot` wraps lerobot, and `use_transformers`
wraps the transformers task taxonomy, this wraps the entire diffusers library with
ZERO hardcoded operations. It is the single tool an agent needs to run any of
diffusers' 300+ pipelines across every modality:

    text / image / video / robot-state  IN
    image / video / audio / ACTIONS      OUT   — natively.

It has two layers:

1. RUN (high-level): construct a pipeline class via from_pretrained and call it.
   Inputs are coerced (paths/URLs/base64 → PIL/video). Outputs (images, video,
   audio, robot actions) are auto-serialized to disk and returned by path.

       use_diffusers(action="run", pipeline="StableDiffusionPipeline",
                     model="runwayml/stable-diffusion-v1-5",
                     parameters={"prompt": "a robot in a kitchen",
                                 "num_inference_steps": 25})

       # World-foundation model action-policy rollout (Cosmos3): returns BOTH a
       # generated world video AND the predicted robot action chunk.
       use_diffusers(action="run", pipeline="Cosmos3OmniPipeline",
                     model="nvidia/Cosmos3-Nano",
                     parameters={"prompt": "Put the pot to the left of the cup.",
                                 "action": "cached:act_cond", "fps": 5,
                                 "num_inference_steps": 30, "guidance_scale": 1.0})

2. CALL (low-level): dynamically resolve & call ANY diffusers class / function /
   method — DiffusionPipeline, schedulers, VAEs, CosmosActionCondition, the
   export_to_video util, or a cached pipeline's method.

       use_diffusers(action="call", target="CosmosActionCondition",
                     parameters={"mode": "policy", "chunk_size": 16,
                                 "domain_name": "bridge_orig_lerobot",
                                 "video": "robot.mp4"},
                     cache_key="act_cond")
       use_diffusers(action="call", target="cached:pipe.enable_model_cpu_offload")

Discovery (so the agent never guesses):
       use_diffusers(action="pipelines")               # all pipelines + modality
       use_diffusers(action="models")                  # all model classes
       use_diffusers(action="schedulers")              # all schedulers
       use_diffusers(action="tasks")                   # AutoPipeline task → class maps
       use_diffusers(action="modalities")              # pipelines grouped by modality
       use_diffusers(action="wfm")                     # world-foundation/action models
       use_diffusers(action="pipeline_info", target="Cosmos3OmniPipeline")
       use_diffusers(action="inspect", target="...")   # signature + docs of anything
       use_diffusers(action="cache" | "clear_cache")
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import traceback
from typing import Any, Dict, Optional

from strands import tool

from strands_diffusers.core import engine, io, registry

logger = logging.getLogger(__name__)


def _ensure(package: str) -> None:
    import importlib
    try:
        importlib.import_module(package)
    except ImportError:
        logger.info("Installing %s ...", package)
        subprocess.run([sys.executable, "-m", "pip", "install", package],
                       check=True, timeout=600)


def _ok(text: str, **extra: Any) -> Dict[str, Any]:
    payload = {"status": "success", "content": [{"text": text}]}
    payload.update(extra)
    return payload


def _err(text: str) -> Dict[str, Any]:
    return {"status": "error", "content": [{"text": text}]}


@tool
def use_diffusers(
    action: str = "pipelines",
    pipeline: Optional[str] = None,
    model: Optional[str] = None,
    inputs: Any = None,
    target: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    cache_key: Optional[str] = None,
    device: Optional[str] = None,
    dtype: Optional[str] = None,
    save_artifacts: bool = True,
    fps: float = 24.0,
    label: str = "",
) -> Dict[str, Any]:
    """Universal access to ALL diffusers functionality — no hardcoding.

    Args:
        action: What to do:
            run          — load a `pipeline` class from `model` and call it on `parameters`
            call         — dynamically call any diffusers class/function/method via `target`
            pipelines    — list every pipeline class with its derived modality
            models       — list every model class (VAEs, transformers, controlnets)
            schedulers   — list every scheduler class
            tasks        — diffusers' AutoPipeline task → {family: class} maps
            modalities   — pipelines grouped by modality (text-to-image/video/world/...)
            wfm          — world-foundation / action-capable pipelines (Cosmos, Wan, ...)
            pipeline_info— modality + __call__ signature for one `target` pipeline class
            inspect      — signature + docstring of any `target`
            cache        — list cached pipelines/objects
            clear_cache  — free a `cache_key` (or everything)
            visualize    — render a robot action chunk to plots + an animation (SEE it)
        pipeline: diffusers pipeline class name for action="run" (e.g.
                  "StableDiffusionPipeline", "Cosmos3OmniPipeline"). Use
                  "DiffusionPipeline"/"AutoPipelineForText2Image" for auto-detect.
        model: HF repo id or local path to load weights from.
        inputs: convenience positional input merged into the pipeline call (rarely
                needed — most diffusers pipelines take keyword args via `parameters`).
        target: For action="call"/"inspect"/"pipeline_info": dotted path into
                diffusers, e.g. "CosmosActionCondition", "utils.export_to_video",
                "cached:key.method".
        parameters: kwargs for the pipeline call / the dynamic call. Values that are
                    "cached:key" resolve to live cached objects; path/URL/base64
                    values are coerced to PIL/video automatically.
        cache_key: name to cache (or fetch) a loaded object under.
        device: "cuda" / "mps" / "cpu" / "auto".
        dtype: "bfloat16" / "float16" / "float32" (default: device-appropriate).
        save_artifacts: write generated images/video/audio/actions to disk.
        fps: frames-per-second used when exporting generated video.
        label: human-readable description for logging.

    Returns:
        Dict with status + content; "run"/"call" also include "data" (JSON-safe
        result) and "artifacts" (paths to generated media + action JSON).
    """
    # LLM tool-calls may serialize the `parameters` object to a JSON string;
    # also accept that gracefully (else dict(str) raises a cryptic ValueError).
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except (ValueError, TypeError):
            return _err("`parameters` must be a JSON object/dict; got an "
                        f"unparseable string: {parameters[:120]!r}")
    if parameters is not None and not isinstance(parameters, dict):
        return _err(f"`parameters` must be a dict, got {type(parameters).__name__}.")
    params = dict(parameters or {})
    try:
        # ───────── discovery ─────────
        if action == "pipelines":
            pipes = registry.pipelines()
            lines = [f"🎨 diffusers exposes {len(pipes)} pipelines (100% coverage):\n"]
            for p in pipes:
                lines.append(f"  • {p}  [{registry.modality_of(p)}]")
            lines.append('\n💡 run:  use_diffusers(action="run", pipeline="<class>", '
                         'model="<repo>", parameters={...})')
            return _ok("\n".join(lines), data=pipes)

        if action == "models":
            ms = registry.models()
            return _ok(f"🧩 {len(ms)} model classes:\n  " + "\n  ".join(ms), data=ms)

        if action == "schedulers":
            sc = registry.schedulers()
            return _ok(f"⏱️  {len(sc)} schedulers:\n  " + "\n  ".join(sc), data=sc)

        if action == "tasks":
            t = registry.auto_pipeline_tasks()
            if "_error" in t:
                # Soft-fail: env-specific upstream issue, not a strands-diffusers bug.
                return _ok(
                    f"⚠️  AutoPipeline task discovery unavailable in this env:\n"
                    f"   {t['_error']}",
                    data=t,
                )
            return _ok("🗂️  AutoPipeline task maps:\n" + json.dumps(t, indent=2), data=t)

        if action == "modalities":
            groups = registry.tasks_by_modality()
            lines = ["🎛️  Pipelines by modality:\n"]
            for mod in sorted(groups):
                lines.append(f"  {mod}  ({len(groups[mod])}):")
                for p in groups[mod]:
                    lines.append(f"      • {p}")
            return _ok("\n".join(lines), data=groups)

        if action == "wfm":
            wfm = registry.world_foundation_models()
            lines = ["🌍 World-foundation / action-capable pipelines:\n"]
            for p in wfm:
                lines.append(f"  • {p}  [{registry.modality_of(p)}]")
            lines.append("\n💡 Cosmos action-policy runs return BOTH a world video "
                         "and a robot action chunk.\n"
                         "   Pass a CosmosActionCondition via parameters={'action': "
                         "'cached:cond'}.")
            return _ok("\n".join(lines), data=wfm)

        if action == "pipeline_info":
            if not target:
                return _err("Provide `target` (a pipeline class name).")
            info = registry.pipeline_info(target)
            if not info:
                return _err(f"Unknown pipeline '{target}'. Use action='pipelines'.")
            return _ok(f"🔍 {target}\n{json.dumps(info, indent=2, default=str)}", data=info)

        if action == "inspect":
            if not target:
                return _err("Provide `target` (e.g. 'StableDiffusionPipeline').")
            obj = _resolve_target(target)
            info = registry.describe(obj)
            return _ok(f"🔍 {target}\n{json.dumps(info, indent=2, default=str)}", data=info)

        if action == "cache":
            c = engine.cache_list()
            if not c:
                return _ok("📦 cache empty")
            return _ok("📦 cached:\n" + "\n".join(f"  • {k}: {v}" for k, v in c.items()),
                       data=c)

        if action == "clear_cache":
            n = engine.cache_clear(cache_key)
            return _ok(f"🧹 cleared {n} object(s)")

        if action == "visualize":
            # Turn a robot ACTION chunk into plots + an animation you can watch.
            # `target` may be a path to an action .json artifact, or pass the raw
            # action via `inputs` (nested list / serialized dict).
            from strands_diffusers.core import viz
            act = inputs
            if act is None and target:
                if target.startswith("cached:"):
                    act = _resolve_target(target)
                elif target.lstrip().startswith("["):
                    act = json.loads(target)          # inline JSON action
                else:
                    with open(target) as f:
                        act = json.load(f)
            if act is None:
                return _err("Provide an action via `inputs` (list/dict) or `target` "
                            "(path to an action .json, or cached:key).")
            vp = params or {}
            res = viz.visualize_action(
                act,
                save_prefix=vp.get("save_prefix", "action"),
                interpret_xyz=vp.get("interpret_xyz", True),
                gripper_index=vp.get("gripper_index", -1),
                cumulative_xyz=vp.get("cumulative_xyz", True),
                world_video=vp.get("world_video"),
                fps=int(vp.get("fps", fps)),
                dim_labels=vp.get("dim_labels"),
            )
            arts = res["artifacts"]
            head = "🎬 action visualization\n📎 artifacts:\n" + "\n".join(
                f"  • {a}" for a in arts)
            return _ok(f"{head}\n{json.dumps(res['summary'], indent=2)}",
                       data=res["summary"], artifacts=arts)

        # ───────── run (pipeline) ─────────
        if action == "run":
            if not pipeline:
                return _err("Provide `pipeline` (a class name). Use action='pipelines'.")
            if not model:
                return _err("Provide `model` (HF repo id or local path).")
            # Modular pipelines have a different lifecycle: from_pretrained loads
            # CONFIG ONLY, components must be loaded via load_components(), and
            # __call__(state, output) takes a PipelineState — not prompt=... So the
            # generic run path (from_pretrained -> .to() -> pipe(**kwargs)) won't work.
            if pipeline.endswith("ModularPipeline"):
                return _err(
                    f"'{pipeline}' is a Modular pipeline with a different lifecycle "
                    "(from_pretrained loads config only; call load_components() then "
                    "invoke with a PipelineState, not prompt=...). The high-level "
                    "`run` path doesn't support Modular pipelines yet. Use action='call' "
                    "to drive it manually, or pick the non-modular variant "
                    f"(e.g. '{pipeline.replace('Modular','')}').")
            _ensure("diffusers")
            from_pretrained_kwargs = params.pop("from_pretrained_kwargs", {}) \
                if isinstance(params, dict) else {}
            pipe, key = engine.get_pipeline(
                pipeline, model, device=device, dtype=dtype,
                cache_key=cache_key, **from_pretrained_kwargs)
            call_kwargs = _coerce_kwargs(params)
            if inputs is not None:
                call_args = [_coerce_param(inputs)]
            else:
                call_args = []
            if label:
                logger.info("run %s (%s): %s", pipeline, model, label)
            result = pipe(*call_args, **call_kwargs)
            sr = _infer_sample_rate(pipe)
            out = io.serialize_output(result, save_artifacts=save_artifacts,
                                      fps=call_kwargs.get("fps", fps),
                                      audio_sample_rate=sr)
            return _ok(_summarize(pipeline, out, key),
                       data=out.get("result"), artifacts=out.get("artifacts", []))

        # ───────── call (dynamic) ─────────
        if action == "call":
            if not target:
                return _err("Provide `target` (e.g. 'CosmosActionCondition' or "
                            "'utils.export_to_video').")
            _ensure("diffusers")
            obj = _resolve_target(target)
            if not callable(obj):
                return _ok(f"📋 {target} = {str(obj)[:500]}", data=str(obj)[:2000])
            coerced = _coerce_kwargs(params)
            unpacked = coerced.pop("**", None)
            if unpacked is not None:
                try:
                    coerced = {**dict(unpacked), **coerced}
                except (TypeError, ValueError) as ue:
                    return _err(f"❌ '**' value is not a mapping: {ue}")
            result = obj(**coerced)
            if cache_key:
                engine._CACHE[cache_key] = result
                return _ok(f"✅ {target}() → cached as '{cache_key}' "
                           f"({type(result).__name__})",
                           data={"cached": cache_key, "type": type(result).__name__})
            out = io.serialize_output(result, save_artifacts=save_artifacts, fps=fps)
            preview = json.dumps(out.get("result"), indent=2, default=str)
            if len(preview) > 2000:
                preview = preview[:2000] + " …"
            arts = out.get("artifacts", [])
            head = f"✅ {target}() → {type(result).__name__}"
            if arts:
                head += "\n📎 artifacts:\n" + "\n".join(f"  • {a}" for a in arts)
            return _ok(f"{head}\n{preview}", data=out.get("result"), artifacts=arts)

        return _err(f"Unknown action '{action}'. Try: pipelines, models, schedulers, "
                    f"tasks, modalities, wfm, pipeline_info, inspect, run, call, "
                    f"visualize, cache, clear_cache.")

    except TypeError as e:
        hint = ""
        try:
            if target:
                hint = "\n\nExpected:\n" + json.dumps(
                    registry.describe(_resolve_target(target)), indent=2, default=str)
            elif pipeline:
                hint = "\n\nExpected:\n" + json.dumps(
                    registry.pipeline_info(pipeline), indent=2, default=str)
        except Exception:
            pass
        return _err(f"❌ TypeError: {e}{hint}")
    except Exception as e:
        logger.error("use_diffusers(%s) failed: %s", action, e, exc_info=True)
        return _err(f"❌ {type(e).__name__}: {e}\n\n{traceback.format_exc()[-800:]}")


def _resolve_target(target: str) -> Any:
    """Resolve a target which may reference a cached object."""
    if target.startswith("cached:"):
        ref = target[len("cached:"):]
        head, _, tail = ref.partition(".")
        obj = engine.cache_get(head)
        if obj is None:
            raise ValueError(f"No cached object '{head}'. Use action='cache' to list.")
        for attr in filter(None, tail.split(".")):
            obj = getattr(obj, attr)
        return obj
    return registry.resolve_attr(target)


_OUTPUT_PATH_KEYS = ("output_path", "output_video_path", "output_obj_path",
                     "output_ply_path", "save_path", "out_path")


def _coerce_kwargs(params: dict) -> dict:
    """Coerce param values, but leave OUTPUT path keys untouched — coercing an
    existing output path would load it as media (a subtle idempotency bug)."""
    out = {}
    for k, v in params.items():
        if k in _OUTPUT_PATH_KEYS:
            out[k] = v
        else:
            out[k] = _coerce_param(v)
    return out


def _coerce_param(value: Any) -> Any:
    """Coerce a single parameter value.

    Resolves "cached:key[.attr]" strings to live cached objects (so pipelines can
    receive e.g. action=cached:cond or scheduler=cached:sched), then applies
    multimodal input coercion (paths/URLs/base64 → PIL/video) to everything else.
    """
    if isinstance(value, str) and value.startswith("cached:"):
        return _resolve_target(value)
    if isinstance(value, list):
        return [_coerce_param(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce_param(v) for k, v in value.items()}
    return io.coerce_input(value)


def _infer_sample_rate(pipe: Any, default: int = 16000) -> int:
    """Best-effort audio sample-rate discovery for pipelines that emit sound.

    Checks, in order: dedicated audio components (vocoder/tokenizer/encoder), the
    pipeline config, then the generative backbone (unet/transformer) — DanceDiffusion
    stores sample_rate on its UNet1D, not the pipeline.
    """
    for attr in ("vae", "sound_tokenizer", "vocoder", "audio_encoder", "unet", "transformer"):
        comp = getattr(pipe, attr, None)
        if comp is None:
            continue
        # some components (e.g. StableAudio's VAE) expose sampling_rate directly
        sr = getattr(comp, "sampling_rate", None) or getattr(comp, "sample_rate", None)
        if sr:
            return int(sr)
        cfg = getattr(comp, "config", None)
        sr = getattr(cfg, "sampling_rate", None) or getattr(cfg, "sample_rate", None)
        if sr:
            return int(sr)
    cfg = getattr(pipe, "config", None)
    sr = getattr(cfg, "sampling_rate", None) or getattr(cfg, "sample_rate", None)
    return int(sr) if sr else default


def _summarize(pipeline: str, out: Dict[str, Any], key: str) -> str:
    arts = out.get("artifacts", [])
    head = f"✅ {pipeline} ({key})"
    if arts:
        head += "\n📎 artifacts:\n" + "\n".join(f"  • {a}" for a in arts)
    preview = json.dumps(out.get("result"), indent=2, default=str)
    if len(preview) > 2000:
        preview = preview[:2000] + " …"
    return f"{head}\n{preview}"


__all__ = ["use_diffusers"]
