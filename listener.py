"""
Robert Telegram Listener — Phase 3
Long-poll getUpdates loop. One instance only (systemd enforces this).
Responds to any message from Chris in the Buildtronix LineUp group.
"""

import sys
import re
import json
import time
import datetime
import sqlite3
import logging
import logging.handlers
import urllib.request
import urllib.error

# ── D11 Inbound Mesh Receiver (Phase B) ─────────────────────────────────────
# Receives Ed25519-signed tasks from BOB only.
# Terminal success state: STAGED. No external execution in Phase B.
# Idempotency sentinel: _is_mesh_task
import os as _d11_os, sys as _d11_sys
_d11_sys.path.insert(0, _d11_os.path.dirname(__file__))
try:
    from mesh_receiver import MeshReceiver
    from mesh_receiver_config import BOB_PUBLIC_KEY_HEX, _mesh_witness_log
    from mesh_task_handlers import register_handlers
    _mesh_receiver = MeshReceiver(
        robert_agent_id="robert",
        bob_public_key_hex=BOB_PUBLIC_KEY_HEX,
        witness_log=_mesh_witness_log,
    )
    register_handlers(_mesh_receiver)
    print("[D11] Mesh receiver initialized — STAGED-only mode (Phase B)")
except Exception as _d11_e:
    print(f"[D11] Mesh receiver init failed: {_d11_e} — mesh tasks will be dropped")
    _mesh_receiver = None

def _is_mesh_task(text: str) -> bool:
    """Check if text is a signed mesh task envelope."""
    if not text or not text.startswith("{"):
        return False
    try:
        import json as _j
        d = _j.loads(text)
        return all(k in d for k in ["task_id", "sender_id", "signature", "nonce", "payload_hash"])
    except Exception:
        return False

def _handle_mesh_task_sync(text: str, chat_id: str) -> None:
    """
    Route a mesh task to the receiver.
    Phase B contract: result state must be STAGED, never EXTERNALLY_COMMITTED.
    """
    if _mesh_receiver is None:
        log("[D11] Mesh receiver not initialized — dropping task")
        return
    import asyncio as _a
    loop = _a.new_event_loop()
    try:
        result = loop.run_until_complete(_mesh_receiver.receive(text.encode()))
        state = result.get("state", "unknown")
        task_id = result.get("task_id", "?")[:8]
        # Phase B enforcement: abort if anything claims EXTERNALLY_COMMITTED
        if state == "externally_committed":
            log(f"[D11] HALT — Phase B violation: EXTERNALLY_COMMITTED received (task={task_id})")
            return
        log(f"[D11] Mesh task complete: state={state} task_id={task_id}...")
    except Exception as e:
        log(f"[D11] Mesh task error: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass
# ── End D11 ──────────────────────────────────────────────────────────────────


sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
from config import ROBERT_BOT_TOKEN, TELEGRAM_CHAT_ID
import memory_store
from policy_engine import check_kill_switch
from auth.jwt_minter import resolve_identity_and_mint, IdentityNotFoundError, JWTMintError
from auth.permissions import check_permission
from startup_preconditions import check_startup_preconditions, StartupState

# Module-level startup state — set in run(); tools may import for degraded gates
STARTUP_STATE: StartupState | None = None

CHRIS_USER_ID = 8480371994
ROBERT_BOT_ID = None

# Alerting — last successful task timestamp
_last_success_ts = time.time()  # reset on startup
SILENCE_ALERT_HOURS = 4  # alert if no successful task in N hours
_silence_alerted = False

# ── RR-0059-rev7: Behavioral Contract Fix ──────────────────────────────────
# SHORT_COMMANDS: short operational inputs treated as intentional commands,
# not accidental sends. Bypass the TOO_SHORT filter.
# GOVERNANCE: changes require a Review Request.
SHORT_COMMANDS: frozenset = frozenset({
    'ok', 'go', 'yes', 'no', 'y', 'n',
    'run', 'stop', 'retry', 'status',
    'help', 'done', 'skip',
})

# Transport health
DELIVERY_FAILURE_WINDOW_SEC: int       = 300
DELIVERY_FAILURE_RATE_THRESHOLD: float = 0.50
DELIVERY_FAILURE_MIN_ATTEMPTS: int     = 5
ALERT_ATTEMPT_THROTTLE_SEC: int        = 60
ALERT_SUCCESS_THROTTLE_SEC: int        = 900

# Protocol violation
PROTOCOL_FALLBACK_COOLDOWN_SEC: int = 300
PROTOCOL_ALERT_THRESHOLD: int       = 3
# DESIGN DECISION: PROTOCOL_ALERT_THRESHOLD = BURST detection only.
# Chronic low-rate violations not detected here (future: Supabase counter).

# Drop-reply cooldown (EMPTY_OUTPUT path only — bare triggers exempt)
DROP_REPLY_COOLDOWN_SEC: int = 30

# In-memory state
_delivery_history: list = []
_last_transport_alert_attempt_at: float = 0.0
_last_transport_alert_success_at: float = 0.0
_last_drop_reply: dict = {}
_protocol_fallback_state: dict = {}


def alert_chris(msg):
    """Send urgent alert to Chris via Telegram (non-transport alerts only)."""
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"\u26a0\ufe0f ROBERT ALERT: {msg}"}
        url = f"https://api.telegram.org/bot{ROBERT_BOT_TOKEN}/sendMessage"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log(f"Alert sent: {msg}")
    except Exception as e:
        log(f"Failed to send alert: {e}")


