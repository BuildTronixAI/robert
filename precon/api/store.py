"""
PRECON API — In-Memory Project Store
Production would swap this for Supabase reads/writes.
Provides project state management for all review screens.
"""
from __future__ import annotations
from typing import Optional
import uuid
from datetime import datetime, timezone
from precon.review_layer.models import (
    InterpretationReviewItem, TakeoffReviewItem, CoverageReviewItem,
    RecapReviewItem, ProjectReviewState, ScreenState, ReviewDecision,
    CoverageStatus, BID_CONFIDENCE_PROFILES, CompanyConfig,
    VendorQualityRecord, QuantityReliabilityScore, CrossDocState,
)
from precon.bid_confidence.bid_confidence import (
    BidConfidenceCalculator, ReviewIntegrityInput, PricingReliabilityInput,
)
from precon.engine2a.engine2a import CoverageBaseline, OmissionFinding
from precon.engine2b.engine2b import ValidationResult
from precon.review_layer.models import GateResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    """
    In-memory store for a single project's review state.
    One instance per project. Thread-safe for single-worker FastAPI.
    """

    def __init__(self, project_id: str, project_name: str,
                 building_type: str = "office", mode: str = "sub"):
        self.project_id = project_id
        self.project_name = project_name
        self.building_type = building_type
        self.mode = mode
        self.config = CompanyConfig(company_id="newco")
        self.calc = BidConfidenceCalculator()

        # Screen data
        self.screen1_items: list[InterpretationReviewItem] = []
        self.screen2_items: list[TakeoffReviewItem] = []
        self.screen25_tab_a: list[CoverageReviewItem] = []
        self.screen25_tab_b: list[CoverageReviewItem] = []
        self.screen3_items: list[RecapReviewItem] = []

        # Review state
        self.review_state = ProjectReviewState(project_id=project_id)
        self.review_state.screen_1 = ScreenState.IN_PROGRESS
        self.review_state.updated_at = _now()

        # Batch tracking
        self.prior_batch_size = 0
        self.individual_since_last_batch = 0

        # Coverage baseline (Engine 2A output)
        self.coverage_baseline: Optional[CoverageBaseline] = None
        self.validation_result: Optional[ValidationResult] = None

    # ------------------------------------------------------------------
    # Bid confidence computation
    # ------------------------------------------------------------------
    def compute_bid_confidence(self):
        from precon.engine2a.engine2a import CoverageBaseline
        from precon.engine2b.engine2b import ValidationResult

        # Build minimal baseline/validation from current state if not set
        if self.coverage_baseline is None:
            self.coverage_baseline = CoverageBaseline(
                baseline_id=str(uuid.uuid4()), project_id=self.project_id,
                building_type=self.building_type, mode=self.mode, run_at=_now(),
                omissions=[], unverified=[],
                source_derived_count=0, cross_reference_count=0,
                heuristic_count=0, blocking_count=0, unverified_count=0,
                document_coverage_score=85.0, heuristic_coverage_score=75.0,
            )
        if self.validation_result is None:
            self.validation_result = ValidationResult(
                validation_id=str(uuid.uuid4()), project_id=self.project_id,
                run_at=_now(), gate_result=GateResult.PASS,
                blocking_gaps=[], advisory_gaps=[],
                approved_csi_sections=[], total_approved_value=0.0,
                blocking_gap_count=0, advisory_gap_count=0,
            )

        # Compute review integrity from current screen 2 state
        high_risk = [i for i in self.screen2_items
                     if i.quantity_reliability and i.quantity_reliability.risk_weight > 30]
        high_risk_reviewed = [i for i in high_risk
                               if i.status in (ReviewDecision.APPROVED, ReviewDecision.CORRECTED)]
        corrections = [i for i in high_risk_reviewed if i.status == ReviewDecision.CORRECTED]

        ri = ReviewIntegrityInput(
            total_items=len(self.screen2_items),
            high_risk_items=len(high_risk),
            high_risk_reviewed=len(high_risk_reviewed),
            verified_corrections=len(corrections),
            unresolved_conflicts=0,
            total_conflicts=0,
        )

        # Pricing from vendor records (placeholder)
        pricing = PricingReliabilityInput(
            vendor_quality_records=[],
            covered_csi_sections=len(set(i.csi_section for i in self.screen2_items)),
            total_csi_sections=max(1, len(set(i.csi_section for i in self.screen2_items))),
            labor_factor_source="benchmark",
            labor_factor_confidence="MEDIUM",
        )

        return self.calc.compute(
            project_id=self.project_id,
            building_type=self.building_type,
            coverage_baseline=self.coverage_baseline,
            validation_result=self.validation_result,
            takeoff_items=self.screen2_items,
            review_integrity=ri,
            pricing_input=pricing,
        )

    # ------------------------------------------------------------------
    # Screen 1 helpers
    # ------------------------------------------------------------------
    def decide_screen1(self, item_id: str, decision: ReviewDecision,
                        notes: str, assume_price: bool, assume_text: str):
        for item in self.screen1_items:
            if item.item_id == item_id:
                item.decision = decision
                item.estimator_notes = notes
                item.assumption_pricing_confirmed = assume_price
                item.assumption_text = assume_text
                item.decided_at = _now()
                break
        self._update_screen1_counts()

    def _update_screen1_counts(self):
        self.review_state.screen_1_total = len(self.screen1_items)
        self.review_state.screen_1_decided = sum(
            1 for i in self.screen1_items
            if i.decision not in (ReviewDecision.AI_PENDING, ReviewDecision.IN_REVIEW)
        )
        self.review_state.updated_at = _now()

    def advance_screen1(self) -> tuple[bool, Optional[str]]:
        pending = [i for i in self.screen1_items
                   if i.decision in (ReviewDecision.AI_PENDING, ReviewDecision.DEFER,
                                     ReviewDecision.IN_REVIEW)]
        if pending:
            return False, f"{len(pending)} item(s) still pending or deferred."
        self.review_state.screen_1 = ScreenState.COMPLETE
        self.review_state.screen_2 = ScreenState.IN_PROGRESS
        self._update_screen2_ceiling()
        self.review_state.updated_at = _now()
        return True, None

    # ------------------------------------------------------------------
    # Screen 2 helpers
    # ------------------------------------------------------------------
    def _update_screen2_ceiling(self):
        self.review_state.screen_2_total = len(self.screen2_items)
        self.review_state.session_batch_ceiling = len(self.screen2_items) // 2

    def approve_screen2(self, item_id: str):
        for item in self.screen2_items:
            if item.item_id == item_id:
                item.status = ReviewDecision.APPROVED
                item.decided_at = _now()
                self.individual_since_last_batch += 1
                break
        self._update_screen2_counts()

    def correct_screen2(self, item_id: str, qty: float, notes: str, sheet: str):
        for item in self.screen2_items:
            if item.item_id == item_id:
                item.status = ReviewDecision.CORRECTED
                item.estimator_quantity = qty
                item.correction_notes = notes
                item.correction_source_sheet = sheet
                item.decided_at = _now()
                self.individual_since_last_batch += 1
                break
        self._update_screen2_counts()

    def batch_approve_screen2(self, item_ids: list[str]) -> tuple[int, Optional[str]]:
        # Gate check
        ceiling = self.review_state.session_batch_ceiling
        current = self.review_state.session_batch_approved_count
        if current + len(item_ids) > ceiling:
            remaining = ceiling - current
            return 0, f"Ceiling: only {remaining} items can be batch-approved this session."

        if self.prior_batch_size > 0 and self.individual_since_last_batch < self.prior_batch_size:
            needed = self.prior_batch_size - self.individual_since_last_batch
            return 0, f"Must individually review {needed} more items before next batch."

        # Eligibility check
        eligible = {i.item_id for i in self.screen2_items
                    if i.ai_confidence == "HIGH"
                    and i.ai_confidence_source in ("schedule_matched", "spec_matched")
                    and i.status == ReviewDecision.AI_PENDING}

        approved = 0
        for iid in item_ids:
            if iid not in eligible:
                continue
            for item in self.screen2_items:
                if item.item_id == iid:
                    item.status = ReviewDecision.APPROVED
                    item.batch_approved = True
                    item.decided_at = _now()
                    approved += 1
                    break

        self.review_state.session_batch_approved_count += approved
        self.prior_batch_size = approved
        self.individual_since_last_batch = 0
        self._update_screen2_counts()
        return approved, None

    def _update_screen2_counts(self):
        self.review_state.screen_2_decided = sum(
            1 for i in self.screen2_items
            if i.status in (ReviewDecision.APPROVED, ReviewDecision.CORRECTED,
                            ReviewDecision.EXCLUDE)
        )
        self.review_state.updated_at = _now()

    def advance_screen2(self) -> tuple[bool, Optional[str]]:
        pending = [i for i in self.screen2_items if i.status == ReviewDecision.AI_PENDING]
        if pending:
            return False, f"{len(pending)} takeoff item(s) still pending."
        if self.review_state.session_batch_approved_count > self.review_state.session_batch_ceiling:
            return False, "Batch approval session ceiling exceeded."
        self.review_state.screen_2 = ScreenState.COMPLETE
        self.review_state.screen_2_5 = ScreenState.IN_PROGRESS
        self._update_screen25_counts()
        self.review_state.updated_at = _now()
        return True, None

    # ------------------------------------------------------------------
    # Screen 2.5 helpers
    # ------------------------------------------------------------------
    def _update_screen25_counts(self):
        blocking = [i for i in self.screen25_tab_a if i.blocking]
        resolved = [i for i in blocking if i.status != CoverageStatus.PENDING]
        self.review_state.screen_2_5_blocking_total = len(blocking)
        self.review_state.screen_2_5_blocking_resolved = len(resolved)
        self.review_state.updated_at = _now()

    def resolve_tab_a(self, item_id: str, resolution: str, notes: str):
        for item in self.screen25_tab_a:
            if item.item_id == item_id:
                item.status = CoverageStatus(resolution)
                item.decision_notes = notes
                item.decided_at = _now()
                break
        self._update_screen25_counts()

    def verify_tab_b(self, item_id: str, sheet: str, grid_row: str) -> str:
        """Returns PASS or FAIL. Mock: PASS if sheet and grid_row both non-empty."""
        citation_result = "PASS" if sheet and grid_row else "FAIL"
        for item in self.screen25_tab_b:
            if item.item_id == item_id:
                item.citation_sheet = sheet
                item.citation_grid_row = grid_row
                item.citation_cross_check = citation_result
                item.status = CoverageStatus.VERIFIED if citation_result == "PASS" else CoverageStatus.CITATION_FAILED
                item.decided_at = _now()
                break
        return citation_result

    def remove_tab_b(self, item_id: str, notes: str):
        for item in self.screen25_tab_b:
            if item.item_id == item_id:
                item.status = CoverageStatus.REMOVED
                item.decision_notes = notes
                item.decided_at = _now()
                break

    def override_tab_b(self, item_id: str, reason: str):
        for item in self.screen25_tab_b:
            if item.item_id == item_id:
                item.status = CoverageStatus.PRINCIPAL_OVERRIDE
                item.citation_override_reason = reason
                item.decided_at = _now()
                break

    def advance_screen25(self) -> tuple[bool, Optional[str]]:
        blocking_pending = [i for i in self.screen25_tab_a
                            if i.blocking and i.status == CoverageStatus.PENDING]
        if blocking_pending:
            return False, f"{len(blocking_pending)} blocking gap(s) unresolved."
        cit_failed = [i for i in self.screen25_tab_b
                      if i.status == CoverageStatus.CITATION_FAILED and not i.citation_override_by]
        if cit_failed:
            return False, f"{len(cit_failed)} citation failure(s) without override."
        self.review_state.screen_2_5 = ScreenState.COMPLETE
        self.review_state.screen_3 = ScreenState.IN_PROGRESS
        self._update_screen3_counts()
        self.review_state.updated_at = _now()
        return True, None

    # ------------------------------------------------------------------
    # Screen 3 helpers
    # ------------------------------------------------------------------
    def _update_screen3_counts(self):
        self.review_state.screen_3_total = len(self.screen3_items)
        self.review_state.screen_3_decided = sum(
            1 for i in self.screen3_items
            if i.status in (ReviewDecision.APPROVED, ReviewDecision.CORRECTED)
        )
        self.review_state.updated_at = _now()

    def save_screen3(self, item_id: str, cost_code: str, labor: float,
                     material: float, equipment: float, notes: str) -> float:
        for item in self.screen3_items:
            if item.item_id == item_id:
                corrected = (cost_code != item.ai_cost_code or
                             item.ai_translation_method == "AI_SEMANTIC")
                total = (labor + material + equipment) * item.quantity
                item.confirmed_cost_code = cost_code
                item.unit_labor = labor
                item.unit_material = material
                item.unit_equipment = equipment
                item.total_cost = total
                item.correction_notes = notes
                item.status = ReviewDecision.CORRECTED if corrected else ReviewDecision.APPROVED
                item.decided_at = _now()
                if corrected:
                    item.was_corrected = True
                    item.correction_from = item.ai_cost_code
                    item.correction_to = cost_code
                self._update_screen3_counts()
                return total
        return 0.0

    def advance_screen3(self) -> tuple[bool, Optional[str]]:
        unmapped = [i for i in self.screen3_items
                    if i.ai_translation_method == "UNMAPPED" and not i.confirmed_cost_code]
        semantic_pending = [i for i in self.screen3_items
                            if i.ai_translation_method == "AI_SEMANTIC"
                            and i.status == ReviewDecision.AI_PENDING]
        if unmapped:
            return False, f"{len(unmapped)} unmapped item(s) need cost codes."
        if semantic_pending:
            return False, f"{len(semantic_pending)} AI-semantic item(s) need review."
        self.review_state.screen_3 = ScreenState.COMPLETE
        self.review_state.updated_at = _now()
        return True, None


