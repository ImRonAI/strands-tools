"""Audio utility tools — probe and play WAV files."""
from __future__ import annotations

import shutil
import subprocess

from strands import tool

from .._common import err, ok, resolve_path


@tool
def audio_probe(audio_path: str) -> dict:
    """Inspect an audio file: duration, sample rate, channels, format.

    Args:
        audio_path: Path to an audio file.
    """
    p = resolve_path(audio_path)
    if not p.exists():
        return err(f"audio not found: {p}")

    try:
        import soundfile as sf

        info = sf.info(str(p))
        data = {
            "path": str(p),
            "duration_s": float(info.frames / info.samplerate) if info.samplerate else 0.0,
            "frames": int(info.frames),
            "samplerate": int(info.samplerate),
            "channels": int(info.channels),
            "format": info.format,
            "subtype": info.subtype,
        }
        return ok(
            text=f"🎧 {p.name} · {data['duration_s']:.2f}s · {data['samplerate']} Hz · {data['channels']}ch",
            data=data,
        )
    except Exception as e:  # noqa: BLE001
        return err(f"probe failed: {type(e).__name__}: {e}")


@tool
def audio_play(audio_path: str, blocking: bool = False) -> dict:
    """Play an audio file via the host's default player.

    Picks the best available command:
      - macOS: ``afplay``
      - Linux: ``aplay`` (ALSA) or ``paplay`` (PulseAudio) or ``ffplay``
      - Windows: PowerShell ``[System.Media.SoundPlayer]``

    Args:
        audio_path: Path to the file to play.
        blocking: If True, wait for playback to finish before returning.
    """
    p = resolve_path(audio_path)
    if not p.exists():
        return err(f"audio not found: {p}")

    candidates = [
        ("afplay", [str(p)]),
        ("aplay", ["-q", str(p)]),
        ("paplay", [str(p)]),
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "error", str(p)]),
    ]
    chosen = None
    for cmd, args in candidates:
        if shutil.which(cmd):
            chosen = (cmd, args)
            break

    if not chosen:
        return err(
            "no audio player found (tried afplay, aplay, paplay, ffplay). "
            "Install one or play the file manually."
        )

    cmd, args = chosen
    try:
        if blocking:
            r = subprocess.run([cmd, *args], capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                return err(f"{cmd} exit {r.returncode}: {r.stderr[:200]}")
            return ok(text=f"▶️ played {p.name} via {cmd}", data={"player": cmd, "blocking": True})
        # Non-blocking — spawn detached
        subprocess.Popen(
            [cmd, *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return ok(text=f"▶️ playing {p.name} via {cmd}", data={"player": cmd, "blocking": False})
    except Exception as e:  # noqa: BLE001
        return err(f"playback failed: {type(e).__name__}: {e}")
