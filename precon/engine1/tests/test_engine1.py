"""
ENGINE 1 — SCOPE EXTRACTION — Tests
Covers: spec parsing, addendum handling, drawing cross-ref,
        schedule field extraction, reconciliation conflicts,
        bidirectional sheet reconciliation
"""

import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from precon.engine1.engine1 import (
    Engine1, DocumentType, ExtractionConfidence,
    RawTextBlock, ConflictType,
    DocumentClassifier, DrawingExtractor, ScheduleExtractor, Reconciler,
    ExtractedScopeItem,
)

def make_id(): return str(uuid.uuid4())

engine = Engine1()


# ===========================================================================
# SPEC PARSING
# ===========================================================================

class TestSpecParsing:

    SPEC_TEXT = """
DIVISION 23 - HVAC

SECTION 23 09 23
DIRECT-DIGITAL CONTROL (DDC) SYSTEM FOR HVAC

PART 1 - GENERAL
1.1 SUMMARY
    A. Provide complete DDC system per drawings M-201 and M-202.
    B. System shall include 48 EA field controllers.
    C. 2,400 LF conduit and wiring.

SECTION 23 05 93
TEST, ADJUST, AND BALANCE FOR HVAC

PART 1 - GENERAL
1.1 Contractor shall perform TAB on all HVAC systems.
    Total airflow: 85,000 CFM

SECTION 22 60 00
MEDICAL GAS AND VACUUM SYSTEMS

1.1 Provide medical gas outlets per drawings P-101.
    12 EA oxygen outlets
    8 EA vacuum outlets
"""

    def test_extracts_csi_sections(self):
        result = engine.extract_from_text(self.SPEC_TEXT, DocumentType.SPEC)
        sections = [i.csi_section for i in result.scope_items if i.csi_section]
        assert "230923" in sections, f"230923 not in {sections}"
        assert "230593" in sections, f"230593 not in {sections}"

    def test_high_confidence_on_section_headers(self):
        result = engine.extract_from_text(self.SPEC_TEXT, DocumentType.SPEC)
        headers = [i for i in result.scope_items
                   if i.csi_section == "230923" and i.confidence == ExtractionConfidence.HIGH]
        assert len(headers) >= 1

    def test_quantity_extraction(self):
        result = engine.extract_from_text(self.SPEC_TEXT, DocumentType.SPEC)
        quantities = [(i.quantity, i.unit) for i in result.scope_items if i.quantity]
        assert any(q == 48.0 and u == "EA" for q, u in quantities), \
            f"48 EA not found in {quantities}"
        assert any(q == 2400.0 and u == "LF" for q, u in quantities), \
            f"2400 LF not found in {quantities}"

    def test_drawing_reference_captured(self):
        result = engine.extract_from_text(self.SPEC_TEXT, DocumentType.SPEC)
        drawing_refs = [i.drawing_reference for i in result.scope_items if i.drawing_reference]
        assert any("M-2" in r for r in drawing_refs), f"M-2xx not found in {drawing_refs}"

    def test_spec_reference_captured(self):
        result = engine.extract_from_text(self.SPEC_TEXT, DocumentType.SPEC)
        spec_refs = [i.spec_reference for i in result.scope_items if i.spec_reference]
        assert len(spec_refs) >= 1

    def test_medical_gas_section_extracted(self):
        result = engine.extract_from_text(self.SPEC_TEXT, DocumentType.SPEC)
        sections = [i.csi_section for i in result.scope_items if i.csi_section]
        assert "226000" in sections


# ===========================================================================
# ADDENDUM PARSING
# ===========================================================================

class TestAddendumParsing:

    ADDENDUM_TEXT = """
ADDENDUM NO. 2
PROJECT: Macdill AFB B53 HVAC Renovation

SECTION 23 09 23 - CONTROLS
Item 1: DELETE reference to Spec Section 23 09 26.
Item 2: REVISE paragraph 2.3A to read: Provide Schneider SE8000 series controllers.

SECTION 23 05 93 - TEST AND BALANCE
Item 3: ADD requirement for duct leakage testing per SMACNA Class A.

DRAWINGS:
M-201: REVISE control diagram to show new controller locations.
M-305: DELETE detail 5/M-305 not applicable to this project.
"""

    def test_addendum_items_flagged(self):
        result = engine.extract_from_text(self.ADDENDUM_TEXT, DocumentType.ADDENDUM)
        addendum_items = [i for i in result.scope_items if i.is_addendum_change]
        assert len(addendum_items) >= 3

    def test_delete_action_detected(self):
        result = engine.extract_from_text(self.ADDENDUM_TEXT, DocumentType.ADDENDUM)
        deletes = [i for i in result.scope_items
                   if i.is_addendum_change and i.addendum_action == "delete"]
        assert len(deletes) >= 1

    def test_revise_action_detected(self):
        result = engine.extract_from_text(self.ADDENDUM_TEXT, DocumentType.ADDENDUM)
        revisions = [i for i in result.scope_items
                     if i.is_addendum_change and i.addendum_action == "modify"]
        assert len(revisions) >= 1

    def test_add_action_detected(self):
        result = engine.extract_from_text(self.ADDENDUM_TEXT, DocumentType.ADDENDUM)
        additions = [i for i in result.scope_items
                     if i.is_addendum_change and i.addendum_action == "add"]
        assert len(additions) >= 1

    def test_csi_section_in_addendum_item(self):
        result = engine.extract_from_text(self.ADDENDUM_TEXT, DocumentType.ADDENDUM)
        with_section = [i for i in result.scope_items if i.csi_section]
        assert len(with_section) >= 1


