"""Executor node for Robert - executes plans."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from state import RobertState
from config import ROBERT_EXEC_MODEL as ROBERT_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from policy_gate import gate
from gateway_prompt import (
    MessageKind,
    assert_payload_roles,
    build_chat_user_message,
    build_context_block,
    build_system_prompt,
    build_user_message,
    format_conversation_history,
)


# Back-compat alias — tests / imports that reference EXECUTOR_PROMPT
EXECUTOR_PROMPT = build_system_prompt("TASK")


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


def _message_kind(state: RobertState) -> MessageKind:
    kind = (state.get("message_kind") or "").upper()
    if kind in ("CHAT", "TASK"):
        return kind  # type: ignore[return-value]
    if state.get("task_type") == "conversational":
        return "CHAT"
    return "TASK"


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
            failure_context = f"PREVIOUS ATTEMPT RESULT (use this to improve):\n{prev_result or prev_error}"
        memory_context = state.get("memory_context", "")
        history = format_conversation_history(state.get("conversation_history") or [])
        context_block = build_context_block(
            memory_context,
            conversation_history=history,
            extra=failure_context,
        )

        kind = _message_kind(state)
        if kind == "CHAT":
            system = build_system_prompt("CHAT", include_identity_doc=True)
            user = build_chat_user_message(
                message=state["current_task"],
                context_block=context_block,
            )
        else:
            system = build_system_prompt("TASK")
            user = build_user_message(
                original_task=state["current_task"],
                plan=plan,
                context_block=context_block,
            )

        assert_payload_roles(system, user)
        print(
            f"[executor] outbound roles kind={kind} system_len={len(system)} "
            f"user_len={len(user)} datetime_in_user={'current_datetime:' in user}"
        )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user),
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
            kind != "CHAT"
            and text.endswith("?")                         # response IS a question
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