def alert_chris_oob(subject: str, body_text: str) -> None:
    """Send transport/protocol alert via SendGrid — independent of Telegram."""
    try:
        from tools.sendgrid import send_email
        send_email(to='chris@buildtronix.ai',
                   subject=f'[ROBERT TRANSPORT ALERT] {subject}',
                   body=body_text)
        log(f'[ALERT][OOB] Sent via SendGrid: {subject}')
    except Exception as e:
        log(f'[ALERT][FAILED] OOB alert failed: {e!r}')
        try:
            import os as _oa
            _oa.makedirs('/var/lib/robert/logs', exist_ok=True)
            with open('/var/lib/robert/logs/alert_failures.log', 'a') as _af:
                _af.write(f'{datetime.datetime.utcnow().isoformat()} ALERT_FAILED: {subject}\n')
        except Exception:
            pass


def _send_with_fallback(reply_chat_id: str, text: str, pending_msg_id=None) -> bool:
    """Edit pending message; fall back to sendMessage on failure. Returns delivery bool."""
    if pending_msg_id:
        edit_result, edit_err = api_call(
            ROBERT_BOT_TOKEN, 'editMessageText',
            {'chat_id': reply_chat_id, 'message_id': pending_msg_id, 'text': text}
        )
        if edit_err or not (edit_result and edit_result.get('ok')):
            log('[FALLBACK] editMessageText failed — attempting sendMessage')
            send_result, send_err = api_call(
                ROBERT_BOT_TOKEN, 'sendMessage',
                {'chat_id': reply_chat_id, 'text': text}
            )
            if send_err or not (send_result and send_result.get('ok')):
                log(f'[FALLBACK][SEND_FAILED] Both edit and send failed: '
                    f'edit_err={edit_err} send_err={send_err}')
                return False
            return True
        return True
    else:
        send_result, send_err = api_call(
            ROBERT_BOT_TOKEN, 'sendMessage',
            {'chat_id': reply_chat_id, 'text': text}
        )
        if send_err or not (send_result and send_result.get('ok')):
            log(f'[FALLBACK][SEND_FAILED] sendMessage failed: {send_err}')
            return False
        return True


