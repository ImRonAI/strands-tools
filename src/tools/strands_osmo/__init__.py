"""strands-osmo - NVIDIA OSMO orchestration for Strands Agents.

Lets a Strands Agent drive the full OSMO workflow lifecycle:
discover GPUs/pools, submit + monitor workflows, manage datasets,
publish apps, and recover from failures.

OSMO is NVIDIA's open-source workflow orchestrator for Physical AI.
It runs heterogeneous compute (training GPUs, simulation GPUs, edge
devices) from a single YAML spec. See https://github.com/NVIDIA/OSMO.

Usage:
    from strands import Agent
    from strands_osmo import (
        osmo_doctor, osmo_pool_list,
        osmo_workflow_submit, osmo_workflow_status,
    )

    agent = Agent(tools=[
        osmo_doctor, osmo_pool_list,
        osmo_workflow_submit, osmo_workflow_status,
    ])
    agent("Find me an idle H100 pool and submit ./train.yaml.")

All tools require the `osmo` CLI on PATH:

    curl -fsSL https://raw.githubusercontent.com/NVIDIA/OSMO/main/install.sh | bash
"""

__version__ = "0.1.0"

from strands_osmo.tools import (  # noqa: F401
    osmo_app_create,
    # App
    osmo_app_list,
    osmo_bucket_list,
    # Cookbook + spec
    osmo_cookbook_fetch,
    osmo_data_download,
    osmo_data_list,
    # Data
    osmo_data_upload,
    osmo_dataset_describe,
    # Dataset
    osmo_dataset_list,
    # Auth
    osmo_doctor,
    osmo_login,
    # Resources
    osmo_pool_list,
    osmo_profile_list,
    osmo_resources_list,
    osmo_task_describe,
    # Task
    osmo_task_list,
    osmo_version,
    osmo_workflow_cancel,
    osmo_workflow_exec,
    osmo_workflow_list,
    osmo_workflow_logs,
    osmo_workflow_render,
    osmo_workflow_status,
    # Workflow
    osmo_workflow_submit,
    osmo_workflow_validate,
)

__all__ = [
    "__version__",
    # Auth
    "osmo_doctor",
    "osmo_login",
    "osmo_version",
    # Resources
    "osmo_pool_list",
    "osmo_resources_list",
    "osmo_profile_list",
    "osmo_bucket_list",
    # Workflow
    "osmo_workflow_submit",
    "osmo_workflow_list",
    "osmo_workflow_status",
    "osmo_workflow_cancel",
    "osmo_workflow_logs",
    "osmo_workflow_exec",
    # Task
    "osmo_task_list",
    "osmo_task_describe",
    # Data
    "osmo_data_upload",
    "osmo_data_download",
    "osmo_data_list",
    # Dataset
    "osmo_dataset_list",
    "osmo_dataset_describe",
    # App
    "osmo_app_list",
    "osmo_app_create",
    # Cookbook + spec
    "osmo_cookbook_fetch",
    "osmo_workflow_validate",
    "osmo_workflow_render",
]
