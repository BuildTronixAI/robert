"""Review Layer v1.0 — Full Test Suite (schema-freeze approved)"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from precon.review_layer.models import (
    InterpretationReviewItem, TakeoffReviewItem, CoverageReviewItem,
    RecapReviewItem, ProjectReviewState, ScreenState, ReviewDecision,
    CoverageStatus, OmissionConfidence, CrossDocState, IntegrityAlertLevel,
    DecisionAuditRecord, CompanyConfig, VendorQualityRecord, FileRootType,
    BID_CONFIDENCE_PROFILES, RISK_WEIGHT_FACTORS, QuantityReliabilityScore,
    UnclassifiedFile, ClassificationStatus, ResidualRiskAssessment, GateResult,
)
from precon.review_layer.gate_engine import ReviewLayerGateEngine

gate = ReviewLayerGateEngine()
PID = str(uuid.uuid4())
SID = str(uuid.uuid4())


def make_interp_item(decision=ReviewDecision.AI_PENDING, **kwargs):
    defaults = dict(
        item_id=str(uuid.uuid4()), project_id=PID, flag_type="ARCH_ONLY",
        description="Test item", source_document="A-211", source_sheet="A-211",
        mep_present=False, ai_reasoning="Test", conflict_details={},
        estimated_value=2500.0, decision=decision, session_id=SID,
    )
    defaults.update(kwargs)
    return InterpretationReviewItem(**defaults)


def make_takeoff_item(status=ReviewDecision.AI_PENDING, confidence="HIGH",
                      confidence_source="schedule_matched", risk_weight=0, **kwargs):
    defaults = dict(
        item_id=str(uuid.uuid4()), project_id=PID, area="Level 1",
        discipline="Mechanical", description="FCU", source_sheet="M-101",
        csi_section="230000", ai_quantity=4.0, ai_unit="EA",
        ai_confidence=confidence, ai_confidence_source=confidence_source,
        ai_reasoning="Test", display_cost_code="110",
        display_cost_code_confidence="EXACT_RULE",
        quantity_reliability=QuantityReliabilityScore(
            item_id="x", source_quality_score=0.9,
            cross_doc_state=CrossDocState.AGREE, cross_doc_score=1.0,
            quantity_provenance="explicit", provenance_score=1.0,
            risk_weight=risk_weight, item_reliability_score=95.0,
        ),
        status=status, session_id=SID,
    )
    defaults.update(kwargs)
    return TakeoffReviewItem(**defaults)


def make_coverage_item(tab="missing_scope", confidence=OmissionConfidence.SOURCE_DERIVED,
                       status=CoverageStatus.PENDING, blocking=True, **kwargs):
    defaults = dict(
        item_id=str(uuid.uuid4()), project_id=PID, tab=tab,
        omission_confidence=confidence, source_evidence="M-001 Row 14",
        blocking=blocking, description="FCU-14", csi_section="230000",
        estimated_value=3400.0, risk_weight=15, status=status,
    )
    defaults.update(kwargs)
    return CoverageReviewItem(**defaults)


def make_recap_item(status=ReviewDecision.AI_PENDING, method="EXACT_RULE",
                    confirmed_code="110", unit_labor=420.0, **kwargs):
    defaults = dict(
        item_id=str(uuid.uuid4()), project_id=PID, takeoff_item_id="x",
        description="FCU", quantity=4.0, unit="EA",
        ai_cost_code="110", ai_translation_method=method,
        ai_confidence="HIGH", confirmed_cost_code=confirmed_code,
        unit_labor=unit_labor, unit_material=1850.0, unit_equipment=0.0,
        total_cost=9080.0, status=status,
    )
    defaults.update(kwargs)
    return RecapReviewItem(**defaults)


def make_state(s1=ScreenState.COMPLETE, s2=ScreenState.IN_PROGRESS,
               total=10, ceiling=5, batch_count=0):
    s = ProjectReviewState(project_id=PID)
    s.screen_1 = s1
    s.screen_2 = s2
    s.screen_2_total = total
    s.session_batch_ceiling = ceiling
    s.session_batch_approved_count = batch_count
    return s


# ============================================================
# SCREEN 1 GATE TESTS
# ============================================================

class TestScreen1Gate:
    def test_all_decided_passes(self):
        items = [make_interp_item(ReviewDecision.INCLUDE),
                 make_interp_item(ReviewDecision.EXCLUDE),
                 make_interp_item(ReviewDecision.CLARIFY),
                 make_interp_item(ReviewDecision.ASSUME)]
        r = gate.check_screen_1_complete(items)
        assert r.passed

    def test_pending_item_blocks(self):
        items = [make_interp_item(ReviewDecision.INCLUDE),
                 make_interp_item(ReviewDecision.AI_PENDING)]
        r = gate.check_screen_1_complete(items)
        assert not r.passed
        assert "AI_PENDING" in r.blocking_reason or "unresolved" in r.blocking_reason

    def test_defer_item_blocks(self):
        items = [make_interp_item(ReviewDecision.DEFER)]
        r = gate.check_screen_1_complete(items)
        assert not r.passed

    def test_empty_items_passes(self):
        r = gate.check_screen_1_complete([])
        assert r.passed

    def test_all_assume_passes(self):
        items = [make_interp_item(ReviewDecision.ASSUME) for _ in range(5)]
        r = gate.check_screen_1_complete(items)
        assert r.passed


# ============================================================
# SCREEN 2 GATE TESTS
# ============================================================

class TestScreen2Gate:
    def test_all_approved_passes(self):
        items = [make_takeoff_item(ReviewDecision.APPROVED) for _ in range(5)]
        state = make_state()
        r = gate.check_screen_2_complete(items, state)
        assert r.passed

    def test_pending_item_blocks(self):
        items = [make_takeoff_item(ReviewDecision.APPROVED),
                 make_takeout_item := make_takeoff_item(ReviewDecision.AI_PENDING)]
        items = [make_takeoff_item(ReviewDecision.APPROVED),
                 make_takeoff_item(ReviewDecision.AI_PENDING)]
        state = make_state()
        r = gate.check_screen_2_complete(items, state)
        assert not r.passed

    def test_corrected_item_passes(self):
        items = [make_takeoff_item(ReviewDecision.CORRECTED),
                 make_takeoff_item(ReviewDecision.APPROVED)]
        state = make_state()
        r = gate.check_screen_2_complete(items, state)
        assert r.passed

    def test_batch_ceiling_exceeded_blocks(self):
        items = [make_takeoff_item(ReviewDecision.APPROVED) for _ in range(5)]
        state = make_state(batch_count=6, ceiling=5)  # Over ceiling
        r = gate.check_screen_2_complete(items, state)
        assert not r.passed
        assert "ceiling" in r.blocking_reason.lower()

    def test_batch_ceiling_exactly_met_passes(self):
        items = [make_takeoff_item(ReviewDecision.APPROVED) for _ in range(5)]
        state = make_state(batch_count=5, ceiling=5)  # Exactly at ceiling
        r = gate.check_screen_2_complete(items, state)
        assert r.passed


# ============================================================
# SCREEN 2.5 GATE TESTS
# ============================================================

class TestScreen25Gate:
    def test_all_resolved_passes(self):
        items = [
            make_coverage_item(status=CoverageStatus.ADDED),
            make_coverage_item(status=CoverageStatus.EXCLUDED),
            make_coverage_item(tab="unverified_scope", blocking=False,
                               confidence=OmissionConfidence.HEURISTIC,
                               status=CoverageStatus.DISMISSED),
        ]
        r = gate.check_screen_2_5_complete(items)
        assert r.passed

    def test_source_derived_pending_blocks(self):
        items = [make_coverage_item(
            confidence=OmissionConfidence.SOURCE_DERIVED,
            status=CoverageStatus.PENDING, blocking=True
        )]
        r = gate.check_screen_2_5_complete(items)
        assert not r.passed

    def test_cross_reference_pending_blocks(self):
        items = [make_coverage_item(
            confidence=OmissionConfidence.CROSS_REFERENCE,
            status=CoverageStatus.PENDING, blocking=True
        )]
        r = gate.check_screen_2_5_complete(items)
        assert not r.passed

    def test_heuristic_pending_does_not_block(self):
        items = [make_coverage_item(
            confidence=OmissionConfidence.HEURISTIC,
            status=CoverageStatus.PENDING, blocking=False
        )]
        r = gate.check_screen_2_5_complete(items)
        assert r.passed  # Heuristic is advisory only — never blocks

    def test_tab_b_citation_failed_blocks(self):
        item = make_coverage_item(tab="unverified_scope", blocking=False,
                                  status=CoverageStatus.CITATION_FAILED)
        item.citation_override_by = ""  # No override
        r = gate.check_screen_2_5_complete([item])
        assert not r.passed

    def test_tab_b_citation_failed_with_override_passes(self):
        item = make_coverage_item(tab="unverified_scope", blocking=False,
                                  status=CoverageStatus.CITATION_FAILED)
        item.citation_override_by = "principal_user"
        item.citation_override_reason = "Confirmed via phone with engineer"
        r = gate.check_screen_2_5_complete([item])
        assert r.passed


# ============================================================
# SCREEN 3 GATE TESTS
# ============================================================

class TestScreen3Gate:
    def test_all_confirmed_passes(self):
        items = [make_recap_item(ReviewDecision.APPROVED) for _ in range(5)]
        r = gate.check_screen_3_complete(items)
        assert r.passed

    def test_unmapped_blocks(self):
        items = [make_recap_item(method="UNMAPPED", confirmed_code="")]
        r = gate.check_screen_3_complete(items)
        assert not r.passed

    def test_ai_semantic_pending_blocks(self):
        items = [make_recap_item(method="AI_SEMANTIC", status=ReviewDecision.AI_PENDING)]
        r = gate.check_screen_3_complete(items)
        assert not r.passed

    def test_ai_semantic_reviewed_passes(self):
        items = [make_recap_item(method="AI_SEMANTIC", status=ReviewDecision.APPROVED)]
        r = gate.check_screen_3_complete(items)
        assert r.passed

    def test_missing_unit_cost_blocks(self):
        items = [make_recap_item(status=ReviewDecision.APPROVED,
                                 unit_labor=0.0, unit_material=0.0, unit_equipment=0.0)]
        r = gate.check_screen_3_complete(items)
        assert not r.passed


# ============================================================
# RESIDUAL RISK GATE TESTS (Q3)
# ============================================================

class TestResidualRiskGate:
    def test_zero_risk_passes(self):
        result = gate.compute_residual_risk(PID, [], [], risk_threshold=50)
        assert result.gate_result == GateResult.PASS
        assert result.total_residual_risk == 0

    def test_high_risk_unreviewed_blocks(self):
        # 5 high-risk items unreviewed
        items = [make_takeoff_item(status=ReviewDecision.AI_PENDING, risk_weight=40)
                 for _ in range(5)]
        result = gate.compute_residual_risk(PID, items, [], risk_threshold=3)
        assert result.gate_result == GateResult.BLOCK
        assert result.unreviewed_high_risk_items == 5

    def test_low_risk_reviewed_passes(self):
        # All items reviewed, no conflicts
        items = [make_takeoff_item(status=ReviewDecision.APPROVED, risk_weight=0)
                 for _ in range(100)]
        result = gate.compute_residual_risk(PID, items, [], risk_threshold=50)
        assert result.gate_result == GateResult.PASS

    def test_diligent_estimator_passes_low_review_pct(self):
        # Estimator reviewed 15% but resolved all high-risk items
        # This is the key Q3 test: behavior (15% reviewed) doesn't block,
        # unresolved risk (0) passes
        approved = [make_takeoff_item(status=ReviewDecision.APPROVED, risk_weight=40)
                    for _ in range(15)]  # 15 high-risk reviewed
        pending_low = [make_takeoff_item(status=ReviewDecision.AI_PENDING, risk_weight=0)
                       for _ in range(85)]  # 85 low-risk pending
        result = gate.compute_residual_risk(PID, approved + pending_low, [],
                                            risk_threshold=50)
        assert result.gate_result == GateResult.PASS  # Low-risk pending doesn't block

    def test_warning_at_intermediate_risk(self):
        items = [make_takeoff_item(status=ReviewDecision.AI_PENDING, risk_weight=40)
                 for _ in range(4)]  # 4 high-risk unreviewed, threshold=3
        result = gate.compute_residual_risk(PID, items, [], risk_threshold=3)
        # 4 > 3 but 4 < 4.5 (threshold * 1.5) → WARNING
        assert result.gate_result == GateResult.WARNING

    def test_source_derived_coverage_gap_adds_to_risk(self):
        coverage = [make_coverage_item(
            confidence=OmissionConfidence.SOURCE_DERIVED,
            status=CoverageStatus.PENDING, blocking=True
        ) for _ in range(5)]
        result = gate.compute_residual_risk(PID, [], coverage, risk_threshold=3)
        assert result.unresolved_coverage_gaps == 5
        assert result.gate_result == GateResult.BLOCK


# ============================================================
# INTEGRITY ALERT TESTS (Q7)
# ============================================================

class TestIntegrityAlert:
    def _make_audit(self, is_conversion=True, artifact=False, crossing=True):
        return DecisionAuditRecord(
            record_id=str(uuid.uuid4()), project_id=PID,
            screen="screen_1", item_id=str(uuid.uuid4()),
            decision_type=ReviewDecision.ASSUME,
            previous_decision=ReviewDecision.CLARIFY if is_conversion else None,
            decided_by="est_user", decided_at="2026-06-16T23:00:00Z",
            session_id=SID, is_clarify_to_assume=is_conversion,
            decision_artifact_present=artifact,
            threshold_crossing=crossing,
        )

    def test_p1_fires_threshold_crossed_no_artifact(self):
        records = [self._make_audit(is_conversion=True, artifact=False, crossing=True)]
        alert = gate.check_integrity_alert(
            PID, records, score_before=72.0, score_after=76.0,
            submission_threshold=75.0, session_id=SID
        )
        assert alert is not None
        assert alert.level == IntegrityAlertLevel.P1_HIGH
        assert alert.routed_to_permission == "integrity_alert"

    def test_p1_not_fired_when_artifact_present(self):
        records = [self._make_audit(is_conversion=True, artifact=True, crossing=True)]
        alert = gate.check_integrity_alert(
            PID, records, score_before=72.0, score_after=76.0,
            submission_threshold=75.0, session_id=SID
        )
        # Threshold crossed but artifact present — P1 requires no artifact
        assert alert is None or alert.level != IntegrityAlertLevel.P1_HIGH

    def test_p2_fires_three_conversions_threshold_crossed(self):
        records = [self._make_audit(is_conversion=True, artifact=True, crossing=True)
                   for _ in range(3)]
        alert = gate.check_integrity_alert(
            PID, records, score_before=72.0, score_after=78.0,
            submission_threshold=75.0, session_id=SID
        )
        assert alert is not None
        assert alert.level == IntegrityAlertLevel.P2_PATTERN

    def test_no_alert_below_threshold(self):
        records = [self._make_audit(is_conversion=True, artifact=True, crossing=False)]
        alert = gate.check_integrity_alert(
            PID, records, score_before=60.0, score_after=65.0,
            submission_threshold=75.0, session_id=SID
        )
        assert alert is None

    def test_integrity_alert_never_routes_to_bid_review(self):
        records = [self._make_audit(is_conversion=True, artifact=False, crossing=True)]
        alert = gate.check_integrity_alert(
            PID, records, 72.0, 76.0, 75.0, SID
        )
        if alert:
            assert alert.routed_to_permission == "integrity_alert"
            assert alert.routed_to_permission != "bid_review"


# ============================================================
# BATCH APPROVAL TESTS (Q6)
# ============================================================

class TestBatchApproval:
    def test_valid_batch_passes(self):
        items = [make_takeoff_item(confidence="HIGH",
                                   confidence_source="schedule_matched")
                 for _ in range(10)]
        state = make_state(batch_count=0, ceiling=20, total=40)
        r = gate.validate_batch_approval(items, state,
                                          individually_reviewed_since_last_batch=0,
                                          prior_batch_size=0)
        assert r.passed

    def test_max_batch_size_exceeded_blocks(self):
        items = [make_takeoff_item() for _ in range(26)]
        state = make_state(batch_count=0, ceiling=100)
        r = gate.validate_batch_approval(items, state, config_max_batch_size=25)
        assert not r.passed

    def test_alternating_requirement_enforced(self):
        items = [make_takeoff_item() for _ in range(10)]
        state = make_state(batch_count=10, ceiling=50)
        # Prior batch was 25, only reviewed 5 since
        r = gate.validate_batch_approval(items, state,
                                          individually_reviewed_since_last_batch=5,
                                          prior_batch_size=25)
        assert not r.passed
        assert "25" in r.blocking_reason

    def test_alternating_requirement_met_passes(self):
        items = [make_takeoff_item() for _ in range(10)]
        state = make_state(batch_count=10, ceiling=50)
        r = gate.validate_batch_approval(items, state,
                                          individually_reviewed_since_last_batch=25,
                                          prior_batch_size=25)
        assert r.passed

    def test_session_ceiling_blocks(self):
        items = [make_takeoff_item() for _ in range(10)]
        state = make_state(batch_count=45, ceiling=50, total=100)
        # Would go to 55 — over 50 ceiling
        r = gate.validate_batch_approval(items, state,
                                          individually_reviewed_since_last_batch=25,
                                          prior_batch_size=25)
        assert not r.passed

    def test_cross_reference_item_ineligible(self):
        items = [make_takeoff_item(confidence="HIGH",
                                   confidence_source="cross_sheet_inference")]
        state = make_state(batch_count=0, ceiling=50)
        r = gate.validate_batch_approval(items, state)
        assert not r.passed

    def test_ai_semantic_item_ineligible(self):
        items = [make_takeoff_item(confidence="HIGH",
                                   confidence_source="ai_semantic")]
        state = make_state(batch_count=0, ceiling=50)
        r = gate.validate_batch_approval(items, state)
        assert not r.passed


# ============================================================
# STATE MACHINE TESTS
# ============================================================

class TestStateMachine:
    def test_screen_advance_updates_state(self):
        from precon.review_layer.gate_engine import GateCheckResult
        state = ProjectReviewState(project_id=PID)
        state.screen_1 = ScreenState.IN_PROGRESS
        result = GateCheckResult(passed=True)
        state = gate.advance_screen(state, "screen_1", result)
        assert state.screen_1 == ScreenState.COMPLETE
        assert state.screen_2 == ScreenState.IN_PROGRESS

    def test_failed_gate_does_not_advance(self):
        from precon.review_layer.gate_engine import GateCheckResult
        state = ProjectReviewState(project_id=PID)
        state.screen_1 = ScreenState.IN_PROGRESS
        result = GateCheckResult(passed=False, blocking_reason="Items pending")
        state = gate.advance_screen(state, "screen_1", result)
        assert state.screen_1 == ScreenState.IN_PROGRESS  # Unchanged

    def test_reopen_screen_1_locks_downstream(self):
        state = ProjectReviewState(project_id=PID)
        state.screen_1 = ScreenState.COMPLETE
        state.screen_2 = ScreenState.COMPLETE
        state.screen_2_5 = ScreenState.COMPLETE
        state.screen_3 = ScreenState.COMPLETE
        state, invalidated = gate.reopen_screen(state, "screen_1", "Addendum received", "pm_user")
        assert state.screen_1 == ScreenState.REOPENED
        assert state.screen_2 == ScreenState.LOCKED
        assert state.screen_2_5 == ScreenState.LOCKED
        assert state.screen_3 == ScreenState.LOCKED
        assert "screen_2" in invalidated
        assert "screen_3" in invalidated

    def test_reopen_screen_3_only_locks_a10(self):
        state = ProjectReviewState(project_id=PID)
        state.screen_1 = ScreenState.COMPLETE
        state.screen_2 = ScreenState.COMPLETE
        state.screen_2_5 = ScreenState.COMPLETE
        state.screen_3 = ScreenState.COMPLETE
        state.a10_complete = True
        state, invalidated = gate.reopen_screen(state, "screen_3", "Cost correction", "est_user")
        assert state.screen_3 == ScreenState.REOPENED
        assert state.screen_2 == ScreenState.COMPLETE  # Unchanged
        assert state.a10_complete is False


# ============================================================
# DATA MODEL VALIDATION TESTS
# ============================================================

class TestDataModels:
    def test_company_config_defaults(self):
        config = CompanyConfig(company_id="newco")
        assert config.vendor_quote_recency_days == 90
        assert config.vendor_award_geography_miles == 100.0
        assert config.batch_session_ceiling_pct == 0.50
        assert config.batch_attestation_required is True
        assert config.file_root_type == FileRootType.LOCAL_NETWORK

    def test_company_config_customizable(self):
        config = CompanyConfig(company_id="newco",
                               vendor_quote_recency_days=60,
                               vendor_award_geography_miles=150.0,
                               file_root_type=FileRootType.ONEDRIVE)
        assert config.vendor_quote_recency_days == 60
        assert config.vendor_award_geography_miles == 150.0
        assert config.file_root_type == FileRootType.ONEDRIVE

    def test_permissions_separable(self):
        config = CompanyConfig(company_id="trias")
        # integrity_alert and bid_review are separate keys
        assert "integrity_alert" in config.permissions
        assert "bid_review" in config.permissions
        assert config.permissions["integrity_alert"] != config.permissions["bid_review"]

    def test_bid_confidence_profiles_sum_to_one(self):
        for profile_name, weights in BID_CONFIDENCE_PROFILES.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001, f"{profile_name} weights sum to {total}"

    def test_all_building_types_have_profiles(self):
        expected = ["hospital", "military", "office", "retail",
                    "restaurant", "warehouse", "school", "government", "default"]
        for bt in expected:
            assert bt in BID_CONFIDENCE_PROFILES

    def test_unclassified_file_pending_by_default(self):
        f = UnclassifiedFile(
            file_id=str(uuid.uuid4()), project_id=PID,
            original_filename="Addendum_3.pdf", file_path="/staging/",
            file_size_bytes=1024000, received_at="2026-06-17T00:00:00Z",
            received_via="drag_drop", ai_classification="ADDENDUM",
            ai_confidence=0.72, ai_reasoning="filename contains Addendum",
            ai_suggested_project="MacdillAFB53",
            ai_suggested_path="/specs/addenda/",
        )
        assert f.status == ClassificationStatus.PENDING_REVIEW
        assert f.confirmed_classification == ""  # Not yet confirmed

    def test_risk_weight_factors_defined(self):
        assert "heuristic_quantity" in RISK_WEIGHT_FACTORS
        assert "explicit_schedule_quantity" in RISK_WEIGHT_FACTORS
        assert RISK_WEIGHT_FACTORS["explicit_schedule_quantity"] == 0
        assert RISK_WEIGHT_FACTORS["heuristic_quantity"] == 40

    def test_cross_doc_three_states(self):
        states = [CrossDocState.AGREE, CrossDocState.DISAGREE, CrossDocState.NO_SECOND_SOURCE]
        assert len(states) == 3
        # DISAGREE is a condition, not a score deduction
        assert CrossDocState.DISAGREE.value == "disagree"
        assert CrossDocState.NO_SECOND_SOURCE.value == "no_second_source"

    def test_assume_distinct_from_clarify(self):
        assert ReviewDecision.ASSUME != ReviewDecision.CLARIFY
        assume_item = make_interp_item(ReviewDecision.ASSUME,
                                        assumption_pricing_confirmed=True,
                                        assumption_text="Priced per A-501")
        clarify_item = make_interp_item(ReviewDecision.CLARIFY,
                                         sia_text="Subject to interpretation")
        assert assume_item.decision != clarify_item.decision
        assert assume_item.assumption_text != ""
        assert clarify_item.sia_text != ""


if __name__ == "__main__":
    import subprocess
    r = subprocess.run(["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
                       capture_output=True, text=True,
                       cwd="/var/lib/openclaw/.openclaw/workspace")
    print(r.stdout)
    if r.stderr:
        print(r.stderr[-500:])
