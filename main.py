"""Main entry point for Robert COO Agent."""

import os
import sys

from graph import graph
from state import RobertState
from config import MAX_ITERATIONS, WORKSPACE_PATH
from tools.telegram import send_telegram


def _load_default_context() -> str:
    """Load engineering KB from workspace; never use absolute escape paths via memory tool."""
    kb_path = os.path.join(WORKSPACE_PATH, "knowledge", "engineering_kb.md")
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        # Fallback relative to this package (repo checkout)
        local_kb = os.path.join(os.path.dirname(__file__), "knowledge", "engineering_kb.md")
        try:
            with open(local_kb, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return (
                "Buildtronix AI platform — construction project management SaaS. "
                "Modules: Pre-Con, PM, Finance, Field Ops, Service Ops. "
                "Stack: Next.js, Supabase, Vercel, Python agents. Protocol: TronixMesh."
            )


def run_task(
    task: str,
    context: str = "",
    notify: bool = True,
    chat_id: str = "default",
    *,
    actor_user_id: str = "",
    actor_role: str = "",
    actor_jwt: str = "",
) -> dict:
    """Run a task through Robert's graph."""
    if not task or not str(task).strip():
        return {
            "result": "",
            "error": "Empty task",
            "requires_escalation": True,
            "needs_revision": False,
            "iteration_count": 0,
            "reply_status": "FAILURE",
        }

    if not context:
        context = _load_default_context()

    # FIX 4 — classify before graph so CHAT skips structured validator path
    from gateway_prompt import classify_inbound
    message_kind = classify_inbound(task)

    # FIX 5 — last N Telegram turns for this chat (identity-break filtered at format time)
    conversation_history: list = []
    try:
        import memory_store as _mem
        conversation_history = _mem.get_conversation_history(str(chat_id), max_turns=8)
    except Exception as hist_err:
        print(f"[main] conversation history unavailable: {hist_err}", flush=True)

    # Bind actor JWT/role for RLS-scoped tools for the duration of this invoke.
    from tools.actor_context import set_actor, reset_actor
    _actor_token = set_actor(
        user_id=actor_user_id or "",
        role=actor_role or "",
        jwt=actor_jwt or "",
        chat_id=str(chat_id),
    )

    initial_state = RobertState(
        # Core task
        current_task=task,
        task="",              # set by planner (alias for current_task)
        task_id="",           # set by planner
        task_type="conversational" if message_kind == "CHAT" else "general",
        memory_context=context,
        # Routing
        is_finance_task=False,
        is_coding_task=False,
        origin_node="executor",
        iteration_count=0,
        requires_escalation=False,
        needs_revision=False,
        needs_redesign=False,
        revision_notes="",
        escalate_reason="",
        # Outputs
        result="",
        error="",
        messages=[],
        # Quality
        quality_approved=False,
        quality_scores={},
        # Workflow
        pending_approvals=[],
        active_workflows=[],
        # Architect/coder pipeline
        context="",
        steps=[],
        design_doc="",
        test_file="",
        tests_generated=False,
        test_results={},
        # Response mode (set by executor — clarification vs engineering)
        response_mode="engineering",
        # Actor context from listener identity mint
        actor_user_id=actor_user_id or "",
        actor_role=actor_role or "",
        actor_jwt=actor_jwt or "",
        telegram_chat_id=str(chat_id),
        message_kind=message_kind,
        conversation_history=conversation_history,
    )

    # Persistent thread per Telegram chat — enables multi-turn memory
    # chat_id comes from the Telegram update; group chats share one thread
    thread_id = f"tg_{chat_id}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = graph.invoke(initial_state, config=config)
        # RR-0032 diagnostic: observe what state graph.invoke() returns
        print(f"[GRAPH invoke_return] needs_revision={result.get('needs_revision')} requires_escalation={result.get('requires_escalation')} iteration_count={result.get('iteration_count')} result_len={len(result.get('result','') or '')}")

        # RR-0032 Option A: if graph exits with needs_revision=True and under max iterations,
        # re-invoke on the same thread to continue the RETRY loop internally.
        # This compensates for SqliteSaver treating reviewer output as terminal state.
        _retry_count = 0
        while (
            result.get("needs_revision", False)
            and not result.get("requires_escalation", False)
            and result.get("iteration_count", 0) < MAX_ITERATIONS
            and _retry_count < MAX_ITERATIONS  # hard safety cap
        ):
            _retry_count += 1
            print(f"[GRAPH Option-A retry] re-invoking graph, retry={_retry_count}, iter={result.get('iteration_count')}")
            result = graph.invoke(result, config=config)
            print(f"[GRAPH Option-A result] needs_revision={result.get('needs_revision')} iteration_count={result.get('iteration_count')} result_len={len(result.get('result','') or '')}")

        # Send result to Chris via Telegram
        if notify and result.get("result"):
            import re
            task_short = task[:80] + "..." if len(task) > 80 else task
            # Strip markdown that breaks Telegram parse
            result_clean = re.sub(r'[*_`#\[\]\(\)]', '', result['result'][:3000])
            task_clean = re.sub(r'[*_`#\[\]\(\)]', '', task_short)
            msg = f"Robert - Task Complete\n\nTask: {task_clean}\n\n{result_clean}"
            if result.get("requires_escalation"):
                msg += "\n\nNeeds your attention."
            send_telegram(msg, skip_gate=True)  # listener/notify path — already authorized

        # RR-0059-rev7 compat: inject reply_status for listener protocol gate
        if isinstance(result, dict) and 'reply_status' not in result:
            if result.get('requires_escalation'):
                result['reply_status'] = 'FAILURE'
            elif result.get('result'):
                result['reply_status'] = 'SUCCESS_REPLY'
            else:
                result['reply_status'] = 'SUCCESS_NO_REPLY'
        return result
    finally:
        reset_actor(_actor_token)


def main():
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        task = input("Enter task for Robert: ").strip()

    if not task:
        print("No task provided.")
        sys.exit(1)

    print(f"\nRobert processing: {task}\n")
    result = run_task(task)

    print("\n=== RESULT ===")
    print(result.get("result", "No result generated"))

    if result.get("error"):
        print(f"\nError: {result['error']}")

    print(f"\nIterations: {result.get('iteration_count', 0)}")
    print(f"Escalated: {result.get('requires_escalation', False)}")


if __name__ == "__main__":
    main()
