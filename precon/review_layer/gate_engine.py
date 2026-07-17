"""
REVIEW LAYER — GATE ENGINE v1.0
Enforces screen state machine and residual risk gate.

Gate logic (schema-freeze approved):
  Screen 1 complete  → zero AI_PENDING or DEFER items
  Screen 2 unlocks   → Screen 1 complete
  Screen 2 complete  → all items APPROVED/CORRECTED/EXCLUDED, batch ceiling not exceeded
  Screen 2.5 unlocks → Screen 2 complete
  Screen 2.5 complete→ zero SOURCE_DERIVED/CROSS_REFERENCE blocking gaps unresolved
                        zero Tab B CITATION_FAILED without PRINCIPAL_OVERRIDE
  Screen 3 unlocks   → Screen 2.5 complete
  Screen 3 complete  → zero UNMAPPED, all AI_SEMANTIC reviewed, all unit costs entered
  A-10 gate          → Screen 3 complete + Engine 2B run
  Proposal           → A-10 PASS or WARNING with override, residual risk <= threshold
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from precon.review_layer.models import (
    ProjectReviewState, ScreenState, ReviewDecision, CoverageStatus,
    OmissionConfidence, TakeoffReviewItem, InterpretationReviewItem,
    CoverageReviewItem, RecapReviewItem, ResidualRiskAssessment,
    RISK_WEIGHT_FACTORS, GateResult, DecisionAuditRecord,
    IntegrityAlert, IntegrityAlertLevel,
)
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GateCheckResult:
    passed: bool
    blocking_reason: Optional[str] = None
    warning_reason: Optional[str] = None


class ReviewLayerGateEngine:

    # ------------------------------------------------------------------
    # Screen 1 gate
    # ------------------------------------------------------------------

    def check_screen_1_complete(
        self, items: list[InterpretationReviewItem]
    ) -> GateCheckResult:
        blocking = [
            i for i in items
            if i.decision in (ReviewDecision.AI_PENDING, ReviewDecision.IN_REVIEW,
                              ReviewDecision.DEFER)
        ]
        if blocking:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(blocking)} interpretation items unresolved "
                    f"(DEFER or AI_PENDING). All must be decided before advancing."
                )
            )
        return GateCheckResult(passed=True)

    # ------------------------------------------------------------------
    # Screen 2 gate
    # ------------------------------------------------------------------

    def check_screen_2_complete(
        self,
        items: list[TakeoffReviewItem],
        state: ProjectReviewState,
    ) -> GateCheckResult:
        pending = [
            i for i in items
            if i.status == ReviewDecision.AI_PENDING
        ]
        if pending:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(pending)} takeoff items still AI_PENDING. "
                    f"All items must be APPROVED, CORRECTED, or EXCLUDED."
                )
            )

        # Batch ceiling check (Q6)
        if state.session_batch_approved_count > state.session_batch_ceiling:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"Batch approval ceiling exceeded. "
                    f"Maximum {state.session_batch_ceiling} items may be batch-approved "
                    f"(50% of {state.screen_2_total} total items). "
                    f"Currently batch-approved: {state.session_batch_approved_count}."
                )
            )

        return GateCheckResult(passed=True)

    # ------------------------------------------------------------------
    # Screen 2.5 gate
    # ------------------------------------------------------------------

    def check_screen_2_5_complete(
        self, items: list[CoverageReviewItem]
    ) -> GateCheckResult:
        # Blocking items: SOURCE_DERIVED and CROSS_REFERENCE gaps unresolved
        blocking_gaps = [
            i for i in items
            if i.tab == "missing_scope"
            and i.blocking
            and i.status == CoverageStatus.PENDING
        ]
        if blocking_gaps:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(blocking_gaps)} SOURCE_DERIVED or CROSS_REFERENCE "
                    f"coverage gaps unresolved. Each must be ADDED, EXCLUDED, or DISMISSED."
                )
            )

        # Tab B: CITATION_FAILED without override blocks
        citation_failed = [
            i for i in items
            if i.tab == "unverified_scope"
            and i.status == CoverageStatus.CITATION_FAILED
            and not i.citation_override_by
        ]
        if citation_failed:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(citation_failed)} unverified scope items have failed "
                    f"citation cross-check with no principal override. "
                    f"Re-cite with correct source, remove from takeoff, or obtain "
                    f"a principal-level override with documented reason."
                )
            )

        # HEURISTIC items: advisory — never blocking
        return GateCheckResult(passed=True)

    # ------------------------------------------------------------------
    # Screen 3 gate
    # ------------------------------------------------------------------

    def check_screen_3_complete(
        self, items: list[RecapReviewItem]
    ) -> GateCheckResult:
        unmapped = [
            i for i in items
            if i.ai_translation_method == "UNMAPPED"
            and i.confirmed_cost_code == ""
        ]
        if unmapped:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(unmapped)} UNMAPPED cost code items must be assigned "
                    f"before advancing."
                )
            )

        ai_semantic_unreviewed = [
            i for i in items
            if i.ai_translation_method == "AI_SEMANTIC"
            and i.status == ReviewDecision.AI_PENDING
        ]
        if ai_semantic_unreviewed:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(ai_semantic_unreviewed)} AI_SEMANTIC items require "
                    f"individual review."
                )
            )

        missing_costs = [
            i for i in items
            if i.status != ReviewDecision.AI_PENDING
            and i.unit_labor == 0.0
            and i.unit_material == 0.0
            and i.unit_equipment == 0.0
            and i.ai_translation_method != "UNMAPPED"
        ]
        if missing_costs:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(missing_costs)} items have no unit costs entered. "
                    f"All confirmed items require at least one cost entry."
                )
            )

        return GateCheckResult(passed=True)

    # ------------------------------------------------------------------
    # Residual Risk Gate (Q3 — gates on unresolved risk, not behavior)
    # ------------------------------------------------------------------

    def compute_residual_risk(
        self,
        project_id: str,
        takeoff_items: list[TakeoffReviewItem],
        coverage_items: list[CoverageReviewItem],
        risk_threshold: int = 50,
    ) -> ResidualRiskAssessment:
        """
        Gate on unresolved risk. Never on review percentage. (Q3)
        A diligent estimator who resolves high-risk items PASSES
        even with low overall review percentage.
        """
        # Unreviewed high-risk takeoff items
        unreviewed_high_risk = sum(
            1 for i in takeoff_items
            if i.status == ReviewDecision.AI_PENDING
            and i.quantity_reliability is not None
            and i.quantity_reliability.risk_weight > 30
        )

        # Unresolved cross-document conflicts
        unresolved_conflicts = sum(
            1 for i in takeoff_items
            if i.quantity_reliability is not None
            and i.quantity_reliability.cross_doc_state.value == "disagree"
            and i.status == ReviewDecision.AI_PENDING
        )

        # Unresolved coverage gaps (SOURCE_DERIVED + CROSS_REFERENCE)
        unresolved_coverage = sum(
            1 for i in coverage_items
            if i.blocking
            and i.status == CoverageStatus.PENDING
        )

        # Unresolved heuristic quantities with no decision
        unresolved_heuristic = sum(
            1 for i in coverage_items
            if i.omission_confidence == OmissionConfidence.HEURISTIC
            and i.status == CoverageStatus.PENDING
        )

        total = (
            unreviewed_high_risk +
            unresolved_conflicts +
            unresolved_coverage +
            unresolved_heuristic
        )

        if total <= risk_threshold:
            result = GateResult.PASS
        elif total <= risk_threshold * 1.5:
            result = GateResult.WARNING
        else:
            result = GateResult.BLOCK

        return ResidualRiskAssessment(
            project_id=project_id,
            assessed_at=_now(),
            unreviewed_high_risk_items=unreviewed_high_risk,
            unresolved_conflicts=unresolved_conflicts,
            unresolved_coverage_gaps=unresolved_coverage,
            unresolved_heuristic_quantities=unresolved_heuristic,
            total_residual_risk=total,
            risk_threshold=risk_threshold,
            gate_result=result,
        )

    # ------------------------------------------------------------------
    # State machine transitions
    # ------------------------------------------------------------------

    def advance_screen(
        self,
        state: ProjectReviewState,
        screen: str,
        gate_result: GateCheckResult,
    ) -> ProjectReviewState:
        """Attempt to advance a screen to COMPLETE. Returns updated state."""
        if not gate_result.passed:
            return state  # Gate did not pass — no state change

        if screen == "screen_1":
            state.screen_1 = ScreenState.COMPLETE
            state.screen_2 = ScreenState.IN_PROGRESS
        elif screen == "screen_2":
            state.screen_2 = ScreenState.COMPLETE
            state.screen_2_5 = ScreenState.IN_PROGRESS
        elif screen == "screen_2_5":
            state.screen_2_5 = ScreenState.COMPLETE
            state.screen_3 = ScreenState.IN_PROGRESS
        elif screen == "screen_3":
            state.screen_3 = ScreenState.COMPLETE

        state.updated_at = _now()
        return state

    def reopen_screen(
        self,
        state: ProjectReviewState,
        screen: str,
        reason: str,
        reopened_by: str,
    ) -> tuple[ProjectReviewState, list[str]]:
        """
        Reopen a screen. Downstream screens flagged NEEDS_RECONFIRM.
        Returns updated state + list of screens invalidated.
        """
        invalidated = []

        if screen == "screen_1":
            state.screen_1 = ScreenState.REOPENED
            state.screen_2 = ScreenState.LOCKED
            state.screen_2_5 = ScreenState.LOCKED
            state.screen_3 = ScreenState.LOCKED
            invalidated = ["screen_2", "screen_2_5", "screen_3"]
        elif screen == "screen_2":
            state.screen_2 = ScreenState.REOPENED
            state.screen_2_5 = ScreenState.LOCKED
            state.screen_3 = ScreenState.LOCKED
            invalidated = ["screen_2_5", "screen_3"]
        elif screen == "screen_2_5":
            state.screen_2_5 = ScreenState.REOPENED
            state.screen_3 = ScreenState.LOCKED
            invalidated = ["screen_3"]
        elif screen == "screen_3":
            state.screen_3 = ScreenState.REOPENED
            state.a10_complete = False
            state.proposal_ready = False
            invalidated = ["a10", "proposal"]

        state.updated_at = _now()
        return state, invalidated

    # ------------------------------------------------------------------
    # Integrity alert detection (Q7)
    # ------------------------------------------------------------------

    def check_integrity_alert(
        self,
        project_id: str,
        audit_records: list[DecisionAuditRecord],
        score_before: float,
        score_after: float,
        submission_threshold: float,
        session_id: str,
    ) -> Optional[IntegrityAlert]:
        score_before_session = score_before
        score_after_session = score_after
        """
        Detect CLARIFY→ASSUME gaming. (Q7)
        Routes to integrity_alert permission — never bid_review.
        Triggers on threshold-crossing + missing decision artifact.
        """
        session_conversions = [
            r for r in audit_records
            if r.session_id == session_id
            and r.is_clarify_to_assume
        ]

        if not session_conversions:
            return None

        threshold_crossed = (
            score_before_session < submission_threshold
            and score_after_session >= submission_threshold
        )

        # P1: Threshold crossed + no decision artifact (highest priority)
        no_artifact_conversions = [
            r for r in session_conversions
            if not r.decision_artifact_present
        ]

        if threshold_crossed and no_artifact_conversions:
            return IntegrityAlert(
                alert_id=str(uuid.uuid4()),
                project_id=project_id,
                level=IntegrityAlertLevel.P1_HIGH,
                triggered_at=_now(),
                conversion_item_ids=[r.item_id for r in no_artifact_conversions],
                threshold_crossed=True,
                decision_artifact_present=False,
                score_before=score_before_session,
                score_after=score_after_session,
                score_delta=score_after_session - score_before_session,
                routed_to_permission="integrity_alert",
            )

        # P2: 3+ conversions + threshold crossed (pattern detection)
        if len(session_conversions) >= 3 and threshold_crossed:
            return IntegrityAlert(
                alert_id=str(uuid.uuid4()),
                project_id=project_id,
                level=IntegrityAlertLevel.P2_PATTERN,
                triggered_at=_now(),
                conversion_item_ids=[r.item_id for r in session_conversions],
                threshold_crossed=True,
                decision_artifact_present=all(
                    r.decision_artifact_present for r in session_conversions
                ),
                score_before=score_before_session,
                score_after=score_after_session,
                score_delta=score_after_session - score_before_session,
                routed_to_permission="integrity_alert",
            )

        # P3: Analytics only — no alert fired, caller handles tracking
        return None

    # ------------------------------------------------------------------
    # Batch approval enforcement (Q6)
    # ------------------------------------------------------------------

    def validate_batch_approval(
        self,
        items_to_batch: list[TakeoffReviewItem],
        state: ProjectReviewState,
        config_max_batch_size: int = 25,
        individually_reviewed_since_last_batch: int = 0,
        prior_batch_size: int = 0,
    ) -> GateCheckResult:
        """
        Validate batch approval attempt. (Q6)
        Alternating requirement: must review N items since last batch (N = prior batch size).
        Session ceiling: 50% of total takeoff items max via batch.
        Eligible items: HIGH confidence with schedule/spec match provenance only.
        """
        # Alternating requirement
        if prior_batch_size > 0 and individually_reviewed_since_last_batch < prior_batch_size:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"Must individually review {prior_batch_size} items before next batch "
                    f"(reviewed {individually_reviewed_since_last_batch} since last batch)."
                )
            )

        # Batch size cap
        if len(items_to_batch) > config_max_batch_size:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"Batch size {len(items_to_batch)} exceeds maximum {config_max_batch_size}."
                )
            )

        # Session ceiling
        projected_total = state.session_batch_approved_count + len(items_to_batch)
        if projected_total > state.session_batch_ceiling:
            remaining = state.session_batch_ceiling - state.session_batch_approved_count
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"Session batch ceiling reached. Only {remaining} more items "
                    f"may be batch-approved this session "
                    f"(50% ceiling = {state.session_batch_ceiling} items)."
                )
            )

        # Eligibility: HIGH confidence with schedule/spec match provenance only
        ineligible = [
            i for i in items_to_batch
            if i.ai_confidence != "HIGH"
            or i.ai_confidence_source not in ("schedule_matched", "spec_matched")
        ]
        if ineligible:
            return GateCheckResult(
                passed=False,
                blocking_reason=(
                    f"{len(ineligible)} items in batch are not eligible for batch approval. "
                    f"Only HIGH confidence items with schedule or spec match provenance qualify. "
                    f"CROSS_REFERENCE and AI_SEMANTIC items require individual review."
                )
            )

        return GateCheckResult(passed=True)
