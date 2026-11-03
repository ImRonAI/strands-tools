"""
Image processing tool for Strands Agent.

This module provides functionality to read image files from disk and convert them
into the required format for use with the Converse API in Strands Agent. It supports
various image formats including PNG, JPEG, GIF, and WebP, with automatic format detection.

Key Features:
1. Image Processing:
   • Automatic format detection (PNG, JPEG/JPG, GIF, WebP)
   • Binary file handling
   • Error handling for invalid files

2. File Path Handling:
   • Support for absolute paths
   • User directory expansion (~/path/to/image.png)
   • Path validation and error reporting

3. Response Format:
   • Properly formatted image content for Converse API
   • Format-specific processing
   • Binary data conversion

Usage with Strands Agent:
```python
from strands import Agent
from strands_tools import image_reader

agent = Agent(tools=[image_reader])

# Basic usage - read an image file
result = agent.tool.image_reader(image_path="/path/to/image.jpg")

# With user directory path
result = agent.tool.image_reader(image_path="~/Documents/images/photo.png")
```

See the image_reader function docstring for more details on parameters and return format.
"""

import os
from os.path import expanduser
from typing import Annotated, Any

from PIL import Image
from strands import tool


@tool
def image_reader(
    image_path: Annotated[str, "The path to the image file"],
) -> dict[str, Any]:
    """Reads an image file from a given path and returns it in the format required for the Converse API.

    Args:
        image_path: Path to the image file to read. Can be absolute or user-relative (with ~/).

    Returns:
        Dictionary containing status and image content formatted for the Converse API.
    """
    try:
        if not image_path:
            return {
                "status": "error",
                "content": [{"text": "File path is required"}],
            }

        file_path = expanduser(image_path)

        if not os.path.exists(file_path):
            return {
                "status": "error",
                "content": [{"text": f"File not found at path: {file_path}"}],
            }

        with open(file_path, "rb") as file:
            file_bytes = file.read()

        # Handle image files using PIL
        with Image.open(file_path) as img:
            image_format = (img.format or "png").lower()
            if image_format not in ["png", "jpeg", "jpg", "gif", "webp"]:
                image_format = "png"  # Default to PNG if format is not recognized

        return {
            "status": "success",
            "content": [{"image": {"format": image_format, "source": {"bytes": file_bytes}}}],
        }
    except Exception as e:
        return {
            "status": "error",
            "content": [{"text": f"Error reading file: {str(e)}"}],
        }
