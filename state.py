"""State schema for Robert COO Agent."""

from typing import TypedDict, List, Optional, Dict, Any


class RobertState(TypedDict):
    """State dictionary for Robert LangGraph execution.

    All fields that any node reads or writes must be declared here.
    Missing declarations cause silent KeyError / None returns at runtime.
    (RR-0022: audit completed 2026-04-24 — added 14 undeclared runtime fields)
    """

    # ── Core task fields ─────────────────────────────────────────────────────

    current_task: str
    """The current task being processed. Set by listener; primary input."""

    task: str
    """Alias for current_task used by reviewer and architect nodes.
    Set by planner. Kept separate for legacy compatibility."""

    task_id: str
    """Short unique ID for this task run (8-char UUID prefix). Set by planner."""

    task_type: str
    """Task classification: 'code', 'design', 'architecture', 'system',
    'finance', 'general'. Set by planner; used for routing and review."""

    memory_context: str
    """Context loaded from knowledge base / memory files. Set by main.py."""

    # ── Routing and control fields ────────────────────────────────────────────

    is_finance_task: bool
    """Whether task involves financial operations. Set by planner."""

    is_coding_task: bool
    """Whether task requires writing and executing code. Set by planner."""

    origin_node: str
    """Which execution node ran this iteration: 'executor', 'coder',
    'architect', 'bill'. Set by each execution node for retry routing."""

    iteration_count: int
    """Number of review iterations completed. Incremented by planner and reviewer."""

    requires_escalation: bool
    """Whether task requires human review / approval. Set by any node."""

    needs_revision: bool
    """Whether reviewer determined output needs another iteration. Set by reviewer."""

    needs_redesign: bool
    """Whether reviewer determined architecture must change (not just code).
    Set by reviewer; triggers re-route to architect instead of coder."""

    revision_notes: str
    """Guidance for the next iteration. Set by reviewer when needs_revision=True."""

    escalate_reason: str
    """Reason for escalation when requires_escalation=True. Set by reviewer."""

    # ── Execution outputs ─────────────────────────────────────────────────────

    result: str
    """Final result of execution. Set by execution nodes, updated by reviewer."""

    error: str
    """Error message if task failed. Set by any node on exception."""

    messages: List[dict]
    """Conversation/planning messages. Each entry: {'role': str, 'content': str}."""

    # ── Quality review fields ─────────────────────────────────────────────────

    quality_approved: bool
    """Whether reviewer approved the output quality. Set by reviewer."""

    quality_scores: Dict[str, Any]
    """Detailed scores from reviewer LLM evaluation. Set by reviewer."""

    # ── Workflow tracking ─────────────────────────────────────────────────────

    pending_approvals: List[str]
    """List of items awaiting human approval."""

    active_workflows: List[str]
    """Currently active workflows."""

    # ── Architect / coder pipeline fields ────────────────────────────────────

    context: str
    """Additional context passed between architect and coder nodes."""

    steps: List[str]
    """Execution steps produced by architect. Consumed by coder."""

    design_doc: str
    """Architecture design document produced by architect node."""

    test_file: str
    """Path to generated test file. Set by coder node."""

    tests_generated: bool
    """Whether tests were generated for this task. Set by coder node."""

    test_results: Dict[str, Any]
    """Test run results: {'passed': int, 'failed': int, 'output': str}.
    Set by coder node after running tests."""

    # ── Response mode (set by executor) ──────────────────────────────────────

    response_mode: str
    """Execution mode for this response. Set by executor node.
    'clarification' = ambiguity rule fired, asking a question.
    'engineering'   = normal task execution output.
    Reviewer uses this to skip structural pre-checks on clarification responses."""

    # ── Actor / auth context (set by listener → main) ─────────────────────────

    actor_user_id: str
    """Buildtronix user id from identity resolution. Empty when CLI/local."""

    actor_role: str
    """Role from profiles (OWNER/ADMIN/...). Empty when CLI/local."""

    actor_jwt: str
    """Short-lived user JWT for RLS-scoped tool calls. Never log this field."""

    telegram_chat_id: str
    """Origin Telegram chat id for this run."""

    # ── Gateway / Telegram conversation (Fixes 4–5) ───────────────────────────

    message_kind: str
    """Inbound classifier: 'CHAT' or 'TASK'. Set by main/listener; refined by planner."""

    conversation_history: List[dict]
    """Prior Telegram turns for this chat: [{'role': 'user'|'assistant', 'content': str}]."""
