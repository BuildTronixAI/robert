"""Phase C — tool boundary: gates, safe_fetch, actor JWT/RLS client."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for _k, _v in {
    "OPENROUTER_API_KEY": "test-key",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-service-key",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "TELEGRAM_BOT_TOKEN": "123:ABC",
    "TELEGRAM_CHAT_ID": "1",
    "WORKSPACE_PATH": "/tmp/robert-phase-c-ws",
    "ROBERT_STORE_DB": "/tmp/robert-phase-c-ws/robert_runtime.db",
    "BOB_SHARED_SECRET": "test-shared-secret-for-signing",
    "ROBERT_GATE_LEVEL": "1",
}.items():
    os.environ[_k] = _v

os.makedirs("/tmp/robert-phase-c-ws", exist_ok=True)


def test_actor_context_roundtrip():
    from tools.actor_context import set_actor, reset_actor, get_actor_jwt, get_actor

    token = set_actor(user_id="u1", role="OWNER", jwt="jwt-abc", chat_id="9")
    try:
        assert get_actor_jwt() == "jwt-abc"
        assert get_actor()["role"] == "OWNER"
    finally:
        reset_actor(token)
    assert get_actor_jwt() == ""


def test_supabase_project_host_allowed():
    from tools.url_validator import is_allowed_hostname, validate_url

    assert is_allowed_hostname("example.supabase.co") is True
    # DNS may fail in sandbox for fake host — allow either pass or DNS error, not allowlist error
    try:
        validate_url("https://example.supabase.co/rest/v1/")
    except ValueError as e:
        assert "allowlist" not in str(e).lower()


def test_user_client_uses_anon_apikey_and_user_jwt():
    from auth.user_client import UserScopedClient

    client = UserScopedClient(jwt_token="user-jwt", anon_key="anon-key")
    headers = client._headers()
    assert headers["apikey"] == "anon-key"
    assert headers["Authorization"] == "Bearer user-jwt"


def test_user_client_rejects_bad_table_name():
    from auth.user_client import UserScopedClient

    client = UserScopedClient(jwt_token="user-jwt", anon_key="anon-key")
    with pytest.raises(ValueError):
        client.select("evil;drop")


def test_insert_row_calls_gate(monkeypatch):
    import tools.supabase_tool as st

    called = {}

    def fake_gate(action, target="", **kwargs):
        called["action"] = action
        called["target"] = target
        called["payload"] = kwargs.get("execution_payload")

    monkeypatch.setattr("tools.actor_context.require_gate", fake_gate)
    client = mock.MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [{"id": 1}]
    monkeypatch.setattr(st, "get_supabase_client", lambda: client)

    out = st.insert_row("projects", {"name": "x"}, actor_id="u1")
    assert out.get("id") == 1
    assert called.get("action") in ("create_record", "write_database")
    assert called.get("target") == "projects"


def test_send_telegram_uses_safe_fetch_and_gate(monkeypatch):
    import tools.telegram as tg

    monkeypatch.setattr(tg, "TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setattr(tg, "TELEGRAM_CHAT_ID", "1")

    gated = {}

    def fake_gate(*a, **k):
        gated["yes"] = True

    monkeypatch.setattr("tools.telegram.require_gate", fake_gate)

    def fake_fetch(url, **kwargs):
        assert "api.telegram.org" in url
        assert kwargs.get("method") == "POST"
        return 200, json.dumps({"ok": True}).encode(), {}

    monkeypatch.setattr("tools.telegram.safe_fetch", fake_fetch)
    assert tg.send_telegram("hello") is True
    assert gated.get("yes") is True


def test_query_table_prefers_actor_jwt(monkeypatch):
    import tools.supabase_tool as st
    from tools.actor_context import set_actor, reset_actor

    token = set_actor(user_id="u1", role="OWNER", jwt="jwt-xyz")
    try:
        fake_client = mock.Mock()
        fake_client.select.return_value = [{"id": 1}]
        monkeypatch.setattr(
            "auth.user_client.get_user_client",
            lambda jwt: fake_client,
        )
        rows = st.query_table("projects")
        assert rows == [{"id": 1}]
        fake_client.select.assert_called_once()
    finally:
        reset_actor(token)
