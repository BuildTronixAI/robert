"""
Robert Startup Preconditions — Constitutional Enforcement
==========================================================
Called by listener.py on startup, before accepting any tasks.

Two preconditions enforced:
  1. Git dirty-check: if working tree is dirty, boot in LOUD DEGRADED MODE
     (log warning, notify Chris, refuse constitutional write operations)
  2. RPC startup probe: if ROBERT_AUDITED_WRITES_ENABLED=true, probe for
     append_audit_record RPC before accepting any task.
     A missing RPC on startup produces a clear error and blocks task acceptance.
     This turns a documented procedure into an enforced precondition.

Usage (in listener.py startup):
    from startup_preconditions import check_startup_preconditions
    STARTUP_STATE = check_startup_preconditions()
    # STARTUP_STATE.git_clean: bool
    # STARTUP_STATE.rpc_ready: bool
    # STARTUP_STATE.degraded: bool
    # STARTUP_STATE.degraded_reason: str | None

Design principle (from final reviewer synthesis):
    "Robert should know when he's running unverifiable code and say so."
    "Make the sequencing requirement an enforced precondition, not a
     documented procedure someone has to remember."
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY", "")
AUDITED_WRITES_ENABLED = os.environ.get("ROBERT_AUDITED_WRITES_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHRIS_CHAT_ID = "8480371994"

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class StartupState:
    git_clean: bool = True
    git_dirty_files: list = field(default_factory=list)
    rpc_ready: bool = True          # True if not needed OR confirmed present
    rpc_checked: bool = False       # Whether we actually probed
    degraded: bool = False
    degraded_reason: Optional[str] = None
    warnings: list = field(default_factory=list)

    def as_summary(self) -> str:
        lines = []
        if self.degraded:
            lines.append(f"⚠️ STARTUP DEGRADED: {self.degraded_reason}")
        if not self.git_clean:
            lines.append(f"  Dirty files ({len(self.git_dirty_files)}): {', '.join(self.git_dirty_files[:5])}")
        if not self.rpc_ready:
            lines.append("  Audit RPC not confirmed — audited writes will fail")
        for w in self.warnings:
            lines.append(f"  Warning: {w}")
        if not lines:
            lines.append("✅ Startup preconditions: all clear")
        return "\n".join(lines)


def _check_git_dirty(workspace: str) -> tuple[bool, list]:
    """
    Run git status --porcelain in the workspace directory.
    Returns (is_dirty, list_of_dirty_files).
    If git is not available or this is not a git repo, returns (False, [])
    with a warning — we don't want a missing git binary to block startup.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning("[startup] git status failed (returncode %d) — skipping dirty check",
                           result.returncode)
            return False, []
        dirty_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return len(dirty_lines) > 0, dirty_lines
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("[startup] git not available or timed out (%s) — skipping dirty check", e)
        return False, []