def _record_delivery_result(success: bool, chat_id: str) -> None:
    """Record delivery outcome; fire OOB alert if failure rate threshold exceeded."""
    global _delivery_history, _last_transport_alert_attempt_at, _last_transport_alert_success_at
    now = time.monotonic()
    _delivery_history.append((now, success))
    cutoff = now - DELIVERY_FAILURE_WINDOW_SEC
    _delivery_history = [(ts, ok) for ts, ok in _delivery_history if ts >= cutoff]
    attempts = len(_delivery_history)
    if attempts < DELIVERY_FAILURE_MIN_ATTEMPTS:
        return
    failures = sum(1 for _, ok in _delivery_history if not ok)
    fail_rate = failures / attempts
    log(f'[TRANSPORT] chat_id={chat_id} window={attempts} failures={failures} rate={fail_rate:.0%}')
    if fail_rate < DELIVERY_FAILURE_RATE_THRESHOLD:
        return
    since_attempt = now - _last_transport_alert_attempt_at
    if since_attempt < ALERT_ATTEMPT_THROTTLE_SEC:
        log(f'[ALERT] Attempt throttled — last attempt {since_attempt:.0f}s ago')
        return
    since_success = now - _last_transport_alert_success_at
    if since_success < ALERT_SUCCESS_THROTTLE_SEC:
        log(f'[ALERT] Success throttled — last success {since_success:.0f}s ago')
        return
    _last_transport_alert_attempt_at = now
    subject = (f'Telegram delivery degraded: {fail_rate:.0%} failure rate '
               f'({failures}/{attempts} in {DELIVERY_FAILURE_WINDOW_SEC}s)')
    detail = (f'Robert Telegram delivery failure rate exceeded threshold.\n'
              f'Window: {DELIVERY_FAILURE_WINDOW_SEC}s | Attempts: {attempts} | '
              f'Failures: {failures} | chat_id={chat_id}')
    try:
        alert_chris_oob(subject, detail)
        _last_transport_alert_success_at = now
        log(f'[ALERT][OOB] Sent. Next attempt in {ALERT_ATTEMPT_THROTTLE_SEC}s.')
    except Exception as e:
        log(f'[ALERT][FAILED] {e!r} — throttle NOT updated, will retry')


def _should_send_drop_reply(chat_id: str) -> bool:
    """Rate-limit drop replies on EMPTY_OUTPUT path only. Bare triggers bypass this."""
    now = time.monotonic()
    last = _last_drop_reply.get(chat_id, 0.0)
    if now - last >= DROP_REPLY_COOLDOWN_SEC:
        _last_drop_reply[chat_id] = now
        return True
    log(f'[DROP][COOLDOWN] Suppressing drop reply — last sent {now - last:.0f}s ago')
    return False


def _handle_protocol_violation(reply_chat_id: str, pending_msg_id, signature: str) -> None:
    """Handle missing/invalid reply_status. Burst detection — see design decision above."""
    global _protocol_fallback_state
    now = time.monotonic()
    key = (reply_chat_id, signature)
    evict_before = now - (PROTOCOL_FALLBACK_COOLDOWN_SEC * 2)
    _protocol_fallback_state = {
        k: v for k, v in _protocol_fallback_state.items() if v[0] >= evict_before
    }
    last_sent, count = _protocol_fallback_state.get(key, (0.0, 0))
    count += 1
    if now - last_sent >= PROTOCOL_FALLBACK_COOLDOWN_SEC:
        log(f'[PROTOCOL] violation #{count} sig={signature!r} — sending fallback')
        delivered = _send_with_fallback(
            reply_chat_id,
            'I encountered an internal error processing that. Please try again.',
            pending_msg_id
        )
        _record_delivery_result(delivered, reply_chat_id)
        _protocol_fallback_state[key] = (now, count)
    else:
        log(f'[PROTOCOL] violation #{count} sig={signature!r} — within cooldown, suppressing')
        _protocol_fallback_state[key] = (last_sent, count)
    if count >= PROTOCOL_ALERT_THRESHOLD:
        try:
            alert_chris_oob(
                f'Protocol violation: {signature}',
                f'Robert has seen {count} violations with signature={signature!r}. '
                f'Check reply_status field in graph.py.'
            )
        except Exception as e:
            log(f'[ALERT][FAILED] protocol alert failed: {e!r}')
