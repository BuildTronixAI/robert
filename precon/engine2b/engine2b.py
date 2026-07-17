"""
ENGINE 2B — COVERAGE VALIDATION v1.0
Runs post-Screen 3 (all takeoff items confirmed, all cost codes assigned).

Purpose:
  Re-runs coverage check against the APPROVED takeoff (not raw extraction).
  Engine 2A ran against what the AI found. Engine 2B runs against what the
  estimator approved. This is the final gate before A-10.

Difference from Engine 2A:
  Engine 2A  — compares document inventory vs expected scope (feeds Screen 2.5)
  Engine 2B  — compares approved takeoff vs expected scope (feeds A-10 gate)
  If an item was in Engine 2A omissions and estimator dismissed it in Screen 2.5,
  Engine 2B still validates whether the approved takeoff is complete enough to submit.

Output:
  ValidationResult — pass/warning/block with specific gap analysis.
  Feeds A-10 gate directly.

Gate logic:
  BLOCK   — any SOURCE_DERIVED or CROSS_REFERENCE omission not resolved in Screen 2.5
  WARNING — heuristic gaps remain unresolved (advisory — can override with reason)
  PASS    — all blocking gaps resolved, bid confidence computable
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime, timezone

from precon.review_layer.models import (
    OmissionConfidence, CoverageStatus, GateResult,
)
from precon.engine2a.engine2a import (
    OmissionFinding, CoverageBaseline,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------

@dataclass
class ApprovedTakeoffItem:
    """One approved/corrected item from Screen 2 + Screen 3."""
    item_id: str
    csi_section: str
    description: str
    confirmed_cost_code: str
    quantity: float
    unit: str
    unit_labor: float
    unit_material: float
    unit_equipment: float
    total_cost: float
    source_sheet: str
    screen2_decision: str   # APPROVED | CORRECTED
    screen3_decision: str   # APPROVED | CORRECTED


@dataclass
class ResolvedCoverageItem:
    """Screen 2.5 decision record — what estimator resolved from Engine 2A findings."""
    finding_id: str         # Links to OmissionFinding.finding_id
    csi_section: str
    resolution: str         # ADDED | EXCLUDED | DISMISSED
    omission_confidence: OmissionConfidence
    resolved_by: str
    resolved_at: str
    resolution_notes: str = ""


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class ValidationGap:
    """A gap that survived into the approved takeoff — still unresolved."""
    gap_id: str
    csi_section: str
    description: str
    omission_confidence: OmissionConfidence
    blocking: bool
    original_finding_id: str
    reason_unresolved: str      # Why it's still a gap
    estimated_value: float
    risk_weight: int


@dataclass
class ValidationResult:
    """
    Full output of Engine 2B.
    Feeds A-10 gate directly.
    """
    validation_id: str
    project_id: str
    run_at: str
    gate_result: GateResult

    # Remaining gaps after Screen 2.5 resolutions
    blocking_gaps: list[ValidationGap]      # SOURCE_DERIVED + CROSS_REFERENCE unresolved
    advisory_gaps: list[ValidationGap]      # HEURISTIC unresolved

    # Coverage metrics (approved takeoff)
    approved_csi_sections: list[str]        # What's actually in the approved takeoff
    total_approved_value: float

    # Summary
    blocking_gap_count: int = 0
    advisory_gap_count: int = 0
    blocking_reason: Optional[str] = None
    warning_reason: Optional[str] = None

    def is_blocked(self) -> bool:
        return self.gate_result == GateResult.BLOCK

    def is_warning(self) -> bool:
        return self.gate_result == GateResult.WARNING

    def is_passing(self) -> bool:
        return self.gate_result == GateResult.PASS


# ---------------------------------------------------------------------------
# Engine 2B Core
# ---------------------------------------------------------------------------

class Engine2B:
    """
    Coverage Validation Engine.
    Runs post-Screen 3. Feeds A-10.
    """

    def run(
        self,
        project_id: str,
        baseline: CoverageBaseline,                     # Engine 2A output
        approved_takeoff: list[ApprovedTakeoffItem],    # Screen 2+3 output
        resolved_items: list[ResolvedCoverageItem],     # Screen 2.5 decisions
    ) -> ValidationResult:
        """
        Compare approved takeoff against Engine 2A baseline.
        Check all blocking omissions were resolved in Screen 2.5.
        """
        # Index approved takeoff by CSI division
        approved_csi = set()
        total_value = 0.0
        for item in approved_takeoff:
            approved_csi.add(item.csi_section[:4] + "0000")
            total_value += item.total_cost

        # Index Screen 2.5 resolutions by finding_id
        resolved_by_id: dict[str, ResolvedCoverageItem] = {
            r.finding_id: r for r in resolved_items
        }

        blocking_gaps: list[ValidationGap] = []
        advisory_gaps: list[ValidationGap] = []

        for omission in baseline.omissions:
            csi_key = omission.csi_section[:4] + "0000"
            resolution = resolved_by_id.get(omission.finding_id)

            # Check 1: Was it resolved in Screen 2.5?
            if resolution:
                if resolution.resolution == "ADDED":
                    # Should now be in approved takeoff
                    if csi_key not in approved_csi:
                        # Estimator said ADDED but it's not in takeoff — gap
                        gap = ValidationGap(
                            gap_id=str(uuid.uuid4()),
                            csi_section=omission.csi_section,
                            description=omission.description,
                            omission_confidence=omission.omission_confidence,
                            blocking=omission.blocking,
                            original_finding_id=omission.finding_id,
                            reason_unresolved=(
                                f"Estimator marked ADDED in Screen 2.5 but "
                                f"CSI section {omission.csi_section} not found in approved takeoff"
                            ),
                            estimated_value=omission.estimated_value,
                            risk_weight=omission.risk_weight,
                        )
                        if omission.blocking:
                            blocking_gaps.append(gap)
                        else:
                            advisory_gaps.append(gap)
                # EXCLUDED or DISMISSED = resolved intentionally, not a gap
                continue

            # Check 2: Not resolved in Screen 2.5 — is it covered by approved takeoff?
            if csi_key in approved_csi:
                # Covered by takeoff even without explicit Screen 2.5 resolution
                continue

            # Check 3: Genuine gap — unresolved and not in takeoff
            gap = ValidationGap(
                gap_id=str(uuid.uuid4()),
                csi_section=omission.csi_section,
                description=omission.description,
                omission_confidence=omission.omission_confidence,
                blocking=omission.blocking,
                original_finding_id=omission.finding_id,
                reason_unresolved=(
                    f"No Screen 2.5 resolution and CSI section "
                    f"{omission.csi_section} absent from approved takeoff"
                ),
                estimated_value=omission.estimated_value,
                risk_weight=omission.risk_weight,
            )

            if omission.blocking:
                blocking_gaps.append(gap)
            else:
                advisory_gaps.append(gap)

        # Determine gate result
        if blocking_gaps:
            gate = GateResult.BLOCK
            blocking_reason = (
                f"{len(blocking_gaps)} SOURCE_DERIVED or CROSS_REFERENCE gap(s) "
                f"unresolved. Resolve in Screen 2.5 before advancing to A-10."
            )
            warning_reason = None
        elif advisory_gaps:
            gate = GateResult.WARNING
            blocking_reason = None
            warning_reason = (
                f"{len(advisory_gaps)} heuristic gap(s) unresolved. "
                f"Advisory only — may advance with documented rationale."
            )
        else:
            gate = GateResult.PASS
            blocking_reason = None
            warning_reason = None

        return ValidationResult(
            validation_id=str(uuid.uuid4()),
            project_id=project_id,
            run_at=_now(),
            gate_result=gate,
            blocking_gaps=blocking_gaps,
            advisory_gaps=advisory_gaps,
            approved_csi_sections=list(approved_csi),
            total_approved_value=total_value,
            blocking_gap_count=len(blocking_gaps),
            advisory_gap_count=len(advisory_gaps),
            blocking_reason=blocking_reason,
            warning_reason=warning_reason,
        )
