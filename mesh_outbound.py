"""
TronixMesh D11 — Outbound result delivery to BOB (Phase C)

Robert never holds BOB's Ed25519 private key. Outbound mesh results use the
existing HMAC envelope contract (bob_contract) so BOB can verify authenticity.

Terminal states:
  STAGED                — result computed, not delivered
  EXTERNALLY_COMMITTED  — result delivered to BOB inbox and acknowledged
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def mesh_phase() -> str:
    """Return 'B' or 'C'. Default B (STAGED-only)."""
    raw = os.environ.get("ROBERT_MESH_PHASE", "B").strip().upper()
    if raw in ("C", "3", "PHASE_C", "PHASEC"):
        return "C"
    if os.environ.get("ROBERT_MESH_EXTERNAL_COMMIT", "").lower() in ("1", "true", "yes"):
        return "C"
    return "B"


def external_commit_enabled() -> bool:
    return mesh_phase() == "C"


def deliver_result_to_bob(
    *,
    task_id: str,
    task_type: str,
    staged_hash: str,
    result: dict,
    sender_id: str = "robert",
) -> dict[str, Any]:
    """
    Deliver a staged mesh result to BOB's inbox.

    Returns:
      {"ok": True, "delivery": ...} on success
      {"ok": False, "error": "..."} on failure

    Fail-closed: caller must NOT mark EXTERNALLY_COMMITTED unless ok=True.
    """
    try:
        from bob_contract import build_envelope, _send_to_bob
    except Exception as e:
        return {"ok": False, "error": f"bob_contract unavailable: {e}"}

    if not os.environ.get("BOB_INBOX_URL", "").strip():
        return {"ok": False, "error": "BOB_INBOX_URL not configured"}
    if not os.environ.get("BOB_SHARED_SECRET", "").strip():
        return {"ok": False, "error": "BOB_SHARED_SECRET not configured"}

    payload = {
        "mesh_task_id": task_id,
        "task_type": task_type,
        "staged_hash": staged_hash,
        "result": result,
        "agent_id": sender_id,
        "terminal_state": "externally_committed",
    }
    try:
        env = build_envelope("mesh_result", payload, in_reply_to=task_id)
        delivery = _send_to_bob(env)
        if isinstance(delivery, dict) and delivery.get("ok") is False:
            return {"ok": False, "error": delivery.get("error", "bob_inbox_rejected")}
        logger.info("[D11 outbound] mesh_result delivered task_id=%s", task_id[:8])
        return {"ok": True, "delivery": delivery}
    except Exception as e:
        logger.error("[D11 outbound] delivery failed: %s", e)
        return {"ok": False, "error": str(e)}