# ── End RR-0059-rev7 ────────────────────────────────────────────────────────

# ── Structured file logging (P1-2) ──────────────────────────
_LOG_PATH = "/var/lib/robert/logs/robert.log"
try:
    import os
    os.makedirs("/var/lib/robert/logs", exist_ok=True)
    _file_handler = logging.handlers.RotatingFileHandler(
        _LOG_PATH, maxBytes=5*1024*1024, backupCount=5
    )
    _file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _file_logger = logging.getLogger("robert")
    _file_logger.setLevel(logging.INFO)
    _file_logger.addHandler(_file_handler)
    _file_logger.propagate = False
except Exception as _log_setup_err:
    _file_logger = None

def log(msg):
    ts = datetime.datetime.now(datetime.UTC).strftime("%H:%M:%S")
    print(f"[Robert {ts}] {msg}", flush=True)
    if _file_logger:
        _file_logger.info(f"[Robert] {msg}")


def cleanup_checkpoints():
    """P1-1: Checkpoint cleanup disabled at startup — handled by maintenance task.
    Startup path must be non-blocking. SQLite write lock conflicts with LangGraph
    checkpointer during service restarts. Cleanup runs via separate cron/timer."""
    log("[startup] Checkpoint cleanup disabled; handled by maintenance task")

def api_call(token, method, payload=None, timeout=35):
    """Make a Telegram API call."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return None, f"HTTP {e.code}: {body[:200]}"
    except Exception as e:
        return None, str(e)

def send(text):
    """Send message to group."""
    # Clean text for Telegram
    clean = re.sub(r'[*_`#\[\]()]', '', str(text))[:3500]
    result, err = api_call(ROBERT_BOT_TOKEN, "sendMessage", {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": clean
    })
    if err:
        log(f"Send error: {err}")
    return result

def get_updates(offset):
    """Long poll for updates. Blocks up to 30s waiting for messages + callbacks."""
    params = {
        "timeout": 30,
        "limit": 10,
        "allowed_updates": ["message", "callback_query"],
    }
    if offset > 0:
        params["offset"] = offset
    result, err = api_call(ROBERT_BOT_TOKEN, "getUpdates", params, timeout=35)
    if err:
        log(f"Poll error: {err}")
        return []
    return result.get("result", []) if result else []


def _handle_callback_query(callback: dict) -> None:
    """Dispatch Telegram inline-button approvals to BOB contract handler."""
    try:
        from bob_contract import handle_callback
        handle_callback(callback)
        log(f"[callback] Handled callback_query id={callback.get('id')}")
    except Exception as e:
        log(f"[callback] handle_callback failed: {e}")
        alert_chris(f"Approval callback failed: {str(e)[:200]}")

def process(text, from_name, chat_id="default"):
    """Run task through Robert's graph."""
    # Kill switch — block all processing if BOB_DISABLED=true
    try:
        check_kill_switch()
    except RuntimeError as e:
        send(f"SYSTEM HALT: {e}")
        return {"status": "killed", "reason": str(e)}

    try:
        from main import run_task
    except Exception as import_err:
        log(f"[process] Import error loading run_task: {import_err}")
        raise RuntimeError(f"run_task import failed: {import_err}")

    context = memory_store.get_context_summary()
    result = run_task(task=text, context=context, notify=False, chat_id=str(chat_id))
    
    output = result.get("result", "No output.")
    task_entry = {"task": text, "source": "telegram", "from": from_name}
    memory_store.complete_task(task_entry, output)
    memory_store.increment_session()
    
    return result

