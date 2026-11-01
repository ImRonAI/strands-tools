"""Multi-purpose utility tool for encoding, encryption, formatting, and data manipulation"""

from typing import Dict, Any, Optional
import base64
import binascii
import json
import yaml
import hashlib
import html
import uuid
from cryptography.fernet import Fernet
from urllib.parse import quote, unquote
from strands import tool


@tool
def utility(
    action: str, input: str, key: Optional[str] = None, format: Optional[str] = None
) -> Dict[str, Any]:
    """Multi-purpose utility for common operations

    Args:
        action: Action to perform (base64_encode, base64_decode, json_format,
                json_minify, yaml_to_json, json_to_yaml, encrypt, decrypt,
                hash_md5, hash_sha256, url_encode, url_decode, html_encode,
                html_decode, generate_uuid)
        input: Input string to process
        key: Encryption/decryption key (required for encrypt/decrypt)
        format: Format string for operations

    Returns:
        Dict with status and content
    """
    try:
        result = ""

        # Base64
        if action == "base64_encode":
            result = base64.b64encode(input.encode()).decode()
        elif action == "base64_decode":
            result = base64.b64decode(input.encode()).decode()

        # JSON
        elif action == "json_format":
            result = json.dumps(json.loads(input), indent=2)
        elif action == "json_minify":
            result = json.dumps(json.loads(input), separators=(",", ":"))
        elif action == "json_validate":
            json.loads(input)
            result = "✅ Valid JSON"

        # YAML
        elif action == "yaml_to_json":
            result = json.dumps(yaml.safe_load(input), indent=2)
        elif action == "json_to_yaml":
            result = yaml.dump(json.loads(input), allow_unicode=True)

        # Encryption
        elif action == "encrypt":
            if not key:
                return {"status": "error", "content": [{"text": "❌ Key required"}]}
            f = Fernet(key.encode())
            result = f.encrypt(input.encode()).decode()
        elif action == "decrypt":
            if not key:
                return {"status": "error", "content": [{"text": "❌ Key required"}]}
            f = Fernet(key.encode())
            result = f.decrypt(input.encode()).decode()

        # Hashing
        elif action == "hash_md5":
            result = hashlib.md5(input.encode()).hexdigest()
        elif action == "hash_sha256":
            result = hashlib.sha256(input.encode()).hexdigest()

        # URL
        elif action == "url_encode":
            result = quote(input)
        elif action == "url_decode":
            result = unquote(input)

        # HTML
        elif action == "html_encode":
            result = html.escape(input)
        elif action == "html_decode":
            result = html.unescape(input)

        # UUID
        elif action == "generate_uuid":
            result = str(uuid.uuid4())

        # Case conversion
        elif action == "case_upper":
            result = input.upper()
        elif action == "case_lower":
            result = input.lower()
        elif action == "case_title":
            result = input.title()

        else:
            return {
                "status": "error",
                "content": [{"text": f"❌ Unknown action: {action}"}],
            }

        return {"status": "success", "content": [{"text": result}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"❌ Error: {str(e)}"}]}
