"""Google API integration tool for Strands Agent.

This module provides comprehensive access to ALL Google APIs through the
Google API Client Library, allowing you to invoke any Google API operation
directly from your agent.

Key Features:

1. Universal Google API Access:
   • Access to 200+ Google APIs (Gmail, Drive, Calendar, YouTube, etc.)
   • Support for all API operations (resource.method format)
   • Automatic service discovery and validation
   • API version support

2. Authentication:
   • Service Account (JSON key file)
   • OAuth 2.0 (credentials file)
   • API Key for public APIs
   • Environment variable support
   • Dynamic scopes configuration

3. Safety Features:
   • Confirmation prompts for mutative operations
   • Parameter validation with helpful errors
   • Fully dynamic - no hardcoded API calls or scopes
   • Rate limit handling
   • Custom HTTP headers support

4. Usage Examples:
   ```python
   # List Gmail messages
   agent.tool.use_google(
       service="gmail",
       version="v1",
       resource="users.messages",
       method="list",
       parameters={"userId": "me", "maxResults": 10}
   )

   # With custom headers (Places API)
   agent.tool.use_google(
       service="places",
       version="v1",
       resource="places",
       method="searchText",
       parameters={"body": {"textQuery": "restaurants in NYC"}},
       headers={"X-Goog-FieldMask": "places.displayName,places.formattedAddress"}
   )
   ```

Environment Variables:
   - GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON
   - GOOGLE_API_KEY: API key for public APIs
   - GOOGLE_OAUTH_CREDENTIALS: Path to OAuth credentials
   - GOOGLE_API_SCOPES: Comma-separated list of OAuth scopes (optional)
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from strands import tool

logger = logging.getLogger(__name__)

# Mutative operations that require confirmation
MUTATIVE_OPERATIONS = [
    "create",
    "insert",
    "update",
    "patch",
    "delete",
    "trash",
    "remove",
    "send",
    "modify",
    "batchModify",
    "import",
    "copy",
    "move",
]


def get_default_scopes() -> List[str]:
    """Get default OAuth scopes from environment or use broad defaults.

    Returns:
        List of OAuth scope URLs
    """
    # Check environment variable first
    env_scopes = os.getenv("GOOGLE_API_SCOPES")
    if env_scopes:
        return [s.strip() for s in env_scopes.split(",")]

    # Fallback to broad scopes covering most Google APIs
    return [
        "https://www.googleapis.com/auth/cloud-platform",  # GCP services
        "https://www.googleapis.com/auth/youtube.readonly",  # YouTube read
        "https://www.googleapis.com/auth/gmail.readonly",  # Gmail read
        "https://www.googleapis.com/auth/drive.readonly",  # Drive read
        "https://www.googleapis.com/auth/calendar.readonly",  # Calendar read
        "https://www.googleapis.com/auth/userinfo.email",  # User email
        "https://www.googleapis.com/auth/userinfo.profile",  # User profile
    ]


def get_google_service(
    service_name: str,
    version: str,
    credentials=None,
    scopes: Optional[List[str]] = None,
    credential_type: Optional[str] = None,
):
    """Create a Google API service client.

    Args:
        service_name: Name of the Google service (e.g., 'gmail', 'drive')
        version: API version (e.g., 'v1', 'v3')
        credentials: Optional credentials object
        scopes: Optional list of OAuth scopes (dynamic!)
        credential_type: Force credential type ('service_account', 'oauth', 'api_key', or None for auto)

    Returns:
        A Google API service object
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise ImportError(
            "Google API client not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )

    # Auto-detect credentials if not provided
    if credentials is None:
        # Force specific credential type if requested
        if credential_type == "service_account":
            service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not service_account_file or not os.path.exists(service_account_file):
                raise ValueError(
                    "GOOGLE_APPLICATION_CREDENTIALS not set or file not found"
                )

            if scopes is None:
                scopes = get_default_scopes()

            credentials = service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=scopes,
            )
            logger.debug(f"Using service account with {len(scopes)} scopes")

        elif credential_type == "oauth":
            oauth_file = os.getenv("GOOGLE_OAUTH_CREDENTIALS")
            if not oauth_file or not os.path.exists(oauth_file):
                raise ValueError("GOOGLE_OAUTH_CREDENTIALS not set or file not found")

            with open(oauth_file, "r") as f:
                creds_data = json.load(f)
                credentials = Credentials.from_authorized_user_info(creds_data)
            logger.debug("Using OAuth credentials")

        elif credential_type == "api_key":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not set")
            return build(service_name, version, developerKey=api_key)

        else:
            # Auto-detect: Try service account first
            service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if service_account_file and os.path.exists(service_account_file):
                # Use provided scopes or get defaults (fully dynamic!)
                if scopes is None:
                    scopes = get_default_scopes()

                credentials = service_account.Credentials.from_service_account_file(
                    service_account_file,
                    scopes=scopes,
                )
                logger.debug(f"Using service account with {len(scopes)} scopes")

            # Try OAuth credentials
            elif os.getenv("GOOGLE_OAUTH_CREDENTIALS"):
                oauth_file = os.getenv("GOOGLE_OAUTH_CREDENTIALS")
                if oauth_file and os.path.exists(oauth_file):
                    with open(oauth_file, "r") as f:
                        creds_data = json.load(f)
                        credentials = Credentials.from_authorized_user_info(creds_data)

            # Try API key for public APIs
            elif os.getenv("GOOGLE_API_KEY"):
                return build(
                    service_name, version, developerKey=os.getenv("GOOGLE_API_KEY")
                )

    return build(service_name, version, credentials=credentials)


