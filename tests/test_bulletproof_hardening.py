"""Regression tests for Robert bulletproof hardening pass."""

from __future__ import annotations

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

# Minimal env so config-importing modules can load in CI/sandbox
for _k, _v in {
    "OPENROUTER_API_KEY": "test-key",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-service-key",
    "TELEGRAM_BOT_TOKEN": "123:ABC",
    "TELEGRAM_CHAT_ID": "1",
    "WORKSPACE_PATH": "/tmp/robert-test-workspace",
    "ROBERT_MEMORY_PATH": "/tmp/robert-test-workspace/robert_memory.json",
    "ROBERT_ALLOW_MEMORY_CHECKPOINTER": "true",
}.items():
    os.environ.setdefault(_k, _v)

os.makedirs(os.environ["WORKSPACE_PATH"], exist_ok=True)


def test_run_little_voice_wrapper_exists_and_returns_flags():
    from orchestrator.little_voice import run_little_voice

    with mock.patch("orchestrator.little_voice.LittleVoice.check", return_value=[]):
        out = run_little_voice("send email about budget", {"role": "OWNER"}, "ctx")
    assert isinstance(out, dict)
    assert "flags" in out
    assert out["flags"] == []


def test_orchestrator_stack_imports_little_voice():
    from orchestrator import stack as orch_stack

    with mock.patch.object(orch_stack, "run_orchestrator_stack", wraps=orch_stack.run_orchestrator_stack):
        with mock.patch("orchestrator.witness.run_witness", create=True, return_value={"flags": []}), \
             mock.patch("orchestrator.little_voice.run_little_voice", create=True, return_value={"flags": []}):
            # Patch at import sites used inside the function
            import orchestrator.witness as witness_mod
            import orchestrator.little_voice as lv_mod
            with mock.patch.object(witness_mod, "run_witness", return_value={"flags": []}), \
                 mock.patch.object(lv_mod, "run_little_voice", return_value={"flags": []}):
                result = orch_stack.run_orchestrator_stack("hello", {"role": "OWNER"}, "memory")
    assert result["should_block"] is False
    assert result.get("error") in (None, "timeout")


def test_mesh_signing_covers_task_type_and_ttl():
    from mesh_receiver import MeshTask, MESH_SIGNING_VERSION

    payload = {"x": 1}
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    task = MeshTask(
        task_id="t1",
        sender_id="bob",
        task_type="analyze_customer",
        payload=payload,
        payload_hash=payload_hash,
        nonce="n1",
        issued_at=time.time(),
        ttl_seconds=60,
        signature="AA==",
    )
    msg = json.loads(task.signing_message())
    assert msg["v"] == MESH_SIGNING_VERSION
    assert msg["task_type"] == "analyze_customer"
    assert msg["ttl_seconds"] == 60


def test_mesh_rejects_oversized_ttl():
    from mesh_receiver import MeshTask, MeshSchemaError, MAX_TTL_SECONDS

    payload = {"x": 1}
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(MeshSchemaError):
        MeshTask.from_dict({
            "task_id": "t1",
            "sender_id": "bob",
            "task_type": "analyze_customer",
            "payload": payload,
            "payload_hash": payload_hash,
            "nonce": "n1",
            "issued_at": time.time(),
            "ttl_seconds": MAX_TTL_SECONDS + 1,
            "signature": "AA==",
        })


def test_mesh_signature_fail_closed_without_cryptography():
    from mesh_receiver import MeshReceiver, MeshAuthError, MeshTask

    payload = {"ok": True}
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # 32-byte fake public key
    recv = MeshReceiver(
        robert_agent_id="robert",
        bob_public_key_hex="00" * 32,
    )
    task = MeshTask(
        task_id="t1",
        sender_id="bob",
        task_type="check_status",
        payload=payload,
        payload_hash=payload_hash,
        nonce="nonce-1",
        issued_at=time.time(),
        ttl_seconds=60,
        signature=base64.b64encode(b"x" * 64).decode(),
    )
    with mock.patch.dict(sys.modules, {"cryptography": None, "cryptography.hazmat": None,
                                       "cryptography.hazmat.primitives": None,
                                       "cryptography.hazmat.primitives.asymmetric": None,
                                       "cryptography.hazmat.primitives.asymmetric.ed25519": None,
                                       "cryptography.exceptions": None}):
        # Force ImportError path inside _verify_signature
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("cryptography"):
                raise ImportError("forced")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(MeshAuthError):
                recv._verify_signature(task)


