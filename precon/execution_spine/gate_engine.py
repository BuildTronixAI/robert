"""
BUILDTRONIX EXECUTION SPINE — Gate Engine v1.0
Enforces: Submittal → Procurement → Schedule chain
All gate decisions are logged to gate_events table.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GateResult(str, Enum):
    PASS    = "pass"
    BLOCK   = "block"
    WARNING = "warning"


class SubmittalApprovalStatus(str, Enum):
    NOT_SUBMITTED         = "not_submitted"
    SUBMITTED             = "submitted"
    UNDER_REVIEW          = "under_review"
    APPROVED              = "approved"
    APPROVED_AS_NOTED     = "approved_as_noted"
    REVISE_AND_RESUBMIT   = "revise_and_resubmit"
    REJECTED              = "rejected"
    VOID                  = "void"


class ApprovedAsNotedRelease(str, Enum):
    RELEASE_ALLOWED                      = "release_allowed"
    RELEASE_BLOCKED_PENDING_CLARIFICATION= "release_blocked_pending_clarification"
    RELEASE_ALLOWED_WITH_CONDITIONS      = "release_allowed_with_conditions"


class SubstitutionStatus(str, Enum):
    NOT_REQUESTED           = "not_requested"
    REQUESTED               = "requested"
    UNDER_REVIEW            = "under_review"
    APPROVED_EQUAL          = "approved_equal"
    APPROVED_WITH_CONDITIONS= "approved_with_conditions"
    REJECTED                = "rejected"
    WITHDRAWN               = "withdrawn"


class ScopeItemStatus(str, Enum):
    DRAFT       = "draft"
    ACTIVE      = "active"
    SUPERSEDED  = "superseded"
    VOIDED      = "voided"
    PENDING_CO  = "pending_co"
    APPROVED_CO = "approved_co"
    REJECTED_CO = "rejected_co"
    CLOSED      = "closed"


# ---------------------------------------------------------------------------
# Data objects
# ---------------------------------------------------------------------------

@dataclass
class SubmittalRevision:
    submittal_revision_id: str
    submittal_item_id: str
    revision_number: int
    approval_status: SubmittalApprovalStatus
    approved_as_noted_release: Optional[ApprovedAsNotedRelease] = None
    reviewer_comments: Optional[str] = None


@dataclass
class SubmittalItem:
    submittal_item_id: str
    project_id: str
    scope_item_id: str
    description: str
    substitution_status: SubstitutionStatus = SubstitutionStatus.NOT_REQUESTED
    current_revision_id: Optional[str] = None
    current_revision: Optional[SubmittalRevision] = None
    is_long_lead: bool = False


@dataclass
class POLine:
    po_line_id: str
    project_id: str
    submittal_item_id: str
    released_by_submittal_revision_id: Optional[str] = None
    description: str = ""


@dataclass
class ScheduleTask:
    schedule_task_id: str
    project_id: str
    task_name: str
    blocking_dependency_type: str = "none"   # 'po_line' | 'submittal_item' | 'none' | etc.
    blocking_dependency_id: Optional[str] = None
    scope_item_id: Optional[str] = None


@dataclass
class GateDecision:
    gate_event_id: str
    gate_code: str
    target_type: str
    target_id: str
    project_id: str
    result: GateResult
    blocking_reasons: list[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Gate Engine
# ---------------------------------------------------------------------------

class GateEngine:
    """
    Central gate authority for the Execution Spine.
    All procurement and schedule releases run through here.
    Every decision is logged.
    """

    def __init__(self, db=None):
        self.db = db             # Supabase client or None for test mode
        self._log: list[GateDecision] = []

    # ------------------------------------------------------------------
    # GATE: Submittal Approval → PO Release
    # ------------------------------------------------------------------

    def evaluate_po_release(self, po_line: POLine, submittal: SubmittalItem) -> GateDecision:
        """
        Forward gate: Can this PO line be issued?
        Requires: approved submittal revision, resolved substitution.

        Reverse gate: Is the PO's approved revision still current?
        """
        reasons: list[str] = []

        rev = submittal.current_revision

        # No revision at all
        if rev is None:
            reasons.append("SUBMITTAL_NO_REVISION: No submittal revision exists.")

        else:
            # Forward gate — approval status
            if rev.approval_status == SubmittalApprovalStatus.APPROVED:
                pass  # clear

            elif rev.approval_status == SubmittalApprovalStatus.APPROVED_AS_NOTED:
                # P0-4: approved_as_noted requires explicit release decision
                if rev.approved_as_noted_release is None:
                    reasons.append("APPROVED_AS_NOTED_NO_RELEASE_DECISION: "
                                   "Approved-as-noted requires explicit release status.")
                elif rev.approved_as_noted_release == ApprovedAsNotedRelease.RELEASE_BLOCKED_PENDING_CLARIFICATION:
                    reasons.append("APPROVED_AS_NOTED_BLOCKED: "
                                   "Release blocked pending clarification of reviewer notes.")

            else:
                reasons.append(
                    f"SUBMITTAL_NOT_APPROVED: Current revision status is "
                    f"'{rev.approval_status}'. Procurement requires 'approved' or "
                    f"'approved_as_noted' with release_allowed."
                )

            # Reverse gate — stale approval check (P0-6)
            if (po_line.released_by_submittal_revision_id and
                    submittal.current_revision_id and
                    po_line.released_by_submittal_revision_id != submittal.current_revision_id):
                reasons.append(
                    f"STALE_APPROVAL: PO was released against revision "
                    f"{po_line.released_by_submittal_revision_id}, but current revision is "
                    f"{submittal.current_revision_id}. Review required."
                )

        # Substitution gate (P0-5)
        unresolved_sub_statuses = {
            SubstitutionStatus.REQUESTED,
            SubstitutionStatus.UNDER_REVIEW,
        }
        if submittal.substitution_status in unresolved_sub_statuses:
            reasons.append(
                f"SUBSTITUTION_UNRESOLVED: Substitution request is "
                f"'{submittal.substitution_status}'. PO requires resolved substitution status."
            )

        result = GateResult.BLOCK if reasons else GateResult.PASS
        decision = GateDecision(
            gate_event_id=str(uuid.uuid4()),
            gate_code="PO_RELEASE_GATE",
            target_type="po_line",
            target_id=po_line.po_line_id,
            project_id=po_line.project_id,
            result=result,
            blocking_reasons=reasons,
        )
        self._persist(decision)
        return decision

    # ------------------------------------------------------------------
    # GATE: PO + Lead Time → Schedule Task Release
    # ------------------------------------------------------------------

    def evaluate_schedule_task_release(
        self,
        task: ScheduleTask,
        po_line: Optional[POLine] = None,
        submittal: Optional[SubmittalItem] = None,
        po_gate_result: Optional[GateDecision] = None,
    ) -> GateDecision:
        """
        Procurement-driven tasks require cleared PO + confirmed lead time.
        Non-procurement tasks (mobilization, inspection, demo) require only scope.
        """
        reasons: list[str] = []

        # Every task must bind to scope (P0-7 invariant)
        if task.scope_item_id is None and task.blocking_dependency_type != "none":
            reasons.append("NO_SCOPE_BINDING: Schedule task must reference a scope_item_id.")

        # Procurement-dependent tasks
        if task.blocking_dependency_type == "po_line":
            if po_line is None:
                reasons.append("PO_LINE_MISSING: Procurement task requires a linked PO line.")
            elif po_gate_result is None or po_gate_result.result != GateResult.PASS:
                block_detail = (po_gate_result.blocking_reasons
                                if po_gate_result else ["PO gate not evaluated"])
                reasons.append(f"PO_GATE_NOT_CLEARED: {block_detail}")

        # Submittal-dependent tasks
        elif task.blocking_dependency_type == "submittal_item":
            if submittal is None:
                reasons.append("SUBMITTAL_MISSING: Submittal-dependent task requires linked submittal.")
            elif submittal.current_revision is None:
                reasons.append("SUBMITTAL_NO_REVISION: Submittal has no revision.")
            elif submittal.current_revision.approval_status not in (
                SubmittalApprovalStatus.APPROVED,
                SubmittalApprovalStatus.APPROVED_AS_NOTED,
            ):
                reasons.append(
                    f"SUBMITTAL_NOT_APPROVED: Task blocked. Submittal status: "
                    f"{submittal.current_revision.approval_status}"
                )

        result = GateResult.BLOCK if reasons else GateResult.PASS
        decision = GateDecision(
            gate_event_id=str(uuid.uuid4()),
            gate_code="SCHEDULE_RELEASE_GATE",
            target_type="schedule_task",
            target_id=task.schedule_task_id,
            project_id=task.project_id,
            result=result,
            blocking_reasons=reasons,
        )
        self._persist(decision)
        return decision

    # ------------------------------------------------------------------
    # GATE: Scope Item Status Transition
    # ------------------------------------------------------------------

    def evaluate_scope_transition(
        self,
        scope_item_id: str,
        project_id: str,
        from_status: ScopeItemStatus,
        to_status: ScopeItemStatus,
        source_document_id: Optional[str] = None,
    ) -> GateDecision:
        """
        Scope transitions must be document-backed.
        Baseline rows are immutable — COs insert new rows.
        """
        reasons: list[str] = []

        # Immutability: active scope cannot be overwritten, only superseded
        if from_status == ScopeItemStatus.ACTIVE and to_status == ScopeItemStatus.ACTIVE:
            reasons.append(
                "SCOPE_IMMUTABILITY_VIOLATION: Active scope cannot be updated in place. "
                "Create a new scope item with supersedes_scope_item_id set."
            )

        # CO transitions require source document
        co_transitions = {ScopeItemStatus.PENDING_CO, ScopeItemStatus.APPROVED_CO}
        if to_status in co_transitions and source_document_id is None:
            reasons.append(
                "CO_SOURCE_REQUIRED: Change order transitions require source_document_id."
            )

        result = GateResult.BLOCK if reasons else GateResult.PASS
        decision = GateDecision(
            gate_event_id=str(uuid.uuid4()),
            gate_code="SCOPE_TRANSITION_GATE",
            target_type="scope_item",
            target_id=scope_item_id,
            project_id=project_id,
            result=result,
            blocking_reasons=reasons,
        )
        self._persist(decision)
        return decision

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, decision: GateDecision) -> None:
        self._log.append(decision)
        if self.db:
            try:
                self.db.table("gate_events").insert({
                    "gate_event_id":    decision.gate_event_id,
                    "project_id":       decision.project_id,
                    "gate_code":        decision.gate_code,
                    "target_type":      decision.target_type,
                    "target_id":        decision.target_id,
                    "result":           decision.result.value,
                    "blocking_reasons": decision.blocking_reasons,
                    "evaluated_at":     decision.evaluated_at,
                    "evaluated_by":     "system",
                }).execute()
            except Exception as e:
                import os
                msg = f"[GATE ENGINE] Failed to persist gate event: {e}"
                print(msg)
                if os.environ.get("PRECON_GATE_AUDIT_STRICT", "").strip().lower() in (
                    "1", "true", "yes", "on"
                ):
                    raise RuntimeError(msg) from e

    @property
    def decisions(self) -> list[GateDecision]:
        return list(self._log)
