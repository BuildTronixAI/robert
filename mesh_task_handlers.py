"""
D11 — Robert Mesh Task Handlers (Phase B)

Handlers for mesh tasks received from BOB.
Phase B: STAGED terminal state — no EXTERNALLY_COMMITTED.

All handlers return a result dict that becomes the STAGED payload.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


async def handle_analyze_customer(task_id: str, payload: dict) -> dict:
    """
    BOB delegates customer analysis to Robert.
    Robert has customer interaction history in its Witness.
    """
    customer_id = payload.get("customer_id", "")
    analysis_type = payload.get("analysis_type", "general")
    
    # Phase B: return analysis stub — real implementation in Phase C
    return {
        "task_id": task_id,
        "customer_id": customer_id,
        "analysis_type": analysis_type,
        "result": f"Analysis staged for {customer_id}",
        "phase": "B",
        "note": "STAGED — not yet EXTERNALLY_COMMITTED (Phase B)",
    }


async def handle_check_status(task_id: str, payload: dict) -> dict:
    """BOB asks Robert for current operational status."""
    return {
        "task_id": task_id,
        "status": "operational",
        "phase": "B",
        "d11": "active",
    }


async def handle_delegate_response(task_id: str, payload: dict) -> dict:
    """
    BOB delegates a customer response task to Robert.
    Robert handles the customer-facing reply.
    Phase B: stage the response, don't send it yet.
    """
    message = payload.get("message", "")
    customer_id = payload.get("customer_id", "")
    
    return {
        "task_id": task_id,
        "customer_id": customer_id,
        "staged_message": message,
        "status": "staged",
        "phase": "B",
        "note": "Response staged — requires convergence before send (Phase C)",
    }


def register_handlers(receiver) -> None:
    """Register all Phase B task handlers with the mesh receiver."""
    receiver.register_handler("analyze_customer", handle_analyze_customer)
    receiver.register_handler("check_status", handle_check_status)
    receiver.register_handler("delegate_response", handle_delegate_response)
    logger.info("[D11] Phase B task handlers registered: %d handlers",
                len(receiver._task_handlers))
