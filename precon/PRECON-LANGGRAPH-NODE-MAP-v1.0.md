# Pre-Con Pipeline — LangGraph Node Architecture v1.0
# BuildTronix | TronixMesh Runtime
# Filed: 2026-06-18

---

## Architecture Overview

The Pre-Con pipeline runs as a LangGraph StateGraph inside Robert.
Each engine is a node. Gates are interrupt points. Joe's corrections
are human-in-the-loop events native to LangGraph.

TronixMesh governs:
- Agent identity and authority
- Cross-agent coordination
- Doctrine enforcement
- Event ledger writes

LangGraph executes:
- Node sequencing
- State persistence across sessions
- Human interrupt handling
- Checkpointing (resume from last good state on failure)

---

## State Schema

```python
class PreConState(TypedDict):
    # Project identity
    project_id:        str
    company_id:        str
    bid_id:            str

    # Document tracking
    documents:         list[DocumentRecord]
    current_doc_id:    Optional[str]

    # Classification results
    doc_type:          Optional[str]          # SPEC | DRAWINGS | ADDENDUM | SCHEDULE | UNKNOWN
    doc_confidence:    Optional[float]
    doc_reason_codes:  list[str]

    # Extraction results
    scope_items:       list[ScopeItem]        # E1 output
    coverage_gaps:     list[CoverageGap]      # E2 output
    estimate_lines:    list[EstimateLine]     # A10 output
    bid_confidence:    Optional[float]        # Bid Confidence output

    # Human review queues
    pending_classification_review: list[str]  # doc_ids awaiting Joe's type confirmation
    pending_scope_review:          list[str]  # scope_item_ids awaiting Joe's review
    pending_coverage_review:       list[str]  # gap_ids awaiting Joe's review

    # Proposal
    proposal_draft:    Optional[ProposalDraft]
    proposal_approved: bool

    # Audit
    event_log:         list[EventRecord]
    corrections_log:   list[CorrectionRecord]  # shadow-mode capture
```

---

## Node Map

