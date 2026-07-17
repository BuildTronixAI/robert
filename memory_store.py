"""
Robert Persistent Memory Store — Phase 3
Robert's own memory, separate from BOB's.
Tracks: completed tasks, learned context, active workflows, task queue.
"""

import json
import os
import sys
import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import atomic_write, backup_before_write, BACKUP_DIR_ROBERT, CRITICAL_FILES, CRITICAL_RETENTION_DAYS, STANDARD_RETENTION_DAYS  # RR-0013 + RR-0014

ROBERT_MEMORY_PATH = "/var/lib/robert/workspace/robert_memory.json"

DEFAULT_MEMORY = {
    "task_queue": [],           # Pending tasks to work through
    "completed_tasks": [],      # Last 50 completed tasks
    "learned_context": {},      # Key facts Robert has learned
    "active_workflows": [],     # Currently running multi-step workflows
    "last_updated": None,
    "session_count": 0,
    "telegram_offset": 0,       # Last Telegram update ID processed
}

def load() -> dict:
    """Load Robert's memory from disk."""
    if not os.path.exists(ROBERT_MEMORY_PATH):
        return DEFAULT_MEMORY.copy()
    try:
        with open(ROBERT_MEMORY_PATH, "r") as f:
            data = json.load(f)
        # Merge with defaults for any missing keys
        for k, v in DEFAULT_MEMORY.items():
            if k not in data:
                data[k] = v
        return data
    except:
        return DEFAULT_MEMORY.copy()

def save(memory: dict):
    """Save Robert's memory to disk with backup + atomic write (RR-0014 + RR-0013)."""
    memory["last_updated"] = datetime.datetime.utcnow().isoformat()
    basename = os.path.basename(ROBERT_MEMORY_PATH)
    retention = CRITICAL_RETENTION_DAYS if basename in CRITICAL_FILES else STANDARD_RETENTION_DAYS
    backup_before_write(ROBERT_MEMORY_PATH, BACKUP_DIR_ROBERT, retention_days=retention)
    atomic_write(ROBERT_MEMORY_PATH, json.dumps(memory, indent=2))

def add_task(task: str, context: str = "", priority: int = 5) -> int:
    """Add a task to Robert's queue. Priority 1=urgent, 10=low. Returns queue size."""
    mem = load()
    mem["task_queue"].append({
        "id": len(mem["completed_tasks"]) + len(mem["task_queue"]) + 1,
        "task": task,
        "context": context,
        "priority": priority,
        "added_at": datetime.datetime.utcnow().isoformat(),
        "source": "manual"
    })
    # Sort by priority (lower = more urgent)
    mem["task_queue"].sort(key=lambda x: x.get("priority", 5))
    save(mem)
    return len(mem["task_queue"])

def get_next_task() -> dict | None:
    """Pop the highest-priority task from the queue."""
    mem = load()
    if not mem["task_queue"]:
        return None
    task = mem["task_queue"].pop(0)
    save(mem)
    return task

def complete_task(task: dict, result: str):
    """Mark a task as completed and store the result."""
    mem = load()
    task["completed_at"] = datetime.datetime.utcnow().isoformat()
    task["result_summary"] = result[:500]
    mem["completed_tasks"].append(task)
    # Keep only last 50
    mem["completed_tasks"] = mem["completed_tasks"][-50:]
    save(mem)

def learn(key: str, value: str):
    """Store a learned fact."""
    mem = load()
    mem["learned_context"][key] = {
        "value": value,
        "learned_at": datetime.datetime.utcnow().isoformat()
    }
    save(mem)

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
    return mem.get("telegram_offset", 0)

def set_telegram_offset(offset: int):
    """Update last processed Telegram update ID."""
    mem = load()
    mem["telegram_offset"] = offset
    save(mem)

def increment_session():
    """Increment session counter."""
    mem = load()
    mem["session_count"] += 1
    save(mem)
