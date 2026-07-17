"""
auth/user_client.py — Robert User-Scoped Supabase Client
=========================================================
Returns a Supabase client authenticated as a specific user via JWT.
All operations through this client execute under RLS for that user's role.

Usage:
    from auth.jwt_minter import resolve_identity_and_mint
    from auth.user_client import get_user_client

    token, profile = resolve_identity_and_mint(telegram_user_id=8480371994)
    client = get_user_client(token)
    # All client.table(...) calls now enforce RLS as this user
"""

import os
import logging
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")


class UserScopedClient:
    """
    Lightweight user-scoped Supabase REST client.
    Authenticates all requests with a short-lived JWT.
    Falls back to urllib (no supabase-py dependency required).
    """

    def __init__(self, jwt_token: str, supabase_url: str = ""):
        self.jwt_token   = jwt_token
        self.base_url    = supabase_url or SUPABASE_URL
        if not self.base_url:
            raise ValueError("SUPABASE_URL is not set — cannot create user client")

    def _headers(self) -> dict:
        return {
            "apikey":        self.jwt_token,
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    def select(self, table: str, columns: str = "*", filters: dict | None = None) -> list:
        """
        SELECT from a table. RLS enforced via JWT.

        Args:
            table:   Table name
            columns: Comma-separated column list (default: *)
            filters: Dict of {column: value} equality filters

        Returns:
            List of row dicts
        """
        url = f"{self.base_url}/rest/v1/{table}?select={columns}"
        if filters:
            for col, val in filters.items():
                url += f"&{col}=eq.{val}"

        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(
                f"[user_client] SELECT {table} failed: HTTP {e.code} — {body}"
            ) from e

    def insert(self, table: str, data: dict) -> dict:
        """
        INSERT a row. RLS enforced via JWT.

        Args:
            table: Table name
            data:  Row dict to insert

        Returns:
            Inserted row dict (with generated id if applicable)
        """
        url     = f"{self.base_url}/rest/v1/{table}"
        payload = json.dumps(data).encode()
        headers = {**self._headers(), "Prefer": "return=representation"}

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return result[0] if isinstance(result, list) else result
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(
                f"[user_client] INSERT {table} failed: HTTP {e.code} — {body}"
            ) from e

    def update(self, table: str, data: dict, filters: dict) -> list:
        """
        UPDATE rows matching filters. RLS enforced via JWT.

        Args:
            table:   Table name
            data:    Dict of {column: new_value}
            filters: Dict of {column: value} equality filters (required — no blind updates)

        Returns:
            List of updated row dicts
        """
        if not filters:
            raise ValueError("[user_client] UPDATE requires at least one filter — no blind updates allowed")

        url = f"{self.base_url}/rest/v1/{table}?"
        url += "&".join(f"{col}=eq.{val}" for col, val in filters.items())
        payload = json.dumps(data).encode()
        headers = {**self._headers(), "Prefer": "return=representation"}

        req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(
                f"[user_client] UPDATE {table} failed: HTTP {e.code} — {body}"
            ) from e


def get_user_client(jwt_token: str) -> UserScopedClient:
    """
    Return a user-scoped Supabase client.
    All operations enforce RLS as the identity embedded in jwt_token.

    Args:
        jwt_token: Short-lived JWT from jwt_minter.mint_user_jwt()

    Returns:
        UserScopedClient instance
    """
    return UserScopedClient(jwt_token=jwt_token)
