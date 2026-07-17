"""
BID CONFIDENCE CALCULATOR v1.0
Four-vector scoring engine (schema-freeze Q3/Q8).

Four vectors:
  1. Coverage Reliability  (40% default) — Did we find everything?
     Sources: document inventory completeness, Engine 2A blocking gap count,
              Engine 2B validation result.

  2. Quantity Reliability  (35% default) — Are extracted quantities trustworthy?
     Sources: item-level QuantityReliabilityScore rollup,
              cross-document agreement rate, source quality distribution.

  3. Review Integrity      (15% default) — Did estimator focus effort on risk?
     Sources: risk-weighted review coverage (not % total items),
              verified corrections only, conflict resolution rate.
              NEVER gates on review percentage. (Q3)

  4. Pricing Reliability   (10% default) — Can we trust the cost model?
     Sources: vendor quality tier distribution (Q4),
              quote freshness, labor-factor confidence.

All weights configurable by project type (Q8).
Pre-built templates: hospital / military / office / retail / restaurant /
                     warehouse / school / government / default.
Company can override per project.

Output:
  BidConfidenceScore — composite 0-100 + vector breakdown.
  Feeds A-10 gate and proposal header.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from precon.review_layer.models import (
    BID_CONFIDENCE_PROFILES,
    TakeoffReviewItem, ReviewDecision, CrossDocState,
    VendorQualityRecord, QuantityReliabilityScore,
)
from precon.engine2a.engine2a import CoverageBaseline
from precon.engine2b.engine2b import ValidationResult


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------

@dataclass
class ReviewIntegrityInput:
    """Computed from Screen 2 decisions."""
    total_items: int
    high_risk_items: int                # risk_weight > 30
    high_risk_reviewed: int             # high-risk items that were APPROVED or CORRECTED
    verified_corrections: int           # Items estimator corrected (vs just approved)
    unresolved_conflicts: int           # Cross-doc DISAGREE items not resolved
    total_conflicts: int


@dataclass
class PricingReliabilityInput:
    """Computed from vendor quotes."""
    vendor_quality_records: list[VendorQualityRecord]
    covered_csi_sections: int           # CSI sections with at least one vendor
    total_csi_sections: int             # Total CSI sections in bid
    labor_factor_source: str            # "historical" | "benchmark" | "estimated"
    labor_factor_confidence: str        # "HIGH" | "MEDIUM" | "LOW"


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class VectorScore:
    """One vector's contribution to the composite score."""
    name: str
    raw_score: float            # 0-100 before weighting
    weight: float               # Configured weight (0-1)
    weighted_score: float       # raw_score * weight * 100
    components: dict            # What went into it
    notes: str = ""


