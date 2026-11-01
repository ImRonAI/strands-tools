"""Shared HTTP client for the Olostep API."""

import os
from typing import Any

import httpx

BASE_URL = os.environ.get("OLOSTEP_BASE_URL", "https://api.olostep.com/v1")

ENDPOINT_SCRAPE = "/scrapes"
ENDPOINT_SEARCH = "/searches"
ENDPOINT_ANSWERS = "/answers"
ENDPOINT_CRAWL = "/crawls"
ENDPOINT_MAP = "/maps"
ENDPOINT_RETRIEVE = "/retrieve"

DEFAULT_TIMEOUT = 120.0


class OlostepError(RuntimeError):
    """Raised when the Olostep API returns an error."""


def _api_key() -> str:
    key = os.environ.get("OLOSTEP_API_KEY")
    if not key:
        raise OlostepError(
            "OLOSTEP_API_KEY is not set. Get a key at https://olostep.com/auth and export it before running your agent."
        )
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def post(endpoint: str, payload: dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """POST a JSON payload to an Olostep endpoint and return the decoded response.

    Args:
        endpoint: Path fragment, e.g. ``/scrapes``.
        payload: JSON body. Keys with ``None`` values are dropped.
        timeout: Request timeout in seconds.

    Returns:
        The decoded JSON response body.

    Raises:
        OlostepError: If the API key is missing or the API returns an error.
    """
    body = {k: v for k, v in payload.items() if v is not None}
    try:
        response = httpx.post(f"{BASE_URL}{endpoint}", json=body, headers=_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise OlostepError(f"Request to Olostep failed: {exc}") from exc
    return _decode(response)


def get(
    endpoint: str,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """GET an Olostep endpoint and return the decoded response.

    Args:
        endpoint: Path fragment, e.g. ``/crawls/crawl_abc123/pages``.
        params: Optional query string parameters. ``None`` values are dropped.
        timeout: Request timeout in seconds.

    Returns:
        The decoded JSON response body.

    Raises:
        OlostepError: If the API key is missing or the API returns an error.
    """
    query = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        response = httpx.get(f"{BASE_URL}{endpoint}", params=query, headers=_headers(), timeout=timeout)
    except httpx.HTTPError as exc:
        raise OlostepError(f"Request to Olostep failed: {exc}") from exc
    return _decode(response)


def _decode(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 400:
        raise OlostepError(f"Olostep API error {response.status_code}: {response.text[:500]}")
    data: dict[str, Any] = response.json()
    return data


def ok(data: dict[str, Any]) -> dict[str, Any]:
    """Wrap a successful API response in the Strands tool result shape."""
    return {"status": "success", "content": [{"json": data}]}


def error(message: str) -> dict[str, Any]:
    """Wrap a failure in the Strands tool result shape."""
    return {"status": "error", "content": [{"text": message}]}
