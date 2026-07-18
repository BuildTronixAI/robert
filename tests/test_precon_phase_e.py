"""Phase E — Precon hardening: auth, no mock seed, ReviewLayer gate advances."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:ABC")
os.environ.setdefault("TELEGRAM_CHAT_ID", "1")


def test_engine0_config_not_dangling_symlink():
    cfg = ROOT / "precon" / "engine0" / "config.py"
    assert cfg.exists()
    assert not cfg.is_symlink()
    text = cfg.read_text()
    assert "precon.a0.config" in text


def test_no_mock_seed_without_flag(monkeypatch):
    monkeypatch.delenv("PRECON_DEV_SEED", raising=False)
    from precon.api import store as store_mod

    store_mod.clear_stores()
    s = store_mod.get_or_create_store("proj-empty")
    assert s.screen1_items == []
    assert s.screen2_items == []


def test_mock_seed_with_flag(monkeypatch):
    monkeypatch.setenv("PRECON_DEV_SEED", "1")
    from precon.api import store as store_mod

    store_mod.clear_stores()
    s = store_mod.get_or_create_store("proj-demo")
    assert len(s.screen1_items) >= 1


def test_advance_screen1_uses_review_layer_gate(monkeypatch):
    monkeypatch.setenv("PRECON_DEV_SEED", "1")
    from precon.api import store as store_mod
    from precon.review_layer.models import ReviewDecision

    store_mod.clear_stores()
    s = store_mod.get_or_create_store("proj-gate")
    ok, reason = s.advance_screen1()
    assert ok is False
    assert reason

    for item in s.screen1_items:
        item.decision = ReviewDecision.APPROVED
    ok2, reason2 = s.advance_screen1()
    assert ok2 is True
    assert reason2 is None


def test_require_api_token_fail_closed(monkeypatch):
    monkeypatch.delenv("PRECON_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("PRECON_DEV_SEED", raising=False)
    monkeypatch.delenv("PRECON_API_TOKEN", raising=False)
    from fastapi import HTTPException
    from precon.api.auth import require_api_token

    with pytest.raises(HTTPException) as ei:
        require_api_token(authorization=None)
    assert ei.value.status_code == 503

    monkeypatch.setenv("PRECON_API_TOKEN", "secret-token")
    with pytest.raises(HTTPException) as ei2:
        require_api_token(authorization=None)
    assert ei2.value.status_code == 401

    with pytest.raises(HTTPException) as ei3:
        require_api_token(authorization="Bearer wrong")
    assert ei3.value.status_code == 403

    require_api_token(authorization="Bearer secret-token")


def test_auth_disabled_bypass(monkeypatch):
    monkeypatch.setenv("PRECON_AUTH_DISABLED", "1")
    from precon.api.auth import require_api_token

    require_api_token(authorization=None)


def _reload_app():
    """Reload precon.api.main after env changes so deps see current settings."""
    import precon.api.auth as auth_mod
    import precon.api.store as store_mod
    import precon.api.main as main_mod

    store_mod.clear_stores()
    importlib.reload(auth_mod)
    importlib.reload(store_mod)
    # Reload routers that closed over require_api_token
    for name in (
        "precon.api.routers.screen1",
        "precon.api.routers.screen2",
        "precon.api.routers.screen25",
        "precon.api.routers.screen3",
        "precon.api.routers.proposal",
        "precon.api.main",
    ):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    from fastapi.testclient import TestClient

    return TestClient(sys.modules["precon.api.main"].app)


def test_mutating_routes_require_auth(monkeypatch):
    monkeypatch.setenv("PRECON_API_TOKEN", "secret-token")
    monkeypatch.setenv("PRECON_DEV_SEED", "1")
    monkeypatch.delenv("PRECON_AUTH_DISABLED", raising=False)
    client = _reload_app()

    denied = client.post("/projects/proj_demo_001/screen1/advance")
    assert denied.status_code == 401

    allowed = client.post(
        "/projects/proj_demo_001/screen1/advance",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert "passed" in body

    # GET remains open (read)
    get_ok = client.get("/projects/proj_demo_001/screen1")
    assert get_ok.status_code == 200

    from precon.api import store as store_mod

    store_mod.clear_stores()
    monkeypatch.delenv("PRECON_API_TOKEN", raising=False)
    monkeypatch.delenv("PRECON_DEV_SEED", raising=False)


def test_mutating_routes_fail_closed_without_token(monkeypatch):
    monkeypatch.delenv("PRECON_API_TOKEN", raising=False)
    monkeypatch.delenv("PRECON_DEV_SEED", raising=False)
    monkeypatch.delenv("PRECON_AUTH_DISABLED", raising=False)
    client = _reload_app()
    resp = client.post("/projects/any/screen2/advance")
    assert resp.status_code == 503


def test_gate_audit_strict_raises(monkeypatch):
    monkeypatch.setenv("PRECON_GATE_AUDIT_STRICT", "1")
    from precon.execution_spine.gate_engine import GateEngine, ScopeItemStatus

    boom = MagicMock()
    boom.table.return_value.insert.return_value.execute.side_effect = RuntimeError("db down")

    engine = GateEngine(db=boom)
    with pytest.raises(RuntimeError, match="Failed to persist"):
        engine.evaluate_scope_transition(
            scope_item_id="scope1",
            project_id="p1",
            from_status=ScopeItemStatus.DRAFT,
            to_status=ScopeItemStatus.ACTIVE,
        )

    monkeypatch.delenv("PRECON_GATE_AUDIT_STRICT", raising=False)
