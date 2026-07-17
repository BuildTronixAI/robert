"""Tests for Robert completion pass: gate lifecycle, durable store, actor context."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _k, _v in {
    "OPENROUTER_API_KEY": "test-key",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-service-key",
    "TELEGRAM_BOT_TOKEN": "123:ABC",
    "TELEGRAM_CHAT_ID": "1",
    "WORKSPACE_PATH": "/tmp/robert-complete-ws",
    "ROBERT_MEMORY_PATH": "/tmp/robert-complete-ws/robert_memory.json",
    "ROBERT_STORE_DB": "/tmp/robert-complete-ws/robert_runtime.db",
    "ROBERT_ALLOW_MEMORY_CHECKPOINTER": "true",
    "BOB_SHARED_SECRET": "test-shared-secret-for-signing",
    "ROBERT_GATE_LEVEL": "1",
}.items():
    os.environ[_k] = _v

os.makedirs("/tmp/robert-complete-ws", exist_ok=True)


def test_durable_nonce_store_blocks_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    import importlib
    import robert_store
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False

    store = robert_store.DurableNonceStore(window_seconds=600)
    assert store.check_and_record("nonce-a", "task-1") is True
    with pytest.raises(robert_store.DurableReplayError):
        store.check_and_record("nonce-a", "task-2")
    with pytest.raises(robert_store.DurableReplayError):
        store.check_and_record("nonce-b", "task-1")


def test_gate_stable_prior_decision_id(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("BOB_SHARED_SECRET", "test-shared-secret-for-signing")
    monkeypatch.setenv("ROBERT_GATE_LEVEL", "1")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    # Empty URL so _persist_decision skips remote write
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")

    import importlib
    import robert_store
    import policy_gate
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False
    importlib.reload(policy_gate)

    # Human-node cache: treat unknown as escalate — use empty target node id via resource_target
    payload = {"originating_task_id": "t1", "code_preview": "print(1)"}
    # First call — YELLOW run_script should proceed under gate 1
    with mock.patch("policy_gate.reject_if_human", return_value=None):
        policy_gate.gate(
            "run_script",
            target="exec_tool",
            reversible=True,
            execution_payload=payload,
        )

    # Capture pending decision id
    with robert_store._conn() as conn:
        row = conn.execute(
            "SELECT decision_id FROM pending_decisions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row, "expected pending decision"
    decision_id = row[0]

    # Re-entry with prior_decision_id must reuse same id (not mint a new one)
    decision = policy_gate._resolve_decision(
        action_type="run_script",
        target="exec_tool",
        data_sensitivity="internal",
        reversible=True,
        confidence=1.0,
        content_flags=[],
        execution_payload={**payload, "prior_decision_id": decision_id},
    )
    assert decision.decision_id == decision_id


def test_gate_red_does_not_claim_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("BOB_SHARED_SECRET", "test-shared-secret-for-signing")
    monkeypatch.setenv("ROBERT_GATE_LEVEL", "1")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")

    import importlib
    import robert_store
    import policy_gate
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False
    importlib.reload(policy_gate)

    payload = {"originating_task_id": "fin1", "amount": 9999}
    with mock.patch("policy_gate.reject_if_human", return_value=None):
        with pytest.raises(PermissionError) as ei:
            policy_gate.gate(
                "financial_transaction",
                target="payments",
                reversible=False,
                execution_payload=payload,
            )
    assert "prior_decision_id=" in str(ei.value)

    # No idempotency claim should exist
    with robert_store._conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM idempotency_keys").fetchone()[0]
    assert n == 0


def test_run_task_accepts_actor_context():
    # Import main without compiling LangGraph: stub heavy deps
    import types
    import importlib.util

    fake_graph = types.ModuleType("graph")
    fake_graph.graph = mock.MagicMock()
    sys.modules["graph"] = fake_graph
    sys.modules.setdefault("tools.telegram", types.ModuleType("tools.telegram"))
    sys.modules["tools.telegram"].send_telegram = lambda *a, **k: True

    spec = importlib.util.spec_from_file_location("main_under_test", ROOT / "main.py")
    main_mod = importlib.util.module_from_spec(spec)
    # Provide state TypedDict
    from state import RobertState
    main_mod.RobertState = RobertState
    with mock.patch.dict(sys.modules, {"graph": fake_graph}):
        spec.loader.exec_module(main_mod)

    out = main_mod.run_task("", actor_user_id="u1", actor_role="OWNER", actor_jwt="jwt")
    assert out["reply_status"] == "FAILURE"


def test_safe_fetch_rejects_non_allowlisted():
    from tools.safe_fetch import safe_fetch

    with pytest.raises(ValueError):
        safe_fetch("https://evil.example/steal")
