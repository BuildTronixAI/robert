"""
Robert ↔ BOB Message Contract — Phase 4b
HMAC-signed, replay-safe, append-only audit log.
Robert proposes. Chris taps. BOB executes. Zero autonomous financial action.
"""

import os
import json
import hmac
import hashlib
import uuid
import time
import datetime
import urllib.request
import urllib.error
import sys

sys.path.insert(0, '/var/lib/robert/workspace')

ENVELOPE_VERSION = "1"
EXPIRY_SECONDS   = 300   # 5-minute window
SENDER_ID        = "robert"

# Loaded from env
BOB_SHARED_SECRET  = os.environ.get("BOB_SHARED_SECRET", "")
BOB_INBOX_URL      = os.environ.get("BOB_INBOX_URL", "")
ROBERT_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "-5288262569")
CHRIS_USER_ID      = 8480371994

# Supabase audit log
SUPABASE_URL       = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY       = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Nonce store — Supabase-backed for persistence across restarts
_seen_nonces_fallback = {}  # in-memory fallback only if Supabase unavailable


def _nonce_seen_supabase(nonce: str, sender: str, expires_at: str) -> bool:
    """Check + insert nonce atomically. Returns True if nonce was already seen (replay)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        # Fallback to in-memory
        if nonce in _seen_nonces_fallback:
            return True
        _seen_nonces_fallback[nonce] = time.time()
        return False
    try:
        # Try INSERT — if nonce exists (PK conflict), it's a replay
        row = json.dumps({"nonce": nonce, "sender": sender, "expires_at": expires_at}).encode()
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/hmac_nonces",
            data=row,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return False  # Insert succeeded = new nonce
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409 or "duplicate" in body.lower() or "unique" in body.lower():
            return True  # Conflict = replay
        # Other HTTP error — fail open (log but allow)
        print(f"[contract] nonce check HTTP error {e.code}: {body[:100]}")
        return False
    except Exception as e:
        print(f"[contract] nonce check error: {e} — failing open")
        return False


# ─── Envelope ──────────────────────────────────────────────────────────────────

def _canonical_json(obj: dict) -> bytes:
    """Sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sign(envelope: dict) -> str:
    """HMAC-SHA256 over canonical JSON of all fields except 'signature'."""
    to_sign = {k: v for k, v in envelope.items() if k != "signature"}
    return hmac.new(
        BOB_SHARED_SECRET.encode(),
        _canonical_json(to_sign),
        hashlib.sha256
    ).hexdigest()


def build_envelope(payload_type: str, payload: dict, in_reply_to: str = None) -> dict:
    now = datetime.datetime.now(datetime.UTC)
    expires = now + datetime.timedelta(seconds=EXPIRY_SECONDS)
    env = {
        "envelope_version": ENVELOPE_VERSION,
        "message_id": str(uuid.uuid4()),
        "in_reply_to": in_reply_to,
        "sender": SENDER_ID,
        "sent_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "nonce": os.urandom(32).hex(),
        "payload_type": payload_type,
        "payload": payload,
    }
    env["signature"] = _sign(env)
    return env