# ===========================================================================
# DRAWING LOG EXTRACTION
# ===========================================================================

class TestDrawingExtraction:

    DRAWING_LOG_TEXT = """
DRAWING SCHEDULE

M-001  Mechanical Legend and Schedules    Rev A
M-101  Level 1 HVAC Plan                 Rev B
M-201  DDC Controls Diagram              Rev A
M-301  Mechanical Details               Rev 0
P-101  Plumbing Plan Level 1             Rev A
P-201  Medical Gas Riser Diagram         Rev A
E-101  Electrical Site Plan              Rev 0
FP-1   Fire Protection Plan              Rev A
"""

    def test_mechanical_sheets_extracted(self):
        extractor = DrawingExtractor()
        blocks = [RawTextBlock(1, self.DRAWING_LOG_TEXT)]
        entries = extractor.extract(blocks)
        sheet_nums = [e.sheet_number for e in entries]
        assert any("M-1" in s for s in sheet_nums)
        assert any("M-2" in s for s in sheet_nums)

    def test_discipline_assigned_correctly(self):
        extractor = DrawingExtractor()
        blocks = [RawTextBlock(1, self.DRAWING_LOG_TEXT)]
        entries = extractor.extract(blocks)
        by_sheet = {e.sheet_number: e for e in entries}
        mech_entry = next((e for e in entries if e.sheet_number.startswith("M")), None)
        assert mech_entry is not None
        assert mech_entry.discipline == "mechanical"

    def test_plumbing_sheets_extracted(self):
        extractor = DrawingExtractor()
        blocks = [RawTextBlock(1, self.DRAWING_LOG_TEXT)]
        entries = extractor.extract(blocks)
        plumbing = [e for e in entries if e.discipline == "plumbing"]
        assert len(plumbing) >= 1

    def test_revision_captured(self):
        extractor = DrawingExtractor()
        blocks = [RawTextBlock(1, self.DRAWING_LOG_TEXT)]
        entries = extractor.extract(blocks)
        with_rev = [e for e in entries if e.revision]
        assert len(with_rev) >= 1


# ===========================================================================
# SCHEDULE EXTRACTION
# ===========================================================================

class TestScheduleExtraction:

    SCHEDULE_TEXT = """
PROJECT SCHEDULE

Bid Due Date:              07/15/2026
Notice to Proceed:         08/01/2026
Mobilization:              08/15/2026
Substantial Completion:    12/31/2026
Final Completion:          01/15/2027
Duration:                  22 weeks
"""

    def test_bid_date_extracted(self):
        extractor = ScheduleExtractor()
        blocks = [RawTextBlock(1, self.SCHEDULE_TEXT)]
        fields = extractor.extract(blocks)
        field_names = [f.field_name for f in fields]
        assert "bid due" in field_names or "bid date" in field_names

    def test_substantial_completion_extracted(self):
        extractor = ScheduleExtractor()
        blocks = [RawTextBlock(1, self.SCHEDULE_TEXT)]
        fields = extractor.extract(blocks)
        sc = [f for f in fields if "substantial" in f.field_name]
        assert len(sc) >= 1
        assert sc[0].parsed_date == "2026-12-31"

    def test_ntp_date_extracted(self):
        extractor = ScheduleExtractor()
        blocks = [RawTextBlock(1, self.SCHEDULE_TEXT)]
        fields = extractor.extract(blocks)
        ntp = [f for f in fields if "ntp" in f.field_name or "notice" in f.field_name]
        assert len(ntp) >= 1

    def test_dates_normalized_to_iso(self):
        extractor = ScheduleExtractor()
        blocks = [RawTextBlock(1, self.SCHEDULE_TEXT)]
        fields = extractor.extract(blocks)
        iso_dates = [f for f in fields if f.parsed_date and "-" in f.parsed_date]
        assert len(iso_dates) >= 2


# ===========================================================================
# RECONCILIATION CONFLICTS
# ===========================================================================

