"""
Policy Gate — Gate 1
Thin wrapper around classify_action() that nodes call before
any tool execution, shell command, or DB write.

Usage:
    from policy_gate import gate

    gate("run_script", target="script.py", reversible=True)
    run_command(...)  # only reached if GREEN or approved

GREEN  actions proceed automatically.
YELLOW actions proceed automatically in v1.1 (approval wiring is Gate 2).
RED    actions raise PermissionError — must be escalated to Chris.
DENY   actions raise PermissionError immediately.

Gate 1 goal: call sites exist, decisions are logged to Supabase.
Gate 2 goal: YELLOW pauses for approval, RED hard-blocks until 3 approvals.
"""

import sys
import os
import json
import hashlib
import urllib.request
import urllib.error
from datetime import datetime

sys.path.insert(0, '/var/lib/robert/workspace')
from policy_engine import classify_action, check_kill_switch, RiskTier
from tronix_human_protection import reject_if_human, TronixHumanNodeViolation, HumanEscalationRequired


def _build_idempotency_key(action_type: str, target: str, payload_hash: str, originating_task_id: str) -> str:
    """
    Build a deterministic idempotency key binding:
      - action_type    (what is being done)
      - target         (what it's being done to)
      - payload_hash   (exact execution content)
      - originating_task_id (decision lineage)

    Same action + same target + same payload + same task → same key → blocked.
    Different payload → different key → allowed.
    """
    components = json.dumps({
        "action_type": action_type,
        "target": target,
        "payload_hash": payload_hash,
        "originating_task_id": originating_task_id,
    }, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(components.encode()).hexdigest()


def _check_and_claim_idempotency(idempotency_key: str, action_type: str, target: str,
                                  payload_hash: str, originating_task_id: str,
                                  decision_id: str) -> None:
    """
    TTL-aware idempotency check via claim_idempotency_key() Postgres function.

    Behavior:
    - Key absent: INSERT and proceed (allowed)
    - Key present, NOT expired: duplicate — BLOCKED
    - Key present, EXPIRED: delete old row, INSERT new, proceed (TTL re-execution allowed)
    - Supabase unavailable: FAIL-CLOSED — execution blocked

    No soft fallback. No silent continue.
    """
    db_url = os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        print(f"[GATE] MISSING_SUPABASE_CONFIG: cannot check idempotency — BLOCKED")
        raise PermissionError(
            f"[GATE] IDEMPOTENCY_CHECK_FAILED: No SUPABASE_DB_URL. "
            f"Cannot verify '{action_type}' is not a duplicate. Execution blocked."
        )
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            "SELECT claim_idempotency_key(%s, %s, %s, %s, %s, %s)",
            (idempotency_key, action_type, target, payload_hash,
             originating_task_id, decision_id)
        )
        result = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        if result == "duplicate":
            print(f"[GATE] DUPLICATE_EXECUTION_BLOCKED: key {idempotency_key[:16]}... within TTL window")
            raise PermissionError(
                f"[GATE] DUPLICATE_EXECUTION_BLOCKED: '{action_type}' on '{target}' "
                f"with key {idempotency_key[:16]}... was already executed within the 24h window. "
                f"Identical action+target+payload is a duplicate. Execution blocked."
            )
        elif result == "allowed":
            print(f"[GATE] IDEMPOTENCY: key {idempotency_key[:16]}... claimed — proceeding")
        else:
            # Unknown return from DB function — fail-closed
            raise PermissionError(
                f"[GATE] IDEMPOTENCY_CHECK_FAILED: unexpected result '{result}' — execution blocked."
            )
    except PermissionError:
        raise  # re-raise our own blocks unchanged
    except Exception as e:
        print(f"[GATE] IDEMPOTENCY_CHECK_FAILED: {e} — BLOCKED")
        raise PermissionError(
            f"[GATE] IDEMPOTENCY_CHECK_FAILED: Cannot reach Supabase to check idempotency. "
            f"Execution blocked."
        )


