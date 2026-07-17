# BUILDTRONIX GC PRE-CON SPEC — Session Addendum
## June 16, 2026 — Architecture Decisions

**Applies to:** BUILDTRONIX-GC-PRECON-SPEC-v1.2.md + AI-TAKEOFF-SPEC-v1-2026-05-27.md
**Status:** Locked decisions, to be merged into v1.3

---

## A1. Proposal Package — Two Modes (Sub and GC)

**Sub Proposal (NewCo/specialty sub → GC):**
1. Cover
2. Introduction / Letter of Transmittal
3. Understanding of Project
4. Scope of Work (own trades only)
5. Schedule / Duration — auto-populated from man-hours in cost recap module. No manual entry.
6. Qualifications / Clarifications / Exceptions
7. Exclusions
8. Bid Summary
9. Closing

Appendix: A — Key Personnel | B — Project Experience | C — Safety/EMR | D — Insurance & Licenses | E — Long-Lead Equipment Cut Sheets

**GC Proposal (GC → Owner/Architect):**
1. Cover
2. Executive Summary
3. Understanding of Project & Owner Goals
4. Project Team / Org Chart
5. Scope of Work (all trades)
6. Schedule (CPM summary)
7. Qualifications / Clarifications / Exceptions
8. Bid Leveling Summary
9. Value Engineering Opportunities
10. Bid Summary + Alternates
11. Closing

Appendix: A — Company Qualifications & Bonding | B — Safety/EMR/OSHA Recordables | C — Project Experience (photos) | D — References | E — Insurance | F — Subcontractor List | G — Long-Lead Equipment Log

**Company Profile** (feeds both templates automatically):
- EMR rating
- OSHA recordable rate
- Safety program name/description
- Bond capacity (GC mode)
- License numbers by state
- Insurance limits and carrier

**Rule:** Duration in Section 5 auto-populates from estimated man-hours. Formula: labor hours by trade ÷ crew size = duration in weeks. Man-hours module already exists — proposal generator reads it directly.

---

## A2. Scope Interpretation Analysis (Quals Generator)

When cross-set reconciliation identifies items in arch set not on MEP drawings, estimator makes one of three decisions:

- **INCLUDE** → item goes into cost recap at correct cost code
- **EXCLUDE** → item listed as "By Others" in clarification section
- **CLARIFY** → item listed as "included per arch documents only, coordinate with GC for final resolution"

**Language rules (enforced in all generated output):**
- NEVER use "bidders" or competitive comparison language
- NEVER say "other contractors may have missed this"
- USE: "subject to interpretation across contract documents"
- USE: "may be priced inconsistently without clarification"
- USE: "scope interpretation analysis"
- USE: "we recommend the following clarification be issued to ensure consistent interpretation"

**Positioning:** Company is the professional who read the full set and is helping the GC make better decisions. Expert, not commentator.

**Output document:** "Scope Interpretation Analysis" on company letterhead.
Sent as part of bid package or as pre-bid clarification request.
Helps GC evaluate all sub proposals on consistent basis.

---

## A3. Document Inventory First — Drawing Reading Sequence

The engine does NOT jump directly to scope extraction. Full sequence:

**Step 1 — Full set inventory**
- Read ALL title pages across ALL drawing sets (arch, MEP, civil, structural)
- Build master drawing index: every sheet, every discipline, every revision
- Identify how many distinct drawing sets exist (typically 2-3 for complex buildings)

**Step 2 — Standards resolution**
- Symbol legend (M-001 or arch general notes) — decoded before any plan is read
- Abbreviations list — project-specific vs. standard CSI
- General notes — NIC, BIC, By Owner, By Others callouts define scope ownership
- Drawing index cross-references — M-101 references M-201, etc.
- Equipment schedules location — identified across all sets

**Step 3 — Arch set first, by area/zone**
- Read architectural for MEP scope buried in arch details
- Flag every room/zone with MEP implications
- Reflected ceiling plans checked for MEP-affecting items

**Step 4 — MEP sets by discipline, by area**
- Read mechanical → extract scope
- Cross-check: does arch plan show anything M-sheets missed?
- Read plumbing → extract scope, check boundary with mechanical
- Read electrical → extract scope for power, controls, disconnects

**Step 5 — Cross-set reconciliation**
- Items in arch but not on M/P/E → FLAG for include/exclude/clarify
- Items on M but not in spec → FLAG
- Schedule conflicts across sets → FLAG
- Equipment counts vs. penetrations vs. drain counts → reconcile

**Critical rule:** GCs expect specialty subs to catch scope in the arch set even when it doesn't appear on the MEP drawings. "It wasn't on the mechanical drawings" is not a defense. The quals generator is the mechanism for handling caught items professionally.

