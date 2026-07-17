"""
auth/jwt_minter.py — Robert JWT Minter
=======================================
Mints short-lived Supabase JWTs for identity-scoped Supabase access.
JWT expires in 60 seconds — scoped to one request cycle only.

This is the ONLY authorized path for minting user JWTs.
Service_role is used ONLY for the profiles lookup (approved carveout).
All subsequent Supabase operations use the minted JWT via RLS.

Requires:
  - SUPABASE_JWT_SECRET in /etc/robert/secrets.env
  - SUPABASE_URL in /etc/robert/secrets.env
  - pip install PyJWT>=2.0.0
"""

import jwt
import time
import os
import urllib.request
import urllib.error
import json
import logging

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
SUPABASE_REF        = "xdgbsoxsxsdrgwfihsdx"  # BuildTronixAI's Project
SUPABASE_URL        = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY        = os.environ.get("SUPABASE_SERVICE_KEY", "")

JWT_EXPIRY_SECONDS  = 60   # Per-request scope — short-lived by design


class IdentityNotFoundError(Exception):
    """Raised when telegram_user_id is not in profiles table."""
    pass


class JWTMintError(Exception):
    """Raised when JWT cannot be minted (missing secret, etc.)."""
    pass


def _check_secret():
    if not SUPABASE_JWT_SECRET:
        raise JWTMintError(
            "SUPABASE_JWT_SECRET is not set. "
            "Check /etc/robert/secrets.env. "
            "This is required for JWT auth migration."
        )


def mint_user_jwt(user_id: str, role: str, org_id: str | None, project_ids: list) -> str:
    """
    Mint a short-lived JWT for Robert to act as a specific user during a request.
    JWT expires in 60 seconds — scoped to one message/request cycle.

    Args:
        user_id:     Supabase UUID (profiles.id)
        role:        buildtronix_role (OWNER, PM, FIELD_SUPER, etc.)
        org_id:      UUID string or None (OWNER has no org restriction)
        project_ids: List of UUID strings the user can access

    Returns:
        Signed JWT string

    Raises:
        JWTMintError: If SUPABASE_JWT_SECRET is missing or JWT encoding fails
    """
    _check_secret()

    now = int(time.time())
    payload = {
        "iss":  "supabase",
        "ref":  SUPABASE_REF,
        "role": "authenticated",
        "sub":  user_id,
        "aud":  "authenticated",
        "iat":  now,
        "exp":  now + JWT_EXPIRY_SECONDS,
        "app_metadata": {
            "buildtronix_role": role,
            "org_id":           org_id,
            "project_ids":      project_ids or [],
        },
    }

    try:
        token = jwt.encode(payload, SUPABASE_JWT_SECRET, algorithm="HS256")
        logger.debug(f"[jwt_minter] Minted JWT for user_id={user_id} role={role} exp={now + JWT_EXPIRY_SECONDS}")
        return token
    except Exception as e:
        raise JWTMintError(f"JWT encoding failed: {e}") from e


def resolve_identity_and_mint(telegram_user_id: int) -> tuple[str, dict]:
    """
    Resolve a Telegram user_id to a Buildtronix identity and mint a request-scoped JWT.

    Uses auth_internal.resolve_identity() RPC (SECURITY DEFINER) — the approved
    service_role carveout for identity resolution only.

    Args:
        telegram_user_id: Integer Telegram user ID

    Returns:
        Tuple of (jwt_token: str, profile: dict)
        profile contains: user_id, role, org_id, project_ids

    Raises:
        IdentityNotFoundError: Telegram user not in profiles
        JWTMintError: Secret missing or encoding failure
        RuntimeError: Supabase RPC call failed
    """
    _check_secret()

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")

    # Call the resolve_identity RPC (service_role — approved carveout)
    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/resolve_identity"
    payload  = json.dumps({"p_telegram_user_id": telegram_user_id}).encode()

    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={
            "apikey":       SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Accept":       "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 404 or "P0002" in body or "not found" in body.lower():
            raise IdentityNotFoundError(
                f"Telegram user {telegram_user_id} not found in profiles. "
                f"Add them to the profiles table first."
            ) from e
        raise RuntimeError(
            f"resolve_identity RPC failed: HTTP {e.code} — {body}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"resolve_identity RPC call error: {e}") from e

    # RPC returns a list (RETURNS TABLE) — take first row
    if not data or not isinstance(data, list) or len(data) == 0:
        raise IdentityNotFoundError(
            f"resolve_identity returned no rows for telegram_user_id={telegram_user_id}"
        )

    profile = data[0]
    token = mint_user_jwt(
        user_id     = profile["user_id"],
        role        = profile["role"],
        org_id      = profile.get("org_id"),
        project_ids = profile.get("project_ids") or [],
    )

    logger.info(
        f"[jwt_minter] Identity resolved: telegram_user_id={telegram_user_id} "
        f"user_id={profile['user_id']} role={profile['role']}"
    )
    return token, profile
