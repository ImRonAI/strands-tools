"""Google OAuth authentication tool for Strands Agents.

Provides OAuth 2.0 authentication for Google APIs with configurable scopes.
Can be run as a standalone script or used as a Strands tool.
"""

import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from strands import tool

# Default comprehensive Google API scopes
DEFAULT_SCOPES = [
    # OpenID
    "openid",
    # Gmail - Full Access
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.settings.sharing",
    # Google Calendar - Full Access
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.settings.readonly",
    # Google Drive - Full Access
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.appdata",
    "https://www.googleapis.com/auth/drive.metadata",
    "https://www.googleapis.com/auth/drive.photos.readonly",
    # Google Sheets
    "https://www.googleapis.com/auth/spreadsheets",
    # Google Docs
    "https://www.googleapis.com/auth/documents",
    # Google Slides
    "https://www.googleapis.com/auth/presentations",
    # YouTube - Full Access
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtubepartner",
    # Custom Search Engine
    "https://www.googleapis.com/auth/cse",
    # Google Contacts/People
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # Google Tasks
    "https://www.googleapis.com/auth/tasks",
    # Google Photos
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    # Google Blogger
    "https://www.googleapis.com/auth/blogger",
    # Google Books
    "https://www.googleapis.com/auth/books",
    # Google Fitness
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.activity.write",
    "https://www.googleapis.com/auth/fitness.location.read",
    "https://www.googleapis.com/auth/fitness.location.write",
    # Google Cloud Platform
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/cloud-platform.read-only",
    # Google Analytics
    "https://www.googleapis.com/auth/analytics.readonly",
    # Google AdSense
    "https://www.googleapis.com/auth/adsense.readonly",
    # Google Classroom
    "https://www.googleapis.com/auth/classroom.courses",
    "https://www.googleapis.com/auth/classroom.rosters",
    # Google Forms
    "https://www.googleapis.com/auth/forms.responses.readonly",
    # Google Business Profile
    "https://www.googleapis.com/auth/business.manage",
]


def authenticate_google_oauth(
    credentials_file: str = "gmail_credentials.json",
    token_file: str = "gmail_token.json",
    scopes: Optional[List[str]] = None,
) -> Optional[Any]:
    """Run OAuth flow to authenticate Google API access.

    Args:
        credentials_file: Path to downloaded OAuth credentials JSON
        token_file: Where to save the generated token
        scopes: List of OAuth scopes (defaults to comprehensive set)

    Returns:
        Credentials object or None if failed
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ Google auth libraries not installed")
        print("Install with: pip install google-auth-oauthlib google-auth-httplib2")
        return None

    if scopes is None:
        scopes = DEFAULT_SCOPES

    creds = None

    # Check if we already have a token
    if os.path.exists(token_file):
        print(f"📝 Loading existing token from {token_file}")
        creds = Credentials.from_authorized_user_file(token_file, scopes)

    # If no valid credentials, run auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                print(f"❌ Credentials file not found: {credentials_file}")
                print("\n📋 Instructions:")
                print("1. Go to: https://console.cloud.google.com/apis/credentials")
                print("2. Create OAuth 2.0 Client ID (Desktop app)")
                print("3. Download JSON and save as 'gmail_credentials.json'")
                return None

            print(f"🔐 Starting OAuth flow with {credentials_file}")
            print(f"🌐 Browser will open - sign in with your Google account")
            print(f"📦 Requesting access to {len(scopes)} scope(s)")

            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
            creds = flow.run_local_server(port=0)

        # Save token for future use
        with open(token_file, "w") as token:
            token.write(creds.to_json())
        print(f"✅ Token saved to {token_file}")

    print(f"✅ Authentication successful!")
    return creds


@tool
def google_auth(
    credentials_file: str = "gmail_credentials.json",
    token_file: str = "gmail_token.json",
    scopes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Authenticate with Google OAuth 2.0 and generate access token.

    This tool runs the OAuth flow to authenticate with Google APIs and generates
    a token file that can be used by use_google and other Google API tools.

    Args:
        credentials_file: Path to OAuth credentials JSON from Google Cloud Console
        token_file: Where to save the generated token (default: gmail_token.json)
        scopes: Optional list of OAuth scopes (defaults to comprehensive set)

    Returns:
        Dict with status and instructions

    Examples:
        # Authenticate with default scopes (comprehensive access)
        google_auth()

        # Authenticate with custom scopes
        google_auth(
            scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )

        # Use custom file paths
        google_auth(
            credentials_file="my_credentials.json",
            token_file="my_token.json"
        )

    Setup Instructions:
        1. Go to: https://console.cloud.google.com/apis/credentials
        2. Create OAuth 2.0 Client ID (Desktop app)
        3. Download JSON and save as 'gmail_credentials.json'
        4. Run this tool - browser will open for sign-in
        5. Set environment variable: export GOOGLE_OAUTH_CREDENTIALS=gmail_token.json
    """
    creds = authenticate_google_oauth(credentials_file, token_file, scopes)

    if creds:
        abs_token_path = os.path.abspath(token_file)

        # Test the credentials
        try:
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds)
            profile = service.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress", "unknown")

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Authentication successful!\n\n"
                        f"📧 Connected to: {email}\n"
                        f"📝 Token saved to: {abs_token_path}\n\n"
                        f"🔧 Set environment variable:\n"
                        f"export GOOGLE_OAUTH_CREDENTIALS={abs_token_path}\n\n"
                        f"🎉 Ready to use Google APIs with {len(scopes or DEFAULT_SCOPES)} scope(s)!"
                    }
                ],
            }
        except Exception as e:
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Token generated: {abs_token_path}\n\n"
                        f"🔧 Set environment variable:\n"
                        f"export GOOGLE_OAUTH_CREDENTIALS={abs_token_path}\n\n"
                        f"⚠️  Could not test credentials: {e}"
                    }
                ],
            }
    else:
        return {
            "status": "error",
            "content": [
                {
                    "text": "❌ Authentication failed\n\n"
                    "Make sure you have:\n"
                    "1. Downloaded OAuth credentials from Google Cloud Console\n"
                    "2. Saved them as 'gmail_credentials.json'\n"
                    "3. Installed required packages: pip install google-auth-oauthlib"
                }
            ],
        }


# Allow running as standalone script
if __name__ == "__main__":
    import sys

    # Accept custom paths as arguments
    creds_file = sys.argv[1] if len(sys.argv) > 1 else "gmail_credentials.json"
    token_file = sys.argv[2] if len(sys.argv) > 2 else "gmail_token.json"

    print("🦆 Google OAuth Authentication Setup")
    print(
        "📦 Gmail, Calendar, Drive, YouTube, Sheets, Docs, Slides, Photos, Tasks, Contacts, and more"
    )
    print("=" * 80)

    creds = authenticate_google_oauth(creds_file, token_file)

    if creds:
        print(f"\n🔧 Set environment variable:")
        print(f"export GOOGLE_OAUTH_CREDENTIALS={os.path.abspath(token_file)}")

        # Test the credentials
        try:
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds)
            profile = service.users().getProfile(userId="me").execute()
            print(f"\n📧 Connected to: {profile.get('emailAddress')}")
            print(f"\n✅ Ready to use all Google APIs!")
        except Exception as e:
            print(f"\n⚠️  Warning: Could not test credentials: {e}")
    else:
        print("\n❌ Authentication failed")
        sys.exit(1)
