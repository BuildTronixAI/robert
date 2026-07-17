"""
A-10 — ESTIMATE ALIGNMENT GATE v1.0
Verifies the estimate is "in band" for the scope and building type.

Uses NewCo overhead/labor rate benchmarks (from Project_Budget_Workbook_v2.2)
to validate whether cost recap entries are within expected ranges.

Three validation layers:
  Layer 1 — Coverage completeness (did Engine 2 find all required scope?)
  Layer 2 — Rate sanity (are labor rates / overhead rates within expected bands?)
  Layer 3 — Value banding (is the total estimate reasonable for this building type + SF?)

Gate result: PASS / WARNING / BLOCK
  PASS    — Estimate is within all bands. Ready for proposal.
  WARNING — One or more items outside band but within override threshold. Estimator review.
  BLOCK   — Critical gap or rate error. Must resolve before proposal.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GateResult(str, Enum):
    PASS    = "pass"
    WARNING = "warning"
    BLOCK   = "block"


class CheckResult(str, Enum):
    PASS    = "pass"
    WARNING = "warning"
    FAIL    = "fail"
    SKIP    = "skip"     # Not enough data to evaluate


@dataclass
class GateCheck:
    check_id: str
    description: str
    result: CheckResult
    expected: str
    actual: str
    variance_pct: Optional[float] = None
    notes: Optional[str] = None
    blocking: bool = False     # True = FAIL here blocks the whole gate


@dataclass
class A10Report:
    project_id: str
    gate_result: GateResult
    checks: list[GateCheck]
    blocking_checks: list[GateCheck]    # Subset — blocking failures only
    warnings: list[GateCheck]           # Subset — warnings only
    total_estimate: float
    coverage_score: float
    ready_for_proposal: bool
    estimator_notes: list[str]


# ---------------------------------------------------------------------------
# NewCo benchmark rates (from Project_Budget_Workbook_v2.2)
# ---------------------------------------------------------------------------

NEWCO_BENCHMARKS = {
    # Labor rates by trade (field rates)
    "labor_rate_mechanical":    50.00,   # $/hr
    "labor_rate_sheet_metal":   40.00,   # $/hr
    "labor_rate_plumbing":      40.00,   # $/hr

    # Overhead X Factor (labor burden + overhead)
    "x_factor_combined":        3.31,
    "x_factor_hvac":            2.79,

    # Minimum margin targets
    "min_margin_labor":         0.30,    # 30%
    "min_margin_material":      0.15,    # 15%
    "min_margin_equipment":     0.10,    # 10%
    "min_margin_subs":          0.10,    # 10%
    "min_gpm":                  0.22,    # 22% minimum gross profit margin

    # Acceptable variance band (± from benchmark before warning)
    "rate_warning_band":        0.15,    # ±15% triggers warning
    "rate_block_band":          0.35,    # ±35% triggers block

    # Value-per-SF bands by building type (total MEP $/SF rough estimate)
    "value_bands": {
        "hospital":       (35, 120),   # MEP-heavy
        "medical_office": (20, 65),
        "office":         (15, 45),
        "warehouse":      (5,  20),
        "school":         (18, 50),
        "retail":         (8,  30),
        "restaurant":     (20, 70),
        "government":     (20, 60),
        "military":       (22, 70),
        "multifamily":    (12, 40),
        "industrial":     (10, 35),
        "mixed_use":      (15, 55),
        "unknown":        (10, 80),    # Wide band — unknown type
    },
}


# ---------------------------------------------------------------------------
# Cost recap entry (simplified — matches cost_recap_entries table)
# ---------------------------------------------------------------------------

@dataclass
class CostRecapSummary:
    proposal_id: str
    total_labor_cost: float
    total_material_cost: float
    total_equipment_cost: float
    total_sub_cost: float
    total_direct_cost: float
    # Labor breakdown by trade
    mechanical_labor_hours: float = 0
    sheet_metal_labor_hours: float = 0
    plumbing_labor_hours: float = 0
    # Average rates applied
    avg_labor_rate: Optional[float] = None
    # Coverage data
    coverage_score: Optional[float] = None
    coverage_gaps: int = 0
    # Project metadata
    sqft: Optional[int] = None
    building_type: str = "unknown"


# ---------------------------------------------------------------------------
# A-10 Gate
# ---------------------------------------------------------------------------

class A10Gate:

    def evaluate(
        self,
        project_id: str,
        recap: CostRecapSummary,
        coverage_score: float,
        coverage_gaps: int,
        required_gaps: int,  # gaps on REQUIRED items specifically
    ) -> A10Report:
        """
        Run all three validation layers.
        Returns A10Report with gate result.
        """
        checks: list[GateCheck] = []

        # === LAYER 1: Coverage Completeness ===
        checks.extend(self._check_coverage(coverage_score, coverage_gaps, required_gaps))

        # === LAYER 2: Rate Sanity ===
        checks.extend(self._check_rates(recap))

        # === LAYER 3: Value Banding ===
        checks.extend(self._check_value_banding(recap))

        # === LAYER 4: Margin Check ===
        checks.extend(self._check_margins(recap))

        # Determine gate result
        blocking = [c for c in checks if c.blocking and c.result == CheckResult.FAIL]
        warnings = [c for c in checks if c.result == CheckResult.WARNING]

        if blocking:
            gate_result = GateResult.BLOCK
        elif warnings:
            gate_result = GateResult.WARNING
        else:
            gate_result = GateResult.PASS

        # Estimator notes
        notes = []
        for c in blocking:
            notes.append(f"BLOCK — {c.description}: {c.notes}")
        for c in warnings:
            notes.append(f"REVIEW — {c.description}: {c.notes}")

        return A10Report(
            project_id=project_id,
            gate_result=gate_result,
            checks=checks,
            blocking_checks=blocking,
            warnings=warnings,
            total_estimate=recap.total_direct_cost,
            coverage_score=coverage_score,
            ready_for_proposal=(gate_result == GateResult.PASS),
            estimator_notes=notes,
        )

    # ------------------------------------------------------------------
    # Layer 1: Coverage
    # ------------------------------------------------------------------

    def _check_coverage(
        self, coverage_score: float, total_gaps: int, required_gaps: int
    ) -> list[GateCheck]:
        checks = []

        # Required items must be 100% covered to pass
        checks.append(GateCheck(
            check_id="COV-01",
            description="Required scope items covered",
            result=CheckResult.PASS if required_gaps == 0 else CheckResult.FAIL,
            expected="0 required gaps",
            actual=f"{required_gaps} required gaps",
            notes=(f"{required_gaps} REQUIRED scope items have no quote or extraction — "
                   f"these are mandatory for this building type") if required_gaps > 0 else None,
            blocking=True,
        ))

        # Overall coverage score
        if coverage_score >= 90:
            cov_result = CheckResult.PASS
        elif coverage_score >= 70:
            cov_result = CheckResult.WARNING
        else:
            cov_result = CheckResult.FAIL

        checks.append(GateCheck(
            check_id="COV-02",
            description="Overall coverage score",
            result=cov_result,
            expected="≥90% coverage",
            actual=f"{coverage_score:.1f}%",
            variance_pct=coverage_score - 90,
            notes=f"Coverage at {coverage_score:.1f}% — {total_gaps} scope items unaccounted for",
            blocking=(cov_result == CheckResult.FAIL),
        ))

        return checks

    # ------------------------------------------------------------------
    # Layer 2: Rate Sanity
    # ------------------------------------------------------------------

    def _check_rates(self, recap: CostRecapSummary) -> list[GateCheck]:
        checks = []
        b = NEWCO_BENCHMARKS

        # Average labor rate check
        if (recap.avg_labor_rate is not None and
                (recap.mechanical_labor_hours + recap.sheet_metal_labor_hours +
                 recap.plumbing_labor_hours) > 0):
            expected_avg = (
                b["labor_rate_mechanical"] * recap.mechanical_labor_hours +
                b["labor_rate_sheet_metal"] * recap.sheet_metal_labor_hours +
                b["labor_rate_plumbing"] * recap.plumbing_labor_hours
            ) / (recap.mechanical_labor_hours + recap.sheet_metal_labor_hours +
                 recap.plumbing_labor_hours)

            variance = abs(recap.avg_labor_rate - expected_avg) / expected_avg
            if variance > b["rate_block_band"]:
                rate_result = CheckResult.FAIL
            elif variance > b["rate_warning_band"]:
                rate_result = CheckResult.WARNING
            else:
                rate_result = CheckResult.PASS

            checks.append(GateCheck(
                check_id="RATE-01",
                description="Blended labor rate vs. benchmark",
                result=rate_result,
                expected=f"${expected_avg:.2f}/hr ±{b['rate_warning_band']*100:.0f}%",
                actual=f"${recap.avg_labor_rate:.2f}/hr",
                variance_pct=round(variance * 100, 1),
                notes=(f"Labor rate {variance*100:.1f}% from benchmark — "
                       f"verify trade mix and prevailing wage requirements")
                      if rate_result != CheckResult.PASS else None,
                blocking=(rate_result == CheckResult.FAIL),
            ))
        else:
            checks.append(GateCheck(
                check_id="RATE-01",
                description="Blended labor rate vs. benchmark",
                result=CheckResult.SKIP,
                expected="$40-50/hr by trade",
                actual="Insufficient data",
                notes="Labor hours not broken down by trade — cannot verify rate",
            ))

        return checks

    # ------------------------------------------------------------------
    # Layer 3: Value Banding
    # ------------------------------------------------------------------

    def _check_value_banding(self, recap: CostRecapSummary) -> list[GateCheck]:
        checks = []
        b = NEWCO_BENCHMARKS

        if recap.sqft and recap.sqft > 0 and recap.total_direct_cost > 0:
            cost_per_sf = recap.total_direct_cost / recap.sqft
            band = b["value_bands"].get(recap.building_type, b["value_bands"]["unknown"])
            low, high = band

            if cost_per_sf < low:
                result = CheckResult.WARNING
                notes = (f"${cost_per_sf:.2f}/SF is below typical range of "
                         f"${low}-${high}/SF for {recap.building_type}. "
                         f"Verify scope is complete — may be missing items.")
            elif cost_per_sf > high:
                result = CheckResult.WARNING
                notes = (f"${cost_per_sf:.2f}/SF exceeds typical range of "
                         f"${low}-${high}/SF for {recap.building_type}. "
                         f"Verify no double-counting or scope creep.")
            else:
                result = CheckResult.PASS
                notes = None

            checks.append(GateCheck(
                check_id="VAL-01",
                description="Estimate value per SF vs. building type benchmark",
                result=result,
                expected=f"${low}-${high}/SF for {recap.building_type}",
                actual=f"${cost_per_sf:.2f}/SF ({recap.total_direct_cost:,.0f} ÷ {recap.sqft:,} SF)",
                notes=notes,
                blocking=False,  # Value banding is always a warning, never a block
            ))
        else:
            checks.append(GateCheck(
                check_id="VAL-01",
                description="Estimate value per SF vs. building type benchmark",
                result=CheckResult.SKIP,
                expected="Building SF required",
                actual="SF not provided",
                notes="Provide building SF to enable value banding check",
            ))

        return checks

    # ------------------------------------------------------------------
    # Layer 4: Margin Check
    # ------------------------------------------------------------------

    def _check_margins(self, recap: CostRecapSummary) -> list[GateCheck]:
        checks = []
        b = NEWCO_BENCHMARKS

        if recap.total_direct_cost > 0:
            # GPM check — overall project
            # Approximate: sub cost as % of direct cost should be under 60%
            # (the rest is own labor + material)
            own_work = recap.total_labor_cost + recap.total_material_cost + recap.total_equipment_cost
            sub_pct = recap.total_sub_cost / recap.total_direct_cost if recap.total_direct_cost > 0 else 0

            if sub_pct > 0.85:
                checks.append(GateCheck(
                    check_id="MARGIN-01",
                    description="Sub cost as % of total estimate",
                    result=CheckResult.WARNING,
                    expected="<85% sub cost",
                    actual=f"{sub_pct*100:.1f}% sub cost",
                    notes="High sub concentration — verify NewCo's own scope and labor are included",
                    blocking=False,
                ))
            else:
                checks.append(GateCheck(
                    check_id="MARGIN-01",
                    description="Sub cost as % of total estimate",
                    result=CheckResult.PASS,
                    expected="<85% sub cost",
                    actual=f"{sub_pct*100:.1f}% sub cost",
                ))

        return checks
