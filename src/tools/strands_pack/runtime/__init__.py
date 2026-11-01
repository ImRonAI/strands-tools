"""strands-pack runtime handlers and Strands tool wrappers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from strands import tool

from strands_pack.runtime import approval_handler, job_runner_handler


@tool
def pack_runtime_approval(
    event: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Invoke the strands-pack Approval API runtime handler (GET/POST /approve or /reject).

    Args:
        event: API Gateway / Lambda HTTP event payload containing requestContext/httpMethod,
            rawPath/path, queryStringParameters, or body (job_id, token).
        context: Optional Lambda context dictionary.

    Returns:
        HTTP response dictionary with statusCode, headers, and body.
    """
    return approval_handler.handler(event, context or {})


@tool
def pack_runtime_job_runner(
    event: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Invoke the strands-pack SQS durable job runner runtime handler.

    Args:
        event: SQS event payload containing Records with JSON body (job_id, namespace, table_name).
        context: Optional Lambda context dictionary.

    Returns:
        Summary dictionary with processed and errors counts.
    """
    return job_runner_handler.handler(event, context or {})


__all__ = [
    "approval_handler",
    "job_runner_handler",
    "pack_runtime_approval",
    "pack_runtime_job_runner",
]
