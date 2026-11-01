"""Strands Diffusers — the universal entrypoint to HuggingFace diffusers.

100% diffusers coverage with zero hardcoding: every pipeline (text→image, image→
video, video→world), model, and scheduler, the same way `use_aws` wraps boto3,
`use_lerobot` wraps lerobot, and `use_transformers` wraps the transformers task
taxonomy.

Special focus: Physical-AI world-foundation models (NVIDIA Cosmos) that emit not
just video but ROBOT ACTIONS. A single Cosmos3 action-policy run returns a
playable world video AND a normalized action chunk — both surfaced as artifacts.

Quick start:
    from strands import Agent
    from strands_diffusers import use_diffusers

    agent = Agent(tools=[use_diffusers])
    agent("Generate an image of a robot arm in a kitchen")
    agent("Run a Cosmos action-policy rollout on this robot video and give me the actions")

Discovery (the agent never guesses):
    use_diffusers(action="pipelines")        # all 300+ pipelines + modality
    use_diffusers(action="wfm")              # world-foundation / action models
    use_diffusers(action="modalities")       # pipelines grouped by modality
    use_diffusers(action="pipeline_info", target="Cosmos3OmniPipeline")
    use_diffusers(action="inspect", target="StableDiffusionPipeline")
"""

try:
    from strands_diffusers._version import version as __version__
except ImportError:  # not installed / no git metadata
    __version__ = "0.1.0"

from strands_diffusers.core import engine, io, registry
from strands_diffusers.tools.use_diffusers import use_diffusers

__all__ = [
    "use_diffusers",
    "registry",
    "engine",
    "io",
]
