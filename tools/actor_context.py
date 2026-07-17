"""Request-scoped actor context for RLS-aware tool calls."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_actor_ctx: ContextVar[dict] = ContextVar("robert_actor", default={})


def set_actor(
    *,
    user_id: str = "",
    role: str = "",
    jwt: str = "",
    chat_id: str = "",
) -> Token:
    """Bind actor identity for the current task. Returns reset token."""
    return _actor_ctx.set({
        "user_id": user_id or "",
        "role": role or "",
        "jwt": jwt or "",
        "chat_id": chat_id or "",
    })


def reset_actor(token: Token) -> None:
    _actor_ctx.reset(token)


def get_actor() -> dict:
    return dict(_actor_ctx.get() or {})


def get_actor_jwt() -> str:
    return str(get_actor().get("jwt") or "")


def get_actor_user_id() -> str:
    return str(get_actor().get("user_id") or "")


def require_gate(action_type: str, target: str = "", **kwargs: Any) -> None:
    """Call policy gate with execution_payload defaults from actor context."""
    from policy_gate import gate

    payload = dict(kwargs.pop("execution_payload", None) or {})
    actor = get_actor()
    payload.setdefault("originating_task_id", actor.get("user_id") or "tool")
    payload.setdefault("actor_user_id", actor.get("user_id") or "")
    payload.setdefault("actor_role", actor.get("role") or "")
    gate(
        action_type,
        target=target,
        execution_payload=payload,
        **kwargs,
    )
