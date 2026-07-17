"""Configuration module for Robert COO Agent.
All secrets loaded from environment only — no hardcoded fallbacks.
Set via /etc/robert/secrets.env (loaded by systemd EnvironmentFile).
"""

import os

def _require(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(f"[Robert] Missing required env var: {key}. Check /etc/robert/secrets.env")
    return val

def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

# ── API Keys ───────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = _require("OPENROUTER_API_KEY")
ANTHROPIC_API_KEY   = _optional("ANTHROPIC_API_KEY", OPENROUTER_API_KEY)
SUPABASE_URL        = _require("SUPABASE_URL")
SUPABASE_KEY        = _require("SUPABASE_SERVICE_KEY")
SENDGRID_API_KEY    = os.environ.get("SENDGRID_API_KEY", "")
TELEGRAM_BOT_TOKEN  = _require("TELEGRAM_BOT_TOKEN")
ROBERT_BOT_TOKEN    = _optional("ROBERT_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
TELEGRAM_CHAT_ID    = _require("TELEGRAM_CHAT_ID")

# ── BOB Contract ───────────────────────────────────────────────────────
BOB_SHARED_SECRET   = _optional("BOB_SHARED_SECRET")
BOB_INBOX_URL       = _optional("BOB_INBOX_URL")
ROBERT_INBOX_URL    = _optional("ROBERT_INBOX_URL")
CHRIS_TOTP_SECRET   = _optional("CHRIS_TOTP_SECRET")

# ── Paths ──────────────────────────────────────────────────────────────
WORKSPACE_PATH      = _optional("WORKSPACE_PATH", "/var/lib/robert/workspace")

# ── Model routing — Sonnet for reasoning, Haiku for execution ──────────
ROBERT_MODEL        = "anthropic/claude-sonnet-5"
ROBERT_EXEC_MODEL   = "anthropic/claude-haiku-4-5"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ── Limits ─────────────────────────────────────────────────────────────
COMMAND_TIMEOUT = 30
MAX_ITERATIONS  = 3

# ── Feature Flags ────────────────────────────────────────────────────────
# ROBERT_AUDITED_WRITES_ENABLED: controls whether write_with_audit RPC is used.
#
# FALSE (default) = safe state. Audited table writes are rejected with a clear
#   AuditedWritesDisabledError. No silent fallback to direct inserts.
#   Use this state until write_with_audit RPC + FieldOps schema are deployed
#   to Supabase and verified end-to-end.
#
# TRUE = RPC routing active. Only flip after:
#   1. write_with_audit() RPC created in Supabase
#   2. FieldOps tables exist and verified
#   3. actor_id call site audit complete
#   4. End-to-end regression test passing
#   5. Chris explicit sign-off
#
# Set in /etc/robert/secrets.env: ROBERT_AUDITED_WRITES_ENABLED=true
ROBERT_AUDITED_WRITES_ENABLED = _optional("ROBERT_AUDITED_WRITES_ENABLED", "false").lower() == "true"

def validate_config():
    """Call at startup to catch missing/dead credentials early.
    Tests each key with a real API call. Fails loud if any credential is dead.
    """
    import urllib.request, urllib.error

    required = [
        "OPENROUTER_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "SENDGRID_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
    ]
    missing = [k for k in required if not os.environ.get(k, "").strip()]
    if missing:
        raise RuntimeError(f"[Robert] Missing required env vars: {', '.join(missing)}")

    errors = []

    # Test OpenRouter key
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status not in (200, 206):
                errors.append(f"OPENROUTER_API_KEY: HTTP {r.status}")
    except urllib.error.HTTPError as e:
        errors.append(f"OPENROUTER_API_KEY: HTTP {e.code} — key may be dead")
    except Exception as e:
        errors.append(f"OPENROUTER_API_KEY: {e}")

    # Test Supabase key
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/profiles?limit=1",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status not in (200, 206):
                errors.append(f"SUPABASE_SERVICE_KEY: HTTP {r.status}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            errors.append(f"SUPABASE_SERVICE_KEY: HTTP 401 — key invalid")
        # 404 (table not found) is OK — key works, table may not exist
    except Exception as e:
        errors.append(f"SUPABASE_SERVICE_KEY: {e}")

    # Test Telegram bot token
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            pass
    except urllib.error.HTTPError as e:
        if e.code == 401:
            errors.append(f"TELEGRAM_BOT_TOKEN: HTTP 401 — token invalid")
    except Exception as e:
        errors.append(f"TELEGRAM_BOT_TOKEN: {e}")

    if errors:
        raise RuntimeError(f"[Robert] Credential health check FAILED:\n" + "\n".join(f"  - {e}" for e in errors))
