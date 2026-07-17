"""Bill node - Finance CFO specialist for Robert."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from state import RobertState
from config import ROBERT_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from policy_gate import gate
# Bill uses Sonnet — financial analysis, wrong numbers = unacceptable


BILL_PROMPT = """You are Bill, the CFO AI agent for Buildtronix AI Corp. You handle all financial analysis, P&L, budgets, and calculations.

Be precise with numbers. Show your work. Flag any anomalies.
Format financial data in clean tables when appropriate.
Always provide actionable insights, not just raw numbers.

---

OUTPUT STRUCTURE — MANDATORY FOR ALL EXECUTABLE OUTPUTS:

Every response MUST contain BOTH sections below, exactly as formatted.
Missing either section or missing Evidence fields = automatic RETRY by reviewer.

## Task Output
[The actual deliverable: financial analysis, P&L, budget, recommendations]

## Completion Report
Action taken: [One sentence — exactly what you did]
Evidence 1: [Must contain at least one concrete observable detail: a filename, number,
             command, quoted output, file path, identifier, metric, URL, timestamp,
             or service name. NOT a placeholder. NOT generic prose. Example: "P&L total
             revenue: $1,250,000 (per Q3 2026 statement)"]
Evidence 2: [A structurally different fact from Evidence 1 — where E1 cites a source
             or artifact, E2 cites a finding or value (or vice versa). Must also
             contain a concrete observable detail. Example: "Variance analysis shows
             COGS overrun of $180K vs. budget"]

EVIDENCE RULES — NON-NEGOTIABLE:
- Evidence 1 and Evidence 2 MUST be present and substantive in EVERY executable response
- Each must contain at least one: filename, number, command, path, quoted string,
  identifier, metric, timestamp, URL, or named artifact
- NEVER write: N/A, None, Pending, TBD, "analysis completed", "numbers calculated",
  "task completed", "financial analysis performed", or any generic completion phrase
- Evidence 1 and Evidence 2 must be structurally distinct — not paraphrases of each other
- For financial outputs: E1 might cite specific line items with values, E2 might cite
  variances, trends, or anomalies

Examples:
  BAD:  Evidence 1: Financial analysis was performed.
  GOOD: Evidence 1: Total project cost variance: -$145,200 vs. 2026-Q3 forecast

  BAD:  Evidence 2: Numbers checked.
  GOOD: Evidence 2: Labor cost breakdown shows 28% Davis-Bacon impact on subs ($85K)
"""


def bill(state: RobertState) -> RobertState:
    state["origin_node"] = "bill"  # track for retry routing
    try:
        client = ChatOpenAI(
            model=ROBERT_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base=OPENROUTER_BASE_URL,
            timeout=60,
            max_retries=1,
        )

        task = state["current_task"]
        context = state.get("memory_context", "")

        # Policy gate: financial analysis — internal, reversible
        gate("run_script", target=f"finance:{task[:60]}", data_sensitivity="internal", reversible=True,
             execution_payload={"task": task[:400], "task_type": "finance", "origin_node": "bill"})
        # Include previous attempt so Bill can learn from it
        prev_result = state.get("result", "")
        failure_context = f"\n\nPREVIOUS ATTEMPT (improve on this):\n{prev_result}" if prev_result else ""

        messages = [
            SystemMessage(content=BILL_PROMPT),
            HumanMessage(content=f"Task: {task}\n\nContext:\n{context}{failure_context}")
        ]

        response = client.invoke(messages)
        state["result"] = response.content
        state["error"] = ""
        state["messages"].append({"role": "bill", "content": response.content})
        return state

    except Exception as e:
        state["error"] = f"Bill error: {str(e)}"
        state["requires_escalation"] = True
        return state
