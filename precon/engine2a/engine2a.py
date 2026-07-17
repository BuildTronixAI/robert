"""
ENGINE 2A — COVERAGE BASELINE v1.0
Runs post-Engine 1 (scope extraction complete).

Purpose:
  Compares the extracted scope items + document inventory against building-type
  expectations to produce the coverage baseline used by Screen 2.5.

Omission Confidence Grading (schema-freeze Q2):
  SOURCE_DERIVED   — Item exists in an actual document (schedule row, spec section,
                     drawing annotation) but Engine 1 did not extract it.
                     ~99% real miss. BLOCKING.
  CROSS_REFERENCE  — Item inferred from two documents in agreement
                     (e.g. spec requires commissioning agent, no Cx vendor in registry).
                     ~70% real miss. BLOCKING.
  HEURISTIC        — Building-type expectation only, no document evidence.
                     ~30% real. ADVISORY ONLY. Never blocking.

Coverage Split (schema-freeze Q1):
  Document coverage:  REQUIRED if found in documents. BLOCKING.
  Scope expectations: Building-type heuristics. ADVISORY ONLY. Never blocking.

Output:
  CoverageBaseline — feeds Screen 2.5 Tab A (missing scope) and Tab B (unverified scope).

Engine 2B (post-Screen 3) re-runs against approved takeoff to produce final validation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid
from datetime import datetime, timezone

from precon.review_layer.models import (
    OmissionConfidence, CoverageReviewItem, CoverageStatus,
)
from precon.engine2.engine2 import (
    BuildingType, ProjectMode, ScopeExpectation,
    get_expected_scope, ExpectedScopeItem,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------

@dataclass
class DocumentInventoryItem:
    """One document in the project's document registry (from A-0)."""
    doc_id: str
    filename: str
    doc_type: str           # DRAWING | SPEC | ADDENDUM | VENDOR_QUOTE | OTHER
    csi_sections: list[str] # CSI sections found in this document
    sheet_refs: list[str]   # e.g. ["M-101", "M-102", "P-201"]
    schedule_rows: list[str] # Row IDs found in schedules (e.g. "AHU-1", "FCU-14")
    raw_text_snippets: dict  # csi_section -> list of text excerpts


@dataclass
class ExtractedScopeItem:
    """One item from Engine 1 output."""
    item_id: str
    csi_section: str
    description: str
    source_doc_id: str
    source_sheet: str
    extraction_method: str  # "schedule_row" | "spec_section" | "drawing_annotation" | "ai_semantic"
    confidence: str         # HIGH | MEDIUM | LOW
    quantity: Optional[float] = None
    unit: Optional[str] = None


@dataclass
class VendorQuoteRecord:
    """Vendor quote from Quote Intake engine."""
    vendor_id: str
    vendor_name: str
    csi_section: str
    quote_date: str
    quote_amount: float
    scope_description: str


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class OmissionFinding:
    """
    One omission identified by Engine 2A.
    Maps directly to a CoverageReviewItem for Screen 2.5.
    """
    finding_id: str
    project_id: str
    csi_section: str
    description: str
    omission_confidence: OmissionConfidence
    blocking: bool                  # True for SOURCE_DERIVED + CROSS_REFERENCE
    source_evidence: str            # Grounds for confidence grade
    estimated_value: float
    risk_weight: int

    # For SOURCE_DERIVED: which document contains it
    source_doc_id: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[str] = None

    # For CROSS_REFERENCE: which two documents agree
    cross_ref_doc_a: Optional[str] = None
    cross_ref_doc_b: Optional[str] = None
    cross_ref_reasoning: Optional[str] = None

    # For HEURISTIC: building type that drives expectation
    heuristic_building_type: Optional[str] = None
    heuristic_expectation_level: Optional[str] = None  # REQUIRED | TYPICAL | OPTIONAL


