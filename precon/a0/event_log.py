"""
A-0 Immutable Event Log
The event log is the truth source. Registry is a projection. Filesystem is observed reality.

All watcher/reconciler components emit events here.
Only a0_ingestor.py reads events and writes registry state.
"""
import uuid
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone
import httpx
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY


# ── Event types ──────────────────────────────────────────────────────────────

# Watcher-emitted
DOCUMENT_DISCOVERED    = "DOCUMENT_DISCOVERED"
DOCUMENT_MODIFIED      = "DOCUMENT_MODIFIED"
DOCUMENT_REMOVED       = "DOCUMENT_REMOVED"
DOCUMENT_RENAMED       = "DOCUMENT_RENAMED"
PATH_NOW_EMPTY         = "PATH_NOW_EMPTY"
PATH_NEWLY_POPULATED   = "PATH_NEWLY_POPULATED"
AUTHORITY_ESCALATION_CANDIDATE = "AUTHORITY_ESCALATION_CANDIDATE"
SUSPECT_AUTHORITY_ESCALATION   = "SUSPECT_AUTHORITY_ESCALATION"

# Reconciler-emitted
RECONCILE_DISCOVERED   = "RECONCILE_DISCOVERED"
RECONCILE_CONFIRMED    = "RECONCILE_CONFIRMED"
RECONCILE_MISSING      = "RECONCILE_MISSING"
RECONCILE_HASH_DRIFT   = "RECONCILE_HASH_DRIFT"
RECONCILE_PATH_MOVED   = "RECONCILE_PATH_MOVED"
RECONCILE_SOURCE_UNAVAILABLE = "RECONCILE_SOURCE_UNAVAILABLE"

# Classifier-emitted
CLASSIFICATION_PROPOSED    = "CLASSIFICATION_PROPOSED"
CLASSIFICATION_FAILED      = "CLASSIFICATION_FAILED"
CLASSIFICATION_LOW_CONFIDENCE = "CLASSIFICATION_LOW_CONFIDENCE"

ALL_EVENT_TYPES = {
    DOCUMENT_DISCOVERED, DOCUMENT_MODIFIED, DOCUMENT_REMOVED, DOCUMENT_RENAMED,
    PATH_NOW_EMPTY, PATH_NEWLY_POPULATED,
    AUTHORITY_ESCALATION_CANDIDATE, SUSPECT_AUTHORITY_ESCALATION,
    RECONCILE_DISCOVERED, RECONCILE_CONFIRMED, RECONCILE_MISSING,
    RECONCILE_HASH_DRIFT, RECONCILE_PATH_MOVED, RECONCILE_SOURCE_UNAVAILABLE,
    CLASSIFICATION_PROPOSED, CLASSIFICATION_FAILED, CLASSIFICATION_LOW_CONFIDENCE,
}


@dataclass
class A0Event:
    event_type:     str
    project_id:     str
    source_type:    str          # "GRAPH", "LOCAL_AGENT", "RECONCILER", "MANUAL", "CLASSIFIER"
    source_path:    str
    event_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    file_hash_before: Optional[str] = None
    file_hash_after:  Optional[str] = None
    byte_size:        Optional[int] = None
    prior_classification: Optional[str] = None
    new_path_hint:    Optional[str] = None
    authority_escalation: bool = False
    gate_impact_type: Optional[str] = None
    payload:          dict = field(default_factory=dict)
    emitted_at:       str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_agent_id:  Optional[str] = None   # for LOCAL_AGENT events

    def to_dict(self) -> dict:
        return asdict(self)

    def event_hash(self) -> str:
        """Deterministic hash for dedup — same logical event = same hash."""
        key = f"{self.event_type}:{self.project_id}:{self.source_path}:{self.file_hash_after or self.file_hash_before}"
        return hashlib.sha256(key.encode()).hexdigest()


class EventLog:
    """
    Append-only event log backed by Supabase precon_a0_watcher_events.
    Only the ingestor consumes events. All other components only emit.
    """

    def __init__(self):
        self._headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        self._client = httpx.Client(base_url=SUPABASE_URL, timeout=15)

    def emit(self, event: A0Event) -> str:
        """Append event to log. Returns event_id."""
        assert event.event_type in ALL_EVENT_TYPES, f"Unknown event type: {event.event_type}"
        row = {
            "event_id":                  event.event_id,
            "project_id":                event.project_id,
            "event_type":                event.event_type,
            "source_path":               event.source_path,
            "file_hash_before":          event.file_hash_before,
            "file_hash_after":           event.file_hash_after,
            "prior_classification":      event.prior_classification,
            "new_path_hint":             event.new_path_hint,
            "authority_escalation":      event.authority_escalation,
            "gate_impact_type":          event.gate_impact_type,
            "gate_invalidation_triggered": False,
            "processed_at":              None,
        }
        r = self._client.post(
            "/rest/v1/precon_a0_watcher_events",
            headers=self._headers,
            json=row,
        )
        r.raise_for_status()
        return event.event_id

    def mark_processed(self, event_id: str) -> None:
        r = self._client.patch(
            f"/rest/v1/precon_a0_watcher_events?event_id=eq.{event_id}",
            headers=self._headers,
            json={"processed_at": datetime.now(timezone.utc).isoformat()},
        )
        r.raise_for_status()

    def unprocessed(self, project_id: str, limit: int = 100) -> list[dict]:
        r = self._client.get(
            "/rest/v1/precon_a0_watcher_events",
            headers={**self._headers, "Prefer": ""},
            params={
                "project_id":   f"eq.{project_id}",
                "processed_at": "is.null",
                "order":        "event_timestamp.asc",
                "limit":        str(limit),
            },
        )
        r.raise_for_status()
        return r.json()
