"""
Bid Tabulation Engine v1.0
Buildtronix Pre-Con — GC Mode + Sub Mode

Layout:
  Rows    = trade packages / scope items (Demo, Electrical, Plumbing, etc.)
  Columns = vendors/subs who quoted (dynamic, user-managed)
  Cells   = quote amount + notes + status
  Award   = per-row: which vendor won this trade

Both modes:
  GC Mode:  rows = CSI trade packages, columns = subcontractors
  Sub Mode: rows = products/materials/services, columns = suppliers
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ── Enums ────────────────────────────────────────────────────────────────────

class BidTabMode(str, Enum):
    GC  = "gc"
    SUB = "sub"


class CellStatus(str, Enum):
    PENDING    = "pending"    # Invited, no quote yet
    QUOTED     = "quoted"     # Quote received and entered
    NO_QUOTE   = "no_quote"   # Declined or no response
    EXCLUDED   = "excluded"   # Scope exclusion / not applicable


class AwardStatus(str, Enum):
    PENDING  = "pending"   # No decision yet
    AWARDED  = "awarded"   # Winning vendor for this trade
    BACKUP   = "backup"    # Second choice
    DECLINED = "declined"  # Not selected


class TabStatus(str, Enum):
    OPEN         = "open"          # Created, building vendor list
    RECEIVING    = "receiving"     # ITB sent, awaiting quotes
    UNDER_REVIEW = "under_review"  # Evaluating received quotes
    AWARDED      = "awarded"       # Winners selected, not yet locked
    LOCKED       = "locked"        # Finalized — no further edits
    NO_BID       = "no_bid"        # No quotes received, trade excluded


# ── Cell ─────────────────────────────────────────────────────────────────────

@dataclass
class BidCell:
    """One cell: intersection of trade row × vendor column."""
    cell_id:      str = field(default_factory=lambda: str(uuid.uuid4()))
    trade_row_id: str = ""
    vendor_col_id: str = ""
    amount:       Optional[float] = None    # Base quote amount
    alt_amount:   Optional[float] = None    # Alternate pricing
    inclusions:   str = ""                  # What is included
    exclusions:   str = ""                  # What is excluded (leveling critical)
    notes:        str = ""                  # Estimator notes
    status:       CellStatus = CellStatus.PENDING
    itb_sent_at:  Optional[datetime] = None
    quote_received_at: Optional[datetime] = None
    updated_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def receive_quote(self, amount: float, inclusions: str = "",
                      exclusions: str = "", notes: str = "") -> None:
        self.amount = amount
        self.inclusions = inclusions
        self.exclusions = exclusions
        self.notes = notes
        self.status = CellStatus.QUOTED
        self.quote_received_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def mark_no_quote(self) -> None:
        self.status = CellStatus.NO_QUOTE
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "cell_id":          self.cell_id,
            "trade_row_id":     self.trade_row_id,
            "vendor_col_id":    self.vendor_col_id,
            "amount":           self.amount,
            "alt_amount":       self.alt_amount,
            "inclusions":       self.inclusions,
            "exclusions":       self.exclusions,
            "notes":            self.notes,
            "status":           self.status.value,
            "itb_sent_at":      self.itb_sent_at.isoformat() if self.itb_sent_at else None,
            "quote_received_at": self.quote_received_at.isoformat() if self.quote_received_at else None,
        }


# ── Vendor Column ─────────────────────────────────────────────────────────────

@dataclass
class VendorColumn:
    """One vendor/sub column across all trade rows."""
    col_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    vendor_id:    Optional[str] = None      # FK to precon_vendors
    company_name: str = ""
    contact_name: str = ""
    email:        str = ""
    phone:        str = ""
    preferred:    bool = False
    sort_order:   int = 0
    added_at:     datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "col_id":       self.col_id,
            "vendor_id":    self.vendor_id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "email":        self.email,
            "phone":        self.phone,
            "preferred":    self.preferred,
            "sort_order":   self.sort_order,
        }


# ── Trade Row ────────────────────────────────────────────────────────────────

@dataclass
class TradeRow:
    """One trade package row (GC) or product/service row (Sub)."""
    row_id:         str = field(default_factory=lambda: str(uuid.uuid4()))
    trade_name:     str = ""        # e.g. "Demolition", "Electrical", "Pipe & Fittings"
    csi_code:       str = ""        # e.g. "024116", "260000"
    description:    str = ""
    sort_order:     int = 0
    award_status:   AwardStatus = AwardStatus.PENDING
    awarded_col_id: Optional[str] = None    # FK to VendorColumn
    backup_col_id:  Optional[str] = None
    award_notes:    str = ""
    awarded_at:     Optional[datetime] = None
    awarded_by:     Optional[str] = None    # user_id

    def award(self, col_id: str, awarded_by: str, notes: str = "") -> None:
        self.awarded_col_id = col_id
        self.award_status = AwardStatus.AWARDED
        self.award_notes = notes
        self.awarded_at = datetime.now(timezone.utc)
        self.awarded_by = awarded_by

    def set_backup(self, col_id: str) -> None:
        self.backup_col_id = col_id

    def to_dict(self) -> dict:
        return {
            "row_id":        self.row_id,
            "trade_name":    self.trade_name,
            "csi_code":      self.csi_code,
            "description":   self.description,
            "sort_order":    self.sort_order,
            "award_status":  self.award_status.value,
            "awarded_col_id": self.awarded_col_id,
            "backup_col_id": self.backup_col_id,
            "award_notes":   self.award_notes,
            "awarded_at":    self.awarded_at.isoformat() if self.awarded_at else None,
            "awarded_by":    self.awarded_by,
        }


# ── Bid Tab ───────────────────────────────────────────────────────────────────

@dataclass
class BidTab:
    """
    One bid tab = one project's complete evaluation matrix.

    Layout:
        rows    = List[TradeRow]      (trades down the left)
        columns = List[VendorColumn]  (subs across the top)
        cells   = dict[(row_id, col_id)] -> BidCell
    """
    tab_id:      str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id:  str = ""
    company_id:  str = ""
    project_name: str = ""
    mode:        BidTabMode = BidTabMode.GC
    status:      TabStatus = TabStatus.OPEN
    bid_due_date: Optional[datetime] = None
    locked_by:   Optional[str] = None
    locked_at:   Optional[datetime] = None
    created_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    rows:    list[TradeRow]    = field(default_factory=list)
    columns: list[VendorColumn] = field(default_factory=list)
    cells:   dict[tuple[str, str], BidCell] = field(default_factory=dict)

    # ── Structure ─────────────────────────────────────────────────────────────

    def add_trade_row(self, trade_name: str, csi_code: str = "",
                      description: str = "") -> TradeRow:
        """Add a trade package row."""
        if self.status == TabStatus.LOCKED:
            raise ValueError("Cannot modify a locked bid tab")
        row = TradeRow(
            trade_name=trade_name,
            csi_code=csi_code,
            description=description,
            sort_order=len(self.rows),
        )
        self.rows.append(row)
        # Create empty cells for all existing vendor columns
        for col in self.columns:
            self._init_cell(row.row_id, col.col_id)
        self._touch()
        return row

    def add_vendor_column(self, company_name: str, contact_name: str = "",
                          email: str = "", phone: str = "",
                          vendor_id: Optional[str] = None,
                          preferred: bool = False) -> VendorColumn:
        """Add a vendor/sub column."""
        if self.status == TabStatus.LOCKED:
            raise ValueError("Cannot modify a locked bid tab")
        col = VendorColumn(
            vendor_id=vendor_id,
            company_name=company_name,
            contact_name=contact_name,
            email=email,
            phone=phone,
            preferred=preferred,
            sort_order=len(self.columns),
        )
        self.columns.append(col)
        # Create empty cells for all existing trade rows
        for row in self.rows:
            self._init_cell(row.row_id, col.col_id)
        self._touch()
        return col

    def _init_cell(self, row_id: str, col_id: str) -> BidCell:
        key = (row_id, col_id)
        if key not in self.cells:
            cell = BidCell(trade_row_id=row_id, vendor_col_id=col_id)
            self.cells[key] = cell
        return self.cells[key]

    # ── Cell Operations ───────────────────────────────────────────────────────

    def get_cell(self, row_id: str, col_id: str) -> BidCell:
        return self.cells.get((row_id, col_id)) or self._init_cell(row_id, col_id)

    def enter_quote(self, row_id: str, col_id: str, amount: float,
                    inclusions: str = "", exclusions: str = "",
                    notes: str = "") -> BidCell:
        if self.status == TabStatus.LOCKED:
            raise ValueError("Cannot modify a locked bid tab")
        cell = self.get_cell(row_id, col_id)
        cell.receive_quote(amount, inclusions, exclusions, notes)
        if self.status == TabStatus.RECEIVING:
            self.status = TabStatus.UNDER_REVIEW
        self._touch()
        return cell

    def mark_no_quote(self, row_id: str, col_id: str) -> BidCell:
        if self.status == TabStatus.LOCKED:
            raise ValueError("Cannot modify a locked bid tab")
        cell = self.get_cell(row_id, col_id)
        cell.mark_no_quote()
        self._touch()
        return cell

    # ── Award ─────────────────────────────────────────────────────────────────

    def award_trade(self, row_id: str, col_id: str, awarded_by: str,
                    notes: str = "", backup_col_id: Optional[str] = None) -> TradeRow:
        """Award a trade to a vendor. Requires a quoted cell."""
        if self.status == TabStatus.LOCKED:
            raise ValueError("Cannot modify a locked bid tab")
        row = self._get_row(row_id)
        cell = self.get_cell(row_id, col_id)
        if cell.status != CellStatus.QUOTED:
            raise ValueError(f"Cannot award: cell status is {cell.status.value}, expected quoted")
        row.award(col_id, awarded_by, notes)
        if backup_col_id:
            row.set_backup(backup_col_id)
        self._touch()
        return row

    # ── Bid Lock ──────────────────────────────────────────────────────────────

    def validate_for_lock(self) -> list[str]:
        """
        Returns list of blocking issues. Empty list = safe to lock.
        Requires VP role check at API layer (not enforced here).
        """
        errors = []
        if not self.rows:
            errors.append("Bid tab has no trade rows")
        if not self.columns:
            errors.append("Bid tab has no vendor columns")
        unawardable = [r for r in self.rows if r.award_status == AwardStatus.PENDING]
        if unawardable:
            errors.append(
                f"{len(unawardable)} trade(s) have no award decision: "
                + ", ".join(r.trade_name for r in unawardable[:5])
            )
        return errors

    def lock(self, locked_by: str) -> None:
        """Lock the bid tab. Caller must verify VP+ role."""
        errors = self.validate_for_lock()
        if errors:
            raise ValueError("Bid lock blocked: " + "; ".join(errors))
        self.status = TabStatus.LOCKED
        self.locked_by = locked_by
        self.locked_at = datetime.now(timezone.utc)
        self._touch()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def lowest_quote_per_trade(self) -> dict[str, Optional[float]]:
        """Returns {row_id: lowest quoted amount} for each trade row."""
        result = {}
        for row in self.rows:
            amounts = [
                self.cells[(row.row_id, col.col_id)].amount
                for col in self.columns
                if (row.row_id, col.col_id) in self.cells
                and self.cells[(row.row_id, col.col_id)].status == CellStatus.QUOTED
                and self.cells[(row.row_id, col.col_id)].amount is not None
            ]
            result[row.row_id] = min(amounts) if amounts else None
        return result

    def total_awarded_amount(self) -> float:
        """Sum of awarded quote amounts across all trades."""
        total = 0.0
        for row in self.rows:
            if row.award_status == AwardStatus.AWARDED and row.awarded_col_id:
                cell = self.cells.get((row.row_id, row.awarded_col_id))
                if cell and cell.amount:
                    total += cell.amount
        return total

    def quote_count_per_trade(self) -> dict[str, int]:
        """Returns {row_id: number of quotes received} per trade."""
        result = {}
        for row in self.rows:
            count = sum(
                1 for col in self.columns
                if self.cells.get((row.row_id, col.col_id), BidCell()).status == CellStatus.QUOTED
            )
            result[row.row_id] = count
        return result

    def to_matrix(self) -> dict:
        """
        Returns the full tabulation matrix as a nested dict for UI rendering.
        {
          "columns": [...vendor columns...],
          "rows": [
            {
              "trade": {...row info...},
              "cells": {col_id: {...cell...}},
              "lowest_amount": float | None,
              "quote_count": int,
            }
          ],
          "total_awarded": float,
          "status": str,
        }
        """
        lowest = self.lowest_quote_per_trade()
        qcount = self.quote_count_per_trade()
        rows_out = []
        for row in sorted(self.rows, key=lambda r: r.sort_order):
            cells_out = {}
            for col in self.columns:
                cell = self.cells.get((row.row_id, col.col_id))
                cells_out[col.col_id] = cell.to_dict() if cell else None
            rows_out.append({
                "trade":         row.to_dict(),
                "cells":         cells_out,
                "lowest_amount": lowest.get(row.row_id),
                "quote_count":   qcount.get(row.row_id, 0),
            })
        return {
            "tab_id":         self.tab_id,
            "project_id":     self.project_id,
            "company_id":     self.company_id,
            "project_name":   self.project_name,
            "mode":           self.mode.value,
            "status":         self.status.value,
            "columns":        [c.to_dict() for c in sorted(self.columns, key=lambda c: c.sort_order)],
            "rows":           rows_out,
            "total_awarded":  self.total_awarded_amount(),
            "locked_by":      self.locked_by,
            "locked_at":      self.locked_at.isoformat() if self.locked_at else None,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_row(self, row_id: str) -> TradeRow:
        for r in self.rows:
            if r.row_id == row_id:
                return r
        raise KeyError(f"Trade row not found: {row_id}")

    def _get_col(self, col_id: str) -> VendorColumn:
        for c in self.columns:
            if c.col_id == col_id:
                return c
        raise KeyError(f"Vendor column not found: {col_id}")

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
