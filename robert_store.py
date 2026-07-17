"""
Durable local store for Robert runtime state.

Used when Supabase RPC/DB is unavailable or for mesh Phase B durability:
  - mesh nonces / task_ids (replay protection across restarts)
  - gate idempotency keys (local claim)

SQLite file under WORKSPACE_PATH. Single-writer, WAL mode.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_LOCK = threading.Lock()
_INITIALIZED = False


def _db_path() -> str:
    workspace = os.environ.get("WORKSPACE_PATH", "/var/lib/robert/workspace")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    return os.environ.get(
        "ROBERT_STORE_DB",
        os.path.join(workspace, "robert_runtime.db"),
    )


@contextmanager
def _conn():
    global _INITIALIZED
    path = _db_path()
    with _LOCK:
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            if not _INITIALIZED:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS mesh_nonces (
                        nonce TEXT PRIMARY KEY,
                        task_id TEXT,
                        recorded_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS mesh_tasks (
                        task_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL,
                        recorded_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS idempotency_keys (
                        key TEXT PRIMARY KEY,
                        action_type TEXT,
                        target TEXT,
                        payload_hash TEXT,
                        originating_task_id TEXT,
                        decision_id TEXT,
                        claimed_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS pending_decisions (
                        decision_id TEXT PRIMARY KEY,
                        action_type TEXT,
                        target TEXT,
                        tier TEXT,
                        payload_hash TEXT,
                        token_json TEXT,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    );
                    """
                )
                conn.commit()
                _INITIALIZED = True
            yield conn
            conn.commit()
        finally:
            conn.close()


class DurableReplayError(Exception):
    """Raised when a mesh nonce or task_id has already been claimed."""


class DurableNonceStore:
    """Replay protection for mesh tasks — survives process restart."""

    def __init__(self, window_seconds: int = 600):
        self.window_seconds = window_seconds

    def check_and_record(self, nonce: str, task_id: str = "") -> bool:
        now = time.time()
        cutoff = now - self.window_seconds
        with _conn() as conn:
            conn.execute("DELETE FROM mesh_nonces WHERE recorded_at < ?", (cutoff,))
            row = conn.execute(
                "SELECT nonce FROM mesh_nonces WHERE nonce = ?", (nonce,)
            ).fetchone()
            if row:
                raise DurableReplayError(f"Nonce already seen: {nonce[:16]}...")
            # Also reject duplicate task_id within window
            if task_id:
                existing = conn.execute(
                    "SELECT task_id FROM mesh_tasks WHERE task_id = ? AND recorded_at >= ?",
                    (task_id, cutoff),
                ).fetchone()
                if existing:
                    raise DurableReplayError(f"Task already seen: {task_id[:16]}...")
                conn.execute(
                    "INSERT INTO mesh_tasks(task_id, state, recorded_at) VALUES (?, ?, ?)",
                    (task_id, "claimed", now),
                )
            conn.execute(
                "INSERT INTO mesh_nonces(nonce, task_id, recorded_at) VALUES (?, ?, ?)",
                (nonce, task_id, now),
            )
        return True

def claim_idempotency_key(
    key: str,
    action_type: str,
    target: str,
    payload_hash: str,
    originating_task_id: str,
    decision_id: str,
    ttl_seconds: int = 86400,
) -> str:
    """
    Local durable idempotency claim.
    Returns 'allowed' or 'duplicate'.
    """
    now = time.time()
    with _conn() as conn:
        conn.execute("DELETE FROM idempotency_keys WHERE expires_at < ?", (now,))
        row = conn.execute(
            "SELECT key, expires_at FROM idempotency_keys WHERE key = ?", (key,)
        ).fetchone()
        if row and row[1] >= now:
            return "duplicate"
        if row:
            conn.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
        conn.execute(
            """
            INSERT INTO idempotency_keys(
                key, action_type, target, payload_hash,
                originating_task_id, decision_id, claimed_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                action_type,
                target,
                payload_hash,
                originating_task_id,
                decision_id,
                now,
                now + ttl_seconds,
            ),
        )
        return "allowed"


def save_pending_decision(
    decision_id: str,
    action_type: str,
    target: str,
    tier: str,
    payload_hash: str,
    token_json: str,
    expires_at_epoch: float,
) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pending_decisions(
                decision_id, action_type, target, tier, payload_hash,
                token_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                action_type,
                target,
                tier,
                payload_hash,
                token_json,
                time.time(),
                expires_at_epoch,
            ),
        )


def load_pending_decision(decision_id: str) -> dict | None:
    now = time.time()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT decision_id, action_type, target, tier, payload_hash, token_json, expires_at
            FROM pending_decisions
            WHERE decision_id = ?
            """,
            (decision_id,),
        ).fetchone()
        if not row:
            return None
        if row[6] < now:
            conn.execute("DELETE FROM pending_decisions WHERE decision_id = ?", (decision_id,))
            return None
        return {
            "decision_id": row[0],
            "action_type": row[1],
            "target": row[2],
            "tier": row[3],
            "payload_hash": row[4],
            "token_json": row[5],
            "expires_at": row[6],
        }
