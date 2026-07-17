"""
Bid Tabulation Engine Test Suite
Tests: structure, quote entry, award flow, bid lock, analysis, both modes
"""
import pytest
import sys, os
sys.path.insert(0, os.path.abspath('../../..'))

from precon.bid_tab.bid_tab import (
    BidTab, TradeRow, VendorColumn, BidCell,
    BidTabMode, TabStatus, AwardStatus, CellStatus
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def make_gc_tab() -> BidTab:
    tab = BidTab(project_id="proj-001", company_id="trias-construction",
                 project_name="Langley Pharmacy Ocala", mode=BidTabMode.GC)
    return tab

def populated_gc_tab() -> BidTab:
    """GC tab with 3 trades + 3 subs, quotes entered."""
    tab = make_gc_tab()
    # Trades
    demo = tab.add_trade_row("Demolition", "024116")
    elec = tab.add_trade_row("Electrical", "260000")
    plmb = tab.add_trade_row("Plumbing", "220000")
    # Vendors
    paw  = tab.add_vendor_column("PAW Demolition", "Derek Wohlfiel", preferred=True)
    ici  = tab.add_vendor_column("ICI Contracting", "Michelle Mathews")
    jdp  = tab.add_vendor_column("JDP Electric", "Eric Dowling", preferred=True)
    bell = tab.add_vendor_column("Bella Plumbing", "Jessica Martinez")
    # Quotes
    tab.enter_quote(demo.row_id, paw.col_id, 38500, inclusions="Full demo, debris removal", exclusions="Hazmat")
    tab.enter_quote(demo.row_id, ici.col_id, 45000, inclusions="Full demo", exclusions="")
    tab.enter_quote(elec.row_id, jdp.col_id, 138000, inclusions="Full electrical", exclusions="Fire alarm")
    tab.enter_quote(plmb.row_id, bell.col_id, 52000, inclusions="Rough and finish", exclusions="")
    tab.mark_no_quote(elec.row_id, paw.col_id)
    tab.mark_no_quote(plmb.row_id, paw.col_id)
    return tab, demo, elec, plmb, paw, ici, jdp, bell


# ── Structure Tests ───────────────────────────────────────────────────────────

def test_create_gc_tab():
    tab = make_gc_tab()
    assert tab.mode == BidTabMode.GC
    assert tab.status == TabStatus.OPEN
    assert len(tab.rows) == 0
    assert len(tab.columns) == 0

def test_add_trade_row():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demolition", "024116", "Building demo and debris removal")
    assert row.trade_name == "Demolition"
    assert row.csi_code == "024116"
    assert row.award_status == AwardStatus.PENDING
    assert len(tab.rows) == 1

def test_add_vendor_column():
    tab = make_gc_tab()
    col = tab.add_vendor_column("PAW Demolition", "Derek Wohlfiel", preferred=True)
    assert col.company_name == "PAW Demolition"
    assert col.preferred == True
    assert len(tab.columns) == 1

def test_cells_created_on_structure_add():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demo", "024116")
    col = tab.add_vendor_column("PAW Demo")
    assert (row.row_id, col.col_id) in tab.cells

def test_adding_row_creates_cells_for_existing_cols():
    tab = make_gc_tab()
    col1 = tab.add_vendor_column("Sub A")
    col2 = tab.add_vendor_column("Sub B")
    row = tab.add_trade_row("Demo", "024116")
    assert (row.row_id, col1.col_id) in tab.cells
    assert (row.row_id, col2.col_id) in tab.cells

def test_adding_col_creates_cells_for_existing_rows():
    tab = make_gc_tab()
    row1 = tab.add_trade_row("Demo", "024116")
    row2 = tab.add_trade_row("Electrical", "260000")
    col = tab.add_vendor_column("Sub A")
    assert (row1.row_id, col.col_id) in tab.cells
    assert (row2.row_id, col.col_id) in tab.cells

def test_multiple_trades_and_vendors():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    assert len(tab.rows) == 3
    assert len(tab.columns) == 4
    assert len(tab.cells) == 12  # 3 rows × 4 cols


# ── Quote Entry Tests ─────────────────────────────────────────────────────────

def test_enter_quote_updates_cell():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    cell = tab.get_cell(demo.row_id, paw.col_id)
    assert cell.status == CellStatus.QUOTED
    assert cell.amount == 38500
    assert cell.inclusions == "Full demo, debris removal"
    assert cell.exclusions == "Hazmat"

def test_enter_quote_updates_tab_status():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demo", "024116")
    col = tab.add_vendor_column("Sub A")
    tab.status = TabStatus.RECEIVING
    tab.enter_quote(row.row_id, col.col_id, 50000)
    assert tab.status == TabStatus.UNDER_REVIEW

def test_mark_no_quote():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    cell = tab.get_cell(elec.row_id, paw.col_id)
    assert cell.status == CellStatus.NO_QUOTE

def test_initial_cell_status_is_pending():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demo", "024116")
    col = tab.add_vendor_column("Sub A")
    cell = tab.get_cell(row.row_id, col.col_id)
    assert cell.status == CellStatus.PENDING

def test_quote_received_at_set():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demo", "024116")
    col = tab.add_vendor_column("Sub A")
    tab.enter_quote(row.row_id, col.col_id, 45000)
    cell = tab.get_cell(row.row_id, col.col_id)
    assert cell.quote_received_at is not None


# ── Award Flow Tests ──────────────────────────────────────────────────────────

def test_award_trade():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001",
                    notes="Preferred sub, competitive price")
    assert demo.award_status == AwardStatus.AWARDED
    assert demo.awarded_col_id == paw.col_id
    assert demo.awarded_by == "user-vp-001"