```
START
  │
  ▼
[N-01] INGEST
  │  A-0: receive document, extract text, SHA256, page count
  │  Output: document record in state
  │
  ▼
[N-02] CLASSIFY
  │  Harness v2: multi-axis scoring (SPEC/ADDENDUM/SCHEDULE/DRAWING)
  │  Output: doc_type + confidence + reason_codes
  │
  ├─── confidence >= threshold AND margin clean ──► [N-03] EXTRACT
  │
  └─── uncertain OR UNKNOWN ──────────────────────► [H-01] HUMAN: CLASSIFY
                                                         │
                                                         │ Joe confirms doc type
                                                         ▼
                                                    [N-03] EXTRACT

[N-03] EXTRACT
  │  E1: heuristic pass + LLM pass on ambiguous segments
  │  Output: scope_items with confidence tiers + bounding boxes
  │
  ├─── scope_items > 0 ────────────────────────────► [N-04] COVERAGE
  │
  └─── scope_items == 0 AND doc is confirmed SPEC ─► EXTRACTION_FAILED
                                                      (alert Joe, do not continue)

[N-04] COVERAGE
  │  E2 / E2A / E2B: check all CSI divisions covered
  │  Output: coverage_gaps list
  │
  ▼
[H-02] HUMAN: SCOPE REVIEW
  │  Joe reviews extracted scope items
  │  - ACCEPT: item confirmed, passes gate
  │  - EDIT: Joe corrects text/quantity — correction logged to shadow mode
  │  - REJECT: item removed — correction logged
  │  - ADD: Joe adds missed item — logged as E1 false negative
  │
  ▼
[N-05] TAXONOMY
  │  E0: map scope items to company cost codes (NewCo/Trias taxonomy)
  │  Output: estimate_lines with CSI + internal code mapping
  │
  ▼
[N-06] ESTIMATE GATE
  │  A10: validate estimate structure and completeness
  │  Check: all required divisions present, no orphaned lines
  │
  ├─── gate PASS ──────────────────────────────────► [N-07] BID CONFIDENCE
  │
  └─── gate FAIL ──────────────────────────────────► [H-03] HUMAN: ESTIMATE REVIEW
                                                         │ Joe resolves gaps
                                                         ▼
                                                    [N-07] BID CONFIDENCE

[N-07] BID CONFIDENCE
  │  4-vector calculator: coverage, supplier intel, scope clarity, schedule risk
  │  Output: bid_confidence score (0-100)
  │
  ▼
[H-04] HUMAN: COVERAGE REVIEW  (if gaps exist)
  │  Joe reviews uncovered divisions
  │  - Acknowledge gap (bid with exclusion)
  │  - Resolve gap (add scope or sub quote)
  │
  ▼
[N-08] PROPOSAL GENERATE
  │  Proposal Generator: build structured proposal from approved state
  │  Output: proposal_draft (PDF-ready)
  │
  ▼
[H-05] HUMAN: PROPOSAL APPROVE
  │  Joe reviews proposal before submission
  │  - APPROVE: proceed to submit
  │  - REVISE: return to specific node
  │
  ▼
[N-09] SUBMIT
  │  Lock proposal state, write final event log entry
  │  Output: submitted bid record with full audit trail
  │
  ▼
END

---

## Human Interrupt Points (LangGraph interrupt_before)

| ID    | Trigger Condition                          | Joe's Actions              |
|-------|--------------------------------------------|----------------------------|
| H-01  | doc_type = UNKNOWN or margin < threshold   | Confirm document type      |
| H-02  | scope_items extracted (always)             | Accept / Edit / Reject / Add |
| H-03  | A10 gate fails                             | Resolve estimate gaps      |
| H-04  | Coverage gaps present                      | Acknowledge or resolve     |
| H-05  | Proposal generated (always)                | Approve or revise          |

---

## Correction Logging (Shadow Mode)

Every human action at H-01 through H-05 writes a CorrectionRecord:

```python
@dataclass
class CorrectionRecord:
    record_id:          str   # UUID
    project_id:         str
    bid_id:             str
    document_sha256:    str
    extractor_version:  str
    harness_version:    str
    node_id:            str   # H-01 through H-05
    item_id:            str   # scope_item_id, doc_id, etc.
    original_value:     str   # what E1 produced
    corrected_value:    str   # what Joe said it should be
    action:             str   # accepted | edited | rejected | added | confirmed
    reason:             str   # Joe's free text (optional)
    reviewed_by:        str   # Joe's user ID
    reviewed_at:        str   # ISO timestamp
```

These records accumulate during the pilot and become the labeled dataset
for calibration harness v2. Joe's corrections ARE the training data.

---

## LangGraph Implementation Notes

**Persistence:** Use LangGraph's SqliteSaver or PostgresSaver (Supabase).
Every state checkpoint is stored. Joe can close his browser and resume.

**Streaming:** Each node streams its progress to the UI in real time.
No spinners. Joe sees "Extracting scope from Division 23... 14 items found."

**Retry on failure:** If E1 crashes on a document, LangGraph replays from
the INGEST checkpoint with the same document. No data loss.

**Parallel processing:** Multiple documents in a bid package can run
through N-01 → N-03 in parallel. They converge at N-04 (coverage check
needs all documents before it can verify completeness).

---

## TronixMesh Integration Points

- N-01 INGEST: writes document record to TronixMesh event ledger
- H-02 SCOPE REVIEW: correction records written to ledger (immutable)
- N-09 SUBMIT: final bid record sealed in ledger with full provenance chain
- All node transitions: logged with agent identity (Robert) + timestamp

---

## Deploy Target

Robert's workspace: `/var/lib/robert/workspace/precon/`
Runtime: TronixMesh agent | LangGraph StateGraph
Entry point: `precon/api/main.py` (FastAPI) → invokes LangGraph graph

---

*Pending RR-0041 approval before deployment.*
*Node map v1.0 — awaiting Chris approval before Robert implementation begins.*
