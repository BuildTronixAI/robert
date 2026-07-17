"""
VENDOR QUOTE INTAKE ENGINE v1.0
Ingests vendor quotes, normalizes them, and routes to:
  - cost_recap_entries (NewCo Sub view — cost codes)
  - GC view (CSI sections — Joe's format)
  - submittal_items (links quote to submittal registry)
  - File directory (governed path per project/trade/CSI)

Flow:
  Quote arrives (PDF/email)
  → Classifier identifies as VENDOR_QUOTE
  → Parser extracts: vendor, amount, line items, scope summary
  → VendorRegistry maps to trade type → CSI sections + cost codes
  → QuoteNormalizer maps line items to specific codes
  → QuoteRouter writes to cost_recap_entries + updates submittal status
  → FilingEngine archives to governed directory path
  → CoverageTracker identifies remaining gaps (????? cells still open)
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from precon.quote_intake.vendor_registry import (
    get_mappings_for_vendor, VendorProfile, TRADE_TYPE_MAPPINGS
)


# ---------------------------------------------------------------------------
# Enums & data objects
# ---------------------------------------------------------------------------

class QuoteStatus(str, Enum):
    RECEIVED         = "received"
    PARSED           = "parsed"
    MAPPED           = "mapped"
    WRITTEN          = "written"
    FILED            = "filed"
    PARSE_FAILED     = "parse_failed"
    MAPPING_FAILED   = "mapping_failed"
    NEEDS_REVIEW     = "needs_review"


class QuoteLineConfidence(str, Enum):
    HIGH    = "high"     # Exact rule match vendor→code
    MEDIUM  = "medium"   # Trade-type match, specific code inferred
    LOW     = "low"      # Keyword match only, needs human review
    UNMAPPED = "unmapped" # Cannot determine code


@dataclass
class RawQuoteLine:
    """A line item as extracted from the PDF/email — uninterpreted."""
    description: str
    amount: float
    unit: Optional[str] = None
    quantity: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class RawQuote:
    """Parsed but unmapped vendor quote."""
    raw_quote_id: str
    vendor_name: str
    project_ref: Optional[str]      # Job number or project name as written on quote
    quote_date: Optional[str]
    total_amount: float
    line_items: list[RawQuoteLine]
    source_file: Optional[str]
    source_type: str = "pdf"        # 'pdf' | 'email'
    received_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class MappedQuoteLine:
    """Quote line mapped to both CSI section and NewCo cost code."""
    raw_line: RawQuoteLine
    csi_section: Optional[str]       # e.g. '230900'
    csi_description: Optional[str]   # e.g. 'Instrumentation & Controls for HVAC'
    cost_code: Optional[str]         # e.g. '502'
    cost_code_description: Optional[str]
    confidence: QuoteLineConfidence
    mapping_source: str              # 'exact_rule' | 'trade_type' | 'keyword' | 'unmapped'
    review_flag: bool = False
    review_reason: Optional[str] = None


@dataclass
class NormalizedQuote:
    """Fully mapped and validated quote, ready to write."""
    normalized_quote_id: str
    raw_quote: RawQuote
    vendor_id: Optional[str]
    trade_type: Optional[str]
    project_id: Optional[str]         # Resolved from project_ref
    mapped_lines: list[MappedQuoteLine]
    total_amount: float
    coverage_csi_sections: list[str]  # Which CSI sections this quote covers
    coverage_cost_codes: list[str]    # Which cost codes this quote covers
    has_unmapped_lines: bool
    needs_review: bool
    filing_path: Optional[str] = None
    status: QuoteStatus = QuoteStatus.MAPPED


@dataclass
class CostRecapEntry:
    """Record to write to cost_recap_entries table."""
    proposal_id: str
    phase: str                  # '10-MECHANICAL' | '21-SHEET METAL' | '31-PLUMBING' | '50-SUBS'
    cost_code: str
    csi_section: Optional[str]
    description: str
    vendor_name: str
    sub_cost: float             # This is a sub/vendor cost
    labor_hours: float = 0
    labor_rate: float = 0
    mat_cost: float = 0
    eqp_cost: float = 0
    source_quote_id: Optional[str] = None
    source_submittal_revision_id: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# CSI section → readable description lookup
# ---------------------------------------------------------------------------

CSI_DESCRIPTIONS: dict[str, str] = {
    "211000": "Fire Sprinklers",
    "212000": "Chemical Fire Suppression Systems",
    "220000": "Plumbing Contractor",
    "220001": "Plumbing Supplier",
    "220110": "Video Piping Inspections",
    "223200": "Water Filtration Systems",
    "223613": "Solar Water Heater Systems",
    "226000": "Medical Gas & Vacuum Systems",
    "230000": "HVAC Contractor",
    "230001": "HVAC Supplier",
    "230131": "HVAC Air-Distribution System Cleaning",
    "230593": "Test & Balance",
    "230800": "HVAC Commissioning",
    "230900": "Instrumentation & Controls for HVAC",
    "231000": "Fuel Systems, Pumps & Storage Tanks",
    "232300": "Refrigeration",
    "233439": "High-Volume Low-Speed Fans",
    "233516": "Engine Exhaust Systems",
    "233813": "Commercial Kitchen Hoods",
    "236000": "Chilled Water Systems",
    "250000": "Integrated Building Automation",
    "260000": "Electrical Contractor",
    "260001": "Electrical Supplier",
    "263100": "Photovoltaic Systems",
    "263213": "Generators",
}

# Cost code → phase mapping (NewCo structure)
def cost_code_to_phase(cost_code: str) -> str:
    if not cost_code:
        return "99-UNKNOWN"
    try:
        code_num = int(cost_code)
        if 100 <= code_num <= 199:
            return "10-MECHANICAL"
        elif 200 <= code_num <= 299:
            return "21-SHEET METAL"
        elif 300 <= code_num <= 399:
            return "31-PLUMBING"
        elif 500 <= code_num <= 599:
            return "50-SUBS"
        else:
            return "99-UNKNOWN"
    except (ValueError, TypeError):
        return "99-UNKNOWN"


# ---------------------------------------------------------------------------
# Quote Normalizer
# Maps raw quote lines to CSI + cost code using vendor trade type
# ---------------------------------------------------------------------------

class QuoteNormalizer:

    def normalize(
        self,
        raw_quote: RawQuote,
        vendor_profile: Optional[VendorProfile] = None,
    ) -> NormalizedQuote:
        """
        Map raw quote to CSI sections + cost codes.
        Uses VendorRegistry for deterministic mapping.
        Falls back to keyword matching on line item descriptions.
        """
        # Resolve vendor mappings
        mappings = get_mappings_for_vendor(
            raw_quote.vendor_name, vendor_profile, mode="both"
        )
        trade_type  = mappings.get("trade_type")
        csi_secs    = mappings.get("csi_sections", [])
        cost_codes  = mappings.get("cost_codes", [])

        mapped_lines: list[MappedQuoteLine] = []
        has_unmapped = False
        needs_review = False

        for line in raw_quote.line_items:
            ml = self._map_line(line, trade_type, csi_secs, cost_codes)
            if ml.confidence == QuoteLineConfidence.UNMAPPED:
                has_unmapped = True
                needs_review = True
            elif ml.confidence == QuoteLineConfidence.LOW:
                needs_review = True
            mapped_lines.append(ml)

        # If no line items, create one summary line
        if not mapped_lines and raw_quote.total_amount > 0:
            summary_line = RawQuoteLine(
                description=f"Quote from {raw_quote.vendor_name} — total",
                amount=raw_quote.total_amount,
            )
            ml = self._map_line(summary_line, trade_type, csi_secs, cost_codes)
            mapped_lines.append(ml)
            if ml.confidence == QuoteLineConfidence.UNMAPPED:
                has_unmapped = True
                needs_review = True

        # Collect coverage
        coverage_csi  = list({ml.csi_section  for ml in mapped_lines if ml.csi_section})
        coverage_codes = list({ml.cost_code    for ml in mapped_lines if ml.cost_code})

        return NormalizedQuote(
            normalized_quote_id=str(uuid.uuid4()),
            raw_quote=raw_quote,
            vendor_id=None,
            trade_type=trade_type,
            project_id=None,  # resolved later by project matcher
            mapped_lines=mapped_lines,
            total_amount=raw_quote.total_amount,
            coverage_csi_sections=coverage_csi,
            coverage_cost_codes=coverage_codes,
            has_unmapped_lines=has_unmapped,
            needs_review=needs_review,
        )

    def _map_line(
        self,
        line: RawQuoteLine,
        trade_type: Optional[str],
        csi_sections: list[str],
        cost_codes: list[str],
    ) -> MappedQuoteLine:
        # If vendor has exactly one CSI section and one cost code → HIGH confidence
        if len(csi_sections) == 1 and len(cost_codes) == 1:
            return MappedQuoteLine(
                raw_line=line,
                csi_section=csi_sections[0],
                csi_description=CSI_DESCRIPTIONS.get(csi_sections[0]),
                cost_code=cost_codes[0],
                cost_code_description=f"Cost code {cost_codes[0]}",
                confidence=QuoteLineConfidence.HIGH,
                mapping_source="exact_rule",
            )

        # Multi-code trade: try keyword match on line description
        if csi_sections and cost_codes:
            kw_csi, kw_code = self._keyword_map_line(line.description, csi_sections, cost_codes)
            if kw_csi and kw_code:
                return MappedQuoteLine(
                    raw_line=line,
                    csi_section=kw_csi,
                    csi_description=CSI_DESCRIPTIONS.get(kw_csi),
                    cost_code=kw_code,
                    cost_code_description=f"Cost code {kw_code}",
                    confidence=QuoteLineConfidence.MEDIUM,
                    mapping_source="trade_type",
                )
            # Trade known but line is ambiguous — flag for review
            return MappedQuoteLine(
                raw_line=line,
                csi_section=csi_sections[0] if csi_sections else None,
                csi_description=CSI_DESCRIPTIONS.get(csi_sections[0]) if csi_sections else None,
                cost_code=cost_codes[0] if cost_codes else None,
                cost_code_description=None,
                confidence=QuoteLineConfidence.LOW,
                mapping_source="trade_type",
                review_flag=True,
                review_reason=f"Multi-code trade '{trade_type}' — line item description ambiguous, defaulted to first code",
            )

        # Unknown vendor — return unmapped
        return MappedQuoteLine(
            raw_line=line,
            csi_section=None,
            csi_description=None,
            cost_code=None,
            cost_code_description=None,
            confidence=QuoteLineConfidence.UNMAPPED,
            mapping_source="unmapped",
            review_flag=True,
            review_reason="Vendor trade type could not be resolved. Manual code assignment required.",
        )

    def _keyword_map_line(
        self, description: str, csi_sections: list[str], cost_codes: list[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Attempt keyword-based line item → code assignment."""
        desc = description.lower()
        keyword_rules = [
            (["control", "bas", "bms", "ddc", "pneumatic"], "230900", "502"),
            (["commission", "cx"],                           "230800", "173"),
            (["tab", "test", "balance", "air balance"],      "230593", "503"),
            (["insul"],                                       "230000", "501"),
            (["duct leak", "duct test"],                     "230593", "504"),
            (["chilled water", "chw", "cooling tower"],      "236000", "141"),
            (["hot water", "heating water", "hhw"],          "236000", "142"),
            (["medical gas", "med gas", "oxygen", "vacuum"], "226000", "350"),
            (["sprinkler", "fire protection"],               "211000", "516"),
            (["electrical", "electric", "power"],            "260000", "512"),
            (["plumb"],                                      "220000", "300"),
            (["refrigerat", "dx system"],                    "232300", "130"),
        ]
        for keywords, csi, code in keyword_rules:
            if any(k in desc for k in keywords):
                if csi in csi_sections or not csi_sections:
                    return csi, code
        return None, None