@dataclass
class BidConfidenceScore:
    """
    Composite bid confidence score.
    0-100. Displayed on proposal header and A-10 gate.
    """
    project_id: str
    composite_score: float          # 0-100 weighted composite
    confidence_tier: str            # HIGH (80+) / MEDIUM (60-79) / LOW (<60)

    # Vector breakdown
    coverage_vector: VectorScore
    quantity_vector: VectorScore
    review_integrity_vector: VectorScore
    pricing_vector: VectorScore

    # Configuration
    profile_used: str               # "hospital" | "office" | "default" | "custom"
    weights_used: dict

    # Submission readiness
    submittable: bool               # composite_score >= submission_threshold
    submission_threshold: float     # Configurable (default 70.0)

    def summary(self) -> str:
        return (
            f"Bid Confidence: {self.composite_score:.1f}/100 ({self.confidence_tier}) | "
            f"Coverage: {self.coverage_vector.raw_score:.0f} | "
            f"Quantity: {self.quantity_vector.raw_score:.0f} | "
            f"Review: {self.review_integrity_vector.raw_score:.0f} | "
            f"Pricing: {self.pricing_vector.raw_score:.0f}"
        )


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class BidConfidenceCalculator:
    """
    Computes the four-vector bid confidence score.
    All weights configurable. Pre-built project-type templates available.
    """

    def compute(
        self,
        project_id: str,
        building_type: str,
        coverage_baseline: CoverageBaseline,
        validation_result: ValidationResult,
        takeoff_items: list[TakeoffReviewItem],
        review_integrity: ReviewIntegrityInput,
        pricing_input: PricingReliabilityInput,
        weight_override: Optional[dict] = None,
        submission_threshold: float = 70.0,
    ) -> BidConfidenceScore:
        """
        Compute composite bid confidence score.

        weight_override: dict with keys coverage_reliability, quantity_reliability,
                         review_integrity, pricing_reliability. Must sum to 1.0.
                         If None, uses building_type profile.
        """
        # Select weights
        if weight_override:
            weights = weight_override
            profile_name = "custom"
        else:
            weights = BID_CONFIDENCE_PROFILES.get(
                building_type, BID_CONFIDENCE_PROFILES["default"]
            )
            profile_name = building_type if building_type in BID_CONFIDENCE_PROFILES else "default"

        # Compute each vector
        coverage = self._compute_coverage_vector(
            coverage_baseline, validation_result, weights["coverage_reliability"]
        )
        quantity = self._compute_quantity_vector(
            takeoff_items, weights["quantity_reliability"]
        )
        review = self._compute_review_integrity_vector(
            review_integrity, weights["review_integrity"]
        )
        pricing = self._compute_pricing_vector(
            pricing_input, weights["pricing_reliability"]
        )

        composite = (
            coverage.weighted_score +
            quantity.weighted_score +
            review.weighted_score +
            pricing.weighted_score
        )
        composite = round(min(100.0, max(0.0, composite)), 1)

        tier = "HIGH" if composite >= 80 else "MEDIUM" if composite >= 60 else "LOW"

        return BidConfidenceScore(
            project_id=project_id,
            composite_score=composite,
            confidence_tier=tier,
            coverage_vector=coverage,
            quantity_vector=quantity,
            review_integrity_vector=review,
            pricing_vector=pricing,
            profile_used=profile_name,
            weights_used=weights,
            submittable=composite >= submission_threshold,
            submission_threshold=submission_threshold,
        )

    # ------------------------------------------------------------------
    # Vector 1 — Coverage Reliability (default 40%)
    # ------------------------------------------------------------------

    def _compute_coverage_vector(
        self,
        baseline: CoverageBaseline,
        validation: ValidationResult,
        weight: float,
    ) -> VectorScore:
        """
        Did we find everything?
        Penalizes unresolved blocking gaps. Rewards complete document inventory.
        """
        # Base: document coverage score from Engine 2A
        base = baseline.document_coverage_score  # 0-100

        # Penalty: blocking gaps that survived to Engine 2B
        blocking_penalty = min(40.0, validation.blocking_gap_count * 15.0)

        # Penalty: unresolved advisory gaps (softer)
        advisory_penalty = min(10.0, validation.advisory_gap_count * 3.0)

        # Bonus: zero blocking gaps
        zero_gap_bonus = 5.0 if validation.blocking_gap_count == 0 else 0.0

        raw = max(0.0, base - blocking_penalty - advisory_penalty + zero_gap_bonus)
        raw = min(100.0, raw)

        return VectorScore(
            name="coverage_reliability",
            raw_score=round(raw, 1),
            weight=weight,
            weighted_score=round(raw * weight, 2),
            components={
                "document_coverage_base": base,
                "blocking_gap_penalty": blocking_penalty,
                "advisory_gap_penalty": advisory_penalty,
                "zero_gap_bonus": zero_gap_bonus,
                "blocking_gaps": validation.blocking_gap_count,
                "advisory_gaps": validation.advisory_gap_count,
            },
        )

    # ------------------------------------------------------------------
    # Vector 2 — Quantity Reliability (default 35%)
    # ------------------------------------------------------------------

    def _compute_quantity_vector(
        self,
        takeoff_items: list[TakeoffReviewItem],
        weight: float,
    ) -> VectorScore:
        """
        Are extracted quantities trustworthy?
        Item-level rollup of QuantityReliabilityScore. (Q3)
        Cross-doc state: AGREE positive, DISAGREE tracked, NO_SECOND_SOURCE neutral.
        """
        if not takeoff_items:
            return VectorScore(
                name="quantity_reliability",
                raw_score=50.0,  # Unknown — no items
                weight=weight,
                weighted_score=round(50.0 * weight, 2),
                components={"note": "No takeoff items"},
            )

        items_with_scores = [
            i for i in takeoff_items
            if i.quantity_reliability is not None
        ]

        if not items_with_scores:
            return VectorScore(
                name="quantity_reliability",
                raw_score=50.0,
                weight=weight,
                weighted_score=round(50.0 * weight, 2),
                components={"note": "No quantity reliability scores computed"},
            )

        # Weighted average item reliability (weight by risk — high-risk items matter more)
        total_weight = 0
        weighted_sum = 0.0
        agree_count = 0
        disagree_count = 0
        no_second_source = 0

        for item in items_with_scores:
            qr = item.quantity_reliability
            item_weight = max(1, qr.risk_weight)
            weighted_sum += qr.item_reliability_score * item_weight
            total_weight += item_weight

            if qr.cross_doc_state == CrossDocState.AGREE:
                agree_count += 1
            elif qr.cross_doc_state == CrossDocState.DISAGREE:
                disagree_count += 1
            else:
                no_second_source += 1

        base = weighted_sum / total_weight if total_weight > 0 else 50.0

        # Cross-doc agreement bonus/penalty
        total = len(items_with_scores)
        agree_rate = agree_count / total if total > 0 else 0
        disagree_rate = disagree_count / total if total > 0 else 0

        agreement_adjustment = (agree_rate * 5.0) - (disagree_rate * 10.0)

        raw = max(0.0, min(100.0, base + agreement_adjustment))

        return VectorScore(
            name="quantity_reliability",
            raw_score=round(raw, 1),
            weight=weight,
            weighted_score=round(raw * weight, 2),
            components={
                "weighted_avg_item_reliability": round(base, 1),
                "agree_count": agree_count,
                "disagree_count": disagree_count,
                "no_second_source_count": no_second_source,
                "agree_rate": round(agree_rate, 2),
                "disagree_rate": round(disagree_rate, 2),
                "agreement_adjustment": round(agreement_adjustment, 2),
                "items_scored": len(items_with_scores),
            },
        )

    # ------------------------------------------------------------------
    # Vector 3 — Review Integrity (default 15%)
    # ------------------------------------------------------------------

    def _compute_review_integrity_vector(
        self,
        review: ReviewIntegrityInput,
        weight: float,
    ) -> VectorScore:
        """
        Did estimator focus effort on risk? (Q3)
        NEVER use % of total items reviewed. Always % of high-risk items reviewed.
        Rewards verified corrections. Penalizes unresolved conflicts.
        """
        # Risk-weighted review coverage (the only coverage metric that matters)
        if review.high_risk_items > 0:
            risk_coverage = review.high_risk_reviewed / review.high_risk_items
        else:
            risk_coverage = 1.0  # No high-risk items = perfect coverage

        base = risk_coverage * 80.0  # Max 80 from coverage alone

        # Correction quality bonus — estimator actively improved AI output
        correction_rate = (
            review.verified_corrections / review.high_risk_reviewed
            if review.high_risk_reviewed > 0 else 0
        )
        correction_bonus = min(15.0, correction_rate * 20.0)

        # Conflict resolution bonus
        if review.total_conflicts > 0:
            conflict_resolution_rate = (
                (review.total_conflicts - review.unresolved_conflicts) /
                review.total_conflicts
            )
            conflict_bonus = conflict_resolution_rate * 5.0
        else:
            conflict_bonus = 5.0  # No conflicts = full bonus

        raw = max(0.0, min(100.0, base + correction_bonus + conflict_bonus))

        return VectorScore(
            name="review_integrity",
            raw_score=round(raw, 1),
            weight=weight,
            weighted_score=round(raw * weight, 2),
            components={
                "high_risk_items": review.high_risk_items,
                "high_risk_reviewed": review.high_risk_reviewed,
                "risk_coverage_pct": round(risk_coverage * 100, 1),
                "verified_corrections": review.verified_corrections,
                "correction_bonus": round(correction_bonus, 2),
                "conflict_bonus": round(conflict_bonus, 2),
                "unresolved_conflicts": review.unresolved_conflicts,
                "note": "Risk-weighted coverage only. Never % total items reviewed.",
            },
        )

    # ------------------------------------------------------------------
    # Vector 4 — Pricing Reliability (default 10%)
    # ------------------------------------------------------------------

    def _compute_pricing_vector(
        self,
        pricing: PricingReliabilityInput,
        weight: float,
    ) -> VectorScore:
        """
        Can we trust the cost model?
        Vendor quality tier distribution (Q4) + labor factor confidence.
        """
        # Vendor coverage quality — average tier weight across covered sections
        if pricing.vendor_quality_records:
            avg_tier_weight = sum(
                v.tier_weight for v in pricing.vendor_quality_records
            ) / len(pricing.vendor_quality_records)
        else:
            avg_tier_weight = 0.0

        vendor_score = avg_tier_weight * 60.0  # Max 60 from vendors

        # Scope coverage: do we have vendors for all CSI sections?
        if pricing.total_csi_sections > 0:
            scope_coverage = pricing.covered_csi_sections / pricing.total_csi_sections
        else:
            scope_coverage = 1.0

        scope_score = scope_coverage * 25.0  # Max 25

        # Labor factor confidence
        labor_score_map = {"HIGH": 15.0, "MEDIUM": 10.0, "LOW": 5.0}
        labor_score = labor_score_map.get(pricing.labor_factor_confidence, 5.0)

        raw = max(0.0, min(100.0, vendor_score + scope_score + labor_score))

        # Tier distribution summary
        tier_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
        for v in pricing.vendor_quality_records:
            tier_counts[v.tier] = tier_counts.get(v.tier, 0) + 1

        return VectorScore(
            name="pricing_reliability",
            raw_score=round(raw, 1),
            weight=weight,
            weighted_score=round(raw * weight, 2),
            components={
                "avg_vendor_tier_weight": round(avg_tier_weight, 2),
                "vendor_score": round(vendor_score, 1),
                "scope_coverage_pct": round(scope_coverage * 100, 1),
                "scope_score": round(scope_score, 1),
                "labor_factor_source": pricing.labor_factor_source,
                "labor_factor_confidence": pricing.labor_factor_confidence,
                "labor_score": labor_score,
                "vendor_tier_distribution": tier_counts,
            },
        )
