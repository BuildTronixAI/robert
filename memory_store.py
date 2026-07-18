"""
Robert Persistent Memory Store — Phase 3
Robert's own memory, separate from BOB's.
Tracks: completed tasks, learned context, active workflows, task queue.

Hardening:
- fcntl file lock around load-modify-save
- Corrupt memory files are quarantined, not silently overwritten forever
- Telegram offset updates are atomic with other memory mutations
"""

import json
import os
import sys
import datetime
import fcntl
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import atomic_write, backup_before_write, BACKUP_DIR_ROBERT, CRITICAL_FILES, CRITICAL_RETENTION_DAYS, STANDARD_RETENTION_DAYS  # RR-0013 + RR-0014

ROBERT_MEMORY_PATH = os.environ.get(
    "ROBERT_MEMORY_PATH",
    "/var/lib/robert/workspace/robert_memory.json",
)
_LOCK_PATH = ROBERT_MEMORY_PATH + ".lock"

DEFAULT_MEMORY = {
    "task_queue": [],           # Pending tasks to work through
    "completed_tasks": [],      # Last 50 completed tasks
    "learned_context": {},      # Key facts Robert has learned
    "active_workflows": [],     # Currently running multi-step workflows
    "last_updated": None,
    "session_count": 0,
    "telegram_offset": 0,       # Last Telegram update ID processed
    "conversation_history": {}, # chat_id -> [{role, content, ts}] last N turns
}

# Max turns retained per Telegram chat (Fix 5 — 6–10 window)
_MAX_CHAT_TURNS = 10


@contextmanager
def _memory_lock():
    """Exclusive lock for memory mutations across processes."""
    os.makedirs(os.path.dirname(os.path.abspath(_LOCK_PATH)) or ".", exist_ok=True)
    fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _quarantine_corrupt(path: str, err: Exception) -> None:
    """Move a corrupt memory file aside so it is not repeatedly clobbered."""
    try:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = f"{path}.corrupt.{stamp}"
        os.rename(path, dest)
        print(f"[memory_store] Quarantined corrupt memory to {dest}: {err}", flush=True)
    except OSError as move_err:
        print(f"[memory_store] Failed to quarantine corrupt memory: {move_err}", flush=True)


