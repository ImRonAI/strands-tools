"""Simulate human-like typing with natural variations"""

from typing import Dict, Any, Optional
import time
import random
import sys
from strands import tool


def simulate_typo(char):
    """Simulate common typing mistakes"""
    nearby_keys = {
        "a": "sq",
        "b": "vn",
        "c": "xv",
        "d": "sf",
        "e": "wr",
        "f": "dg",
        "g": "fh",
        "h": "gj",
        "i": "uo",
        "j": "hk",
        "k": "jl",
        "l": "k;",
        "m": "n,",
        "n": "bm",
        "o": "ip",
        "p": "o[",
        "q": "wa",
        "r": "et",
        "s": "ad",
        "t": "ry",
        "u": "yi",
        "v": "cb",
        "w": "qe",
        "x": "zc",
        "y": "tu",
        "z": "xs",
    }
    return random.choice(nearby_keys.get(char.lower(), char))


def get_emotion_params(emotion: str, custom: Optional[Dict] = None):
    """Get typing parameters for emotion"""
    presets = {
        "excited": {"speed": 1.3, "pause": 0.7, "var": 0.4},
        "thoughtful": {"speed": 0.8, "pause": 1.5, "var": 0.2},
        "rushed": {"speed": 1.5, "pause": 0.5, "var": 0.5},
        "calm": {"speed": 1.0, "pause": 1.0, "var": 0.1},
        "nervous": {"speed": 1.2, "pause": 1.3, "var": 0.6},
    }

    if emotion == "custom" and custom:
        return {
            "speed": custom.get("speed_multiplier", 1.0),
            "pause": custom.get("pause_multiplier", 1.0),
            "var": custom.get("variance", 0.1),
        }
    return presets.get(emotion, presets["calm"])


@tool
def human_typer(
    text: str,
    emotion: str = "calm",
    emotion_params: Optional[Dict] = None,
    typo_rate: float = 0.02,
    thinking_pauses: bool = True,
    base_speed: float = 7.0,
) -> Dict[str, Any]:
    """Simulate human-like typing with emotions and natural patterns

    Args:
        text: Text to type
        emotion: Emotion (excited, thoughtful, rushed, calm, nervous, custom)
        emotion_params: Custom params when emotion='custom'
        typo_rate: Rate of typos (0-1)
        thinking_pauses: Pause at punctuation
        base_speed: Base typing speed in chars/sec

    Returns:
        Dict with status and content
    """
    try:
        params = get_emotion_params(emotion, emotion_params)
        base_delay = 1.0 / (base_speed * params["speed"])

        i = 0
        while i < len(text):
            variance = random.uniform(-params["var"], params["var"])
            current_delay = max(0.01, base_delay * (1 + variance))

            # Thinking pauses
            if thinking_pauses and i > 0 and text[i - 1] in ".!?":
                time.sleep(random.uniform(0.5, 1.5) * params["pause"])

            # Word pauses
            if i > 0 and text[i - 1] == " ":
                time.sleep(current_delay * 2)

            # Typos
            if random.random() < typo_rate:
                typo = simulate_typo(text[i])
                sys.stdout.write(typo)
                sys.stdout.flush()
                time.sleep(current_delay)
                sys.stdout.write("\b \b")
                sys.stdout.flush()
                time.sleep(current_delay * 1.5)
                sys.stdout.write(text[i])
            else:
                sys.stdout.write(text[i])

            sys.stdout.flush()
            time.sleep(current_delay)
            i += 1

        return {
            "status": "success",
            "content": [
                {"text": f"\n✅ Typing completed"},
                {"text": f"• Emotion: {emotion}"},
                {"text": f"• Speed: {base_speed} chars/sec"},
                {"text": f"• Typo rate: {typo_rate}"},
            ],
        }

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
