"""
Dead Letter Queue — D11
Failed tasks go here instead of vanishing.
Poller retries up to max_retries with exponential backoff.
Dead tasks require manual resolution by Chris.
"""

import os
import json
import time
import urllib.request
from datetime import datetime, timezone
from policy_engine import check_kill_switch

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def _sb_request(method: str, path: str, data: dict = None) -> dict:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()) if r.read else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Supabase {method} {path} failed: {e.code} {body}")


def enqueue(
    agent: str,
    operation: str,
    payload: dict,
    task_id: str = None,
    error_message: str = None,
    error_type: str = "unknown",
    max_retries: int = 3,
) -> str:
    """Push a failed task to the DLQ. Returns the DLQ row id."""
    check_kill_switch()
    row = {
        "agent": agent,
        "task_id": task_id,
        "operation": operation,
        "payload": payload,
        "error_message": error_message,
        "error_type": error_type,
        "max_retries": max_retries,
        "status": "pending",
    }
    result = _sb_request("POST", "dlq", row)
    dlq_id = result[0]["id"] if isinstance(result, list) else result.get("id")
    print(f"[DLQ] Enqueued {operation} for agent={agent} task_id={task_id} → dlq_id={dlq_id}")
    return dlq_id


def mark_resolved(dlq_id: int, resolved_by: str = "system", note: str = ""):
    """Mark a DLQ item as manually resolved."""
    _sb_request("PATCH", f"dlq?id=eq.{dlq_id}", {
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolved_by": resolved_by,
        "resolution_note": note,
    })
    print(f"[DLQ] Resolved dlq_id={dlq_id} by {resolved_by}")


def get_pending(limit: int = 10) -> list:
    """Fetch pending DLQ items for retry."""
    result = _sb_request(
        "GET",
        f"dlq?status=eq.pending&order=created_at.asc&limit={limit}",
    )
    return result if isinstance(result, list) else []


def retry_with_backoff(dlq_id: int, retry_fn, *args, **kwargs):
    """
    Attempt retry of a DLQ item. Marks dead after max_retries.
    Uses exponential backoff: 2^retry_count seconds (max 60s).
    """
    check_kill_switch()

    items = _sb_request("GET", f"dlq?id=eq.{dlq_id}")
    if not items:
        raise ValueError(f"DLQ item {dlq_id} not found")

    item = items[0]
    retry_count = item["retry_count"] + 1
    max_retries = item["max_retries"]

    if retry_count > max_retries:
        _sb_request("PATCH", f"dlq?id=eq.{dlq_id}", {"status": "dead"})
        print(f"[DLQ] dlq_id={dlq_id} marked DEAD after {max_retries} retries. Manual intervention required.")
        return None

    # Exponential backoff
    wait = min(2 ** (retry_count - 1), 60)
    print(f"[DLQ] Retrying dlq_id={dlq_id} (attempt {retry_count}/{max_retries}) after {wait}s backoff")
    time.sleep(wait)

    _sb_request("PATCH", f"dlq?id=eq.{dlq_id}", {
        "status": "retrying",
        "retry_count": retry_count,
        "last_attempted_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        result = retry_fn(*args, **kwargs)
        mark_resolved(dlq_id, resolved_by="auto_retry", note=f"Resolved on retry {retry_count}")
        return result
    except Exception as e:
        error_msg = str(e)
        next_status = "dead" if retry_count >= max_retries else "pending"
        _sb_request("PATCH", f"dlq?id=eq.{dlq_id}", {
            "status": next_status,
            "error_message": error_msg,
            "retry_count": retry_count,
        })
        if next_status == "dead":
            print(f"[DLQ] dlq_id={dlq_id} DEAD: {error_msg}")
        else:
            print(f"[DLQ] dlq_id={dlq_id} retry failed ({retry_count}/{max_retries}): {error_msg}")
        raise