def _load_unlocked() -> dict:
    """Load Robert's memory from disk (caller must hold lock for mutations)."""
    if not os.path.exists(ROBERT_MEMORY_PATH):
        return DEFAULT_MEMORY.copy()
    try:
        with open(ROBERT_MEMORY_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("memory root must be a JSON object")
        for k, v in DEFAULT_MEMORY.items():
            if k not in data:
                data[k] = v if not isinstance(v, (dict, list)) else v.copy()
        return data
    except Exception as e:
        _quarantine_corrupt(ROBERT_MEMORY_PATH, e)
        return DEFAULT_MEMORY.copy()


def load() -> dict:
    """Load Robert's memory from disk."""
    with _memory_lock():
        return _load_unlocked()


def _save_unlocked(memory: dict):
    """Save Robert's memory to disk with backup + atomic write."""
    memory["last_updated"] = datetime.datetime.utcnow().isoformat()
    basename = os.path.basename(ROBERT_MEMORY_PATH)
    retention = CRITICAL_RETENTION_DAYS if basename in CRITICAL_FILES else STANDARD_RETENTION_DAYS
    backup_before_write(ROBERT_MEMORY_PATH, BACKUP_DIR_ROBERT, retention_days=retention)
    atomic_write(ROBERT_MEMORY_PATH, json.dumps(memory, indent=2))


def save(memory: dict):
    """Save Robert's memory to disk with backup + atomic write (RR-0014 + RR-0013)."""
    with _memory_lock():
        _save_unlocked(memory)


def add_task(task: str, context: str = "", priority: int = 5) -> int:
    """Add a task to Robert's queue. Priority 1=urgent, 10=low. Returns queue size."""
    with _memory_lock():
        mem = _load_unlocked()
        mem["task_queue"].append({
            "id": len(mem["completed_tasks"]) + len(mem["task_queue"]) + 1,
            "task": task,
            "context": context,
            "priority": priority,
            "added_at": datetime.datetime.utcnow().isoformat(),
            "source": "manual"
        })
        mem["task_queue"].sort(key=lambda x: x.get("priority", 5))
        _save_unlocked(mem)
        return len(mem["task_queue"])


def get_next_task() -> dict | None:
    """Pop the highest-priority task from the queue."""
    with _memory_lock():
        mem = _load_unlocked()
        if not mem["task_queue"]:
            return None
        task = mem["task_queue"].pop(0)
        _save_unlocked(mem)
        return task


def complete_task(task: dict, result: str):
    """Mark a task as completed and store the result."""
    with _memory_lock():
        mem = _load_unlocked()
        task["completed_at"] = datetime.datetime.utcnow().isoformat()
        task["result_summary"] = result[:500]
        mem["completed_tasks"].append(task)
        mem["completed_tasks"] = mem["completed_tasks"][-50:]
        _save_unlocked(mem)


def learn(key: str, value: str):
    """Store a learned fact."""
    with _memory_lock():
        mem = _load_unlocked()
        mem["learned_context"][key] = {
            "value": value,
            "learned_at": datetime.datetime.utcnow().isoformat()
        }
        _save_unlocked(mem)


def get_context_summary() -> str:
    """Return a summary of what Robert knows for use in prompts."""
    mem = load()
    lines = [f"Robert Session #{mem['session_count'] + 1}"]

    if mem["learned_context"]:
        lines.append("\nWhat I know:")
        for k, v in list(mem["learned_context"].items())[-10:]:
            lines.append(f"  - {k}: {v['value']}")

    if mem["completed_tasks"]:
        lines.append(f"\nRecent work ({len(mem['completed_tasks'])} tasks completed):")
        for t in mem["completed_tasks"][-3:]:
            lines.append(f"  - {t['task'][:80]}")

    if mem["task_queue"]:
        lines.append(f"\nQueue: {len(mem['task_queue'])} pending tasks")

    return "\n".join(lines)


def get_queue_status() -> dict:
    """Return queue stats."""
    mem = load()
    return {
        "pending": len(mem["task_queue"]),
        "completed": len(mem["completed_tasks"]),
        "next": mem["task_queue"][0]["task"][:80] if mem["task_queue"] else None
    }


def get_telegram_offset() -> int:
    """Get last processed Telegram update ID."""
    mem = load()
    return int(mem.get("telegram_offset", 0) or 0)


def set_telegram_offset(offset: int):
    """Update last processed Telegram update ID."""
    with _memory_lock():
        mem = _load_unlocked()
        mem["telegram_offset"] = int(offset)
        _save_unlocked(mem)


def increment_session():
    """Increment session counter."""
    with _memory_lock():
        mem = _load_unlocked()
        mem["session_count"] += 1
        _save_unlocked(mem)


def append_conversation_turn(chat_id: str, role: str, content: str) -> None:
    """Append a Telegram turn for multi-turn context (Fix 5). Skips empty / identity-break."""
    from gateway_prompt import looks_like_identity_break

    text = (content or "").strip()
    if not text or looks_like_identity_break(text):
        return
    key = str(chat_id or "default")
    with _memory_lock():
        mem = _load_unlocked()
        hist = mem.setdefault("conversation_history", {})
        turns = list(hist.get(key) or [])
        turns.append({
            "role": role,
            "content": text[:2000],
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        hist[key] = turns[-_MAX_CHAT_TURNS:]
        mem["conversation_history"] = hist
        _save_unlocked(mem)


def get_conversation_history(chat_id: str, max_turns: int = 8) -> list:
    """Return recent turns for a chat (caller filters identity-break again at format time)."""
    mem = load()
    hist = mem.get("conversation_history") or {}
    turns = list(hist.get(str(chat_id or "default")) or [])
    return turns[-max_turns:]


def clear_conversation_history(chat_id: str | None = None) -> None:
    """Reset conversation replay after persona deploy (Fix 5). chat_id=None clears all."""
    with _memory_lock():
        mem = _load_unlocked()
        if chat_id is None:
            mem["conversation_history"] = {}
        else:
            hist = mem.setdefault("conversation_history", {})
            hist.pop(str(chat_id), None)
            mem["conversation_history"] = hist
        _save_unlocked(mem)