@dataclass
class UnverifiedScopeItem:
    """
    Item Engine 1 extracted but cannot be cross-referenced to a second source.
    Feeds Screen 2.5 Tab B — estimator must provide citation.
    """
    item_id: str
    project_id: str
    takeoff_item_id: str        # Link to Screen 2 item
    csi_section: str
    description: str
    source_sheet: str           # Primary source
    cross_check_result: str     # AGREE | NO_SECOND_SOURCE | DISAGREE
    estimated_value: float
    risk_weight: int

    # Verification data
    verified_sheet: Optional[str] = None
    verified_grid_row: Optional[str] = None
    disagreement_details: Optional[str] = None  # If DISAGREE: what conflicts


@dataclass
class CoverageBaseline:
    """
    Full output of Engine 2A.
    Feeds Screen 2.5 directly.
    """
    baseline_id: str
    project_id: str
    building_type: str
    mode: str                   # "sub" | "gc"
    run_at: str

    # Tab A — Missing Scope (omissions)
    omissions: list[OmissionFinding]

    # Tab B — Unverified Scope (items needing citation)
    unverified: list[UnverifiedScopeItem]

    # Summary counts
    source_derived_count: int = 0
    cross_reference_count: int = 0
    heuristic_count: int = 0
    blocking_count: int = 0     # SOURCE_DERIVED + CROSS_REFERENCE
    unverified_count: int = 0

    # Coverage score (document coverage only — heuristics excluded)
    document_coverage_score: float = 0.0    # 0-100
    heuristic_coverage_score: float = 0.0   # 0-100 (informational only)

    def to_coverage_review_items(self) -> list[CoverageReviewItem]:
        """Convert omissions to CoverageReviewItem objects for Screen 2.5 Tab A."""
        items = []
        for o in self.omissions:
            items.append(CoverageReviewItem(
                item_id=o.finding_id,
                project_id=o.project_id,
                tab="missing_scope",
                omission_confidence=o.omission_confidence,
                source_evidence=o.source_evidence,
                blocking=o.blocking,
                description=o.description,
                csi_section=o.csi_section,
                estimated_value=o.estimated_value,
                risk_weight=o.risk_weight,
                status=CoverageStatus.PENDING,
            ))
        return items


# ---------------------------------------------------------------------------
# Engine 2A Core
# ---------------------------------------------------------------------------

# Risk weight by omission type
OMISSION_RISK_WEIGHTS = {
    OmissionConfidence.SOURCE_DERIVED:  40,
    OmissionConfidence.CROSS_REFERENCE: 30,
    OmissionConfidence.HEURISTIC:       15,
}

# Rough value estimates by CSI division (for sorting/prioritization)
CSI_VALUE_ESTIMATES = {
    "210000": 45000,   # Fire Suppression
    "220000": 85000,   # Plumbing
    "230000": 180000,  # HVAC
    "240000": 35000,   # HVAC Controls
    "250000": 28000,   # Integrated Automation
    "260000": 95000,   # Electrical
    "270000": 42000,   # Communications
    "280000": 38000,   # Electronic Safety/Security
    "310000": 55000,   # Earthwork
    "320000": 48000,   # Exterior Improvements
    "330000": 62000,   # Utilities
}


