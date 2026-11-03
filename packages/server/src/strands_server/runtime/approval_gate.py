# pyright: strict
"""Money approval gate as FastMCP middleware on the Agent Factory root (CAT-115)."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeGuard

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
import mcp.types as mt

logger = logging.getLogger(__name__)

_RULES_FILE = Path(__file__).parent / "money_rules.json"


def _is_str_mapping(val: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(val, Mapping)


def _is_obj_sequence(val: object) -> TypeGuard[Sequence[object]]:
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes))


def canonical_json(data: object) -> str:
    """Produces sorted-key compact JSON matching Branding-App canonicalJson."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_action_hash(tool_name: str, payload: Mapping[str, object]) -> str:
    canonical = canonical_json({"payload": dict(payload), "toolName": tool_name})
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

    def _load_rules(self) -> list[dict[str, object]]:
        if _RULES_FILE.exists():
            try:
                loaded: object = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
                if _is_obj_sequence(loaded):
                    return [dict(item) for item in loaded if _is_str_mapping(item)]
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

    def is_money_tool(self, name: str, args: Mapping[str, object]) -> tuple[bool, str]:
        for rule in self.rules:
            glob_pat = str(rule.get("tool_glob", "*"))
            if fnmatch.fnmatch(name, glob_pat):
                raw_eps = rule.get("endpoints")
                endpoints = [str(ep) for ep in raw_eps] if _is_obj_sequence(raw_eps) else []
                if endpoints:
                    endpoint_name = str(args.get("endpoint_name", "")).lower()
                    if any(ep in endpoint_name for ep in endpoints):
                        return True, str(rule.get("category", "money_costing"))
                    continue
                return True, str(rule.get("category", "money_costing"))
        return False, ""

    def is_channel_gated(self, category: str, args: Mapping[str, object]) -> bool:
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
            return True

        channels = args.get("channels")
        if _is_str_mapping(channels) and category in channels:
            return channels.get(category) != "auto"

        env_channels = os.environ.get("VENTURE_CHANNELS")
        if env_channels:
            try:
                parsed: object = json.loads(env_channels)
                if _is_str_mapping(parsed) and category in parsed:
                    return parsed.get(category) != "auto"
            except Exception:
                pass
        return True

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: Callable[[MiddlewareContext[mt.CallToolRequestParams]], Awaitable[ToolResult]],
    ) -> ToolResult:
        p = context.message
        name = p.name
        raw_args: dict[str, object] = dict(p.arguments) if p.arguments is not None else {}

        is_gated, category = self.is_money_tool(name, raw_args)
        if not is_gated:
            return await call_next(context)

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
                body: object = json.loads(e.read().decode("utf-8"))
                if _is_str_mapping(body):
                    return False, str(body.get("error", str(e)))
                return False, str(e)
            except Exception:
                return False, str(e)
        except Exception as e:
            logger.warning("Could not contact approvals API: %s", e)
            return False, str(e)

    def _request_approval(
        self, tool_name: str, args: Mapping[str, object], category: str, action_hash: str
    ) -> str:
        req_data = json.dumps(
            {
                "toolName": tool_name,
                "args": dict(args),
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
                    res: object = json.loads(response.read().decode("utf-8"))
                    if _is_str_mapping(res):
                        return str(res.get("id", ""))
        except Exception as e:
            logger.warning("Approvals API request failed: %s", e)

        return f"appr-{action_hash[:12]}"
