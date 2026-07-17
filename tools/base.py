"""
Base tool utilities for Robert — credential scrubbing and shared helpers.
v1.3: IGNORECASE applied consistently, sbp_ pattern added, UUID non-redaction documented.
All tool methods must call sanitize_error() on error strings before returning or logging.
"""
import re
from typing import Optional

_SANITIZE_PATTERNS = [
    # Bearer tokens: case-insensitive
    (re.compile(r'Bearer [A-Za-z0-9._\-+/=~]+', re.IGNORECASE), '[TOKEN-REDACTED]'),

    # JWT tokens: eyJ prefix is base64url for '{"' — all JWTs start this way
    (re.compile(r'eyJ[A-Za-z0-9._\-+/=]{20,}'), '[JWT-REDACTED]'),

    # Supabase Personal Access Tokens (admin-level)
    (re.compile(r'sbp_[A-Za-z0-9]{40,}'), '[SUPABASE-PAT-REDACTED]'),

    # client_secret in URLs
    (re.compile(r'client_secret=[^&\s]+', re.IGNORECASE), 'client_secret=[REDACTED]'),

    # access_token in URLs
    (re.compile(r'access_token=[^&\s]+', re.IGNORECASE), 'access_token=[REDACTED]'),

    # password in URLs
    (re.compile(r'password=[^&\s]+', re.IGNORECASE), 'password=[REDACTED]'),

    # generic token= param
    (re.compile(r'\btoken=[A-Za-z0-9._\-+/=]{8,}', re.IGNORECASE), 'token=[REDACTED]'),

    # generic secret= param
    (re.compile(r'\bsecret=[A-Za-z0-9._\-+/=]{8,}', re.IGNORECASE), 'secret=[REDACTED]'),

    # api_key= param
    (re.compile(r'api_key=[A-Za-z0-9._\-+/=]{8,}', re.IGNORECASE), 'api_key=[REDACTED]'),

    # key= param
    (re.compile(r'\bkey=[A-Za-z0-9._\-+/=]{16,}', re.IGNORECASE), 'key=[REDACTED]'),

    # URL-embedded credentials: https://user:PASSWORD@host
    (re.compile(r'://[^:]+:[^@]+@'), '://[CREDENTIALS-REDACTED]@'),

    # AWS access key format
    (re.compile(r'AKIA[A-Z0-9]{16}'), '[AWS-KEY-REDACTED]'),

    # Stripe key format
    (re.compile(r'(sk|pk)_(live|test)_[A-Za-z0-9]+'), '[STRIPE-KEY-REDACTED]'),

    # Anthropic API keys
    (re.compile(r'sk-ant-[A-Za-z0-9\-_]{20,}'), '[ANTHROPIC-KEY-REDACTED]'),

    # GitHub tokens
    (re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}'), '[GITHUB-TOKEN-REDACTED]'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{20,}'), '[GITHUB-TOKEN-REDACTED]'),

    # Google OAuth refresh tokens
    (re.compile(r'1//0[A-Za-z0-9\-_]{20,}'), '[GOOGLE-OAUTH-REDACTED]'),

    # Slack tokens
    (re.compile(r'xox[baprs]-[A-Za-z0-9\-]{10,}'), '[SLACK-TOKEN-REDACTED]'),
]


def sanitize_error(error_str: Optional[str]) -> Optional[str]:
    """
    Remove potential credential material from error strings before logging or surfacing.
    Call this on ALL error strings before returning from any tool method.

    UUID NON-REDACTION POLICY (deliberate, v1.3):
    UUIDs are NOT redacted — they are entity identifiers, not credentials.
    Without a valid JWT, a UUID is not exploitable by an external attacker.
    UUID retention aids debugging. Review if UUIDs are ever used as capability tokens.
    """
    if not isinstance(error_str, str) or not error_str:
        return error_str
    s = error_str
    for pattern, replacement in _SANITIZE_PATTERNS:
        s = pattern.sub(replacement, s)
    return s