def test_memory_path_traversal_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    import importlib
    import importlib.util

    # Load tools.memory without importing tools package __init__ (telegram dep)
    spec = importlib.util.spec_from_file_location(
        "robert_tools_memory", ROOT / "tools" / "memory.py"
    )
    memory = importlib.util.module_from_spec(spec)
    # Ensure config.WORKSPACE_PATH matches tmp
    import config
    monkeypatch.setattr(config, "WORKSPACE_PATH", str(tmp_path))
    spec.loader.exec_module(memory)
    memory.MEMORY_DIR = os.path.join(str(tmp_path), "memory")

    with pytest.raises(Exception):
        memory.write_memory("/tmp/evil.txt", "nope")
    with pytest.raises(Exception):
        memory.write_memory("../../etc/passwd", "nope")

    assert memory.write_memory("safe.md", "ok") is True
    assert memory.read_memory("safe.md") == "ok"


def test_exec_tool_argv_no_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    import importlib.util
    import config
    monkeypatch.setattr(config, "WORKSPACE_PATH", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "robert_tools_exec", ROOT / "tools" / "exec_tool.py"
    )
    exec_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exec_tool)

    result = exec_tool.run_argv(["python3", "-c", "print('hello-robert')"], timeout=10, cwd=str(tmp_path))
    assert result["returncode"] == 0
    assert "hello-robert" in result["stdout"]


def test_policy_token_refuses_empty_secret(monkeypatch):
    from policy_engine import PolicyDecision
    from datetime import datetime, timezone, timedelta

    monkeypatch.delenv("BOB_SHARED_SECRET", raising=False)
    decision = PolicyDecision(
        decision_id="d1",
        action_type="test",
        target="t",
        data_sensitivity="internal",
        reversible=True,
        request_source="robert",
        tier="GREEN",
        confidence=1.0,
        approved=True,
        deny_reason=None,
        approvals_required=0,
        approvals_received=0,
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    )
    with pytest.raises(RuntimeError):
        decision.to_token()


def test_graph_retry_routing_prefers_revision():
    """Ensure needs_revision retries even if requires_escalation is also set."""
    src = (ROOT / "graph.py").read_text()
    # Extract and exec only route_after_review
    start = src.index("def route_after_review")
    end = src.index("\ndef build_graph")
    fn_src = src[start:end]
    ns = {"END": "__END__", "MAX_ITERATIONS": 3, "print": lambda *a, **k: None}
    exec(fn_src, ns)
    route_after_review = ns["route_after_review"]

    state = {
        "iteration_count": 1,
        "needs_revision": True,
        "requires_escalation": True,  # legacy contradictory flags
        "origin_node": "executor",
        "needs_redesign": False,
    }
    assert route_after_review(state) == "executor"
    assert route_after_review({**state, "needs_revision": False}) == "__END__"

def test_limits_do_not_overwrite_existing(tmp_path, monkeypatch):
    limits_file = tmp_path / "limits.json"
    limits_file.write_text(json.dumps({"telegram_messages_per_minute": 99}))
    monkeypatch.setattr("limits.LIMITS_FILE", str(limits_file))
    import limits
    limits.write_default_limits()
    data = json.loads(limits_file.read_text())
    assert data["telegram_messages_per_minute"] == 99


def test_permissions_owner_free_text():
    from auth.permissions import check_permission

    ok, reason = check_permission("OWNER", "build a report")
    assert ok is True
    ok2, reason2 = check_permission("CLIENT", "build a report")
    assert ok2 is False
    assert "OWNER" in reason2


def test_memory_store_quarantines_corrupt(tmp_path, monkeypatch):
    mem_path = tmp_path / "robert_memory.json"
    mem_path.write_text("{not-json")
    monkeypatch.setenv("ROBERT_MEMORY_PATH", str(mem_path))
    import importlib
    import memory_store
    importlib.reload(memory_store)

    data = memory_store.load()
    assert data["session_count"] == 0
    # Corrupt file should have been quarantined
    assert not mem_path.exists() or mem_path.read_text().startswith("{")
    corrupt = list(tmp_path.glob("robert_memory.json.corrupt.*"))
    assert corrupt, "expected quarantined corrupt memory file"
