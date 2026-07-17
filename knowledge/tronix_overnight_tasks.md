# Robert Overnight Task Queue — May 28, 2026

## Context

## Task Queue (Priority Order)

### Task 1: LienTronix Content — "Cost of Doing Nothing" Case Studies
Write 3 additional real-world case study vignettes for the LienTronix site based on Florida Chapter 713 lien law. Each should be:
- 2-3 sentences
- Real dollar amounts
- Specific failure point (missed NTO, missed 90-day window, missed Notice of Contest deadline)
- Written in plain contractor language (not legal)
Format: JSON array with fields: icon, risk, cost, detail

The first cold outreach email to mechanical contractors is already written. Write Emails 2-5 in the sequence:
- Email 2 (Day 3): Specific Florida SAM.gov opportunity highlight — real agency, real dollar range, real NAICS code
- Email 3 (Day 7): Social proof angle — small shop won federal contract story
- Email 4 (Day 14): SDVOSB/veteran angle — set-aside education
- Email 5 (Day 21): Final close — ROI framing, urgency, Scout $29/mo CTA
Each email: subject line, preview text, body (150-200 words), CTA

### Task 3: PermitTronix — "Project Start Acceleration" Positioning Copy
Write hero section copy for PermitTronix repositioned as "project start acceleration infrastructure" not "permit management":
- New headline (max 8 words)
- New subheadline (max 20 words)
- 3 benefit bullets (contractor language)
- One-line guarantee statement

### Task 4: Tronix Bundle — Landing Page Copy
- Hero: "One platform. Every compliance layer." (or better)
- 3 product summaries (1 sentence each)
- Feature comparison: Bundle vs. individual products
- Pricing section: $1,499/mo annual, what's included
- ROI calculator copy: "Protect $X in receivables for $Y/mo"
- CTA: "Talk to us" → contact form (no self-serve, this is enterprise)

### Task 5: Competitive Battle Cards
Write 3 competitive battle cards (one per main competitor):
- vs. Levelset (lien management)
- vs. PermitFlow (permit tracking)
- vs. doing nothing (strongest competitor)
Format each: Their pitch, our counter, proof point, close line

## Output Format
For each task: save output to /var/lib/robert/workspace/output/tronix_[task_name].md
Send completion notification to BOB via: write to /var/lib/robert/workspace/output/COMPLETED.md

---

## TASK: Build NIA (News Intelligence Agent) — Phase 1
*Added: 2026-05-28 23:58 UTC*
*Priority: HIGH*

Build the News Intelligence Agent as a Robert chassis node. Full spec at:
/var/lib/openclaw/.openclaw/workspace/specs/NIA-ROBERT-BUILD-TASK-v1-2026-05-28.md
/var/lib/openclaw/.openclaw/workspace/specs/NEWS-INTELLIGENCE-AGENT-SPEC-v1-2026-05-28.md

Deliverables:
1. /var/lib/robert/workspace/nodes/nia.py
2. Supabase table: nia_articles (create via service role key)
3. /var/lib/robert/workspace/outputs/nia_daily_brief.json (generated on first run)
4. Update morning brief integration notes

Constraints: NO simulation. Real RSS only. Deterministic scoring. Log failures, don't fake data.
