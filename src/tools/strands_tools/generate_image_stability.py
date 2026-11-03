"""
Image generation tool for Strands Agent using Stability Platform API.

This module provides functionality to generate high-quality images using Stability AI's
latest models including SD3.5, Stable Image Ultra, and Stable Image Core through the
Stability Platform API.

This means agents can create images in a cost effective way, using state of the art models.

Key Features:

1. Image Generation:
   • Text-to-image and image-to-image conversion
   • Support for multiple Stability AI models
   • Customizable generation parameters (seed, cfg_scale, aspect_ratio)
   • Style preset selection for consistent aesthetics
   • Flexible output formats (JPEG, PNG, WebP)

2. Response Format:
   • Rich response with both text and image data
   • Returns finish reason for generation, to allow identification of requests that have been content moderated
   • Direct image data for immediate display

Usage with Strands Agent:
```python
import os
from strands import Agent
from strands_tools import generate_image_stability


# Set your API key and model as environment variables
os.environ['STABILITY_API_KEY'] = 'sk-xxx'
os.environ['STABILITY_MODEL_ID'] = 'stability.stable-image-ultra-v1:1'

If you want to save the generated images to disk, set the environment variable `STABILITY_OUTPUT_DIR`
to a local directory where the images should be saved.

If no model is selected, the tool defaults to 'stability.stable-image-core-v1:1'.

# Create agent with the tool
agent = Agent(tools=[generate_image_stability])

# Basic usage - agent only needs to provide the prompt
agent("Generate an image of a futuristic robot in a cyberpunk city")

# Advanced usage with custom parameters
agent.tool.generate_image_stability(
    prompt="A serene mountain landscape",
    aspect_ratio="16:9",
    style_preset="photographic",
    cfg_scale=7.0,
    seed=42
)
"""

import base64
import os
from typing import Annotated, Any, Literal, Optional, Tuple, Union

import requests
from strands import tool


def api_route(model_id: str) -> str:
    """
    Generate the API route based on the model ID.

    Args:
        model_id: The model identifier to generate the route for.

    Returns:
        str: The complete API route for the specified model.

    Raises:
        ValueError: If the model_id is not supported.
    """
    route_map = {
        "stability.sd3-5-large-v1:0": "sd3",
        "stability.stable-image-ultra-v1:1": "ultra",
        "stability.stable-image-core-v1:1": "core",
    }

    try:
        route_suffix = route_map[model_id]
    except KeyError as err:
        supported_models = list(route_map.keys())
        raise ValueError(
            f"Unsupported model_id: {model_id}. Supported models are: {', '.join(supported_models)}"
        ) from err

    base_url = "https://api.stability.ai/v2beta/stable-image"
    return f"{base_url}/generate/{route_suffix}"


def call_stability_api(
    prompt: str,
    model_id: str,
    stability_api_key: str,
    return_type: str = "json",
    aspect_ratio: Optional[str] = "1:1",
    cfg_scale: Optional[float] = 4.0,
    seed: Optional[int] = 0,
    output_format: Optional[str] = "png",
    style_preset: Optional[str] = None,
    image: Optional[str] = None,
    mode: Optional[str] = "text-to-image",
    strength: Optional[float] = None,
    negative_prompt: Optional[str] = None,
) -> Tuple[Union[bytes, str], str]:
    """
    Generate images using Stability Platform API.

    Args:
        prompt: Text prompt for image generation
        model_id: Model to use for generation
        stability_api_key: API key for Stability Platform
        return_type: Return format - "json" or "image"
        aspect_ratio: Aspect ratio for the output image
        cfg_scale: CFG scale for prompt adherence
        seed: Random seed for reproducible results
        output_format: Output format (jpeg, png, webp)
        style_preset: Style preset to apply
        image: Input image for image-to-image generation
        mode: Generation mode (text-to-image or image-to-image)
        strength: Influence of input image (for image-to-image)
        negative_prompt: Text describing what not to include in the image

    Returns:
        Tuple of (image_data, finish_reason)
        - image_data: bytes if return_type="image", base64 string if return_type="json"
        - finish_reason: string indicating completion status
    """
    # Get API endpoint using the api_route function
    url = api_route(model_id)

    # Set accept header based on return type
    accept_header = "application/json" if return_type == "json" else "image/*"

    # Prepare headers
    headers = {"authorization": f"Bearer {stability_api_key}", "accept": accept_header}

    # Prepare data payload
    data = {
        "prompt": prompt,
        "output_format": output_format,
    }

    # Add optional parameters
    if aspect_ratio and mode == "text-to-image":
        data["aspect_ratio"] = aspect_ratio
    if cfg_scale is not None:
        data["cfg_scale"] = cfg_scale
    if seed is not None and seed > 0:
        data["seed"] = seed
    if style_preset:
        data["style_preset"] = style_preset
    if strength is not None and mode == "image-to-image":
        data["strength"] = strength
    if negative_prompt:
        data["negative_prompt"] = negative_prompt

    # Prepare files
    files = {}
    if image:
        # Handle base64 encoded image data
        if image.startswith("data:"):
            # Remove data URL prefix if present (e.g., "data:image/png;base64,")
            image = image.split(",", 1)[1]

        # Decode base64 image data
        image_bytes = base64.b64decode(image)
        files["image"] = image_bytes
    else:
        files["none"] = ""

    # Make the API request
    response = requests.post(
        url,
        headers=headers,
        files=files,
        data=data,
    )

    response.raise_for_status()

    # Extract finish_reason and image data based on return type
    if return_type == "json":
        response_data = response.json()
        finish_reason = response_data.get("finish_reason", "SUCCESS")
        # Assuming the JSON response contains base64 image data
        image_data = response_data.get("image", "")
        return image_data, finish_reason
    else:
        finish_reason = response.headers.get("finish_reason", "SUCCESS")
        image_data = response.content
        return image_data, finish_reason


