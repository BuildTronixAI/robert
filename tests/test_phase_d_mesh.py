"""Phase D — Mesh Phase C: shared nonces, outbound deliver, EXTERNALLY_COMMITTED."""

from __future__ import annotations

import asyncio
import base64
import hashlib
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
    "WORKSPACE_PATH": "/tmp/robert-phase-d-ws",
    "ROBERT_STORE_DB": "/tmp/robert-phase-d-ws/robert_runtime.db",
    "BOB_SHARED_SECRET": "test-shared-secret-for-signing",
    "BOB_INBOX_URL": "https://example.supabase.co/functions/v1/bob-inbox",
    "ROBERT_MESH_PHASE": "B",
}.items():
    os.environ[_k] = _v

os.makedirs("/tmp/robert-phase-d-ws", exist_ok=True)


def _make_task_dict(task_type="check_status", payload=None, nonce="n-1"):
    payload = payload or {"ping": True}
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "task_id": "11111111-1111-1111-1111-111111111111",
        "sender_id": "bob",
        "task_type": task_type,
        "payload": payload,
        "payload_hash": payload_hash,
        "nonce": nonce,
        "issued_at": time.time(),
        "ttl_seconds": 60,
        "signature": base64.b64encode(b"x" * 64).decode(),
    }


def test_mesh_phase_flag():
    from mesh_outbound import mesh_phase, external_commit_enabled

    os.environ["ROBERT_MESH_PHASE"] = "B"
    assert mesh_phase() == "B"
    assert external_commit_enabled() is False
    os.environ["ROBERT_MESH_PHASE"] = "C"
    assert mesh_phase() == "C"
    assert external_commit_enabled() is True
    os.environ["ROBERT_MESH_PHASE"] = "B"


def test_deliver_result_requires_inbox(monkeypatch):
    from mesh_outbound import deliver_result_to_bob

    monkeypatch.delenv("BOB_INBOX_URL", raising=False)
    out = deliver_result_to_bob(
        task_id="t1", task_type="check_status", staged_hash="abc", result={"ok": True}
    )
    assert out["ok"] is False
    assert "BOB_INBOX_URL" in out["error"]


def test_deliver_result_success(monkeypatch):
    from mesh_outbound import deliver_result_to_bob

    monkeypatch.setenv("BOB_INBOX_URL", "https://example.supabase.co/inbox")
    monkeypatch.setenv("BOB_SHARED_SECRET", "secret")
    monkeypatch.setattr(
        "bob_contract.build_envelope",
        lambda *a, **k: {"envelope": True},
    )
    monkeypatch.setattr(
        "bob_contract._send_to_bob",
        lambda env: {"ok": True, "status": 200},
    )
    # deliver imports inside function — patch modules after import path
    import bob_contract
    monkeypatch.setattr(bob_contract, "build_envelope", lambda *a, **k: {"envelope": True})
    monkeypatch.setattr(bob_contract, "_send_to_bob", lambda env: {"ok": True})

    out = deliver_result_to_bob(
        task_id="t1", task_type="check_status", staged_hash="abc", result={"ok": True}
    )
    assert out["ok"] is True


def test_shared_nonce_supabase_duplicate(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "key")

    import importlib
    import robert_store
    import mesh_nonce_store
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False
    importlib.reload(mesh_nonce_store)

    store = mesh_nonce_store.SharedNonceStore(window_seconds=600)

    def fake_fetch(url, **kwargs):
        import urllib.error
        raise urllib.error.HTTPError(url, 409, "Conflict", hdrs=None, fp=None)

    monkeypatch.setattr("tools.safe_fetch.safe_fetch", fake_fetch)
    from mesh_receiver import MeshReplayError
    with pytest.raises(MeshReplayError):
        store.check_and_record("nonce-dup", "task-1", "bob")


def test_receive_phase_b_stays_staged(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("ROBERT_MESH_PHASE", "B")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    import importlib
    import robert_store
    import mesh_receiver
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False
    importlib.reload(mesh_receiver)

    recv = mesh_receiver.MeshReceiver(
        robert_agent_id="robert",
        bob_public_key_hex="00" * 32,
    )

    async def handler(task_id, payload):
        return {"task_id": task_id, "ok": True, "commit_external": True}

    recv.register_handler("check_status", handler)
    monkeypatch.setattr(recv, "_verify_signature", lambda task: None)

    raw = json.dumps(_make_task_dict(nonce="phase-b-1")).encode()
    out = asyncio.run(recv.receive(raw))
    assert out["state"] == "staged"
    assert out.get("commit_error") == "phase_b_external_commit_disabled"


def test_receive_phase_c_externally_commits(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("ROBERT_MESH_PHASE", "C")
    monkeypatch.setenv("BOB_INBOX_URL", "https://example.supabase.co/inbox")
    monkeypatch.setenv("BOB_SHARED_SECRET", "secret")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    import importlib
    import robert_store
    import mesh_receiver
    import mesh_outbound
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False
    importlib.reload(mesh_outbound)
    importlib.reload(mesh_receiver)

    monkeypatch.setattr(
        mesh_outbound,
        "deliver_result_to_bob",
        lambda **kwargs: {"ok": True, "delivery": {"acked": True}},
    )

    recv = mesh_receiver.MeshReceiver(
        robert_agent_id="robert",
        bob_public_key_hex="00" * 32,
    )

    async def handler(task_id, payload):
        return {"task_id": task_id, "ok": True}

    recv.register_handler("check_status", handler)
    monkeypatch.setattr(recv, "_verify_signature", lambda task: None)

    raw = json.dumps(_make_task_dict(nonce="phase-c-1")).encode()
    out = asyncio.run(recv.receive(raw))
    assert out["state"] == "externally_committed"


def test_receive_phase_c_commit_failure_stays_staged(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("ROBERT_STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("ROBERT_MESH_PHASE", "C")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    import importlib
    import robert_store
    import mesh_receiver
    import mesh_outbound
    importlib.reload(robert_store)
    robert_store._INITIALIZED = False
    importlib.reload(mesh_outbound)
    importlib.reload(mesh_receiver)

    monkeypatch.setattr(
        mesh_outbound,
        "deliver_result_to_bob",
        lambda **kwargs: {"ok": False, "error": "inbox_down"},
    )

    recv = mesh_receiver.MeshReceiver(
        robert_agent_id="robert",
        bob_public_key_hex="00" * 32,
    )

    async def handler(task_id, payload):
        return {"task_id": task_id, "ok": True}

    recv.register_handler("check_status", handler)
    monkeypatch.setattr(recv, "_verify_signature", lambda task: None)

    raw = json.dumps(_make_task_dict(nonce="phase-c-fail")).encode()
    out = asyncio.run(recv.receive(raw))
    assert out["state"] == "staged"
    assert out.get("commit_error") == "inbox_down"
