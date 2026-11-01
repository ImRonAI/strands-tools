"""Strands OSMO tools - full coverage of the OSMO CLI surface for Strands Agents.

Tools are thin Python wrappers over `osmo <subcommand>` invocations.
The OSMO CLI is the single source of truth for every operation.

Tool families:
  - Auth / system: osmo_login, osmo_version, osmo_doctor
  - Resources: osmo_pool_list, osmo_resources_list, osmo_profile_list, osmo_bucket_list
  - Workflow: osmo_workflow_submit, osmo_workflow_list, osmo_workflow_status,
              osmo_workflow_cancel, osmo_workflow_logs, osmo_workflow_exec
  - Task: osmo_task_list, osmo_task_describe
  - Data: osmo_data_upload, osmo_data_download, osmo_data_list
  - Dataset: osmo_dataset_list, osmo_dataset_describe
  - App: osmo_app_list, osmo_app_create
  - Cookbook: osmo_cookbook_fetch
  - Spec: osmo_workflow_validate, osmo_workflow_render
"""

# ── Auth / system ────────────────────────────────────────────────────────
from strands_osmo.tools.app_create import osmo_app_create

# ── Apps ────────────────────────────────────────────────────────────────
from strands_osmo.tools.app_list import osmo_app_list
from strands_osmo.tools.bucket_list import osmo_bucket_list

# ── Cookbook + spec helpers ─────────────────────────────────────────────
from strands_osmo.tools.cookbook_fetch import osmo_cookbook_fetch
from strands_osmo.tools.data_download import osmo_data_download
from strands_osmo.tools.data_list import osmo_data_list

# ── Data plane ──────────────────────────────────────────────────────────
from strands_osmo.tools.data_upload import osmo_data_upload
from strands_osmo.tools.dataset_describe import osmo_dataset_describe

# ── Datasets ────────────────────────────────────────────────────────────
from strands_osmo.tools.dataset_list import osmo_dataset_list
from strands_osmo.tools.doctor import osmo_doctor
from strands_osmo.tools.login import osmo_login

# ── Resource discovery ──────────────────────────────────────────────────
from strands_osmo.tools.pool_list import osmo_pool_list
from strands_osmo.tools.profile_list import osmo_profile_list
from strands_osmo.tools.resources_list import osmo_resources_list
from strands_osmo.tools.task_describe import osmo_task_describe

# ── Task introspection ──────────────────────────────────────────────────
from strands_osmo.tools.task_list import osmo_task_list
from strands_osmo.tools.version import osmo_version
from strands_osmo.tools.workflow_cancel import osmo_workflow_cancel
from strands_osmo.tools.workflow_exec import osmo_workflow_exec
from strands_osmo.tools.workflow_list import osmo_workflow_list
from strands_osmo.tools.workflow_logs import osmo_workflow_logs
from strands_osmo.tools.workflow_render import osmo_workflow_render
from strands_osmo.tools.workflow_status import osmo_workflow_status

# ── Workflow lifecycle ──────────────────────────────────────────────────
from strands_osmo.tools.workflow_submit import osmo_workflow_submit
from strands_osmo.tools.workflow_validate import osmo_workflow_validate

__all__ = [
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