@tool
def generate_image_stability(
    prompt: Annotated[
        str,
        "The text prompt to generate the image from. Be descriptive for best results.",
    ],
    return_type: Annotated[
        Literal["json", "image"],
        (
            "The format in which to return the generated image. "
            "Use 'image' to return the image data directly, or 'json' "
            "to return a JSON object containing the image data as a base64-encoded string."
        ),
    ] = "json",
    aspect_ratio: Annotated[
        Literal["16:9", "1:1", "21:9", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"],
        (
            "Controls the aspect ratio of the generated image. "
            "This parameter is only valid for text-to-image requests."
        ),
    ] = "1:1",
    seed: Annotated[
        int,
        (
            "Optional: Seed for random number generation. "
            "Use the same seed to reproduce similar results. "
            "Omit or use 0 for random generation."
        ),
    ] = 0,
    output_format: Annotated[
        Literal["jpeg", "png", "webp"],
        "Output format for the generated image",
    ] = "png",
    style_preset: Annotated[
        Literal[
            "3d-model",
            "analog-film",
            "anime",
            "cinematic",
            "comic-book",
            "digital-art",
            "enhance",
            "fantasy-art",
            "isometric",
            "line-art",
            "low-poly",
            "modeling-compound",
            "neon-punk",
            "origami",
            "photographic",
            "pixel-art",
            "tile-texture",
        ]
        | None,
        "Style preset for image generation. Applies a predefined artistic style to the output",
    ] = None,
    cfg_scale: Annotated[
        float,
        (
            "Controls how closely the image follows the prompt (only used with SD3.5 model). "
            "Higher values mean stricter adherence to the prompt."
        ),
    ] = 4.0,
    negative_prompt: Annotated[
        str | None,
        (
            "Text describing what you do not want to see in the generated image. "
            "Helps exclude unwanted elements or styles."
        ),
    ] = None,
    mode: Annotated[
        Literal["text-to-image", "image-to-image"],
        "Mode of operation",
    ] = "text-to-image",
    image: Annotated[
        str | None,
        (
            "Input image for image-to-image generation. "
            "Should be base64-encoded image data in jpeg, png or webp format."
        ),
    ] = None,
    strength: Annotated[
        float,
        (
            "For image-to-image mode: controls how much the input image influences the result. "
            "0 = identical to input, 1 = completely new image based on prompt."
        ),
    ] = 0.5,
) -> dict[str, Any]:
    """Generates an image using Stability AI. Simply provide a text description of what you want to create."""
    try:
        # Get API key from environment
        stability_api_key = os.environ.get("STABILITY_API_KEY")
        if not stability_api_key:
            raise ValueError(
                "STABILITY_API_KEY environment variable not set. Please set it with your Stability API key."
            )

        # Get model ID from environment or use default
        model_id = os.environ.get("STABILITY_MODEL_ID", "stability.stable-image-core-v1:1")

        # cfg_scale only for SD3.5 model
        effective_cfg_scale = cfg_scale if model_id == "stability.sd3-5-large-v1:0" else 4.0

        # Generate the image using the API
        image_data, finish_reason = call_stability_api(
            prompt=prompt,
            model_id=model_id,
            stability_api_key=stability_api_key,
            return_type=return_type,
            aspect_ratio=aspect_ratio,
            cfg_scale=effective_cfg_scale,
            seed=seed,
            output_format=output_format,
            style_preset=style_preset,
            image=image,
            mode=mode,
            strength=strength,
            negative_prompt=negative_prompt,
        )

        # Handle image data based on return type
        if return_type == "json":
            # image_data is base64 string - decode it for the ToolResult
            image_bytes = base64.b64decode(image_data)
        else:
            # image_data is already bytes
            image_bytes = image_data if isinstance(image_data, bytes) else image_data.encode("utf-8")

        filename = None
        save_info = ""
        # Check if we should save the image to a file
        output_dir = os.environ.get("STABILITY_OUTPUT_DIR")
        if output_dir:
            # Create a unique filename
            import datetime
            import hashlib
            import uuid

            # Get current timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # Create a short hash from the prompt (first 8 chars of md5)
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]

            # Generate a short UUID (first 6 chars)
            unique_id = str(uuid.uuid4())[:6]

            # Create directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)

            # Construct the filename
            filename = f"{output_dir}/{timestamp}_{prompt_hash}_{unique_id}.{output_format}"

            # Save the image
            with open(filename, "wb") as f:
                f.write(image_bytes)

            # Add filename to the response
            save_info = f"Image saved to {filename}"

        # Prepare the image object with optional filename
        image_object = {
            "format": output_format,
            "source": {"bytes": image_bytes},
        }

        return {
            "status": "success",
            "content": [
                {
                    "text": (
                        f"Generated image using {model_id}. Finish reason: {finish_reason}"
                        f"{' ' + save_info if save_info else ''}"
                    ),
                },
                {"image": image_object},
            ],
        }

    except Exception as e:
        return {
            "status": "error",
            "content": [{"text": f"Error generating image: {str(e)}"}],
        }