class TestReconciliation:

    def test_drawing_ref_in_scope_not_in_log(self):
        """Scope item references M-999 which is not in drawing log → conflict."""
        reconciler = Reconciler()
        scope_item = ExtractedScopeItem(
            item_id=make_id(),
            source_document_id=make_id(),
            source_page=1,
            csi_division="23",
            csi_section="230923",
            csi_description="Controls",
            description="Provide DDC per M-999",
            quantity=None, unit=None,
            spec_reference="Section 23 09 23",
            drawing_reference="M-999",  # Not in drawing log
            confidence=ExtractionConfidence.MEDIUM,
            raw_text="Provide DDC per M-999",
        )
        conflicts = reconciler.reconcile([scope_item], drawing_entries=[], schedule_fields=[])
        assert len(conflicts) >= 1
        assert any(c.conflict_type == ConflictType.DRAWING_NOT_IN_SPEC for c in conflicts)

    def test_date_conflict_detected(self):
        """Same schedule field with two different dates → conflict."""
        from precon.engine1.engine1 import ScheduleField
        reconciler = Reconciler()
        fields = [
            ScheduleField("substantial completion", "12/31/2026", "2026-12-31",
                          ExtractionConfidence.HIGH),
            ScheduleField("substantial completion", "01/15/2027", "2027-01-15",
                          ExtractionConfidence.HIGH),
        ]
        conflicts = reconciler.reconcile([], drawing_entries=[], schedule_fields=fields)
        date_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DATE_CONFLICT]
        assert len(date_conflicts) >= 1
        assert "substantial completion" in date_conflicts[0].description

    def test_no_conflicts_clean_document(self):
        """Clean scope + matching drawing entries → no conflicts."""
        from precon.engine1.engine1 import DrawingEntry
        reconciler = Reconciler()
        scope_item = ExtractedScopeItem(
            item_id=make_id(),
            source_document_id=make_id(),
            source_page=1,
            csi_division="23",
            csi_section="230923",
            csi_description="Controls",
            description="Provide DDC per M-201",
            quantity=None, unit=None,
            spec_reference="Section 23 09 23",
            drawing_reference="M-201",
            confidence=ExtractionConfidence.HIGH,
            raw_text="Provide DDC per M-201",
        )
        drawing = DrawingEntry("M-201", "mechanical", "Controls Diagram", "A")
        conflicts = reconciler.reconcile([scope_item], [drawing], [])
        conflict_types = [c.conflict_type for c in conflicts]
        assert ConflictType.DRAWING_NOT_IN_SPEC not in conflict_types


# ===========================================================================
# DOCUMENT CLASSIFIER
# ===========================================================================

class TestDocumentClassifier:

    def test_spec_filename_classified(self):
        clf = DocumentClassifier()
        assert clf.classify("Div23_Specifications.pdf") == DocumentType.SPEC

    def test_addendum_filename_classified(self):
        clf = DocumentClassifier()
        assert clf.classify("Addendum_2_HVAC.pdf") == DocumentType.ADDENDUM

    def test_drawing_log_classified(self):
        clf = DocumentClassifier()
        assert clf.classify("Drawing_List_Rev3.pdf") == DocumentType.DRAWINGS

    def test_schedule_classified_by_content(self):
        clf = DocumentClassifier()
        text = "MILESTONE SCHEDULE\nSUBSTANTIAL COMPLETION\nSTART DATE\nDURATION"
        assert clf.classify("project_docs.pdf", text) == DocumentType.SCHEDULE

    def test_estimate_classified_by_content(self):
        clf = DocumentClassifier()
        text = "TOTAL COST SUMMARY\nUNIT PRICE\nLABOR HOURS\nMATERIAL COST"
        assert clf.classify("bid_docs.pdf", text) == DocumentType.ESTIMATE

    def test_unknown_fallback(self):
        clf = DocumentClassifier()
        assert clf.classify("document.pdf", "Hello world") == DocumentType.UNKNOWN


# ===========================================================================
# SCOPE NARRATIVE / TABLE
# ===========================================================================

class TestScopeNarrativeParsing:

    SCOPE_TEXT = """
SCOPE OF WORK — HVAC SYSTEM RENOVATION

The mechanical contractor shall provide all labor, material, and equipment for:

• 23 09 23 - Complete DDC building automation system upgrade
• 23 05 93 - Test, adjust, and balance all HVAC systems
• 22 60 00 - Medical gas outlets: 12 EA oxygen, 8 EA vacuum
• 21 10 00 - Fire protection sprinkler system

CONTRACTOR SHALL furnish and install the following:
- Variable frequency drives (VFDs) for AHU-1, AHU-2, AHU-3
- New DDC controllers for all AHUs and FCUs
- Complete TAB of all systems
"""

    def test_scope_bullet_items_extracted(self):
        result = engine.extract_from_text(self.SCOPE_TEXT, DocumentType.SCOPE)
        assert len(result.scope_items) >= 3

    def test_csi_sections_from_scope_bullets(self):
        result = engine.extract_from_text(self.SCOPE_TEXT, DocumentType.SCOPE)
        sections = [i.csi_section for i in result.scope_items if i.csi_section]
        assert "230923" in sections or "230593" in sections

    def test_overall_result_structure(self):
        result = engine.extract_from_text(self.SCOPE_TEXT, DocumentType.SCOPE)
        assert result.extraction_id
        assert result.document_type == DocumentType.SCOPE
        assert result.extracted_at
        assert isinstance(result.scope_items, list)
        assert isinstance(result.conflicts, list)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    import subprocess
    r = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd="/var/lib/openclaw/.openclaw/workspace"
    )
    print(r.stdout)
    print(r.stderr[-500:] if r.stderr else "")
