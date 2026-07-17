"""
ENGINE 2 — COVERAGE ENGINE v1.0
Mode-specific Expected Scope.

For a given project type (building_type) and mode (GC/Sub),
produces the expected scope checklist — what SHOULD be in this bid.

Then compares against what was actually extracted (Engine 1 output)
and what quotes have been received (Quote Intake output) to produce:
  - Coverage gaps (expected but not found)
  - Unexpected items (found but not expected — potential scope creep or error)
  - Coverage score (% of expected scope accounted for)

Building types supported:
  hospital / medical_office / office / warehouse / school / retail /
  restaurant / government / military / multifamily / industrial / mixed_use

Mode:
  sub  — NewCo scope only (Div 21/22/23 + specialty subs)
  gc   — All trades (all CSI divisions)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BuildingType(str, Enum):
    HOSPITAL          = "hospital"
    MEDICAL_OFFICE    = "medical_office"
    OFFICE            = "office"
    WAREHOUSE         = "warehouse"
    SCHOOL            = "school"
    RETAIL            = "retail"
    RESTAURANT        = "restaurant"
    GOVERNMENT        = "government"
    MILITARY          = "military"
    MULTIFAMILY       = "multifamily"
    INDUSTRIAL        = "industrial"
    MIXED_USE         = "mixed_use"
    UNKNOWN           = "unknown"


class ProjectMode(str, Enum):
    SUB = "sub"   # NewCo specialty sub — Div 21/22/23
    GC  = "gc"    # General contractor — all trades


class ScopeExpectation(str, Enum):
    REQUIRED    = "required"    # Always present for this building type
    TYPICAL     = "typical"     # Present on most projects of this type
    OPTIONAL    = "optional"    # Sometimes present, depends on project
    RARE        = "rare"        # Uncommon, flag if present


@dataclass
class ExpectedScopeItem:
    csi_section: str
    description: str
    expectation: ScopeExpectation
    reasoning: str                          # Why expected for this building type
    typical_cost_range: Optional[str] = None  # e.g. "$15-45K" — rough sanity check
    cost_codes: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)  # keywords that confirm presence


@dataclass
class CoverageItem:
    csi_section: str
    description: str
    expectation: ScopeExpectation
    status: str         # 'covered' | 'gap' | 'unexpected' | 'partial'
    covered_by: Optional[str] = None    # vendor name or source document
    confidence: Optional[str] = None    # 'high' | 'medium' | 'low'
    notes: Optional[str] = None


@dataclass
class CoverageReport:
    project_id: str
    building_type: BuildingType
    mode: ProjectMode
    sqft: Optional[int]
    total_expected: int
    covered: int
    gaps: int
    unexpected: int
    coverage_score: float           # 0-100
    items: list[CoverageItem]
    gap_items: list[CoverageItem]   # subset — gaps only
    unexpected_items: list[CoverageItem]
    warnings: list[str]
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Expected Scope Library
# Building type → list of expected CSI sections with reasoning
# Sub mode: Div 21/22/23 + specialty subs
# GC mode: all divisions
# ---------------------------------------------------------------------------

# Base MEP scope (present on almost every commercial project)
BASE_MEP_SUB = [
    ExpectedScopeItem("230000", "HVAC Contractor", ScopeExpectation.REQUIRED,
        "All commercial buildings require HVAC", "$50K-2M+",
        ["100","110","111","112"], ["hvac","mechanical","ahu","fcu","rtu"]),
    ExpectedScopeItem("230593", "Test & Balance", ScopeExpectation.REQUIRED,
        "TAB required on all HVAC systems by code", "$8-45K",
        ["503"], ["tab","test and balance","air balance","smacna"]),
    ExpectedScopeItem("220000", "Plumbing", ScopeExpectation.REQUIRED,
        "All occupied buildings require plumbing", "$20K-500K+",
        ["300","301","302"], ["plumbing","sanitary","domestic water","fixture"]),
    ExpectedScopeItem("230000", "Mechanical Insulation", ScopeExpectation.REQUIRED,
        "Code requires insulation on all HVAC piping and ductwork", "$5-50K",
        ["501"], ["insulation","insulate","insul"]),
    ExpectedScopeItem("230900", "Instrumentation & Controls", ScopeExpectation.TYPICAL,
        "Most commercial HVAC requires DDC controls", "$25-200K",
        ["172","173","502"], ["controls","ddc","bas","bms","pneumatic"]),
]

BASE_MEP_GC = [
    ExpectedScopeItem("260000", "Electrical", ScopeExpectation.REQUIRED,
        "All buildings require electrical", None, ["512"], ["electrical","power"]),
    ExpectedScopeItem("211000", "Fire Sprinklers", ScopeExpectation.REQUIRED,
        "Required by code in most commercial occupancies", "$8-25/SF",
        ["516"], ["sprinkler","fire protection"]),
    ExpectedScopeItem("010000", "General Conditions", ScopeExpectation.REQUIRED,
        "GC always has general conditions", None, [], ["supervision","general conditions"]),
    ExpectedScopeItem("033000", "Concrete", ScopeExpectation.TYPICAL,
        "Most commercial projects have concrete work", None, [], ["concrete","slab"]),
    ExpectedScopeItem("092900", "Drywall / Framing", ScopeExpectation.TYPICAL,
        "Interior partitions in most commercial buildings", None, [], ["drywall","framing","gypsum"]),
    ExpectedScopeItem("096000", "Flooring", ScopeExpectation.TYPICAL,
        "All occupied buildings need finished flooring", None, [], ["flooring","tile","carpet","vct"]),
    ExpectedScopeItem("075000", "Roofing", ScopeExpectation.REQUIRED,
        "All buildings require a roof", "$8-20/SF", [], ["roofing","membrane","tpo","epdm"]),
]

# Building-type specific expected scope
BUILDING_TYPE_SCOPE: dict[BuildingType, dict[ProjectMode, list[ExpectedScopeItem]]] = {

    BuildingType.HOSPITAL: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("226000", "Medical Gas & Vacuum Systems", ScopeExpectation.REQUIRED,
                "Hospitals always have medical gas and vacuum", "$50-500K",
                ["350","517"], ["medical gas","oxygen","vacuum","med gas","piped gas"]),
            ExpectedScopeItem("236000", "Chilled Water Systems", ScopeExpectation.REQUIRED,
                "Hospitals use central chilled water plants", "$100K-2M",
                ["141","142","144"], ["chilled water","cooling tower","chiller","cwt"]),
            ExpectedScopeItem("230800", "HVAC Commissioning", ScopeExpectation.REQUIRED,
                "Hospital HVAC commissioning required by ASHRAE and Joint Commission", "$15-100K",
                ["173"], ["commissioning","cx","retro-cx"]),
            ExpectedScopeItem("230000", "Duct Leakage Testing", ScopeExpectation.TYPICAL,
                "Infection control requires verified duct integrity in hospitals", "$5-25K",
                ["504"], ["duct leakage","duct testing","smacna class"]),
        ],
        ProjectMode.GC: BASE_MEP_GC + [
            ExpectedScopeItem("226000", "Medical Gas", ScopeExpectation.REQUIRED,
                "Required in all hospital projects", None, [], ["medical gas"]),
            ExpectedScopeItem("128000", "Casework", ScopeExpectation.REQUIRED,
                "Hospitals have extensive casework/millwork", None, [], ["casework","millwork"]),
        ],
    },

    BuildingType.MEDICAL_OFFICE: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("226000", "Medical Gas & Vacuum Systems", ScopeExpectation.TYPICAL,
                "Medical offices often have piped oxygen/vacuum", "$15-150K",
                ["350","517"], ["medical gas","oxygen","vacuum","exam room"]),
            ExpectedScopeItem("230800", "HVAC Commissioning", ScopeExpectation.TYPICAL,
                "MOB commissioning increasingly standard", "$8-50K",
                ["173"], ["commissioning","cx"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.OFFICE: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("230800", "HVAC Commissioning", ScopeExpectation.OPTIONAL,
                "Office commissioning required on LEED projects or owner-specified", "$5-30K",
                ["173"], ["commissioning","leed","cx"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.RESTAURANT: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("233813", "Commercial Kitchen Hoods", ScopeExpectation.REQUIRED,
                "All restaurants with cooking require commercial exhaust hoods", "$15-100K",
                ["150"], ["hood","exhaust","kitchen","type 1","type 2","grease"]),
            ExpectedScopeItem("231000", "Fuel Systems", ScopeExpectation.TYPICAL,
                "Most restaurants use gas for cooking", "$5-25K",
                ["160"], ["gas","natural gas","fuel","grease"]),
        ],
        ProjectMode.GC: BASE_MEP_GC + [
            ExpectedScopeItem("114000", "Food Service Equipment", ScopeExpectation.TYPICAL,
                "Restaurant equipment typically by GC or Owner-furnished", None,
                [], ["food service","kitchen equipment"]),
        ],
    },

    BuildingType.SCHOOL: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("230800", "HVAC Commissioning", ScopeExpectation.REQUIRED,
                "Florida schools require HVAC commissioning per FSBA standards", "$10-60K",
                ["173"], ["commissioning","cx","fsba"]),
            ExpectedScopeItem("226000", "Medical Gas", ScopeExpectation.RARE,
                "Only in schools with health clinics", "$8-30K",
                ["350"], ["medical gas","health clinic","nurse"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.WAREHOUSE: {
        ProjectMode.SUB: [
            ExpectedScopeItem("230000", "HVAC Contractor", ScopeExpectation.OPTIONAL,
                "Warehouses often have minimal or no HVAC — verify with drawings", "$20K-500K",
                ["100"], ["hvac","unit heater","evaporative","dock"]),
            ExpectedScopeItem("220000", "Plumbing", ScopeExpectation.TYPICAL,
                "Warehouse requires at minimum restroom plumbing", "$15-80K",
                ["300"], ["plumbing","restroom","hose bib"]),
            ExpectedScopeItem("211000", "Fire Sprinklers", ScopeExpectation.REQUIRED,
                "All warehouses over 12,000 SF require sprinklers", "$3-8/SF",
                ["516"], ["sprinkler"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.GOVERNMENT: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("230800", "HVAC Commissioning", ScopeExpectation.REQUIRED,
                "Federal/state government projects require commissioning", "$10-75K",
                ["173"], ["commissioning","cx","leed","government"]),
            ExpectedScopeItem("230900", "Controls — Enhanced", ScopeExpectation.REQUIRED,
                "Government buildings require BAS with remote monitoring", "$30-250K",
                ["172","502"], ["bas","building automation","remote monitoring","energy"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.MILITARY: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("230800", "HVAC Commissioning", ScopeExpectation.REQUIRED,
                "Military projects require commissioning per UFC standards", "$15-100K",
                ["173"], ["commissioning","ufc","military","army","navy","air force"]),
            ExpectedScopeItem("230900", "Controls — BAS", ScopeExpectation.REQUIRED,
                "Military installations require BAS integration with installation-wide systems", "$50-400K",
                ["172","502"], ["bas","emcs","metering","installation"]),
            ExpectedScopeItem("226000", "Medical Gas", ScopeExpectation.OPTIONAL,
                "Present if project includes medical treatment facility", "$20-200K",
                ["350"], ["medical","mtf","clinic","hospital"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.MULTIFAMILY: {
        ProjectMode.SUB: BASE_MEP_SUB + [
            ExpectedScopeItem("232300", "Refrigeration / Mechanical Equipment", ScopeExpectation.OPTIONAL,
                "High-rise multifamily may have central plant", "$50K-1M",
                ["130"], ["central plant","chilled water","high rise"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },

    BuildingType.INDUSTRIAL: {
        ProjectMode.SUB: [
            ExpectedScopeItem("230000", "HVAC — Process & Comfort", ScopeExpectation.TYPICAL,
                "Industrial often has process cooling/ventilation requirements", "$30K-2M",
                ["100"], ["process","cooling","ventilation","exhaust"]),
            ExpectedScopeItem("233516", "Engine Exhaust Systems", ScopeExpectation.TYPICAL,
                "Industrial facilities often have generator/vehicle exhaust", "$10-75K",
                ["215"], ["exhaust","generator","vehicle","diesel"]),
            ExpectedScopeItem("220000", "Plumbing — Industrial", ScopeExpectation.REQUIRED,
                "Industrial requires process plumbing + restrooms", "$25K-500K",
                ["300"], ["plumbing","process","eyewash","safety shower"]),
        ],
        ProjectMode.GC: BASE_MEP_GC,
    },
}

# Default for unknown building types
BUILDING_TYPE_SCOPE[BuildingType.UNKNOWN] = {
    ProjectMode.SUB: BASE_MEP_SUB,
    ProjectMode.GC: BASE_MEP_GC,
}
BUILDING_TYPE_SCOPE[BuildingType.MIXED_USE] = {
    ProjectMode.SUB: BASE_MEP_SUB + [
        ExpectedScopeItem("233813", "Kitchen Hoods", ScopeExpectation.OPTIONAL,
            "If retail component includes restaurant", "$15-100K",
            ["150"], ["hood","restaurant","kitchen"]),
        ExpectedScopeItem("226000", "Medical Gas", ScopeExpectation.OPTIONAL,
            "If medical component present", "$15-150K",
            ["350","517"], ["medical","clinic","health"]),
    ],
    ProjectMode.GC: BASE_MEP_GC,
}
BUILDING_TYPE_SCOPE[BuildingType.RETAIL] = {
    ProjectMode.SUB: BASE_MEP_SUB,
    ProjectMode.GC: BASE_MEP_GC,
}


# ---------------------------------------------------------------------------
# Module-level helper — used by Engine 2A
# ---------------------------------------------------------------------------

def get_expected_scope(
    building_type: BuildingType, mode: ProjectMode
) -> list["ExpectedScopeItem"]:
    """Return expected scope items for a building type + mode. Public API for Engine 2A."""
    type_scope = BUILDING_TYPE_SCOPE.get(building_type, BUILDING_TYPE_SCOPE[BuildingType.UNKNOWN])
    return type_scope.get(mode, type_scope.get(ProjectMode.SUB, BASE_MEP_SUB))


# ---------------------------------------------------------------------------
# Engine 2 — Coverage Engine
# ---------------------------------------------------------------------------

class Engine2:

    def analyze(
        self,
        project_id: str,
        building_type: BuildingType,
        mode: ProjectMode,
        sqft: Optional[int],
        extracted_csi_sections: list[str],      # from Engine 1
        received_quote_csi_sections: list[str], # from Quote Intake
        vendor_names: list[str] = None,         # vendors who submitted
    ) -> CoverageReport:
        """
        Compare expected scope vs. what was found/quoted.
        Returns coverage report with gaps, unexpected items, and recommendations.
        """
        vendor_names = vendor_names or []
        expected = self._get_expected_scope(building_type, mode)

        # Build combined "covered" set from both Engine 1 extractions + received quotes
        covered_sections = set(extracted_csi_sections) | set(received_quote_csi_sections)

        items: list[CoverageItem] = []
        gap_items: list[CoverageItem] = []
        unexpected_items: list[CoverageItem] = []
        warnings: list[str] = []

        for exp in expected:
            # Check if this section is covered
            is_covered = exp.csi_section in covered_sections

            # Also check by keyword if not directly matched
            if not is_covered and exp.triggers:
                # Triggers are not checked here (would need full text)
                # Flag as gap for required/typical
                pass

            if is_covered:
                # Find covering vendor if applicable
                covering_vendor = next(
                    (v for v in vendor_names
                     if any(t in v.lower() for t in exp.triggers)),
                    None
                )
                status = "covered"
                item = CoverageItem(
                    csi_section=exp.csi_section,
                    description=exp.description,
                    expectation=exp.expectation,
                    status=status,
                    covered_by=covering_vendor,
                    confidence="high" if exp.csi_section in received_quote_csi_sections else "medium",
                )
            else:
                if exp.expectation in (ScopeExpectation.REQUIRED, ScopeExpectation.TYPICAL):
                    status = "gap"
                    item = CoverageItem(
                        csi_section=exp.csi_section,
                        description=exp.description,
                        expectation=exp.expectation,
                        status=status,
                        notes=exp.reasoning,
                    )
                    gap_items.append(item)
                else:
                    # Optional/rare — not a gap, just not present
                    status = "not_applicable"
                    item = CoverageItem(
                        csi_section=exp.csi_section,
                        description=exp.description,
                        expectation=exp.expectation,
                        status=status,
                        notes="Optional — not required for this project",
                    )
            items.append(item)

        # Find unexpected items (in covered but not in expected)
        expected_sections = {e.csi_section for e in expected}
        for section in covered_sections:
            if section not in expected_sections:
                # Look up description
                from precon.engine1.engine1 import CSI_SECTION_LOOKUP
                desc = CSI_SECTION_LOOKUP.get(section, f"CSI {section}")
                unexpected_item = CoverageItem(
                    csi_section=section,
                    description=desc,
                    expectation=ScopeExpectation.OPTIONAL,
                    status="unexpected",
                    notes="Found in documents/quotes but not typical for this building type — verify scope inclusion is intentional",
                )
                unexpected_items.append(unexpected_item)

        # Generate warnings
        if any(i.expectation == ScopeExpectation.REQUIRED and i.status == "gap" for i in gap_items):
            req_gaps = [i.description for i in gap_items if i.expectation == ScopeExpectation.REQUIRED]
            warnings.append(
                f"REQUIRED scope missing: {', '.join(req_gaps)}. "
                f"These items are expected on every {building_type} project."
            )

        if building_type == BuildingType.HOSPITAL and "226000" not in covered_sections:
            warnings.append(
                "Medical gas not found in documents or quotes. "
                "Hospitals always require medical gas — verify this is excluded intentionally."
            )

        if sqft and sqft > 50000 and "230800" not in covered_sections:
            warnings.append(
                "Large project (>50K SF) with no commissioning found. "
                "Commissioning is standard on projects this size."
            )

        # Recommendations
        recommendations = []
        for gap in gap_items:
            if gap.expectation == ScopeExpectation.REQUIRED:
                recommendations.append(
                    f"Obtain quote for {gap.description} ({gap.csi_section}) — required for {building_type} projects."
                )
            elif gap.expectation == ScopeExpectation.TYPICAL:
                recommendations.append(
                    f"Verify whether {gap.description} ({gap.csi_section}) is in scope — typical for this building type."
                )

        # Coverage score: required + typical items only
        scoreable = [e for e in expected if e.expectation in (ScopeExpectation.REQUIRED, ScopeExpectation.TYPICAL)]
        covered_scoreable = sum(
            1 for e in scoreable if e.csi_section in covered_sections
        )
        score = (covered_scoreable / len(scoreable) * 100) if scoreable else 100.0

        return CoverageReport(
            project_id=project_id,
            building_type=building_type,
            mode=mode,
            sqft=sqft,
            total_expected=len([e for e in expected if e.expectation in
                                 (ScopeExpectation.REQUIRED, ScopeExpectation.TYPICAL)]),
            covered=covered_scoreable,
            gaps=len(gap_items),
            unexpected=len(unexpected_items),
            coverage_score=round(score, 1),
            items=items,
            gap_items=gap_items,
            unexpected_items=unexpected_items,
            warnings=warnings,
            recommendations=recommendations,
        )

    def _get_expected_scope(
        self, building_type: BuildingType, mode: ProjectMode
    ) -> list[ExpectedScopeItem]:
        type_scope = BUILDING_TYPE_SCOPE.get(building_type, BUILDING_TYPE_SCOPE[BuildingType.UNKNOWN])
        return type_scope.get(mode, type_scope.get(ProjectMode.SUB, BASE_MEP_SUB))

    def get_expected_csi_sections(
        self, building_type: BuildingType, mode: ProjectMode,
        min_expectation: ScopeExpectation = ScopeExpectation.TYPICAL
    ) -> list[str]:
        """Return just the CSI section numbers expected for this building type."""
        rank = {ScopeExpectation.REQUIRED: 3, ScopeExpectation.TYPICAL: 2,
                ScopeExpectation.OPTIONAL: 1, ScopeExpectation.RARE: 0}
        min_rank = rank[min_expectation]
        expected = self._get_expected_scope(building_type, mode)
        return [e.csi_section for e in expected if rank[e.expectation] >= min_rank]
