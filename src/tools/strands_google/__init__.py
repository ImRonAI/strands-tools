"""strands-google - Google API integration for Strands Agents.

This package provides comprehensive access to 200+ Google APIs including
Gmail, Drive, Calendar, YouTube, and more.

Main exports:
- use_google: Universal Google API access tool
- google_auth: OAuth authentication tool
- gmail_send: Easy email sending
- gmail_reply: Reply to emails
"""

from strands_google.use_google import use_google
from strands_google.google_auth import google_auth
from strands_google.gmail_helpers import gmail_send, gmail_reply

__version__ = "0.1.0"

__all__ = [
    "use_google",
    "google_auth",
    "gmail_send",
    "gmail_reply",
]
