"""Generate and display custom spinners"""

from typing import Dict, Any, Optional
from halo import Halo
from colorama import Fore, Style, init
import time
from strands import tool

init(autoreset=True)

EMOJI_PATTERNS = {
    "moon": ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"],
    "clock": ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"],
    "earth": ["🌍", "🌎", "🌏"],
    "weather": ["☀️", "⛅️", "☁️", "🌧️", "⛈️", "🌩️"],
    "hearts": ["💗", "💓", "💖", "💘", "💝"],
    "stars": ["⭐️", "🌟", "✨", "💫", "⚡️"],
}

COLORS = {
    "yellow": Fore.YELLOW,
    "green": Fore.GREEN,
    "red": Fore.RED,
    "cyan": Fore.CYAN,
    "blue": Fore.BLUE,
    "magenta": Fore.MAGENTA,
    "white": Fore.WHITE,
}


@tool
def spinner_generator(
    text: str,
    spinner_type: str = "dots",
    color: str = "cyan",
    interval: int = 80,
    duration: float = 3.0,
    custom_pattern: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate and display custom spinner with various styles

    Args:
        text: Text to display alongside spinner
        spinner_type: Type of animation (dots, dots12, line, pipe, star, dots2)
        color: Color (yellow, green, red, cyan, blue, magenta, white)
        interval: Animation interval in ms (50-1000)
        duration: How long to run in seconds (1-10)
        custom_pattern: Preset name (moon, clock, earth, weather, hearts, stars)

    Returns:
        Dict with status and content
    """
    try:
        color_code = COLORS.get(color, Fore.CYAN)

        # Handle custom pattern
        if custom_pattern and custom_pattern in EMOJI_PATTERNS:
            spinner_type = {
                "interval": interval,
                "frames": EMOJI_PATTERNS[custom_pattern],
            }

        spinner = Halo(
            text=f"{color_code}{text}{Style.RESET_ALL}",
            spinner=spinner_type,
            interval=interval,
        )

        spinner.start()
        time.sleep(duration)
        spinner.succeed(f"{color_code}{text} - Complete!{Style.RESET_ALL}")

        return {
            "status": "success",
            "content": [
                {"text": f"✅ Spinner displayed:"},
                {"text": f"• Type: {custom_pattern or spinner_type}"},
                {"text": f"• Color: {color}"},
                {"text": f"• Duration: {duration}s"},
            ],
        }
    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