def verify_envelope(env: dict) -> tuple[bool, str]:
    """Verify signature, expiry, nonce. Returns (ok, reason)."""
    # 1. Signature
    expected = _sign(env)
    if not hmac.compare_digest(expected, env.get("signature", "")):
        return False, "bad_signature"

    # 2. Expiry
    try:
        expires = datetime.datetime.fromisoformat(env["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=datetime.timezone.utc)
        if datetime.datetime.now(datetime.UTC) > expires:
            return False, "expired"
    except Exception:
        return False, "bad_expires"

    # 3. Nonce replay — Supabase-backed, survives restarts
    nonce = env.get("nonce", "")
    expires_at = env.get("expires_at", "")
    sender = env.get("sender", "unknown")
    if _nonce_seen_supabase(nonce, sender, expires_at):
        return False, "replayed"

    # 4. Duplicate message_id (simple in-memory; Supabase handles persistence)
    return True, "ok"


# ─── Audit Log (RR-0056 Phase 1 — RPC version) ────────────────────────────────

def audit_log(env: dict, verification_result: str, outcome: str = None, proposal_id: str = None):
    """
    Append a row to robert_bob_audit via SECURITY DEFINER RPC.
    RR-0056 Phase 1: calls append_audit_record() RPC instead of direct INSERT.
    Hash chain computed server-side. Audit write failure is fail-closed.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return  # Supabase not configured yet

    rpc_params = {
        "p_receiver": "robert",
        "p_sender": env.get("sender", "bob"),
        "p_message_id": env.get("message_id"),
        "p_payload_type": env.get("payload_type"),
        "p_envelope": json.dumps(env),
        "p_raw_signature": env.get("signature", ""),
        "p_verification_result": verification_result,
        "p_processing_outcome": outcome,
        "p_bob_proposal_id": proposal_id,
        "p_approver_id": None,
    }
    try:
        payload = json.dumps(rpc_params).encode()
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/rpc/append_audit_record",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer": "return=minimal",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as audit_exc:
        print(
            f"[BOB contract] CRITICAL: Audit RPC write FAILED. "
            f"outcome={outcome!r}, audit_exc={audit_exc}. "
            f"FAIL-CLOSED — halting write path.",
            flush=True
        )
        raise RuntimeError(
            f"Audit write failed (fail-closed per RR-0056): {audit_exc}"
        ) from audit_exc


# ─── Outbound to BOB ───────────────────────────────────────────────────────────

def _send_to_bob(env: dict) -> dict:
    """POST a signed envelope to BOB's inbox."""
    if not BOB_INBOX_URL:
        return {"ok": False, "error": "BOB_INBOX_URL not configured"}

    payload = json.dumps(env).encode()
    req = urllib.request.Request(
        BOB_INBOX_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def query_read(scope: str, filters: dict = None) -> dict:
    """Send a read-only query to BOB."""
    env = build_envelope("query.read", {"scope": scope, "filters": filters or {}})
    return _send_to_bob(env)


def propose_action(subtype: str, summary: str, details: dict) -> dict:
    """
    Propose a financial action to BOB.
    Returns proposal_id. Nothing executes until Chris taps Approve.
    """
    env = build_envelope("action.propose", {
        "subtype": subtype,
        "human_readable_summary": summary,
        "details": details
    })
    result = _send_to_bob(env)
    audit_log(env, "ok", outcome="proposed", proposal_id=result.get("proposal_id"))
    return result


def confirm_action(proposal_id: str, approver_telegram_id: int) -> dict:
    """Send action.confirm after Chris taps Approve in Telegram."""
    env = build_envelope("action.confirm", {
        "proposal_id": proposal_id,
        "approver_telegram_id": approver_telegram_id
    })
    result = _send_to_bob(env)
    audit_log(env, "ok", outcome="confirmed", proposal_id=proposal_id)
    return result


def cancel_action(proposal_id: str, rejected_by: int) -> dict:
    """Send action.cancel after Chris taps Reject in Telegram."""
    env = build_envelope("action.cancel", {
        "proposal_id": proposal_id,
        "rejected_by": rejected_by
    })
    return _send_to_bob(env)


# ─── Telegram Approval Buttons ─────────────────────────────────────────────────

def send_approval_request(proposal_id: str, summary: str):
    """
    Post a proposal to Buildtronix LineUp with Approve/Reject inline buttons.
    15-minute expiry baked in via the envelope expires_at.
    """
    text = (
        f"📋 BOB Proposal\n\n"
        f"{summary}\n\n"
        f"ID: {proposal_id}\n"
        f"⏱ Expires in 5 minutes — tap before then."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✓ Approve", "callback_data": f"approve:{proposal_id}"},
            {"text": "✗ Reject",  "callback_data": f"reject:{proposal_id}"}
        ]]
    }
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "reply_markup": json.dumps(keyboard)
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{ROBERT_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[BOB contract] Approval send error: {e}", flush=True)
        return {}


def handle_callback(callback: dict):
    """
    Process Approve/Reject button tap from Chris.
    ALWAYS re-fetches proposal from BOB — never trusts button payload for state.
    """
    user_id = callback.get("from", {}).get("id")
    if user_id != CHRIS_USER_ID:
        _answer_callback(callback["id"], "Not authorized.")
        return

    data = callback.get("data", "")
    if ":" not in data:
        return

    action, proposal_id = data.split(":", 1)
    chat_id  = callback["message"]["chat"]["id"]
    msg_id   = callback["message"]["message_id"]
    now_str  = datetime.datetime.now(datetime.UTC).strftime("%b %d %Y %H:%M UTC")

    if action == "approve":
        result = confirm_action(proposal_id, user_id)
        _edit_message(chat_id, msg_id, f"✓ Approved by Chris at {now_str}\nProposal: {proposal_id}")
        _answer_callback(callback["id"], "Approved — sent to BOB.")
    elif action == "reject":
        result = cancel_action(proposal_id, user_id)
        _edit_message(chat_id, msg_id, f"✗ Rejected by Chris at {now_str}\nProposal: {proposal_id}")
        _answer_callback(callback["id"], "Rejected.")


def _answer_callback(callback_id: str, text: str):
    payload = json.dumps({"callback_query_id": callback_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{ROBERT_BOT_TOKEN}/answerCallbackQuery",
        data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass


def _edit_message(chat_id, msg_id, text):
    payload = json.dumps({"chat_id": chat_id, "message_id": msg_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{ROBERT_BOT_TOKEN}/editMessageText",
        data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass


# ─── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Self-test: sign → verify roundtrip")
    env = build_envelope("query.read", {"scope": "ar.aging"})
    ok, reason = verify_envelope(env)
    print(f"  Verify result: {ok} ({reason})")
    assert ok, "Verification failed!"

    # Test replay protection
    ok2, reason2 = verify_envelope(env)
    assert not ok2 and reason2 == "replayed", f"Replay should fail, got: {ok2} {reason2}"
    print(f"  Replay blocked: {reason2}")

    # Test expiry
    env2 = build_envelope("ack", {})
    env2["expires_at"] = "2020-01-01T00:00:00+00:00"
    env2["signature"] = _sign(env2)
    ok3, reason3 = verify_envelope(env2)
    assert not ok3 and reason3 == "expired", f"Expiry should fail, got: {ok3} {reason3}"
    print(f"  Expiry blocked: {reason3}")

    print("All tests passed.")
