"""Engine 2B — Coverage Validation Tests"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from precon.engine2b.engine2b import (
    Engine2B, ApprovedTakeoffItem, ResolvedCoverageItem, ValidationResult, ValidationGap,
)
from precon.engine2a.engine2a import OmissionFinding, CoverageBaseline
from precon.review_layer.models import OmissionConfidence, GateResult

engine = Engine2B()
PID = str(uuid.uuid4())


def make_baseline(omissions=None):
    return CoverageBaseline(
        baseline_id=str(uuid.uuid4()), project_id=PID,
        building_type="office", mode="sub", run_at="2026-06-17T00:00:00Z",
        omissions=omissions or [], unverified=[],
        source_derived_count=0, cross_reference_count=0,
        heuristic_count=0, blocking_count=0, unverified_count=0,
        document_coverage_score=80.0, heuristic_coverage_score=75.0,
    )


def make_omission(confidence=OmissionConfidence.SOURCE_DERIVED,
                  csi="230000", blocking=True):
    fid = str(uuid.uuid4())
    return OmissionFinding(
        finding_id=fid, project_id=PID, csi_section=csi,
        description=f"Test omission {csi}",
        omission_confidence=confidence, blocking=blocking,
        source_evidence="Test evidence", estimated_value=45000.0,
        risk_weight=40 if blocking else 15,
    )


def make_takeoff_item(csi="230000", total=85000.0):
    return ApprovedTakeoffItem(
        item_id=str(uuid.uuid4()), csi_section=csi,
        description="HVAC Equipment", confirmed_cost_code="110",
        quantity=4.0, unit="EA",
        unit_labor=5000.0, unit_material=16250.0, unit_equipment=0.0,
        total_cost=total, source_sheet="M-101",
        screen2_decision="APPROVED", screen3_decision="APPROVED",
    )


def make_resolution(finding_id, resolution="ADDED", csi="230000",
                    confidence=OmissionConfidence.SOURCE_DERIVED):
    return ResolvedCoverageItem(
        finding_id=finding_id, csi_section=csi, resolution=resolution,
        omission_confidence=confidence,
        resolved_by="est_user", resolved_at="2026-06-17T00:30:00Z",
    )


# ============================================================
# BASIC GATE TESTS
# ============================================================

class TestEngine2BGateBasics:
    def test_empty_baseline_passes(self):
        result = engine.run(PID, make_baseline(), [], [])
        assert result.gate_result == GateResult.PASS
        assert result.is_passing()

    def test_source_derived_unresolved_blocks(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        baseline = make_baseline([omission])
        result = engine.run(PID, baseline, [], [])
        assert result.gate_result == GateResult.BLOCK
        assert result.is_blocked()
        assert result.blocking_gap_count == 1

    def test_cross_reference_unresolved_blocks(self):
        omission = make_omission(OmissionConfidence.CROSS_REFERENCE, blocking=True)
        baseline = make_baseline([omission])
        result = engine.run(PID, baseline, [], [])
        assert result.gate_result == GateResult.BLOCK

    def test_heuristic_unresolved_is_warning_not_block(self):
        omission = make_omission(OmissionConfidence.HEURISTIC, blocking=False)
        baseline = make_baseline([omission])
        result = engine.run(PID, baseline, [], [])
        assert result.gate_result == GateResult.WARNING
        assert result.is_warning()
        assert not result.is_blocked()

    def test_all_resolved_passes(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        baseline = make_baseline([omission])
        resolution = make_resolution(omission.finding_id, "EXCLUDED")
        result = engine.run(PID, baseline, [], [resolution])
        assert result.gate_result == GateResult.PASS

    def test_blocking_reason_populated_on_block(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        baseline = make_baseline([omission])
        result = engine.run(PID, baseline, [], [])
        assert result.blocking_reason
        assert "SOURCE_DERIVED" in result.blocking_reason or "unresolved" in result.blocking_reason

    def test_warning_reason_populated_on_warning(self):
        omission = make_omission(OmissionConfidence.HEURISTIC, blocking=False)
        baseline = make_baseline([omission])
        result = engine.run(PID, baseline, [], [])
        assert result.warning_reason
        assert "heuristic" in result.warning_reason.lower() or "advisory" in result.warning_reason.lower()


# ============================================================
# RESOLUTION HANDLING TESTS
# ============================================================

class TestResolutionHandling:
    def test_excluded_resolution_removes_gap(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        baseline = make_baseline([omission])
        resolution = make_resolution(omission.finding_id, "EXCLUDED")
        result = engine.run(PID, baseline, [], [resolution])
        assert result.blocking_gap_count == 0

    def test_dismissed_resolution_removes_gap(self):
        omission = make_omission(OmissionConfidence.HEURISTIC, blocking=False)
        baseline = make_baseline([omission])
        resolution = make_resolution(omission.finding_id, "DISMISSED",
                                      confidence=OmissionConfidence.HEURISTIC)
        result = engine.run(PID, baseline, [], [resolution])
        assert result.advisory_gap_count == 0

    def test_added_resolution_with_item_in_takeoff_passes(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED,
                                  csi="230000", blocking=True)
        baseline = make_baseline([omission])
        resolution = make_resolution(omission.finding_id, "ADDED", csi="230000")
        takeoff = [make_takeoff_item(csi="230000")]  # Item IS in takeoff
        result = engine.run(PID, baseline, takeoff, [resolution])
        assert result.blocking_gap_count == 0
        assert result.gate_result == GateResult.PASS

    def test_added_resolution_without_item_in_takeoff_is_gap(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED,
                                  csi="230000", blocking=True)
        baseline = make_baseline([omission])
        resolution = make_resolution(omission.finding_id, "ADDED", csi="230000")
        # No takeoff item for 230000 — inconsistency
        result = engine.run(PID, baseline, [], [resolution])
        assert result.blocking_gap_count == 1
        assert result.blocking_gaps[0].reason_unresolved
        assert "ADDED" in result.blocking_gaps[0].reason_unresolved

    def test_unresolved_omission_covered_by_takeoff_passes(self):
        # No explicit Screen 2.5 resolution, but CSI is in approved takeoff
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED,
                                  csi="230000", blocking=True)
        baseline = make_baseline([omission])
        takeoff = [make_takeoff_item(csi="230000")]
        result = engine.run(PID, baseline, takeoff, [])
        assert result.blocking_gap_count == 0
        assert result.gate_result == GateResult.PASS


# ============================================================
# MIXED SCENARIO TESTS
# ============================================================

class TestMixedScenarios:
    def test_multiple_omissions_all_resolved_passes(self):
        o1 = make_omission(OmissionConfidence.SOURCE_DERIVED, csi="230000", blocking=True)
        o2 = make_omission(OmissionConfidence.CROSS_REFERENCE, csi="220000", blocking=True)
        o3 = make_omission(OmissionConfidence.HEURISTIC, csi="210000", blocking=False)
        baseline = make_baseline([o1, o2, o3])
        resolutions = [
            make_resolution(o1.finding_id, "EXCLUDED", csi="230000"),
            make_resolution(o2.finding_id, "ADDED", csi="220000"),
            make_resolution(o3.finding_id, "DISMISSED", csi="210000",
                            confidence=OmissionConfidence.HEURISTIC),
        ]
        takeoff = [make_takeoff_item(csi="220000")]  # o2 ADDED and in takeoff
        result = engine.run(PID, baseline, takeoff, resolutions)
        assert result.gate_result == GateResult.PASS

    def test_blocking_takes_priority_over_warning(self):
        o1 = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        o2 = make_omission(OmissionConfidence.HEURISTIC, csi="210000", blocking=False)
        baseline = make_baseline([o1, o2])
        # Only heuristic resolved
        resolution = make_resolution(o2.finding_id, "DISMISSED", csi="210000",
                                      confidence=OmissionConfidence.HEURISTIC)
        result = engine.run(PID, baseline, [], [resolution])
        # SOURCE_DERIVED still unresolved → BLOCK (not WARNING)
        assert result.gate_result == GateResult.BLOCK

    def test_approved_csi_sections_populated(self):
        takeoff = [
            make_takeoff_item(csi="230000"),
            make_takeoff_item(csi="220000"),
        ]
        result = engine.run(PID, make_baseline(), takeoff, [])
        assert any("2300" in s for s in result.approved_csi_sections)
        assert any("2200" in s for s in result.approved_csi_sections)

    def test_total_approved_value_computed(self):
        takeoff = [
            make_takeoff_item(csi="230000", total=85000.0),
            make_takeoff_item(csi="220000", total=42000.0),
        ]
        result = engine.run(PID, make_baseline(), takeoff, [])
        assert abs(result.total_approved_value - 127000.0) < 0.01

    def test_gap_has_original_finding_id(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        baseline = make_baseline([omission])
        result = engine.run(PID, baseline, [], [])
        assert result.blocking_gaps[0].original_finding_id == omission.finding_id


# ============================================================
# INTERFACE TESTS
# ============================================================

class TestValidationResultInterface:
    def test_is_blocked_true_on_block(self):
        omission = make_omission(OmissionConfidence.SOURCE_DERIVED, blocking=True)
        result = engine.run(PID, make_baseline([omission]), [], [])
        assert result.is_blocked() is True
        assert result.is_warning() is False
        assert result.is_passing() is False

    def test_is_warning_true_on_warning(self):
        omission = make_omission(OmissionConfidence.HEURISTIC, blocking=False)
        result = engine.run(PID, make_baseline([omission]), [], [])
        assert result.is_warning() is True
        assert result.is_blocked() is False
        assert result.is_passing() is False

    def test_is_passing_true_on_pass(self):
        result = engine.run(PID, make_baseline(), [], [])
        assert result.is_passing() is True
        assert result.is_blocked() is False
        assert result.is_warning() is False

    def test_validation_result_has_id_and_timestamp(self):
        result = engine.run(PID, make_baseline(), [], [])
        assert result.validation_id
        assert result.run_at


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
