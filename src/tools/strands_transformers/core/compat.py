"""Backward-compat shims for older `trust_remote_code` models on new transformers.

Many published models (e.g. openvla/openvla-7b) ship custom code written against
transformers 4.x. On transformers 5.x some symbols moved and some Auto* classes
were renamed/removed. Rather than forcing users to pin an old transformers, we
patch the gaps at runtime so the model's own code loads unchanged.

Currently handled:
- `transformers.tokenization_utils.{PaddingStrategy,TruncationStrategy,
  PreTokenizedInput,TextInput,...}` re-exported from `tokenization_utils_base`.
- `AutoModelForVision2Seq` recreated as an alias of `AutoModelForImageTextToText`
  so old `auto_map` entries resolve (used by OpenVLA & friends).

`apply()` is idempotent and safe to call repeatedly.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_APPLIED = False
_VISION2SEQ_ALIAS = None


def apply(force: bool = False) -> None:
    """Apply compat shims. Idempotent.

    Some trust_remote_code models (OpenVLA) re-import transformers during load,
    which can replace the cached aliases. Callers may pass force=True (or call
    `ensure_alias()`) to re-assert the shims right before resolving a class.
    """
    global _APPLIED
    if _APPLIED and not force:
        return
    _patch_tokenization_utils()
    _patch_vision2seq()
    _patch_tie_weights()
    _patch_broken_torchcodec()
    _APPLIED = True


def ensure_alias() -> None:
    """Cheaply re-assert the Vision2Seq alias on the live transformers module."""
    _patch_vision2seq()


_MOVED_SYMBOLS = (
    "PaddingStrategy",
    "TruncationStrategy",
    "PreTokenizedInput",
    "TextInput",
    "TextInputPair",
    "PreTokenizedInputPair",
    "EncodedInput",
    "EncodedInputPair",
)


def _patch_tokenization_utils() -> None:
    """Re-export symbols that moved to tokenization_utils_base in transformers 5.x.

    In transformers 5.x `transformers.tokenization_utils` is a virtual alias
    module with `__spec__ = None` / `__file__ = None`. The HuggingFace dynamic
    module loader (used by trust_remote_code models like OpenVLA) executes
    `from transformers.tokenization_utils import PaddingStrategy` through the
    import machinery, which rejects a module with no location ("unknown
    location") even when the attribute is set.

    Fix: rebind `transformers.tokenization_utils` in sys.modules to a *real*
    module object that has a proper spec/loader (we reuse the concrete
    `tokenization_utils_sentencepiece` module file) and inject the moved
    symbols onto it. This makes `from ... import ...` succeed.
    """
    import sys

    try:
        import transformers.tokenization_utils_base as tub

        # the concrete file transformers aliases tokenization_utils to
        import transformers.tokenization_utils_sentencepiece as concrete
    except Exception as e:  # pragma: no cover
        logger.debug("tokenization_utils patch skipped: %s", e)
        return

    missing = [n for n in _MOVED_SYMBOLS if not hasattr(concrete, n) and hasattr(tub, n)]
    # Inject the moved symbols onto the concrete (real, file-backed) module.
    for name in _MOVED_SYMBOLS:
        if not hasattr(concrete, name) and hasattr(tub, name):
            setattr(concrete, name, getattr(tub, name))

    # Point the virtual alias at the real module so import machinery has a
    # valid location and finds the symbols.
    current = sys.modules.get("transformers.tokenization_utils")
    if current is None or getattr(current, "__spec__", None) is None:
        sys.modules["transformers.tokenization_utils"] = concrete
        import transformers

        transformers.tokenization_utils = concrete
    logger.debug("tokenization_utils compat: injected %s", missing)


def _patch_vision2seq() -> None:
    """Recreate AutoModelForVision2Seq (removed in 5.x) as an ImageTextToText alias.

    Custom-code models look up their `auto_map` key by the Auto class *name*, so a
    same-named subclass is enough for `AutoModelForVision2Seq.from_pretrained(...,
    trust_remote_code=True)` to find the remote class.
    """
    import sys

    import transformers

    base = getattr(transformers, "AutoModelForImageTextToText", None)
    if base is None:
        return

    global _VISION2SEQ_ALIAS
    if _VISION2SEQ_ALIAS is None:

        class AutoModelForVision2Seq(base):  # type: ignore[misc, valid-type]
            """Compat alias of AutoModelForImageTextToText for legacy auto_map entries."""

        _VISION2SEQ_ALIAS = AutoModelForVision2Seq

    alias = _VISION2SEQ_ALIAS
    # Assert the alias on every live handle to the transformers module. OpenVLA's
    # remote code can re-import transformers and swap sys.modules, so set it on
    # both the imported object and the current sys.modules entry.
    for target in {transformers, sys.modules.get("transformers")}:
        if target is not None and getattr(target, "AutoModelForVision2Seq", None) is not alias:
            try:
                target.AutoModelForVision2Seq = alias
            except Exception:
                pass
    try:
        import transformers.models.auto.modeling_auto as ma

        if getattr(ma, "AutoModelForVision2Seq", None) is not alias:
            ma.AutoModelForVision2Seq = alias
    except Exception:
        pass
    # register_for_auto_class() validates against transformers.models.auto, so
    # the alias must be visible there too (used by remote code during load).
    try:
        import transformers.models.auto as auto_module

        if getattr(auto_module, "AutoModelForVision2Seq", None) is not alias:
            auto_module.AutoModelForVision2Seq = alias
    except Exception:
        pass


def _patch_tie_weights() -> None:
    """Tolerate transformers 5.x calling tie_weights(missing_keys, recompute_mapping).

    transformers 5.x invokes `model.tie_weights(missing_keys=..., recompute_mapping=...)`
    during from_pretrained, but many 4.x-era custom models override `tie_weights(self)`
    with no extra params, raising TypeError. We wrap PreTrainedModel.tie_weights so any
    subclass override that rejects the new kwargs is retried without them.
    """
    try:
        from transformers.modeling_utils import PreTrainedModel
    except Exception:  # pragma: no cover
        return
    if getattr(PreTrainedModel, "_st_tie_weights_wrapped", False):
        return

    # Wrap init_weights (defined on the base class, not overridden by legacy
    # models) so its internal `self.tie_weights(recompute_mapping=...)` call
    # tolerates subclasses whose tie_weights() override rejects the new kwargs.
    original_init = PreTrainedModel.init_weights

    def init_weights(self):
        cls = type(self)
        tw = cls.tie_weights
        if not getattr(cls, "_st_tw_wrapped", False) and tw is not PreTrainedModel.tie_weights:

            def safe_tie_weights(self, *args, _orig=tw, **kwargs):
                try:
                    return _orig(self, *args, **kwargs)
                except TypeError:
                    return _orig(self)

            cls.tie_weights = safe_tie_weights
            cls._st_tw_wrapped = True
        return original_init(self)

    PreTrainedModel.init_weights = init_weights
    PreTrainedModel._st_tie_weights_wrapped = True


def _patch_broken_torchcodec() -> None:
    """Disable torchcodec detection when the installed torchcodec is broken.

    transformers' audio pipelines call `is_torchcodec_available()` and then do an
    unconditional `import torchcodec`. If torchcodec is installed but its native
    lib fails to load (common ffmpeg ABI mismatch), this crashes even for already
    decoded array/dict inputs. We probe the actual import once; if it fails, we
    override the availability checks to return False so pipelines fall back to the
    ffmpeg/array path.
    """
    try:
        import torchcodec  # noqa: F401

        return  # torchcodec works - nothing to do
    except Exception:
        pass

    def _false() -> bool:
        return False

    patched = 0
    for modname in (
        "transformers.utils",
        "transformers.utils.import_utils",
        "transformers.pipelines.automatic_speech_recognition",
        "transformers.pipelines.audio_classification",
    ):
        try:
            import importlib

            mod = importlib.import_module(modname)
            if hasattr(mod, "is_torchcodec_available"):
                mod.is_torchcodec_available = _false
                patched += 1
        except Exception:
            continue
    if patched:
        logger.debug("Disabled broken torchcodec in %d module(s)", patched)


def spoof_timm_version(version: str = "0.9.16"):
    """Temporarily spoof `timm.__version__` for models with hard version pins.

    Some legacy models (e.g. OpenVLA) hard-assert an exact old timm version in
    their remote code. Newer timm is usually API-compatible for inference. This
    returns a context manager that swaps `timm.__version__` and restores it.

    Usage:
        with compat.spoof_timm_version():
            model = AutoModel.from_pretrained(..., trust_remote_code=True)
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        try:
            import timm
        except ImportError:
            yield
            return
        original = getattr(timm, "__version__", None)
        try:
            timm.__version__ = version
            yield
        finally:
            if original is not None:
                timm.__version__ = original

    return _ctx()
