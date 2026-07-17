"""
PRECON API — Pydantic request/response models
Mirrors TypeScript types exactly. Used by all FastAPI routes.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ReviewDecision(str, Enum):
    AI_PENDING      = "ai_pending"
    IN_REVIEW       = "in_review"
    INCLUDE         = "include"
    EXCLUDE         = "exclude"
    CLARIFY         = "clarify"
    ASSUME          = "assume"
    DEFER           = "defer"
    APPROVED        = "approved"
    CORRECTED       = "corrected"
    NEEDS_RECONFIRM = "needs_reconfirm"

class CoverageStatus(str, Enum):
    PENDING           = "pending"
    ADDED             = "added"
    EXCLUDED          = "excluded"
    DISMISSED         = "dismissed"
    VERIFIED          = "verified"
    CITATION_FAILED   = "citation_failed"
    PRINCIPAL_OVERRIDE = "principal_override"
    REMOVED           = "removed"

class ScreenState(str, Enum):
    LOCKED      = "locked"
    IN_PROGRESS = "in_progress"
    COMPLETE    = "complete"
    REOPENED    = "reopened"

class GateResultEnum(str, Enum):
    PASS    = "pass"
    WARNING = "warning"
    BLOCK   = "block"


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------
class QuantityReliabilityOut(BaseModel):
    item_id: str
    source_quality_score: float
    cross_doc_state: str
    cross_doc_score: float
    quantity_provenance: str
    provenance_score: float
    risk_weight: int
    item_reliability_score: float

class VectorScoreOut(BaseModel):
    name: str
    raw_score: float
    weight: float
    weighted_score: float
    components: dict[str, Any]
    notes: str = ""

class BidConfidenceOut(BaseModel):
    project_id: str
    composite_score: float
    confidence_tier: str
    coverage_vector: VectorScoreOut
    quantity_vector: VectorScoreOut
    review_integrity_vector: VectorScoreOut
    pricing_vector: VectorScoreOut
    profile_used: str
    weights_used: dict[str, float]
    submittable: bool
    submission_threshold: float

class ProjectReviewStateOut(BaseModel):
    project_id: str
    screen1: ScreenState
    screen2: ScreenState
    screen25: ScreenState
    screen3: ScreenState
    engine2b_run: bool
    a10_complete: bool
    proposal_ready: bool
    screen1_total: int
    screen1_decided: int
    screen2_total: int
    screen2_decided: int
    screen25_blocking_total: int
    screen25_blocking_resolved: int
    screen3_total: int
    screen3_decided: int
    session_batch_approved_count: int
    session_batch_ceiling: int
    updated_at: str

class GateCheckOut(BaseModel):
    passed: bool
    blocking_reason: Optional[str] = None
    warning_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Screen 1
# ---------------------------------------------------------------------------
class ConflictDetailsOut(BaseModel):
    doc_a: str
    value_a: str
    doc_b: str
    value_b: str

class Screen1ItemOut(BaseModel):
    item_id: str
    project_id: str
    flag_type: str
    description: str
    source_document: str
    source_sheet: str
    mep_present: bool
    ai_reasoning: str
    conflict_details: Optional[ConflictDetailsOut] = None
    estimated_value: float
    decision: ReviewDecision
    estimator_notes: str
    decided_by: str
    decided_at: str
    assumption_pricing_confirmed: bool = False
    assumption_text: str = ""
    sia_text: str = ""

class Screen1DecideRequest(BaseModel):
    decision: ReviewDecision
    notes: str
    assume_price_confirmed: bool = False
    assume_text: str = ""

class Screen1DecideResponse(BaseModel):
    ok: bool
    bid_confidence: BidConfidenceOut


# ---------------------------------------------------------------------------
# Screen 2
# ---------------------------------------------------------------------------
class Screen2ItemOut(BaseModel):
    item_id: str
    project_id: str
    area: str
    discipline: str
    description: str
    source_sheet: str
    csi_section: str
    ai_quantity: float
    ai_unit: str
    ai_confidence: str
    ai_confidence_source: str
    ai_reasoning: str
    display_cost_code: str
    display_cost_code_confidence: str
    quantity_reliability: Optional[QuantityReliabilityOut] = None
    status: ReviewDecision
    estimator_quantity: Optional[float] = None
    correction_notes: str
    correction_source_sheet: str
    decided_by: str
    decided_at: str
    batch_approved: bool

class Screen2CorrectRequest(BaseModel):
    qty: float
    notes: str
    sheet: str

class Screen2BatchApproveRequest(BaseModel):
    item_ids: list[str]

class Screen2BatchApproveResponse(BaseModel):
    ok: bool
    approved: int
    blocked: Optional[str] = None


# ---------------------------------------------------------------------------
# Screen 2.5
# ---------------------------------------------------------------------------
class CoverageItemOut(BaseModel):
    item_id: str
    project_id: str
    tab: str
    omission_confidence: str
    source_evidence: str
    blocking: bool
    description: str
    csi_section: str
    estimated_value: float
    risk_weight: int
    status: CoverageStatus
    decision_notes: str
    decided_by: str
    decided_at: str
    citation_sheet: str = ""
    citation_grid_row: str = ""
    citation_cross_check: Optional[str] = None
    citation_override_by: str = ""
    citation_override_reason: str = ""

class Screen25Out(BaseModel):
    tab_a: list[CoverageItemOut]
    tab_b: list[CoverageItemOut]

class TabAResolveRequest(BaseModel):
    resolution: str     # added | excluded | dismissed
    notes: str

class TabBVerifyRequest(BaseModel):
    sheet: str
    grid_row: str

class TabBVerifyResponse(BaseModel):
    ok: bool
    citation_result: str    # PASS | FAIL

class TabBRemoveRequest(BaseModel):
    notes: str

class TabBOverrideRequest(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# Screen 3
# ---------------------------------------------------------------------------
class Screen3ItemOut(BaseModel):
    item_id: str
    project_id: str
    takeoff_item_id: str
    description: str
    quantity: float
    unit: str
    ai_cost_code: str
    ai_translation_method: str
    ai_confidence: str
    confirmed_cost_code: str
    unit_labor: float
    unit_material: float
    unit_equipment: float
    total_cost: float
    status: ReviewDecision
    correction_notes: str
    decided_by: str
    decided_at: str
    was_corrected: bool
    correction_from: str
    correction_to: str

class Screen3SaveRequest(BaseModel):
    cost_code: str
    labor: float
    material: float
    equipment: float
    notes: str

class Screen3SaveResponse(BaseModel):
    ok: bool
    total_cost: float
