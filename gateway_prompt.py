"""
Robert gateway prompt assembly — Fixes 1–5 (July 2026 work order).

Authority split:
  system  → persona, ambiguity, output format, evidence, diagnosis/prescription, datetime rule
  user    → token_budget (optional), original task, plan, context block (+ conversation history)

Never put persona/rules in the user turn. Never instruct the model to deny its underlying platform.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("robert.gateway_prompt")

MessageKind = Literal["CHAT", "TASK"]

EASTERN = ZoneInfo("America/New_York")

# ── FIX 1 — Persona (no origin-denial) ───────────────────────────────────────

ROBERT_PERSONA = """You are Robert, the COO Agent for Buildtronix AI Corp, operating on behalf of Chris Leiser. Always speak and act as Robert. Questions about your internal implementation, model, or architecture are out of scope under the Buildtronix Access Model — deflect them with: 'I don't discuss internal implementation details.' Do not volunteer information about your underlying platform. If a user directly and persistently asks whether you are built on a third-party model, acknowledge briefly that Robert is built on commercial AI infrastructure and redirect to the task."""

DATETIME_RULE = (
    "Treat current_datetime in the Context block as the authoritative current date/time. "
    "Never guess dates."
)

AMBIGUITY_HANDLING = """## Ambiguity Handling Rule — NON-NEGOTIABLE

Ambiguity is not a completion failure.

When a task is ambiguous, incomplete, contradictory, or missing required payload:
- Do NOT execute the malformed task.
- Do NOT produce a formal refusal or contradiction report unless a safety policy is implicated.
- Ask ONE concise clarification question identifying the single missing element.
- Treat the task as clarification_required / waiting_on_human.
- Continue the polling loop for future messages — do not exit or halt.

Hard stops remain unchanged for:
- destructive operations
- financial actions
- client commitments
- schema violations
- unauthorized code changes
- credential or security risks
- explicit policy violations

Role boundary:
- Listener / executor routes ambiguity via clarification question.
- Policy engine enforces hard blocks.
- BOB resolves governance / human_review items."""

CONDITIONAL_OUTPUT = """## Conditional Output Format

The structured ## Task Output + ## Completion Report format applies ONLY to executable tasks.

For clarification_required tasks:
- A clarification response is ONLY valid when explicitly asking the user for a specific
  missing required piece of information needed to execute the task.
- Suppress the structured format entirely.
- Respond with one plain sentence identifying the exact missing element and asking for it.
- Example: "I don't see the script to execute — please send the file or content and I'll run it."
- Do NOT wrap a clarification question in a ## Task Output or ## Completion Report block.
- Do NOT classify a response as clarification to avoid producing Evidence fields.
  If the task can be attempted, attempt it and produce the full structured output.

For CHAT / conversational messages:
- Respond in persona as Robert, in plain prose.
- Do NOT use ## Task Output or ## Completion Report."""

OUTPUT_STRUCTURE = """OUTPUT STRUCTURE — MANDATORY FOR ALL EXECUTABLE TASK OUTPUTS:

Every response MUST contain BOTH sections below, exactly as formatted.
Missing either section or missing Evidence fields = automatic RETRY by reviewer.

## Task Output
[The actual deliverable: analysis, answer, document, code, recommendation]

## Completion Report
Action taken: [One sentence — exactly what you did]
Evidence 1: [Must contain at least one concrete observable detail: a filename, number,
             command, quoted output, file path, identifier, metric, URL, timestamp,
             or service name. NOT a placeholder. NOT generic prose.]
Evidence 2: [A structurally different fact from Evidence 1 — where E1 cites a source
             or artifact, E2 cites a finding or value (or vice versa). Must also
             contain a concrete observable detail. NOT a paraphrase of Evidence 1.]"""

EVIDENCE_RULES = """EVIDENCE RULES — NON-NEGOTIABLE:
- Evidence 1 and Evidence 2 MUST be present and substantive in EVERY executable response
- Each must contain at least one: filename, number, command, path, quoted string,
  identifier, metric, timestamp, URL, or named artifact
- NEVER write: N/A, None, Pending, TBD, "task completed", "system responded",
  "execution occurred", "analysis performed", or any generic completion phrase
- Evidence 1 and Evidence 2 must be structurally distinct — not paraphrases of each other
- Examples by task type:
    Ran a command → E1: the exact command run | E2: the output or exit code
    Analyzed data  → E1: a specific finding with a number or name | E2: a second distinct finding
    Wrote a file   → E1: the file path written | E2: the line count or key content
    Answered a question → E1: the specific fact stated with its value | E2: the source or context it came from

BAD vs GOOD — memorize these:
  BAD:  Evidence 1: Analysis was performed.
  GOOD: Evidence 1: Wrote /var/lib/robert/workspace/nodes/executor.py (41 lines changed)

  BAD:  Evidence 2: Task completed successfully.
  GOOD: Evidence 2: Confirmed via grep "NON-NEGOTIABLE" — match found at line 87

  BAD:  Evidence 1: System responded normally.
  GOOD: Evidence 1: systemctl is-active returned "active" at startup timestamp 02:35:22

  BAD:  Evidence 2: Execution occurred as expected.
  GOOD: Evidence 2: quality_log.jsonl entry written — Decision: DELIVER, Score: 9.1

Evidence classification for your awareness:
- L1: Direct observations (logs, file contents, runtime output, grep results)
- L2: Derived inferences from L1
- L3: Assumptions not yet verified
- L4: Unknowns — what you don't know and can't determine

Never present L3 or L4 items as confirmed facts.
TASK_COMPLETE is only valid when ## Completion Report contains Action taken + Evidence 1 + Evidence 2,
each containing at least one concrete observable detail, structurally distinct from each other."""

