"""Resend email tool for Robert — gated + safe_fetch."""

import os
import json
from typing import Optional

from tools.base import sanitize_error
from tools.actor_context import require_gate
from tools.safe_fetch import safe_fetch

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_BASE_URL = "https://api.resend.com/emails"
INTERNAL_DOMAINS = ("buildtronix.ai", "l2rholdings.com")


def _is_internal_recipient(to: str) -> bool:
    addr = (to or "").lower().strip()
    if "@" not in addr:
        return False
    domain = addr.rsplit("@", 1)[-1]
    return any(domain == d or domain.endswith("." + d) for d in INTERNAL_DOMAINS)


def send_email(
    to: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
    from_email: str = "robert@buildtronix.ai",
    *,
    skip_gate: bool = False,
) -> bool:
    """
    Send an email via Resend API.
    External recipients are RED-tier (approval required at Gate 2).
    """
    try:
        if not RESEND_API_KEY:
            raise ValueError("RESEND_API_KEY not configured")

        internal = _is_internal_recipient(to)
        action = "send_internal_message" if internal else "send_email_external"
        if not skip_gate:
            require_gate(
                action,
                target=to,
                reversible=False,
                data_sensitivity="confidential" if not internal else "internal",
                execution_payload={
                    "to": to,
                    "subject": subject[:200],
                    "from_email": from_email,
                    "internal": internal,
                },
            )

        payload = {
            "from": from_email,
            "to": to,
            "subject": subject,
        }
        if html:
            payload["html"] = html
        else:
            payload["text"] = body

        status, body_bytes, _ = safe_fetch(
            RESEND_BASE_URL,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        if status in (200, 201):
            response_data = json.loads(body_bytes.decode("utf-8"))
            print(f"[Resend] Email sent to {to}. ID: {response_data.get('id', 'unknown')}")
            return True
        print(f"[Resend] Unexpected status {status}")
        return False
    except Exception as e:
        print(f"[Resend] Failed to send email to {to}: {sanitize_error(str(e))}")
        return False
