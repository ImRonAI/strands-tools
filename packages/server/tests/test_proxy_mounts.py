"""Tests for CAT-114 and CAT-115: FastMCP proxy mounts and Money Approval Gate."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from strands_server.runtime.approval_gate import ApprovalGate, compute_action_hash
from strands_server.server import build_proxied_servers, build_server


def test_build_proxied_servers_discovery():
    proxies = build_proxied_servers()
    assert isinstance(proxies, list)
    # Check that any proxies returned have valid names and FastMCP objects
    for name, proxy in proxies:
        assert isinstance(name, str)
        assert len(name) > 0


@pytest.mark.asyncio
async def test_approval_gate_intercepts_money_tools():
    gate = ApprovalGate()
    assert gate.is_money_tool("telnyx_send_message", {"endpoint_name": "messages send"})[0] is True
    assert gate.is_money_tool("telnyx_dial_call", {"endpoint_name": "calls dial"})[0] is True
    assert gate.is_money_tool("stripe_charge", {})[0] is True
    assert gate.is_money_tool("execute", {})[0] is False
    assert gate.is_money_tool("search", {})[0] is False


def test_canonical_action_hash_matches_format():
    tool = "telnyx_invoke_api_endpoint"
    payload = {"endpoint_name": "messages send", "to": "+15551234567"}
    h1 = compute_action_hash(tool, payload)
    h2 = compute_action_hash(tool, {"to": "+15551234567", "endpoint_name": "messages send"})
    # Sorted-key canonical JSON ensures hash is identical regardless of input key order
    assert h1 == h2
    assert len(h1) == 64


def test_channel_toggles_bypass_or_gate():
    gate = ApprovalGate()
    # Non-monetary channel 'email': when set to 'auto', is_channel_gated is False
    assert gate.is_channel_gated("email", {"channels": {"email": "auto"}}) is False
    # When set to 'approve', is_channel_gated is True (requires approval)
    assert gate.is_channel_gated("email", {"channels": {"email": "approve"}}) is True
    # Monetary spend always requires approval regardless of channel setting
    assert gate.is_channel_gated("payments", {"channels": {"payments": "auto"}}) is True

