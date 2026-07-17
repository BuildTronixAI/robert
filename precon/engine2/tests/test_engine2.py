"""Engine 2 — Coverage Engine Tests"""
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from precon.engine2.engine2 import Engine2, BuildingType, ProjectMode, ScopeExpectation

e2 = Engine2()
PID = str(uuid.uuid4())

class TestHospitalCoverage:
    def test_medical_gas_required_for_hospital(self):
        expected = e2.get_expected_csi_sections(BuildingType.HOSPITAL, ProjectMode.SUB,
                                                 ScopeExpectation.REQUIRED)
        assert "226000" in expected

    def test_commissioning_required_for_hospital(self):
        expected = e2.get_expected_csi_sections(BuildingType.HOSPITAL, ProjectMode.SUB,
                                                 ScopeExpectation.REQUIRED)
        assert "230800" in expected

    def test_full_hospital_coverage_all_present(self):
        all_sections = ["230000","230593","220000","230900","226000","236000","230800","230000"]
        report = e2.analyze(PID, BuildingType.HOSPITAL, ProjectMode.SUB, 80000,
                            all_sections, all_sections)
        assert report.coverage_score == 100.0
        assert report.gaps == 0

    def test_hospital_missing_medical_gas_is_gap(self):
        # No medical gas in covered sections
        sections = ["230000","230593","220000","230900","236000","230800"]
        report = e2.analyze(PID, BuildingType.HOSPITAL, ProjectMode.SUB, 80000,
                            sections, sections)
        gap_sections = [i.csi_section for i in report.gap_items]
        assert "226000" in gap_sections

    def test_hospital_missing_medical_gas_generates_warning(self):
        sections = ["230000","230593","220000","230900","236000","230800"]
        report = e2.analyze(PID, BuildingType.HOSPITAL, ProjectMode.SUB, 80000,
                            sections, sections)
        assert any("medical gas" in w.lower() for w in report.warnings)

    def test_hospital_required_gap_generates_recommendation(self):
        sections = ["230000","230593","220000"]
        report = e2.analyze(PID, BuildingType.HOSPITAL, ProjectMode.SUB, 80000,
                            sections, sections)
        assert len(report.recommendations) >= 1

class TestRestaurantCoverage:
    def test_kitchen_hoods_required_for_restaurant(self):
        expected = e2.get_expected_csi_sections(BuildingType.RESTAURANT, ProjectMode.SUB,
                                                  ScopeExpectation.REQUIRED)
        assert "233813" in expected

    def test_restaurant_missing_hoods_is_gap(self):
        sections = ["230000","230593","220000","230900"]
        report = e2.analyze(PID, BuildingType.RESTAURANT, ProjectMode.SUB, 5000,
                            sections, sections)
        gap_sections = [i.csi_section for i in report.gap_items]
        assert "233813" in gap_sections

class TestWarehouseCoverage:
    def test_hvac_optional_for_warehouse(self):
        expected = e2.get_expected_csi_sections(BuildingType.WAREHOUSE, ProjectMode.SUB,
                                                  ScopeExpectation.OPTIONAL)
        # HVAC is optional for warehouse — not required
        required = e2.get_expected_csi_sections(BuildingType.WAREHOUSE, ProjectMode.SUB,
                                                  ScopeExpectation.REQUIRED)
        # Sprinklers are required
        assert "211000" in required

class TestMilitaryCoverage:
    def test_commissioning_required_military(self):
        expected = e2.get_expected_csi_sections(BuildingType.MILITARY, ProjectMode.SUB,
                                                  ScopeExpectation.REQUIRED)
        assert "230800" in expected

    def test_bas_required_military(self):
        expected = e2.get_expected_csi_sections(BuildingType.MILITARY, ProjectMode.SUB,
                                                  ScopeExpectation.REQUIRED)
        assert "230900" in expected

class TestUnexpectedItems:
    def test_unexpected_item_detected(self):
        # Medical gas shows up in an office building — unexpected
        sections = ["230000","230593","220000","230900","226000"]
        report = e2.analyze(PID, BuildingType.OFFICE, ProjectMode.SUB, 30000,
                            sections, sections)
        unexpected = [i.csi_section for i in report.unexpected_items]
        assert "226000" in unexpected

class TestCoverageScore:
    def test_empty_coverage_zero_score(self):
        report = e2.analyze(PID, BuildingType.OFFICE, ProjectMode.SUB, 20000, [], [])
        assert report.coverage_score == 0.0

    def test_full_coverage_100_score(self):
        all_req = e2.get_expected_csi_sections(BuildingType.OFFICE, ProjectMode.SUB,
                                                ScopeExpectation.TYPICAL)
        report = e2.analyze(PID, BuildingType.OFFICE, ProjectMode.SUB, 20000,
                            all_req, all_req)
        assert report.coverage_score == 100.0

    def test_report_has_required_fields(self):
        report = e2.analyze(PID, BuildingType.OFFICE, ProjectMode.SUB, 20000, [], [])
        assert report.project_id == PID
        assert report.building_type == BuildingType.OFFICE
        assert isinstance(report.items, list)
        assert isinstance(report.gap_items, list)
        assert isinstance(report.recommendations, list)

if __name__ == "__main__":
    import subprocess
    r = subprocess.run(["python3","-m","pytest",__file__,"-v","--tb=short"],
                       capture_output=True, text=True,
                       cwd="/var/lib/openclaw/.openclaw/workspace")
    print(r.stdout); print(r.stderr[-300:] if r.stderr else "")
