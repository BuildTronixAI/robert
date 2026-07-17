"""
LLM Usage Metering — Task 6
Logs every LLM call to Supabase llm_usage table.
Import and wrap every client.invoke() call.
"""

import os
import time
import urllib.request
import urllib.error
import json
import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Model pricing (USD per million tokens)
MODEL_PRICING = {
    "anthropic/claude-sonnet-4-6": (3.00, 15.00),
    "anthropic/claude-haiku-4-5":  (0.80,  4.00),
    "claude-sonnet-4-6":           (3.00, 15.00),
    "claude-haiku-4-5":            (0.80,  4.00),
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, (3.00, 15.00))
    return round((input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000, 6)


def log_llm_usage(
    agent: str,
    node: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int = None,
    task_id: str = None,
    customer_id: str = "ams",
    success: bool = True,
    error_code: str = None,
):
    """Log one LLM call to Supabase. Fire-and-forget — never raises."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    cost = compute_cost(model, input_tokens, output_tokens)

    row = {
        "occurred_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "customer_id": customer_id,
        "agent": agent,
        "node": node,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost,
        "task_id": task_id,
        "success": success,
        "error_code": error_code,
    }

    try:
        data = json.dumps(row).encode()
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/llm_usage",
            data=data,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        # Never let metering break the main flow
        print(f"[meter] log failed: {e}")


def timed_llm_call(fn, agent: str, node: str, model: str, task_id: str = None, customer_id: str = "ams"):
    """
    Wrapper: call fn(), capture tokens + latency, log usage.
    Usage:
        response = timed_llm_call(lambda: client.invoke(messages), 'robert', 'planner', PLANNER_MODEL)
    """
    start = time.time()
    try:
        response = fn()
        latency_ms = int((time.time() - start) * 1000)
        usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
        input_tokens  = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
        log_llm_usage(
            agent=agent, node=node, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=latency_ms, task_id=task_id,
            customer_id=customer_id, success=True,
        )
        return response
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        log_llm_usage(
            agent=agent, node=node, model=model,
            input_tokens=0, output_tokens=0,
            latency_ms=latency_ms, task_id=task_id,
            customer_id=customer_id, success=False,
            error_code=type(e).__name__,
        )
        raise