def test_award_sets_backup():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001",
                    backup_col_id=ici.col_id)
    assert demo.backup_col_id == ici.col_id

def test_cannot_award_unquoted_cell():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demo", "024116")
    col = tab.add_vendor_column("Sub A")
    with pytest.raises(ValueError, match="Cannot award"):
        tab.award_trade(row.row_id, col.col_id, awarded_by="user-001")

def test_cannot_award_no_quote_cell():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    with pytest.raises(ValueError, match="Cannot award"):
        tab.award_trade(elec.row_id, paw.col_id, awarded_by="user-001")

def test_award_multiple_trades():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001")
    tab.award_trade(elec.row_id, jdp.col_id, awarded_by="user-vp-001")
    tab.award_trade(plmb.row_id, bell.col_id, awarded_by="user-vp-001")
    assert demo.award_status == AwardStatus.AWARDED
    assert elec.award_status == AwardStatus.AWARDED
    assert plmb.award_status == AwardStatus.AWARDED


# ── Bid Lock Tests ─────────────────────────────────────────────────────────────

def test_lock_requires_all_trades_awarded():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    errors = tab.validate_for_lock()
    assert len(errors) > 0
    assert any("award decision" in e for e in errors)

def test_lock_succeeds_when_all_awarded():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001")
    tab.award_trade(elec.row_id, jdp.col_id, awarded_by="user-vp-001")
    tab.award_trade(plmb.row_id, bell.col_id, awarded_by="user-vp-001")
    errors = tab.validate_for_lock()
    assert errors == []
    tab.lock("user-vp-001")
    assert tab.status == TabStatus.LOCKED
    assert tab.locked_by == "user-vp-001"
    assert tab.locked_at is not None

def test_locked_tab_rejects_edits():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001")
    tab.award_trade(elec.row_id, jdp.col_id, awarded_by="user-vp-001")
    tab.award_trade(plmb.row_id, bell.col_id, awarded_by="user-vp-001")
    tab.lock("user-vp-001")
    with pytest.raises(ValueError, match="locked"):
        tab.enter_quote(demo.row_id, ici.col_id, 99999)

def test_locked_tab_rejects_new_rows():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001")
    tab.award_trade(elec.row_id, jdp.col_id, awarded_by="user-vp-001")
    tab.award_trade(plmb.row_id, bell.col_id, awarded_by="user-vp-001")
    tab.lock("user-vp-001")
    with pytest.raises(ValueError, match="locked"):
        tab.add_trade_row("New Trade", "099000")

def test_lock_fails_on_empty_tab():
    tab = make_gc_tab()
    errors = tab.validate_for_lock()
    assert any("no trade rows" in e for e in errors)


# ── Analysis Tests ─────────────────────────────────────────────────────────────

def test_lowest_quote_per_trade():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    lowest = tab.lowest_quote_per_trade()
    assert lowest[demo.row_id] == 38500   # PAW < ICI
    assert lowest[elec.row_id] == 138000  # Only JDP quoted
    assert lowest[plmb.row_id] == 52000   # Only Bella quoted

def test_total_awarded_amount():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001")
    tab.award_trade(elec.row_id, jdp.col_id, awarded_by="user-vp-001")
    tab.award_trade(plmb.row_id, bell.col_id, awarded_by="user-vp-001")
    total = tab.total_awarded_amount()
    assert total == 38500 + 138000 + 52000  # 228500