class Engine2A:
    """
    Coverage Baseline Engine.
    Runs post-Engine 1. Feeds Screen 2.5.
    """

    def run(
        self,
        project_id: str,
        building_type: str,
        mode: str,
        documents: list[DocumentInventoryItem],
        extracted_items: list[ExtractedScopeItem],
        vendor_quotes: list[VendorQuoteRecord],
    ) -> CoverageBaseline:
        """
        Full coverage baseline run.

        1. Build expected scope from building type + mode
        2. Compare extracted items against expected scope
        3. Scan document inventory for items not extracted (SOURCE_DERIVED)
        4. Cross-reference spec + vendor registry (CROSS_REFERENCE)
        5. Flag remaining expected items with no evidence (HEURISTIC)
        6. Identify unverified items for Tab B
        """
        bt = BuildingType(building_type) if building_type in [b.value for b in BuildingType] else BuildingType.UNKNOWN
        pm = ProjectMode(mode)
        expected = get_expected_scope(bt, pm)

        # Index extracted items by CSI section
        extracted_by_csi: dict[str, list[ExtractedScopeItem]] = {}
        for item in extracted_items:
            key = item.csi_section[:4] + "0000"  # Normalize to division level
            extracted_by_csi.setdefault(key, []).append(item)

        # Index documents by CSI section
        docs_by_csi: dict[str, list[DocumentInventoryItem]] = {}
        for doc in documents:
            for csi in doc.csi_sections:
                key = csi[:4] + "0000"
                docs_by_csi.setdefault(key, []).append(doc)

        # Index vendor quotes by CSI section
        quotes_by_csi: dict[str, list[VendorQuoteRecord]] = {}
        for q in vendor_quotes:
            key = q.csi_section[:4] + "0000"
            quotes_by_csi.setdefault(key, []).append(q)

        omissions: list[OmissionFinding] = []
        unverified: list[UnverifiedScopeItem] = []

        # --- Pass 1: Find omissions per expected scope item ---
        for exp in expected:
            csi_key = exp.csi_section[:4] + "0000"
            extracted = extracted_by_csi.get(csi_key, [])
            docs = docs_by_csi.get(csi_key, [])
            quotes = quotes_by_csi.get(csi_key, [])

            if extracted:
                # Already extracted — not an omission
                continue

            # Classify omission confidence
            omission = self._classify_omission(
                project_id=project_id,
                exp=exp,
                csi_key=csi_key,
                docs=docs,
                quotes=quotes,
                building_type=building_type,
            )

            if omission:
                omissions.append(omission)

        # --- Pass 2: Find unverified scope items for Tab B ---
        for item in extracted_items:
            csi_key = item.csi_section[:4] + "0000"
            docs = docs_by_csi.get(csi_key, [])

            uv = self._check_cross_reference(
                project_id=project_id,
                item=item,
                docs=docs,
            )
            if uv:
                unverified.append(uv)

        # --- Compute summary counts ---
        source_derived = [o for o in omissions if o.omission_confidence == OmissionConfidence.SOURCE_DERIVED]
        cross_reference = [o for o in omissions if o.omission_confidence == OmissionConfidence.CROSS_REFERENCE]
        heuristic = [o for o in omissions if o.omission_confidence == OmissionConfidence.HEURISTIC]
        blocking = [o for o in omissions if o.blocking]

        # Document coverage score: expected items with document evidence / total expected
        expected_with_docs = sum(1 for exp in expected if docs_by_csi.get(exp.csi_section[:4] + "0000"))
        doc_coverage = (expected_with_docs / len(expected) * 100) if expected else 100.0

        # Heuristic coverage: extracted / expected (informational only)
        heuristic_covered = sum(1 for exp in expected if extracted_by_csi.get(exp.csi_section[:4] + "0000"))
        heuristic_cov = (heuristic_covered / len(expected) * 100) if expected else 100.0

        return CoverageBaseline(
            baseline_id=str(uuid.uuid4()),
            project_id=project_id,
            building_type=building_type,
            mode=mode,
            run_at=_now(),
            omissions=omissions,
            unverified=unverified,
            source_derived_count=len(source_derived),
            cross_reference_count=len(cross_reference),
            heuristic_count=len(heuristic),
            blocking_count=len(blocking),
            unverified_count=len(unverified),
            document_coverage_score=round(doc_coverage, 1),
            heuristic_coverage_score=round(heuristic_cov, 1),
        )

    def _classify_omission(
        self,
        project_id: str,
        exp: ExpectedScopeItem,
        csi_key: str,
        docs: list[DocumentInventoryItem],
        quotes: list[VendorQuoteRecord],
        building_type: str,
    ) -> Optional[OmissionFinding]:
        """
        Classify an omission finding with appropriate confidence grade.
        Returns None if no omission (item is covered).
        """
        finding_id = str(uuid.uuid4())
        est_value = CSI_VALUE_ESTIMATES.get(csi_key, 25000)

        # --- SOURCE_DERIVED: item found in document but not extracted ---
        # Check schedule rows (highest specificity)
        for doc in docs:
            for row in doc.schedule_rows:
                if self._row_matches_csi(row, exp.csi_section):
                    return OmissionFinding(
                        finding_id=finding_id,
                        project_id=project_id,
                        csi_section=exp.csi_section,
                        description=f"{exp.description} — found in schedule ({row}) but not extracted",
                        omission_confidence=OmissionConfidence.SOURCE_DERIVED,
                        blocking=True,
                        source_evidence=f"Schedule row '{row}' in {doc.filename} references {exp.csi_section}",
                        estimated_value=est_value,
                        risk_weight=OMISSION_RISK_WEIGHTS[OmissionConfidence.SOURCE_DERIVED],
                        source_doc_id=doc.doc_id,
                        source_sheet=doc.sheet_refs[0] if doc.sheet_refs else None,
                        source_row=row,
                    )

        # Check spec sections
        for doc in docs:
            if exp.csi_section in doc.csi_sections:
                snippets = doc.raw_text_snippets.get(exp.csi_section, [])
                if snippets:
                    return OmissionFinding(
                        finding_id=finding_id,
                        project_id=project_id,
                        csi_section=exp.csi_section,
                        description=f"{exp.description} — spec section present but not extracted",
                        omission_confidence=OmissionConfidence.SOURCE_DERIVED,
                        blocking=True,
                        source_evidence=f"Spec section {exp.csi_section} found in {doc.filename} with content",
                        estimated_value=est_value,
                        risk_weight=OMISSION_RISK_WEIGHTS[OmissionConfidence.SOURCE_DERIVED],
                        source_doc_id=doc.doc_id,
                        source_sheet=None,
                        source_row=None,
                    )

        # --- CROSS_REFERENCE: two documents agree on scope but no extraction ---
        cross_ref = self._find_cross_reference(exp, csi_key, docs, quotes)
        if cross_ref:
            doc_a_name, doc_b_name, reasoning = cross_ref
            return OmissionFinding(
                finding_id=finding_id,
                project_id=project_id,
                csi_section=exp.csi_section,
                description=f"{exp.description} — inferred from cross-document reference",
                omission_confidence=OmissionConfidence.CROSS_REFERENCE,
                blocking=True,
                source_evidence=f"Cross-reference: {reasoning}",
                estimated_value=est_value,
                risk_weight=OMISSION_RISK_WEIGHTS[OmissionConfidence.CROSS_REFERENCE],
                cross_ref_doc_a=doc_a_name,
                cross_ref_doc_b=doc_b_name,
                cross_ref_reasoning=reasoning,
            )

        # --- HEURISTIC: only building-type expectation, no document evidence ---
        # Only fire for REQUIRED and TYPICAL expectations (not OPTIONAL/RARE)
        if exp.expectation in (ScopeExpectation.REQUIRED, ScopeExpectation.TYPICAL):
            return OmissionFinding(
                finding_id=finding_id,
                project_id=project_id,
                csi_section=exp.csi_section,
                description=f"{exp.description} — expected for {building_type} but not found",
                omission_confidence=OmissionConfidence.HEURISTIC,
                blocking=False,  # ADVISORY ONLY — never blocks
                source_evidence=f"Building-type expectation: {exp.reasoning}",
                estimated_value=est_value,
                risk_weight=OMISSION_RISK_WEIGHTS[OmissionConfidence.HEURISTIC],
                heuristic_building_type=building_type,
                heuristic_expectation_level=exp.expectation.value,
            )

        # OPTIONAL / RARE with no evidence → not reported
        return None

    def _find_cross_reference(
        self,
        exp: ExpectedScopeItem,
        csi_key: str,
        docs: list[DocumentInventoryItem],
        quotes: list[VendorQuoteRecord],
    ) -> Optional[tuple[str, str, str]]:
        """
        Look for two independent document references that together imply scope.
        Returns (doc_a_name, doc_b_name, reasoning) or None.
        """
        # Pattern 1: Spec requires a subcontractor type + no vendor quote exists
        spec_docs = [d for d in docs if d.doc_type == "SPEC"]
        for spec in spec_docs:
            for keyword in (exp.triggers or []):
                snippets = spec.raw_text_snippets.get(exp.csi_section, [])
                if any(keyword.lower() in s.lower() for s in snippets):
                    # Spec mentions this scope — if no vendor quote, that's a cross-ref signal
                    if not quotes:
                        return (
                            spec.filename,
                            "Vendor Registry",
                            f"Spec {spec.filename} references '{keyword}' in section {exp.csi_section}, "
                            f"but no vendor quote exists for this CSI section"
                        )

        # Pattern 2: Drawing sheet reference + addendum confirms scope change
        drawing_docs = [d for d in docs if d.doc_type == "DRAWING"]
        addendum_docs = [d for d in docs if d.doc_type == "ADDENDUM"]

        for drawing in drawing_docs:
            if exp.csi_section in drawing.csi_sections:
                for addendum in addendum_docs:
                    if exp.csi_section in addendum.csi_sections:
                        return (
                            drawing.filename,
                            addendum.filename,
                            f"Drawing {drawing.filename} and Addendum {addendum.filename} "
                            f"both reference section {exp.csi_section}"
                        )

        return None

    def _check_cross_reference(
        self,
        project_id: str,
        item: ExtractedScopeItem,
        docs: list[DocumentInventoryItem],
    ) -> Optional[UnverifiedScopeItem]:
        """
        Check if an extracted item can be cross-referenced to a second source.
        Items with NO_SECOND_SOURCE or DISAGREE feed Screen 2.5 Tab B.
        """
        csi_key = item.csi_section[:4] + "0000"
        primary_doc_type = None
        secondary_refs = []

        # Find primary source type
        for doc in docs:
            if doc.doc_id == item.source_doc_id:
                primary_doc_type = doc.doc_type
            elif csi_key in [c[:4] + "0000" for c in doc.csi_sections]:
                secondary_refs.append(doc)

        # Only flag items extracted from lower-confidence sources
        if item.extraction_method in ("ai_semantic",) or item.confidence == "LOW":
            cross_check = "NO_SECOND_SOURCE" if not secondary_refs else "AGREE"

            # DISAGREE: same CSI section in secondary but conflicting data
            if secondary_refs:
                # Simplified disagreement check — in production would compare quantities
                for sec_doc in secondary_refs:
                    if sec_doc.doc_type == primary_doc_type:
                        # Same doc type in two places = potential conflict
                        cross_check = "DISAGREE"
                        return UnverifiedScopeItem(
                            item_id=str(uuid.uuid4()),
                            project_id=project_id,
                            takeoff_item_id=item.item_id,
                            csi_section=item.csi_section,
                            description=item.description,
                            source_sheet=item.source_sheet,
                            cross_check_result="DISAGREE",
                            estimated_value=CSI_VALUE_ESTIMATES.get(csi_key, 15000),
                            risk_weight=30,
                            disagreement_details=(
                                f"Same CSI section found in both {item.source_doc_id} "
                                f"and {sec_doc.filename} — quantities may conflict"
                            ),
                        )

            if cross_check == "NO_SECOND_SOURCE":
                return UnverifiedScopeItem(
                    item_id=str(uuid.uuid4()),
                    project_id=project_id,
                    takeoff_item_id=item.item_id,
                    csi_section=item.csi_section,
                    description=item.description,
                    source_sheet=item.source_sheet,
                    cross_check_result="NO_SECOND_SOURCE",
                    estimated_value=CSI_VALUE_ESTIMATES.get(csi_key, 15000),
                    risk_weight=15,
                )

        return None

    def _row_matches_csi(self, row: str, csi_section: str) -> bool:
        """Check if a schedule row ID matches a CSI section."""
        # Map common schedule row prefixes to CSI sections
        prefix_map = {
            "AHU": "230000", "FCU": "230000", "CU": "230000", "RTU": "230000",
            "EF": "230000", "SF": "230000", "RF": "230000", "MUA": "230000",
            "ERU": "230000", "DOAS": "230000", "HX": "230000", "CT": "230000",
            "CHILLER": "230000", "BOILER": "230000", "PUMP": "230000",
            "HWH": "220000", "FD": "210000", "SD": "210000", "SP": "210000",
            "PRV": "220000", "WH": "220000",
            "DP": "260000", "PANEL": "260000", "XFMR": "260000",
        }
        row_prefix = ''.join(c for c in row if c.isalpha()).upper()
        mapped = prefix_map.get(row_prefix, "")
        return mapped[:2] == csi_section[:2]  # Division-level match
