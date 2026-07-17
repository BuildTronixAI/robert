#!/usr/bin/env python3
"""Read checkpoint DB — used for smoke test evidence collection."""
import sqlite3, sys

DB = "/var/lib/robert/workspace/robert_checkpoints.db"

def check_latest(thread_id=None):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    if thread_id:
        rows = conn.execute(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints WHERE thread_id=? LIMIT 5",
            (thread_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints LIMIT 10"
        ).fetchall()

    if not rows:
        print("No checkpoints found.")
        return

    print(f"{'thread_id':<38} {'ns':<6} {'checkpoint_id'}")
    print("-" * 90)
    for r in rows:
        print(f"{r['thread_id']:<38} {r['checkpoint_ns']:<6} {r['checkpoint_id']}")

def count():
    conn = sqlite3.connect(DB)
    n = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    print(f"Total checkpoints: {n}")

if __name__ == "__main__":
    count()
    print()
    check_latest(sys.argv[1] if len(sys.argv) > 1 else None)
