"""Proposal Generator Tests"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from precon.proposal.proposal_generator import (
    ProposalGenerator, ProposalMode, ProposalData, CompanyProfile,
    ProjectMetadata, ScheduleData, ScopeInterpretationItem,
    calculate_duration,
)

gen = ProposalGenerator()

def make_company():
    return CompanyProfile(
        company_name="NewCo Mechanical & Plumbing",
        address="123 Industrial Blvd",
        city_state_zip="Naples, FL 34104",
        phone="(239) 555-0100",
        email="bids@newco.com",
        emr_rating=0.82,
        osha_recordable_rate=1.2,
        safety_program_name="OSHA 10/30 Certified Safety Program",
        license_numbers={"FL": "CMC1234567"},
        insurance_gl_limit="$2M/$4M",
    )

def make_project(mode="sub"):
    return ProjectMetadata(
        project_name="Macdill AFB Building 53 HVAC Renovation",
        project_number="AMS-2026-001",
        gc_name="Trias Construction" if mode == "sub" else None,
        owner_name="US Air Force" if mode == "gc" else None,
        architect_name="Smith Architects",
        location="Tampa, FL",
        building_type="military",
        sqft=48000,
        bid_date="2026-07-15",
        proposal_number="P-2026-047",
        validity_days=30,
    )

def make_schedule():
    return ScheduleData(
        mechanical_hours=1200,
        sheet_metal_hours=800,
        plumbing_hours=400,
        mechanical_crew=4,
        sheet_metal_crew=3,
        plumbing_crew=2,
        proposed_mobilization="Within 2 weeks of NTP",
        long_lead_items=[
            {"item": "DDC Controls Equipment", "lead_weeks": 14, "notes": "Submit immediately upon award."},
            {"item": "AHU-1 through AHU-4", "lead_weeks": 12, "notes": "Early release required."},
        ],
    )

def make_data(mode="sub"):
    return ProposalData(
        mode=ProposalMode.SUB if mode == "sub" else ProposalMode.GC,
        company=make_company(),
        project=make_project(mode),
        schedule=make_schedule(),
        bid_amount=485000.00,
        bid_breakdown={"Mechanical": 220000, "Sheet Metal": 145000, "Plumbing": 85000, "Subs": 35000},
        scope_items=[
            "Complete mechanical HVAC system replacement per Div 23",
            "DDC controls and BAS upgrade per Section 23 09 23",
            "Test, adjust, and balance all HVAC systems",
            "Mechanical insulation — all piping and ductwork",
            "HVAC commissioning per UFC standards",
        ],
        exclusions=[
            "Electrical power wiring to equipment (by Electrical Contractor)",
            "Structural steel supports (by GC)",
            "Painting of mechanical equipment",
        ],
        qualifications=[
            "Proposal based on documents dated June 1, 2026",
            "Allowance for unknown existing conditions: $10,000",
        ],
        scope_interpretation_items=[
            ScopeInterpretationItem(
                description="Unit heater in mechanical room 114",
                location="Arch Sheet A-211, Room 114",
                decision="included",
                basis="per Arch Sheet A-211 — not shown on Mechanical drawings",
                estimated_value=2800,
            ),
            ScopeInterpretationItem(
                description="Roof curb sizes for AHU-1 through AHU-4",
                location="Roof Plan A-501",
                decision="clarification",
                basis="curb sizes on A-501 differ from equipment sizes on M-001 schedule",
            ),
        ],
        project_experience=[
            {"name": "MacDill AFB Hangar 8 HVAC", "value": 1200000, "gc": "Trias Construction", "year": 2024},
            {"name": "Bayfront Medical Center HVAC", "value": 850000, "gc": "Ajax GC", "year": 2023},
        ],
    )


class TestDurationCalculator:
    def test_single_trade_duration(self):
        s = ScheduleData(mechanical_hours=800, mechanical_crew=4)
        d = calculate_duration(s)
        # 800 hrs / (4 × 40) = 5 weeks
        assert d["mechanical_weeks"] == 5.0

    def test_multi_trade_concurrent_shorter_than_sum(self):
        s = ScheduleData(mechanical_hours=1200, sheet_metal_hours=800, plumbing_hours=400,
                         mechanical_crew=4, sheet_metal_crew=3, plumbing_crew=2)
        d = calculate_duration(s)
        # Concurrent — total should be less than sum of individual durations
        total = d["total_weeks"]
        sum_individual = d["mechanical_weeks"] + d["sheet_metal_weeks"] + d["plumbing_weeks"]
        assert total < sum_individual

    def test_zero_hours_zero_duration(self):
        s = ScheduleData()
        d = calculate_duration(s)
        assert d["total_weeks"] == 0

    def test_duration_in_months_calculated(self):
        s = ScheduleData(mechanical_hours=1200, mechanical_crew=4)
        d = calculate_duration(s)
        assert d["total_months"] > 0


class TestSubProposal:
    def test_sub_proposal_has_all_sections(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        sections = proposal["sections"]
        required = ["cover","introduction","understanding","scope_of_work",
                    "schedule","qualifications","exclusions","bid_summary","closing"]
        for s in required:
            assert s in sections, f"Missing section: {s}"

    def test_sub_proposal_cover_has_bid_amount(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        cover = proposal["sections"]["cover"]
        assert "485,000" in cover["bid_amount"]

    def test_sub_proposal_cover_has_gc_name(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        assert proposal["sections"]["cover"]["submitted_to"] == "Trias Construction"

    def test_schedule_section_has_duration(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        schedule = proposal["sections"]["schedule"]
        assert schedule["duration_weeks"] > 0
        assert schedule["duration_months"] > 0

    def test_schedule_has_long_lead_items(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        schedule = proposal["sections"]["schedule"]
        assert len(schedule["long_lead_items"]) == 2
        assert any("DDC" in item for item in schedule["long_lead_items"])

    def test_scope_items_in_proposal(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        scope = proposal["sections"]["scope_of_work"]
        assert len(scope["items"]) >= 5

    def test_quals_has_scope_interpretation(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        quals = proposal["sections"]["qualifications"]
        assert len(quals["scope_interpretation"]) == 2

    def test_interpretation_uses_correct_language(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        quals = proposal["sections"]["qualifications"]
        all_text = " ".join(quals["scope_interpretation"])
        assert "bidder" not in all_text.lower()
        assert "competitor" not in all_text.lower()

    def test_clarification_item_uses_interpretation_framing(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        quals = proposal["sections"]["qualifications"]
        clarification = next(q for q in quals["scope_interpretation"] if "CLARIFICATION" in q)
        assert "interpretation" in clarification.lower() or "consistent" in clarification.lower()

    def test_included_item_shows_value(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        quals = proposal["sections"]["qualifications"]
        included = next(q for q in quals["scope_interpretation"] if "INCLUDED" in q)
        assert "2,800" in included

    def test_exclusions_section_has_default_exclusions(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        exclusions = proposal["sections"]["exclusions"]
        assert len(exclusions) >= 3
        assert any("hazardous" in e.lower() for e in exclusions)

    def test_bid_summary_has_breakdown(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        bid = proposal["sections"]["bid_summary"]
        assert bid["base_bid"] == 485000.00
        assert "Mechanical" in bid["breakdown"]

    def test_appendix_has_emr(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        assert proposal["appendix"]["C_safety_emr"]["emr"] == 0.82

    def test_proposal_mode_is_sub(self):
        data = make_data("sub")
        proposal = gen.generate(data)
        assert proposal["mode"] == "sub"


class TestGCProposal:
    def test_gc_proposal_has_all_sections(self):
        data = make_data("gc")
        proposal = gen.generate(data)
        sections = proposal["sections"]
        required = ["cover","executive_summary","understanding","project_team",
                    "scope_of_work","schedule","qualifications","bid_summary","closing"]
        for s in required:
            assert s in sections, f"Missing section: {s}"

    def test_gc_cover_has_owner(self):
        data = make_data("gc")
        proposal = gen.generate(data)
        assert proposal["sections"]["cover"]["submitted_to"] == "US Air Force"

    def test_gc_appendix_has_subcontractor_list(self):
        data = make_data("gc")
        proposal = gen.generate(data)
        assert "F_subcontractor_list" in proposal["appendix"]

    def test_gc_appendix_has_bond_capacity(self):
        data = make_data("gc")
        proposal = gen.generate(data)
        assert "A_company_qualifications" in proposal["appendix"]

    def test_proposal_mode_is_gc(self):
        data = make_data("gc")
        proposal = gen.generate(data)
        assert proposal["mode"] == "gc"

if __name__ == "__main__":
    import subprocess
    r = subprocess.run(["python3","-m","pytest",__file__,"-v","--tb=short"],
                       capture_output=True, text=True,
                       cwd="/var/lib/openclaw/.openclaw/workspace")
    print(r.stdout); print(r.stderr[-300:] if r.stderr else "")
