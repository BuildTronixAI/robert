"""
VENDOR QUOTE INTAKE ENGINE — Tests
Covers: normalization, GC view, Sub view, filing paths, coverage gaps
"""

import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from precon.quote_intake.quote_intake import (
    QuoteNormalizer, QuoteRouter, FilingEngine, CoverageTracker,
    RawQuote, RawQuoteLine, QuoteLineConfidence, cost_code_to_phase,
)

def make_id(): return str(uuid.uuid4())
PROJECT_ID = make_id()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def make_quote(vendor: str, total: float, lines=None) -> RawQuote:
    return RawQuote(
        raw_quote_id=make_id(),
        vendor_name=vendor,
        project_ref="AMS-2026-001",
        quote_date="2026-06-16",
        total_amount=total,
        line_items=lines or [],
        source_file=f"/tmp/{vendor.lower().replace(' ', '_')}_quote.pdf",
    )


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

class TestQuoteNormalizer:

    def test_single_code_vendor_high_confidence(self):
        """TAB vendor → 230593 + cost code 503, HIGH confidence."""
        norm = QuoteNormalizer()
        q = make_quote("Southeastern TAB Services", 18500.00, [
            RawQuoteLine("Complete TAB services per spec", 18500.00)
        ])
        result = norm.normalize(q)
        assert result.trade_type == "tab"
        assert "230593" in result.coverage_csi_sections
        assert "503" in result.coverage_cost_codes
        assert result.mapped_lines[0].confidence == QuoteLineConfidence.HIGH
        assert not result.needs_review

    def test_controls_vendor_high_confidence(self):
        """Controls vendor → 230900 + 502."""
        norm = QuoteNormalizer()
        q = make_quote("Johnson Controls", 125000.00, [
            RawQuoteLine("DDC controls and BAS installation", 125000.00)
        ])
        result = norm.normalize(q)
        assert result.trade_type == "controls"
        assert "230900" in result.coverage_csi_sections
        assert "502" in result.coverage_cost_codes

    def test_fire_sprinkler_vendor(self):
        """Sprinkler sub → 211000 + 516."""
        norm = QuoteNormalizer()
        q = make_quote("Gulf Coast Fire Sprinkler Inc", 48000.00, [
            RawQuoteLine("Fire sprinkler system installation", 48000.00)
        ])
        result = norm.normalize(q)
        assert result.trade_type == "fire_sprinkler"
        assert "211000" in result.coverage_csi_sections
        assert "516" in result.coverage_cost_codes

    def test_unknown_vendor_returns_unmapped(self):
        """Unknown vendor → UNMAPPED, needs review."""
        norm = QuoteNormalizer()
        q = make_quote("XYZ Specialty Contractors LLC", 75000.00, [
            RawQuoteLine("Various work per scope", 75000.00)
        ])
        result = norm.normalize(q)
        assert result.has_unmapped_lines
        assert result.needs_review
        assert result.mapped_lines[0].confidence == QuoteLineConfidence.UNMAPPED

    def test_multi_code_trade_with_keyword_match(self):
        """HVAC contractor with keyword-identifiable line items."""
        norm = QuoteNormalizer()
        q = make_quote("Carrier HVAC Contractor", 250000.00, [
            RawQuoteLine("Chilled water piping and equipment", 150000.00),
            RawQuoteLine("DDC controls for AHU", 100000.00),
        ])
        result = norm.normalize(q)
        # Trade resolves to hvac_contractor
        assert result.trade_type is not None
        # At least one line mapped
        assert len(result.mapped_lines) == 2

    def test_plumbing_vendor(self):
        """Plumbing contractor → 220000 + 300-series."""
        norm = QuoteNormalizer()
        q = make_quote("ABC Plumbing Inc", 95000.00, [
            RawQuoteLine("Complete plumbing installation", 95000.00)
        ])
        result = norm.normalize(q)
        assert result.trade_type == "plumbing_contractor"
        assert "220000" in result.coverage_csi_sections
        assert any(c.startswith("3") for c in result.coverage_cost_codes)

    def test_no_line_items_summary_created(self):
        """Quote with no line items gets a single summary mapped line."""
        norm = QuoteNormalizer()
        q = make_quote("Southeast TAB", 22000.00, [])
        result = norm.normalize(q)
        assert len(result.mapped_lines) == 1
        assert result.total_amount == 22000.00

    def test_electrical_contractor(self):
        """Electrical contractor → 260000 + 512."""
        norm = QuoteNormalizer()
        q = make_quote("Sparks Electrical Services", 340000.00, [
            RawQuoteLine("Electrical installation per Division 26", 340000.00)
        ])
        result = norm.normalize(q)
        assert result.trade_type == "electrical_contractor"
        assert "260000" in result.coverage_csi_sections
        assert "512" in result.coverage_cost_codes

    def test_insulation_vendor(self):
        """Insulation sub → 501."""
        norm = QuoteNormalizer()
        q = make_quote("Thermal Insulation Specialists", 32000.00, [
            RawQuoteLine("Mechanical insulation all piping and equipment", 32000.00)
        ])
        result = norm.normalize(q)
        assert result.trade_type == "insulation"
        assert "501" in result.coverage_cost_codes


