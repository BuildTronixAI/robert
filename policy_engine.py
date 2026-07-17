"""
Policy Engine v1 — D11
Default-deny action classification with hard escalation guardrails.
Control Plane: classifies and signs decisions.
Execution Plane: verifies signed token before acting.
"""

import os
import json
import hmac
import hashlib
import secrets
import time
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional

# ─── Kill Switch ──────────────────────────────────────────────────────────────
def check_kill_switch():
    """Must be called at the top of every action. Raises if BOB is disabled."""
    if os.environ.get("BOB_DISABLED", "").lower() in ("true", "1", "yes"):
        raise RuntimeError("BOB_DISABLED=true — all actions blocked. Contact Chris.")

# ─── Action Classification ────────────────────────────────────────────────────

class RiskTier(str, Enum):
    GREEN  = "GREEN"   # Execute autonomously
    YELLOW = "YELLOW"  # Single approval required
    RED    = "RED"     # Triple approval required (RED_30F3)
    DENY   = "DENY"    # Automatic block

# Five hard-escalation classes — ALWAYS RED regardless of confidence
HARD_ESCALATION_CLASSES = {
    "financial_transaction",    # payments, transfers, invoices
    "client_commitment",        # contracts, proposals sent externally
    "permission_change",        # RLS, user roles, API access grants
    "production_deployment",    # Vercel prod deploys, DB migrations on prod
    "api_key_rotation",         # rotating or generating credentials
}

# Action type → default tier (can be overridden by confidence or content)
ACTION_TIERS = {
    # GREEN — safe autonomous operations
    "read_file":              RiskTier.GREEN,
    "read_database":          RiskTier.GREEN,
    "write_log":              RiskTier.GREEN,
    "send_internal_message":  RiskTier.GREEN,
    "run_test":               RiskTier.GREEN,
    "lint_code":              RiskTier.GREEN,
    "schema_introspect":      RiskTier.GREEN,
    "vercel_preview_deploy":  RiskTier.GREEN,

    # YELLOW — single approval
    "write_database":         RiskTier.YELLOW,
    "send_external_message":  RiskTier.YELLOW,
    "git_push":               RiskTier.YELLOW,
    "create_record":          RiskTier.YELLOW,
    "update_record":          RiskTier.YELLOW,
    "delete_record":          RiskTier.YELLOW,
    "run_script":             RiskTier.YELLOW,  # temporary execution
    "create_user":            RiskTier.YELLOW,
    # commit_artifact: permanent state change — higher tier than run_script
    # Irreversible by default — policy_engine escalates non-reversible GREEN→YELLOW
    # but we set YELLOW explicitly and mark reversible=False so it escalates to RED
    # at Gate 2. For Gate 1: YELLOW (logs + proceeds). Gate 2: RED (requires approval).
    "commit_artifact":        RiskTier.YELLOW,  # permanent persistence of execution result
    "git_commit_branch":      RiskTier.GREEN,   # robert/auto/* branches only (non-artifact)

    # RED — triple approval (hard escalation classes override to RED always)
    "financial_transaction":  RiskTier.RED,
    "client_commitment":      RiskTier.RED,
    "permission_change":      RiskTier.RED,
    "production_deployment":  RiskTier.RED,
    "api_key_rotation":       RiskTier.RED,
    "delete_database":        RiskTier.RED,
    "schema_change":          RiskTier.RED,
    "send_email_external":    RiskTier.RED,
}

