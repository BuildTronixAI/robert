"""Bid Confidence Calculator Tests — 4 vectors, Q3/Q8 schema decisions"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from precon.bid_confidence.bid_confidence import (
    BidConfidenceCalculator, ReviewIntegrityInput, PricingReliabilityInput,
    BidConfidenceScore, VectorScore,
)
from precon.engine2a.engine2a import CoverageBaseline
from precon.engine2b.engine2b import ValidationResult
from precon.review_layer.models import (
    TakeoffReviewItem, ReviewDecision, CrossDocState, VendorQualityRecord,
    QuantityReliabilityScore, GateResult, BID_CONFIDENCE_PROFILES,
)

calc = BidConfidenceCalculator()
PID = str(uuid.uuid4())


def make_baseline(doc_coverage=85.0):
    return CoverageBaseline(
        baseline_id=str(uuid.uuid4()), project_id=PID,
        building_type="office", mode="sub", run_at="2026-06-17T00:00:00Z",
        omissions=[], unverified=[],
        source_derived_count=0, cross_reference_count=0,
        heuristic_count=0, blocking_count=0, unverified_count=0,
        document_coverage_score=doc_coverage, heuristic_coverage_score=75.0,
    )


def make_validation(gate=GateResult.PASS, blocking=0, advisory=0):
    return ValidationResult(
        validation_id=str(uuid.uuid4()), project_id=PID,
        run_at="2026-06-17T00:00:00Z", gate_result=gate,
        blocking_gaps=[], advisory_gaps=[],
        approved_csi_sections=["230000"], total_approved_value=185000.0,
        blocking_gap_count=blocking, advisory_gap_count=advisory,
    )


def make_takeoff_item(cross_doc=CrossDocState.AGREE, risk_weight=10,
                      reliability=90.0, status=ReviewDecision.APPROVED):
    qr = QuantityReliabilityScore(
        item_id=str(uuid.uuid4()), source_quality_score=0.9,
        cross_doc_state=cross_doc, cross_doc_score=1.0 if cross_doc == CrossDocState.AGREE else 0.5,
        quantity_provenance="explicit", provenance_score=1.0,
        risk_weight=risk_weight, item_reliability_score=reliability,
    )
    return TakeoffReviewItem(
        item_id=str(uuid.uuid4()), project_id=PID, area="Level 1",
        discipline="Mechanical", description="FCU", source_sheet="M-101",
        csi_section="230000", ai_quantity=4.0, ai_unit="EA",
        ai_confidence="HIGH", ai_confidence_source="schedule_matched",
        ai_reasoning="Test", display_cost_code="110",
        display_cost_code_confidence="EXACT_RULE",
        quantity_reliability=qr, status=status,
    )


def make_review_integrity(high_risk=10, reviewed=10, corrections=2,
                           conflicts=0, unresolved=0):
    return ReviewIntegrityInput(
        total_items=20, high_risk_items=high_risk,
        high_risk_reviewed=reviewed, verified_corrections=corrections,
        unresolved_conflicts=unresolved, total_conflicts=conflicts,
    )


def make_vendor(tier=3, tier_weight=0.75):
    return VendorQualityRecord(
        record_id=str(uuid.uuid4()), project_id=PID,
        csi_section="230000", vendor_id=str(uuid.uuid4()),
        vendor_name="ABC Mechanical", tier=tier,
        tier_label="Active", tier_weight=tier_weight,
        quality_score=tier_weight,
    )


def make_pricing(tier=3, tier_weight=None, covered=3, total=3, labor_conf="HIGH"):
    tw = tier_weight if tier_weight is not None else tier * 0.25
    return PricingReliabilityInput(
        vendor_quality_records=[make_vendor(tier=tier, tier_weight=tw)],
        covered_csi_sections=covered, total_csi_sections=total,
        labor_factor_source="historical", labor_factor_confidence=labor_conf,
    )


def run_default(building_type="office", doc_coverage=85.0, blocking=0, advisory=0,
                high_risk=10, reviewed=10, corrections=2):
    return calc.compute(
        project_id=PID,
        building_type=building_type,
        coverage_baseline=make_baseline(doc_coverage),
        validation_result=make_validation(blocking=blocking, advisory=advisory),
        takeoff_items=[make_takeoff_item() for _ in range(5)],
        review_integrity=make_review_integrity(high_risk=high_risk, reviewed=reviewed,
                                                corrections=corrections),
        pricing_input=make_pricing(),
    )


# ============================================================
# COMPOSITE SCORE TESTS
# ============================================================

class TestCompositeScore:
    def test_returns_bid_confidence_score(self):
        result = run_default()
        assert isinstance(result, BidConfidenceScore)

    def test_composite_in_range(self):
        result = run_default()
        assert 0.0 <= result.composite_score <= 100.0

    def test_high_quality_bid_scores_high(self):
        result = run_default(doc_coverage=95.0)
        assert result.composite_score >= 70.0

    def test_blocking_gaps_lower_score(self):
        good = run_default(blocking=0)
        bad = run_default(blocking=3)
        assert good.composite_score > bad.composite_score

    def test_submittable_above_threshold(self):
        result = calc.compute(
            PID, "office", make_baseline(95.0), make_validation(),
            [make_takeoff_item() for _ in range(5)],
            make_review_integrity(), make_pricing(),
            submission_threshold=70.0,
        )
        if result.composite_score >= 70.0:
            assert result.submittable is True

    def test_not_submittable_below_threshold(self):
        result = calc.compute(
            PID, "office", make_baseline(20.0),
            make_validation(blocking=5),
            [], make_review_integrity(high_risk=10, reviewed=0),
            make_pricing(tier=0, tier_weight=0.0, labor_conf="LOW"),
            submission_threshold=70.0,
        )
        assert result.submittable is False

    def test_confidence_tier_high(self):
        result = run_default(doc_coverage=95.0)
        if result.composite_score >= 80:
            assert result.confidence_tier == "HIGH"

    def test_confidence_tier_low(self):
        result = calc.compute(
            PID, "office", make_baseline(30.0),
            make_validation(blocking=3),
            [], make_review_integrity(high_risk=5, reviewed=0),
            make_pricing(tier=0, tier_weight=0.0, labor_conf="LOW"),
        )
        if result.composite_score < 60:
            assert result.confidence_tier == "LOW"


# ============================================================
# COVERAGE VECTOR TESTS
# ============================================================

class TestCoverageVector:
    def test_zero_blocking_gaps_scores_well(self):
        result = run_default(doc_coverage=90.0, blocking=0)
        assert result.coverage_vector.raw_score > 80.0

    def test_blocking_gaps_penalize_coverage(self):
        no_gaps = run_default(blocking=0, doc_coverage=85.0)
        with_gaps = run_default(blocking=2, doc_coverage=85.0)
        assert no_gaps.coverage_vector.raw_score > with_gaps.coverage_vector.raw_score

    def test_components_populated(self):
        result = run_default()
        c = result.coverage_vector.components
        assert "document_coverage_base" in c
        assert "blocking_gap_penalty" in c
        assert "zero_gap_bonus" in c

    def test_weight_applied_correctly(self):
        result = run_default(building_type="office")
        w = result.weights_used["coverage_reliability"]
        expected = result.coverage_vector.raw_score * w
        assert abs(result.coverage_vector.weighted_score - expected) < 0.1


# ============================================================
# QUANTITY VECTOR TESTS (Q3)
# ============================================================

class TestQuantityVector:
    def test_agree_items_score_higher_than_no_second_source(self):
        agree_items = [make_takeoff_item(CrossDocState.AGREE) for _ in range(5)]
        nss_items = [make_takeoff_item(CrossDocState.NO_SECOND_SOURCE) for _ in range(5)]

        r_agree = calc.compute(PID, "office", make_baseline(), make_validation(),
                                agree_items, make_review_integrity(), make_pricing())
        r_nss = calc.compute(PID, "office", make_baseline(), make_validation(),
                              nss_items, make_review_integrity(), make_pricing())
        assert r_agree.quantity_vector.raw_score >= r_nss.quantity_vector.raw_score

    def test_disagree_items_penalize_quantity_score(self):
        agree_items = [make_takeoff_item(CrossDocState.AGREE) for _ in range(5)]
        disagree_items = [make_takeoff_item(CrossDocState.DISAGREE) for _ in range(5)]

        r_agree = calc.compute(PID, "office", make_baseline(), make_validation(),
                                agree_items, make_review_integrity(), make_pricing())
        r_disagree = calc.compute(PID, "office", make_baseline(), make_validation(),
                                   disagree_items, make_review_integrity(), make_pricing())
        assert r_agree.quantity_vector.raw_score > r_disagree.quantity_vector.raw_score

    def test_no_second_source_is_neutral_not_penalty(self):
        # NO_SECOND_SOURCE should score between AGREE and DISAGREE
        agree_items = [make_takeoff_item(CrossDocState.AGREE) for _ in range(5)]
        nss_items = [make_takeoff_item(CrossDocState.NO_SECOND_SOURCE) for _ in range(5)]
        disagree_items = [make_takeoff_item(CrossDocState.DISAGREE) for _ in range(5)]

        def score(items):
            return calc.compute(PID, "office", make_baseline(), make_validation(),
                                items, make_review_integrity(), make_pricing()
                                ).quantity_vector.raw_score

        assert score(agree_items) >= score(nss_items) >= score(disagree_items)

    def test_empty_takeoff_returns_fifty(self):
        result = calc.compute(PID, "office", make_baseline(), make_validation(),
                               [], make_review_integrity(), make_pricing())
        assert result.quantity_vector.raw_score == 50.0

    def test_components_include_cross_doc_counts(self):
        result = run_default()
        c = result.quantity_vector.components
        assert "agree_count" in c
        assert "disagree_count" in c
        assert "no_second_source_count" in c


# ============================================================
# REVIEW INTEGRITY VECTOR TESTS (Q3)
# ============================================================

class TestReviewIntegrityVector:
    def test_100pct_high_risk_reviewed_scores_high(self):
        ri = make_review_integrity(high_risk=10, reviewed=10, corrections=3)
        result = calc.compute(PID, "office", make_baseline(), make_validation(),
                               [], ri, make_pricing())
        assert result.review_integrity_vector.raw_score >= 80.0

    def test_zero_high_risk_reviewed_scores_low(self):
        ri = make_review_integrity(high_risk=10, reviewed=0, corrections=0)
        result = calc.compute(PID, "office", make_baseline(), make_validation(),
                               [], ri, make_pricing())
        assert result.review_integrity_vector.raw_score < 20.0

    def test_no_high_risk_items_scores_high(self):
        # No high-risk items = risk coverage = 1.0 = good score
        ri = make_review_integrity(high_risk=0, reviewed=0, corrections=0)
        result = calc.compute(PID, "office", make_baseline(), make_validation(),
                               [], ri, make_pricing())
        assert result.review_integrity_vector.raw_score >= 80.0

    def test_corrections_add_bonus(self):
        ri_no_corrections = make_review_integrity(reviewed=10, corrections=0)
        ri_with_corrections = make_review_integrity(reviewed=10, corrections=5)
        r1 = calc.compute(PID, "office", make_baseline(), make_validation(),
                           [], ri_no_corrections, make_pricing())
        r2 = calc.compute(PID, "office", make_baseline(), make_validation(),
                           [], ri_with_corrections, make_pricing())
        assert r2.review_integrity_vector.raw_score > r1.review_integrity_vector.raw_score

    def test_review_integrity_note_confirms_no_pct_total(self):
        result = run_default()
        note = result.review_integrity_vector.components.get("note", "")
        assert "Risk-weighted" in note or "risk" in note.lower()

    def test_unresolved_conflicts_penalize(self):
        ri_clean = make_review_integrity(conflicts=5, unresolved=0)
        ri_dirty = make_review_integrity(conflicts=5, unresolved=5)
        r1 = calc.compute(PID, "office", make_baseline(), make_validation(),
                           [], ri_clean, make_pricing())
        r2 = calc.compute(PID, "office", make_baseline(), make_validation(),
                           [], ri_dirty, make_pricing())
        assert r1.review_integrity_vector.raw_score > r2.review_integrity_vector.raw_score


# ============================================================
# PRICING VECTOR TESTS (Q4/Q8)
# ============================================================

class TestPricingVector:
    def test_tier4_vendors_score_highest(self):
        pricing = make_pricing(tier=4, tier_weight=1.0, labor_conf="HIGH")
        result = calc.compute(PID, "office", make_baseline(), make_validation(),
                               [], make_review_integrity(), pricing)
        assert result.pricing_vector.raw_score >= 90.0

    def test_tier0_no_vendor_scores_lowest(self):
        pricing = PricingReliabilityInput(
            vendor_quality_records=[make_vendor(tier=0, tier_weight=0.0)],
            covered_csi_sections=0, total_csi_sections=5,
            labor_factor_source="estimated", labor_factor_confidence="LOW",
        )
        result = calc.compute(PID, "office", make_baseline(), make_validation(),
                               [], make_review_integrity(), pricing)
        assert result.pricing_vector.raw_score < 30.0

    def test_tier_distribution_in_components(self):
        result = run_default()
        assert "vendor_tier_distribution" in result.pricing_vector.components

    def test_labor_confidence_high_beats_low(self):
        p_high = make_pricing(labor_conf="HIGH")
        p_low = make_pricing(labor_conf="LOW")
        r1 = calc.compute(PID, "office", make_baseline(), make_validation(),
                           [], make_review_integrity(), p_high)
        r2 = calc.compute(PID, "office", make_baseline(), make_validation(),
                           [], make_review_integrity(), p_low)
        assert r1.pricing_vector.raw_score > r2.pricing_vector.raw_score


# ============================================================
# PROJECT TYPE TEMPLATE TESTS (Q8)
# ============================================================

class TestProjectTypeTemplates:
    def test_all_profiles_available(self):
        for bt in ["hospital", "military", "office", "retail",
                   "restaurant", "warehouse", "school", "government"]:
            result = run_default(building_type=bt)
            assert result.profile_used == bt

    def test_hospital_weights_coverage_more(self):
        hospital_w = BID_CONFIDENCE_PROFILES["hospital"]["coverage_reliability"]
        office_w = BID_CONFIDENCE_PROFILES["office"]["coverage_reliability"]
        assert hospital_w > office_w  # Hospital needs better coverage confidence

    def test_weight_override_uses_custom(self):
        custom = {
            "coverage_reliability": 0.25,
            "quantity_reliability": 0.25,
            "review_integrity": 0.25,
            "pricing_reliability": 0.25,
        }
        result = calc.compute(
            PID, "office", make_baseline(), make_validation(),
            [make_takeoff_item()], make_review_integrity(), make_pricing(),
            weight_override=custom,
        )
        assert result.profile_used == "custom"
        assert result.weights_used == custom

    def test_weights_sum_to_one_for_all_profiles(self):
        for name, weights in BID_CONFIDENCE_PROFILES.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001


# ============================================================
# SUMMARY STRING TEST
# ============================================================

class TestSummaryString:
    def test_summary_contains_all_vectors(self):
        result = run_default()
        s = result.summary()
        assert "Bid Confidence:" in s
        assert "Coverage:" in s
        assert "Quantity:" in s
        assert "Review:" in s
        assert "Pricing:" in s


if __name__ == "__main__":
    import subprocess
    r = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd="/var/lib/openclaw/.openclaw/workspace"
    )
    print(r.stdout)
    if r.stderr:
        print(r.stderr[-300:])
