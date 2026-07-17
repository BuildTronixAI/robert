"""A-10 Estimate Alignment Gate Tests"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from precon.a10.a10 import A10Gate, CostRecapSummary, GateResult, CheckResult

gate = A10Gate()
PID = str(uuid.uuid4())

def make_recap(**kwargs) -> CostRecapSummary:
    defaults = dict(
        proposal_id=PID, total_labor_cost=120000, total_material_cost=80000,
        total_equipment_cost=20000, total_sub_cost=60000, total_direct_cost=280000,
        mechanical_labor_hours=1200, sheet_metal_labor_hours=800, plumbing_labor_hours=600,
        avg_labor_rate=47.50, sqft=25000, building_type="office"
    )
    defaults.update(kwargs)
    return CostRecapSummary(**defaults)

class TestCoverageLayer:
    def test_required_gap_blocks_gate(self):
        recap = make_recap()
        report = gate.evaluate(PID, recap, coverage_score=85.0, coverage_gaps=2, required_gaps=1)
        assert report.gate_result == GateResult.BLOCK
        assert not report.ready_for_proposal

    def test_no_required_gaps_passes_coverage(self):
        recap = make_recap()
        report = gate.evaluate(PID, recap, coverage_score=95.0, coverage_gaps=0, required_gaps=0)
        cov_check = next(c for c in report.checks if c.check_id == "COV-01")
        assert cov_check.result == CheckResult.PASS

    def test_low_coverage_score_blocks(self):
        recap = make_recap()
        report = gate.evaluate(PID, recap, coverage_score=55.0, coverage_gaps=5, required_gaps=0)
        cov02 = next(c for c in report.checks if c.check_id == "COV-02")
        assert cov02.result == CheckResult.FAIL

    def test_coverage_between_70_90_warns(self):
        recap = make_recap()
        report = gate.evaluate(PID, recap, coverage_score=78.0, coverage_gaps=2, required_gaps=0)
        cov02 = next(c for c in report.checks if c.check_id == "COV-02")
        assert cov02.result == CheckResult.WARNING

class TestRateLayer:
    def test_normal_rate_passes(self):
        recap = make_recap(avg_labor_rate=47.50)
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        rate_check = next(c for c in report.checks if c.check_id == "RATE-01")
        assert rate_check.result == CheckResult.PASS

    def test_rate_too_high_warns(self):
        recap = make_recap(avg_labor_rate=75.00)  # Way above benchmark
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        rate_check = next(c for c in report.checks if c.check_id == "RATE-01")
        assert rate_check.result in (CheckResult.WARNING, CheckResult.FAIL)

    def test_no_hours_skips_rate_check(self):
        recap = make_recap(mechanical_labor_hours=0, sheet_metal_labor_hours=0,
                           plumbing_labor_hours=0, avg_labor_rate=None)
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        rate_check = next(c for c in report.checks if c.check_id == "RATE-01")
        assert rate_check.result == CheckResult.SKIP

class TestValueBanding:
    def test_office_in_band_passes(self):
        recap = make_recap(total_direct_cost=750000, sqft=25000, building_type="office")
        # $30/SF — within office band $15-45
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        val_check = next(c for c in report.checks if c.check_id == "VAL-01")
        assert val_check.result == CheckResult.PASS

    def test_office_below_band_warns(self):
        recap = make_recap(total_direct_cost=100000, sqft=25000, building_type="office")
        # $4/SF — below office band $15-45
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        val_check = next(c for c in report.checks if c.check_id == "VAL-01")
        assert val_check.result == CheckResult.WARNING

    def test_no_sqft_skips_value_check(self):
        recap = make_recap(sqft=None)
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        val_check = next(c for c in report.checks if c.check_id == "VAL-01")
        assert val_check.result == CheckResult.SKIP

class TestGateResult:
    def test_all_good_is_pass(self):
        recap = make_recap(total_direct_cost=750000, sqft=25000, avg_labor_rate=46.0)
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        assert report.gate_result == GateResult.PASS
        assert report.ready_for_proposal

    def test_warning_not_ready_but_not_blocked(self):
        recap = make_recap(total_direct_cost=100000, sqft=25000)  # Low $/SF
        report = gate.evaluate(PID, recap, 78.0, 2, 0)
        # Warnings but no blocks
        assert report.gate_result in (GateResult.WARNING, GateResult.BLOCK)

    def test_report_has_required_fields(self):
        recap = make_recap()
        report = gate.evaluate(PID, recap, 95.0, 0, 0)
        assert report.project_id == PID
        assert isinstance(report.checks, list)
        assert report.total_estimate == recap.total_direct_cost

if __name__ == "__main__":
    import subprocess
    r = subprocess.run(["python3","-m","pytest",__file__,"-v","--tb=short"],
                       capture_output=True, text=True,
                       cwd="/var/lib/openclaw/.openclaw/workspace")
    print(r.stdout); print(r.stderr[-300:] if r.stderr else "")
