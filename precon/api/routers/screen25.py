"""PRECON API — Screen 2.5 routes"""
from fastapi import APIRouter, Depends
from precon.api.auth import require_api_token
from precon.api.models import (
    Screen25Out, CoverageItemOut, TabAResolveRequest,
    TabBVerifyRequest, TabBVerifyResponse, TabBRemoveRequest, TabBOverrideRequest,
    GateCheckOut,
)
from precon.api.store import get_or_create_store

router = APIRouter(prefix="/projects/{project_id}/screen25", tags=["screen25"])


def _item_out(item) -> CoverageItemOut:
    return CoverageItemOut(
        item_id=item.item_id, project_id=item.project_id, tab=item.tab,
        omission_confidence=item.omission_confidence.value,
        source_evidence=item.source_evidence, blocking=item.blocking,
        description=item.description, csi_section=item.csi_section,
        estimated_value=item.estimated_value, risk_weight=item.risk_weight,
        status=item.status, decision_notes=item.decision_notes,
        decided_by=item.decided_by, decided_at=item.decided_at,
        citation_sheet=item.citation_sheet or "",
        citation_grid_row=item.citation_grid_row or "",
        citation_cross_check=item.citation_cross_check,
        citation_override_by=item.citation_override_by or "",
        citation_override_reason=item.citation_override_reason or "",
    )


@router.get("", response_model=Screen25Out)
def get_screen25(project_id: str):
    store = get_or_create_store(project_id)
    return Screen25Out(
        tab_a=[_item_out(i) for i in store.screen25_tab_a],
        tab_b=[_item_out(i) for i in store.screen25_tab_b],
    )


@router.post("/tab-a/{item_id}/resolve", response_model=dict)
def resolve_tab_a(project_id: str, item_id: str, body: TabAResolveRequest, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    store.resolve_tab_a(item_id, body.resolution, body.notes)
    return {"ok": True}


@router.post("/tab-b/{item_id}/verify", response_model=TabBVerifyResponse)
def verify_tab_b(project_id: str, item_id: str, body: TabBVerifyRequest, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    result = store.verify_tab_b(item_id, body.sheet, body.grid_row)
    return TabBVerifyResponse(ok=True, citation_result=result)


@router.post("/tab-b/{item_id}/remove", response_model=dict)
def remove_tab_b(project_id: str, item_id: str, body: TabBRemoveRequest, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    store.remove_tab_b(item_id, body.notes)
    return {"ok": True}


@router.post("/tab-b/{item_id}/override", response_model=dict)
def override_tab_b(project_id: str, item_id: str, body: TabBOverrideRequest, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    store.override_tab_b(item_id, body.reason)
    return {"ok": True}


@router.post("/advance", response_model=GateCheckOut)
def advance_screen25(project_id: str, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    passed, error = store.advance_screen25()
    return GateCheckOut(passed=passed, blocking_reason=error)
