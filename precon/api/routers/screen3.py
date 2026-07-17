"""PRECON API — Screen 3 routes"""
from fastapi import APIRouter, Depends
from precon.api.auth import require_api_token
from precon.api.models import (
    Screen3ItemOut, Screen3SaveRequest, Screen3SaveResponse, GateCheckOut,
)
from precon.api.store import get_or_create_store

router = APIRouter(prefix="/projects/{project_id}/screen3", tags=["screen3"])


def _item_out(item) -> Screen3ItemOut:
    return Screen3ItemOut(
        item_id=item.item_id, project_id=item.project_id,
        takeoff_item_id=item.takeoff_item_id,
        description=item.description, quantity=item.quantity, unit=item.unit,
        ai_cost_code=item.ai_cost_code, ai_translation_method=item.ai_translation_method,
        ai_confidence=item.ai_confidence, confirmed_cost_code=item.confirmed_cost_code,
        unit_labor=item.unit_labor, unit_material=item.unit_material,
        unit_equipment=item.unit_equipment, total_cost=item.total_cost,
        status=item.status, correction_notes=item.correction_notes,
        decided_by=item.decided_by, decided_at=item.decided_at,
        was_corrected=item.was_corrected,
        correction_from=item.correction_from, correction_to=item.correction_to,
    )


@router.get("", response_model=list[Screen3ItemOut])
def get_screen3_items(project_id: str):
    store = get_or_create_store(project_id)
    return [_item_out(i) for i in store.screen3_items]


@router.post("/{item_id}/save", response_model=Screen3SaveResponse)
def save_screen3_item(project_id: str, item_id: str, body: Screen3SaveRequest, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    total = store.save_screen3(
        item_id, body.cost_code, body.labor, body.material, body.equipment, body.notes
    )
    return Screen3SaveResponse(ok=True, total_cost=total)


@router.post("/advance", response_model=GateCheckOut)
def advance_screen3(project_id: str, _auth: None = Depends(require_api_token)):
    store = get_or_create_store(project_id)
    passed, error = store.advance_screen3()
    return GateCheckOut(passed=passed, blocking_reason=error)