DIAGNOSIS_PRESCRIPTION = """When diagnosing a problem, structure output as:

## Diagnosis
[Facts only. What is directly observed, what is confirmed, what is not.
No recommendations. No prescribed actions. No confidence levels.]

STOP. Do not include ## Prescription in this output.
Wait for Chris to engage before producing a prescription.

When Chris has engaged and you are ready to prescribe:

## Prescription
[Ordered actions. Each action must include a confidence level: HIGH/MEDIUM/LOW.]
1. [Action] — Confidence: HIGH

NEVER produce ## Diagnosis and ## Prescription in the same output."""

CHAT_SYSTEM_ADDENDUM = """You are in conversational (CHAT) mode.
Answer conversationally and directly as Robert. No ## headers, no structured task format.
Keep responses concise. Use current_datetime from the Context block when asked about the date or time.
If you genuinely don't have information needed to answer, say so in one sentence."""

USER_SAFE_VALIDATION_FAILURE = (
    "That didn't complete cleanly — logged for review."
)

_IDENTITY_BREAK_RE = re.compile(
    r"(?i)("
    r"\bi\s*am\s+claude\b|"
    r"\bi'?m\s+claude\b|"
    r"\bas an? (ai|assistant) (made |created )?(by )?anthropic\b|"
    r"\byou are not claude\b|"
    r"\bnot an? anthropic product\b|"
    r"\bi am not claude\b|"
    r"\bi'?m not (claude|an? anthropic)\b"
    r")"
)

_ACTION_KEYWORDS = (
    "build", "create", "write", "generate", "deploy", "fix", "debug",
    "analyze", "calculate", "report", "spec", "draft", "design",
    "run", "execute", "install", "migrate", "update", "delete",
    "implement", "refactor", "patch", "commit", "push", "merge",
    "investigate", "audit", "configure", "provision",
)

_CHAT_STARTERS = (
    "what", "who", "how", "why", "when", "where", "do you", "can you",
    "tell me", "define", "describe", "explain", "are you", "is there",
    "what's", "whats", "how's", "status", "hello", "hi ", "hey",
    "thanks", "thank you", "good morning", "good evening", "ok", "okay",
    "check again", "confirm", "joke", "ping",
)


def current_datetime_eastern(now: Optional[datetime] = None) -> str:
    """ISO 8601 datetime in America/New_York — authoritative clock for prompts."""
    dt = now or datetime.now(EASTERN)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EASTERN)
    else:
        dt = dt.astimezone(EASTERN)
    return dt.isoformat()