# ---------------------------------------------------------------------------
# Quote Router — writes to cost_recap_entries
# ---------------------------------------------------------------------------

class QuoteRouter:

    def build_cost_recap_entries(
        self,
        normalized: NormalizedQuote,
        project_id: str,
        submittal_revision_id: Optional[str] = None,
    ) -> list[CostRecapEntry]:
        """
        Convert normalized quote to cost_recap_entries records.
        One entry per distinct cost code (consolidated if multiple lines on same code).
        """
        # Group mapped lines by cost code
        by_code: dict[str, list[MappedQuoteLine]] = {}
        for ml in normalized.mapped_lines:
            if ml.cost_code:
                by_code.setdefault(ml.cost_code, []).append(ml)
            # Unmapped lines get a review entry under code '999'
            else:
                by_code.setdefault("999-UNASSIGNED", []).append(ml)

        entries: list[CostRecapEntry] = []
        for code, lines in by_code.items():
            total = sum(ml.raw_line.amount for ml in lines)
            desc_parts = list({ml.raw_line.description[:60] for ml in lines})
            description = "; ".join(desc_parts[:3])
            csi = next((ml.csi_section for ml in lines if ml.csi_section), None)

            entry = CostRecapEntry(
                proposal_id=project_id,
                phase=cost_code_to_phase(code.split("-")[0]),
                cost_code=code,
                csi_section=csi,
                description=description or f"Quote from {normalized.raw_quote.vendor_name}",
                vendor_name=normalized.raw_quote.vendor_name,
                sub_cost=total,
                source_quote_id=normalized.normalized_quote_id,
                source_submittal_revision_id=submittal_revision_id,
                notes=f"Received {normalized.raw_quote.received_at[:10]}",
            )
            entries.append(entry)
        return entries

    def build_gc_view(self, normalized: NormalizedQuote) -> list[dict]:
        """
        Return quote in GC format (Joe's template structure):
        CSI section + description + vendor amount.
        Used to populate the '?????' cells in Joe's scope sheet.
        """
        gc_rows = []
        by_csi: dict[str, float] = {}
        for ml in normalized.mapped_lines:
            if ml.csi_section:
                by_csi[ml.csi_section] = by_csi.get(ml.csi_section, 0) + ml.raw_line.amount
        for csi, amount in by_csi.items():
            gc_rows.append({
                "csi_section":   csi,
                "csi_description": CSI_DESCRIPTIONS.get(csi, "Unknown"),
                "vendor_name":   normalized.raw_quote.vendor_name,
                "amount":        amount,
                "template_column": "vendor_quote",  # the '?????' cell column
            })
        return gc_rows


