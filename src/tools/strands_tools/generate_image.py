"""
Image generation tool for Strands Agent using Stable Diffusion.

This module provides functionality to generate high-quality images using Amazon Bedrock's
Stable Diffusion models based on text prompts. It handles the entire image generation
process including API integration, parameter management, response processing, and
local storage of results.

Key Features:

1. Image Generation:
   • Text-to-image conversion using Stable Diffusion models
   • Support for the following models:
        • stability.sd3-5-large-v1:0
        • stability.stable-image-core-v1:1
        • stability.stable-image-ultra-v1:1
   • Customizable generation parameters (seed, aspect_ratio, output_format, negative_prompt)

2. Output Management:
   • Automatic local saving with intelligent filename generation
   • Base64 encoding/decoding for transmission
   • Duplicate filename detection and resolution
   • Organized output directory structure

3. Response Format:
   • Rich response with both text and image data
   • Status tracking and error handling
   • Direct base64 image data for immediate display
   • File path reference for local access

Usage with Strands Agent:
```python
from strands import Agent
from strands_tools import generate_image

agent = Agent(tools=[generate_image])

# Basic usage with default parameters
agent.tool.generate_image(prompt="A steampunk robot playing chess")

# Advanced usage with Stable Diffusion
agent.tool.generate_image(
    prompt="A futuristic city with flying cars",
    model_id="stability.sd3-5-large-v1:0",
    aspect_ratio="5:4",
    output_format="jpeg",
    negative_prompt="bad lighting, harsh lighting, abstract, surreal, twisted, multiple levels",
)

# Using another Stable Diffusion model
agent.tool.generate_image(
    prompt="A photograph of a cup of coffee from the side",
    model_id="stability.stable-image-ultra-v1:1",
    aspect_ratio="1:1",
    output_format="png",
    negative_prompt="blurry, distorted",
)
```

See the generate_image function docstring for more details on parameters and options.
"""

import base64
import json
import os
import random
import re
from typing import Annotated, Any

import boto3
from botocore.config import Config as BotocoreConfig
from strands import tool

STABLE_DIFFUSION_MODEL_ID = [
    "stability.sd3-5-large-v1:0",
    "stability.stable-image-core-v1:1",
    "stability.stable-image-ultra-v1:1",
]


# Create a filename based on the prompt
def create_filename(prompt: str) -> str:
    """Generate a filename from the prompt text."""
    words = re.findall(r"\w+", prompt.lower())[:5]
    filename = "_".join(words)
    filename = re.sub(r"[^\w\-_\.]", "_", filename)
    return filename[:100]  # Limit filename length


@tool
def generate_image(
    prompt: Annotated[str, "The text prompt for image generation"],
    model_id: Annotated[
        str,
        (
            "Model id for image model: stability.sd3-5-large-v1:0, "
            "stability.stable-image-core-v1:1, or stability.stable-image-ultra-v1:1"
        ),
    ] = "stability.stable-image-core-v1:1",
    region: Annotated[
        str,
        "AWS region for the image generation model (default: us-west-2)",
    ] = "us-west-2",
    seed: Annotated[
        int | None,
        "Optional: Seed for random number generation (default: random)",
    ] = None,
    aspect_ratio: Annotated[
        str,
        (
            "Optional: Controls the aspect ratio of the generated image for "
            "Stable Diffusion models. Default 1:1. Enum: 16:9, 1:1, 21:9, 2:3, 3:2, 4:5, 5:4, 9:16, 9:21"
        ),
    ] = "1:1",
    output_format: Annotated[
        str,
        "Optional: Specifies the format of the output image for Stable Diffusion models. Supported formats: jpeg, png.",
    ] = "jpeg",
    negative_prompt: Annotated[
        str,
        "Optional: Keywords of what you do not wish to see in the output image. Default: bad lighting, harsh lighting.",
    ] = "bad lighting, harsh lighting",
) -> dict[str, Any]:
    """Generates an image using Stable Diffusion models based on a given prompt.

    Args:
        prompt: The text prompt for image generation.
        model_id: Specific model to use (defaults to stability.stable-image-core-v1:1).
        region: AWS region for the image generation model (default: us-west-2).
        seed: Controls randomness for reproducible results.
        aspect_ratio: Controls the aspect ratio of the generated image.
        output_format: Specifies the format of the output image (jpeg or png).
        negative_prompt: Keywords of what you do not wish to see in the output image.

    Returns:
        Dictionary containing the result status and image content.
    """
    try:
        resolved_seed = seed if seed is not None else random.randint(0, 4294967295)

        # Create a Bedrock Runtime client
        config = BotocoreConfig(user_agent_extra="strands-agents-generate-image")
        client = boto3.client("bedrock-runtime", region_name=region, config=config)

        # create the request body
        native_request = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "seed": resolved_seed,
            "output_format": output_format,
            "negative_prompt": negative_prompt,
        }
        request = json.dumps(native_request)

        # Invoke the model
        response = client.invoke_model(modelId=model_id, body=request)

        # Decode the response body
        model_response = json.loads(response["body"].read().decode("utf-8"))

        # Extract the image data
        base64_image_data = model_response["images"][0]

        # If we have image data, process and save it
        if base64_image_data:
            filename = create_filename(prompt)

            # Save the generated image to a local folder
            output_dir = "output"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            i = 1
            base_image_path = os.path.join(output_dir, f"{filename}.{output_format}")
            image_path = base_image_path
            while os.path.exists(image_path):
                image_path = os.path.join(output_dir, f"{filename}_{i}.{output_format}")
                i += 1

            with open(image_path, "wb") as file:
                file.write(base64.b64decode(base64_image_data))

            return {
                "status": "success",
                "content": [
                    {"text": f"The generated image has been saved locally to {image_path}. "},
                    {
                        "image": {
                            "format": output_format,
                            "source": {"bytes": base64.b64decode(base64_image_data)},
                        }
                    },
                ],
            }
        else:
            raise Exception("No image data found in the response.")
    except Exception as e:
        return {
            "status": "error",
            "content": [
                {
                    "text": (
                        f"Error generating image: {str(e)} \n Try other supported models for this tool are: \n "
                        "1. stability.sd3-5-large-v1:0 \n "
                        "2. stability.stable-image-core-v1:1 \n "
                        "3. stability.stable-image-ultra-v1:1"
                    )
                }
            ],
        }
