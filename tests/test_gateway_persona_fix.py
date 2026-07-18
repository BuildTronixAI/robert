"""Acceptance coverage for ROBERT GATEWAY FIX work order (Fixes 1–5)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:ABC")
os.environ.setdefault("TELEGRAM_CHAT_ID", "1")

from gateway_prompt import (
    ROBERT_PERSONA,
    USER_SAFE_VALIDATION_FAILURE,
    assert_payload_roles,
    build_chat_user_message,
    build_context_block,
    build_system_prompt,
    build_user_message,
    classify_inbound,
    contains_forbidden_denial,
    current_datetime_eastern,
    format_conversation_history,
    looks_like_identity_break,
)


def test_fix1_persona_has_no_origin_denial():
    assert "NOT Claude" not in ROBERT_PERSONA
    assert "NOT an Anthropic" not in ROBERT_PERSONA
    assert "You are Robert, the COO Agent" in ROBERT_PERSONA
    assert "I don't discuss internal implementation details" in ROBERT_PERSONA
    assert "commercial AI infrastructure" in ROBERT_PERSONA
    assert not contains_forbidden_denial(ROBERT_PERSONA)
    assert not contains_forbidden_denial(build_system_prompt("TASK"))
    assert not contains_forbidden_denial(build_system_prompt("CHAT"))


def test_fix1_identity_md_has_no_origin_denial():
    text = (ROOT / "knowledge" / "robert_identity.md").read_text()
    assert "You are not Claude" not in text
    assert "NOT Claude" not in text
    assert "commercial AI infrastructure" in text


def test_fix2_system_holds_rules_user_holds_task_only():
    system = build_system_prompt("TASK")
    assert "Ambiguity Handling Rule" in system
    assert "OUTPUT STRUCTURE" in system
    assert "EVIDENCE RULES" in system
    assert "current_datetime" in system or "Treat current_datetime" in system

    ctx = build_context_block("session facts")
    user = build_user_message(
        original_task="Deploy the listener",
        plan="1. Restart service",
        context_block=ctx,
        token_budget="4000",
    )
    assert "Original task: Deploy the listener" in user
    assert "Plan:" in user
    assert "token_budget: 4000" in user
    assert "current_datetime:" in user
    assert "You are Robert, the COO Agent" not in user
    assert "Ambiguity Handling" not in user
    assert "EVIDENCE RULES" not in user
    assert_payload_roles(system, user)


def test_fix3_datetime_is_america_new_york():
    fixed = datetime(2026, 7, 17, 20, 30, 0, tzinfo=ZoneInfo("America/New_York"))
    stamp = current_datetime_eastern(fixed)
    assert stamp.startswith("2026-07-17T20:30:00")
    assert "-04:00" in stamp or "-05:00" in stamp  # EDT or EST
    block = build_context_block(now=fixed)
    assert f"current_datetime: {stamp}" in block


def test_fix4_chat_vs_task_discriminator():
    assert classify_inbound("Robert, status report") == "CHAT"
    assert classify_inbound("What is today's date") == "CHAT"
    assert classify_inbound("Check again") == "CHAT"
    assert classify_inbound("Are you Claude?") == "CHAT"
    assert classify_inbound("Tell me a one-sentence joke") == "CHAT"
    assert classify_inbound("who are you") == "CHAT"
    assert classify_inbound("Write a Python script to parse journalctl") == "TASK"
    assert classify_inbound("Deploy robert.service and verify health") == "TASK"
    assert classify_inbound('{"mesh": true, "task": "x"}') == "TASK"


def test_fix4_user_safe_failure_copy():
    assert "Missing required" not in USER_SAFE_VALIDATION_FAILURE
    assert "logged for review" in USER_SAFE_VALIDATION_FAILURE


def test_fix5_history_excludes_identity_break():
    assert looks_like_identity_break("I am Claude, an Anthropic product.")
    assert looks_like_identity_break("You are NOT Claude. You are Robert.")
    assert not looks_like_identity_break("Today is July 17, 2026.")

    turns = [
        {"role": "user", "content": "What is today's date?"},
        {"role": "assistant", "content": "I am Claude and cannot help with that framing."},
        {"role": "user", "content": "Check again"},
        {"role": "assistant", "content": "July 17, 2026."},
    ]
    formatted = format_conversation_history(turns, max_turns=10)
    assert "Check again" in formatted
    assert "July 17, 2026" in formatted
    assert "I am Claude" not in formatted


def test_executor_prompt_alias_has_no_denial():
    # Avoid importing nodes package (heavy langchain deps); assert source + system builder.
    src = (ROOT / "nodes" / "executor.py").read_text()
    assert "You are NOT Claude" not in src
    assert "build_system_prompt" in src
    assert "assert_payload_roles" in src
    assert not contains_forbidden_denial(build_system_prompt("TASK"))


def test_chat_user_message_shape():
    ctx = build_context_block("facts", conversation_history="User: hi\nRobert: hello")
    user = build_chat_user_message(message="What is today's date?", context_block=ctx)
    assert user.startswith("Message: What is today's date?")
    assert "Conversation history:" in user
    assert "You are Robert, the COO Agent" not in user


def test_memory_conversation_roundtrip(tmp_path, monkeypatch):
    import memory_store as ms
    import utils as utils_mod

    mem_path = tmp_path / "robert_memory.json"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(ms, "ROBERT_MEMORY_PATH", str(mem_path))
    monkeypatch.setattr(ms, "_LOCK_PATH", str(mem_path) + ".lock")
    monkeypatch.setattr(ms, "BACKUP_DIR_ROBERT", str(backup_dir))
    monkeypatch.setattr(utils_mod, "BACKUP_DIR_ROBERT", str(backup_dir))

    ms.append_conversation_turn("42", "user", "What is today's date?")
    ms.append_conversation_turn("42", "assistant", "I am Claude.")  # filtered out
    ms.append_conversation_turn("42", "assistant", "July 17, 2026.")
    hist = ms.get_conversation_history("42", max_turns=8)
    assert len(hist) == 2
    assert hist[0]["content"].startswith("What is")
    assert hist[1]["content"].startswith("July")

    ms.clear_conversation_history("42")
    assert ms.get_conversation_history("42") == []
