"""Money approval gate as FastMCP middleware on the Agent Factory root (CAT-115)."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
import mcp.types as mt

logger = logging.getLogger(__name__)

_RULES_FILE = Path(__file__).parent / "money_rules.json"


def canonical_json(data: Any) -> str:
    """Produces sorted-key compact JSON matching Branding-App canonicalJson."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_action_hash(tool_name: str, payload: dict[str, Any]) -> str:
    canonical = canonical_json({"payload": payload, "toolName": tool_name})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalGate(Middleware):
    def __init__(self, approvals_api_url: str | None = None, service_token: str | None = None) -> None:
        super().__init__()
        self.approvals_api_url = (
            approvals_api_url
            or os.environ.get("APPROVALS_API_URL")
            or "http://localhost:3000/api/approvals"
        )
        self.service_token = service_token or os.environ.get("APPROVALS_SERVICE_TOKEN", "")
        self.rules = self._load_rules()

    def _load_rules(self) -> list[dict[str, Any]]:
        if _RULES_FILE.exists():
            try:
                loaded = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    return [item for item in loaded if isinstance(item, dict)]
            except Exception as e:
                logger.warning("Failed to load money_rules.json: %s", e)
        return [
            {
                "tool_glob": "telnyx_*",
                "endpoints": [
                    "messages send",
                    "calls dial",
                    "number orders create",
                    "porting",
                    "10dlc",
                    "fax send",
                ],
                "category": "telecommunications",
            },
            {
                "tool_glob": "*stripe*",
                "category": "payments",
            },
            {
                "tool_glob": "*resend*",
                "category": "email",
            },
        ]

    def is_money_tool(self, name: str, args: dict[str, Any]) -> tuple[bool, str]:
        for rule in self.rules:
            glob_pat = str(rule.get("tool_glob", "*"))
            if fnmatch.fnmatch(name, glob_pat):
                endpoints: list[str] = rule.get("endpoints", [])
                if endpoints:
                    endpoint_name = str(args.get("endpoint_name", "")).lower()
                    if any(ep in endpoint_name for ep in endpoints):
                        return True, str(rule.get("category", "money_costing"))
                    # If endpoints required but not matched, do not match this rule
                    continue
                return True, str(rule.get("category", "money_costing"))
        return False, ""

    def is_channel_gated(self, category: str, args: dict[str, Any]) -> bool:
        """Checks if a non-monetary channel tool is gated based on venture channel toggles (CAT-115 FR-M2-4.5)."""
        channel_categories = {
            "email",
            "social",
            "social_publishing",
            "outreach",
            "publishing",
            "deploy",
            "customer_reply",
        }
        if category not in channel_categories:
            return True  # Monetary spend always requires approval

        channels = args.get("channels")
        if isinstance(channels, dict) and category in channels:
            return channels.get(category) != "auto"

        env_channels = os.environ.get("VENTURE_CHANNELS")
        if env_channels:
            try:
                parsed = json.loads(env_channels)
                if isinstance(parsed, dict) and category in parsed:
                    return parsed.get(category) != "auto"
            except Exception:
                pass
        return True

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: Any,
    ) -> ToolResult:
        p = context.message
        name = p.name
        raw_args: dict[str, Any] = p.arguments or {}

        is_gated, category = self.is_money_tool(name, raw_args)
        if not is_gated:
            return await call_next(context)

        # Non-monetary channel toggle: if set to 'auto', proceed without approval gate
        if not self.is_channel_gated(category, raw_args):
            return await call_next(context)

        args = {k: v for k, v in raw_args.items() if k != "approval_id"}
        action_hash = compute_action_hash(name, args)
        approval_id = raw_args.get("approval_id")

        if approval_id:
            ok, err = self._consume_approval(str(approval_id), name, action_hash)
            if ok:
                return await call_next(context)
            raise ToolError(f"APPROVAL_INVALID: {err}")

        req_id = self._request_approval(name, args, category, action_hash)
        raise ToolError(f"APPROVAL_REQUIRED id={req_id}; retry with approval_id after the founder approves")

    def _consume_approval(self, approval_id: str, tool_name: str, action_hash: str) -> tuple[bool, str]:
        consume_url = f"{self.approvals_api_url}/{approval_id}/consume"
        req_data = json.dumps({"toolName": tool_name, "actionHash": action_hash}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"

        req = urllib.request.Request(consume_url, data=req_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return True, ""
                return False, f"HTTP {response.status}"
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
                return False, body.get("error", str(e))
            except Exception:
                return False, str(e)
        except Exception as e:
            logger.warning("Could not contact approvals API: %s", e)
            return False, str(e)

    def _request_approval(
        self, tool_name: str, args: dict[str, Any], category: str, action_hash: str
    ) -> str:
        req_data = json.dumps(
            {
                "toolName": tool_name,
                "args": args,
                "category": category,
                "actionHash": action_hash,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"

        req = urllib.request.Request(self.approvals_api_url, data=req_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status in (200, 201):
                    res = json.loads(response.read().decode("utf-8"))
                    return str(res.get("id", ""))
        except Exception as e:
            logger.warning("Approvals API request failed: %s", e)

        return f"appr-{action_hash[:12]}"
