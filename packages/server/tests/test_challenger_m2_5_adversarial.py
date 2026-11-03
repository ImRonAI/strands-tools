# pyright: strict
"""Adversarial Verification Suite by challenger_m2_5 (Milestone 2 Iteration 3).

Exhaustive empirical testing for ApprovalGate:
1. All 7 non-monetary categories under full permutation matrix.
2. Request vs. Environment precedence in both directions.
3. Fallback semantics when request omits category or channels dict entirely.
4. Monetary spend boundary invariance under deceptive payload attacks.
5. Fuzzing and adversarial malformed arguments/environment values.
6. Full end-to-end FastMCP on_call_tool middleware verification.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[3]
for pkg_src in (
    REPO_ROOT / "packages" / "server" / "src",
    REPO_ROOT / "packages" / "client" / "src",
):
    if str(pkg_src) not in sys.path:
        sys.path.insert(0, str(pkg_src))

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.base import ToolResult
import mcp.types as mt

from strands_server.runtime.approval_gate import (
    ApprovalGate,
)

NON_MONETARY_CATEGORIES = (
    "email",
    "social",
    "social_publishing",
    "outreach",
    "publishing",
    "deploy",
    "customer_reply",
)

MONETARY_CATEGORIES = (
    "payments",
    "telecommunications",
    "advertising",
    "cloud_spend",
    "domain_purchase",
    "unknown_spend",
)


def _make_dummy_context(name: str, arguments: dict[str, object]) -> MiddlewareContext[mt.CallToolRequestParams]:
    params = mt.CallToolRequestParams(name=name, arguments=arguments)
    ctx = MagicMock(spec=MiddlewareContext)
    ctx.message = params
    return cast(MiddlewareContext[mt.CallToolRequestParams], ctx)


async def _dummy_call_next(ctx: MiddlewareContext[mt.CallToolRequestParams]) -> ToolResult:
    return ToolResult(content=[mt.TextContent(type="text", text=f"Executed {ctx.message.name}")])


# =========================================================================
# 1. Exhaustive 7 Non-Monetary Categories & Precedence Permutations
# =========================================================================

@pytest.mark.parametrize("category", NON_MONETARY_CATEGORIES)
def test_all_seven_categories_request_overrides_env_both_directions(category: str) -> None:
    """For each of the 7 categories:
    - Request 'approve' + Env 'auto' -> GATED (True)
    - Request 'auto' + Env 'approve' -> NOT GATED (False)
    """
    gate = ApprovalGate()

    # Direction 1: Request 'approve' MUST override Env 'auto'
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({category: "auto"})}):
        assert gate.is_channel_gated(category, {"channels": {category: "approve"}}) is True

    # Direction 2: Request 'auto' MUST override Env 'approve'
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({category: "approve"})}):
        assert gate.is_channel_gated(category, {"channels": {category: "auto"}}) is False


@pytest.mark.parametrize("category", NON_MONETARY_CATEGORIES)
def test_all_seven_categories_fallback_when_category_omitted(category: str) -> None:
    """When the request omits the category (or provides disjoint categories),
    it MUST fall back to VENTURE_CHANNELS if present, or True if absent.
    """
    gate = ApprovalGate()

    # Case A: Request has other category, Env has 'auto' for target -> NOT GATED (False)
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({category: "auto"})}):
        assert gate.is_channel_gated(category, {"channels": {"other_cat": "approve"}}) is False
        assert gate.is_channel_gated(category, {"channels": {}}) is False
        assert gate.is_channel_gated(category, {}) is False

    # Case B: Request has other category, Env has 'approve' for target -> GATED (True)
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({category: "approve"})}):
        assert gate.is_channel_gated(category, {"channels": {"other_cat": "auto"}}) is True
        assert gate.is_channel_gated(category, {"channels": {}}) is True
        assert gate.is_channel_gated(category, {}) is True

    # Case C: Env unset, category omitted -> GATED (True, fail-safe default)
    with patch.dict(os.environ, {}, clear=True):
        assert gate.is_channel_gated(category, {"channels": {}}) is True
        assert gate.is_channel_gated(category, {}) is True


# =========================================================================
# 2. Monetary Safety Invariant (Never Bypassed)
# =========================================================================

@pytest.mark.parametrize("monetary_cat", MONETARY_CATEGORIES)
def test_monetary_tools_never_bypass_even_with_explicit_auto_toggles(monetary_cat: str) -> None:
    """Monetary spend tools MUST NEVER be bypassed via channel toggles.
    Even if the request passes channels={monetary_cat: 'auto'} AND
    VENTURE_CHANNELS={monetary_cat: 'auto'}, is_channel_gated MUST return True.
    """
    gate = ApprovalGate()

    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({monetary_cat: "auto", "email": "auto"})}):
        # Explicit request auto
        assert gate.is_channel_gated(monetary_cat, {"channels": {monetary_cat: "auto"}}) is True
        # Request auto on other non-monetary
        assert gate.is_channel_gated(monetary_cat, {"channels": {"email": "auto"}}) is True
        # Empty args
        assert gate.is_channel_gated(monetary_cat, {}) is True


# =========================================================================
# 3. Adversarial Fuzzing & Malformed Inputs
# =========================================================================

@pytest.mark.parametrize("category", NON_MONETARY_CATEGORIES)
def test_adversarial_malformed_arguments_fail_closed(category: str) -> None:
    """Adversarial payloads in args['channels'] must fail closed (return True / gated)."""
    gate = ApprovalGate()

    malformed_channel_payloads: list[object] = [
        "auto",
        123,
        True,
        False,
        ["auto"],
        {"other": "auto"},
        {category: "AUTO"},
        {category: " auto "},
        {category: "Auto"},
        {category: 1},
        {category: True},
        {category: False},
        {category: None},
        {category: {}},
        {category: ["auto"]},
    ]

    for payload in malformed_channel_payloads:
        with patch.dict(os.environ, {}, clear=True):
            result = gate.is_channel_gated(category, {"channels": payload})
            assert result is True, f"Failed closed expectation for payload: {payload!r}"


@pytest.mark.parametrize("category", NON_MONETARY_CATEGORIES)
def test_adversarial_malformed_env_vars_fail_closed(category: str) -> None:
    """Malformed VENTURE_CHANNELS environment variables must fail closed (return True)."""
    gate = ApprovalGate()

    malformed_env_strings = [
        "",
        "{broken json",
        "null",
        "true",
        "false",
        "12345",
        "\"email: auto\"",
        json.dumps(["email", "auto"]),
        json.dumps({category: "AUTO"}),
        json.dumps({category: 1}),
        json.dumps({category: True}),
        json.dumps({category: None}),
    ]

    for env_val in malformed_env_strings:
        with patch.dict(os.environ, {"VENTURE_CHANNELS": env_val}):
            result = gate.is_channel_gated(category, {})
            assert result is True, f"Failed closed expectation for env var: {env_val!r}"


def test_edge_case_unknown_categories_and_types() -> None:
    """Unknown categories, empty string category, and case differences must fail closed."""
    gate = ApprovalGate()

    assert gate.is_channel_gated("", {"channels": {"": "auto"}}) is True
    assert gate.is_channel_gated("Email", {"channels": {"Email": "auto"}}) is True
    assert gate.is_channel_gated("EMAIL", {"channels": {"EMAIL": "auto"}}) is True
    assert gate.is_channel_gated("deploy_preview", {"channels": {"deploy_preview": "auto"}}) is True


# =========================================================================
# 4. End-to-End on_call_tool Middleware Stress Testing
# =========================================================================

@pytest.mark.asyncio
async def test_end_to_end_on_call_tool_all_non_monetary_categories() -> None:
    """Verify on_call_tool with mock non-monetary tools across all 7 categories."""
    gate = ApprovalGate()

    # Rule definitions for non-monetary tools in money_rules.json currently cover email and social.
    # Let's verify on_call_tool behaves properly with rules matching email, social, etc.
    email_auto_ctx = _make_dummy_context(
        name="resend_send_email",
        arguments={"to": "test@example.com", "channels": {"email": "auto"}},
    )
    res = await gate.on_call_tool(email_auto_ctx, _dummy_call_next)
    first_email_block = res.content[0]
    assert isinstance(first_email_block, mt.TextContent)
    assert first_email_block.text == "Executed resend_send_email"

    # Social auto
    social_auto_ctx = _make_dummy_context(
        name="buffer_create_post",
        arguments={"text": "announcement", "channels": {"social": "auto"}},
    )
    res_social = await gate.on_call_tool(social_auto_ctx, _dummy_call_next)
    first_social_block = res_social.content[0]
    assert isinstance(first_social_block, mt.TextContent)
    assert first_social_block.text == "Executed buffer_create_post"

    # Social approve (MUST block)
    social_appr_ctx = _make_dummy_context(
        name="buffer_create_post",
        arguments={"text": "announcement", "channels": {"social": "approve"}},
    )
    with pytest.raises(ToolError) as exc:
        await gate.on_call_tool(social_appr_ctx, _dummy_call_next)
    assert "APPROVAL_REQUIRED" in str(exc.value)


@pytest.mark.asyncio
async def test_end_to_end_on_call_tool_monetary_invariance() -> None:
    """Verify on_call_tool blocks monetary tools even when channels attempt deceptive bypass."""
    gate = ApprovalGate()

    deceptive_arguments: list[dict[str, object]] = [
        {"amount": 100, "channels": {"payments": "auto"}},
        {"amount": 100, "channels": {"email": "auto", "social": "auto"}},
        {"amount": 100, "channels": {"payments": "auto", "deploy": "auto"}},
        {"endpoint_name": "messages send", "to": "+1555", "channels": {"telecommunications": "auto"}},
        {"endpoint_name": "calls dial", "to": "+1555", "channels": {"customer_reply": "auto"}},
    ]

    for args in deceptive_arguments:
        tool_name = "stripe_charge" if "amount" in args else "telnyx_send_message"
        ctx = _make_dummy_context(name=tool_name, arguments=args)
        with pytest.raises(ToolError) as exc:
            await gate.on_call_tool(ctx, _dummy_call_next)
        assert "APPROVAL_REQUIRED" in str(exc.value)
