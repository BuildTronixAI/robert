# Pre-Con AI Takeoff Viewport — Spec v1.0
**Status:** DRAFT — June 17, 2026  
**Author:** BOB (Chief of Staff)  
**Product:** Buildtronix Pre-Con Module  
**Component:** AI Takeoff Viewport (ATV)

---

## 1. Purpose

The AI Takeoff Viewport is the visual proof layer for Engine 1. When Engine 1 reads a document and extracts scope items, quantities, and conflicts — the estimator can see *exactly what the AI saw* on the actual document, overlaid with annotations. This is not a PDF viewer bolted on. It is the primary verification interface between the AI's extraction and the estimator's judgment.

Without this, the estimator is asked to trust a list of extracted items with no way to verify them against the source. The ATV closes that gap.

---

## 2. Core Design Principles

1. **AI shows its work.** Every extracted item traces back to a location on the document. No orphaned data.
2. **Multiple documents, multiple views.** Estimator can open drawings, specs, and schedules simultaneously. Independent panels, synchronized when relevant.
3. **Two annotation modes.** Overlay (annotations on top of document) and side-by-side (document left, annotation list right). Estimator toggles per panel.
4. **Two granularity levels.** Zone-level (area color overlay for broad coverage) and item-level (pin/callout per extracted item). Both shown simultaneously — zones first, pins on demand.
5. **Desktop-first, mobile-capable.** Full feature set on desktop. Mobile collapses to single panel, swipeable between document and annotation list.
6. **Read-only for the document.** The PDF is never modified. Annotations are a separate layer stored in the database.

---

## 3. Document Types & Behavior

| Type | Annotation Style | Notes |
|------|-----------------|-------|
| Drawings (MEP/Architectural) | Zone overlays + item pins | Primary use case. Color by trade. |
| Specifications | Section highlights + paragraph callouts | Per-section extraction shown inline |
| Schedules (equipment, door, finish) | Row highlights + conflict flags | Row-level confidence scores |
| Addenda | Diff overlay — what changed vs. base | Side-by-side with base document |
| Vendor Quotes | Line item extraction markers | Rate and quantity confidence per line |

---

## 4. Panel System

### 4.1 Multi-Panel Layout

The ATV is a **panel workspace** — estimators can open multiple documents simultaneously.

```
┌─────────────────────────────────────────────────────────────────┐
│  [ATV Workspace]  [+ Add Panel ▾]  [Sync All]  [Close All]     │
├────────────────────────┬────────────────────────────────────────┤
│  Panel 1               │  Panel 2                               │
│  M-201 HVAC Floor Plan │  Mechanical Schedule                   │
│  [Overlay ▾] [Zones]   │  [Side-by-Side ▾] [Rows]              │
│                        │                                        │
│  [  PDF + overlays  ]  │  [ PDF ]  │  [ Annotation List ]      │
│                        │                                        │
└────────────────────────┴────────────────────────────────────────┘
```

**Rules:**
- No hard limit on open panels (browser memory permitting; warn at 5+)
- Each panel is independent by default
- **Sync mode**: When two panels are synced, selecting an item in Panel 1 highlights its reference in Panel 2 (e.g., FCU-101 on drawing syncs to FCU-101 row in schedule)
- Panels can be resized (drag divider), minimized, or popped out to a second monitor (detach to new browser tab)

### 4.2 Panel Header Controls

Each panel has:
- Document name + page selector (dropdown, prev/next arrows)
- View mode toggle: **Overlay** | **Side-by-Side**
- Granularity: **Zones** | **Items** | **Both**
- Filter: **All Items** | **Flagged** | **Conflicts** | **Unreviewed** | **By Trade**
- Sync toggle (link icon — pair with another panel)
- Zoom controls (fit-to-width, fit-to-height, %, +/-)
- Download original PDF button

---

## 5. Annotation Layers

### 5.1 Zone Overlays (Area Level)

Color-coded semi-transparent polygons drawn on top of the document page. Each zone represents a spatial region the AI identified as belonging to a scope area.

