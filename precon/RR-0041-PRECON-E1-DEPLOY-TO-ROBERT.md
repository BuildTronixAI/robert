# RR-0041 — Pre-Con Engine Package: Deploy to Robert

**Filed:** 2026-06-18 21:22 UTC  
**Filed by:** BOB (Chief of Staff)  
**Status:** PENDING CHRIS APPROVAL  

---

## 1. Summary

Deploy the Pre-Con engine package from BOB's workspace (OpenClaw) to Robert's workspace (TronixMesh/LangGraph runtime). This moves all customer-facing Pre-Con code out of OpenClaw and into Robert's environment. Nothing customer-facing runs through OpenClaw.

---

## 2. Claim

After this deploy, the Pre-Con pipeline runs inside Robert. The Trias pilot (Joe) has zero dependency on OpenClaw or BOB's session.

---

## 3. Files Being Deployed

**Core engines — 312/312 tests passing (verified June 17, 2026)**
- precon/engine1/ — Scope Extraction
- precon/a0/ — File Ingestion
- precon/engine0/ — Taxonomy Translation
- precon/engine2/, engine2a/, engine2b/ — Coverage
- precon/a10/ — Estimate Alignment Gate
- precon/proposal/ — Proposal Generator
- precon/execution_spine/ — Gate Engine
- precon/bid_confidence/ — Bid Confidence
- precon/bid_tab/ — Bid Tabulation
- precon/documents/ — Document Store
- precon/plan_distribution/ — Plan Distribution
- precon/api/ — FastAPI backend (20 routes)

**Calibration harness**
- precon/e1_calibration/harness_v2.py
- precon/e1_calibration/README.md
- precon/e1_calibration/ground_truth.csv (template)

**NOT deploying:** precon/ui/ (Vercel), seed scripts, reference data, BOB workspace files

---

## 4. Deploy Path — Decision Required

The staged deploy pipeline (RR-0042) does not exist yet.

**Option A** — Build pipeline first (RR-0042), then deploy. Correct order. Pilot may slip past June 20.

**Option B** — Manual SSH deploy for pilot only. File RR-0042 separately for production pipeline. Gets Joe running by June 20.

**BOB recommendation:** Option B for pilot, Option A for production.

---

## 5. Known Gaps

- E1 tested on 1 real document only (need 5-10 from Joe)
- Calibration thresholds not yet set (need labeled dataset)
- Robert's environment not yet verified (Python version, pdfplumber)
- Deploy pipeline does not yet exist

---

## 6. BOB Confidence: MEDIUM

Code solid and tested. Uncertainty: deploy path and E1 real-document performance.

---

## 7. Chris Decision Required

1. Option A or Option B for deploy path?
2. Smoke test E1 against Clearwater Airport PDF post-deploy?
3. Verify Robert environment dependencies first?

---

## Review Status

- [x] Filed — 2026-06-18 21:22 UTC
- [ ] Chris decision on deploy path
- [ ] Final approval

*RR-Before-Deploy Rule (RR-0040) — no deployment without this RR approved.*
