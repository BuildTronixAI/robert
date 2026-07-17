# Pre-Con Spec Suite — Change Requests CR-018 through CR-024
**Architectural Hardening — Pre-Build Checklist**
**Filed:** June 18, 2026
**Filed by:** BOB (Chief of Staff) following three-pass peer review convergence
**Status:** OPEN — Requires resolution before Trias pilot build begins
**Source:** v2.0 spec suite review (external reviewer + synthesis + BOB independent pass)
**Convergence note:** CR-018 through CR-023 independently identified by two reviewers. Convergence at P0/HIGH = confirmed architectural defects, not opinions.

---

## CR-018 — Dual Vendor Authority (Bid Tab vs Sub-Leveling)
**Severity:** CRITICAL (P0)

**Finding:**
Bid Tabulation Engine and Sub-Leveling Engine both perform vendor comparison, selection, and award determination. No authoritative source defined. Divergent awards can exist simultaneously with no reconciliation. Decision corruption is worse than number corruption.

**Resolution — Option C (Successor Model):**
```
Bid Tab → Award Engine → Sub-Leveling Projection → Cost Recap
```
- Bid Tab = single authoritative vendor-award engine
- Sub-Leveling = read-only compatibility projection only
- Sub-Leveling as input/write surface is deprecated organically (no forced migration)
- Bid Tab award event triggers Sub-Leveling projection update (append-only, timestamped, versioned)

**Pre-build gate:** Architecture documented in Chapter 0 before any Bid Tab or Sub-Leveling code is written.

---

## CR-019 — line_subtotal Derived-State Enforcement
**Severity:** CRITICAL (P0)

**Finding:**
`line_subtotal` is the aggregation spine for CSI recap, fee calculations, proposal generation, balance checks, and submission snapshots. Current spec permits nullable, application-written values. Silent under-reporting possible with no error.

**Resolution:**
```sql
line_subtotal NUMERIC(15,2) GENERATED ALWAYS AS (
  extended_labor + pti_burden + extended_material + sales_tax + extended_sub
) STORED NOT NULL
```
- Application writes prohibited by database engine
- NULL prohibited
- Expression changes require schema migration, not app patch
- No manual override permitted

**Pre-build gate:** DDL compiles and passes integration tests before recap or fee-stack code is written.

---

## CR-020 — Bid State Machine Contradiction (LOCKED vs REVISED)
**Severity:** CRITICAL (P0)

**Finding:**
LOCKED defined as terminal. RBAC permits "Revise locked bid." Mutually exclusive. Unresolved = undefined behavior at submission.

**Resolution — Supersession Model:**
```
DRAFT → PENDING_APPROVAL → APPROVED → SUBMITTED → LOCKED
                                                      ↓
                                               REVISED (new version, supersedes_bid_id set)
```
- LOCKED records permanently immutable
- Revision = new record with `supersedes_bid_id` pointing to locked original
- `bid_version` incremented on each supersession
- REVISED is a state on the new record, not the locked one

**Pre-build gate:** State machine redrawn before submission/lock/revision code is written.

---

## CR-021 — Tenant Identity Fragmentation
**Severity:** CRITICAL (P0)

**Finding:**
`org_id` used in Opportunity Engine. `company_id` used in Pre-Con. Schema has UUID/TEXT type inconsistencies. OPP-06 promotion path (Opportunity → Project) undefined. RLS on UUID/TEXT mismatches silently fails.

**Resolution:**
- `company_id UUID` everywhere, platform-wide
- All `org_id` references renamed to `company_id`
- All TEXT FK usages converted to UUID
- OPP-06: `opportunities.company_id` maps 1:1 to `gc_projects.company_id`
- All RLS policies reference `company_id UUID`

**Pre-build gate:** Schema DDL passes type-consistency check before any cross-module join or RLS policy deploys.

---

## CR-022 — Opportunity Score Reproducibility
**Severity:** HIGH (P1)