def _verify_approval_signature(approver_id: str, approval_type: str,
                               approved_hash: str, signature_b64: str,
                               decision_id: str = "", nonce: str = "",
                               expires_at: str = "", interaction_id: str = "",
                               action_type: str = "", target: str = "") -> bool:
    """
    Verify Ed25519 signature on an approval using canonical_approval().

    Uses THE SAME canonical() function as the signer service.
    If the canonical output differs between signer and verifier, verification fails.
    No silent coercion. No datetime objects. No extra fields.

    Returns True only if signature is valid. Returns False on any failure (never raises).
    """
    try:
        import base64, psycopg2 as _pg
        import sys as _sys
        _sys.path.insert(0, '/root/.openclaw/workspace/scripts')
        from approval_canonical import canonical_approval

        db_url = os.environ.get("SUPABASE_DB_URL", "")
        if not db_url:
            print(f"[GATE] SIG_VERIFY: no DB URL — cannot fetch public key for {approver_id}")
            return False

        conn = _pg.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT public_key_b64 FROM approver_keys
            WHERE approver_id = %s AND active = true
            LIMIT 1;
        """, (approver_id,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if not row:
            print(f"[GATE] SIG_VERIFY: no active public key for approver '{approver_id}'")
            return False

        pub_bytes = base64.urlsafe_b64decode(row[0] + "==")
        sig_bytes = base64.urlsafe_b64decode(signature_b64 + "==")

        # Reconstruct canonical payload — MUST match signer exactly
        # expires_at must be a string (ISO8601 with T) — canonical_approval() enforces this
        msg = canonical_approval({
            "payload_hash":   approved_hash,
            "decision_id":    decision_id,
            "nonce":          nonce,
            "expires_at":     expires_at,
            "approver_id":    approver_id,
            "interaction_id": interaction_id,
            "action_type":    action_type,
            "target":         target,
        })

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(sig_bytes, msg)  # raises InvalidSignature on failure
        return True

    except Exception as e:
        name = type(e).__name__
        print(f"[GATE] SIG_VERIFY: FAILED for {approver_id} ({name}): {str(e)[:80]}")
        return False


# Quorum requirements per tier
_QUORUM_REQUIREMENTS = {
    # YELLOW: 1 approval of any type (Gate 1 exempts, Gate 2+ enforces)
    "YELLOW": {"count": 1, "required_types": {"human"}},
    # RED: 3 approvals, one of each type
    "RED":    {"count": 3, "required_types": {"finance", "qc", "human"}},
}

# Approvers authorized by type
_AUTHORIZED_APPROVERS = {
    "human":   {"chris", "chris_leiser", "8480371994"},
    "finance": {"chris", "chris_leiser", "bill_agent"},
    "qc":      {"chris", "chris_leiser", "reviewer_agent"},
}


def _check_approvals(decision_id: str, payload_hash: str, tier: str,
                     action_type: str = "", target: str = "") -> None:
    """
    Phase 3: Enforce quorum before execution proceeds.

    Rules:
    - YELLOW tier: 1 approval (type: human) required
    - RED tier:    3 approvals (finance + qc + human) required
    - Approval must match current payload_hash (hash binding, not decision_id alone)
    - Approval must not be expired (1h window)
    - Duplicate approval from same approver blocked (UNIQUE constraint)
    - Any DB failure → FAIL-CLOSED

    Gate 1 exemption: called only when GATE_LEVEL env var >= 2.
    Gate 1 logs decisions but does not enforce approvals.
    """
    gate_level = int(os.environ.get("ROBERT_GATE_LEVEL", "1"))
    if gate_level < 2:
        print(f"[GATE] Phase 3 approval check: Gate {gate_level} — logging only, not enforcing")
        return  # Gate 1: log path, no enforcement

    quorum = _QUORUM_REQUIREMENTS.get(tier)
    if not quorum:
        return  # GREEN — no approvals required

    db_url = os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        raise PermissionError(
            f"[GATE] APPROVAL_CHECK_FAILED: No SUPABASE_DB_URL. "
            f"Cannot verify approvals for '{tier}' action. Execution blocked."
        )

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        # Fetch all non-expired approvals for this decision
        cur.execute("""
            SELECT approver_id, approval_type, approved_hash, expires_at,
                   signature, public_key_id, nonce, interaction_id,
                   canonical_expires_at
            FROM approvals
            WHERE decision_id = %s
              AND expires_at > now()
        """, (decision_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        raise PermissionError(
            f"[GATE] APPROVAL_CHECK_FAILED: DB error fetching approvals: {e}. Execution blocked."
        )

    # Validate each approval: hash + signature + interaction_id + authorization
    valid_approvals = []
    for approver_id, approval_type, approved_hash, expires_at, signature, public_key_id, nonce, interaction_id, canonical_expires_at in rows:
        # 1. Hash must match current payload
        if approved_hash != payload_hash:
            print(f"[GATE] APPROVAL_HASH_MISMATCH: approver={approver_id} "
                  f"approved_hash={approved_hash[:16]}... != current={payload_hash[:16]}...")
            continue
        # 2. Signature must be present
        if not signature:
            print(f"[GATE] UNSIGNED_APPROVAL: approver={approver_id} has no signature — rejected")
            continue
        # 3. interaction_id must be present (no anonymous approvals)
        if not interaction_id:
            print(f"[GATE] MISSING_INTERACTION_ID: approver={approver_id} — rejected")
            continue
        # 4. Use canonical_expires_at (exact string the signer used) — NOT isoformat() on DB datetime
        # This is the fix for Attack 8: DB normalizes timestamptz and isoformat() could
        # silently produce a different string than what was signed.
        # canonical_expires_at stores the raw ISO8601 string from the signer, verbatim.
        if canonical_expires_at:
            expires_at_str = canonical_expires_at
        else:
            # Fallback for rows pre-dating this column (old approvals)
            expires_at_str = expires_at.isoformat() if hasattr(expires_at, 'isoformat') else str(expires_at)
            print(f"[GATE] WARN: no canonical_expires_at for approver={approver_id} — using isoformat() fallback")
        # 5. Verify signature using shared canonical_approval() function
        if not _verify_approval_signature(
            approver_id, approval_type, approved_hash, signature,
            decision_id=decision_id,
            nonce=nonce or "",
            expires_at=expires_at_str,
            interaction_id=interaction_id or "",
            action_type=action_type,
            target=target or "",
        ):
            print(f"[GATE] INVALID_SIGNATURE: approver={approver_id} signature verification failed")
            continue
        # 6. Approver must be authorized for this type
        authorized = _AUTHORIZED_APPROVERS.get(approval_type, set())
        if approver_id not in authorized:
            print(f"[GATE] UNAUTHORIZED_APPROVER: {approver_id} not authorized for type '{approval_type}'")
            continue
        print(f"[GATE] APPROVAL_VALID: approver={approver_id} type={approval_type} "
              f"interaction={interaction_id[:16]}... sig=verified")
        valid_approvals.append((approver_id, approval_type))

    valid_types = {atype for _, atype in valid_approvals}
    valid_count = len(valid_approvals)

    # Check quorum
    missing_types = quorum["required_types"] - valid_types
    if valid_count < quorum["count"] or missing_types:
        print(f"[GATE] APPROVAL_QUORUM_MISSING: tier={tier} "
              f"have={valid_count}/{quorum['count']} types={valid_types} "
              f"missing_types={missing_types}")
        raise PermissionError(
            f"[GATE] APPROVAL_REQUIRED: '{tier}' action requires "
            f"{quorum['count']} approval(s) of type(s) {quorum['required_types']}. "
            f"Have {valid_count} valid approval(s), types={valid_types}. "
            f"Missing: {missing_types}. Execution blocked."
        )

    print(f"[GATE] APPROVALS_VERIFIED: {valid_count} valid approval(s) for tier={tier} "
          f"types={valid_types} — proceeding")


def _persist_decision(decision, execution_payload: dict = None) -> None:
    """Write decision to Supabase policy_decisions table. Fail loudly on error."""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        print(f"[GATE] WARNING: No Supabase config — decision {decision.decision_id} not persisted")
        return

    # Compute payload_hash (SHA-256 of canonical JSON of FULL execution payload)
    # Phase 0 condition 2: hash must cover actual executable content, not just metadata
    # If execution_payload provided, it takes precedence — this is what actually runs
    # If not provided, hash decision metadata (backward-compat, but lower integrity guarantee)
    payload_for_hash = {
        "decision_id": decision.decision_id,
        "action_type": decision.action_type,
        "target": decision.target or "",
        "execution_payload": execution_payload,
    }
    canonical = json.dumps(payload_for_hash, sort_keys=True, separators=(',', ':'))
    payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
    print(f"[GATE] payload_hash: {payload_hash[:16]}... (full execution payload bound)")

    row = {
        "decision_id": decision.decision_id,
        "action_type": decision.action_type,
        "target": decision.target or "",
        "data_sensitivity": decision.data_sensitivity,
        "reversible": decision.reversible,
        "request_source": decision.request_source,
        "tier": decision.tier,
        "confidence": decision.confidence,
        "approved": decision.approved,
        "deny_reason": decision.deny_reason,
        "approvals_required": decision.approvals_required,
        "approvals_received": decision.approvals_received,
        "created_at": decision.created_at,
        "expires_at": decision.expires_at,
        "signature": decision.signature,
        "payload_hash": payload_hash,
    }

    for attempt in range(2):
        try:
            data = json.dumps(row).encode()
            req = urllib.request.Request(
                f"{url}/rest/v1/policy_decisions",
                data=data,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            print(f"[GATE] Decision {decision.decision_id} persisted ({decision.tier})")
            return
        except Exception as e:
            print(f"[GATE] Persist attempt {attempt+1} failed: {e}")

    # Both attempts failed
    # FAIL-CLOSED: Phase 0 directive — if decision write fails, BLOCK execution
    # This ensures no action proceeds without an audit record
    _alert_gate_failure(decision.decision_id, decision.action_type)
    raise PermissionError(
        f"[GATE] FAIL-CLOSED: Decision {decision.decision_id} for '{decision.action_type}' "
        f"could not be persisted to Supabase after 2 attempts. "
        f"Execution blocked. Audit trail integrity required."
    )


def _alert_gate_failure(decision_id: str, action_type: str) -> None:
    """Alert Chris if policy decision cannot be persisted."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        msg = (
            f"⚠️ POLICY GATE FAILURE\n"
            f"Decision {decision_id} for action '{action_type}' "
            f"could not be persisted to Supabase.\n"
            f"Audit trail incomplete."
        )
        data = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def gate(
    action_type: str,
    target: str = "",
    data_sensitivity: str = "internal",
    reversible: bool = True,
    confidence: float = 1.0,
    content_flags: list = None,
    execution_payload: dict = None,  # Phase 0 expanded: actual command/script/params being executed
) -> None:
    """
    Policy gate — call before any tool execution.
    Raises PermissionError for RED/DENY actions.
    Logs all decisions to Supabase.

    Gate 1 behavior: GREEN/YELLOW proceed; RED/DENY raise.
    Gate 2 will add YELLOW pause-for-approval.
    """
    check_kill_switch()

    # RR-0056 Phase 1 — Human Node Protection
    # Enforce before any classification or execution.
    # DENY: raises TronixHumanNodeViolation (maps to PermissionError)
    # ESCALATE: raises HumanEscalationRequired (maps to PermissionError)
    if target:
        try:
            reject_if_human(
                node_id=target,
                operation=action_type,
                agent_id="robert",
            )
        except TronixHumanNodeViolation as e:
            raise PermissionError(f"[GATE] HUMAN_NODE_VIOLATION: {e}") from e
        except HumanEscalationRequired as e:
            raise PermissionError(f"[GATE] HUMAN_ESCALATION_REQUIRED: {e}") from e

    # FAIL-CLOSED: execution_payload REQUIRED — no fallback path
    # Must be checked before classify_action to block before any processing
    if not execution_payload:
        print(f"[GATE] MISSING_EXECUTION_PAYLOAD: action='{action_type}' target='{target}' — BLOCKED")
        raise PermissionError(
            f"[GATE] MISSING_EXECUTION_PAYLOAD: '{action_type}' on '{target}' cannot proceed. "
            f"execution_payload is required for all gated executions. "
            f"Pass execution_payload={{...}} to gate() at this call site."
        )

    # STEP 1: Classify (no side effects — pure risk assessment)
    decision = classify_action(
        action_type=action_type,
        target=target,
        data_sensitivity=data_sensitivity,
        reversible=reversible,
        request_source="robert",
        confidence=confidence,
        content_flags=content_flags or [],
    )

    # STEP 2: Sign the decision token (no side effects)
    token = decision.to_token()
    import json as _json
    payload = _json.loads(token)
    decision.signature = payload.get("signature")

    # STEP 3: Compute payload_hash (no side effects)
    _payload_for_key = json.dumps({
        "action_type": action_type,
        "target": target or "",
        "execution_payload": execution_payload,
    }, sort_keys=True, separators=(',', ':'))
    _payload_hash = hashlib.sha256(_payload_for_key.encode()).hexdigest()
    _originating_task_id = str(execution_payload.get("originating_task_id") or
                               execution_payload.get("originating_decision_id") or
                               execution_payload.get("task", "")[:80] or
                               "unset")
    _idempotency_key = _build_idempotency_key(
        action_type=action_type,
        target=target or "",
        payload_hash=_payload_hash,
        originating_task_id=_originating_task_id,
    )

    # STEP 4: RED/DENY block — before any DB write or idempotency claim
    # A RED/DENY action must never consume an idempotency slot or produce an audit record
    # that implies it was evaluated for execution.
    if decision.tier == RiskTier.RED.value:
        raise PermissionError(
            f"[GATE] RED action blocked: '{action_type}' on '{target}'. "
            f"Requires 3 approvals from Chris. Escalate via Telegram."
        )
    if decision.tier == RiskTier.DENY.value:
        raise PermissionError(
            f"[GATE] DENY: '{action_type}' blocked. Reason: {decision.deny_reason}"
        )

    # STEP 5: Idempotency check — AFTER classification, BEFORE persist or execution
    # If this raises, nothing has been written to Supabase and no execution has occurred.
    _check_and_claim_idempotency(
        idempotency_key=_idempotency_key,
        action_type=action_type,
        target=target or "",
        payload_hash=_payload_hash,
        originating_task_id=_originating_task_id,
        decision_id=decision.decision_id,
    )

    # STEP 6: Approval quorum check — AFTER idempotency, BEFORE persist or execution
    # Gate 1: logs only. Gate 2+: enforces quorum.
    # Approval must match _payload_hash (hash binding, not decision_id alone).
    _check_approvals(
        decision_id=decision.decision_id,
        payload_hash=_payload_hash,
        tier=decision.tier,
        action_type=action_type,
        target=target or "",
    )

    # STEP 7: Persist decision record — after all guards pass
    # At this point: not duplicate, not RED/DENY, approvals verified.
    _persist_decision(decision, execution_payload=execution_payload)

    # STEP 8: Return to caller — execution may proceed
    if decision.tier == RiskTier.YELLOW.value:
        print(f"[GATE] YELLOW: '{action_type}' proceeding (Gate 2 will require approval)")

    print(f"[GATE] {decision.tier}: '{action_type}' -> '{target}' approved (id={decision.decision_id[:8]})")