# ---------------------------------------------------------------------------
# Cost recap entry tests
# ---------------------------------------------------------------------------

class TestQuoteRouter:

    def test_builds_cost_recap_entry(self):
        """Normalized quote → cost_recap_entries records."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        q = make_quote("Southeast TAB Services", 18500.00, [
            RawQuoteLine("TAB all systems", 18500.00)
        ])
        normalized = norm.normalize(q)
        entries = router.build_cost_recap_entries(normalized, PROJECT_ID)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry.proposal_id == PROJECT_ID
        assert entry.sub_cost == 18500.00
        assert entry.vendor_name == "Southeast TAB Services"
        assert entry.cost_code == "503"
        assert entry.phase == "50-SUBS"

    def test_cost_recap_phase_mapping(self):
        """Cost code → phase mapping correct for all series."""
        assert cost_code_to_phase("502") == "50-SUBS"
        assert cost_code_to_phase("150") == "10-MECHANICAL"
        assert cost_code_to_phase("210") == "21-SHEET METAL"
        assert cost_code_to_phase("310") == "31-PLUMBING"
        assert cost_code_to_phase("999") == "99-UNKNOWN"

    def test_gc_view_returns_csi_rows(self):
        """GC view returns CSI-formatted rows for Joe's template."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        q = make_quote("Johnson Controls", 125000.00, [
            RawQuoteLine("BAS controls installation", 125000.00)
        ])
        normalized = norm.normalize(q)
        gc_rows = router.build_gc_view(normalized)
        assert len(gc_rows) >= 1
        row = gc_rows[0]
        assert "csi_section" in row
        assert "csi_description" in row
        assert row["vendor_name"] == "Johnson Controls"
        assert row["amount"] == 125000.00
        assert row["template_column"] == "vendor_quote"

    def test_multiple_lines_same_code_consolidated(self):
        """Multiple lines on same cost code → single consolidated entry."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        q = make_quote("Southeast TAB", 30000.00, [
            RawQuoteLine("TAB Phase 1", 18000.00),
            RawQuoteLine("TAB Phase 2", 12000.00),
        ])
        normalized = norm.normalize(q)
        entries = router.build_cost_recap_entries(normalized, PROJECT_ID)
        # Both TAB lines map to 503 → should consolidate
        code_503_entries = [e for e in entries if e.cost_code == "503"]
        assert len(code_503_entries) == 1
        assert code_503_entries[0].sub_cost == 30000.00

    def test_unmapped_line_gets_review_entry(self):
        """Unmapped line creates 999-UNASSIGNED entry."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        q = make_quote("Mystery Contractor LLC", 50000.00, [
            RawQuoteLine("Unspecified work", 50000.00)
        ])
        normalized = norm.normalize(q)
        entries = router.build_cost_recap_entries(normalized, PROJECT_ID)
        assert any("999" in e.cost_code for e in entries)

    def test_source_quote_id_preserved(self):
        """Each cost_recap_entry carries source_quote_id for traceability."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        q = make_quote("Southeast TAB Services", 18500.00, [
            RawQuoteLine("TAB all systems", 18500.00)
        ])
        normalized = norm.normalize(q)
        entries = router.build_cost_recap_entries(normalized, PROJECT_ID,
                                                   submittal_revision_id=make_id())
        for entry in entries:
            assert entry.source_quote_id == normalized.normalized_quote_id

    def test_submittal_revision_id_bound_to_entry(self):
        """PO-6 compliance: entry carries submittal_revision_id."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        rev_id = make_id()
        q = make_quote("Southeast TAB Services", 18500.00, [
            RawQuoteLine("TAB all systems", 18500.00)
        ])
        normalized = norm.normalize(q)
        entries = router.build_cost_recap_entries(normalized, PROJECT_ID,
                                                   submittal_revision_id=rev_id)
        assert entries[0].source_submittal_revision_id == rev_id


