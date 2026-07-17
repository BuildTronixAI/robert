"""PRECON API — Screen 2 routes"""
from fastapi import APIRouter
from precon.api.models import (
    Screen2ItemOut, QuantityReliabilityOut, Screen2CorrectRequest,
    Screen2BatchApproveRequest, Screen2BatchApproveResponse, GateCheckOut,
    BidConfidenceOut,
)
from precon.api.store import get_or_create_store
from precon.api.routers.projects import _bid_confidence_out

router = APIRouter(prefix="/projects/{project_id}/screen2", tags=["screen2"])


def _item_out(item) -> Screen2ItemOut:
    qr = None
    if item.quantity_reliability:
        q = item.quantity_reliability
        qr = QuantityReliabilityOut(
            item_id=q.item_id, source_quality_score=q.source_quality_score,
            cross_doc_state=q.cross_doc_state.value,
            cross_doc_score=q.cross_doc_score,
            quantity_provenance=q.quantity_provenance,
            provenance_score=q.provenance_score, risk_weight=q.risk_weight,
            item_reliability_score=q.item_reliability_score,
        )
    return Screen2ItemOut(
        item_id=item.item_id, project_id=item.project_id,
        area=item.area, discipline=item.discipline, description=item.description,
        source_sheet=item.source_sheet, csi_section=item.csi_section,
        ai_quantity=item.ai_quantity, ai_unit=item.ai_unit,
        ai_confidence=item.ai_confidence,
        ai_confidence_source=item.ai_confidence_source,
        ai_reasoning=item.ai_reasoning, display_cost_code=item.display_cost_code,
        display_cost_code_confidence=item.display_cost_code_confidence,
        quantity_reliability=qr, status=item.status,
        estimator_quantity=item.estimator_quantity,
        correction_notes=item.correction_notes,
        correction_source_sheet=item.correction_source_sheet,
        decided_by=item.decided_by, decided_at=item.decided_at,
        batch_approved=item.batch_approved,
    )


@router.get("", response_model=list[Screen2ItemOut])
def get_screen2_items(project_id: str):
    store = get_or_create_store(project_id)
    return [_item_out(i) for i in store.screen2_items]


@router.post("/{item_id}/approve", response_model=dict)
def approve_item(project_id: str, item_id: str):
    store = get_or_create_store(project_id)
    store.approve_screen2(item_id)
    return {"ok": True, "bid_confidence": _bid_confidence_out(store.compute_bid_confidence()).model_dump()}


@router.post("/{item_id}/correct", response_model=dict)
def correct_item(project_id: str, item_id: str, body: Screen2CorrectRequest):
    store = get_or_create_store(project_id)
    store.correct_screen2(item_id, body.qty, body.notes, body.sheet)
    return {"ok": True, "bid_confidence": _bid_confidence_out(store.compute_bid_confidence()).model_dump()}


@router.post("/batch-approve", response_model=Screen2BatchApproveResponse)
def batch_approve(project_id: str, body: Screen2BatchApproveRequest):
    store = get_or_create_store(project_id)
    approved, error = store.batch_approve_screen2(body.item_ids)
    return Screen2BatchApproveResponse(ok=error is None, approved=approved, blocked=error)


@router.post("/advance", response_model=GateCheckOut)
def advance_screen2(project_id: str):
    store = get_or_create_store(project_id)
    passed, error = store.advance_screen2()
    return GateCheckOut(passed=passed, blocking_reason=error)