**Finding:**
Scores stored as bare integers. No algorithm version preserved. Historical scores non-reproducible when scoring rules change. Same class of problem already solved elsewhere in the platform via snapshots and versioning — not yet applied to scoring.

**Resolution — Add to score storage:**
```sql
score_algorithm_version  TEXT NOT NULL,
score_inputs_json        JSONB NOT NULL,
score_breakdown          JSONB NOT NULL,
scored_at                TIMESTAMPTZ NOT NULL DEFAULT now()
```

**Re-score policy (explicit):**
- Open opportunities: MAY re-score; original score preserved as prior event
- Closed (WON/LOST/NO-BID): SHALL NEVER re-score; score is frozen

**Pre-build gate:** Score schema includes versioning before scoring logic touches the database.

---

## CR-023 — Balance Check Arithmetic Determinism
**Severity:** CRITICAL (P0) — elevated from HIGH

**Elevation rationale:** Authoritative gates require deterministic arithmetic. $0.01 hard block on non-deterministic floating-point accumulation = operational deadlock. Valid bids fail submission. Worse than a calculation error.

**Finding:**
SS-06-03 blocks submission at variance > $0.01. Arithmetic mixes GENERATED and app-written NUMERIC across hundreds of lines. Deterministic reconciliation not guaranteed.

**Resolution — Integer Cents:**
- Every line item rounded to 2 decimal places at write time via GENERATED expressions
- Balance checks operate on integer cents: `ABS(recap_cents - formula_cents) > 1` = block
- Division totals = SUM of rounded line subtotals (no re-rounding at division level)
- Rounding policy stated explicitly in Formula Contract section

**Pre-build gate:** Rounding policy in Formula Contract before any arithmetic test is written.

---

## CR-024 — Test Integrity: Vendor Cap False Pass
**Severity:** MEDIUM (P2)

**Finding:**
SS-05-01 claims to verify a hard 20-vendor-per-division limit. No schema constraint enforces this. A test claiming a hard limit passes against a schema with no enforcement is a false test. False passing tests are worse than no tests.

**Resolution — Option B (Soft Warning, recommended):**
- Remove SS-05-01 as written
- Replace with UI-layer advisory: "21+ vendors on one trade — confirm?"
- Advisory only, not a hard block
- The data-quality signal is valuable; the arbitrary ceiling is not

**Pre-build gate:** SS-05-01 rewritten or removed before test matrix is treated as authoritative.

---

## Summary Table

| CR | Finding | Severity | Status |
|----|---------|----------|--------|
| CR-018 | Dual Vendor Authority | CRITICAL | OPEN |
| CR-019 | line_subtotal GENERATED enforcement | CRITICAL | OPEN |
| CR-020 | LOCKED vs REVISED contradiction | CRITICAL | OPEN |
| CR-021 | Tenant identity fragmentation | CRITICAL | OPEN |
| CR-022 | Opportunity score reproducibility | HIGH | OPEN |
| CR-023 | Balance check arithmetic determinism | CRITICAL | OPEN |
| CR-024 | Vendor cap false test | MEDIUM | OPEN |

**5 CRITICAL · 1 HIGH · 1 MEDIUM**
**All must be resolved before first line of Trias pilot code.**

---

## Build Order

1. **CR-018** — Document Bid Tab → Sub-Leveling architecture in Chapter 0
2. **CR-019 + CR-023** — Coupled. GENERATED line_subtotal + rounding policy. Test together.
3. **CR-020** — Redraw state machine. Supersession model.
4. **CR-021** — Unify tenant ID. UUID everywhere. Fix RLS.
5. **CR-022** — Score versioning schema + re-score policy.
6. **CR-024** — Rewrite or remove SS-05-01.

---

## What Closing These Unlocks

After CR-018–024 closed, future reviews surface only:
UX friction · workflow edge cases · pilot tuning · performance optimization

No further architecture-level defects expected.
Platform transitions from **design risk** → **execution risk**.
That's where Trias pilot needs it.

---
*BOB · Three-pass peer review convergence · June 18, 2026*
*Next: Chris approves → BOB begins CR-018 architecture resolution*