def run():
    global _last_success_ts, _silence_alerted
    global ROBERT_BOT_ID
    global STARTUP_STATE
    
    cleanup_checkpoints()
    log("Starting Phase 3 listener")

    # Constitutional startup preconditions (git dirty + audit RPC)
    STARTUP_STATE = check_startup_preconditions()
    log(STARTUP_STATE.as_summary())
    if STARTUP_STATE.degraded:
        log("[startup] DEGRADED MODE active — constitutional writes blocked")
    
    # Get bot info
    result, err = api_call(ROBERT_BOT_TOKEN, "getMe")
    if result and result.get("ok"):
        ROBERT_BOT_ID = result["result"]["id"]
        log(f"Bot: @{result['result']['username']} (ID: {ROBERT_BOT_ID})")
    else:
        log(f"Could not get bot info: {err}")
        raise RuntimeError(f"Bot startup failed — getMe returned: {err}")

    # Load last offset
    offset = memory_store.get_telegram_offset()
    log(f"Starting from offset {offset}")

    # Announce once per hour max — persistent across restarts and reboots
    from pathlib import Path
    _throttle_path = Path("/var/lib/robert/last_announcement.ts")
    _throttle_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    # Read — handle missing or corrupt file
    try:
        last_announced = float(_throttle_path.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        last_announced = 0  # Treat as never announced
    if now - last_announced > 3600:
        boot_msg = "Robert online. Sonnet loaded. Listening."
        if STARTUP_STATE and STARTUP_STATE.degraded:
            boot_msg += "\n\nDEGRADED MODE: " + (STARTUP_STATE.degraded_reason or "see logs")
        send(boot_msg)
        # Write — non-fatal if fails
        try:
            _throttle_path.write_text(str(now))
        except (OSError, IOError) as e:
            log(f"Warning: could not write announcement timestamp: {e}")

    while True:
        try:
            updates = get_updates(offset)
            
            for update in updates:
                update_id = update.get("update_id", 0)
                next_offset = update_id + 1
                # Advance in-memory offset for polling continuity; persist only after
                # successful handling so a crash mid-task can redeliver.
                offset = next_offset

                # Inline approval callbacks (Approve / Reject buttons)
                callback = update.get("callback_query")
                if callback:
                    try:
                        _handle_callback_query(callback)
                        memory_store.set_telegram_offset(next_offset)
                    except Exception as cb_err:
                        log(f"[callback] Failed without advancing durable offset: {cb_err}")
                    continue
                
                msg = update.get("message", {})
                if not msg:
                    update_type = next(
                        (k for k in update.keys() if k != "update_id"),
                        "unknown"
                    )
                    log(f"[Robert] Skipping non-message update type: {update_type}")
                    memory_store.set_telegram_offset(next_offset)
                    continue

                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not chat_id:
                    log(f"[Robert] Skipping update with message but no chat.id (update_id={update.get('update_id', 'unknown')})")
                    memory_store.set_telegram_offset(next_offset)
                    continue

                from_user = msg.get("from", {})
                from_id = from_user.get("id", 0)
                from_name = from_user.get("first_name", "Unknown")
                text = msg.get("text", "").strip()
                
                # Accept messages from our group OR direct from Chris
                CHRIS_DIRECT_ID = "8480371994"
                if chat_id != str(TELEGRAM_CHAT_ID) and chat_id != CHRIS_DIRECT_ID:
                    log(f'[DROP][CHAT_FILTER] Wrong chat_id: got {chat_id}')
                    memory_store.set_telegram_offset(next_offset)
                    continue
                # For direct messages, reply to the DM chat not the group
                reply_chat_id = chat_id if chat_id == CHRIS_DIRECT_ID else TELEGRAM_CHAT_ID
                
                # Skip empty messages
                if not text:
                    memory_store.set_telegram_offset(next_offset)
                    continue
                
                # Skip bots UNLESS signed mesh task from BOB (D11 Phase B)
                if from_user.get("is_bot", False):
                    if _is_mesh_task(text):
                        try:
                            _handle_mesh_task_sync(text, chat_id)
                            memory_store.set_telegram_offset(next_offset)
                        except Exception as mesh_err:
                            log(f"[D11] Mesh handling failed — offset not advanced: {mesh_err}")
                    else:
                        memory_store.set_telegram_offset(next_offset)
                    continue
                
                # Skip Robert's own messages
                if from_id == ROBERT_BOT_ID:
                    memory_store.set_telegram_offset(next_offset)
                    continue
                
                log(f"Message from {from_name} ({from_id}): {text[:60]}")
                
                # Only respond to Chris
                if from_id != CHRIS_USER_ID:
                    log(f"Ignoring — not Chris (got {from_id})")
                    memory_store.set_telegram_offset(next_offset)
                    continue

                # RR-0059-rev7: Input normalization
                normalized = text.strip().casefold()
                looks_like_slash = text.strip().startswith(('/', '!'))
                looks_like_command = (normalized in SHORT_COMMANDS) or looks_like_slash

                # Bare trigger — always reply, EXEMPT from cooldown
                bare_triggers = {'robert', 'hey robert', 'hi robert', 'yo robert',
                                 'robert?', '@buildtronix_bobbot'}
                if normalized in bare_triggers:
                    log(f'[DROP][BARE_TRIGGER] {text!r}')
                    delivered = _send_with_fallback(reply_chat_id,
                        'Hey — what do you need? Give me a task or question.')
                    _record_delivery_result(delivered, reply_chat_id)
                    memory_store.set_telegram_offset(next_offset)
                    continue

                # Too short and not a recognized command — silent drop (accidental send)
                if len(text.strip()) < 4 and not looks_like_command:
                    log(f'[DROP][TOO_SHORT] {text!r}')
                    memory_store.set_telegram_offset(next_offset)
                    continue

                # Rate limit Telegram-driven work
                try:
                    from limits import get_limiter
                    allowed, reason = get_limiter().check_telegram()
                    if not allowed:
                        hits = get_limiter().record_rate_limit_hit()
                        log(f"[limits] Telegram rate limited: {reason} (hits={hits})")
                        api_call(ROBERT_BOT_TOKEN, "sendMessage", {
                            "chat_id": reply_chat_id,
                            "text": f"Rate limit: {reason}"
                        })
                        memory_store.set_telegram_offset(next_offset)
                        continue
                except Exception as lim_err:
                    log(f"[limits] Limiter error — fail-open: {lim_err}")

                # Phase 1: Identity resolution + JWT minting
                jwt_token = None
                identity_profile = None
                try:
                    jwt_token, identity_profile = resolve_identity_and_mint(from_id)
                    log(f"[auth] Identity resolved: user_id={identity_profile['user_id']} role={identity_profile['role']}")
                except IdentityNotFoundError as e:
                    log(f"[auth] Identity not found for {from_id}: {e}")
                    alert_chris(f"Identity resolution failed for Telegram user {from_id} — not in profiles table. Message dropped.")
                    memory_store.set_telegram_offset(next_offset)
                    continue
                except JWTMintError as e:
                    log(f"[auth] JWT mint failed: {e}")
                    alert_chris(f"JWT mint error — SUPABASE_JWT_SECRET missing or invalid. Message dropped.")
                    memory_store.set_telegram_offset(next_offset)
                    continue
                except Exception as e:
                    log(f"[auth] Identity resolution error: {e}")
                    alert_chris(f"Unexpected identity resolution error: {str(e)[:200]}. Message dropped.")
                    memory_store.set_telegram_offset(next_offset)
                    continue

                # Phase 2: Role-based permission enforcement
                role = identity_profile.get("role", "GUEST")
                allowed, deny_reason = check_permission(role, text)
                if not allowed:
                    log(f"[auth] Permission denied role={role}: {deny_reason}")
                    api_call(ROBERT_BOT_TOKEN, "sendMessage", {
                        "chat_id": reply_chat_id,
                        "text": f"Permission denied: {deny_reason}"
                    })
                    memory_store.set_telegram_offset(next_offset)
                    continue

                # Typing indicator — send immediately, replace with answer
                pending_msg_id = None
                pending_result, _ = api_call(ROBERT_BOT_TOKEN, "sendMessage", {
                    "chat_id": reply_chat_id,
                    "text": "[PENDING] Working on it..."
                })
                if pending_result and pending_result.get("ok"):
                    pending_msg_id = pending_result["result"]["message_id"]
                # Orchestrator Stack — Witness + Little Voice v1.1
                try:
                    from orchestrator.stack import run_orchestrator_stack
                    orch_result = run_orchestrator_stack(text, identity_profile, memory_store.get_context_summary())
                    if orch_result.get("should_block"):
                        block_reason = orch_result.get("block_reason", "Human approval required.")
                        log(f"[orchestrator] Hard block: {block_reason}")
                        if pending_msg_id:
                            api_call(ROBERT_BOT_TOKEN, "editMessageText", {"chat_id": reply_chat_id, "message_id": pending_msg_id, "text": "WARNING: Approval required:\n\n" + block_reason + "\n\nReply approve or cancel."})
                        else:
                            api_call(ROBERT_BOT_TOKEN, "sendMessage", {"chat_id": reply_chat_id, "text": "WARNING: Approval required:\n\n" + block_reason + "\n\nReply approve or cancel."})
                        memory_store.set_telegram_offset(next_offset)
                        continue
                    if orch_result.get("combined_flags"):
                        log(f"[orchestrator] {len(orch_result['combined_flags'])} non-blocking flags")
                except ImportError:
                    log("[orchestrator] Stack not loaded — fail-open")
                except Exception as orch_err:
                    log(f"[orchestrator] Stack error — fail-open: {orch_err}")

                log(f"Processing: {text[:60]}")
                try:
                    result = process(text, from_name, chat_id=chat_id)
                    # result may be a dict or string
                    # RR-0028: extract reviewer verdict flags BEFORE meaningful-output check
                    if isinstance(result, dict):
                        raw_output = result.get("result") or result.get("output") or ""
                        reviewer_flagged_failure = (
                            result.get("requires_escalation", False)
                            or result.get("needs_revision", False)
                        )
                        # If escalated/failed and output is bare/empty, surface the actual reason
                        if reviewer_flagged_failure and (not raw_output or len(raw_output.strip()) < 20):
                            escalate_reason = result.get("escalate_reason", "")
                            revision_notes = result.get("revision_notes", "")
                            error = result.get("error", "")
                            reason = escalate_reason or revision_notes or error or "Task could not be completed after review."
                            output = f"I wasn't able to complete that task. Reason: {reason[:300]}"
                        else:
                            output = raw_output if raw_output else "I processed that but had nothing to return."
                    else:
                        output = str(result) if result else "I processed that but had nothing to return."
                        reviewer_flagged_failure = False
                    # Strip markdown that breaks Telegram plain text
                    output = output.strip()[:3500]
                    # RR-0059-rev7: typed reply_status replaces empty-string inference
                    reply_status = result.get('reply_status', None) if isinstance(result, dict) else None
                    if reply_status is None:
                        log('[PROTOCOL] reply_status missing — producer bug, defaulting to FAILURE')
                        _handle_protocol_violation(reply_chat_id, pending_msg_id, 'missing_reply_status')
                        memory_store.set_telegram_offset(next_offset)
                        continue
                    elif reply_status not in ('SUCCESS_REPLY', 'SUCCESS_NO_REPLY', 'FAILURE'):
                        log(f'[PROTOCOL] Unknown reply_status={reply_status!r} — defaulting to FAILURE')
                        _handle_protocol_violation(reply_chat_id, pending_msg_id, f'unknown:{reply_status}')
                        memory_store.set_telegram_offset(next_offset)
                        continue
                    if not output:
                        if reply_status == 'SUCCESS_NO_REPLY':
                            log('[FILTER] Silent completion — no reply expected')
                            if pending_msg_id:
                                api_call(ROBERT_BOT_TOKEN, "deleteMessage", {
                                    "chat_id": reply_chat_id,
                                    "message_id": pending_msg_id
                                })
                        else:
                            log('[EMPTY_OUTPUT] process() returned empty — sending fallback')
                            if _should_send_drop_reply(reply_chat_id):
                                delivered = _send_with_fallback(
                                    reply_chat_id,
                                    'I processed that but could not generate a response. '
                                    'Try rephrasing or give me more detail.',
                                    pending_msg_id
                                )
                                _record_delivery_result(delivered, reply_chat_id)
                            elif pending_msg_id:
                                api_call(ROBERT_BOT_TOKEN, "deleteMessage", {
                                    "chat_id": reply_chat_id,
                                    "message_id": pending_msg_id
                                })
                        memory_store.set_telegram_offset(next_offset)
                        continue
                    # Replace the pending indicator with the real answer
                    delivered = _send_with_fallback(reply_chat_id, output, pending_msg_id)
                    _record_delivery_result(delivered, reply_chat_id)
                    log("Response sent.")
                    memory_store.set_telegram_offset(next_offset)
                except Exception as e:
                    log(f"Process error: {e}")
                    err_text = f"Error processing task: {str(e)[:200]}"
                    alert_chris(f"Task execution failed: {str(e)[:200]}")
                    if pending_msg_id:
                        api_call(ROBERT_BOT_TOKEN, "editMessageText", {
                            "chat_id": reply_chat_id,
                            "message_id": pending_msg_id,
                            "text": err_text
                        })
                    else:
                        api_call(ROBERT_BOT_TOKEN, "sendMessage", {"chat_id": reply_chat_id, "text": err_text})
                    # Persist offset after user was notified — avoids infinite redelivery loops.
                    # Crash before this line leaves offset unadvanced for redelivery.
                    memory_store.set_telegram_offset(next_offset)
                else:
                    # Task succeeded at listener level — check reviewer verdict before
                    # updating silence tracker (RR-0028: reviewer escalation = task failure)
                    if reviewer_flagged_failure:
                        log(f"Task flagged as failed by reviewer (requires_escalation or needs_revision) — not updating silence tracker")
                    else:
                        # Meaningful = non-empty, non-whitespace, not error-prefixed,
                        # not a bare ack, and length > 20 chars
                        bare_acks = {'ok', 'done', 'completed', 'success', 'acknowledged', 'roger'}
                        stripped = output.strip()
                        is_meaningful = (
                            len(stripped) > 20
                            and not stripped.lower().startswith('error')
                            and stripped.lower() not in bare_acks
                        )
                        if is_meaningful:
                            _last_success_ts = time.time()
                            _silence_alerted = False
                        else:
                            log(f"Task returned clean but output not meaningful: {stripped[:80]!r} — not resetting silence timer")

        except KeyboardInterrupt:
            log("Shutting down.")
            send("Robert going offline.")
            break
        except Exception as e:
            log(f"[loop] Recoverable error — staying alive: {e}")
            alert_chris(f"Listener loop error: {str(e)[:200]}")
            time.sleep(10)
            log("[loop] Resuming poll after error")

        # Silence heartbeat check — alert if no successful task in N hours
        hours_silent = (time.time() - _last_success_ts) / 3600
        if hours_silent >= SILENCE_ALERT_HOURS and not _silence_alerted:
            alert_chris(f"Robert has been silent for {hours_silent:.1f} hours — no successful task completed. Check service logs.")
            _silence_alerted = True

if __name__ == "__main__":
    run()
