"""Shared safe HTTP client — SSRF-validated, size-capped, sanitized errors."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from tools.url_validator import validate_url

try:
    from tools.base import sanitize_error
except Exception:  # pragma: no cover
    def sanitize_error(text: str) -> str:
        return text


DEFAULT_TIMEOUT = 15
DEFAULT_MAX_BYTES = 2_000_000  # 2 MiB


def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict] = None,
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    skip_allowlist: bool = False,
) -> tuple[int, bytes, dict]:
    """
    Fetch a URL after SSRF validation.

    Returns (status, body_bytes, response_headers).
    Raises ValueError for unsafe URLs; URLError/HTTPError for transport failures.
    """
    if not skip_allowlist:
        validate_url(url)

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError(f"Response exceeds max_bytes={max_bytes}")
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        err_body = e.read(4096) if hasattr(e, "read") else b""
        raise urllib.error.HTTPError(
            e.url, e.code, sanitize_error(e.reason or ""), e.headers, None
        ) from None
    except Exception as e:
        raise type(e)(sanitize_error(str(e))) from e


def safe_fetch_json(url: str, **kwargs) -> tuple[int, dict]:
    status, body, _ = safe_fetch(url, **kwargs)
    return status, json.loads(body.decode("utf-8"))
