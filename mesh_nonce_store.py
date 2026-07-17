"""
Shared mesh nonce / task_id claim store.

Order of backends:
  1. Supabase REST table `mesh_nonces` (multi-host) when configured
  2. Local SQLite via robert_store.DurableNonceStore (single-host durable)
  3. In-memory NonceStore (last resort — logged loudly)

Claim is atomic INSERT; conflict = replay.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class SharedNonceStore:
    def __init__(self, window_seconds: int = 600):
        self.window_seconds = window_seconds
        self._local = None
        try:
            from robert_store import DurableNonceStore
            self._local = DurableNonceStore(window_seconds=window_seconds)
        except Exception as e:
            logger.warning("SharedNonceStore: local durable store unavailable: %s", e)

    def check_and_record(self, nonce: str, task_id: str = "", sender_id: str = "") -> bool:
        """
        Claim nonce (+ optional task_id). Raises MeshReplayError on duplicate.
        Prefer Supabase for multi-host; always mirror to local when available.
        """
        from mesh_receiver import MeshReplayError

        supabase_ok = self._claim_supabase(nonce, task_id, sender_id)
        if supabase_ok is True:
            # Mirror locally best-effort
            self._mirror_local(nonce, task_id)
            return True
        if supabase_ok is False:
            raise MeshReplayError(f"Nonce already seen (supabase): {nonce[:16]}...")

        # Supabase unavailable — local durable
        if self._local is not None:
            try:
                return self._local.check_and_record(nonce, task_id)
            except Exception as e:
                if e.__class__.__name__ == "DurableReplayError":
                    raise MeshReplayError(str(e)) from e
                raise

        # Last resort in-memory
        logger.error("SharedNonceStore: falling back to in-memory nonce store — NOT multi-host safe")
        from mesh_receiver import NonceStore
        if not hasattr(self, "_memory"):
            self._memory = NonceStore()
        return self._memory.check_and_record(nonce)

    def _claim_supabase(self, nonce: str, task_id: str, sender_id: str):
        """
        Returns:
          True  — claimed successfully
          False — duplicate (replay)
          None  — backend unavailable / error (caller should fall back)
        """
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return None

        expires = datetime.now(timezone.utc) + timedelta(seconds=self.window_seconds)
        row = {
            "nonce": nonce,
            "task_id": task_id or None,
            "sender_id": sender_id or None,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires.isoformat(),
        }
        try:
            from tools.safe_fetch import safe_fetch
            status, body, _ = safe_fetch(
                f"{url}/rest/v1/mesh_nonces",
                method="POST",
                data=json.dumps(row).encode(),
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                timeout=5,
            )
            if status in (200, 201, 204):
                return True
            # Unexpected success-ish
            logger.warning("mesh_nonces insert unexpected status=%s body=%s", status, body[:120])
            return None
        except Exception as e:
            # HTTPError from urllib may be wrapped; inspect message
            msg = str(e).lower()
            # Also try urllib HTTPError directly if safe_fetch re-raises it
            import urllib.error
            if isinstance(e, urllib.error.HTTPError):
                if e.code in (409, 23505) or e.code == 409:
                    return False
                try:
                    body = e.read().decode()
                except Exception:
                    body = ""
                if "duplicate" in body.lower() or "unique" in body.lower():
                    return False
                logger.warning("mesh_nonces HTTP %s: %s", e.code, body[:120])
                return None
            if "409" in msg or "duplicate" in msg or "unique" in msg:
                return False
            logger.warning("mesh_nonces claim unavailable: %s — falling back", e)
            return None

    def _mirror_local(self, nonce: str, task_id: str) -> None:
        if self._local is None:
            return
        try:
            self._local.check_and_record(nonce, task_id)
        except Exception:
            # Already present locally is fine after supabase claim
            pass
