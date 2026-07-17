"""PRECON API — Screen 1 routes"""
from fastapi import APIRouter, HTTPException
from precon.api.models import (
    Screen1ItemOut, ConflictDetailsOut, Screen1DecideRequest, Screen1DecideResponse,
    GateCheckOut, BidConfidenceOut, VectorScoreOut, ReviewDecision,
)
from precon.api.store import get_or_create_store
from precon.api.routers.projects import _bid_confidence_out

router = APIRouter(prefix="/projects/{project_id}/screen1", tags=["screen1"])


def _item_out(item) -> Screen1ItemOut:
    cd = None
    if item.conflict_details:
        d = item.conflict_details
        cd = ConflictDetailsOut(
            doc_a=d.get("doc_a", ""), value_a=d.get("value_a", ""),
            doc_b=d.get("doc_b", ""), value_b=d.get("value_b", ""),
        )
    return Screen1ItemOut(
        item_id=item.item_id, project_id=item.project_id,
        flag_type=item.flag_type, description=item.description,
        source_document=item.source_document, source_sheet=item.source_sheet,
        mep_present=item.mep_present, ai_reasoning=item.ai_reasoning,
        conflict_details=cd, estimated_value=item.estimated_value,
        decision=item.decision, estimator_notes=item.estimator_notes,
        decided_by=item.decided_by, decided_at=item.decided_at,
        assumption_pricing_confirmed=item.assumption_pricing_confirmed or False,
        assumption_text=item.assumption_text or "",
        sia_text=item.sia_text or "",
    )


@router.get("", response_model=list[Screen1ItemOut])
def get_screen1_items(project_id: str):
    store = get_or_create_store(project_id)
    return [_item_out(i) for i in store.screen1_items]


@router.post("/{item_id}/decide", response_model=Screen1DecideResponse)
def decide_screen1_item(project_id: str, item_id: str, body: Screen1DecideRequest):
    store = get_or_create_store(project_id)
    store.decide_screen1(item_id, body.decision, body.notes,
                          body.assume_price_confirmed, body.assume_text)
    return Screen1DecideResponse(
        ok=True,
        bid_confidence=_bid_confidence_out(store.compute_bid_confidence()),
    )


@router.post("/advance", response_model=GateCheckOut)
def advance_screen1(project_id: str):
    store = get_or_create_store(project_id)
    passed, error = store.advance_screen1()
    return GateCheckOut(passed=passed, blocking_reason=error)
