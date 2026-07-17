"""
ENGINE 1 — SCOPE EXTRACTION ENGINE v1.0
Extracts scope line items from construction bid documents (PDFs):
  - Division/section identification
  - Scope item extraction with quantities, units, descriptions
  - Schedule field validation (dates, durations)
  - Bidirectional sheet reconciliation (spec section ↔ drawings)
  - Cross-sheet conflict detection

Output: list of ScopeItem candidates → feeds Engine 2 (Coverage) and
        vendor quote normalizer (real line items vs. trade-level summaries)

Document types handled:
  SPEC     — CSI specification sections (text-heavy, section-structured)
  DRAWINGS — Drawing log / sheet list (cross-reference validation)
  ADDENDUM — Addendum/bulletin (delta changes)
  SCOPE    — Scope narrative / bid scope of work
  SCHEDULE — Project schedule (date extraction)
  ESTIMATE — Estimate / cost recap sheet
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExtractionConfidence(str, Enum):
    HIGH    = "high"      # Structured table or section header match
    MEDIUM  = "medium"    # Pattern match on known CSI keywords
    LOW     = "low"       # Weak pattern, needs review
    FAILED  = "failed"    # Could not extract


class DocumentType(str, Enum):
    SPEC      = "spec"
    DRAWINGS  = "drawings"
    ADDENDUM  = "addendum"
    SCOPE     = "scope"
    SCHEDULE  = "schedule"
    ESTIMATE  = "estimate"
    UNKNOWN   = "unknown"


class ConflictType(str, Enum):
    SECTION_MISMATCH    = "section_mismatch"     # Spec section in doc ≠ expected
    DRAWING_NOT_IN_SPEC = "drawing_not_in_spec"  # Drawing sheet has no spec section
    SPEC_NOT_IN_DRAWING = "spec_not_in_drawing"  # Spec section has no drawing reference
    DATE_CONFLICT       = "date_conflict"         # Conflicting dates across sheets
    QUANTITY_CONFLICT   = "quantity_conflict"     # Same item, different quantities


# ---------------------------------------------------------------------------
# Data objects
# ---------------------------------------------------------------------------

@dataclass
class RawTextBlock:
    page_number: int
    text: str
    bbox: Optional[tuple] = None   # (x0, y0, x1, y1) from PDF
    table_data: Optional[list] = None  # Extracted table rows


@dataclass
class ExtractedScopeItem:
    item_id: str
    source_document_id: str
    source_page: int
    csi_division: Optional[str]        # e.g. '23'
    csi_section: Optional[str]         # e.g. '230900'
    csi_description: Optional[str]
    description: str
    quantity: Optional[float]
    unit: Optional[str]
    spec_reference: Optional[str]      # e.g. 'Section 23 09 23'
    drawing_reference: Optional[str]   # e.g. 'M-101'
    confidence: ExtractionConfidence
    raw_text: str
    notes: Optional[str] = None
    is_addendum_change: bool = False
    addendum_action: Optional[str] = None  # 'add' | 'delete' | 'modify'


@dataclass
class DrawingEntry:
    sheet_number: str      # e.g. 'M-101'
    discipline: str        # 'M' | 'P' | 'E' | 'FP' | 'A' | 'S' | 'C'
    title: str
    revision: Optional[str]
    spec_sections: list[str] = field(default_factory=list)


@dataclass
class ScheduleField:
    field_name: str
    value: str
    parsed_date: Optional[str]   # ISO 8601
    confidence: ExtractionConfidence


@dataclass
class ReconciliationConflict:
    conflict_id: str
    conflict_type: ConflictType
    description: str
    source_a: str
    source_b: str
    resolution_required: bool = True


@dataclass
class ExtractionResult:
    extraction_id: str
    source_file: str
    document_type: DocumentType
    page_count: int
    scope_items: list[ExtractedScopeItem]
    drawing_entries: list[DrawingEntry]
    schedule_fields: list[ScheduleField]
    conflicts: list[ReconciliationConflict]
    overall_confidence: ExtractionConfidence
    extracted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    extraction_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSI Pattern Library
# ---------------------------------------------------------------------------

# Section number patterns: 23 09 23 / 230923 / 23-09-23
_CSI_SECTION_PATTERN = re.compile(
    r'\b(0[0-9]|[1-4][0-9])\s?[-.]?\s?([0-9]{2})\s?[-.]?\s?([0-9]{2})\b'
)
# Division header: DIVISION 23, DIV. 22, 23 - HVAC
_CSI_DIVISION_PATTERN = re.compile(
    r'\b(?:DIVISION|DIV\.?)\s+([0-9]{2})\b|\b([0-9]{2})\s+[-–]\s+([A-Z][A-Z &]+)',
    re.IGNORECASE
)
# Quantity patterns: 1,200 LF, 48 EA, 2.5 TON
_QUANTITY_PATTERN = re.compile(
    r'\b([0-9,]+(?:\.[0-9]+)?)\s+(LF|SF|CY|EA|TON|TONS|CFM|GPM|KW|HP|LB|LS|'
    r'EACH|UNIT|UNITS|LOT|SET|SETS|PAIR|IN|FT|SQ\.?FT|CU\.?FT)\b',
    re.IGNORECASE
)
# Drawing sheet number patterns: M-101, P-2, E-301, FP-1
_DRAWING_SHEET_PATTERN = re.compile(
    r'\b([MPEFASC](?:P)?)-?(\d{1,3}[A-Z]?)\b'
)
# Schedule date patterns
_DATE_PATTERN = re.compile(
    r'\b((?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s+\d{1,2},?\s+\d{4}|'
    r'\d{1,2}/\d{1,2}/\d{2,4}|'
    r'\d{4}-\d{2}-\d{2})\b',
    re.IGNORECASE
)
# Addendum action patterns
_ADDENDUM_ADD    = re.compile(r'\b(?:ADD|NEW|INSERT|PROVIDE)\b', re.IGNORECASE)
_ADDENDUM_DELETE = re.compile(r'\b(?:DELETE|REMOVE|ELIMINATE|VOID)\b', re.IGNORECASE)
_ADDENDUM_MODIFY = re.compile(r'\b(?:REVISE|MODIFY|CHANGE|REPLACE|UPDATE|AMEND)\b', re.IGNORECASE)

# Known CSI section → description lookup (MEP + common)
CSI_SECTION_LOOKUP: dict[str, str] = {
    "211000": "Fire Sprinklers",
    "212000": "Chemical Fire Suppression",
    "220000": "Plumbing",
    "220110": "Video Piping Inspections",
    "223200": "Water Filtration",
    "223613": "Solar Water Heater",
    "226000": "Medical Gas & Vacuum",
    "230000": "HVAC",
    "230131": "HVAC System Cleaning",
    "230593": "Test & Balance",
    "230800": "HVAC Commissioning",
    "230900": "Instrumentation & Controls",
    "230923": "DDC Controls",
    "231000": "Fuel Systems",
    "232300": "Refrigeration",
    "233439": "High-Volume Low-Speed Fans",
    "233516": "Engine Exhaust Systems",
    "233813": "Commercial Kitchen Hoods",
    "236000": "Chilled Water Systems",
    "250000": "Integrated Automation",
    "260000": "Electrical",
    "263100": "Photovoltaic",
    "263213": "Generators",
}

# Discipline map: drawing prefix → trade
DRAWING_DISCIPLINE: dict[str, str] = {
    "M":  "mechanical",
    "P":  "plumbing",
    "E":  "electrical",
    "FP": "fire_protection",
    "A":  "architectural",
    "S":  "structural",
    "C":  "civil",
}


# ---------------------------------------------------------------------------
# PDF Text Extractor
# ---------------------------------------------------------------------------

class PDFExtractor:
    """Extracts raw text blocks and tables from PDF using pdfplumber."""

    def extract(self, file_path: str) -> tuple[list[RawTextBlock], int]:
        """Returns (text_blocks, page_count)."""
        if not HAS_PDFPLUMBER:
            raise RuntimeError("pdfplumber not installed")

        blocks: list[RawTextBlock] = []
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, 1):
                # Plain text
                text = page.extract_text() or ""
                if text.strip():
                    blocks.append(RawTextBlock(
                        page_number=page_num,
                        text=text,
                    ))
                # Tables
                tables = page.extract_tables()
                for table in (tables or []):
                    if table:
                        blocks.append(RawTextBlock(
                            page_number=page_num,
                            text="\n".join(
                                " | ".join(str(c) if c else "" for c in row)
                                for row in table if row
                            ),
                            table_data=table,
                        ))
        return blocks, page_count

    def extract_text_only(self, file_path: str) -> tuple[str, int]:
        """Returns (full_text, page_count) for simpler parsing."""
        blocks, page_count = self.extract(file_path)
        full_text = "\n".join(b.text for b in blocks)
        return full_text, page_count


# ---------------------------------------------------------------------------
# Document Classifier
# ---------------------------------------------------------------------------

class DocumentClassifier:
    """Determines document type from filename + content."""

    FILENAME_RULES: list[tuple[re.Pattern, DocumentType]] = [
        (re.compile(r'spec|specification|division', re.I),  DocumentType.SPEC),
        (re.compile(r'addendum|bulletin|asi',        re.I),  DocumentType.ADDENDUM),
        (re.compile(r'drawing|sheet.?list|dwg.?log', re.I),  DocumentType.DRAWINGS),
        (re.compile(r'schedule|gantt|milestone',     re.I),  DocumentType.SCHEDULE),
        (re.compile(r'scope|bid.?scope|narrative',   re.I),  DocumentType.SCOPE),
        (re.compile(r'estimate|recap|budget|cost',   re.I),  DocumentType.ESTIMATE),
    ]

    CONTENT_SIGNALS: dict[DocumentType, list[str]] = {
        DocumentType.SPEC:      ["PART 1", "GENERAL", "PRODUCTS", "EXECUTION", "SECTION"],
        DocumentType.ADDENDUM:  ["ADDENDUM", "BULLETIN", "ASI", "ADD-"],
        DocumentType.DRAWINGS:  ["SHEET NO", "DRAWING NO", "REVISIONS", "M-1", "P-1", "E-1"],
        DocumentType.SCHEDULE:  ["SUBSTANTIAL COMPLETION", "MILESTONE", "DURATION", "START DATE"],
        DocumentType.SCOPE:     ["SCOPE OF WORK", "CONTRACTOR SHALL", "INCLUDE BUT NOT LIMITED"],
        DocumentType.ESTIMATE:  ["TOTAL COST", "UNIT PRICE", "LABOR HOURS", "MATERIAL COST"],
    }

    def classify(self, filename: str, sample_text: str = "") -> DocumentType:
        # Filename rules first
        for pattern, doc_type in self.FILENAME_RULES:
            if pattern.search(filename):
                return doc_type
        # Content signals
        upper_text = sample_text[:3000].upper()
        scores: dict[DocumentType, int] = {}
        for doc_type, signals in self.CONTENT_SIGNALS.items():
            scores[doc_type] = sum(1 for s in signals if s in upper_text)
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] >= 2:
                return best
        return DocumentType.UNKNOWN


# ---------------------------------------------------------------------------
# Scope Item Extractor
# ---------------------------------------------------------------------------

class ScopeItemExtractor:
    """Extracts scope items from text blocks."""

    def extract(
        self,
        blocks: list[RawTextBlock],
        doc_type: DocumentType,
        source_document_id: str,
    ) -> list[ExtractedScopeItem]:
        items: list[ExtractedScopeItem] = []

        for block in blocks:
            if doc_type == DocumentType.SPEC:
                items.extend(self._extract_from_spec(block, source_document_id))
            elif doc_type == DocumentType.ADDENDUM:
                items.extend(self._extract_from_addendum(block, source_document_id))
            elif doc_type in (DocumentType.SCOPE, DocumentType.ESTIMATE):
                items.extend(self._extract_from_scope_narrative(block, source_document_id))
            # DRAWINGS and SCHEDULE handled by separate extractors

        return self._deduplicate(items)

    def _extract_from_spec(
        self, block: RawTextBlock, source_doc_id: str
    ) -> list[ExtractedScopeItem]:
        items = []
        lines = block.text.split("\n")
        current_section: Optional[str] = None
        current_division: Optional[str] = None

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Section header detection
            section_match = _CSI_SECTION_PATTERN.search(line_stripped)
            if section_match:
                div, sub, subsub = section_match.groups()
                current_section = f"{div}{sub}{subsub}"
                current_division = div
                desc = CSI_SECTION_LOOKUP.get(current_section, line_stripped[:80])
                items.append(ExtractedScopeItem(
                    item_id=str(uuid.uuid4()),
                    source_document_id=source_doc_id,
                    source_page=block.page_number,
                    csi_division=current_division,
                    csi_section=current_section,
                    csi_description=desc,
                    description=desc,
                    quantity=None,
                    unit=None,
                    spec_reference=f"Section {div} {sub} {subsub}",
                    drawing_reference=None,
                    confidence=ExtractionConfidence.HIGH,
                    raw_text=line_stripped,
                ))
                continue

            # Quantity extraction within a known section
            if current_section:
                # Drawing reference scan on every line (not just quantity lines)
                drw_match = _DRAWING_SHEET_PATTERN.search(line_stripped)
                if drw_match and not qty_match if (qty_match := _QUANTITY_PATTERN.search(line_stripped)) else drw_match:
                    pass  # handled below
                qty_match = _QUANTITY_PATTERN.search(line_stripped)
                drw_match = _DRAWING_SHEET_PATTERN.search(line_stripped)
                if drw_match and not qty_match:
                    # Line has a drawing reference but no quantity — still record it
                    items.append(ExtractedScopeItem(
                        item_id=str(uuid.uuid4()),
                        source_document_id=source_doc_id,
                        source_page=block.page_number,
                        csi_division=current_division,
                        csi_section=current_section,
                        csi_description=CSI_SECTION_LOOKUP.get(current_section),
                        description=line_stripped[:120],
                        quantity=None,
                        unit=None,
                        spec_reference=f"Section {current_section[:2]} {current_section[2:4]} {current_section[4:]}",
                        drawing_reference=drw_match.group(0),
                        confidence=ExtractionConfidence.MEDIUM,
                        raw_text=line_stripped,
                    ))
                if qty_match and len(line_stripped) > 10:
                    qty_str, unit = qty_match.groups()
                    qty = float(qty_str.replace(",", ""))
                    drawing_ref = drw_match.group(0) if drw_match else None
                    items.append(ExtractedScopeItem(
                        item_id=str(uuid.uuid4()),
                        source_document_id=source_doc_id,
                        source_page=block.page_number,
                        csi_division=current_division,
                        csi_section=current_section,
                        csi_description=CSI_SECTION_LOOKUP.get(current_section),
                        description=line_stripped[:120],
                        quantity=qty,
                        unit=unit.upper(),
                        spec_reference=f"Section {current_section[:2]} {current_section[2:4]} {current_section[4:]}",
                        drawing_reference=drawing_ref,
                        confidence=ExtractionConfidence.MEDIUM,
                        raw_text=line_stripped,
                    ))
        return items

    def _extract_from_addendum(
        self, block: RawTextBlock, source_doc_id: str
    ) -> list[ExtractedScopeItem]:
        items = []
        lines = block.text.split("\n")
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 10:
                continue

            section_match = _CSI_SECTION_PATTERN.search(line_stripped)
            csi_section = None
            csi_division = None
            if section_match:
                div, sub, subsub = section_match.groups()
                csi_section = f"{div}{sub}{subsub}"
                csi_division = div

            # Determine addendum action — check MODIFY before ADD (REVISE > ADD)
            action = None
            if _ADDENDUM_DELETE.search(line_stripped):
                action = "delete"
            elif _ADDENDUM_MODIFY.search(line_stripped):
                action = "modify"
            elif _ADDENDUM_ADD.search(line_stripped):
                action = "add"

            if action or csi_section:
                items.append(ExtractedScopeItem(
                    item_id=str(uuid.uuid4()),
                    source_document_id=source_doc_id,
                    source_page=block.page_number,
                    csi_division=csi_division,
                    csi_section=csi_section,
                    csi_description=CSI_SECTION_LOOKUP.get(csi_section) if csi_section else None,
                    description=line_stripped[:120],
                    quantity=None,
                    unit=None,
                    spec_reference=None,
                    drawing_reference=None,
                    confidence=ExtractionConfidence.MEDIUM if csi_section else ExtractionConfidence.LOW,
                    raw_text=line_stripped,
                    is_addendum_change=True,
                    addendum_action=action,
                ))
        return items

    def _extract_from_scope_narrative(
        self, block: RawTextBlock, source_doc_id: str
    ) -> list[ExtractedScopeItem]:
        items = []
        # Table data path (structured estimate/scope tables)
        if block.table_data:
            for row in block.table_data:
                if not row or all(c is None or str(c).strip() == "" for c in row):
                    continue
                cells = [str(c).strip() if c else "" for c in row]
                description = next((c for c in cells if len(c) > 5), "")
                if not description:
                    continue

                # Find quantity/unit in row
                qty, unit = None, None
                for cell in cells:
                    m = _QUANTITY_PATTERN.match(cell.strip())
                    if m:
                        qty = float(m.group(1).replace(",", ""))
                        unit = m.group(2).upper()
                        break

                # Find CSI section in row
                csi_section = None
                for cell in cells:
                    m = _CSI_SECTION_PATTERN.search(cell)
                    if m:
                        div, sub, subsub = m.groups()
                        csi_section = f"{div}{sub}{subsub}"
                        break

                items.append(ExtractedScopeItem(
                    item_id=str(uuid.uuid4()),
                    source_document_id=source_doc_id,
                    source_page=block.page_number,
                    csi_division=csi_section[:2] if csi_section else None,
                    csi_section=csi_section,
                    csi_description=CSI_SECTION_LOOKUP.get(csi_section) if csi_section else None,
                    description=description[:120],
                    quantity=qty,
                    unit=unit,
                    spec_reference=None,
                    drawing_reference=None,
                    confidence=ExtractionConfidence.HIGH if csi_section else ExtractionConfidence.MEDIUM,
                    raw_text=" | ".join(cells),
                ))
        else:
            # Free text — look for CSI references + scope bullet points
            lines = block.text.split("\n")
            for line in lines:
                s = line.strip()
                if not s or len(s) < 15:
                    continue
                # Lines starting with bullets, numbers, or CSI sections
                if re.match(r'^[\•\-\*\d\.]', s) or _CSI_SECTION_PATTERN.search(s):
                    section_match = _CSI_SECTION_PATTERN.search(s)
                    csi_section = None
                    if section_match:
                        div, sub, subsub = section_match.groups()
                        csi_section = f"{div}{sub}{subsub}"
                    items.append(ExtractedScopeItem(
                        item_id=str(uuid.uuid4()),
                        source_document_id=source_doc_id,
                        source_page=block.page_number,
                        csi_division=csi_section[:2] if csi_section else None,
                        csi_section=csi_section,
                        csi_description=CSI_SECTION_LOOKUP.get(csi_section) if csi_section else None,
                        description=s[:120],
                        quantity=None,
                        unit=None,
                        spec_reference=None,
                        drawing_reference=None,
                        confidence=ExtractionConfidence.MEDIUM if csi_section else ExtractionConfidence.LOW,
                        raw_text=s,
                    ))
        return items

    def _deduplicate(self, items: list[ExtractedScopeItem]) -> list[ExtractedScopeItem]:
        """Remove exact description+section duplicates, keep highest confidence."""
        seen: dict[str, ExtractedScopeItem] = {}
        conf_rank = {
            ExtractionConfidence.HIGH: 3,
            ExtractionConfidence.MEDIUM: 2,
            ExtractionConfidence.LOW: 1,
            ExtractionConfidence.FAILED: 0,
        }
        for item in items:
            key = f"{item.csi_section}::{item.description[:50]}"
            if key not in seen or conf_rank[item.confidence] > conf_rank[seen[key].confidence]:
                seen[key] = item
        return list(seen.values())


# ---------------------------------------------------------------------------
# Drawing Extractor
# ---------------------------------------------------------------------------

class DrawingExtractor:

    def extract(self, blocks: list[RawTextBlock]) -> list[DrawingEntry]:
        entries: list[DrawingEntry] = []
        for block in blocks:
            for line in block.text.split("\n"):
                m = _DRAWING_SHEET_PATTERN.search(line)
                if m:
                    prefix = m.group(1).upper()
                    discipline = DRAWING_DISCIPLINE.get(prefix, "unknown")
                    sheet_num = m.group(0)
                    title = line.strip()[:80]
                    revision = None
                    rev_match = re.search(r'\bREV\.?\s*([A-Z0-9]+)', line, re.I)
                    if rev_match:
                        revision = rev_match.group(1)
                    entries.append(DrawingEntry(
                        sheet_number=sheet_num,
                        discipline=discipline,
                        title=title,
                        revision=revision,
                    ))
        # Deduplicate by sheet number
        by_sheet: dict[str, DrawingEntry] = {}
        for e in entries:
            if e.sheet_number not in by_sheet:
                by_sheet[e.sheet_number] = e
        return list(by_sheet.values())


# ---------------------------------------------------------------------------
# Schedule Extractor
# ---------------------------------------------------------------------------

class ScheduleExtractor:

    FIELD_LABELS = [
        "bid date", "bid due", "bid opening",
        "start date", "notice to proceed", "ntp",
        "substantial completion", "final completion",
        "owner occupancy", "opening date",
        "mobilization", "duration",
    ]

    def extract(self, blocks: list[RawTextBlock]) -> list[ScheduleField]:
        fields: list[ScheduleField] = []
        for block in blocks:
            for line in block.text.split("\n"):
                lower = line.lower()
                for label in self.FIELD_LABELS:
                    if label in lower:
                        date_match = _DATE_PATTERN.search(line)
                        value = date_match.group(0) if date_match else line.strip()[:60]
                        parsed = self._parse_date(date_match.group(0)) if date_match else None
                        fields.append(ScheduleField(
                            field_name=label,
                            value=value,
                            parsed_date=parsed,
                            confidence=ExtractionConfidence.HIGH if date_match
                                       else ExtractionConfidence.LOW,
                        ))
        return fields

    def _parse_date(self, raw: str) -> Optional[str]:
        """Attempt to normalize date to ISO 8601."""
        try:
            from datetime import datetime as dt
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
                try:
                    return dt.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        except Exception:
            pass
        return raw  # Return as-is if unparseable


# ---------------------------------------------------------------------------
# Reconciler — bidirectional sheet reconciliation + conflict detection
# ---------------------------------------------------------------------------

class Reconciler:

    def reconcile(
        self,
        scope_items: list[ExtractedScopeItem],
        drawing_entries: list[DrawingEntry],
        schedule_fields: list[ScheduleField],
    ) -> list[ReconciliationConflict]:
        conflicts: list[ReconciliationConflict] = []

        # 1. Drawings referenced in scope but not in drawing log
        scope_drawing_refs = {
            item.drawing_reference
            for item in scope_items
            if item.drawing_reference
        }
        drawing_sheet_numbers = {d.sheet_number for d in drawing_entries}
        for ref in scope_drawing_refs:
            if ref not in drawing_sheet_numbers:
                conflicts.append(ReconciliationConflict(
                    conflict_id=str(uuid.uuid4()),
                    conflict_type=ConflictType.DRAWING_NOT_IN_SPEC,
                    description=f"Drawing '{ref}' referenced in scope but not found in drawing log",
                    source_a="scope_items",
                    source_b="drawing_log",
                ))

        # 2. Duplicate CSI sections with conflicting descriptions
        section_descriptions: dict[str, set[str]] = {}
        for item in scope_items:
            if item.csi_section:
                section_descriptions.setdefault(item.csi_section, set()).add(
                    item.description[:50]
                )
        for section, descs in section_descriptions.items():
            if len(descs) > 3:  # High variation → potential conflict
                conflicts.append(ReconciliationConflict(
                    conflict_id=str(uuid.uuid4()),
                    conflict_type=ConflictType.SECTION_MISMATCH,
                    description=f"Section {section} has {len(descs)} distinct descriptions — review for scope overlap",
                    source_a="scope_items",
                    source_b="scope_items",
                    resolution_required=False,
                ))

        # 3. Schedule conflicts: duplicate field labels with different dates
        schedule_by_label: dict[str, list[str]] = {}
        for sf in schedule_fields:
            if sf.parsed_date:
                schedule_by_label.setdefault(sf.field_name, []).append(sf.parsed_date)
        for label, dates in schedule_by_label.items():
            if len(set(dates)) > 1:
                conflicts.append(ReconciliationConflict(
                    conflict_id=str(uuid.uuid4()),
                    conflict_type=ConflictType.DATE_CONFLICT,
                    description=f"'{label}' has conflicting dates: {', '.join(set(dates))}",
                    source_a="schedule",
                    source_b="schedule",
                ))

        return conflicts


# ---------------------------------------------------------------------------
# Engine 1 — Main entry point
# ---------------------------------------------------------------------------

class Engine1:
    """
    Main extraction engine. Accepts a file path, returns ExtractionResult.
    Can also operate on raw text blocks (for testing without real PDFs).
    """

    def __init__(self):
        self.classifier       = DocumentClassifier()
        self.pdf_extractor    = PDFExtractor()
        self.scope_extractor  = ScopeItemExtractor()
        self.drawing_extractor = DrawingExtractor()
        self.schedule_extractor = ScheduleExtractor()
        self.reconciler       = Reconciler()

    def extract_file(self, file_path: str, source_document_id: Optional[str] = None) -> ExtractionResult:
        """Full extraction pipeline from a PDF file."""
        doc_id = source_document_id or str(uuid.uuid4())
        warnings: list[str] = []

        if not HAS_PDFPLUMBER:
            return ExtractionResult(
                extraction_id=str(uuid.uuid4()),
                source_file=file_path,
                document_type=DocumentType.UNKNOWN,
                page_count=0,
                scope_items=[],
                drawing_entries=[],
                schedule_fields=[],
                conflicts=[],
                overall_confidence=ExtractionConfidence.FAILED,
                extraction_warnings=["pdfplumber not available"],
            )

        try:
            blocks, page_count = self.pdf_extractor.extract(file_path)
        except Exception as e:
            return ExtractionResult(
                extraction_id=str(uuid.uuid4()),
                source_file=file_path,
                document_type=DocumentType.UNKNOWN,
                page_count=0,
                scope_items=[],
                drawing_entries=[],
                schedule_fields=[],
                conflicts=[],
                overall_confidence=ExtractionConfidence.FAILED,
                extraction_warnings=[f"PDF extraction failed: {e}"],
            )

        sample_text = " ".join(b.text[:200] for b in blocks[:5])
        doc_type = self.classifier.classify(file_path, sample_text)

        return self._process_blocks(
            blocks, doc_type, file_path, doc_id, page_count, warnings
        )

    def extract_from_text(
        self,
        text: str,
        doc_type: DocumentType,
        source_document_id: Optional[str] = None,
        filename: str = "test_document",
    ) -> ExtractionResult:
        """Extraction from raw text — used in tests and when PDF is pre-extracted."""
        doc_id = source_document_id or str(uuid.uuid4())
        blocks = [RawTextBlock(page_number=1, text=text)]
        return self._process_blocks(blocks, doc_type, filename, doc_id, 1, [])

    def extract_from_blocks(
        self,
        blocks: list[RawTextBlock],
        doc_type: DocumentType,
        source_document_id: Optional[str] = None,
        filename: str = "test_document",
    ) -> ExtractionResult:
        """Extraction from pre-built text blocks."""
        doc_id = source_document_id or str(uuid.uuid4())
        return self._process_blocks(blocks, doc_type, filename, doc_id, len(blocks), [])

    def _process_blocks(
        self,
        blocks: list[RawTextBlock],
        doc_type: DocumentType,
        source_file: str,
        doc_id: str,
        page_count: int,
        warnings: list[str],
    ) -> ExtractionResult:
        scope_items     = self.scope_extractor.extract(blocks, doc_type, doc_id)
        drawing_entries = self.drawing_extractor.extract(blocks)
        schedule_fields = self.schedule_extractor.extract(blocks)
        conflicts       = self.reconciler.reconcile(scope_items, drawing_entries, schedule_fields)

        # Overall confidence: worst case across items
        conf_rank = {
            ExtractionConfidence.HIGH: 3,
            ExtractionConfidence.MEDIUM: 2,
            ExtractionConfidence.LOW: 1,
            ExtractionConfidence.FAILED: 0,
        }
        if not scope_items:
            overall = ExtractionConfidence.LOW
        else:
            min_conf = min(scope_items, key=lambda i: conf_rank[i.confidence])
            overall = min_conf.confidence

        return ExtractionResult(
            extraction_id=str(uuid.uuid4()),
            source_file=source_file,
            document_type=doc_type,
            page_count=page_count,
            scope_items=scope_items,
            drawing_entries=drawing_entries,
            schedule_fields=schedule_fields,
            conflicts=conflicts,
            overall_confidence=overall,
            extraction_warnings=warnings,
        )
