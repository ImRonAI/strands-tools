"""Gmail helper tools for easy email operations.

Simplifies common Gmail operations like sending emails without dealing with base64 encoding.
"""

import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
import json
from strands import tool


def create_message(
    sender: str,
    to: str,
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    html: bool = False,
) -> str:
    """Create a base64 encoded email message.

    Args:
        sender: Sender email address
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text or HTML)
        cc: Optional list of CC recipients
        bcc: Optional list of BCC recipients
        html: If True, body is treated as HTML

    Returns:
        Base64 URL-safe encoded message string
    """
    from email.mime.base import MIMEBase

    message: MIMEBase
    if html:
        message = MIMEMultipart("alternative")
        text_part = MIMEText(body, "plain")
        html_part = MIMEText(body, "html")
        message.attach(text_part)
        message.attach(html_part)
    else:
        message = MIMEText(body)

    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject

    if cc:
        message["Cc"] = ", ".join(cc)
    if bcc:
        message["Bcc"] = ", ".join(bcc)

    # Encode to base64 URL-safe format
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return raw_message


@tool
def gmail_send(
    to: str,
    subject: str,
    body: str,
    sender: str = "me",
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    html: bool = False,
    credential_type: str = "oauth",
) -> Dict[str, Any]:
    """
    Send an email via Gmail with automatic message formatting.

    This tool simplifies email sending by handling base64 encoding and message
    formatting automatically. No need to manually encode messages!

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body content (plain text or HTML)
        sender: Sender email ("me" for authenticated user, or specific email)
        cc: Optional list of CC recipients
        bcc: Optional list of BCC recipients
        html: If True, body is treated as HTML content
        credential_type: Credential type to use (default: "oauth")

    Returns:
        Dict with status and response

    Examples:
        # Simple email
        gmail_send(
            to="friend@example.com",
            subject="Hello!",
            body="This is a test email."
        )

        # With CC and BCC
        gmail_send(
            to="friend@example.com",
            subject="Team Update",
            body="Meeting at 3pm",
            cc=["boss@example.com"],
            bcc=["archive@example.com"]
        )

        # HTML email
        gmail_send(
            to="friend@example.com",
            subject="Newsletter",
            body="<h1>Hello!</h1><p>This is <b>HTML</b> content.</p>",
            html=True
        )
    """
    # Import use_google from same package
    from strands_google.use_google import use_google

    # Get sender email if "me"
    if sender == "me":
        # Get profile to determine sender email
        profile_result = use_google(
            service="gmail",
            version="v1",
            resource="users",
            method="getProfile",
            parameters={"userId": "me"},
            credential_type=credential_type,
            label="Get Gmail profile for sender email",
        )

        if profile_result["status"] == "success":
            profile_data = json.loads(
                profile_result["content"][0]["text"].split("Response:\n")[1]
            )
            sender = profile_data.get("emailAddress", "me")

    # Create base64 encoded message
    raw_message = create_message(
        sender=sender, to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html
    )

    # Send via use_google tool
    result = use_google(
        service="gmail",
        version="v1",
        resource="users.messages",
        method="send",
        parameters={"userId": "me", "body": {"raw": raw_message}},
        credential_type=credential_type,
        label=f"Send email to {to}",
    )

    return result


@tool
def gmail_reply(
    message_id: str,
    body: str,
    thread_id: Optional[str] = None,
    html: bool = False,
    credential_type: str = "oauth",
) -> Dict[str, Any]:
    """
    Reply to an existing Gmail message.

    Args:
        message_id: ID of the message to reply to
        body: Reply body content
        thread_id: Optional thread ID (auto-fetched if not provided)
        html: If True, body is treated as HTML
        credential_type: Credential type to use (default: "oauth")

    Returns:
        Dict with status and response

    Example:
        gmail_reply(
            message_id="19b1ff0cf255af0d",
            body="Thanks for your email! I'll get back to you soon."
        )
    """
    # Import use_google from same package
    from strands_google.use_google import use_google

    # Get original message to extract thread_id and headers
    msg_result = use_google(
        service="gmail",
        version="v1",
        resource="users.messages",
        method="get",
        parameters={
            "userId": "me",
            "id": message_id,
            "format": "metadata",
            "metadataHeaders": ["From", "To", "Subject"],
        },
        credential_type=credential_type,
        label="Get original message for reply",
    )

    if msg_result["status"] != "success":
        return msg_result

    msg_data = json.loads(msg_result["content"][0]["text"].split("Response:\n")[1])

    if not thread_id:
        thread_id = msg_data.get("threadId")

    # Extract headers
    headers = msg_data.get("payload", {}).get("headers", [])
    original_from: Optional[str] = None
    original_subject: Optional[str] = None

    for header in headers:
        if header["name"] == "From":
            original_from = header["value"]
        elif header["name"] == "Subject":
            original_subject = header["value"]

    # Validate required fields
    if not original_from:
        return {
            "status": "error",
            "content": [{"text": "Could not extract sender from original message"}],
        }

    # Add "Re:" prefix if not present
    reply_subject = original_subject or "Re: (no subject)"
    if not reply_subject.startswith("Re:"):
        reply_subject = f"Re: {reply_subject}"

    # Get sender email
    profile_result = use_google(
        service="gmail",
        version="v1",
        resource="users",
        method="getProfile",
        parameters={"userId": "me"},
        credential_type=credential_type,
        label="Get Gmail profile",
    )

    sender = "me"
    if profile_result["status"] == "success":
        profile_data = json.loads(
            profile_result["content"][0]["text"].split("Response:\n")[1]
        )
        sender = profile_data.get("emailAddress", "me")

    # Create reply message
    raw_message = create_message(
        sender=sender, to=original_from, subject=reply_subject, body=body, html=html
    )

    # Send reply
    result = use_google(
        service="gmail",
        version="v1",
        resource="users.messages",
        method="send",
        parameters={
            "userId": "me",
            "body": {"raw": raw_message, "threadId": thread_id},
        },
        credential_type=credential_type,
        label=f"Reply to message {message_id}",
    )

    return result