# ---------------------------------------------------------------------------
# Filing Engine — governs file storage paths
# ---------------------------------------------------------------------------

class FilingEngine:

    BASE_PATH = "/project-files"

    def resolve_path(
        self,
        project_id: str,
        project_name: str,
        vendor_name: str,
        trade_type: Optional[str],
        quote_date: Optional[str],
    ) -> str:
        """
        Returns governed file path for a vendor quote.
        Structure: /project-files/{project_id}/{trade_type}/quotes/{YYYY-MM}/{vendor_name}/
        """
        date_folder = (quote_date or datetime.now(timezone.utc).strftime("%Y-%m"))[:7]
        trade_folder = (trade_type or "unknown-trade").replace("_", "-")
        vendor_folder = vendor_name.lower().replace(" ", "-")[:40]
        return (
            f"{self.BASE_PATH}/{project_id}/{trade_folder}/quotes/{date_folder}/{vendor_folder}/"
        )

    def file_document(
        self,
        source_path: str,
        filing_path: str,
        document_hash: Optional[str] = None,
    ) -> dict:
        """
        Move/copy document to governed path.
        Returns provenance record (for contract_documents table).
        Production: calls A-0 ingestor to register in event_log.
        """
        return {
            "source_path":    source_path,
            "filing_path":    filing_path,
            "document_hash":  document_hash,
            "filed_at":       datetime.now(timezone.utc).isoformat(),
            "source_system":  "quote_intake",
        }


