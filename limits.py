"""
Robert Rate Limiter — ADD-4
Enforced in Robert before any proposal reaches BOB.
Limits are configured in /etc/robert/limits.json.
Watchdog: second per-minute hit in 5 minutes → auto kill switch + alert Chris.
"""

import json
import time
import threading
import collections
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import atomic_write, backup_before_write, BACKUP_DIR_ROBERT, CRITICAL_FILES, CRITICAL_RETENTION_DAYS, STANDARD_RETENTION_DAYS  # RR-0013 + RR-0014

LIMITS_FILE = "/etc/robert/limits.json"
DEFAULT_LIMITS = {
    "proposals_per_minute": 3,
    "proposals_per_hour": 20,
    "proposals_per_day": 100,
    "proposals_per_subtype_per_day": {
        "payment.schedule": 10,
        "invoice.send": 50,
        "journal.post": 30
    },
    "queries_per_minute": 30,
    "telegram_messages_per_minute": 10
}

WATCHDOG_WINDOW   = 300  # 5 minutes
WATCHDOG_TRIGGERS = 2    # second hit within window → auto-pause


class RateLimiter:
    def __init__(self):
        self._events = collections.defaultdict(collections.deque)
        self._lock   = threading.Lock()
        self._rate_limit_hits = collections.deque()
        self._load_config()

    def _load_config(self):
        try:
            with open(LIMITS_FILE) as f:
                self.cfg = json.load(f)
        except Exception:
            self.cfg = DEFAULT_LIMITS

    def check(self, key: str, window_seconds: int, limit: int) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            q = self._events[key]
            while q and q[0] < now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False, int(q[0] + window_seconds - now) + 1
            q.append(now)
            return True, 0

    def check_proposal(self, subtype: str) -> tuple[bool, str]:
        """Check all proposal rate limits. Returns (allowed, reason)."""
        checks = [
            ("prop_min",  60,    self.cfg.get("proposals_per_minute", 3)),
            ("prop_hour", 3600,  self.cfg.get("proposals_per_hour", 20)),
            ("prop_day",  86400, self.cfg.get("proposals_per_day", 100)),
        ]
        for key, window, limit in checks:
            ok, wait = self.check(key, window, limit)
            if not ok:
                return False, f"{key.replace('prop_', '')}-limit hit, retry in {wait}s"

        # Per-subtype daily limit
        per_sub = self.cfg.get("proposals_per_subtype_per_day", {}).get(subtype, 1000)
        ok, wait = self.check(f"prop_sub_{subtype}", 86400, per_sub)
        if not ok:
            return False, f"per-subtype limit for {subtype}, retry in {wait}s"

        return True, ""

    def check_query(self) -> tuple[bool, str]:
        ok, wait = self.check("query_min", 60, self.cfg.get("queries_per_minute", 30))
        if not ok:
            return False, f"query rate limit, retry in {wait}s"
        return True, ""

    def check_telegram(self) -> tuple[bool, str]:
        ok, wait = self.check("tg_min", 60, self.cfg.get("telegram_messages_per_minute", 10))
        if not ok:
            return False, f"telegram rate limit, retry in {wait}s"
        return True, ""

    def record_rate_limit_hit(self) -> int:
        """Record a rate limit hit. Returns number of hits in watchdog window."""
        now = time.time()
        with self._lock:
            while self._rate_limit_hits and self._rate_limit_hits[0] < now - WATCHDOG_WINDOW:
                self._rate_limit_hits.popleft()
            self._rate_limit_hits.append(now)
            return len(self._rate_limit_hits)

    def reset(self):
        """Clear all rate limit counters (for /robert reset-limits command)."""
        with self._lock:
            self._events.clear()
            self._rate_limit_hits.clear()
        self._load_config()


def write_default_limits():
    """Write default limits file with backup + atomic write (RR-0014 + RR-0013)."""
    if not os.path.exists(LIMITS_FILE):
        os.makedirs(os.path.dirname(LIMITS_FILE), exist_ok=True)
        # No backup on first-time write (backup_before_write guards nonexistent files)
        atomic_write(LIMITS_FILE, json.dumps(DEFAULT_LIMITS, indent=2))
    else:
        basename = os.path.basename(LIMITS_FILE)
        retention = CRITICAL_RETENTION_DAYS if basename in CRITICAL_FILES else STANDARD_RETENTION_DAYS
        backup_before_write(LIMITS_FILE, BACKUP_DIR_ROBERT, retention_days=retention)
        atomic_write(LIMITS_FILE, json.dumps(DEFAULT_LIMITS, indent=2))


# Singleton
_limiter = None

def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        write_default_limits()
        _limiter = RateLimiter()
    return _limiter