---

## A4. Past Projects Intake System

**Directory structure:**
```
/past-projects/
  {job-number}_{project-name}/
    drawings/
      arch/
      mechanical/
      plumbing/
      electrical/
      civil/
      structural/
      specs/
      addenda/
    estimate/
      {job-number}_estimate.xlsx
      {job-number}_recap.xlsx
    award/
      awarded.json       {won: bool, value: float, awarded_to: str}
    metadata.json
```

**metadata.json fields:**
```json
{
  "job_number": "AMS-2026-001",
  "project_name": "Macdill AFB B53 HVAC Renovation",
  "gc": "Trias Construction",
  "owner": "US Air Force",
  "location": "Tampa, FL",
  "building_type": "government/military",
  "sqft": 48000,
  "bid_date": "2026-07-15",
  "award_date": null,
  "won": null,
  "final_value": null
}
```

**Intake automation:**
- A-0 watcher monitors `/past-projects/` directory
- No per-file manual entry — metadata.json is the only manual input per job
- All drawing sets ingested by discipline automatically
- Estimate file = ground truth labels for AI training
- Delta between AI extraction output and actual estimate = correction rule

**Training flywheel:**
- 5 projects: baseline calibration
- 20-30 projects: trade-type patterns solidify
- 50+ projects: building-type intelligence (hospital = medical gas always present, military = BIC on some trades)
- Ongoing: every corrected estimate improves future extractions

**Joe Trias's project library** trains the GC-side (arch takeoff, wall types, ceilings, concrete, site work).
**NewCo's project library** trains the Sub-side (MEP scope, equipment schedules, TAB/controls).
Data from both modes improves both engines. Network effect.

---

## A5. GC Internal Estimate (Clarification — Already in Spec)

**Confirmed June 16:** GC internal estimate is already part of the sub leveling grid. Not a new feature.

**Clarification added:** The internal estimate's unit cost database has two calibration layers:
1. RSMeans — industry baseline (starting point)
2. Historical closed project data — local market calibration (more accurate over time)

As past projects directory grows, unit costs for the GC's market get more accurate. Automatic — no manual input required beyond closed project recap files.

**Variance flagging** is already in the leveling grid spec.

---

## A6. Roofing Added to Full Takeoff Division List

**Division 07 — Thermal and Moisture Protection**

Primary quantities:
- Roof area (SF) by system type: TPO, EPDM, PVC, BUR, Modified Bitumen, Metal Standing Seam, SPF, Green Roof
- Roof insulation (SF + R-value/thickness)
- Crickets and saddles (SF)
- Parapets (LF + height)

Edge/perimeter: Edge metal, gravel stop/fascia, coping, counter-flashing (all LF)

Penetrations: Roof curbs EA (by size — HVAC units, fans, skylights), pipe penetrations EA, roof drains EA, roof hatches EA, expansion joints LF

Accessories: Walkway pads SF, roof anchor points EA, lightning protection LF

**Cross-trade reconciliation checks:**
- HVAC unit on mechanical schedule but no roof curb on arch roof plan → FLAG
- Roof drain on arch plan but not on plumbing riser diagram → FLAG
- Curb size on roof plan vs. unit size on mechanical schedule → sizes must match
- Number of equipment penetrations on roof plan vs. mechanical unit count → must reconcile

---

## A7. Bluebeam — Interim Bridge Only

Bluebeam used as interim scope intake bridge ONLY until Phase 3 drawing AI engine is built.

Markup type conventions: Highlight=include, Callout=clarify, Cloud=conflict, Stamp=excluded.
Export Markup Summary CSV → intake engine reads it → populates cost recap + quals generator.

**Bluebeam limitations:** No scope intelligence, no cost code mapping, no quals generation, no coverage analysis, no cross-set reconciliation, no learning. It is a PDF viewer only.

When Phase 3 is ready: Bluebeam becomes optional review layer. AI reads drawings directly.

---

## A8. GC vs. Sub Mode — Confirmed as Core Architecture (Already in Spec)

| Component | GC Mode | Sub Mode |
|---|---|---|
| Scope filter | All 35 divisions | Assigned trades only |
| Output format | Joe's CSI template (9 vendor slots) | NewCo cost codes (100/200/300/500) |
| Takeoff scope | Full (walls, floors, MEP, site, roofing, concrete) | MEP only |
| Proposal format | GC proposal to Owner | Specialty sub proposal to GC |
| Default company | Trias Construction | NewCo |

Network effect: Sub data trains MEP extraction. GC data trains architectural takeoff. Both improve both.

---

*Addendum locked: June 16, 2026*
*To be merged into BUILDTRONIX-GC-PRECON-SPEC-v1.3.md*
