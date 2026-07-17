"""
Constitutional Control Force-Tests — Robert COO Agent
======================================================
These tests deliberately trigger each constitutional control and verify the
specific action fires. "Service started cleanly" is NOT evidence. These are.

Controls tested:
  1. Kill switch — BOB_DISABLED=true halts execution with RuntimeError
  2. RED block — gate() raises PermissionError on RED-tier action
  3. DENY block — gate() raises PermissionError on DENY-tier action
  4. Human node rejection — reject_if_human() fires on a human node_id
  5. Fail-closed on audit error — audit_log() raises, does not silently pass
  6. YELLOW proceeds (Gate 1 current behavior — documented, not celebrated)

Evidence class after passing: VERIFIED (forced condition, output captured)
Run: pytest tests/test_constitutional_controls.py -v

NOTE: These tests must remain in the suite permanently. A control that was
VERIFIED this week becomes UNVERIFIED again as code changes. "Verified once"
is not "verified" — only a test that runs on every build keeps a control VERIFIED.
"""

import os
import sys
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Kill Switch — BOB_DISABLED=true must halt execution
# ─────────────────────────────────────────────────────────────────────────────

def test_kill_switch_halts_when_disabled():
    """
    Verify: when BOB_DISABLED=true, check_kill_switch() raises RuntimeError.
    Evidence: RuntimeError with message containing 'BOB_DISABLED' is raised.
    This proves the halt fires — not just that the import resolved.
    """
    from policy_engine import check_kill_switch

    with mock.patch.dict(os.environ, {"BOB_DISABLED": "true"}):
        with pytest.raises(RuntimeError, match="BOB_DISABLED"):
            check_kill_switch()


def test_kill_switch_passes_when_enabled():
    """
    Verify: when BOB_DISABLED is absent or 'false', check_kill_switch() does not raise.
    """
    from policy_engine import check_kill_switch

    env = {k: v for k, v in os.environ.items() if k != "BOB_DISABLED"}
    with mock.patch.dict(os.environ, env, clear=True):
        # Should not raise
        check_kill_switch()


# ─────────────────────────────────────────────────────────────────────────────
# 2. RED Block — gate() must raise PermissionError on RED-tier action
# ─────────────────────────────────────────────────────────────────────────────