def _probe_audit_rpc() -> tuple[bool, str]:
    """
    Probe Supabase for the append_audit_record RPC by querying pg_proc via
    the PostgREST /rest/v1/rpc endpoint. A 200 or 404 from the specific RPC
    path tells us whether it's deployed.

    Returns (rpc_present: bool, detail: str).
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False, "SUPABASE_URL or SUPABASE_KEY not configured"

    # Attempt to call the RPC with empty params — a 400 (bad params) means
    # the function exists. A 404 means it doesn't.
    probe_url = f"{SUPABASE_URL}/rest/v1/rpc/append_audit_record"
    probe_payload = json.dumps({}).encode()
    req = urllib.request.Request(
        probe_url,
        data=probe_payload,
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            # 200 with empty params would be unusual — treat as present
            return True, f"RPC probe returned HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        if e.code == 400:
            # Bad request = function exists but rejected our empty params
            return True, f"RPC present (HTTP 400 on empty params — expected)"
        if e.code == 404:
            return False, f"RPC not found (HTTP 404) — deploy 02_create_audit_rpc.sql first"
        if e.code in (401, 403):
            return False, f"RPC auth error (HTTP {e.code}) — check SUPABASE_SERVICE_KEY"
        # Other errors — unknown state
        return False, f"RPC probe error HTTP {e.code}: {body}"
    except Exception as e:
        return False, f"RPC probe exception: {e}"


def _notify_chris_degraded(state: StartupState) -> None:
    """
    Send a Telegram message to Chris alerting that Robert booted in degraded mode.
    Non-fatal — if this fails, we still boot degraded (don't crash the crash handler).
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("[startup] TELEGRAM_BOT_TOKEN not set — cannot notify Chris of degraded boot")
        return

    msg = (
        f"⚠️ ROBERT DEGRADED BOOT\n"
        f"{state.degraded_reason}\n\n"
        f"Constitutional write operations are blocked until resolved.\n"
        f"Details:\n{state.as_summary()}"
    )
    payload = json.dumps({"chat_id": CHRIS_CHAT_ID, "text": msg}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            logger.info("[startup] Chris notified of degraded boot via Telegram")
    except Exception as e:
        logger.error("[startup] Failed to notify Chris of degraded boot: %s", e)


def check_startup_preconditions(workspace: str = WORKSPACE_DIR) -> StartupState:
    """
    Run all startup precondition checks. Called once on boot before accepting tasks.

    Returns a StartupState. The caller (listener.py) should:
      - Log state.as_summary() on every boot
      - If state.degraded: block constitutional write operations
      - If state.degraded: notify Chris (done here if Telegram available)
    """
    state = StartupState()

    # ── 1. Git dirty check ────────────────────────────────────────────────────
    is_dirty, dirty_files = _check_git_dirty(workspace)
    if is_dirty:
        state.git_clean = False
        state.git_dirty_files = dirty_files
        state.degraded = True
        state.degraded_reason = (
            f"Working tree has {len(dirty_files)} uncommitted file(s). "
            f"Running unverifiable code. Constitutional writes blocked. "
            f"Commit all modified files to restore clean mode."
        )
        logger.warning(
            "[startup] ⚠️ GIT DIRTY: %d uncommitted file(s): %s",
            len(dirty_files),
            ", ".join(dirty_files[:5])
        )
    else:
        logger.info("[startup] ✅ Git clean — working tree matches HEAD")

    # ── 2. Audit RPC probe (only if audited writes are enabled) ───────────────
    if AUDITED_WRITES_ENABLED:
        logger.info("[startup] Audited writes enabled — probing append_audit_record RPC...")
        rpc_present, rpc_detail = _probe_audit_rpc()
        state.rpc_checked = True
        state.rpc_ready = rpc_present

        if not rpc_present:
            state.degraded = True
            reason = (
                f"ROBERT_AUDITED_WRITES_ENABLED=true but append_audit_record RPC not confirmed: "
                f"{rpc_detail}. "
                f"Deploy deploy/rr0056-phase1/02_create_audit_rpc.sql to Supabase first."
            )
            state.degraded_reason = (state.degraded_reason + " | " + reason
                                     if state.degraded_reason else reason)
            logger.error("[startup] ❌ Audit RPC not found: %s", rpc_detail)
        else:
            logger.info("[startup] ✅ Audit RPC confirmed: %s", rpc_detail)
    else:
        state.rpc_ready = True  # Not needed if writes disabled
        state.warnings.append(
            "ROBERT_AUDITED_WRITES_ENABLED=false — audit writes disabled. "
            "Constitutional compliance not achievable in this state."
        )
        logger.warning("[startup] ⚠️ Audited writes DISABLED — not governance-compliant")

    # ── 3. Notify Chris if degraded ───────────────────────────────────────────
    if state.degraded:
        _notify_chris_degraded(state)

    # ── 4. Log final state ────────────────────────────────────────────────────
    logger.info("[startup] Precondition check complete:\n%s", state.as_summary())
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Degraded mode enforcement helper — call this before any constitutional write
# ─────────────────────────────────────────────────────────────────────────────

def assert_not_degraded(startup_state: StartupState, operation: str) -> None:
    """
    Raise RuntimeError if Robert is in degraded mode and the requested
    operation is constitutional (requires audit trail).

    Usage in tool layer:
        from startup_preconditions import assert_not_degraded, STARTUP_STATE
        assert_not_degraded(STARTUP_STATE, "supabase_insert")
    """
    if startup_state.degraded:
        raise RuntimeError(
            f"[constitutional-gate] Operation '{operation}' blocked — "
            f"Robert is in DEGRADED MODE: {startup_state.degraded_reason}"
        )
