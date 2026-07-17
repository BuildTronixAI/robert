"""LangGraph definition for Robert — v2 PhD Engineer upgrade.

Graph flow:
  Engineering tasks: planner → architect → coder → reviewer
  Finance tasks:     planner → bill → reviewer
  Operational tasks: planner → executor → reviewer
"""

import os
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver
from state import RobertState
from nodes import planner, executor, reviewer, bill
from nodes.coder import coder
from nodes.architect import architect_node
from config import MAX_ITERATIONS, WORKSPACE_PATH

CHECKPOINT_DB = os.environ.get(
    "ROBERT_CHECKPOINT_DB",
    os.path.join(WORKSPACE_PATH, "robert_checkpoints.db"),
)
# Loud degraded mode when durable checkpoints are unavailable
ALLOW_MEMORY_CHECKPOINTER = os.environ.get("ROBERT_ALLOW_MEMORY_CHECKPOINTER", "false").lower() == "true"


def route_after_planner(state: RobertState) -> str:
    """Route to appropriate execution node based on task type."""
    if state.get("is_finance_task", False):
        return "bill"
    if state.get("is_coding_task", False) or state.get("task_type") in ["code", "design", "architecture", "system"]:
        return "architect"  # Engineering tasks go through architect first
    return "executor"


def route_after_architect(state: RobertState) -> str:
    """After architecture review, always go to coder."""
    return "coder"


def route_after_review(state: RobertState) -> str:
    """Route based on review outcome.
    - Engineering: coder-first retry. If needs_redesign=True, escalate back to architect.
    - Financial: bill retry.
    - Operational: executor retry.
    - Max 3 iterations then END.
    """
    # RR-0032 diagnostic logging: observe actual routing decisions
    iteration = state.get("iteration_count", 0)
    needs_revision = state.get("needs_revision", False)
    requires_escalation = state.get("requires_escalation", False)
    origin = state.get("origin_node", "executor")
    needs_redesign = state.get("needs_redesign", False)
    print(f"[GRAPH route_after_review] iter={iteration} needs_revision={needs_revision} requires_escalation={requires_escalation} origin={origin} needs_redesign={needs_redesign}")

    if iteration >= MAX_ITERATIONS:
        print(f"[GRAPH route_after_review] -> END (max iterations={MAX_ITERATIONS})")
        return END
    if requires_escalation and not needs_revision:
        print(f"[GRAPH route_after_review] -> END (requires_escalation)")
        return END
    if needs_revision:
        if origin in ("coder", "architect"):
            if needs_redesign:
                print(f"[GRAPH route_after_review] -> architect (needs_redesign)")
                return "architect"
            print(f"[GRAPH route_after_review] -> coder (needs_revision, origin={origin})")
            return "coder"
        if origin == "bill":
            print(f"[GRAPH route_after_review] -> bill (needs_revision)")
            return "bill"
        print(f"[GRAPH route_after_review] -> executor (needs_revision, origin={origin})")
        return "executor"
    print(f"[GRAPH route_after_review] -> END (clean completion)")
    return END


def build_graph():
    """Build and return the Robert v2 execution graph."""

    graph = StateGraph(RobertState)

    # Add nodes
    graph.add_node("planner", planner)
    graph.add_node("architect", architect_node)  # NEW — design before code
    graph.add_node("executor", executor)
    graph.add_node("coder", coder)
    graph.add_node("bill", bill)
    graph.add_node("reviewer", reviewer)

    # Edges
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_after_planner)

    # Engineering path: architect → coder → reviewer
    graph.add_conditional_edges("architect", route_after_architect)
    graph.add_edge("coder", "reviewer")

    # Other paths
    graph.add_edge("bill", "reviewer")
    graph.add_edge("executor", "reviewer")

    graph.add_conditional_edges("reviewer", route_after_review)

    try:
        import sqlite3
        from pathlib import Path
        Path(CHECKPOINT_DB).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        try:
            checkpointer.setup()  # Idempotent — CREATE TABLE IF NOT EXISTS
            print(f"[Robert] SqliteSaver initialized at {CHECKPOINT_DB}")
        except sqlite3.Error as setup_err:
            print(f"[Robert] CRITICAL: Checkpointer setup failed: {setup_err}")
            # Alert directly via Telegram API — avoids circular import with listener
            try:
                import urllib.request, json as _json
                from config import ROBERT_BOT_TOKEN, TELEGRAM_CHAT_ID
                _payload = _json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": f"⚠️ ROBERT ALERT: startup failed: checkpointer setup error: {setup_err}"}).encode()
                _req = urllib.request.Request(f"https://api.telegram.org/bot{ROBERT_BOT_TOKEN}/sendMessage", data=_payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(_req, timeout=10)
            except Exception:
                pass
            raise
    except sqlite3.Error as e:
        if not ALLOW_MEMORY_CHECKPOINTER:
            print(f"[Robert] CRITICAL: Sqlite checkpointer failed ({e}) — refusing MemorySaver fallback")
            raise
        print(f"[Robert] WARNING: Sqlite checkpointer failed ({e}), falling back to MemorySaver (degraded)")
        checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Compile and expose the graph
graph = build_graph()