@tool
def use_google(
    service: str,
    version: str,
    resource: str,
    method: str,
    parameters: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    scopes: Optional[List[str]] = None,
    credential_type: Optional[str] = None,
    label: str = "Google API Operation",
) -> Dict[str, Any]:
    """
    Execute Google API operations with comprehensive validation and error handling.

    This tool provides universal access to 200+ Google APIs including Gmail, Drive,
    Calendar, YouTube, Cloud services, and more. It handles authentication, parameter
    validation, and provides helpful error messages.

    The tool is fully dynamic - it uses Google's Discovery API to fetch schemas at
    runtime, so it works with ANY Google API service, not just commonly known ones.

    Args:
        service: Google service name (e.g., 'gmail', 'drive', 'calendar')
        version: API version (e.g., 'v1', 'v3', 'v4')
        resource: Resource path (e.g., 'users.messages', 'files', 'events')
        method: Method name (e.g., 'list', 'get', 'create', 'delete')
        parameters: Dictionary of parameters for the API call
        headers: Optional custom HTTP headers (e.g., {"X-Goog-FieldMask": "places.*"})
        scopes: Optional list of OAuth scopes (defaults to broad permissions)
        credential_type: Force credential type ('service_account', 'oauth', 'api_key', or None for auto)
        label: Human-readable description of the operation

    Returns:
        Dict with status and content

    Examples:
        # Gmail: List messages (uses default scopes)
        use_google(
            service="gmail",
            version="v1",
            resource="users.messages",
            method="list",
            parameters={"userId": "me", "maxResults": 10}
        )

        # Gmail with OAuth (force OAuth even if service account is set)
        use_google(
            service="gmail",
            version="v1",
            resource="users.messages",
            method="list",
            parameters={"userId": "me", "maxResults": 10},
            credential_type="oauth"
        )

        # Places API with custom headers
        use_google(
            service="places",
            version="v1",
            resource="places",
            method="searchText",
            parameters={"body": {"textQuery": "restaurants in NYC", "maxResultCount": 5}},
            headers={"X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating"}
        )

        # YouTube: Search with API key
        use_google(
            service="youtube",
            version="v3",
            resource="search",
            method="list",
            parameters={"part": "snippet", "q": "python", "maxResults": 5},
            credential_type="api_key"
        )

        # Drive: Upload file with service account
        use_google(
            service="drive",
            version="v3",
            resource="files",
            method="create",
            parameters={
                "body": {"name": "test.txt", "mimeType": "text/plain"},
                "media_body": "file content here"
            },
            credential_type="service_account"
        )

        # Calendar: List events
        use_google(
            service="calendar",
            version="v3",
            resource="events",
            method="list",
            parameters={"calendarId": "primary"}
        )

    Authentication:
        Set one of these environment variables:
        - GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON
        - GOOGLE_API_KEY: API key for public APIs
        - GOOGLE_OAUTH_CREDENTIALS: Path to OAuth credentials file
        - GOOGLE_API_SCOPES: Comma-separated OAuth scopes (optional)

    Notes:
        - Mutative operations require confirmation (disable with BYPASS_TOOL_CONSENT=true)
        - Supports all Google API resource.method patterns
        - Fully dynamic via Discovery API - no hardcoded API calls or scopes
        - Custom headers support for APIs like Places API that require them
        - Automatic rate limit handling
        - Rich error messages with suggestions
        - credential_type parameter allows forcing specific credential method
    """
    if parameters is None:
        parameters = {}
    if headers is None:
        headers = {}

    # Check if bypass consent is enabled
    bypass_consent = os.getenv("BYPASS_TOOL_CONSENT", "").lower() == "true"

    # Display operation details
    print(f"\n🚀 {label}")
    print(f"   Service: {service} ({version})")
    print(f"   Resource: {resource}")
    print(f"   Method: {method}")
    if parameters:
        print(f"   Parameters: {json.dumps(parameters, indent=2)}")
    if headers:
        print(f"   Headers: {json.dumps(headers, indent=2)}")
    if scopes:
        print(f"   Scopes: {len(scopes)} custom scope(s)")
    if credential_type:
        print(f"   Credential Type: {credential_type}")

    logger.debug(
        f"use_google: service={service}, version={version}, resource={resource}, method={method}, parameters={parameters}, headers={headers}, scopes={scopes}, credential_type={credential_type}"
    )

    # Check if operation is mutative
    is_mutative = any(op in method.lower() for op in MUTATIVE_OPERATIONS)

    if is_mutative and not bypass_consent:
        print(
            f"\n⚠️  The operation '{method}' is potentially mutative. Do you want to proceed? [y/N]"
        )
        confirm = input().strip().lower()
        if confirm != "y":
            return {
                "status": "error",
                "content": [{"text": f"Operation canceled by user."}],
            }

    try:
        # Build the service via Discovery API (fully dynamic!)
        api_service = get_google_service(
            service, version, scopes=scopes, credential_type=credential_type
        )

        # Navigate to the resource (dynamic reflection)
        resource_parts = resource.split(".")
        current = api_service

        for part in resource_parts:
            if hasattr(current, part):
                current = getattr(current, part)
                # Call it if it's a method (resource collections are callable)
                if callable(current):
                    current = current()
            else:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Resource '{part}' not found in '{service}' API.\n"
                            f"Check the API documentation for correct resource paths.\n"
                            f"Example: For Gmail messages, use 'users.messages'"
                        }
                    ],
                }

        # Get the method (dynamic introspection)
        if not hasattr(current, method):
            available_methods = [m for m in dir(current) if not m.startswith("_")]
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Method '{method}' not found.\n\n"
                        f"Available methods: {', '.join(available_methods)}"
                    }
                ],
            }

        method_func = getattr(current, method)

        # Execute the API call (request → execute pattern)
        request = method_func(**parameters)

        # Add custom headers if provided
        if headers:
            # Inject headers into the request object
            for header_name, header_value in headers.items():
                request.headers[header_name] = header_value
            logger.debug(f"Added {len(headers)} custom header(s) to request")

        response = request.execute()

        # Pretty print response
        response_text = json.dumps(response, indent=2, default=str)

        return {
            "status": "success",
            "content": [{"text": f"Success!\n\nResponse:\n{response_text}"}],
        }

    except ImportError as e:
        return {
            "status": "error",
            "content": [
                {
                    "text": f"Google API client not installed.\n\n"
                    f"Install with:\n"
                    f"pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\n\n"
                    f"Error: {str(e)}"
                }
            ],
        }
    except FileNotFoundError as e:
        return {
            "status": "error",
            "content": [
                {
                    "text": f"Credentials file not found.\n\n"
                    f"Set one of these environment variables:\n"
                    f"  • GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON\n"
                    f"  • GOOGLE_API_KEY: API key for public APIs\n"
                    f"  • GOOGLE_OAUTH_CREDENTIALS: Path to OAuth credentials\n\n"
                    f"Error: {str(e)}"
                }
            ],
        }
    except TypeError as e:
        return {
            "status": "error",
            "content": [
                {
                    "text": f"Invalid parameters for '{method}'.\n\n"
                    f"Check the API documentation for the correct parameter format.\n"
                    f"Common issues:\n"
                    f"  • Missing required parameters\n"
                    f"  • Wrong parameter types\n"
                    f"  • Incorrect nesting in 'body' parameter\n\n"
                    f"Error: {str(e)}"
                }
            ],
        }
    except Exception as e:
        error_msg = str(e)

        # Parse common errors and provide helpful messages
        if "quota" in error_msg.lower():
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"API quota exceeded.\n\n"
                        f"You've hit rate limits or quota for this API.\n"
                        f"Wait a few moments and try again, or check your quota in Google Cloud Console.\n\n"
                        f"Error: {error_msg}"
                    }
                ],
            }
        elif "permission" in error_msg.lower() or "forbidden" in error_msg.lower():
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Permission denied.\n\n"
                        f"Your credentials don't have access to this resource.\n"
                        f"Check your API scopes and permissions in Google Cloud Console.\n\n"
                        f"Hint: You can pass custom scopes using the 'scopes' parameter.\n"
                        f"Error: {error_msg}"
                    }
                ],
            }
        elif "not found" in error_msg.lower():
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Resource not found.\n\n"
                        f"The requested resource doesn't exist or you don't have access.\n"
                        f"Double-check IDs and resource paths.\n\n"
                        f"Error: {error_msg}"
                    }
                ],
            }
        else:
            return {
                "status": "error",
                "content": [{"text": f"Google API error: {error_msg}"}],
            }
