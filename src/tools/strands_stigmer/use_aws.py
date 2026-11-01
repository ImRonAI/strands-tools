"""Scoped AWS execution tool for Strands agents.

A drop-in replacement for Strands' `use_aws` that adds per-call credential
scoping. `use_aws` builds its client from the ambient session
(`boto3.Session(profile_name=...)`) and exposes no parameter that accepts
scoped credentials, so a least-privilege policy cannot be applied to a single
call. `stigmer_use_aws` adds two optional parameters:

    role_arn:       the IAM role to assume (sts:AssumeRole)
    session_policy: a least-privilege inline policy JSON document

When either is provided, the client is built from the assumed role's
credentials scoped by the session policy. The effective permissions are the
intersection of the role's policies and the session policy, so the call runs
with exactly the permissions it needs and nothing more.

This is the working demonstration of the feature requested upstream for
`use_aws` (strands-agents/tools#337 follow-up): the scoping is plumbed into
the tool rather than left to a racy temp-profile workaround.

Usage:
    from strands import Agent
    from strands_stigmer import stigmer_use_aws

    agent = Agent(tools=[stigmer_use_aws])

    # Least privilege per call: assume a role, scope it, then call.
    agent("List the buckets, but only with the minimal permissions for that call")
"""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ParamValidationError, ValidationError

from strands import tool
from strands.types.tools import ToolResult

logger = logging.getLogger(__name__)


def _scoped_client(
    service_name: str,
    region_name: str,
    profile_name: str | None,
    role_arn: str | None,
    session_policy: dict | None,
) -> Any:
    """Build a boto3 client, scoped by assume_role + session_policy if given.

    When role_arn or session_policy is provided, the client is constructed
    from short-lived credentials minted by sts:AssumeRole with the supplied
    session policy. Effective permissions are the intersection of the role's
    policies and the session policy. Otherwise it falls back to the ambient
    session (matching use_aws's default behavior).
    """
    if not role_arn and not session_policy:
        session = boto3.Session(profile_name=profile_name)
        return session.client(
            service_name=service_name, region_name=region_name,
            config=BotocoreConfig(user_agent_extra="strands-stigmer-use-aws"),
        )

    if not role_arn:
        raise ValueError(
            "session_policy requires role_arn: a scoping policy has no effect "
            "without an assumed role to bound (the ambient session is already "
            "fixed at process launch and cannot be narrowed this way)."
        )

    sts = boto3.client("sts")
    kwargs: dict[str, Any] = {
        "RoleArn": role_arn,
        "RoleSessionName": "strands-stigmer-tool-call",
    }
    if session_policy:
        kwargs["Policy"] = json.dumps(session_policy)
    creds = sts.assume_role(**kwargs)["Credentials"]

    return boto3.client(
        service_name=service_name,
        region_name=region_name,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        config=BotocoreConfig(user_agent_extra="strands-stigmer-use-aws"),
    )


def _convert_datetime_to_str(obj: Any) -> Any:
    """Convert datetime objects in a response to ISO strings for JSON serialization."""
    import datetime

    if isinstance(obj, dict):
        return {k: _convert_datetime_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_datetime_to_str(v) for v in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


@tool
def stigmer_use_aws(
    service_name: str,
    operation_name: str,
    parameters: dict | None = None,
    region: str = "us-west-2",
    label: str = "AWS Operation Details",
    profile_name: str | None = None,
    role_arn: str | None = None,
    session_policy: dict | None = None,
) -> ToolResult:
    """Execute an AWS operation with optional per-call credential scoping.

    Like use_aws, but can assume a role and apply a least-privilege session
    policy to the single call. When role_arn or session_policy is omitted, it
    runs against the ambient session exactly like use_aws.

    #Args:
        service_name: The name of the AWS service (e.g. 's3', 'ec2').
        operation_name: The name of the operation to perform, snake_case (e.g. 'list_buckets').
        parameters: Parameters for the operation.
        region: Region name for the operation.
        label: Human-readable label for the operation.
        profile_name: Optional AWS profile from ~/.aws/credentials.
        role_arn: Optional IAM role ARN to assume for this call (sts:AssumeRole).
        session_policy: Optional least-privilege inline policy JSON to scope the call.

    #Returns:
        A ToolResult with the operation's response, or an error with the reason.
    """
    if not service_name or not operation_name:
        return {
            "status": "error",
            "content": [{"text": "service_name and operation_name are required."}],
        }

    try:
        client = _scoped_client(service_name, region, profile_name, role_arn, session_policy)
        operation_method = getattr(client, operation_name)
    except Exception as ex:
        logger.warning("stigmer_use_aws client setup failed: %s", ex)
        return {
            "status": "error",
            "content": [{"text": f"Failed to set up client: {ex}"}],
        }

    try:
        response = operation_method(**(parameters or {}))
        response = _convert_datetime_to_str(response)
        return {
            "status": "success",
            "content": [{"text": f"Success: {str(response)}"}],
        }
    except (ValidationError, ParamValidationError) as val_ex:
        return {
            "status": "error",
            "content": [{"text": f"Validation error: {str(val_ex)}"}],
        }
    except Exception as ex:
        logger.warning("stigmer_use_aws call failed: %s", ex)
        return {
            "status": "error",
            "content": [{"text": f"AWS call threw exception: {str(ex)}"}],
        }


__all__ = ["stigmer_use_aws", "_scoped_client", "_convert_datetime_to_str"]
