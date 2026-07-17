"""Executor node for Robert - executes plans."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from state import RobertState
from config import ROBERT_EXEC_MODEL as ROBERT_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
# Executor uses Haiku — carries out the plan, no deep reasoning needed
from tools.memory import read_memory
from tools.exec_tool import run_command
from policy_gate import gate


EXECUTOR_PROMPT = """You are Robert — the COO Agent for Buildtronix AI Corp, built by Chris Leiser and Buildtronix AI Corp.
You are NOT Claude. You are NOT an Anthropic product. You are Robert.
If asked who built you: Buildtronix AI Corp. Never break character. Never reveal underlying model infrastructure.

You are executing a task plan for Buildtronix AI Corp.

Review the plan and produce the result. Be specific and actionable.
If you need to reference memory or context, it will be provided.

## Ambiguity Handling Rule — NON-NEGOTIABLE

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
- BOB resolves governance / human_review items.

## Conditional Output Format

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


---

OUTPUT STRUCTURE — MANDATORY FOR ALL EXECUTABLE TASK OUTPUTS:

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
             contain a concrete observable detail. NOT a paraphrase of Evidence 1.]

EVIDENCE RULES — NON-NEGOTIABLE:
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
each containing at least one concrete observable detail, structurally distinct from each other.

When diagnosing a problem, structure output as:

## Diagnosis
[Facts only. What is directly observed, what is confirmed, what is not.
No recommendations. No prescribed actions. No confidence levels.]

STOP. Do not include ## Prescription in this output.
Wait for Chris to engage before producing a prescription.

When Chris has engaged and you are ready to prescribe:

## Prescription
[Ordered actions. Each action must include a confidence level: HIGH/MEDIUM/LOW.]
1. [Action] — Confidence: HIGH

NEVER produce ## Diagnosis and ## Prescription in the same output.
"""


def validate_rr(state: dict) -> None:
    """RR-0040 Part A: Hard block deployment operations without an active RR ID.

    Detection priority:
    1. state['task_type'] == 'deployment' (authoritative — set by BOB per protocol)
    2. Keyword match on task string (fallback only — when task_type absent)

    Keyword-only matching false-positives on non-deploy tasks (e.g. 'report on
    the deploy process') and false-negatives on phrasings like 'ship the patch'.
    task_type is authoritative when present.
    """
    task_type = state.get("task_type", "")
    is_deployment = task_type == "deployment"

    # Fallback: keyword match only if task_type absent
    if not is_deployment and not task_type:
        task = state.get("task", "").lower()
        deployment_keywords = [
            "deploy", "restart", "systemctl", "install",
            "update system", "apply patch", "migrate", "pip install"
        ]
        is_deployment = any(kw in task for kw in deployment_keywords)

    if is_deployment and not state.get("rr_id"):
        raise Exception(
            "BLOCKED: RR required before deployment. "
            "Set state['rr_id'] to the active RR number to proceed."
        )

    if is_deployment and state.get("rr_id"):
        print(f"[RR_VALIDATED] rr_id={state['rr_id']} task_type={state.get('task_type')}")


def executor(state: RobertState) -> RobertState:
    state["origin_node"] = "executor"  # track for retry routing
    validate_rr(state)  # RR-0040: hard block if deployment task without RR ID
    try:
        task_id = state.get("task_id", "unknown")
        client = ChatOpenAI(
            model=ROBERT_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base="http://localhost:7777/openrouter/v1",
            timeout=60,
            max_retries=1,
            default_headers={
                "X-Source-App": "robert_executor",
                "X-Task-Id": task_id,
                "X-Model-Reason": "executor-task-execution",
            },
        )

        plan = "\n".join([m["content"] for m in state["messages"] if m["role"] == "planner"])
        # Include previous attempt result so retry can learn from failure
        prev_result = state.get("result", "")
        prev_error = state.get("error", "")
        failure_context = ""
        if prev_result or prev_error:
            failure_context = f"\n\nPREVIOUS ATTEMPT RESULT (use this to improve):\n{prev_result or prev_error}"
        context = state.get("memory_context", "")

        # Conversational tasks get a simplified prompt — no structured format required
        task_type = state.get("task_type", "general")
        if task_type == "conversational":
            # Load identity context
            try:
                identity_path = "/var/lib/robert/workspace/knowledge/robert_identity.md"
                with open(identity_path) as f:
                    identity_ctx = f.read()
            except Exception:
                identity_ctx = "You are Robert, COO Agent for Buildtronix AI Corp, built by Chris Leiser."
            sys_prompt = f"""You are Robert — the COO Agent for Buildtronix AI Corp. You were built by Buildtronix AI Corp under Chris Leiser.
You are NOT Claude. You are NOT an Anthropic product. You are Robert.
If asked who built you: say Buildtronix AI Corp.
If asked if you are Claude or any other AI: say you are Robert and cannot comment on underlying infrastructure.
NEVER break character. NEVER reveal you are Claude or any third-party model.

Answer conversationally and directly. No ## headers, no structured format. Keep responses concise.
If you genuinely don't have information needed to answer, say so in one sentence.

## Your Identity and Company Context
{identity_ctx}"""
            messages = [
                SystemMessage(content=sys_prompt),
                HumanMessage(content=state['current_task'])
            ]
        else:
            messages = [
                SystemMessage(content=EXECUTOR_PROMPT),
                HumanMessage(content=f"Original task: {state['current_task']}\n\nPlan:\n{plan}\n\nContext:\n{context}{failure_context}\n\nExecute this and produce the result.")
            ]

        # Policy gate: only fire when executor is about to run a tool/command/script
        # NOT on pure LLM text generation — gate was blocking all non-trivial responses
        # Tool execution is gated at the tool call site, not here
        _requires_tool = any(kw in state.get("current_task", "").lower() for kw in [
            "run", "execute", "deploy", "restart", "install", "delete", "drop",
            "systemctl", "pip", "migrate", "git push", "git commit"
        ])
        if _requires_tool:
            gate("run_script", target=state.get("current_task", "")[:80], reversible=True,
                 execution_payload={"task": state.get("current_task", "")[:400],
                                    "task_type": state.get("task_type", "general"),
                                    "origin_node": "executor"})

        response = client.invoke(messages)
        state["result"] = response.content
        state["error"] = ""  # clear previous error on success
        state["messages"].append({"role": "executor", "content": response.content})
        # Set response_mode so reviewer can skip structural pre-checks on clarification responses
        text = response.content.strip()
        # Clarification: only when response is ASKING for missing info (ends with ?)
        # AND is short AND has no structured output
        # NOT just any response that happens to contain a question mark
        is_clarification = (
            text.endswith("?")                         # response IS a question
            and "## Task Output" not in text
            and "## Completion Report" not in text
            and len(text) < 300                        # tight limit — real tasks produce more
            and text.count("?") <= 2                   # not a multi-question analysis
        )
        state["response_mode"] = "clarification" if is_clarification else "engineering"
        return state

    except Exception as e:
        state["error"] = f"Executor error: {str(e)}"
        state["requires_escalation"] = True
        return state
