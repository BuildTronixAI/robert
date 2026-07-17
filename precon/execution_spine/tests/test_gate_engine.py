"""
BUILDTRONIX EXECUTION SPINE — Gate Engine Tests
Covers all 7 P0 findings from Claude's review.
"""

import sys
import os
import uuid
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from precon.execution_spine.gate_engine import (
    GateEngine, GateResult,
    SubmittalItem, SubmittalRevision, POLine, ScheduleTask,
    SubmittalApprovalStatus, ApprovedAsNotedRelease,
    SubstitutionStatus, ScopeItemStatus,
)


def make_id():
    return str(uuid.uuid4())


PROJECT_ID = make_id()


def approved_submittal(sub_id=None, rev_id=None, scope_id=None) -> SubmittalItem:
    sub_id = sub_id or make_id()
    rev_id = rev_id or make_id()
    rev = SubmittalRevision(
        submittal_revision_id=rev_id,
        submittal_item_id=sub_id,
        revision_number=1,
        approval_status=SubmittalApprovalStatus.APPROVED,
    )
    return SubmittalItem(
        submittal_item_id=sub_id,
        project_id=PROJECT_ID,
        scope_item_id=scope_id or make_id(),
        description="Test submittal",
        current_revision_id=rev_id,
        current_revision=rev,
    )


# =============================================================================
# P0-1 / P0-2: Scope transition invariant — no in-place overwrite
# =============================================================================

class TestScopeTransitionGate:

    def test_active_to_active_is_blocked(self):
        """P0-1/P0-2: Active scope cannot be updated in place."""
        engine = GateEngine()
        dec = engine.evaluate_scope_transition(
            scope_item_id=make_id(),
            project_id=PROJECT_ID,
            from_status=ScopeItemStatus.ACTIVE,
            to_status=ScopeItemStatus.ACTIVE,
        )
        assert dec.result == GateResult.BLOCK
        assert any("SCOPE_IMMUTABILITY_VIOLATION" in r for r in dec.blocking_reasons)

    def test_active_to_superseded_is_pass(self):
        """Active → superseded is the correct path (new row with supersedes_id)."""
        engine = GateEngine()
        dec = engine.evaluate_scope_transition(
            scope_item_id=make_id(),
            project_id=PROJECT_ID,
            from_status=ScopeItemStatus.ACTIVE,
            to_status=ScopeItemStatus.SUPERSEDED,
        )
        assert dec.result == GateResult.PASS

    def test_co_transition_requires_source_doc(self):
        """P0-2: CO transitions require source_document_id."""
        engine = GateEngine()
        dec = engine.evaluate_scope_transition(
            scope_item_id=make_id(),
            project_id=PROJECT_ID,
            from_status=ScopeItemStatus.ACTIVE,
            to_status=ScopeItemStatus.PENDING_CO,
            source_document_id=None,
        )
        assert dec.result == GateResult.BLOCK
        assert any("CO_SOURCE_REQUIRED" in r for r in dec.blocking_reasons)

    def test_co_transition_with_source_doc_passes(self):
        """CO transition passes when source document is provided."""
        engine = GateEngine()
        dec = engine.evaluate_scope_transition(
            scope_item_id=make_id(),
            project_id=PROJECT_ID,
            from_status=ScopeItemStatus.ACTIVE,
            to_status=ScopeItemStatus.PENDING_CO,
            source_document_id=make_id(),
        )
        assert dec.result == GateResult.PASS


# =============================================================================
# P0-3: Submittal revision — PO requires a revision, not just an item
# =============================================================================

class TestPOReleaseGate:

    def test_approved_submittal_passes(self):
        """P0-3: PO releases when submittal has approved revision."""
        engine = GateEngine()
        sub = approved_submittal()
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.PASS

    def test_no_revision_blocks_po(self):
        """P0-3: No revision = no PO."""
        engine = GateEngine()
        sub = SubmittalItem(
            submittal_item_id=make_id(),
            project_id=PROJECT_ID,
            scope_item_id=make_id(),
            description="No revision submittal",
            current_revision_id=None,
            current_revision=None,
        )
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK
        assert any("SUBMITTAL_NO_REVISION" in r for r in dec.blocking_reasons)

    def test_under_review_blocks_po(self):
        """Submittal under review cannot release PO."""
        engine = GateEngine()
        rev_id = make_id()
        sub_id = make_id()
        rev = SubmittalRevision(
            submittal_revision_id=rev_id,
            submittal_item_id=sub_id,
            revision_number=1,
            approval_status=SubmittalApprovalStatus.UNDER_REVIEW,
        )
        sub = SubmittalItem(
            submittal_item_id=sub_id,
            project_id=PROJECT_ID,
            scope_item_id=make_id(),
            description="Under review",
            current_revision_id=rev_id,
            current_revision=rev,
        )
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub_id,
            released_by_submittal_revision_id=rev_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK
        assert any("SUBMITTAL_NOT_APPROVED" in r for r in dec.blocking_reasons)

    def test_revise_and_resubmit_blocks_po(self):
        """Revise & resubmit cannot release PO."""
        engine = GateEngine()
        rev_id = make_id()
        sub_id = make_id()
        rev = SubmittalRevision(
            submittal_revision_id=rev_id,
            submittal_item_id=sub_id,
            revision_number=1,
            approval_status=SubmittalApprovalStatus.REVISE_AND_RESUBMIT,
        )
        sub = SubmittalItem(
            submittal_item_id=sub_id,
            project_id=PROJECT_ID,
            scope_item_id=make_id(),
            description="RR submittal",
            current_revision_id=rev_id,
            current_revision=rev,
        )
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub_id,
            released_by_submittal_revision_id=rev_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK


# =============================================================================
# P0-4: Approved-as-noted release rules
# =============================================================================

class TestApprovedAsNotedGate:

    def _make_aan_submittal(self, release: ApprovedAsNotedRelease | None):
        rev_id = make_id()
        sub_id = make_id()
        rev = SubmittalRevision(
            submittal_revision_id=rev_id,
            submittal_item_id=sub_id,
            revision_number=1,
            approval_status=SubmittalApprovalStatus.APPROVED_AS_NOTED,
            approved_as_noted_release=release,
        )
        sub = SubmittalItem(
            submittal_item_id=sub_id, project_id=PROJECT_ID,
            scope_item_id=make_id(), description="AAN submittal",
            current_revision_id=rev_id, current_revision=rev,
        )
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub_id,
            released_by_submittal_revision_id=rev_id,
        )
        return sub, po

    def test_aan_no_release_decision_blocks(self):
        """P0-4: AAN with no release decision must block."""
        engine = GateEngine()
        sub, po = self._make_aan_submittal(None)
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK
        assert any("APPROVED_AS_NOTED_NO_RELEASE_DECISION" in r for r in dec.blocking_reasons)

    def test_aan_release_allowed_passes(self):
        """P0-4: AAN with release_allowed passes."""
        engine = GateEngine()
        sub, po = self._make_aan_submittal(ApprovedAsNotedRelease.RELEASE_ALLOWED)
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.PASS

    def test_aan_blocked_pending_clarification(self):
        """P0-4: AAN with release_blocked_pending_clarification blocks."""
        engine = GateEngine()
        sub, po = self._make_aan_submittal(
            ApprovedAsNotedRelease.RELEASE_BLOCKED_PENDING_CLARIFICATION
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK

    def test_aan_release_with_conditions_passes(self):
        """P0-4: AAN with release_allowed_with_conditions passes."""
        engine = GateEngine()
        sub, po = self._make_aan_submittal(ApprovedAsNotedRelease.RELEASE_ALLOWED_WITH_CONDITIONS)
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.PASS


# =============================================================================
# P0-5: Substitution workflow
# =============================================================================

class TestSubstitutionGate:

    def test_unresolved_substitution_blocks_po(self):
        """P0-5: Pending substitution request blocks PO."""
        engine = GateEngine()
        sub = approved_submittal()
        sub.substitution_status = SubstitutionStatus.UNDER_REVIEW
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK
        assert any("SUBSTITUTION_UNRESOLVED" in r for r in dec.blocking_reasons)

    def test_approved_equal_substitution_passes(self):
        """P0-5: Approved-equal substitution does not block PO."""
        engine = GateEngine()
        sub = approved_submittal()
        sub.substitution_status = SubstitutionStatus.APPROVED_EQUAL
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.PASS

    def test_rejected_substitution_passes_po_gate(self):
        """P0-5: Rejected substitution (specified product stands) does not block PO."""
        engine = GateEngine()
        sub = approved_submittal()
        sub.substitution_status = SubstitutionStatus.REJECTED
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.PASS


# =============================================================================
# P0-6: Stale approval detection
# =============================================================================

class TestStaleApprovalGate:

    def test_po_on_stale_revision_is_blocked(self):
        """P0-6: PO released against old revision is flagged when new revision exists."""
        engine = GateEngine()
        old_rev_id = make_id()
        new_rev_id = make_id()
        sub_id = make_id()

        new_rev = SubmittalRevision(
            submittal_revision_id=new_rev_id,
            submittal_item_id=sub_id,
            revision_number=2,
            approval_status=SubmittalApprovalStatus.APPROVED,
        )
        sub = SubmittalItem(
            submittal_item_id=sub_id,
            project_id=PROJECT_ID,
            scope_item_id=make_id(),
            description="Re-submitted",
            current_revision_id=new_rev_id,  # new revision is current
            current_revision=new_rev,
        )
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub_id,
            released_by_submittal_revision_id=old_rev_id,  # PO still on old revision
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.result == GateResult.BLOCK
        assert any("STALE_APPROVAL" in r for r in dec.blocking_reasons)


# =============================================================================
# P0-7: Schedule task polymorphic dependency
# =============================================================================

class TestScheduleTaskGate:

    def test_procurement_task_without_po_blocks(self):
        """P0-7: procurement task requires linked PO line."""
        engine = GateEngine()
        task = ScheduleTask(
            schedule_task_id=make_id(),
            project_id=PROJECT_ID,
            task_name="Install controls equipment",
            blocking_dependency_type="po_line",
            scope_item_id=make_id(),
        )
        dec = engine.evaluate_schedule_task_release(task, po_line=None)
        assert dec.result == GateResult.BLOCK
        assert any("PO_LINE_MISSING" in r for r in dec.blocking_reasons)

    def test_non_procurement_task_no_po_passes(self):
        """P0-7: Mobilization, inspection, etc. require only scope — no PO."""
        engine = GateEngine()
        task = ScheduleTask(
            schedule_task_id=make_id(),
            project_id=PROJECT_ID,
            task_name="Site mobilization",
            blocking_dependency_type="none",
            scope_item_id=make_id(),
        )
        dec = engine.evaluate_schedule_task_release(task)
        assert dec.result == GateResult.PASS

    def test_procurement_task_with_cleared_po_passes(self):
        """P0-7: Procurement task passes when PO gate is cleared."""
        engine = GateEngine()
        sub = approved_submittal()
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        po_gate = engine.evaluate_po_release(po, sub)
        assert po_gate.result == GateResult.PASS

        task = ScheduleTask(
            schedule_task_id=make_id(),
            project_id=PROJECT_ID,
            task_name="Install controls",
            blocking_dependency_type="po_line",
            blocking_dependency_id=po.po_line_id,
            scope_item_id=make_id(),
        )
        dec = engine.evaluate_schedule_task_release(task, po_line=po, po_gate_result=po_gate)
        assert dec.result == GateResult.PASS

    def test_submittal_dependent_task_blocks_without_approval(self):
        """P0-7: Submittal-dependent task blocks if submittal not approved."""
        engine = GateEngine()
        rev_id = make_id()
        sub_id = make_id()
        rev = SubmittalRevision(
            submittal_revision_id=rev_id,
            submittal_item_id=sub_id,
            revision_number=1,
            approval_status=SubmittalApprovalStatus.UNDER_REVIEW,
        )
        sub = SubmittalItem(
            submittal_item_id=sub_id, project_id=PROJECT_ID,
            scope_item_id=make_id(), description="Under review",
            current_revision_id=rev_id, current_revision=rev,
        )
        task = ScheduleTask(
            schedule_task_id=make_id(),
            project_id=PROJECT_ID,
            task_name="Order long-lead equipment",
            blocking_dependency_type="submittal_item",
            blocking_dependency_id=sub_id,
            scope_item_id=make_id(),
        )
        dec = engine.evaluate_schedule_task_release(task, submittal=sub)
        assert dec.result == GateResult.BLOCK

    def test_task_without_scope_binding_non_procurement_passes(self):
        """P0-7: None-dependency task with no scope (e.g. admin) still passes."""
        engine = GateEngine()
        task = ScheduleTask(
            schedule_task_id=make_id(),
            project_id=PROJECT_ID,
            task_name="Closeout documentation",
            blocking_dependency_type="none",
            scope_item_id=None,
        )
        dec = engine.evaluate_schedule_task_release(task)
        assert dec.result == GateResult.PASS


# =============================================================================
# Gate event log
# =============================================================================

class TestGateEventLog:

    def test_all_decisions_logged(self):
        """Enhancement 4: Every gate decision is logged internally."""
        engine = GateEngine()
        sub = approved_submittal()
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        engine.evaluate_po_release(po, sub)
        engine.evaluate_scope_transition(
            make_id(), PROJECT_ID, ScopeItemStatus.ACTIVE, ScopeItemStatus.SUPERSEDED
        )
        assert len(engine.decisions) == 2
        assert all(d.gate_event_id for d in engine.decisions)

    def test_gate_event_has_required_fields(self):
        """Gate event must have project_id, gate_code, target, result, timestamp."""
        engine = GateEngine()
        sub = approved_submittal()
        po = POLine(
            po_line_id=make_id(), project_id=PROJECT_ID,
            submittal_item_id=sub.submittal_item_id,
            released_by_submittal_revision_id=sub.current_revision_id,
        )
        dec = engine.evaluate_po_release(po, sub)
        assert dec.project_id == PROJECT_ID
        assert dec.gate_code == "PO_RELEASE_GATE"
        assert dec.target_type == "po_line"
        assert dec.result in (GateResult.PASS, GateResult.BLOCK)
        assert dec.evaluated_at


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd="/var/lib/openclaw/.openclaw/workspace"
    )
    print(result.stdout)
    print(result.stderr)
