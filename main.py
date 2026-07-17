"""Main entry point for Robert COO Agent."""

import sys

from graph import graph
from state import RobertState
from tools.memory import read_memory
from tools.telegram import send_telegram


def run_task(task: str, context: str = "", notify: bool = True, chat_id: str = "default") -> dict:
    """Run a task through Robert's graph."""
    if not context:
        try:
            # Load only the engineering KB — not the full MEMORY.md (too large)
            context = read_memory("/var/lib/robert/workspace/knowledge/engineering_kb.md")
        except:
            context = "Buildtronix AI platform — construction project management SaaS. Modules: Pre-Con, PM, Finance, Field Ops, Service Ops. Stack: Next.js, Supabase, Vercel, Python agents."

    initial_state = RobertState(
        # Core task
        current_task=task,
        task="",              # set by planner (alias for current_task)
        task_id="",           # set by planner
        task_type="general",  # set by planner
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
    )

    # Persistent thread per Telegram chat — enables multi-turn memory
    # chat_id comes from the Telegram update; group chats share one thread
    thread_id = f"tg_{chat_id}"
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial_state, config=config)
    # RR-0032 diagnostic: observe what state graph.invoke() returns
    print(f"[GRAPH invoke_return] needs_revision={result.get('needs_revision')} requires_escalation={result.get('requires_escalation')} iteration_count={result.get('iteration_count')} result_len={len(result.get('result','') or '')}")

    # RR-0032 Option A: if graph exits with needs_revision=True and under max iterations,
    # re-invoke on the same thread to continue the RETRY loop internally.
    # This compensates for SqliteSaver treating reviewer output as terminal state.
    # Observable risk: if re-invoke re-runs planner, iteration_count will jump unexpectedly.
    _retry_count = 0
    while (
        result.get("needs_revision", False)
        and not result.get("requires_escalation", False)
        and result.get("iteration_count", 0) < 3
        and _retry_count < 3  # hard safety cap
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
        send_telegram(msg)

    # RR-0059-rev7 compat: inject reply_status for listener protocol gate
    if isinstance(result, dict) and 'reply_status' not in result:
        if result.get('requires_escalation'):
            result['reply_status'] = 'FAILURE'
        elif result.get('result'):
            result['reply_status'] = 'SUCCESS_REPLY'
        else:
            result['reply_status'] = 'SUCCESS_NO_REPLY'
    return result


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
