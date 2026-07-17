"""
auth/user_client.py — Robert User-Scoped Supabase Client
=========================================================
Returns a Supabase client authenticated as a specific user via JWT.
All operations through this client execute under RLS for that user's role.
"""

from __future__ import annotations

import json
import logging
import os
import re
from urllib.parse import quote

from tools.base import sanitize_error
from tools.safe_fetch import safe_fetch

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "") or os.environ.get("SUPABASE_SERVICE_KEY", "")

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_ident(name: str, kind: str = "identifier") -> str:
    if not name or not _SAFE_IDENT.match(name):
        raise ValueError(f"Invalid {kind}: {name!r}")
    return name


class UserScopedClient:
    """
    Lightweight user-scoped Supabase REST client.
    Uses project anon/service key as apikey and user JWT as Authorization (RLS).
    """

    def __init__(self, jwt_token: str, supabase_url: str = "", anon_key: str = ""):
        self.jwt_token = jwt_token
        self.base_url = (supabase_url or SUPABASE_URL).rstrip("/")
        self.anon_key = anon_key or SUPABASE_ANON_KEY
        if not self.base_url:
            raise ValueError("SUPABASE_URL is not set — cannot create user client")
        if not self.anon_key:
            raise ValueError("SUPABASE_ANON_KEY (or SERVICE_KEY fallback) required for apikey header")
        if not self.jwt_token:
            raise ValueError("jwt_token required for user-scoped client")

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def select(self, table: str, columns: str = "*", filters: dict | None = None) -> list:
        table = _validate_ident(table, "table")
        # columns may be "*" or comma-separated identifiers
        if columns != "*":
            for col in columns.split(","):
                _validate_ident(col.strip(), "column")

        url = f"{self.base_url}/rest/v1/{table}?select={quote(columns, safe='*,()')}"
        if filters:
            for col, val in filters.items():
                col = _validate_ident(col, "filter column")
                url += f"&{quote(col)}=eq.{quote(str(val), safe='')}"

        try:
            status, body, _ = safe_fetch(url, headers=self._headers(), timeout=10)
            if status >= 400:
                raise RuntimeError(f"SELECT {table} failed: HTTP {status}")
            return json.loads(body.decode())
        except Exception as e:
            raise RuntimeError(
                sanitize_error(f"[user_client] SELECT {table} failed: {e}")
            ) from e

    def insert(self, table: str, data: dict) -> dict:
        table = _validate_ident(table, "table")
        url = f"{self.base_url}/rest/v1/{table}"
        try:
            status, body, _ = safe_fetch(
                url,
                method="POST",
                data=json.dumps(data).encode(),
                headers=self._headers({"Prefer": "return=representation"}),
                timeout=10,
            )
            if status >= 400:
                raise RuntimeError(f"INSERT {table} failed: HTTP {status}")
            result = json.loads(body.decode())
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            raise RuntimeError(
                sanitize_error(f"[user_client] INSERT {table} failed: {e}")
            ) from e

    def update(self, table: str, data: dict, filters: dict) -> list:
        if not filters:
            raise ValueError("[user_client] UPDATE requires at least one filter — no blind updates allowed")
        table = _validate_ident(table, "table")
        parts = []
        for col, val in filters.items():
            col = _validate_ident(col, "filter column")
            parts.append(f"{quote(col)}=eq.{quote(str(val), safe='')}")
        url = f"{self.base_url}/rest/v1/{table}?" + "&".join(parts)
        try:
            status, body, _ = safe_fetch(
                url,
                method="PATCH",
                data=json.dumps(data).encode(),
                headers=self._headers({"Prefer": "return=representation"}),
                timeout=10,
            )
            if status >= 400:
                raise RuntimeError(f"UPDATE {table} failed: HTTP {status}")
            return json.loads(body.decode())
        except Exception as e:
            raise RuntimeError(
                sanitize_error(f"[user_client] UPDATE {table} failed: {e}")
            ) from e


def get_user_client(jwt_token: str) -> UserScopedClient:
    """Return a user-scoped Supabase client (RLS via JWT)."""
    return UserScopedClient(jwt_token=jwt_token)
