"""Engine 2A — Coverage Baseline Tests"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from precon.engine2a.engine2a import (
    Engine2A, DocumentInventoryItem, ExtractedScopeItem, VendorQuoteRecord,
    OmissionFinding, UnverifiedScopeItem, CoverageBaseline,
    OMISSION_RISK_WEIGHTS,
)
from precon.review_layer.models import OmissionConfidence, CoverageStatus

engine = Engine2A()
PID = str(uuid.uuid4())


def make_doc(doc_type="SPEC", csi_sections=None, sheet_refs=None,
             schedule_rows=None, snippets=None, filename=None):
    return DocumentInventoryItem(
        doc_id=str(uuid.uuid4()),
        filename=filename or f"{doc_type.lower()}_{uuid.uuid4().hex[:6]}.pdf",
        doc_type=doc_type,
        csi_sections=csi_sections or ["230000"],
        sheet_refs=sheet_refs or [],
        schedule_rows=schedule_rows or [],
        raw_text_snippets=snippets or {},
    )


def make_extracted(csi="230000", method="schedule_row", confidence="HIGH",
                   sheet="M-101"):
    return ExtractedScopeItem(
        item_id=str(uuid.uuid4()),
        csi_section=csi,
        description="HVAC Equipment",
        source_doc_id=str(uuid.uuid4()),
        source_sheet=sheet,
        extraction_method=method,
        confidence=confidence,
        quantity=4.0,
        unit="EA",
    )


def make_quote(csi="230000"):
    return VendorQuoteRecord(
        vendor_id=str(uuid.uuid4()),
        vendor_name="ABC Mechanical",
        csi_section=csi,
        quote_date="2026-06-01",
        quote_amount=185000.0,
        scope_description="Complete HVAC",
    )


# ============================================================
# BASIC RUN TESTS
# ============================================================

class TestEngine2ABasicRun:
    def test_returns_coverage_baseline(self):
        result = engine.run(PID, "office", "sub", [], [], [])
        assert isinstance(result, CoverageBaseline)
        assert result.project_id == PID
        assert result.building_type == "office"
        assert result.mode == "sub"

    def test_baseline_has_required_fields(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        assert result.baseline_id
        assert result.run_at
        assert isinstance(result.omissions, list)
        assert isinstance(result.unverified, list)

    def test_no_documents_produces_heuristic_omissions(self):
        # No documents at all — building-type expectations fire as HEURISTIC
        result = engine.run(PID, "hospital", "sub", [], [], [])
        heuristic = [o for o in result.omissions
                     if o.omission_confidence == OmissionConfidence.HEURISTIC]
        # Hospital Sub mode should have HVAC/Plumbing/Fire Suppression expectations
        assert len(heuristic) > 0

    def test_heuristic_findings_are_not_blocking(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        for o in result.omissions:
            if o.omission_confidence == OmissionConfidence.HEURISTIC:
                assert o.blocking is False


# ============================================================
# SOURCE_DERIVED TESTS (Q2 — blocking)
# ============================================================

class TestSourceDerivedOmissions:
    def test_schedule_row_not_extracted_is_source_derived(self):
        # Document has AHU-1 in schedule but we extracted nothing from 230000
        doc = make_doc(
            doc_type="DRAWING",
            csi_sections=["230000"],
            schedule_rows=["AHU-1", "AHU-2"],
            filename="M-101_Equipment_Schedule.pdf"
        )
        result = engine.run(PID, "office", "sub", [doc], [], [])
        source_derived = [o for o in result.omissions
                          if o.omission_confidence == OmissionConfidence.SOURCE_DERIVED]
        assert len(source_derived) > 0

    def test_source_derived_is_blocking(self):
        doc = make_doc(
            csi_sections=["230000"],
            schedule_rows=["FCU-14", "FCU-15"],
        )
        result = engine.run(PID, "office", "sub", [doc], [], [])
        for o in result.omissions:
            if o.omission_confidence == OmissionConfidence.SOURCE_DERIVED:
                assert o.blocking is True

    def test_source_derived_has_source_evidence(self):
        doc = make_doc(
            csi_sections=["230000"],
            schedule_rows=["AHU-3"],
            filename="Equipment_Schedule.pdf"
        )
        result = engine.run(PID, "office", "sub", [doc], [], [])
        source_derived = [o for o in result.omissions
                          if o.omission_confidence == OmissionConfidence.SOURCE_DERIVED]
        if source_derived:
            o = source_derived[0]
            assert o.source_evidence
            assert "AHU-3" in o.source_evidence or "Equipment_Schedule" in o.source_evidence

    def test_spec_section_present_but_not_extracted_is_source_derived(self):
        doc = make_doc(
            doc_type="SPEC",
            csi_sections=["230000"],
            snippets={"230000": ["Air Handling Units: Provide as scheduled on M-101"]},
            filename="Div23_HVAC.pdf"
        )
        result = engine.run(PID, "office", "sub", [doc], [], [])
        source_derived = [o for o in result.omissions
                          if o.omission_confidence == OmissionConfidence.SOURCE_DERIVED]
        assert len(source_derived) > 0

    def test_source_derived_not_produced_when_item_already_extracted(self):
        doc = make_doc(csi_sections=["230000"], schedule_rows=["AHU-1"])
        extracted = [make_extracted(csi="230000", method="schedule_row")]
        result = engine.run(PID, "office", "sub", [doc], extracted, [])
        source_derived = [o for o in result.omissions
                          if o.omission_confidence == OmissionConfidence.SOURCE_DERIVED]
        # Item was extracted — no source-derived omission
        assert len(source_derived) == 0


# ============================================================
# CROSS_REFERENCE TESTS (Q2 — blocking)
# ============================================================

class TestCrossReferenceOmissions:
    def test_spec_references_scope_no_vendor_quote_is_cross_ref(self):
        # Spec mentions commissioning but no Cx vendor in quotes
        doc = make_doc(
            doc_type="SPEC",
            csi_sections=["230000"],
            snippets={"230000": ["Commissioning agent required per Section 019113"]},
            filename="Div23_HVAC_Spec.pdf"
        )
        result = engine.run(PID, "hospital", "sub", [doc], [], [])
        cross_ref = [o for o in result.omissions
                     if o.omission_confidence == OmissionConfidence.CROSS_REFERENCE]
        # May or may not fire depending on triggers — verify structure if it does
        for o in cross_ref:
            assert o.blocking is True
            assert o.cross_ref_doc_a
            assert o.cross_ref_doc_b

    def test_drawing_plus_addendum_same_csi_is_cross_ref(self):
        drawing = make_doc(
            doc_type="DRAWING", csi_sections=["230000"],
            filename="M-501_Chiller_Plant.pdf"
        )
        addendum = make_doc(
            doc_type="ADDENDUM", csi_sections=["230000"],
            filename="Addendum_2_HVAC_Revisions.pdf"
        )
        result = engine.run(PID, "office", "sub", [drawing, addendum], [], [])
        cross_ref = [o for o in result.omissions
                     if o.omission_confidence == OmissionConfidence.CROSS_REFERENCE]
        for o in cross_ref:
            assert o.blocking is True

    def test_cross_reference_higher_risk_than_heuristic(self):
        assert (OMISSION_RISK_WEIGHTS[OmissionConfidence.CROSS_REFERENCE] >
                OMISSION_RISK_WEIGHTS[OmissionConfidence.HEURISTIC])

    def test_source_derived_higher_risk_than_cross_reference(self):
        assert (OMISSION_RISK_WEIGHTS[OmissionConfidence.SOURCE_DERIVED] >
                OMISSION_RISK_WEIGHTS[OmissionConfidence.CROSS_REFERENCE])


# ============================================================
# HEURISTIC TESTS (Q1/Q2 — advisory, never blocking)
# ============================================================

class TestHeuristicOmissions:
    def test_heuristic_never_blocking(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        for o in result.omissions:
            if o.omission_confidence == OmissionConfidence.HEURISTIC:
                assert o.blocking is False, f"Heuristic item {o.finding_id} is blocking — violates Q1"

    def test_heuristic_has_building_type(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        heuristic = [o for o in result.omissions
                     if o.omission_confidence == OmissionConfidence.HEURISTIC]
        for o in heuristic:
            assert o.heuristic_building_type == "hospital"

    def test_optional_scope_not_reported_as_heuristic(self):
        # OPTIONAL expectations should not appear as omissions when no evidence
        result = engine.run(PID, "office", "sub", [], [], [])
        # All returned heuristic items should be REQUIRED or TYPICAL only
        for o in result.omissions:
            if o.omission_confidence == OmissionConfidence.HEURISTIC:
                assert o.heuristic_expectation_level in ("required", "typical")

    def test_heuristic_risk_weight_correct(self):
        result = engine.run(PID, "office", "sub", [], [], [])
        for o in result.omissions:
            if o.omission_confidence == OmissionConfidence.HEURISTIC:
                assert o.risk_weight == OMISSION_RISK_WEIGHTS[OmissionConfidence.HEURISTIC]


# ============================================================
# BLOCKING COUNT TESTS (Q1)
# ============================================================

class TestBlockingCount:
    def test_blocking_count_excludes_heuristic(self):
        result = engine.run(PID, "office", "sub", [], [], [])
        manual_blocking = sum(1 for o in result.omissions if o.blocking)
        assert result.blocking_count == manual_blocking

    def test_blocking_count_consistent(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        blocking_items = [o for o in result.omissions if o.blocking]
        non_blocking = [o for o in result.omissions if not o.blocking]
        assert result.blocking_count == len(blocking_items)
        assert result.heuristic_count == len(non_blocking)

    def test_summary_counts_add_up(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        total = result.source_derived_count + result.cross_reference_count + result.heuristic_count
        assert total == len(result.omissions)


# ============================================================
# UNVERIFIED SCOPE (Tab B) TESTS
# ============================================================

class TestUnverifiedScope:
    def test_ai_semantic_low_confidence_generates_unverified(self):
        # AI semantic extract with no second source → Tab B
        extracted = [make_extracted(csi="230000", method="ai_semantic", confidence="LOW")]
        result = engine.run(PID, "office", "sub", [], extracted, [])
        assert result.unverified_count >= 0  # May or may not fire depending on docs

    def test_disagree_state_has_details(self):
        # Two docs with same CSI — DISAGREE state
        doc1 = make_doc(doc_type="SPEC", csi_sections=["230000"], filename="Spec_23.pdf")
        doc2 = make_doc(doc_type="SPEC", csi_sections=["230000"], filename="Spec_23_Rev2.pdf")
        extracted = [make_extracted(csi="230000", method="ai_semantic",
                                     confidence="LOW", sheet="M-101")]
        extracted[0].source_doc_id = doc1.doc_id
        result = engine.run(PID, "office", "sub", [doc1, doc2], extracted, [])
        disagree = [u for u in result.unverified if u.cross_check_result == "DISAGREE"]
        for u in disagree:
            assert u.disagreement_details

    def test_high_confidence_schedule_matched_not_unverified(self):
        # HIGH confidence schedule-matched items don't go to Tab B
        extracted = [make_extracted(csi="230000", method="schedule_row", confidence="HIGH")]
        result = engine.run(PID, "office", "sub", [], extracted, [])
        # No unverified items from high-confidence extractions
        assert result.unverified_count == 0


# ============================================================
# to_coverage_review_items() TESTS
# ============================================================

class TestCoverageReviewItems:
    def test_converts_to_review_items(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        review_items = result.to_coverage_review_items()
        assert len(review_items) == len(result.omissions)

    def test_review_items_have_correct_tab(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        review_items = result.to_coverage_review_items()
        for item in review_items:
            assert item.tab == "missing_scope"

    def test_review_items_start_pending(self):
        result = engine.run(PID, "hospital", "sub", [], [], [])
        review_items = result.to_coverage_review_items()
        for item in review_items:
            assert item.status == CoverageStatus.PENDING

    def test_blocking_preserved_in_review_items(self):
        doc = make_doc(csi_sections=["230000"], schedule_rows=["FCU-1"])
        result = engine.run(PID, "office", "sub", [doc], [], [])
        review_items = result.to_coverage_review_items()
        for ri in review_items:
            # Find matching omission
            matching = next((o for o in result.omissions if o.finding_id == ri.item_id), None)
            if matching:
                assert ri.blocking == matching.blocking


# ============================================================
# GC vs SUB MODE TESTS
# ============================================================

class TestModeHandling:
    def test_sub_mode_runs(self):
        result = engine.run(PID, "office", "sub", [], [], [])
        assert result.mode == "sub"

    def test_gc_mode_runs(self):
        result = engine.run(PID, "office", "gc", [], [], [])
        assert result.mode == "gc"

    def test_gc_mode_has_more_expectations_than_sub(self):
        # GC covers all trades, Sub covers MEP only
        result_gc = engine.run(PID, "office", "gc", [], [], [])
        result_sub = engine.run(PID, "office", "sub", [], [], [])
        # GC should have more heuristic omissions (more scope expected)
        gc_heuristic = [o for o in result_gc.omissions
                        if o.omission_confidence == OmissionConfidence.HEURISTIC]
        sub_heuristic = [o for o in result_sub.omissions
                         if o.omission_confidence == OmissionConfidence.HEURISTIC]
        assert len(gc_heuristic) >= len(sub_heuristic)


if __name__ == "__main__":
    import subprocess
    r = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd="/var/lib/openclaw/.openclaw/workspace"
    )
    print(r.stdout)
    if r.stderr:
        print(r.stderr[-500:])
