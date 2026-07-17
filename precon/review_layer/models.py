"""
REVIEW LAYER — DATA MODELS v1.0
Schema-freeze approved June 16, 2026.

All 10 schema decisions incorporated:
  Q1  - Document Coverage blocks; Heuristic advisory only
  Q2  - 3-tier omission confidence: SOURCE_DERIVED / CROSS_REFERENCE / HEURISTIC
  Q3  - Risk-weighted review, item-level quantity scores, residual risk gate, 4-vector bid confidence
  Q4  - Vendor quality thresholds configurable with smart defaults
  Q5  - Override authority role-permission-based
  Q6  - Batch approval configurable with auto defaults
  Q7  - Integrity alerts separate permission, threshold-crossing + missing artifact trigger
  Q8  - Bid confidence weights: pre-built project-type templates + company override
  Q9  - File root: OneDrive + local network
  Q10 - Drag-and-drop: unclassified/pending + AI best guess pre-populated

IMMUTABLE after schema freeze. Changes require formal schema change request.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class OmissionConfidence(str, Enum):
    SOURCE_DERIVED   = "source_derived"    # Item in actual document, engine missed it. Blocks.
    CROSS_REFERENCE  = "cross_reference"   # Inferred from 2 docs agreeing. Blocks.
    HEURISTIC        = "heuristic"         # Building-type expectation only. Advisory only. Never blocks.


class CrossDocState(str, Enum):
    AGREE            = "agree"             # Two+ docs agree on qty/spec. Positive signal.
    DISAGREE         = "disagree"          # Docs conflict. Tracked condition, not a penalty.
    NO_SECOND_SOURCE = "no_second_source"  # Single source only. Neutral — not positive, not negative.


class ReviewDecision(str, Enum):
    AI_PENDING       = "ai_pending"
    IN_REVIEW        = "in_review"
    INCLUDE          = "include"
    EXCLUDE          = "exclude"
    CLARIFY          = "clarify"
    ASSUME           = "assume"           # Priced + disclosed. Different from CLARIFY.
    DEFER            = "defer"
    APPROVED         = "approved"         # Takeoff/recap: estimator confirmed AI correct
    CORRECTED        = "corrected"        # Estimator changed AI output
    NEEDS_RECONFIRM  = "needs_reconfirm"  # Set when upstream screen reopened


class CoverageStatus(str, Enum):
    PENDING          = "pending"
    ADDED            = "added"            # Tab A: added to takeoff
    EXCLUDED         = "excluded"         # Tab A: confirmed by others / not in scope
    DISMISSED        = "dismissed"        # Tab A: heuristic dismissed (advisory only)
    VERIFIED         = "verified"         # Tab B: citation cross-check passed
    CITATION_FAILED  = "citation_failed"  # Tab B: citation didn't pass cross-check
    PRINCIPAL_OVERRIDE = "principal_override"  # Tab B: senior role overrode failed citation
    REMOVED          = "removed"          # Tab B: removed from takeoff


class IntegrityAlertLevel(str, Enum):
    P1_HIGH          = "p1_high"          # Threshold crossed + no decision artifact
    P2_PATTERN       = "p2_pattern"       # 3+ conversions + threshold crossed
    P3_ANALYTICS     = "p3_analytics"     # Tracked only, no alert fired


class FileRootType(str, Enum):
    ONEDRIVE         = "onedrive"
    LOCAL_NETWORK    = "local_network"
    LOCAL            = "local"


class ClassificationStatus(str, Enum):
    CLASSIFIED       = "classified"
    PENDING_REVIEW   = "pending_review"   # In unclassified/pending holding area
    CONFIRMED        = "confirmed"        # Human confirmed AI classification
    CORRECTED        = "corrected"        # Human corrected AI classification


class GateResult(str, Enum):
    PASS    = "pass"
    WARNING = "warning"
    BLOCK   = "block"


# ---------------------------------------------------------------------------
# Q1/Q2 — Interpretation Review (Screen 1)
# ---------------------------------------------------------------------------

@dataclass
class InterpretationReviewItem:
    """One card in Screen 1 — Interpretation Review."""
    item_id: str
    project_id: str
    flag_type: str              # ARCH_ONLY | CONFLICT | NIC_BIC | ADDENDUM
    description: str
    source_document: str        # e.g. "Arch Sheet A-211"
    source_sheet: str           # e.g. "A-211"
    mep_present: bool           # False = not found on MEP drawings
    ai_reasoning: str           # Plain-English explanation for estimator
    conflict_details: dict      # For CONFLICT: {doc_a, value_a, doc_b, value_b}
    estimated_value: float      # AI rough cost estimate — shown on card

    # Decision
    decision: ReviewDecision = ReviewDecision.AI_PENDING
    estimator_notes: str = ""   # Required before decision saved
    decided_by: str = ""        # Role + user ID
    decided_at: str = ""        # ISO timestamp
    session_id: str = ""

    # ASSUME-specific — only populated when decision == ASSUME
    assumption_pricing_confirmed: bool = False  # Was a line-item price entered?
    assumption_text: str = ""                   # Disclosure text for proposal

    # CLARIFY-specific — for SIA letter generation
    sia_text: str = ""          # Auto-generated, estimator reviews before proposal

    # Audit
    previous_decision: Optional[ReviewDecision] = None  # For conversion tracking
    is_conversion: bool = False
    conversion_score_impact: float = 0.0        # Bid confidence delta from this decision


# ---------------------------------------------------------------------------
# Q3 — Takeoff Review (Screen 2) — item-level quantity confidence
# ---------------------------------------------------------------------------

# Risk weight factors (Q3) — used to compute item-level risk weight
RISK_WEIGHT_FACTORS = {
    "heuristic_quantity":        40,
    "coverage_anomaly":          40,
    "cross_document_conflict":   30,
    "addendum_impact":           15,
    "single_source_quantity":    15,
    "prior_estimator_correction": 10,
    "explicit_schedule_quantity":  0,
}


@dataclass
class QuantityReliabilityScore:
    """Item-level quantity reliability — Q3. Never project-level aggregate."""
    item_id: str
    source_quality_score: float     # 0-1: schedule_matched=1.0, spec_matched=0.9, cross_ref=0.6, ai_semantic=0.2
    cross_doc_state: CrossDocState
    cross_doc_score: float          # AGREE=1.0, NO_SECOND_SOURCE=0.5, DISAGREE=0.0
    quantity_provenance: str        # explicit | derived | inferred
    provenance_score: float         # explicit=1.0, derived=0.7, inferred=0.3
    risk_weight: int                # Sum of applicable RISK_WEIGHT_FACTORS
    item_reliability_score: float   # 0-100, weighted composite
    # Weights: source_quality=45%, cross_doc=30%, provenance=25%


@dataclass
class TakeoffReviewItem:
    """One row in Screen 2 — Takeoff Review."""
    item_id: str
    project_id: str
    area: str                   # Level 1 | Level 2 | Mech Room | Roof | Site
    discipline: str             # Mechanical | Plumbing | Sheet Metal | Controls
    description: str
    source_sheet: str
    csi_section: str

    # AI extraction
    ai_quantity: float
    ai_unit: str                # EA | LF | SF | TON | CFM | GPM | KW | HP | LS
    ai_confidence: str          # HIGH | MEDIUM | LOW
    ai_confidence_source: str   # "schedule_matched" | "spec_matched" | "cross_sheet_inference" | "ai_semantic"
    ai_reasoning: str

    # Display-only cost code (Q6 — no edits here, corrections in Screen 3)
    display_cost_code: str
    display_cost_code_confidence: str   # EXACT_RULE | HISTORICAL | AI_SEMANTIC | UNMAPPED

    # Quantity reliability (item-level, Q3)
    quantity_reliability: Optional[QuantityReliabilityScore] = None

    # Estimator decision
    status: ReviewDecision = ReviewDecision.AI_PENDING
    estimator_quantity: Optional[float] = None  # Only on CORRECTED
    correction_notes: str = ""
    correction_source_sheet: str = ""           # Source cited for correction
    decided_by: str = ""
    decided_at: str = ""
    session_id: str = ""
    batch_approved: bool = False

    # Training hypothesis (never auto-promotes)
    is_correction: bool = False
    correction_delta: float = 0.0
    correction_pct: float = 0.0
    # Correction generates a hypothesis only — requires multi-project,
    # multi-estimator corroboration + explicit admin approval before promotion


# ---------------------------------------------------------------------------
# Q1/Q2 — Coverage Review (Screen 2.5)
# ---------------------------------------------------------------------------

@dataclass
class CoverageReviewItem:
    """One card in Screen 2.5 — Coverage Review (Tab A or Tab B)."""
    item_id: str
    project_id: str
    tab: str                    # "missing_scope" | "unverified_scope"

    # Omission confidence (Q2)
    omission_confidence: OmissionConfidence
    source_evidence: str        # What grounds the confidence grade
    blocking: bool              # SOURCE_DERIVED + CROSS_REFERENCE = True; HEURISTIC = False

    description: str
    csi_section: str
    estimated_value: float
    risk_weight: int            # From RISK_WEIGHT_FACTORS

    # Estimator decision
    status: CoverageStatus = CoverageStatus.PENDING
    decision_notes: str = ""
    decided_by: str = ""
    decided_at: str = ""
    session_id: str = ""

    # Tab B only — citation enforcement (Q10 analog, Q5 for override)
    citation_sheet: str = ""            # Must be from Engine 2A inventory dropdown
    citation_grid_row: str = ""         # Required for VERIFIED status
    citation_cross_check: str = ""      # PASS | FAIL
    citation_override_by: str = ""      # Role with integrity_alert permission
    citation_override_reason: str = ""


# ---------------------------------------------------------------------------
# Q3 — Cost Code Recap Review (Screen 3)
# ---------------------------------------------------------------------------

@dataclass
class RecapReviewItem:
    """One row in Screen 3 — Cost Code Recap Review."""
    item_id: str
    project_id: str
    takeoff_item_id: str        # Link to Screen 2 item

    description: str
    quantity: float             # LOCKED — from Screen 2 (approved or corrected qty)
    unit: str

    # AI assignment
    ai_cost_code: str
    ai_translation_method: str  # EXACT_RULE | HISTORICAL | AI_SEMANTIC | UNMAPPED
    ai_confidence: str

    # Estimator fields
    confirmed_cost_code: str = ""
    unit_labor: float = 0.0
    unit_material: float = 0.0
    unit_equipment: float = 0.0
    total_cost: float = 0.0     # Calculated field

    # Status
    status: ReviewDecision = ReviewDecision.AI_PENDING
    correction_notes: str = ""
    decided_by: str = ""
    decided_at: str = ""

    # Hypothesis log — never auto-promotes (Q3)
    was_corrected: bool = False
    correction_from: str = ""   # Original AI code
    correction_to: str = ""     # Estimator's correct code
    # These feed hypothesis log only. No rule promotion without:
    # - multiple projects
    # - multiple estimators
    # - closed-project outcome validation
    # - explicit admin approval


# ---------------------------------------------------------------------------
# Q4 — Vendor Quality (4-tier weighted)
# ---------------------------------------------------------------------------

@dataclass
class VendorQualityRecord:
    """Vendor quality tier for a CSI section on a project."""
    record_id: str
    project_id: str
    csi_section: str
    vendor_id: str
    vendor_name: str

    # Tier classification (Q4)
    tier: int                   # 0-4
    tier_label: str             # No Coverage / Assigned / Historical / Active / Active+Local
    tier_weight: float          # 0 / 0.25 / 0.50 / 0.75 / 1.00

    last_quote_date: Optional[str] = None       # ISO date
    last_award_date: Optional[str] = None       # ISO date — in-geography award
    award_distance_miles: Optional[float] = None
    quote_age_days: Optional[int] = None

    # Computed against company config thresholds (Q4 — configurable)
    quality_score: float = 0.0  # 0-1


# ---------------------------------------------------------------------------
# Q4/Q6/Q8 — Company Configuration
# ---------------------------------------------------------------------------

@dataclass
class CompanyConfig:
    """All configurable platform parameters. Set in Company Settings. (Q4/Q6/Q8/Q9/Q10)"""
    company_id: str

    # Vendor Quality thresholds (Q4)
    vendor_quote_recency_days: int = 90
    vendor_award_geography_miles: float = 100.0
    vendor_award_history_months: int = 24
    vendor_tier_weights: list = field(default_factory=lambda: [0.0, 0.25, 0.50, 0.75, 1.00])

    # Batch approval (Q6)
    batch_session_ceiling_pct: float = 0.50     # Max 50% of takeoff via batch
    batch_max_size: int = 25
    batch_attestation_required: bool = True     # Always True — not configurable
    # Alternating requirement: review N items after each batch (N = prior batch size)

    # Bid confidence weights (Q8) — defaults; project-type templates override
    bid_confidence_weights: dict = field(default_factory=lambda: {
        "coverage_reliability": 0.40,
        "quantity_reliability": 0.35,
        "review_integrity":     0.15,
        "pricing_reliability":  0.10,
    })

    # File root (Q9)
    file_root_type: FileRootType = FileRootType.LOCAL_NETWORK
    file_root_path: str = ""

    # Permissions (Q5/Q7)
    permissions: dict = field(default_factory=lambda: {
        "verification_override": ["operations_manager", "principal"],
        "bid_review":            ["chief_estimator", "principal"],
        "integrity_alert":       ["principal"],  # Separate from bid_review (Q7)
        "batch_approval_override": ["operations_manager", "principal"],
        "schema_rule_approval":  ["principal"],
    })


# ---------------------------------------------------------------------------
# Q8 — Bid Confidence Weight Profiles (pre-built templates)
# ---------------------------------------------------------------------------

BID_CONFIDENCE_PROFILES = {
    "hospital": {
        "coverage_reliability": 0.50,
        "quantity_reliability": 0.30,
        "review_integrity":     0.12,
        "pricing_reliability":  0.08,
    },
    "military": {
        "coverage_reliability": 0.48,
        "quantity_reliability": 0.32,
        "review_integrity":     0.12,
        "pricing_reliability":  0.08,
    },
    "office": {
        "coverage_reliability": 0.35,
        "quantity_reliability": 0.35,
        "review_integrity":     0.15,
        "pricing_reliability":  0.15,
    },
    "retail": {
        "coverage_reliability": 0.30,
        "quantity_reliability": 0.30,
        "review_integrity":     0.15,
        "pricing_reliability":  0.25,
    },
    "restaurant": {
        "coverage_reliability": 0.35,
        "quantity_reliability": 0.30,
        "review_integrity":     0.15,
        "pricing_reliability":  0.20,
    },
    "warehouse": {
        "coverage_reliability": 0.30,
        "quantity_reliability": 0.30,
        "review_integrity":     0.15,
        "pricing_reliability":  0.25,
    },
    "school": {
        "coverage_reliability": 0.42,
        "quantity_reliability": 0.33,
        "review_integrity":     0.15,
        "pricing_reliability":  0.10,
    },
    "government": {
        "coverage_reliability": 0.45,
        "quantity_reliability": 0.33,
        "review_integrity":     0.12,
        "pricing_reliability":  0.10,
    },
    "default": {
        "coverage_reliability": 0.40,
        "quantity_reliability": 0.35,
        "review_integrity":     0.15,
        "pricing_reliability":  0.10,
    },
}


# ---------------------------------------------------------------------------
# Q7 — Integrity Alert
# ---------------------------------------------------------------------------

@dataclass
class IntegrityAlert:
    """
    Fired when CLARIFY→ASSUME conversion pattern detected. (Q7)
    Routes to integrity_alert permission — NOT bid_review permission.
    These are separate governance functions.
    """
    alert_id: str
    project_id: str
    level: IntegrityAlertLevel
    triggered_at: str           # ISO timestamp

    # Trigger evidence
    conversion_item_ids: list   # Items that converted CLARIFY→ASSUME
    threshold_crossed: bool     # Did bid become submittable after conversion?
    decision_artifact_present: bool  # Was a pricing decision made? (Q7)
    # Decision artifact = any of:
    #   line_item_value_changed, contingency_allocated,
    #   pricing_note_entered, assumption_text_updated

    score_before: float
    score_after: float
    score_delta: float

    # Routing (Q5/Q7 — role-permission-based)
    routed_to_permission: str = "integrity_alert"  # Never bid_review
    reviewed_by: str = ""
    reviewed_at: str = ""
    resolution: str = ""        # "legitimate" | "reversed" | "escalated"


# ---------------------------------------------------------------------------
# Q10 — Drag-and-drop file intake (Unclassified/Pending)
# ---------------------------------------------------------------------------

@dataclass
class UnclassifiedFile:
    """
    File dropped into project — held in pending area until human confirms. (Q10)
    AI populates best guess. Human confirms or corrects in one click.
    Nothing enters live document registry unconfirmed.
    """
    file_id: str
    project_id: str
    original_filename: str
    file_path: str              # Staging path — not yet in governed path
    file_size_bytes: int
    received_at: str
    received_via: str           # "drag_drop" | "watcher" | "manual_upload"

    # AI best guess (always populated) (Q10)
    ai_classification: str      # DRAWING | SPEC | ADDENDUM | VENDOR_QUOTE | OTHER
    ai_confidence: float        # 0-1
    ai_reasoning: str
    ai_suggested_project: str
    ai_suggested_path: str      # Where it would go if confirmed

    # Human confirmation
    status: ClassificationStatus = ClassificationStatus.PENDING_REVIEW
    confirmed_classification: str = ""
    confirmed_path: str = ""    # Final governed path after confirmation
    confirmed_by: str = ""
    confirmed_at: str = ""


# ---------------------------------------------------------------------------
# Q3 — Residual Risk Gate (replaces behavioral gating)
# ---------------------------------------------------------------------------

@dataclass
class ResidualRiskAssessment:
    """
    Replaces behavioral gating (Q3).
    Gate blocks on unresolved risk, never on review percentage.
    """
    project_id: str
    assessed_at: str

    # Residual risk components
    unreviewed_high_risk_items: int     # Items with risk_weight > 30, not reviewed
    unresolved_conflicts: int           # Cross-document disagreements not resolved
    unresolved_coverage_gaps: int       # SOURCE_DERIVED + CROSS_REFERENCE gaps not resolved
    unresolved_heuristic_quantities: int # HEURISTIC items with no decision

    # Totals
    total_residual_risk: int
    risk_threshold: int         # From company config — default 50
    gate_result: GateResult

    # The gate rule:
    # PASS when total_residual_risk <= risk_threshold
    # WARNING when threshold < risk <= threshold * 1.5
    # BLOCK when risk > threshold * 1.5
    # A diligent estimator who resolves high-risk items PASSES
    # even with low overall review percentage.


# ---------------------------------------------------------------------------
# Audit Log — every decision across all screens
# ---------------------------------------------------------------------------

@dataclass
class DecisionAuditRecord:
    """Immutable audit log entry for every review decision."""
    record_id: str
    project_id: str
    screen: str                 # screen_1 | screen_2 | screen_2_5 | screen_3
    item_id: str

    decision_type: ReviewDecision
    previous_decision: Optional[ReviewDecision]
    decided_by: str
    decided_at: str
    session_id: str

    # Batch approval tracking (Q6)
    batch_approved: bool = False
    batch_session_count: int = 0    # Total batch-approved in this session
    batch_session_pct: float = 0.0  # % of project takeoff batch-approved so far

    notes: str = ""

    # Integrity monitoring (Q7)
    is_clarify_to_assume: bool = False
    score_before: Optional[float] = None
    score_after: Optional[float] = None
    score_delta: float = 0.0
    threshold_crossing: bool = False        # Did bid become submittable?
    decision_artifact_present: bool = True  # False = no pricing change made
    deadline_pressure_flag: bool = False    # Conversion within 10min of score < threshold


# ---------------------------------------------------------------------------
# Screen state machine — gate enforcement
# ---------------------------------------------------------------------------

class ScreenState(str, Enum):
    LOCKED          = "locked"
    IN_PROGRESS     = "in_progress"
    COMPLETE        = "complete"
    REOPENED        = "reopened"    # Downstream items flagged NEEDS_RECONFIRM


@dataclass
class ProjectReviewState:
    """
    Master state for a project's review progress.
    Screen N cannot be IN_PROGRESS unless Screen N-1 is COMPLETE.
    """
    project_id: str
    screen_1:   ScreenState = ScreenState.LOCKED
    screen_2:   ScreenState = ScreenState.LOCKED
    screen_2_5: ScreenState = ScreenState.LOCKED
    screen_3:   ScreenState = ScreenState.LOCKED
    engine_2b_run: bool = False
    a10_complete:  bool = False
    proposal_ready: bool = False

    # Progress counters (for dashboard display)
    screen_1_total:   int = 0
    screen_1_decided: int = 0
    screen_2_total:   int = 0
    screen_2_decided: int = 0
    screen_2_5_blocking_total:   int = 0
    screen_2_5_blocking_resolved: int = 0
    screen_3_total:   int = 0
    screen_3_decided: int = 0

    # Batch tracking (Q6)
    session_batch_approved_count: int = 0
    session_batch_ceiling: int = 0          # 50% of screen_2_total

    # Last updated
    updated_at: str = ""
