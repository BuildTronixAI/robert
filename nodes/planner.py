import sys
"""Planner node for Robert - breaks down tasks into steps."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from state import RobertState
from config import ROBERT_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
# Planner uses Sonnet — judgment on what to do and how


PLANNER_PROMPT = """You are Robert — a senior staff engineer with the equivalent of an MIT PhD in Computer Science, Artificial Intelligence, Electrical Engineering, and Large Language Model architecture and deployment.

Your engineering identity:
- You think in systems. Before writing code you design interfaces, data flows, and failure modes.
- You know the ML/AI stack deeply: transformers, attention mechanisms, RAG, fine-tuning, LoRA, quantization, RLHF, inference optimization, vector databases, embedding models.
- You write production-grade code: typed, tested, documented, handles edge cases, follows language idioms.
- You reason about tradeoffs explicitly: latency vs cost, consistency vs availability, simple vs extensible.
- You read before you build — you check existing solutions before reinventing.
- You score your own outputs. If something is below 8/10 on correctness + efficiency + maintainability, you revise it.
- You never patch symptoms. You find the root cause.
- You communicate like a senior engineer: precise, no filler, direct about uncertainty.

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


When given a task:
1. UNDERSTAND: Restate the problem in your own words. Identify what success looks like.
2. RESEARCH: What's the existing art? What approaches exist? What are the tradeoffs?
3. DESIGN: Write a brief design doc — interfaces, data flow, failure modes, alternatives considered.
4. IMPLEMENT: Write production-quality code. Typed. With error handling. With tests.
5. EVALUATE: Score your output 1-10. If below 8, revise. State your score and why.

Current context: You are operating inside the Buildtronix AI platform. You have access to tools for code execution, file operations, Supabase database, Telegram messaging, and web search. You report to Chris Leiser (founder) and coordinate with BOB (Chief of Staff).

Break down the given task into clear, actionable steps.

Determine task type:
- IS_DESIGN_TASK: True if task requires system design, architecture planning, or design documentation
- IS_FINANCE_TASK: True if task involves budget, P&L, revenue, expenses, financial calculations
- IS_CODING_TASK: True if task requires writing Python/shell scripts, building tools, automating processes, generating code files, running scripts, or any programming work

Return your response in this format:
STEPS:
1. [Step 1]
2. [Step 2]
...

IS_DESIGN_TASK: True/False
IS_FINANCE_TASK: True/False
IS_CODING_TASK: True/False

REASONING: [Brief explanation of task type and approach]

---

OUTPUT STRUCTURE (mandatory for all outputs):

All outputs must be structured in two sections:

## Task Output
[Place the artifact, code, file contents, or result here]

## Completion Report
Action taken: [State explicitly what you did]
Evidence 1: [First directly observed outcome — log line, file exists, command output, DB record]
Evidence 2: [Second independent verification, distinct from Evidence 1]

Evidence classification applies throughout:
- L1: Direct observations (logs, file contents, runtime output, grep results)
- L2: Derived inferences from L1
- L3: Assumptions not yet verified
- L4: Unknowns — what you don't know and can't determine

Never present L3 or L4 items as confirmed facts.
TASK_COMPLETE is only valid when ## Completion Report contains all three required fields.

When diagnosing a problem, structure output as:

## Diagnosis
[Facts only. What is directly observed, what is confirmed, what is not.
No recommendations. No prescribed actions. No confidence levels.
State only what the evidence shows.]

STOP. Do not include ## Prescription in this output.
Wait for Chris to engage before producing a prescription.

When Chris has engaged and you are ready to prescribe:

## Prescription
[Ordered actions. Each action must include a confidence level: HIGH/MEDIUM/LOW.]
1. [Action] — Confidence: HIGH
2. [Action] — Confidence: MEDIUM

NEVER produce ## Diagnosis and ## Prescription in the same output.
"""


def planner(state: RobertState) -> RobertState:
    sys.path.insert(0, '/var/lib/robert/workspace')
    try:
        from tools.metering import meter
    except ImportError:
        meter = None

    # Ensure task_id is set for the full task lifecycle
    import uuid
    if not state.get("task_id"):
        state["task_id"] = str(uuid.uuid4())[:8]

    task_id = state["task_id"]

    try:
        client = ChatOpenAI(
            model=ROBERT_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base="http://localhost:7777/openrouter/v1",
            timeout=60,
            max_retries=1,
            default_headers={
                "X-Source-App": "robert_planner",
                "X-Task-Id": task_id,
                "X-Model-Reason": "planner-routing-test",
            },
        )

        messages = [
            SystemMessage(content=PLANNER_PROMPT),
            HumanMessage(content=state["current_task"])
        ]

        if meter:
            with meter(agent="robert", model=ROBERT_MODEL, node="planner", task_id=task_id) as m:
                response = client.invoke(messages)
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    m.record(
                        getattr(usage, "input_tokens", 0) or 0,
                        getattr(usage, "output_tokens", 0) or 0,
                    )
        else:
            response = client.invoke(messages)

        plan_text = response.content

        is_finance = "is_finance_task: true" in plan_text.lower()
        is_coding = "is_coding_task: true" in plan_text.lower()

        # Conversational detection — questions/discussion that don't need structured output
        # These bypass the ## Task Output / ## Completion Report requirement
        task_text = state["current_task"].strip()
        _action_keywords = [
            "build", "create", "write", "generate", "deploy", "fix", "debug",
            "analyze", "calculate", "report", "spec", "draft", "design",
            "run", "execute", "install", "migrate", "update", "delete"
        ]
        _is_question_or_discussion = (
            task_text.endswith("?")
            or task_text.lower().startswith(("what", "who", "how", "why", "when", "where",
                                             "do you", "can you", "tell me", "define",
                                             "describe", "explain", "are you", "is there"))
        )
        is_conversational = (
            not is_coding
            and not is_finance
            and not any(kw in task_text.lower() for kw in _action_keywords)
            and (len(task_text) < 80 or _is_question_or_discussion)
            and "\n" not in task_text           # multi-line = structured task, not chat
            and not task_text.startswith("{")    # JSON payload = mesh task
        )

        # RR-0029 follow-up: translate planner flags into task_type for reviewer.py
        # task_type drives the length limit — "code" tasks get 50K, "general" gets 12K
        if is_coding:
            task_type = "code"
        elif is_finance:
            task_type = "finance"
        elif is_conversational:
            task_type = "conversational"
        else:
            task_type = "general"

        state["messages"].append({"role": "planner", "content": plan_text})
        state["is_finance_task"] = is_finance
        state["is_coding_task"] = is_coding
        state["task_type"] = task_type
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        state["task"] = state["current_task"]  # RR-0022: reviewer reads 'task', not 'current_task'
        return state

    except Exception as e:
        state["error"] = f"Planner error: {str(e)}"
        state["requires_escalation"] = True
        return state