# ---------------------------------------------------------------------------
# Global registry (in-memory — swap for DB in production)
# ---------------------------------------------------------------------------
_stores: dict[str, ProjectStore] = {}

def get_store(project_id: str) -> Optional[ProjectStore]:
    return _stores.get(project_id)

def get_or_create_store(project_id: str, project_name: str = "",
                         building_type: str = "office", mode: str = "sub") -> ProjectStore:
    if project_id not in _stores:
        store = ProjectStore(project_id, project_name or project_id,
                             building_type, mode)
        # Seed with mock data for dev
        _seed_mock_data(store)
        _stores[project_id] = store
    return _stores[project_id]


def _seed_mock_data(store: ProjectStore):
    """Seed a project store with realistic demo data."""
    from precon.review_layer.models import (
        InterpretationReviewItem, TakeoffReviewItem, CoverageReviewItem,
        RecapReviewItem, QuantityReliabilityScore, CrossDocState,
    )

    pid = store.project_id

    # Screen 1
    store.screen1_items = [
        InterpretationReviewItem(
            item_id="s1-001", project_id=pid, flag_type="ARCH_ONLY",
            description="Radiant floor heating on A-201 — not on mechanical drawings",
            source_document="A-201", source_sheet="A-201", mep_present=False,
            ai_reasoning="Radiant tubing shown on A-201, no hydronic piping on P-series.",
            conflict_details={}, estimated_value=28500,
            decision=ReviewDecision.AI_PENDING, estimator_notes="",
            decided_by="", decided_at="", session_id="",
        ),
        InterpretationReviewItem(
            item_id="s1-002", project_id=pid, flag_type="CONFLICT",
            description="AHU-3 supply CFM conflict — Schedule vs. Addendum 2",
            source_document="M-101", source_sheet="M-101", mep_present=True,
            ai_reasoning="Original: 8,500 CFM. Addendum 2: 12,000 CFM.",
            conflict_details={"doc_a": "M-101 (Original)", "value_a": "8,500 CFM 5HP",
                              "doc_b": "Addendum 2", "value_b": "12,000 CFM 7.5HP"},
            estimated_value=14000,
            decision=ReviewDecision.AI_PENDING, estimator_notes="",
            decided_by="", decided_at="", session_id="",
        ),
        InterpretationReviewItem(
            item_id="s1-003", project_id=pid, flag_type="ADDENDUM",
            description="Addendum 3 adds cooling tower bypass piping",
            source_document="Addendum 3", source_sheet="Addendum 3", mep_present=True,
            ai_reasoning="120 LF 4\" bypass loop added. Significant labor impact.",
            conflict_details={}, estimated_value=42000,
            decision=ReviewDecision.AI_PENDING, estimator_notes="",
            decided_by="", decided_at="", session_id="",
        ),
    ]
    store.review_state.screen1_total = len(store.screen1_items)

    # Screen 2
    def make_qr(item_id, risk=0, state=CrossDocState.AGREE, reliability=95.0):
        return QuantityReliabilityScore(
            item_id=item_id, source_quality_score=1.0, cross_doc_state=state,
            cross_doc_score=1.0 if state == CrossDocState.AGREE else 0.5,
            quantity_provenance="explicit", provenance_score=1.0,
            risk_weight=risk, item_reliability_score=reliability,
        )

    store.screen2_items = [
        TakeoffReviewItem(
            item_id="s2-001", project_id=pid, area="Level 1", discipline="Mechanical",
            description="Air Handling Unit AHU-1", source_sheet="M-101", csi_section="237300",
            ai_quantity=1, ai_unit="EA", ai_confidence="HIGH",
            ai_confidence_source="schedule_matched", ai_reasoning="M-101 schedule row AHU-1",
            display_cost_code="110", display_cost_code_confidence="EXACT_RULE",
            quantity_reliability=make_qr("s2-001"), status=ReviewDecision.AI_PENDING,
            correction_notes="", correction_source_sheet="",
            decided_by="", decided_at="", session_id="", batch_approved=False,
        ),
        TakeoffReviewItem(
            item_id="s2-002", project_id=pid, area="Level 1", discipline="Mechanical",
            description="Fan Coil Units FCU-101 thru FCU-118 (18 EA)", source_sheet="M-101",
            csi_section="238216", ai_quantity=18, ai_unit="EA", ai_confidence="HIGH",
            ai_confidence_source="schedule_matched", ai_reasoning="Schedule rows FCU-101–FCU-118",
            display_cost_code="110", display_cost_code_confidence="EXACT_RULE",
            quantity_reliability=make_qr("s2-002"), status=ReviewDecision.AI_PENDING,
            correction_notes="", correction_source_sheet="",
            decided_by="", decided_at="", session_id="", batch_approved=False,
        ),
        TakeoffReviewItem(
            item_id="s2-003", project_id=pid, area="Mech Room", discipline="Mechanical",
            description="Chiller Plant — 120 Ton Centrifugal", source_sheet="M-501",
            csi_section="236500", ai_quantity=1, ai_unit="EA", ai_confidence="HIGH",
            ai_confidence_source="schedule_matched", ai_reasoning="Chiller schedule M-501",
            display_cost_code="120", display_cost_code_confidence="EXACT_RULE",
            quantity_reliability=make_qr("s2-003"), status=ReviewDecision.AI_PENDING,
            correction_notes="", correction_source_sheet="",
            decided_by="", decided_at="", session_id="", batch_approved=False,
        ),
        TakeoffReviewItem(
            item_id="s2-004", project_id=pid, area="Level 2", discipline="Mechanical",
            description="Supply duct main trunk 48x24", source_sheet="M-201",
            csi_section="233100", ai_quantity=340, ai_unit="LF", ai_confidence="MEDIUM",
            ai_confidence_source="cross_sheet_inference",
            ai_reasoning="Measured from M-201, cross-ref M-202",
            display_cost_code="200", display_cost_code_confidence="EXACT_RULE",
            quantity_reliability=make_qr("s2-004", risk=45, state=CrossDocState.DISAGREE, reliability=52.0),
            status=ReviewDecision.AI_PENDING,
            correction_notes="", correction_source_sheet="",
            decided_by="", decided_at="", session_id="", batch_approved=False,
        ),
        TakeoffReviewItem(
            item_id="s2-005", project_id=pid, area="Level 1", discipline="Plumbing",
            description="Domestic HW Heater 80 Gal Electric", source_sheet="P-201",
            csi_section="223500", ai_quantity=2, ai_unit="EA", ai_confidence="HIGH",
            ai_confidence_source="schedule_matched", ai_reasoning="Water heater schedule P-201",
            display_cost_code="310", display_cost_code_confidence="EXACT_RULE",
            quantity_reliability=make_qr("s2-005"), status=ReviewDecision.AI_PENDING,
            correction_notes="", correction_source_sheet="",
            decided_by="", decided_at="", session_id="", batch_approved=False,
        ),
    ]
    store.review_state.screen2_total = len(store.screen2_items)
    store.review_state.session_batch_ceiling = len(store.screen2_items) // 2

    # Screen 2.5
    from precon.review_layer.models import OmissionConfidence
    store.screen25_tab_a = [
        CoverageReviewItem(
            item_id="cv-001", project_id=pid, tab="missing_scope",
            omission_confidence=OmissionConfidence.SOURCE_DERIVED, blocking=True,
            source_evidence='Schedule row "ERV-1" in M-101 — not extracted',
            description="Energy Recovery Ventilator ERV-1 — in schedule, not extracted",
            csi_section="238126", estimated_value=38500, risk_weight=40,
            status=CoverageStatus.PENDING, decision_notes="", decided_by="", decided_at="",
        ),
        CoverageReviewItem(
            item_id="cv-002", project_id=pid, tab="missing_scope",
            omission_confidence=OmissionConfidence.CROSS_REFERENCE, blocking=True,
            source_evidence="Spec 230900 requires BACnet DDC contractor — no vendor quoted",
            description="BACnet DDC Controls — spec requires contractor, no vendor quoted",
            csi_section="230900", estimated_value=85000, risk_weight=30,
            status=CoverageStatus.PENDING, decision_notes="", decided_by="", decided_at="",
        ),
        CoverageReviewItem(
            item_id="cv-003", project_id=pid, tab="missing_scope",
            omission_confidence=OmissionConfidence.HEURISTIC, blocking=False,
            source_evidence="Military facilities typically require HVAC commissioning",
            description="HVAC Commissioning — typical for military, not in docs",
            csi_section="019113", estimated_value=22000, risk_weight=15,
            status=CoverageStatus.PENDING, decision_notes="", decided_by="", decided_at="",
        ),
    ]
    store.screen25_tab_b = [
        CoverageReviewItem(
            item_id="uv-001", project_id=pid, tab="unverified_scope",
            omission_confidence=OmissionConfidence.HEURISTIC, blocking=False,
            source_evidence="M-301 AI semantic extraction — LOW confidence",
            description="Exhaust Fan EF-12 — needs citation",
            csi_section="233423", estimated_value=4200, risk_weight=15,
            status=CoverageStatus.PENDING, decision_notes="", decided_by="", decided_at="",
        ),
    ]
    store._update_screen25_counts()

    # Screen 3
    store.screen3_items = [
        RecapReviewItem(
            item_id="s3-001", project_id=pid, takeoff_item_id="s2-001",
            description="Air Handling Unit AHU-1", quantity=1.0, unit="EA",
            ai_cost_code="110", ai_translation_method="EXACT_RULE", ai_confidence="HIGH",
            confirmed_cost_code="", unit_labor=0, unit_material=0, unit_equipment=0,
            total_cost=0, status=ReviewDecision.AI_PENDING, correction_notes="",
            decided_by="", decided_at="", was_corrected=False,
            correction_from="", correction_to="",
        ),
        RecapReviewItem(
            item_id="s3-002", project_id=pid, takeoff_item_id="s2-004",
            description="Supply duct main trunk 48x24", quantity=340.0, unit="LF",
            ai_cost_code="200", ai_translation_method="EXACT_RULE", ai_confidence="HIGH",
            confirmed_cost_code="", unit_labor=0, unit_material=0, unit_equipment=0,
            total_cost=0, status=ReviewDecision.AI_PENDING, correction_notes="",
            decided_by="", decided_at="", was_corrected=False,
            correction_from="", correction_to="",
        ),
        RecapReviewItem(
            item_id="s3-003", project_id=pid, takeoff_item_id="s2-005",
            description="Domestic HW Heater 80 Gal Electric", quantity=2.0, unit="EA",
            ai_cost_code="310", ai_translation_method="EXACT_RULE", ai_confidence="HIGH",
            confirmed_cost_code="", unit_labor=0, unit_material=0, unit_equipment=0,
            total_cost=0, status=ReviewDecision.AI_PENDING, correction_notes="",
            decided_by="", decided_at="", was_corrected=False,
            correction_from="", correction_to="",
        ),
        RecapReviewItem(
            item_id="s3-004", project_id=pid, takeoff_item_id="s2-003",
            description="Cooling Tower Bypass 4\" Pipe 120 LF", quantity=120.0, unit="LF",
            ai_cost_code="", ai_translation_method="UNMAPPED", ai_confidence="LOW",
            confirmed_cost_code="", unit_labor=0, unit_material=0, unit_equipment=0,
            total_cost=0, status=ReviewDecision.AI_PENDING, correction_notes="",
            decided_by="", decided_at="", was_corrected=False,
            correction_from="", correction_to="",
        ),
    ]
    store._update_screen3_counts()
