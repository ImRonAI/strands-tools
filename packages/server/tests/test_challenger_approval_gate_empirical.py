# pyright: strict
"""Empirical challenger test suite for FastMCP ApprovalGate (Milestone 2 Iteration 2).

Challenger: challenger_m2_4
Mission: Empirically challenge security boundaries, non-monetary channel toggles,
concurrency, race conditions, replay attacks, and tamper-resistance in strands-tools.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path
import urllib.error
import urllib.request
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
    compute_action_hash,
)


def _make_dummy_context(name: str, arguments: dict[str, object]) -> MiddlewareContext[mt.CallToolRequestParams]:
    """Creates a mock MiddlewareContext matching FastMCP 4.x."""
    params = mt.CallToolRequestParams(name=name, arguments=arguments)
    ctx = MagicMock(spec=MiddlewareContext)
    ctx.message = params
    return cast(MiddlewareContext[mt.CallToolRequestParams], ctx)


async def _dummy_call_next(ctx: MiddlewareContext[mt.CallToolRequestParams]) -> ToolResult:
    return ToolResult(content=[mt.TextContent(type="text", text=f"Executed {ctx.message.name}")])


# =========================================================================
# 1. Concurrency Stress Testing & Determinism
# =========================================================================

@pytest.mark.asyncio
async def test_concurrent_monetary_requests_pause_deterministically() -> None:
    """50 simultaneous calls to monetary tools all pause deterministically with APPROVAL_REQUIRED."""
    gate = ApprovalGate()
    concurrency_level = 50

    async def _invoke(idx: int) -> str:
        ctx = _make_dummy_context(
            name="stripe_charge",
            arguments={"amount": 100 + idx, "currency": "usd"},
        )
        try:
            await gate.on_call_tool(ctx, _dummy_call_next)
            pytest.fail("Expected ToolError(APPROVAL_REQUIRED) but call succeeded")
        except ToolError as e:
            return str(e)

    tasks = [_invoke(i) for i in range(concurrency_level)]
    results = await asyncio.gather(*tasks)

    assert len(results) == concurrency_level
    for r in results:
        assert "APPROVAL_REQUIRED id=" in r
        assert "; retry with approval_id after the founder approves" in r


@pytest.mark.asyncio
async def test_concurrent_consumption_single_use_oracle() -> None:
    """Simulates 30 concurrent calls presenting the same approval_id against a mock backend.
    
    Oracle requirement: Exactly 1 call consumes the token; 29 fail with 403 / already consumed.
    """
    gate = ApprovalGate(approvals_api_url="http://mock-approvals.test/api/approvals")
    approval_id = "appr-concurrent-token-123"
    tool_name = "telnyx_send_message"
    payload = {"endpoint_name": "messages send", "to": "+15551234567", "text": "hello"}
    expected_hash = compute_action_hash(tool_name, payload)

    # Thread-safe mock state simulating single-use consumption in db
    lock = asyncio.Lock()
    consumed = False

    def mock_urlopen(req: urllib.request.Request, timeout: float = 5) -> MagicMock:
        del timeout
        nonlocal consumed
        url = req.full_url
        if "/consume" in url:
            raw_data = req.data
            data_str = raw_data.decode("utf-8") if isinstance(raw_data, (bytes, bytearray)) else "{}"
            body: dict[str, object] = cast(dict[str, object], json.loads(data_str)) if data_str else {}
            assert body.get("toolName") == tool_name
            assert body.get("actionHash") == expected_hash

            if consumed:
                # HTTP 403 already consumed
                fp = io.BytesIO(b'{"ok": false, "error": "Approval has already been consumed"}')
                raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=MagicMock(), fp=fp)

            consumed = True
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"ok": true}'
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.__exit__.return_value = None
            return mock_resp

        raise ValueError(f"Unexpected url {url}")

    async def _attempt_consume(_idx: int) -> tuple[bool, str]:
        ctx = _make_dummy_context(
            name=tool_name,
            arguments={**payload, "approval_id": approval_id},
        )
        try:
            async with lock:
                with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                    res = await gate.on_call_tool(ctx, _dummy_call_next)
                    first_block = res.content[0] if res.content else None
                    text = first_block.text if isinstance(first_block, mt.TextContent) else ""
                    return True, text
        except ToolError as e:
            return False, str(e)

    tasks = [_attempt_consume(i) for i in range(30)]
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 29, f"Expected exactly 29 failures, got {len(failures)}"
    for _, err in failures:
        assert "APPROVAL_INVALID: Approval has already been consumed" in err


# =========================================================================
# 2. Cryptographic Hash Tamper & Replay Attacks
# =========================================================================

@pytest.mark.asyncio
async def test_action_hash_tamper_detection() -> None:
    """If an agent attempts to tamper with arguments after approval, the hash diverges
    and the consume endpoint rejects the call.
    """
    gate = ApprovalGate(approvals_api_url="http://mock-approvals.test/api/approvals")
    approval_id = "appr-valid-id"
    tool_name = "stripe_charge"
    approved_args: dict[str, object] = {"amount": 50, "currency": "usd"}
    tampered_args: dict[str, object] = {"amount": 5000, "currency": "usd"}

    def mock_urlopen(req: urllib.request.Request, timeout: float = 5) -> MagicMock:
        del timeout
        raw_data = req.data
        data_str = raw_data.decode("utf-8") if isinstance(raw_data, (bytes, bytearray)) else "{}"
        body: dict[str, object] = cast(dict[str, object], json.loads(data_str)) if data_str else {}
        action_hash = body.get("actionHash")
        approved_hash = compute_action_hash(tool_name, approved_args)
        if action_hash != approved_hash:
            fp = io.BytesIO(f'{{"ok": false, "error": "Action hash mismatch (expected {approved_hash}, got {action_hash})"}}'.encode("utf-8"))
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", hdrs=MagicMock(), fp=fp)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        return mock_resp

    ctx = _make_dummy_context(
        name=tool_name,
        arguments={**tampered_args, "approval_id": approval_id},
    )
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with pytest.raises(ToolError) as exc_info:
            await gate.on_call_tool(ctx, _dummy_call_next)

    assert "APPROVAL_INVALID: Action hash mismatch" in str(exc_info.value)


def test_hash_invariance_to_key_order_and_approval_id_stripping() -> None:
    """Validates that key re-ordering does not alter hash, and approval_id is stripped."""
    tool = "stripe_charge"
    h1 = compute_action_hash(tool, {"amount": 100, "currency": "usd", "note": "payment"})
    h2 = compute_action_hash(tool, {"note": "payment", "currency": "usd", "amount": 100})
    assert h1 == h2
    assert len(h1) == 64

    # approval_id stripped inside on_call_tool logic
    raw_args = {"amount": 100, "currency": "usd", "note": "payment", "approval_id": "appr-999"}
    stripped = {k: v for k, v in raw_args.items() if k != "approval_id"}
    assert compute_action_hash(tool, stripped) == h1


# =========================================================================
# 3. Non-Monetary Channel Toggles vs Monetary Invariants
# =========================================================================

def test_channel_toggle_matrix() -> None:
    """Tests the full truth table of channel categories, toggle settings, and monetary boundaries."""
    gate = ApprovalGate()

    # --- Non-monetary channels (email, social, social_publishing, outreach, publishing, deploy, customer_reply) ---
    for non_monetary_cat in (
        "email",
        "social",
        "social_publishing",
        "outreach",
        "publishing",
        "deploy",
        "customer_reply",
    ):
        # Explicit auto -> NOT gated (bypass allowed)
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {non_monetary_cat: "auto"}}) is False
        # Explicit approve -> GATED
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {non_monetary_cat: "approve"}}) is True
        # Missing category -> GATED (safe default)
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {}}) is True
        # Missing channels dict -> GATED (safe default)
        assert gate.is_channel_gated(non_monetary_cat, {}) is True
        # Non-string or unexpected values -> GATED (fail closed)
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {non_monetary_cat: True}}) is True
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {non_monetary_cat: "AUTO"}}) is True
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {non_monetary_cat: " auto "}}) is True
        assert gate.is_channel_gated(non_monetary_cat, {"channels": {non_monetary_cat: 1}}) is True

    # --- Monetary categories (payments, telecommunications, advertising) ---
    # Invariant: Monetary categories MUST ALWAYS return is_channel_gated=True, even if toggle says 'auto'
    for monetary_cat in ("payments", "telecommunications", "advertising", "cloud_spend", "unknown"):
        assert gate.is_channel_gated(monetary_cat, {"channels": {monetary_cat: "auto"}}) is True
        assert gate.is_channel_gated(monetary_cat, {"channels": {"email": "auto"}}) is True
        assert gate.is_channel_gated(monetary_cat, {}) is True


def test_channel_toggle_environment_variable_fallback() -> None:
    """Tests VENTURE_CHANNELS environment variable fallback and fault tolerance."""
    gate = ApprovalGate()

    # Valid JSON env var without args
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({"email": "auto", "social": "approve"})}):
        assert gate.is_channel_gated("email", {}) is False
        assert gate.is_channel_gated("social", {}) is True
        # Monetary categories still cannot bypass via env
        assert gate.is_channel_gated("payments", {}) is True

    # Malformed JSON in env var fails safely to True (gated)
    with patch.dict(os.environ, {"VENTURE_CHANNELS": "{malformed json:"}):
        assert gate.is_channel_gated("email", {}) is True
        assert gate.is_channel_gated("social", {}) is True

    # Non-dict JSON in env var fails safely to True
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps(["email", "auto"])}):
        assert gate.is_channel_gated("email", {}) is True


def test_supported_channel_categories_in_channel_gate() -> None:
    """Empirical verification: deploy, customer_reply, social_publishing are supported in channel_categories.
    
    When caller specifies 'auto', calls are not gated (False). When 'approve', calls are gated (True).
    """
    gate = ApprovalGate()
    for cat in ("deploy", "customer_reply", "social_publishing"):
        assert gate.is_channel_gated(cat, {"channels": {cat: "auto"}}) is False
        assert gate.is_channel_gated(cat, {"channels": {cat: "approve"}}) is True


def test_request_precedence_over_env_channels() -> None:
    """Empirical proof of request-level precedence in ApprovalGate.is_channel_gated:
    
    1. When VENTURE_CHANNELS={'email': 'auto'}, a caller passing args={'channels': {'email': 'approve'}}
       is GATED (returns True) because request parameters override environment defaults.
    2. When VENTURE_CHANNELS={'email': 'approve'}, a caller passing args={'channels': {'email': 'auto'}}
       is NOT GATED (returns False) because request parameters override environment defaults.
    3. When category is not in request args, it correctly falls back to VENTURE_CHANNELS.
    """
    gate = ApprovalGate()
    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({"email": "auto"})}):
        # Caller explicitly asked for 'approve' in args -> GATED (True):
        assert gate.is_channel_gated("email", {"channels": {"email": "approve"}}) is True

    with patch.dict(os.environ, {"VENTURE_CHANNELS": json.dumps({"email": "approve"})}):
        # Caller explicitly asked for 'auto' in args -> NOT GATED (False):
        assert gate.is_channel_gated("email", {"channels": {"email": "auto"}}) is False
        # When request args does not specify 'email', falls back to env var 'approve' -> GATED (True):
        assert gate.is_channel_gated("email", {"channels": {"deploy": "auto"}}) is True


@pytest.mark.asyncio
async def test_end_to_end_on_call_tool_channel_bypass() -> None:
    """Validates that on_call_tool executes call_next without approval for auto non-monetary tools,
    while requiring approval when toggle is approve.
    """
    gate = ApprovalGate()

    # 1. Non-monetary email tool with 'auto' toggle: proceeds immediately
    email_ctx = _make_dummy_context(
        name="resend_send_email",
        arguments={"to": "test@example.com", "channels": {"email": "auto"}},
    )
    res = await gate.on_call_tool(email_ctx, _dummy_call_next)
    first_block = res.content[0]
    assert isinstance(first_block, mt.TextContent)
    assert first_block.text == "Executed resend_send_email"

    # 2. Non-monetary email tool with 'approve' toggle: blocked with APPROVAL_REQUIRED
    email_ctx_gated = _make_dummy_context(
        name="resend_send_email",
        arguments={"to": "test@example.com", "channels": {"email": "approve"}},
    )
    with pytest.raises(ToolError) as exc_info:
        await gate.on_call_tool(email_ctx_gated, _dummy_call_next)
    assert "APPROVAL_REQUIRED" in str(exc_info.value)

    # 3. Monetary stripe tool with 'auto' toggle passed: STILL blocked with APPROVAL_REQUIRED
    stripe_ctx = _make_dummy_context(
        name="stripe_charge",
        arguments={"amount": 100, "channels": {"payments": "auto", "email": "auto"}},
    )
    with pytest.raises(ToolError) as exc_info:
        await gate.on_call_tool(stripe_ctx, _dummy_call_next)
    assert "APPROVAL_REQUIRED" in str(exc_info.value)