# ---------------------------------------------------------------------------
# Coverage Tracker — identifies procurement gaps
# ---------------------------------------------------------------------------

class CoverageTracker:

    def gap_report(
        self,
        project_id: str,
        required_csi_sections: list[str],
        received_quotes: list[NormalizedQuote],
    ) -> dict:
        """
        Identify which CSI sections still have no quote (the '?????' cells).
        Returns: covered, missing, partial (mapped but low confidence).
        """
        covered: dict[str, str] = {}   # csi_section → vendor_name
        low_confidence: dict[str, str] = {}

        for q in received_quotes:
            for ml in q.mapped_lines:
                if ml.csi_section:
                    if ml.confidence in (QuoteLineConfidence.HIGH, QuoteLineConfidence.MEDIUM):
                        covered[ml.csi_section] = q.raw_quote.vendor_name
                    elif ml.csi_section not in covered:
                        low_confidence[ml.csi_section] = q.raw_quote.vendor_name

        missing = [s for s in required_csi_sections if s not in covered and s not in low_confidence]
        partial = [s for s in required_csi_sections if s in low_confidence and s not in covered]

        return {
            "project_id":   project_id,
            "required":     len(required_csi_sections),
            "covered":      len(covered),
            "partial":      len(partial),
            "missing":      len(missing),
            "covered_sections":  covered,
            "partial_sections":  {s: low_confidence[s] for s in partial},
            "missing_sections":  {s: CSI_DESCRIPTIONS.get(s, "Unknown") for s in missing},
            "coverage_pct": round(len(covered) / len(required_csi_sections) * 100, 1)
                            if required_csi_sections else 0,
        }
