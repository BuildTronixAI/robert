"""
NEWCO VENDOR REGISTRY — Integration tests
Real company names from AMS vendor list → correct trade + codes
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import uuid
from precon.quote_intake.newco_vendors import (
    lookup_vendor, list_vendors_by_trade, get_all_bid_emails_for_trade, NEWCO_VENDORS
)
from precon.quote_intake.quote_intake import (
    QuoteNormalizer, QuoteRouter, RawQuote, RawQuoteLine
)

def make_id(): return str(uuid.uuid4())
PROJECT_ID = make_id()

def make_quote(vendor, total, lines=None):
    return RawQuote(
        raw_quote_id=make_id(), vendor_name=vendor,
        project_ref="AMS-2026-001", quote_date="2026-06-16",
        total_amount=total, line_items=lines or [],
        source_file=f"/tmp/{vendor.lower()[:20]}.pdf",
    )


class TestVendorLookup:

    def test_ecotab_resolves_to_tab(self):
        v = lookup_vendor("EcoTab")
        assert v is not None
        assert v.trade_type == "tab"
        assert "503" in v.cost_codes
        assert "230593" in v.csi_sections

    def test_rome_insulation_resolves(self):
        v = lookup_vendor("Rome Insulation")
        assert v is not None
        assert v.trade_type == "insulation"
        assert "501" in v.cost_codes

    def test_johnson_controls_resolves(self):
        v = lookup_vendor("Johnson Controls")
        assert v is not None
        assert v.trade_type == "controls"
        assert "502" in v.cost_codes
        assert "230900" in v.csi_sections

    def test_ferguson_resolves_to_plumbing_supplier(self):
        v = lookup_vendor("Ferguson")
        assert v is not None
        assert v.trade_type == "plumbing_supplier"
        assert "304" in v.cost_codes

    def test_siemens_resolves_to_controls(self):
        v = lookup_vendor("Siemens")
        assert v is not None
        assert v.trade_type == "controls"

    def test_mercury_med_resolves_to_medical_gas(self):
        v = lookup_vendor("Mercury Med")
        assert v is not None
        assert v.trade_type == "medical_gas"
        assert "226000" in v.csi_sections
        assert "517" in v.cost_codes

    def test_trane_resolves_to_hvac_supplier(self):
        v = lookup_vendor("Trane")
        assert v is not None
        assert v.trade_type == "hvac_supplier"

    def test_carrier_enterprise_resolves(self):
        v = lookup_vendor("Carrier Enterprise")
        assert v is not None
        assert v.trade_type == "hvac_supplier"
        assert v.email is not None

    def test_unknown_vendor_returns_none(self):
        v = lookup_vendor("Random Company XYZ 999")
        assert v is None

    def test_partial_match_smith_casady(self):
        v = lookup_vendor("Smith & Casady")
        assert v is not None
        assert v.trade_type == "insulation"

    def test_commercial_duct_resolves_to_sheet_metal(self):
        v = lookup_vendor("Commercial Duct Systems")
        assert v is not None
        assert v.trade_type == "sheet_metal_contractor"

    def test_captive_aire_resolves_to_kitchen_hoods(self):
        v = lookup_vendor("Captive Aire")
        assert v is not None
        assert v.trade_type == "kitchen_hoods"
        assert "233813" in v.csi_sections


class TestTradeListings:

    def test_tab_vendors_list(self):
        vendors = list_vendors_by_trade("tab")
        names = [v.name for v in vendors]
        assert "EcoTab" in names
        assert "Bay to Bay / Palmetto" in names
        assert "Omni Balancing Solutions" in names
        assert len(vendors) >= 4

    def test_controls_vendors_list(self):
        vendors = list_vendors_by_trade("controls")
        names = [v.name for v in vendors]
        assert "Johnson Controls" in names
        assert "Siemens" in names
        assert len(vendors) >= 8

    def test_insulation_vendors_list(self):
        vendors = list_vendors_by_trade("insulation")
        names = [v.name for v in vendors]
        assert "Rome Insulation" in names
        assert "General Insulation" in names
        assert len(vendors) >= 4

    def test_rfq_blast_emails_for_tab(self):
        """get_all_bid_emails_for_trade returns email list for RFQ blast."""
        emails = get_all_bid_emails_for_trade("tab")
        # Some TAB vendors don't have emails yet — that's OK
        # At least the function returns the structure
        assert isinstance(emails, list)
        for e in emails:
            assert "vendor" in e
            assert "email" in e

    def test_rfq_blast_emails_for_hvac_supplier(self):
        """HVAC suppliers have bid emails wired."""
        emails = get_all_bid_emails_for_trade("hvac_supplier")
        email_addresses = [e["email"] for e in emails if e["email"]]
        assert len(email_addresses) >= 4
        assert any("carrierenterprise" in addr for addr in email_addresses)
        assert any("stanweaver" in addr for addr in email_addresses)


class TestNormalizerWithRealVendors:

    def test_ecotab_quote_maps_correctly(self):
        norm = QuoteNormalizer()
        profile = lookup_vendor("EcoTab")
        q = make_quote("EcoTab", 22000.00, [
            RawQuoteLine("Complete TAB services per spec 230593", 22000.00)
        ])
        result = norm.normalize(q, vendor_profile=profile)
        assert result.trade_type == "tab"
        assert "503" in result.coverage_cost_codes
        assert "230593" in result.coverage_csi_sections
        assert not result.needs_review

    def test_rome_insulation_quote_maps_correctly(self):
        norm = QuoteNormalizer()
        profile = lookup_vendor("Rome Insulation")
        q = make_quote("Rome Insulation", 38000.00, [
            RawQuoteLine("Mechanical insulation all piping", 38000.00)
        ])
        result = norm.normalize(q, vendor_profile=profile)
        assert result.trade_type == "insulation"
        assert "501" in result.coverage_cost_codes

    def test_johnson_controls_quote_cost_recap(self):
        """JCI quote → cost_recap_entries with correct code and phase."""
        norm = QuoteNormalizer()
        router = QuoteRouter()
        profile = lookup_vendor("Johnson Controls")
        q = make_quote("Johnson Controls", 145000.00, [
            RawQuoteLine("BAS DDC controls full system", 145000.00)
        ])
        normalized = norm.normalize(q, vendor_profile=profile)
        entries = router.build_cost_recap_entries(normalized, PROJECT_ID)
        assert len(entries) >= 1
        # Controls → 502 → 50-SUBS phase
        sub_entries = [e for e in entries if e.phase == "50-SUBS"]
        assert len(sub_entries) >= 1
        assert sub_entries[0].sub_cost == 145000.00
        assert sub_entries[0].vendor_name == "Johnson Controls"

    def test_mercury_med_quote_maps_to_medical_gas(self):
        norm = QuoteNormalizer()
        router = QuoteRouter()
        profile = lookup_vendor("Mercury Med")
        q = make_quote("Mercury Med", 65000.00, [
            RawQuoteLine("Medical gas and vacuum systems installation", 65000.00)
        ])
        normalized = norm.normalize(q, vendor_profile=profile)
        assert "226000" in normalized.coverage_csi_sections
        gc_view = router.build_gc_view(normalized)
        assert gc_view[0]["csi_section"] == "226000"
        assert gc_view[0]["csi_description"] == "Medical Gas & Vacuum Systems"

    def test_full_bid_day_scenario(self):
        """
        Simulate 5 quotes arriving on bid day.
        Verify coverage tracker shows correct gaps.
        """
        norm = QuoteNormalizer()
        tracker_obj = __import__(
            'precon.quote_intake.quote_intake', fromlist=['CoverageTracker']
        ).CoverageTracker()

        required_csi = ["230593", "230900", "226000", "211000", "260000"]

        quotes = [
            ("EcoTab",           18500,  [RawQuoteLine("TAB", 18500)]),
            ("Johnson Controls", 145000, [RawQuoteLine("BAS controls", 145000)]),
            ("Mercury Med",      65000,  [RawQuoteLine("Med gas", 65000)]),
            # Fire sprinkler and electrical NOT received yet
        ]

        normalized = []
        for vendor, amount, lines in quotes:
            profile = lookup_vendor(vendor)
            q = make_quote(vendor, amount, lines)
            normalized.append(norm.normalize(q, vendor_profile=profile))

        report = tracker_obj.gap_report(PROJECT_ID, required_csi, normalized)

        assert report["covered"] == 3
        assert report["missing"] == 2
        assert "211000" in report["missing_sections"]  # Fire sprinkler
        assert "260000" in report["missing_sections"]  # Electrical
        assert report["coverage_pct"] == 60.0

    def test_vendor_registry_total_count(self):
        """Sanity: verify vendor count matches what was seeded."""
        assert len(NEWCO_VENDORS) >= 35


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd="/var/lib/openclaw/.openclaw/workspace"
    )
    print(result.stdout)
    print(result.stderr[-500:] if result.stderr else "")
