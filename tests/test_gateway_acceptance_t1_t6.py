"""
Local acceptance harness for ROBERT-GATEWAY-FIX T1–T6.

These validate classifier + outbound payload assembly (system vs user).
Live Telegram replies still require deploy + a fresh thread.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gateway_prompt import (
    assert_payload_roles,
    build_chat_user_message,
    build_context_block,
    build_system_prompt,
    build_user_message,
    classify_inbound,
    contains_forbidden_denial,
    format_conversation_history,
)


def _chat_payload(message: str, history: list | None = None, now=None) -> dict:
    system = build_system_prompt("CHAT", include_identity_doc=True)
    hist = format_conversation_history(history or [])
    ctx = build_context_block("Robert Session #test", conversation_history=hist, now=now)
    user = build_chat_user_message(message=message, context_block=ctx)
    assert_payload_roles(system, user)
    return {
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }


def test_t1_status_report_payload_has_system_no_denial(tmp_path):
    """T1 evidence: outbound payload with populated system field."""
    now = datetime(2026, 7, 17, 20, 41, 0, tzinfo=ZoneInfo("America/New_York"))
    assert classify_inbound("Robert, status report") == "CHAT"
    payload = _chat_payload("Robert, status report", now=now)

    assert payload["system"]
    assert "You are Robert, the COO Agent" in payload["system"]
    assert not contains_forbidden_denial(payload["system"])
    user = payload["messages"][0]["content"]
    assert "You are Robert, the COO Agent" not in user
    assert "current_datetime: 2026-07-17T20:41:00" in user

    evidence = tmp_path / "t1_outbound_payload.json"
    evidence.write_text(json.dumps(payload, indent=2))
    # Also write under /tmp for operator pickup when pytest tmp is cleaned
    out = Path("/tmp/cursor/artifacts")
    out.mkdir(parents=True, exist_ok=True)
    (out / "t1_outbound_payload.json").write_text(json.dumps(payload, indent=2))
    assert evidence.exists()


def test_t2_t3_date_chat_and_history():
    now = datetime(2026, 7, 17, 20, 41, 0, tzinfo=ZoneInfo("America/New_York"))
    assert classify_inbound("What is today's date") == "CHAT"
    assert classify_inbound("Check again") == "CHAT"

    t2 = _chat_payload("What is today's date", now=now)
    assert "2026-07-17" in t2["messages"][0]["content"]

    history = [
        {"role": "user", "content": "What is today's date"},
        {"role": "assistant", "content": "Today is Friday, July 17, 2026."},
    ]
    t3 = _chat_payload("Check again", history=history, now=now)
    user = t3["messages"][0]["content"]
    assert "Conversation history:" in user
    assert "July 17, 2026" in user
    assert "I am Claude" not in user


def test_t4_identity_question_is_chat():
    assert classify_inbound("Are you Claude?") == "CHAT"
    payload = _chat_payload("Are you Claude?")
    assert "internal implementation details" in payload["system"]
    assert "commercial AI infrastructure" in payload["system"]
    assert not contains_forbidden_denial(payload["system"])


def test_t5_joke_is_chat_not_task_wrapper():
    assert classify_inbound("Tell me a one-sentence joke") == "CHAT"
    payload = _chat_payload("Tell me a one-sentence joke")
    user = payload["messages"][0]["content"]
    # CHAT path must not demand structured task sections in the user turn
    assert "## Task Output" not in user
    assert "Completion Report" not in user
    assert "CHAT" in payload["system"] or "conversational" in payload["system"].lower()


def test_t6_real_task_keeps_structured_system():
    assert classify_inbound("Write a Python script to parse journalctl and save the summary") == "TASK"
    system = build_system_prompt("TASK")
    ctx = build_context_block()
    user = build_user_message(
        original_task="Write a Python script to parse journalctl and save the summary",
        plan="1. Write script\n2. Run dry check",
        context_block=ctx,
    )
    assert_payload_roles(system, user)
    assert "## Task Output" in system
    assert "## Completion Report" in system
    assert "EVIDENCE RULES" in system
    assert "You are Robert, the COO Agent" not in user
    assert "current_datetime:" in user