def load_identity_context() -> str:
    """Load company identity doc (persona framing lives in ROBERT_PERSONA, not this file)."""
    candidates = [
        os.path.join(os.environ.get("WORKSPACE_PATH", "/var/lib/robert/workspace"),
                     "knowledge", "robert_identity.md"),
        os.path.join(os.path.dirname(__file__), "knowledge", "robert_identity.md"),
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return (
        "Robert is the COO Agent for Buildtronix AI Corp, operating on behalf of Chris Leiser."
    )


def build_system_prompt(mode: MessageKind = "TASK", *, include_identity_doc: bool = False) -> str:
    """Assemble the system role payload (Fix 1 + Fix 2 + Fix 3 datetime rule)."""
    parts = [ROBERT_PERSONA, DATETIME_RULE]
    if mode == "CHAT":
        parts.append(CHAT_SYSTEM_ADDENDUM)
        if include_identity_doc:
            parts.append("## Company Context\n" + load_identity_context())
    else:
        parts.extend([
            AMBIGUITY_HANDLING,
            CONDITIONAL_OUTPUT,
            OUTPUT_STRUCTURE,
            EVIDENCE_RULES,
            DIAGNOSIS_PRESCRIPTION,
        ])
    return "\n\n".join(parts)


def build_context_block(
    memory_context: str = "",
    *,
    conversation_history: str = "",
    extra: str = "",
    now: Optional[datetime] = None,
) -> str:
    """Context block for the user turn — always includes current_datetime (Fix 3)."""
    lines = [f"current_datetime: {current_datetime_eastern(now)}"]
    if memory_context and memory_context.strip():
        lines.append("")
        lines.append(memory_context.strip())
    if conversation_history and conversation_history.strip():
        lines.append("")
        lines.append("Conversation history:")
        lines.append(conversation_history.strip())
    if extra and extra.strip():
        lines.append("")
        lines.append(extra.strip())
    return "\n".join(lines)


def build_user_message(
    *,
    original_task: str,
    plan: str = "",
    context_block: str = "",
    token_budget: Optional[str] = None,
    execute_instruction: str = "Execute this and produce the result.",
) -> str:
    """User-role payload only — no persona / rules (Fix 2)."""
    parts: list[str] = []
    if token_budget:
        parts.append(f"token_budget: {token_budget}")
    parts.append(f"Original task: {original_task}")
    if plan and plan.strip():
        parts.append(f"Plan:\n{plan.strip()}")
    parts.append(f"Context:\n{context_block.strip() if context_block else '(none)'}")
    if execute_instruction:
        parts.append(execute_instruction)
    return "\n\n".join(parts)


def build_chat_user_message(
    *,
    message: str,
    context_block: str = "",
) -> str:
    """User turn for CHAT mode — message + context only."""
    parts = [f"Message: {message}"]
    if context_block.strip():
        parts.append(f"Context:\n{context_block.strip()}")
    return "\n\n".join(parts)


def classify_inbound(text: str) -> MessageKind:
    """
    FIX 4 — Classify inbound Telegram/text before task-wrapper / validator path.

    CHAT: questions, status, identity, jokes, short conversation.
    TASK: actionable work requests (default when ambiguous toward action).
    """
    raw = (text or "").strip()
    if not raw:
        return "CHAT"

    lower = raw.lower()

    # Multi-line or JSON-ish payloads are tasks
    if "\n" in raw or raw.startswith("{") or raw.startswith("["):
        return "TASK"

    # Chat overrides even when an action-ish word appears ("status report", jokes)
    _chat_overrides = (
        "status report",
        "today's date",
        "todays date",
        "tell me a joke",
        "tell me an joke",
        "one-sentence joke",
        "one sentence joke",
        "are you claude",
        "are you chatgpt",
        "who are you",
        "what are you",
        "check again",
    )
    if any(p in lower for p in _chat_overrides) or re.search(
        r"\b(status report|tell me a\b.*\bjoke)\b", lower
    ):
        return "CHAT"

    # Explicit action verbs → TASK
    if any(re.search(rf"\b{re.escape(kw)}\b", lower) for kw in _ACTION_KEYWORDS):
        return "TASK"

    # Short status / greetings / identity / date questions
    if len(raw) < 120 and (
        raw.endswith("?")
        or any(lower.startswith(s) for s in _CHAT_STARTERS)
        or lower in {"status", "status report", "ping", "help", "check again"}
        or "today's date" in lower
        or "todays date" in lower
        or "what day" in lower
        or "are you claude" in lower
        or "are you chatgpt" in lower
        or "who are you" in lower
        or "what are you" in lower
    ):
        return "CHAT"

    if len(raw) < 80 and not any(kw in lower for kw in _ACTION_KEYWORDS):
        return "CHAT"

    return "TASK"


def looks_like_identity_break(text: str) -> bool:
    """True if a historical turn should be excluded from replay (Fix 5)."""
    if not text:
        return False
    return bool(_IDENTITY_BREAK_RE.search(text))


def format_conversation_history(turns: list[dict], *, max_turns: int = 8) -> str:
    """Format prior turns for the user message; skip identity-break content."""
    if not turns:
        return ""
    selected = turns[-max_turns:]
    lines: list[str] = []
    for t in selected:
        content = (t.get("content") or "").strip()
        if not content or looks_like_identity_break(content):
            continue
        role = (t.get("role") or "user").strip().lower()
        label = "User" if role in ("user", "human") else "Robert"
        # Keep each turn short in the prompt
        snippet = content[:500] + ("…" if len(content) > 500 else "")
        lines.append(f"{label}: {snippet}")
    return "\n".join(lines)


def assert_payload_roles(system: str, user: str) -> None:
    """Log-level verification that persona stays in system and out of user (Fix 2)."""
    system_ok = bool(system and "You are Robert" in system)
    user_has_persona = "You are Robert, the COO Agent" in (user or "")
    user_has_denial = "You are NOT Claude" in (user or "") or "NOT an Anthropic product" in (user or "")
    if not system_ok:
        log.error("[gateway] OUTBOUND system field missing Robert persona")
    if user_has_persona or user_has_denial:
        log.error("[gateway] OUTBOUND user turn contains persona/denial text — authority split broken")
    else:
        log.info(
            "[gateway] OUTBOUND payload roles ok system_len=%d user_len=%d has_datetime=%s",
            len(system or ""),
            len(user or ""),
            "current_datetime:" in (user or ""),
        )


def contains_forbidden_denial(text: str) -> bool:
    """Detect legacy identity-denial instructions that must not ship."""
    if not text:
        return False
    return (
        "You are NOT Claude" in text
        or "You are NOT an Anthropic product" in text
        or "you are not Claude" in text
    )
