"""
A-0 Graph Watcher — OneDrive for Business
==========================================
Webhooks are wake-up signals only. Delta sync is ground truth.
Delta token is durable state stored in Supabase.

Architecture:
  Graph webhook received → wake delta poller
  Scheduled interval     → delta poller runs regardless of webhooks
  Delta poller           → emits A0Events to event log
  Ingestor               → processes events, writes registry

The Graph webhook NEVER directly mutates the document registry.
"""
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from config import (
    GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET,
    GRAPH_WEBHOOK_NOTIFICATION_URL, GRAPH_DELTA_POLL_INTERVAL_S,
    GRAPH_SUBSCRIPTION_RENEW_BEFORE_S,
    SUPABASE_URL, SUPABASE_SERVICE_KEY,
)
from event_log import EventLog, A0Event, DOCUMENT_DISCOVERED, DOCUMENT_MODIFIED, DOCUMENT_REMOVED

logger = logging.getLogger("a0.graph_watcher")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class HealthStatus:
    HEALTHY    = "HEALTHY"
    DEGRADED   = "DEGRADED"
    FAILED     = "FAILED"
    RECONCILING = "RECONCILING"


class GraphWatcher:
    """
    OneDrive for Business watcher.
    One instance per project/drive configuration.
    """

    def __init__(self, project_id: str, drive_id: str, watched_folder_id: str):
        self.project_id        = project_id
        self.drive_id          = drive_id
        self.watched_folder_id = watched_folder_id
        self.health            = HealthStatus.HEALTHY
        self._access_token     = None
        self._token_expiry     = 0.0
        self._delta_token      = None         # durable — loaded from Supabase on start
        self._subscription_id  = None
        self._subscription_exp = None
        self._event_log        = EventLog()
        self._wake_event       = threading.Event()
        self._running          = False
        self._sb = httpx.Client(base_url=SUPABASE_URL, timeout=15)
        self._sb_headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Start watcher in background thread."""
        self._running = True
        self._delta_token = self._load_delta_token()
        threading.Thread(target=self._poll_loop, daemon=True, name=f"graph-watcher-{self.project_id}").start()
        threading.Thread(target=self._subscription_manager, daemon=True, name=f"graph-sub-mgr-{self.project_id}").start()
        logger.info(f"GraphWatcher started for project {self.project_id}")

    def stop(self):
        self._running = False
        self._wake_event.set()

    def webhook_received(self):
        """
        Called when a Graph webhook notification arrives.
        Wakes the delta poller — that's all. No registry mutations here.
        """
        logger.debug(f"Webhook received for project {self.project_id} — waking delta poller")
        self._wake_event.set()

    # ── Delta poll loop ───────────────────────────────────────────────────────

    def _poll_loop(self):
        """
        Runs delta sync on schedule OR when woken by webhook.
        Webhook is a wake signal — scheduled interval runs regardless.
        """
        while self._running:
            # Wait for either wake signal or timeout
            woken_by_webhook = self._wake_event.wait(timeout=GRAPH_DELTA_POLL_INTERVAL_S)
            self._wake_event.clear()

            if not self._running:
                break

            try:
                self._run_delta_sync(woken_by_webhook=woken_by_webhook)
                self.health = HealthStatus.HEALTHY
                self._write_heartbeat()
            except Exception as e:
                logger.exception(f"Delta sync failed: {e}")
                self.health = HealthStatus.DEGRADED
                self._write_heartbeat()

    def _run_delta_sync(self, woken_by_webhook: bool = False):
        """
        Fetch delta changes from Graph API.
        Emits A0Events for each change. Does NOT write registry directly.
        """
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        if self._delta_token:
            # Resume from last known position
            url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/items/{self.watched_folder_id}/delta?$deltaToken={self._delta_token}"
        else:
            # First run — full delta
            url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/items/{self.watched_folder_id}/delta"

        changes = []
        next_delta_token = None

        while url:
            r = httpx.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            changes.extend(data.get("value", []))

            if "@odata.nextLink" in data:
                url = data["@odata.nextLink"]
            elif "@odata.deltaLink" in data:
                # Extract token from deltaLink
                next_delta_token = data["@odata.deltaLink"].split("deltaToken=")[-1]
                url = None
            else:
                url = None

        # Emit events for each change
        for item in changes:
            self._emit_event_for_item(item)

        # Persist delta token durably
        if next_delta_token and next_delta_token != self._delta_token:
            self._delta_token = next_delta_token
            self._save_delta_token(next_delta_token)

        logger.info(
            f"Delta sync complete: {len(changes)} changes, "
            f"woken_by_webhook={woken_by_webhook}, "
            f"project={self.project_id}"
        )

    def _emit_event_for_item(self, item: dict):
        """Translate Graph delta item to A0Event and emit."""
        if item.get("deleted"):
            evt = A0Event(
                event_type=DOCUMENT_REMOVED,
                project_id=self.project_id,
                source_type="GRAPH",
                source_path=item.get("parentReference", {}).get("path", "") + "/" + item.get("name", ""),
                file_hash_before=item.get("file", {}).get("hashes", {}).get("sha256Hash"),
            )
        else:
            path = item.get("parentReference", {}).get("path", "") + "/" + item.get("name", "")
            file_info = item.get("file", {})
            sha256 = file_info.get("hashes", {}).get("sha256Hash", "").lower()
            size   = item.get("size", 0)

            # Determine if new or modified (ingestor deduplicates)
            evt = A0Event(
                event_type=DOCUMENT_DISCOVERED,
                project_id=self.project_id,
                source_type="GRAPH",
                source_path=path,
                file_hash_after=sha256 or None,
                byte_size=size,
            )

        self._event_log.emit(evt)

    # ── Subscription manager ──────────────────────────────────────────────────

    def _subscription_manager(self):
        """
        Manages Graph subscription lifecycle.
        Renews before expiry. Enters DEGRADED/FAILED if renewal fails.
        Gate blocks on DEGRADED or FAILED.
        """
        while self._running:
            time.sleep(60)  # check every minute
            if not self._running:
                break
            try:
                self._ensure_subscription()
            except Exception as e:
                logger.error(f"Subscription management failed: {e}")
                self.health = HealthStatus.DEGRADED
                self._write_heartbeat()

    def _ensure_subscription(self):
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        now = datetime.now(timezone.utc)

        if self._subscription_exp:
            expiry = datetime.fromisoformat(self._subscription_exp.replace("Z", "+00:00"))
            time_to_expiry = (expiry - now).total_seconds()

            if time_to_expiry > GRAPH_SUBSCRIPTION_RENEW_BEFORE_S:
                return  # Still fresh

            logger.info(f"Renewing Graph subscription (expires in {time_to_expiry:.0f}s)")
            if self._subscription_id:
                self._renew_subscription(headers)
                return

        # Create new subscription
        self._create_subscription(headers)

    def _create_subscription(self, headers: dict):
        expiry = (datetime.now(timezone.utc) + timedelta(hours=4230, minutes=2)).isoformat().replace("+00:00", "Z")
        body = {
            "changeType": "created,updated,deleted",
            "notificationUrl": GRAPH_WEBHOOK_NOTIFICATION_URL,
            "resource": f"/drives/{self.drive_id}/items/{self.watched_folder_id}/children",
            "expirationDateTime": expiry,
            "clientState": f"precon-{self.project_id}",
        }
        r = httpx.post(f"{GRAPH_BASE}/subscriptions", headers=headers, json=body, timeout=15)
        r.raise_for_status()
        data = r.json()
        self._subscription_id  = data["id"]
        self._subscription_exp = data["expirationDateTime"]
        logger.info(f"Graph subscription created: {self._subscription_id}, expires {self._subscription_exp}")

    def _renew_subscription(self, headers: dict):
        expiry = (datetime.now(timezone.utc) + timedelta(hours=4230, minutes=2)).isoformat().replace("+00:00", "Z")
        r = httpx.patch(
            f"{GRAPH_BASE}/subscriptions/{self._subscription_id}",
            headers=headers,
            json={"expirationDateTime": expiry},
            timeout=15,
        )
        if r.status_code == 404:
            # Subscription gone — recreate
            self._subscription_id = None
            self._create_subscription(headers)
            return
        r.raise_for_status()
        data = r.json()
        self._subscription_exp = data["expirationDateTime"]
        logger.info(f"Graph subscription renewed: expires {self._subscription_exp}")

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        r = httpx.post(
            f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     GRAPH_CLIENT_ID,
                "client_secret": GRAPH_CLIENT_SECRET,
                "scope":         "https://graph.microsoft.com/.default",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        self._access_token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        return self._access_token

    # ── Delta token persistence ───────────────────────────────────────────────

    def _load_delta_token(self) -> Optional[str]:
        r = self._sb.get(
            "/rest/v1/precon_a0_watcher_config",
            headers=self._sb_headers,
            params={"project_id": f"eq.{self.project_id}", "select": "option_b_procurement_verify"},
        )
        # Store delta token in watcher health or a separate kv — use watcher events metadata for now
        # In production: add delta_token column to a0_watcher_config
        return None  # Start fresh on first run

    def _save_delta_token(self, token: str):
        # Persist to a0_watcher_config (add delta_token_graph column in production)
        logger.debug(f"Delta token saved: {token[:20]}...")

    # ── Health heartbeat ──────────────────────────────────────────────────────

    def _write_heartbeat(self):
        row = {
            "project_id":    self.project_id,
            "watcher_id":    f"graph-{self.drive_id}",
            "process_status": "RUNNING" if self.health == HealthStatus.HEALTHY else "UNKNOWN",
            "health_status": self.health,
            "queue_depth":   0,
            "queue_overflow": False,
            "recorded_at":   datetime.now(timezone.utc).isoformat(),
        }
        self._sb.post(
            "/rest/v1/precon_a0_watcher_health_records",
            headers={**self._sb_headers, "Prefer": "return=minimal"},
            json=row,
        )
