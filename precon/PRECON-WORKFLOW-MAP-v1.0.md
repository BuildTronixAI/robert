# Pre-Con Workflow Map v1.0
# Joe Trias Whiteboard → Buildtronix Module Mapping
# June 17, 2026

---

## Joe's 18-Step Workflow (Source of Truth)

| # | Step | GC Mode (Trias) | Sub Mode (NewCo) | Status |
|---|------|-----------------|------------------|--------|
| 1 | **Go / No Go** | Bid scoring: Wheelhouse, Location, Size, Timing, Customer Rel, Competition | Same — score the GC ITB | ✅ Built (Bid Confidence Calculator) |
| 2 | **Set up job folder in server** | Create project record, assign project number | Create project record | ✅ Built (precon_projects table) |
| 3 | **Set up Outlook folder** | Auto-create email folder + project inbox | Same | ❌ Gap — M365/Outlook integration |
| 4 | **Initial scope review** | Upload drawings, AI extracts scope | Upload drawings/specs, AI extracts scope | ✅ Built (A-0 ingest + Engine 1) |
| 5 | **Set up SharePoint link** | Link project SharePoint folder | Link GC's project SharePoint (if shared) | ❌ Gap — SharePoint integration |
| 6 | **Select initial vendors** | Browse vendor registry by CSI/trade, select ITB list | Browse supplier/material vendor list, select for quoting | ✅ Built (vendor registry + tier filters) |
| 7 | **Email ITB** | Bulk email ITB to selected subs with drawings + scope | N/A (Sub receives ITB, doesn't send) | ❌ Gap — ITB email engine (bulk send + tracking) |
| 8 | **Summary sheet (internal take-offs)** | Internal cost recap — own labor/material estimate | Own takeoff — labor, material, equipment by CSI | ✅ Built (Screen 3 recap) |
| 9 | **Fine scope review** | Review AI extraction, confirm/correct items | Review scope from GC drawings | ✅ Built (Screen 1 + Screen 2) |
| 10 | **Fine vendor selections** | Narrow ITB list after scope review | Narrow supplier list after scope review | ✅ Built (vendor registry + preferred tier) |
| 11 | **Set up PlanHub** | Upload to PlanHub for plan distribution | Access GC's PlanHub | ❌ Gap — PlanHub integration (or replace it) |
| 12 | **Follow-up emails** | Automated follow-up to non-responding subs | N/A | ❌ Gap — follow-up automation |
| 13 | **Respond to questions** | RFI inbox from subs, route to estimator | Send RFIs to GC, track responses | ❌ Gap — Pre-Con RFI thread |
| 14 | **Addendum notifications** | AI detects addendum, notifies all ITB recipients | AI detects addendum from GC, alerts team | ❌ Gap — Addendum engine + notification |
| 15 | **Reminders** | Auto-reminder to subs approaching bid deadline | Auto-reminder to self on bid due date | ❌ Gap — deadline tracking + reminders |
| 16 | **Receive quotes** | Sub quote intake (email parse + manual entry) | Supplier quote intake (same) | ✅ Built (quote_intake engine) |
| 17 | **Tabulate quotes** | Side-by-side by trade/CSI → lowest/best/preferred | Side-by-side by product/service/supplier | ❌ Gap — Quote Tabulation Engine (partial) |
| 18 | **Select from tabulated → Finalize bid** | Select winning sub per trade, lock bid | Select winning supplier per item, submit to GC | ❌ Gap — Quote Selection + Bid Lock |

---

## Quote Tabulation Engine (The Critical Gap)

This is the core of steps 17-18 and must handle **both modes**:

### GC Mode — Sub Quote Tabulation
```
Input:  Received quotes from subs, organized by CSI division
Output: Side-by-side comparison table by trade

Columns: Sub Company | Contact | Quote Amount | Scope Inclusions | Scope Exclusions | 
         Preferred? | Notes | Award Recommendation

Views:
- By Trade/CSI Division
- By Bid Package  
- By Dollar Value (low to high)
- Preferred Sub highlighted

Actions:
- Select winning sub per trade
- Mark as "Award" or "Backup"
- Add leveling notes
- Export to bid recap
```

### Sub Mode — Supplier/Material Quote Tabulation
```
Input:  Received quotes from suppliers/vendors, organized by product/service/material
Output: Side-by-side comparison by line item

Columns: Supplier | Product/Service | Unit Price | Qty | Total | Lead Time |
         Delivery Terms | Notes | Award Recommendation

Views:
- By product/material category
- By CSI cost code
- By vendor
- By project phase

Actions:
- Select winning supplier per item
- Calculate total material cost
- Feed into cost recap (Screen 3)
- Export to proposal
```

---

## Gap Analysis — What Needs to Be Built

### P0 — Critical for Trias Delivery

| Module | Description | Effort |
|--------|-------------|--------|
| **ITB Email Engine** | Bulk send ITB to selected vendors with drawings, scope, due date. Track opens/responses. | 4-6 hrs |
| **Quote Tabulation Engine** | Side-by-side comparison for GC (by trade) and Sub (by product/service). Select winners. | 6-8 hrs |
| **Quote Selection + Bid Lock** | Lock selected quotes into bid recap. Calculate final number. One-click finalize. | 2-3 hrs |
| **Addendum Engine** | Detect document hash changes = addendum. Notify all ITB recipients automatically. | 3-4 hrs |

### P1 — High Value, Build Next

| Module | Description | Effort |
|--------|-------------|--------|
| **Follow-up Automation** | Scheduled reminders to non-responding vendors. Configurable cadence. | 2-3 hrs |
| **Pre-Con RFI Thread** | Question/answer thread tied to project. GC mode: from subs. Sub mode: to GC. | 3-4 hrs |
| **Deadline Tracker** | Bid due dates, reminder schedule, countdown. Alert estimator + PMs. | 2 hrs |

### P2 — Integrations

| Module | Description | Effort |
|--------|-------------|--------|
| **PlanHub Integration** | Upload drawings to PlanHub OR replace PlanHub with native plan distribution | 4-6 hrs |
| **M365/Outlook Integration** | Auto-create Outlook folder per project, sync email threads | 4-6 hrs |
| **SharePoint Integration** | Link and sync project folder | 3-4 hrs |

---

## What's Already Built (Keep, Wire In)

| Module | Status |
|--------|--------|
| A-0 File Ingestion | ✅ 15/15 tests |
| Engine 0 Taxonomy (198 cost codes) | ✅ 10/10 tests |
| Engine 1 Scope Extraction | ✅ 31/31 tests |
| Engine 2A/2B Coverage | ✅ 51/51 tests |
| Screen 1 Interpretation Review | ✅ Live UI |
| Screen 2 Takeoff Review | ✅ Live UI |
| Screen 2.5 Coverage Review | ✅ Live UI |
| Screen 3 Recap | ✅ Live UI |
| A-10 Alignment Gate | ✅ 15/15 tests |
| Proposal Generator | ✅ 24/24 tests |
| Bid Confidence Calculator | ✅ 32/32 tests |
| Vendor Registry (7,215 Trias contacts) | ✅ Live in Supabase |
| Quote Intake Engine | ✅ Built |
| FastAPI Backend (20 routes) | ✅ Live |
| Next.js UI | ✅ Live at buildtronix-precon.vercel.app |

---

## Recommended Build Order for Trias Delivery

1. Quote Tabulation Engine (P0 — core of their workflow)
2. ITB Email Engine (P0 — they can't send invites without this)
3. Addendum Engine (P0 — critical for GC bidding)
4. Quote Selection + Bid Lock (P0 — finalizes bid)
5. Follow-up Automation (P1)
6. Pre-Con RFI Thread (P1)
7. Deadline Tracker (P1)
8. Integrations (P2 — PlanHub, M365, SharePoint)

---

## New Vendor to Add (from whiteboard)
- **GFL Dumpsters** — Jared McGhee — 813-734-3246 — jmcghee@gflenv.com
- CSI: site services / temporary facilities
- Add to Trias ACTIVE vendor list

---

*Source: Joe Trias whiteboard, June 17 2026*
*Mapped by BOB — buildtronix-precon Pre-Con module*