# ---------------------------------------------------------------------------
# Filing engine tests
# ---------------------------------------------------------------------------

class TestFilingEngine:

    def test_governed_path_structure(self):
        """Filing path follows governed structure."""
        fe = FilingEngine()
        path = fe.resolve_path(
            project_id="AMS-2026-001",
            project_name="Macdill B53",
            vendor_name="Southeast TAB Services",
            trade_type="tab",
            quote_date="2026-06-16",
        )
        assert "AMS-2026-001" in path
        assert "tab" in path
        assert "quotes" in path
        assert "2026-06" in path
        assert "southeast-tab" in path

    def test_unknown_trade_uses_unknown_folder(self):
        """Unknown trade type uses 'unknown-trade' folder."""
        fe = FilingEngine()
        path = fe.resolve_path("proj-123", "Test Project", "Mystery Co", None, "2026-06-16")
        assert "unknown-trade" in path

    def test_file_document_returns_provenance(self):
        """file_document returns provenance record with required fields."""
        fe = FilingEngine()
        result = fe.file_document(
            source_path="/tmp/quote.pdf",
            filing_path="/project-files/proj-123/tab/quotes/2026-06/southeast-tab/",
            document_hash="abc123",
        )
        assert result["source_path"] == "/tmp/quote.pdf"
        assert result["document_hash"] == "abc123"
        assert result["source_system"] == "quote_intake"
        assert "filed_at" in result


# ---------------------------------------------------------------------------
# Coverage tracker tests
# ---------------------------------------------------------------------------

class TestCoverageTracker:

    def test_gap_report_identifies_missing_sections(self):
        """Coverage tracker identifies uncovered CSI sections."""
        norm = QuoteNormalizer()
        tracker = CoverageTracker()

        # Project requires TAB + Controls + Electrical
        required = ["230593", "230900", "260000"]

        # Only TAB quote received
        tab_quote = make_quote("Southeast TAB", 18500.00, [
            RawQuoteLine("TAB services", 18500.00)
        ])
        normalized_tab = norm.normalize(tab_quote)

        report = tracker.gap_report(PROJECT_ID, required, [normalized_tab])
        assert report["covered"] == 1
        assert report["missing"] == 2
        assert "230900" in report["missing_sections"]  # Controls
        assert "260000" in report["missing_sections"]  # Electrical

    def test_full_coverage_zero_gaps(self):
        """All required sections covered → no gaps."""
        norm = QuoteNormalizer()
        tracker = CoverageTracker()

        required = ["230593", "230900"]
        tab_q    = make_quote("Southeast TAB", 18500.00, [RawQuoteLine("TAB", 18500.00)])
        ctrl_q   = make_quote("Johnson Controls", 125000.00, [RawQuoteLine("DDC controls", 125000.00)])

        normalized = [norm.normalize(tab_q), norm.normalize(ctrl_q)]
        report = tracker.gap_report(PROJECT_ID, required, normalized)

        assert report["missing"] == 0
        assert report["coverage_pct"] == 100.0

    def test_empty_quotes_all_missing(self):
        """No quotes received → all sections missing."""
        tracker = CoverageTracker()
        required = ["230593", "230900", "260000"]
        report = tracker.gap_report(PROJECT_ID, required, [])
        assert report["missing"] == 3
        assert report["covered"] == 0
        assert report["coverage_pct"] == 0.0

    def test_coverage_pct_calculation(self):
        """Coverage percentage calculated correctly."""
        norm = QuoteNormalizer()
        tracker = CoverageTracker()

        required = ["230593", "230900", "260000", "211000"]
        tab_q = make_quote("Southeast TAB", 18500.00, [RawQuoteLine("TAB", 18500.00)])
        ctrl_q = make_quote("Johnson Controls", 125000.00, [RawQuoteLine("DDC controls", 125000.00)])

        normalized = [norm.normalize(tab_q), norm.normalize(ctrl_q)]
        report = tracker.gap_report(PROJECT_ID, required, normalized)
        assert report["covered"] == 2
        assert report["coverage_pct"] == 50.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd="/var/lib/openclaw/.openclaw/workspace"
    )
    print(result.stdout)
    print(result.stderr[-500:] if result.stderr else "")