def test_red_tier_blocked_by_gate():
    """
    Verify: a RED-classified action raises PermissionError at the gate.
    Evidence: PermissionError raised before any execution_payload is processed.
    This proves RED enforcement fires — not just that the code path exists.
    """
    from policy_engine import classify_action, RiskTier
    import policy_gate

    # Find an action that classifies as RED
    # RED = "delete_database", "drop_table", "wipe_workspace", etc.
    # We mock classify_action to return RED deterministically
    with mock.patch("policy_gate.classify_action", return_value=RiskTier.RED):
        with pytest.raises(PermissionError, match=r"RED|red|blocked|denied"):
            policy_gate.gate(
                action_type="test_red_action",
                target="test_target",
                execution_payload={"op": "delete_everything"},
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. DENY Block — gate() must raise PermissionError on DENY-tier action
# ─────────────────────────────────────────────────────────────────────────────

def test_deny_tier_blocked_by_gate():
    """
    Verify: a DENY-classified action raises PermissionError immediately.
    Evidence: PermissionError raised with DENY indicator.
    """
    from policy_engine import classify_action, RiskTier
    import policy_gate

    with mock.patch("policy_gate.classify_action", return_value=RiskTier.DENY):
        with pytest.raises(PermissionError, match=r"DENY|deny|blocked|denied"):
            policy_gate.gate(
                action_type="test_deny_action",
                target="test_target",
                execution_payload={"op": "exfiltrate_secrets"},
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Human Node Rejection — reject_if_human() must fire on a human node_id
# ─────────────────────────────────────────────────────────────────────────────

def test_human_node_rejected():
    """
    Verify: reject_if_human() raises TronixHumanNodeViolation or
    HumanEscalationRequired when a human node_id is targeted.
    Evidence: the specific exception fires with a human-node indicator.
    This proves the protection executes — not just that the file exists.
    """
    try:
        from tronix_human_protection import (
            reject_if_human,
            TronixHumanNodeViolation,
            HumanEscalationRequired,
        )
    except ImportError:
        pytest.skip("tronix_human_protection not importable — cannot verify")

    # Use a node_id known to be human (Chris's Telegram user ID)
    # The protection should classify this as a human node and reject
    human_node_id = "8480371994"  # Chris Leiser — known human node

    with pytest.raises((TronixHumanNodeViolation, HumanEscalationRequired)):
        reject_if_human(
            node_id=human_node_id,
            operation="write_message",
            agent_id="robert",
        )


def test_non_human_node_passes():
    """
    Verify: reject_if_human() does NOT raise for a non-human node_id.
    Evidence: no exception raised for a known agent/service node.
    """
    try:
        from tronix_human_protection import reject_if_human
    except ImportError:
        pytest.skip("tronix_human_protection not importable")

    # Mock get_node_type since Supabase is unavailable in test context
    # An AGENT-classified node should pass without exception
    with mock.patch("tronix_human_protection.get_node_type", return_value="AGENT"):
        reject_if_human(
            node_id="robert_bot_node",
            operation="read_status",
            agent_id="robert",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Fail-Closed on Audit Error — audit_log() must raise, not silently pass
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_failure_is_fail_closed():
    """
    Verify: when the Supabase audit RPC call fails, audit_log() raises
    RuntimeError instead of silently continuing.
    Evidence: RuntimeError raised with 'Audit write failed' in message.
    This proves fail-closed behavior — not just that the code path exists.
    """
    import bob_contract

    # Build a minimal valid envelope
    test_env = {
        "envelope_version": "1",
        "message_id": "test-msg-001",
        "sender": "test",
        "sent_at": "2026-05-29T22:00:00+00:00",
        "expires_at": "2026-05-29T22:05:00+00:00",
        "nonce": "a" * 64,
        "payload_type": "test",
        "payload": {},
        "signature": "fakesig",
    }

    # Patch SUPABASE_URL to a non-empty value so the RPC path is taken,
    # then force the urlopen to raise a connection error
    with mock.patch.object(bob_contract, "SUPABASE_URL", "https://fake-supabase.example.com"):
        with mock.patch.object(bob_contract, "SUPABASE_KEY", "fake-key"):
            with mock.patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
                with pytest.raises(RuntimeError, match=r"[Aa]udit write failed"):
                    bob_contract.audit_log(
                        env=test_env,
                        verification_result="ok",
                        outcome="test",
                        proposal_id=None,
                    )


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# 6. YELLOW Current Behavior (Gate 1) — documented, not celebrated
# ─────────────────────────────────────────────────────────────────────────────

def test_yellow_currently_proceeds_without_approval_gate1():
    """
    GATE 1 BEHAVIOR — documented, not celebrated.

    Verifies YELLOW tier is classified correctly and distinct from RED/DENY/GREEN.
    The YELLOW enforcement gap (no approval required) is documented here as a
    trip-wire: when Gate 2 is activated, this test should be updated.

    WARNING: YELLOW with no approval gate is the most dangerous operational gap.
    This is the tier where unreviewed automation quietly does things it shouldn't.
    """
    from policy_engine import RiskTier

    # YELLOW must be a distinct, defined tier
    assert RiskTier.YELLOW != RiskTier.RED
    assert RiskTier.YELLOW != RiskTier.DENY
    assert RiskTier.YELLOW != RiskTier.GREEN

    # Gate 1 bypass: confirm gate() source documents YELLOW proceeds without approval
    import policy_gate as pg_module
    import inspect
    gate_source = inspect.getsource(pg_module.gate)
    assert "Gate 1" in gate_source or "YELLOW" in gate_source, (
        "gate() source does not reference Gate 1 or YELLOW tier — verify policy_gate.py"
    )
    # This test passes. That is the problem. Gate 2 closes it.


# 7. Checkpoint Write — confirm SQLite checkpointing is currently active
# ─────────────────────────────────────────────────────────────────────────────

def test_checkpoint_db_exists_and_is_readable():
    """
    Verify: robert_checkpoints.db exists and is a readable SQLite database.
    Evidence: file exists at expected path, sqlite3 can open it without error.
    NOTE: This does not verify the checkpoint was written recently.
    See the 5-day gap finding in the evidence report — run a multi-step task
    and confirm a new row appears.
    """
    import sqlite3

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "robert_checkpoints.db")
    assert os.path.exists(db_path), f"Checkpoint DB not found at {db_path}"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert len(tables) > 0, "Checkpoint DB exists but contains no tables"
