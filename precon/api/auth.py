"""
Precon API auth — Bearer token for mutating routes.

Env:
  PRECON_API_TOKEN       — required in production for POST/PATCH/PUT/DELETE
  PRECON_AUTH_DISABLED=1 — explicit local bypass (tests / emergency)
  PRECON_DEV_SEED=1      — allows missing token only in local mock-seed mode
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency — fail-closed for mutating Precon routes."""
    if _truthy("PRECON_AUTH_DISABLED"):
        return

    expected = os.environ.get("PRECON_API_TOKEN", "").strip()
    if not expected:
        if _truthy("PRECON_DEV_SEED"):
            # Local demo mode without a configured token
            return
        raise HTTPException(
            status_code=503,
            detail="PRECON_API_TOKEN not configured — mutating routes disabled",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    provided = authorization[len("Bearer "):].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid API token")
