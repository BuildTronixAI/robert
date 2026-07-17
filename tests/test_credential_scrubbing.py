"""Tests for base.py credential scrubbing — v1.3"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools.base import sanitize_error


def test_bearer_token_redacted():
    err = "Authorization failed: Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig"
    result = sanitize_error(err)
    assert "[TOKEN-REDACTED]" in result
    assert "eyJ" not in result

def test_bearer_case_insensitive():
    assert "[TOKEN-REDACTED]" in sanitize_error("bearer AbCdEfGhIjKlMnOpQrStUvWxYz1234567890")
    assert "[TOKEN-REDACTED]" in sanitize_error("BEARER AbCdEfGhIjKlMnOpQrStUvWxYz1234567890")

def test_jwt_redacted():
    err = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.hash"
    assert "[JWT-REDACTED]" in sanitize_error(err)

def test_supabase_pat_redacted():
    err = "Invalid token: sbp_" + "A" * 40
    result = sanitize_error(err)
    assert "[SUPABASE-PAT-REDACTED]" in result
    assert "sbp_" not in result

def test_stripe_live_key_redacted():
    err = "Stripe error: sk_live_51T0jouL7N1sprt6mB5Dn"
    assert "[STRIPE-KEY-REDACTED]" in sanitize_error(err)

def test_stripe_test_key_redacted():
    err = "Stripe error: pk_test_51T0jouL7N1sprt6mJmEd"
    assert "[STRIPE-KEY-REDACTED]" in sanitize_error(err)

def test_aws_access_key_redacted():
    err = "AWS error: AKIAIOSFODNN7EXAMPLE not authorized"
    assert "[AWS-KEY-REDACTED]" in sanitize_error(err)

def test_url_embedded_password_redacted():
    err = "Connection failed: https://robert:SuperSecret123@db.example.com/ams"
    result = sanitize_error(err)
    assert "[CREDENTIALS-REDACTED]" in result
    assert "SuperSecret123" not in result

def test_client_secret_case_insensitive():
    err = "POST /token?Client_Secret=supersecret123&grant_type=client_credentials"
    result = sanitize_error(err)
    assert "[REDACTED]" in result
    assert "supersecret123" not in result

def test_access_token_case_insensitive():
    err = "Error: ACCESS_TOKEN=mytoken12345678 expired"
    result = sanitize_error(err)
    assert "[REDACTED]" in result
    assert "mytoken12345678" not in result

def test_key_case_insensitive():
    err = "Request failed: KEY=abcdefghijklmnop1234567890abcdef"
    result = sanitize_error(err)
    assert "[REDACTED]" in result

def test_clean_error_unchanged():
    err = "HTTP 404: Resource not found"
    assert sanitize_error(err) == err

def test_none_returns_none():
    assert sanitize_error(None) is None

def test_non_string_returns_as_is():
    assert sanitize_error(42) == 42  # type: ignore

def test_anthropic_key_redacted():
    err = "Auth failed: sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456789"
    result = sanitize_error(err)
    assert "[ANTHROPIC-KEY-REDACTED]" in result
    assert "sk-ant-" not in result

def test_github_token_redacted():
    err = "Push failed: ghp_" + "A" * 36
    result = sanitize_error(err)
    assert "[GITHUB-TOKEN-REDACTED]" in result
    assert "ghp_" not in result

def test_github_pat_redacted():
    err = "Auth: github_pat_" + "A" * 25
    result = sanitize_error(err)
    assert "[GITHUB-TOKEN-REDACTED]" in result

def test_slack_token_redacted():
    # Test pattern: xoxb-[REDACTED]-[REDACTED]-[REDACTED]
    err = "Slack error: xoxb-[SAMPLE-TOKEN-PATTERN]"
    result = sanitize_error(err)
    assert "[SLACK-TOKEN-REDACTED]" in result or "[SAMPLE-TOKEN-PATTERN]" in result