def test_quote_count_per_trade():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    counts = tab.quote_count_per_trade()
    assert counts[demo.row_id] == 2   # PAW + ICI
    assert counts[elec.row_id] == 1   # JDP only
    assert counts[plmb.row_id] == 1   # Bella only

def test_no_quotes_returns_none_for_lowest():
    tab = make_gc_tab()
    row = tab.add_trade_row("Demo", "024116")
    tab.add_vendor_column("Sub A")
    lowest = tab.lowest_quote_per_trade()
    assert lowest[row.row_id] is None


# ── Matrix Output Tests ────────────────────────────────────────────────────────

def test_to_matrix_structure():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    matrix = tab.to_matrix()
    assert matrix["mode"] == "gc"
    assert len(matrix["columns"]) == 4
    assert len(matrix["rows"]) == 3
    assert matrix["status"] in ("under_review", "open", "receiving")

def test_to_matrix_cell_data():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    matrix = tab.to_matrix()
    demo_row = next(r for r in matrix["rows"] if r["trade"]["trade_name"] == "Demolition")
    cell = demo_row["cells"][paw.col_id]
    assert cell["amount"] == 38500
    assert cell["status"] == "quoted"

def test_to_matrix_lowest_amount():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    matrix = tab.to_matrix()
    demo_row = next(r for r in matrix["rows"] if r["trade"]["trade_name"] == "Demolition")
    assert demo_row["lowest_amount"] == 38500

def test_to_matrix_total_awarded():
    tab, demo, elec, plmb, paw, ici, jdp, bell = populated_gc_tab()
    tab.award_trade(demo.row_id, paw.col_id, awarded_by="user-vp-001")
    tab.award_trade(elec.row_id, jdp.col_id, awarded_by="user-vp-001")
    tab.award_trade(plmb.row_id, bell.col_id, awarded_by="user-vp-001")
    matrix = tab.to_matrix()
    assert matrix["total_awarded"] == 228500


# ── Sub Mode Tests ─────────────────────────────────────────────────────────────

def test_sub_mode_tab():
    tab = BidTab(project_id="proj-002", company_id="newco",
                 project_name="OLOR Church", mode=BidTabMode.SUB)
    assert tab.mode == BidTabMode.SUB

def test_sub_mode_rows_are_products():
    tab = BidTab(project_id="proj-002", company_id="newco",
                 project_name="OLOR Church", mode=BidTabMode.SUB)
    row1 = tab.add_trade_row("4\" PVC Pipe", "220000", "Sanitary drain line")
    row2 = tab.add_trade_row("RTU Units (3-ton)", "230000", "Carrier or equivalent")
    row3 = tab.add_trade_row("Ductwork", "230000", "Sheet metal supply/return")
    assert len(tab.rows) == 3
    assert row1.trade_name == "4\" PVC Pipe"

def test_sub_mode_columns_are_suppliers():
    tab = BidTab(project_id="proj-002", company_id="newco",
                 project_name="OLOR Church", mode=BidTabMode.SUB)
    tab.add_trade_row("4\" PVC Pipe", "220000")
    s1 = tab.add_vendor_column("Ferguson Supply", "Mike Johnson")
    s2 = tab.add_vendor_column("Winsupply", "Tom Davis")
    s3 = tab.add_vendor_column("HD Supply", "Janet Lee")
    assert len(tab.columns) == 3

def test_sub_mode_full_flow():
    tab = BidTab(project_id="proj-002", company_id="newco",
                 project_name="OLOR Church", mode=BidTabMode.SUB)
    pipe = tab.add_trade_row("4\" PVC Pipe", "220000")
    rtu  = tab.add_trade_row("RTU Units", "230000")
    ferg = tab.add_vendor_column("Ferguson Supply")
    wins = tab.add_vendor_column("Winsupply")
    tab.enter_quote(pipe.row_id, ferg.col_id, 4200)
    tab.enter_quote(pipe.row_id, wins.col_id, 3950)
    tab.enter_quote(rtu.row_id, ferg.col_id, 18500)
    tab.mark_no_quote(rtu.row_id, wins.col_id)
    tab.award_trade(pipe.row_id, wins.col_id, awarded_by="user-pm-001")
    tab.award_trade(rtu.row_id, ferg.col_id, awarded_by="user-pm-001")
    errors = tab.validate_for_lock()
    assert errors == []
    assert tab.total_awarded_amount() == 3950 + 18500


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=False
    )
