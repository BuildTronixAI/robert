"""
D11 — Robert Mesh Task Handlers

Phase B: STAGED terminal (default)
Phase C: handlers may set commit_external=True; receiver delivers to BOB
"""

from __future__ import annotations

import logging

from mesh_outbound import mesh_phase

logger = logging.getLogger(__name__)


async def handle_analyze_customer(task_id: str, payload: dict) -> dict:
    """BOB delegates customer analysis to Robert."""
    customer_id = payload.get("customer_id", "")
    analysis_type = payload.get("analysis_type", "general")
    phase = mesh_phase()
    return {
        "task_id": task_id,
        "customer_id": customer_id,
        "analysis_type": analysis_type,
        "result": f"Analysis staged for {customer_id}",
        "phase": phase,
        "commit_external": phase == "C",
        "note": (
            "EXTERNALLY_COMMITTED path available (Phase C)"
            if phase == "C"
            else "STAGED — not yet EXTERNALLY_COMMITTED (Phase B)"
        ),
    }


async def handle_check_status(task_id: str, payload: dict) -> dict:
    """BOB asks Robert for current operational status."""
    phase = mesh_phase()
    return {
        "task_id": task_id,
        "status": "operational",
        "phase": phase,
        "d11": "active",
        "commit_external": phase == "C",
    }


async def handle_delegate_response(task_id: str, payload: dict) -> dict:
    """
    BOB delegates a customer response task to Robert.
    Phase B: stage only.
    Phase C: stage then deliver result envelope to BOB (BOB owns customer send).
    """
    message = payload.get("message", "")
    customer_id = payload.get("customer_id", "")
    phase = mesh_phase()
    return {
        "task_id": task_id,
        "customer_id": customer_id,
        "staged_message": message,
        "status": "staged",
        "phase": phase,
        "commit_external": phase == "C",
        "note": (
            "Result delivered to BOB for customer send (Phase C)"
            if phase == "C"
            else "Response staged — requires Phase C for external commit"
        ),
    }


def register_handlers(receiver) -> None:
    """Register mesh task handlers with the receiver."""
    receiver.register_handler("analyze_customer", handle_analyze_customer)
    receiver.register_handler("check_status", handle_check_status)
    receiver.register_handler("delegate_response", handle_delegate_response)
    logger.info(
        "[D11] Mesh task handlers registered: %d handlers (phase=%s)",
        len(receiver._task_handlers),
        mesh_phase(),
    )
