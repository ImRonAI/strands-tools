"""Authentication and credential management for the Strands Tools FastMCP Server."""

from strands_server.auth.provider import (
    CREDENTIAL_SCHEMAS,
    INTROSPECTION_CACHE_TTL_SECONDS,
    build_auth,
    configure_strands_credentials,
    get_auth_status,
)

__all__ = [
    "CREDENTIAL_SCHEMAS",
    "INTROSPECTION_CACHE_TTL_SECONDS",
    "build_auth",
    "configure_strands_credentials",
    "get_auth_status",
]
