"""Telegram tool for Robert — gated outbound messages."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from tools.actor_context import require_gate
from tools.base import sanitize_error
from tools.safe_fetch import safe_fetch


def send_telegram(
    message: str,
    chat_id: Optional[str] = None,
    *,
    skip_gate: bool = False,
) -> bool:
    """
    Send a message via Telegram Bot API (sync, no event-loop hazards).
    Uses urllib/safe_fetch instead of python-telegram-bot to avoid nested-loop issues.
    """
    try:
        token = TELEGRAM_BOT_TOKEN
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured")

        target_chat = str(chat_id or TELEGRAM_CHAT_ID or "")
        if not target_chat:
            raise ValueError("No chat_id provided and TELEGRAM_CHAT_ID not configured")

        # Primary Buildtronix chats are internal; unknown chats are external.
        internal = target_chat in {str(TELEGRAM_CHAT_ID), "8480371994"}
        action = "send_internal_message" if internal else "send_external_message"
        if not skip_gate:
            require_gate(
                action,
                target=f"telegram:{target_chat}",
                reversible=False,
                execution_payload={
                    "chat_id": target_chat,
                    "message_preview": (message or "")[:300],
                    "internal": internal,
                },
            )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": target_chat,
            "text": (message or "")[:4000],
        }).encode("utf-8")
        status, body, _ = safe_fetch(
            url,
            method="POST",
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if status != 200:
            return False
        data = json.loads(body.decode("utf-8"))
        return bool(data.get("ok"))
    except Exception as e:
        print(f"Failed to send Telegram message: {sanitize_error(str(e))}")
        return False


async def send_telegram_async(message: str, chat_id: str = None) -> bool:
    """Async wrapper — runs sync send in a thread to avoid blocking."""
    return await asyncio.to_thread(send_telegram, message, chat_id)
