"""
Initiative 1, Step 1.2 — LLM Call Metering
Context-manager based. Every LLM call wrapped with `meter()` writes a row to llm_usage.
Pricing fetched from model_pricing table, cached hourly.
"""

import os
import time
import json
import urllib.request
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# In-memory pricing cache, refreshed hourly
_pricing_cache = {}
_pricing_cache_fetched_at = 0.0


def _fetch_pricing():
    global _pricing_cache, _pricing_cache_fetched_at
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/model_pricing?select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            }
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            rows = json.loads(r.read())
            _pricing_cache = {row["model"]: row for row in rows}
            _pricing_cache_fetched_at = time.time()
    except Exception as e:
        print(f"[meter] pricing fetch failed: {e}")


def _get_pricing(model: str) -> dict:
    if time.time() - _pricing_cache_fetched_at > 3600:
        _fetch_pricing()
    return _pricing_cache.get(model)


def compute_cost(model: str, input_tokens: int, output_tokens: int,
                 cache_read: int = 0, cache_write: int = 0) -> float | None:
    p = _get_pricing(model)
    if not p:
        return None
    cost = (
        (input_tokens / 1_000_000) * float(p["input_per_m_usd"])
        + (output_tokens / 1_000_000) * float(p["output_per_m_usd"])
        + (cache_read / 1_000_000) * float(p.get("cache_read_per_m_usd") or 0)
        + (cache_write / 1_000_000) * float(p.get("cache_write_per_m_usd") or 0)
    )
    return round(cost, 6)


def log_llm_usage(
    agent: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    node: str = None,
    task_id: str = None,
    customer_id: str = "ams",
    latency_ms: int = None,
    cache_read: int = 0,
    cache_write: int = 0,
    success: bool = True,
    error_code: str = None,
):
    """Write one row to llm_usage. Fire-and-forget — never raises."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    cost = compute_cost(model, input_tokens, output_tokens, cache_read, cache_write)

    row = {
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "customer_id": customer_id,
        "agent": agent,
        "node": node,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
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
        print(f"[meter] log failed: {e}")


class _Recorder:
    def __init__(self):
        self.input = 0
        self.output = 0
        self.cache_r = 0
        self.cache_w = 0
        self.success = True
        self.error = None

    def record(self, inp: int, out: int, cache_read: int = 0, cache_write: int = 0):
        self.input = inp
        self.output = out
        self.cache_r = cache_read
        self.cache_w = cache_write


@contextmanager
def meter(agent: str, model: str, node: str = None, task_id: str = None,
          customer_id: str = "ams"):
    """
    Context manager for metering LLM calls.

    Usage:
        with meter(agent='robert', model=PLANNER_MODEL, node='planner', task_id=tid) as m:
            resp = client.invoke(messages)
            usage = resp.usage_metadata
            m.record(usage.input_tokens, usage.output_tokens)
    """
    start = time.time()
    rec = _Recorder()
    try:
        yield rec
    except Exception as e:
        rec.success = False
        rec.error = type(e).__name__
        raise
    finally:
        latency_ms = int((time.time() - start) * 1000)
        log_llm_usage(
            agent=agent,
            model=model,
            node=node,
            task_id=task_id,
            customer_id=customer_id,
            input_tokens=rec.input,
            output_tokens=rec.output,
            cache_read=rec.cache_r,
            cache_write=rec.cache_w,
            latency_ms=latency_ms,
            success=rec.success,
            error_code=rec.error,
        )