**Zone color coding — by extraction status:**
| Status | Color | Meaning |
|--------|-------|---------|
| Confirmed | Emerald (#10b981, 20% opacity) | Estimator approved all items in zone |
| Flagged | Amber (#f59e0b, 25% opacity) | One or more items need review |
| Conflict | Red (#ef4444, 30% opacity) | Disagreement between documents |
| Unreviewed | Blue (#3b82f6, 20% opacity) | AI extracted, not yet reviewed |
| Excluded | Gray (#6b7280, 15% opacity) | Estimator marked out of scope |

**Zone interaction:**
- Hover: show zone label + item count tooltip
- Click: expand zone panel (slides in from right in overlay mode, highlights rows in side-by-side mode)
- Zone panel shows all extracted items within that zone

### 5.2 Item Pins (Item Level)

Each individual extracted item gets a pin at its location on the document. Pins are shown when **Items** or **Both** granularity is selected.

**Pin anatomy:**
```
  ┌───────────────────┐
  │ FCU-101           │   ← Equipment tag / item label
  │ 2 Ton / 800 CFM   │   ← Primary extracted value
  │ ⚠ Conf: MEDIUM    │   ← Confidence indicator
  └───────┬───────────┘
          │
          ●  ← Point on drawing (callout line to exact location)
```

**Pin colors match zone colors** (confirmed/flagged/conflict/unreviewed/excluded).

**Pin interaction:**
- Click pin → open Item Detail Panel (see §6)
- Hover → show quick summary tooltip
- Pins can be toggled off per trade (show only Plumbing pins, hide HVAC)

### 5.3 Annotation in Specs (Text Documents)

For spec sections and addenda:
- **Section highlight**: entire section gets a left border color (same status palette)
- **Paragraph callout**: specific paragraph or sentence highlighted inline with the extracted value shown in margin
- **Addendum diff**: changed text shown with green/red diff overlay vs. base document

### 5.4 Annotation in Schedules (Tables)

For equipment schedules, door schedules, finish schedules:
- **Row highlight**: entire row colored by status
- **Cell callout**: extracted value shown in cell, with confidence score
- **Conflict cell**: red border on specific cell where values disagree across documents

---

## 6. Item Detail Panel

When an estimator clicks a pin, zone, or annotation callout, the Item Detail Panel opens. This is the single most important UI interaction — it shows everything the AI knows about one extracted item.

```
┌────────────────────────────────────────────────────────┐
│  FCU-101 — Fan Coil Unit                        [×]    │
│  ─────────────────────────────────────────────────────  │
│  EXTRACTED VALUES                                       │
│  Capacity:    2 Ton / 24,000 BTU/hr                    │
│  CFM:         800 CFM                                  │
│  Qty:         1 EA                                     │
│  Location:    Zone 3 — East Office Wing, Level 1       │
│  Cost Code:   23-82-00 (Fan Coil Units)                │
│                                                        │
│  CONFIDENCE                                            │
│  ████████░░  HIGH (82%)  SOURCE-DERIVED                │
│  Source: M-201 Equipment Schedule, Row 14              │
│                                                        │
│  CROSS-REFERENCES                                      │
│  ✓ M-301 Piping Plan — FCU-101 shown connected        │
│  ✓ Spec 23 82 19 — FCU-101 tag confirmed              │
│  ⚠ Addendum 2 — CFM revised to 850 CFM (updated)     │
│                                                        │
│  CONFLICTS                                             │
│  ⚠ Drawing M-201 shows 800 CFM                        │
│    Addendum 2 says 850 CFM                             │
│    → AI used ADDENDUM (most recent)                    │
│                                                        │
│  ESTIMATOR DECISION                         [Pending]  │
│  ○ Confirm as-is     ○ Override value                  │
│  ○ Flag for review   ○ Exclude from scope              │
│  Notes: ________________________________               │
│                                                        │
│  [Confirm]  [Override]  [Flag]  [Exclude]              │
└────────────────────────────────────────────────────────┘
```

**Item Detail Panel syncs with the Screen 2 takeoff table** — a decision made in the viewport is reflected in Screen 2 immediately and vice versa.

---

## 7. Trade Filter System

Every annotation layer can be filtered by trade. The trade filter appears in each panel header.

**Default trades (configurable per company):**
- All Trades
- HVAC (Div 23)
- Plumbing (Div 22)
- Controls (Div 23 09)
- Fire Protection (Div 21)
- Electrical (Div 26) — visible only in GC mode
- Architectural (Div 06/08/09) — visible only in GC mode
- Structural (Div 03/05) — visible only in GC mode

Filtering by trade dims all other annotations to 10% opacity. Active trade annotations remain full.

---

## 8. Sync System

Two panels can be synced. When synced:
- Selecting FCU-101 pin in Panel 1 (drawing) → auto-scrolls Panel 2 (schedule) to FCU-101 row and highlights it
- Selecting a spec section in Panel 1 → highlights relevant cost codes in Panel 2 (scope list)
- Conflicts found in one panel surface as indicators in the synced panel

**Sync is bi-directional.** Action in either panel propagates to the other.

**Multi-panel sync (3+ panels):** Any panel can be the "anchor." Others follow the anchor. Anchor is indicated by a gold chain icon.

---

## 9. Document Navigator

At the workspace level, a collapsible left sidebar shows all documents in the project:

```
┌─────────────────────┐
│  Documents (8)       │
│  ───────────────────│
│  ▸ Drawings (5)     │
│    M-201 Floor Plan  │ ● 24 items
│    M-301 Piping      │ ● 18 items
│    M-401 Details     │ ● 6 items
│    P-101 Plumbing    │ ● 31 items
│    P-201 Isometrics  │ ● 12 items
│  ▸ Specs (2)        │
│    Div 22 Plumbing   │ ⚠ 3 flags
│    Div 23 HVAC       │ ⚠ 1 conflict
│  ▸ Addenda (1)      │
│    Addendum 2        │ 🔴 2 changes
│                     │
│  [Open in Panel ▾]  │
└─────────────────────┘
```

Each document shows:
- Total extracted items
- Flag count (orange ⚠)
- Conflict count (red)
- Review completion percentage

Double-click → opens in current active panel
Right-click → "Open in New Panel" / "Open in Synced Panel"

---

## 10. Extraction Confidence Display

Every extracted item carries a confidence score (0–100) and a source tier:

| Source Tier | Meaning | Typical Confidence |
|-------------|---------|-------------------|
| SOURCE-DERIVED | Found directly in this document | 85–99% |
| CROSS-REFERENCE | Inferred from two documents | 55–84% |
| HEURISTIC | Building-type expectation only | 20–54% |

**Visual treatment:**
- HIGH (≥80%): solid green pin, no badge
- MEDIUM (50–79%): amber pin, "⚠ MEDIUM" badge
- LOW (<50%): red pin, "LOW" badge, auto-flagged for review

Heuristic items render with a dashed outline on their zone/pin to visually distinguish from document-sourced items.

---

## 11. Conflict Resolution Flow

When Engine 1 detects a conflict between two documents (e.g., drawing says 800 CFM, addendum says 850 CFM):

1. Both references shown in Item Detail Panel
2. AI decision shown with reasoning (e.g., "Used Addendum — most recent supersedes")
3. Estimator can:
   - **Accept AI decision** — confirm the addendum value
   - **Override to drawing value** — with required note
   - **Mark unresolved** — surfaces to Screen 1 as an interpretation flag
4. Resolved conflicts shown with green checkmark in both source documents
5. Unresolved conflicts block Screen 1 advancement (treated as interpretation items)

---

## 12. Viewport ↔ Screen Integration

The ATV is not a standalone tool — it is integrated with the review screens:

| ATV Action | Screen Effect |
|-----------|--------------|
| Confirm item in viewport | Screen 2 row marked approved |
| Flag item in viewport | Screen 1 interpretation item created |
| Override value in viewport | Screen 2 row shows corrected value + source note |
| Exclude item in viewport | Screen 2 row marked excluded |
| Resolve conflict in viewport | Screen 1 interpretation item closed |

**Entry points:**
- Screen 1: Each interpretation flag has a "View in Drawing →" button → opens ATV to the relevant location
- Screen 2: Each takeoff row has a "View Source →" button → opens ATV to the source document
- Screen 2.5: Each coverage gap has "Show Evidence →" button → opens relevant document
- ATV has a "Return to Review →" button to go back to the active screen

---

## 13. Mobile Behavior

On screens < 768px:
- Single panel view only
- Document and annotation list are swipeable tabs (left: document, right: annotations)
- Item Detail Panel opens as a bottom sheet (slides up from bottom, covers 70% of screen)
- Trade filter shown as horizontal scroll chips below the panel header
- Multi-panel: panels accessible via a "Panels" tab at bottom of screen (tap to switch active panel)
- Sync still works — synced panels update in background, notification dot on Panels tab when synced panel has a new highlight

---

## 14. Keyboard Shortcuts (Desktop)

| Key | Action |
|-----|--------|
| `←` / `→` | Previous / Next page in active panel |
| `↑` / `↓` | Previous / Next extracted item |
| `C` | Confirm active item |
| `F` | Flag active item |
| `E` | Exclude active item |
| `O` | Override active item (opens input) |
| `Esc` | Close Item Detail Panel |
| `Ctrl+P` | New panel |
| `Ctrl+W` | Close active panel |
| `Ctrl+S` | Sync active panel with another (shows pair picker) |
| `Z` / `+` / `-` | Zoom controls |
| `0` | Fit to width |

---

## 15. Data Model

```python
@dataclass
class ATVAnnotation:
    """Single annotation on a document"""
    id: str
    project_id: str
    document_id: str
    document_type: str          # drawing | spec | schedule | addendum | quote
    page_number: int
    
    # Spatial data
    annotation_type: str        # zone | pin | row_highlight | text_highlight
    bounding_box: dict          # {x, y, w, h} normalized 0-1 relative to page
    polygon_points: list        # For zone overlays — list of {x,y} points
    
    # Linked item
    extracted_item_id: str
    item_label: str
    item_values: dict
    
    # Status
    confidence_score: float
    confidence_tier: str        # HIGH | MEDIUM | LOW
    source_tier: str            # SOURCE-DERIVED | CROSS-REFERENCE | HEURISTIC
    status: str                 # unreviewed | confirmed | flagged | conflict | excluded
    trade: str                  # hvac | plumbing | controls | fire | electrical | arch | structural
    
    # Conflicts
    conflicts: list[ConflictRecord]
    
    # Estimator decision
    estimator_decision: str | None
    estimator_note: str | None
    decided_by: str | None
    decided_at: datetime | None


@dataclass
class ConflictRecord:
    document_id_a: str
    document_id_b: str
    value_a: str
    value_b: str
    ai_resolution: str
    resolution_source: str      # document_a | document_b | addendum | manual


@dataclass
class ATVPanel:
    """State of one open panel"""
    panel_id: str
    document_id: str
    page_number: int
    view_mode: str              # overlay | side-by-side
    granularity: str            # zones | items | both
    trade_filter: str
    zoom_level: float
    scroll_position: dict       # {x, y}
    synced_with: str | None
```

---

## 16. API Routes

```
GET  /projects/{id}/atv/documents                              — list all documents
GET  /projects/{id}/atv/documents/{doc_id}/pages               — page list + annotation counts
GET  /projects/{id}/atv/documents/{doc_id}/page/{n}/annotations — all annotations on page
GET  /projects/{id}/atv/items/{item_id}                        — full item detail
POST /projects/{id}/atv/items/{item_id}/decide                 — estimator decision
GET  /projects/{id}/atv/conflicts                              — all unresolved conflicts
POST /projects/{id}/atv/conflicts/{id}/resolve                 — resolve conflict

# Panel state
GET  /projects/{id}/atv/panels                    — list open panels
POST /projects/{id}/atv/panels                    — open new panel
PUT  /projects/{id}/atv/panels/{panel_id}         — update panel state
DELETE /projects/{id}/atv/panels/{panel_id}       — close panel
POST /projects/{id}/atv/panels/{id}/sync          — sync two panels
```

---

## 17. Engine 1 Output Requirements

For the ATV to work, Engine 1 must output bounding box coordinates for every extracted item.

**Engine 1 must produce per item:**
```python
{
  "item_id": "fcu-101",
  "document_id": "m-201-hvac-floor-plan",
  "page": 3,
  "bounding_box": {"x": 0.42, "y": 0.31, "w": 0.08, "h": 0.06},  # normalized 0-1
  "zone_polygon": [...],
  "extracted_values": {...},
  "confidence": 0.82,
  "source_tier": "SOURCE-DERIVED",
  "cross_references": [...],
  "conflicts": [...]
}
```

If Engine 1 cannot produce coordinates (e.g., spec text extraction without position data), the ATV falls back to **section-level** highlighting.

---

## 18. Build Phases

### Phase 1 — Core Viewer (MVP)
- Single panel, overlay mode only
- Zone overlays on drawings (color-coded by status)
- Item Detail Panel (click zone or pin → see full item detail)
- Basic trade filter
- Integration with Screen 2 ("View Source →" button)
- 25+ unit tests on data model + API routes
- **Blocked by:** Engine 1 bounding box output (Q1 below)

### Phase 2 — Multi-Panel + Sync
- Multi-panel workspace (up to 4 panels simultaneously)
- Panel sync system (bi-directional, anchor model)
- Item pins with confidence badges
- Spec section + schedule row highlighting
- 20+ additional tests

### Phase 3 — Conflict Resolution + Full Integration
- Conflict overlay and resolution flow
- Addendum diff view
- Full keyboard shortcuts
- Mobile responsive (single panel, bottom sheet)
- Deep links from all 4 review screens into ATV
- 15+ additional tests

---

## 19. Open Questions

| # | Question | Impact |
|---|----------|--------|
| Q1 | Does Engine 1 currently output bounding box coordinates? If not, Phase 1 cannot start until Engine 1 is updated. | **Blocking** |
| Q2 | PDF rendering: PDF.js (browser-native) or server-side rasterize to images? PDF.js = better UX, heavier bundle. Images = simpler, less accurate zoom. | Architecture |
| Q3 | Annotations stored per-user or per-project? Can two estimators annotate the same drawing independently? | Data model |
| Q4 | Zone polygons: auto-generated by Engine 1 or manually drawn by the estimator in-browser? | Phase 1 scope |

---

## 20. Success Criteria

**Phase 1 ships when:**
- Estimator can open any project drawing and see color-coded zone overlays
- Click any zone → see all extracted items with confidence scores
- Confirm or flag any item from the viewport
- Decision syncs to Screen 2 immediately
- 25/25 tests pass

**The product is complete when:**
An estimator can open the MacDill AFB project, pull up M-201, see every FCU and AHU annotated with extracted quantities and confidence levels, click FCU-101, see the addendum conflict flagged, accept the AI's resolution, and have that decision flow through to the bid recap — without leaving the drawing.

---

*Spec v1.0 — Ready for adversarial review.*