@dataclass
class PolicyDecision:
    decision_id: str
    action_type: str
    target: str
    data_sensitivity: str        # "public" | "internal" | "confidential" | "restricted"
    reversible: bool
    request_source: str          # "robert" | "bob" | "scout" | "ava" | "human"
    tier: str                    # RiskTier value
    confidence: float            # 0.0 - 1.0
    approved: bool
    deny_reason: Optional[str]
    approvals_required: int      # 0, 1, or 3
    approvals_received: int
    created_at: str
    expires_at: str
    signature: Optional[str] = None

    def to_token(self) -> str:
        """Serialize to signed JSON token for Execution Plane verification."""
        payload = asdict(self)
        payload.pop("signature", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        secret = os.environ.get("BOB_SHARED_SECRET", "dev-secret")
        sig = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        payload["signature"] = sig
        return json.dumps(payload)

    @classmethod
    def from_token(cls, token: str) -> "PolicyDecision":
        """Verify and deserialize a signed token."""
        payload = json.loads(token)
        sig = payload.pop("signature", None)
        if not sig:
            raise ValueError("Token missing signature")
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        secret = os.environ.get("BOB_SHARED_SECRET", "dev-secret")
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Token signature invalid")
        # Check expiry
        expires_str = payload["expires_at"].rstrip("Z")
        expires = datetime.fromisoformat(expires_str).replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise ValueError("Token expired")
        payload["signature"] = sig
        return cls(**payload)


def classify_action(
    action_type: str,
    target: str = "",
    data_sensitivity: str = "internal",
    reversible: bool = True,
    request_source: str = "robert",
    confidence: float = 1.0,
    content_flags: list[str] = None,
) -> PolicyDecision:
    """
    Classify an action and return a PolicyDecision.
    This is the Control Plane — it never executes, only decides.
    """
    check_kill_switch()

    content_flags = content_flags or []
    now = datetime.now(timezone.utc)
    decision_id = secrets.token_hex(12)

    # Hard escalation: content flags override everything
    hard_escalated = action_type in HARD_ESCALATION_CLASSES or any(
        f in HARD_ESCALATION_CLASSES for f in content_flags
    )

    # Confidence band logic
    # < 0.4 → automatic DENY
    # 0.4 - 0.7 → escalate one tier up
    if confidence < 0.4:
        return PolicyDecision(
            decision_id=decision_id,
            action_type=action_type,
            target=target,
            data_sensitivity=data_sensitivity,
            reversible=reversible,
            request_source=request_source,
            tier=RiskTier.DENY.value,
            confidence=confidence,
            approved=False,
            deny_reason=f"Confidence {confidence:.2f} below minimum threshold (0.4)",
            approvals_required=0,
            approvals_received=0,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=30)).isoformat(),
        )

    # Determine base tier
    if hard_escalated:
        tier = RiskTier.RED
    else:
        tier = ACTION_TIERS.get(action_type, RiskTier.YELLOW)  # default YELLOW for unknown

        # Confidence band: 0.4-0.7 escalates one tier
        if 0.4 <= confidence < 0.7:
            if tier == RiskTier.GREEN:
                tier = RiskTier.YELLOW
            elif tier == RiskTier.YELLOW:
                tier = RiskTier.RED

        # Irreversible actions escalate one tier
        if not reversible and tier == RiskTier.GREEN:
            tier = RiskTier.YELLOW

        # Restricted data always at least YELLOW
        if data_sensitivity == "restricted" and tier == RiskTier.GREEN:
            tier = RiskTier.YELLOW

    # Approval requirements
    approvals_map = {
        RiskTier.GREEN:  0,
        RiskTier.YELLOW: 1,
        RiskTier.RED:    3,
        RiskTier.DENY:   0,
    }
    approvals_required = approvals_map[tier]

    # GREEN actions are auto-approved
    approved = tier == RiskTier.GREEN

    return PolicyDecision(
        decision_id=decision_id,
        action_type=action_type,
        target=target,
        data_sensitivity=data_sensitivity,
        reversible=reversible,
        request_source=request_source,
        tier=tier.value,
        confidence=confidence,
        approved=approved,
        deny_reason=None,
        approvals_required=approvals_required,
        approvals_received=1 if approved else 0,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=30)).isoformat(),
    )


def verify_and_execute(token: str, execute_fn, *args, **kwargs):
    """
    Execution Plane gate. Verifies signed decision token before running action.
    execute_fn is only called if token is valid and decision is approved.
    """
    check_kill_switch()

    try:
        decision = PolicyDecision.from_token(token)
    except ValueError as e:
        raise PermissionError(f"Decision token invalid: {e}")

    if not decision.approved:
        raise PermissionError(
            f"Action '{decision.action_type}' not approved. "
            f"Tier: {decision.tier}. "
            f"Reason: {decision.deny_reason or 'Pending approvals'}"
        )

    if decision.approvals_received < decision.approvals_required:
        raise PermissionError(
            f"Action '{decision.action_type}' requires {decision.approvals_required} approvals, "
            f"has {decision.approvals_received}."
        )

    return execute_fn(*args, **kwargs)
