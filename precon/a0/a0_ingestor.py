"""
A-0 Ingestor — Single Writer for Document Registry State
=========================================================
The ONLY component that writes to precon_project_documents.
All other components emit events. The ingestor processes events and updates state.

Responsibilities:
  - Dedup across Graph, local agent, manual import, reconciler
  - Run classifier (or queue for retry)
  - Write registry state
  - Emit gate-invalidation signals
  - Route to DLQ on persistent failures

Architecture rule: no other module writes to precon_project_documents.
"""
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from config import (
    SUPABASE_URL, SUPABASE_SERVICE_KEY,
    GATE_CRITICAL_TYPES,
)
from event_log import (
    EventLog, A0Event,
    DOCUMENT_DISCOVERED, DOCUMENT_MODIFIED, DOCUMENT_REMOVED, DOCUMENT_RENAMED,
    RECONCILE_DISCOVERED, RECONCILE_CONFIRMED, RECONCILE_MISSING,
    RECONCILE_HASH_DRIFT, RECONCILE_PATH_MOVED, RECONCILE_SOURCE_UNAVAILABLE,
    CLASSIFICATION_PROPOSED, CLASSIFICATION_FAILED, CLASSIFICATION_LOW_CONFIDENCE,
)
from classifier import (
    DocumentClassifier, ClassificationStatus,
    get_folder_hint, resolve_final_type,
)

logger = logging.getLogger("a0.ingestor")


class A0Ingestor:
    """
    Processes A0Events and maintains precon_project_documents registry.
    Stateless across calls — all state is in Supabase.
    """

    def __init__(self):
        self._sb = httpx.Client(base_url=SUPABASE_URL, timeout=30)
        self._headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }
        self._event_log = EventLog()
        self._classifier = DocumentClassifier()

    # ── Public entry point ───────────────────────────────────────────────────

    def process_event(self, event: A0Event) -> dict:
        """
        Process one A0Event. Returns action dict describing what was done.
        Never raises — all errors are logged and returned in action dict.
        """
        try:
            if event.event_type in (DOCUMENT_DISCOVERED, RECONCILE_DISCOVERED):
                return self._handle_discovered(event)
            elif event.event_type in (DOCUMENT_MODIFIED, RECONCILE_HASH_DRIFT):
                return self._handle_modified(event)
            elif event.event_type in (DOCUMENT_REMOVED, RECONCILE_MISSING, RECONCILE_SOURCE_UNAVAILABLE):
                return self._handle_removed(event)
            elif event.event_type in (DOCUMENT_RENAMED, RECONCILE_PATH_MOVED):
                return self._handle_renamed(event)
            elif event.event_type == RECONCILE_CONFIRMED:
                return self._handle_confirmed(event)
            elif event.event_type == CLASSIFICATION_PROPOSED:
                return self._handle_classification_proposed(event)
            elif event.event_type == CLASSIFICATION_FAILED:
                return self._handle_classification_failed(event)
            else:
                return {"action": "SKIPPED", "reason": f"Unhandled event type {event.event_type}"}
        except Exception as e:
            logger.exception(f"Ingestor error on event {event.event_id}: {e}")
            return {"action": "ERROR", "error": str(e), "event_id": event.event_id}

    # ── Dedup ────────────────────────────────────────────────────────────────

    def _lookup_by_hash(self, project_id: str, content_hash: str) -> Optional[dict]:
        """Find existing document record by content hash (preferred identity)."""
        r = self._sb.get(
            "/rest/v1/precon_project_documents",
            headers=self._headers,
            params={
                "project_id": f"eq.{project_id}",
                "file_hash":  f"eq.{content_hash}",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def _lookup_by_path(self, project_id: str, source_path: str) -> Optional[dict]:
        r = self._sb.get(
            "/rest/v1/precon_project_documents",
            headers=self._headers,
            params={
                "project_id":  f"eq.{project_id}",
                "source_path": f"eq.{source_path}",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_discovered(self, event: A0Event) -> dict:
        content_hash = event.file_hash_after or event.file_hash_before
        if not content_hash:
            return {"action": "SKIPPED", "reason": "No hash in event"}

        # Dedup by content hash first
        existing = self._lookup_by_hash(event.project_id, content_hash)
        if existing:
            # Same bytes — update path if different (path alias)
            if existing["source_path"] != event.source_path:
                self._patch_document(existing["document_id"], {
                    "source_path": event.source_path,
                    "updated_at":  _now(),
                })
                return {"action": "PATH_ALIAS_UPDATED", "document_id": existing["document_id"]}
            return {"action": "DEDUP_NO_OP", "document_id": existing["document_id"]}

        # Check path too
        existing_path = self._lookup_by_path(event.project_id, event.source_path)
        if existing_path and existing_path["file_hash"] != content_hash:
            # Same path, new hash → version event (handled by MODIFIED)
            logger.info(f"Path {event.source_path} exists with different hash — treating as MODIFIED")
            event.file_hash_before = existing_path["file_hash"]
            return self._handle_modified(event)

        # New document
        folder_hint = get_folder_hint(event.source_path)
        doc_id = str(uuid.uuid4())

        row = {
            "document_id":            doc_id,
            "project_id":             event.project_id,
            "source_path":            event.source_path,
            "file_name":              event.source_path.split("/")[-1].split("\\")[-1],
            "file_hash":              content_hash,
            "last_verified_hash":     content_hash,
            "last_verified_at":       _now(),
            "byte_size":              event.byte_size,
            "discovered_at":          event.emitted_at,
            "folder_hint_type":       folder_hint,
            "content_classified_type": None,
            "final_document_type":    "UNKNOWN",
            "classification_mismatch": False,
            "evidence_status":        "PRESENT",
            "authority_escalation":   False,
            "created_at":             _now(),
            "updated_at":             _now(),
        }
        self._insert_document(row)

        # Kick off classification (non-blocking — failures go to retry queue)
        self._schedule_classification(doc_id, event.project_id, event.source_path,
                                      content_hash, folder_hint, event.byte_size)

        return {"action": "DOCUMENT_CREATED", "document_id": doc_id}

    def _handle_modified(self, event: A0Event) -> dict:
        new_hash  = event.file_hash_after
        old_hash  = event.file_hash_before
        if not new_hash:
            return {"action": "SKIPPED", "reason": "No new hash"}

        existing = self._lookup_by_path(event.project_id, event.source_path)
        if not existing:
            # Not in registry — treat as discovered
            return self._handle_discovered(event)

        if existing["file_hash"] == new_hash:
            # Hash unchanged — confirm freshness
            self._patch_document(existing["document_id"], {
                "last_verified_hash": new_hash,
                "last_verified_at":   _now(),
                "updated_at":         _now(),
            })
            return {"action": "HASH_CONFIRMED", "document_id": existing["document_id"]}

        # Hash changed — EVIDENCE_TAMPERING_CANDIDATE per P0-5
        logger.warning(
            f"Hash mismatch on {event.source_path}: "
            f"registry={existing['file_hash']} observed={new_hash}"
        )
        self._patch_document(existing["document_id"], {
            "evidence_status":    "TAMPERING_CANDIDATE",
            "last_verified_hash": new_hash,
            "last_verified_at":   _now(),
            "updated_at":         _now(),
        })
        # Invalidate gate for this project
        self._invalidate_gates(event.project_id, existing["document_id"],
                                reason="HASH_MISMATCH")
        return {
            "action":      "TAMPERING_CANDIDATE",
            "document_id": existing["document_id"],
            "old_hash":    old_hash,
            "new_hash":    new_hash,
        }

    def _handle_removed(self, event: A0Event) -> dict:
        existing = self._lookup_by_path(event.project_id, event.source_path)
        if not existing:
            return {"action": "NOT_FOUND", "path": event.source_path}

        self._patch_document(existing["document_id"], {
            "evidence_status": "UNAVAILABLE",
            "updated_at":      _now(),
        })
        # Invalidate gate if this was a gate-critical doc
        doc_type = existing.get("final_document_type", "UNKNOWN")
        if doc_type in GATE_CRITICAL_TYPES or existing.get("content_classified_type") in GATE_CRITICAL_TYPES:
            self._invalidate_gates(event.project_id, existing["document_id"],
                                    reason="EVIDENCE_UNAVAILABLE")
        return {"action": "EVIDENCE_UNAVAILABLE", "document_id": existing["document_id"]}

    def _handle_renamed(self, event: A0Event) -> dict:
        old_path = event.payload.get("old_path") or event.source_path
        new_path = event.payload.get("new_path") or event.source_path
        existing = self._lookup_by_path(event.project_id, old_path)
        if not existing:
            # Treat as discovery at new path
            return self._handle_discovered(event)

        new_folder_hint = get_folder_hint(new_path)
        old_type = existing.get("final_document_type", "UNKNOWN")

        # Authority escalation check
        authority_escalation = _is_authority_escalation(
            old_type, new_folder_hint, existing.get("content_classified_type", "UNKNOWN")
        )
        new_final_type = new_folder_hint
        if authority_escalation:
            new_final_type = "AUTHORITY_ESCALATION_PENDING"

        self._patch_document(existing["document_id"], {
            "source_path":         new_path,
            "folder_hint_type":    new_folder_hint,
            "final_document_type": new_final_type,
            "authority_escalation": authority_escalation,
            "updated_at":          _now(),
        })
        return {
            "action":      "PATH_UPDATED",
            "document_id": existing["document_id"],
            "authority_escalation": authority_escalation,
        }

    def _handle_confirmed(self, event: A0Event) -> dict:
        existing = self._lookup_by_path(event.project_id, event.source_path)
        if not existing:
            return self._handle_discovered(event)
        self._patch_document(existing["document_id"], {
            "last_verified_hash": event.file_hash_after or existing["file_hash"],
            "last_verified_at":   _now(),
            "evidence_status":    "PRESENT",
            "updated_at":         _now(),
        })
        return {"action": "RECONCILE_CONFIRMED", "document_id": existing["document_id"]}

    def _handle_classification_proposed(self, event: A0Event) -> dict:
        doc_id = event.payload.get("document_id")
        result = event.payload.get("classification_result", {})
        if not doc_id:
            return {"action": "ERROR", "reason": "No document_id in classification event"}

        status    = result.get("status", ClassificationStatus.CLASSIFIED)
        doc_type  = result.get("document_type", "UNKNOWN")
        confidence = result.get("confidence", 0.0)
        folder_hint = result.get("folder_hint", "UNKNOWN")

        final_type, mismatch = resolve_final_type(folder_hint, doc_type, confidence)

        self._patch_document(doc_id, {
            "content_classified_type":           doc_type,
            "content_classification_confidence": confidence,
            "final_document_type":               final_type,
            "classification_mismatch":           mismatch,
            "classified_by_execution_version_id": result.get("classifier_version"),
            "document_classifier_version":       result.get("classifier_version"),
            "classification_prompt_hash":        result.get("prompt_hash"),
            "classification_result_hash":        result.get("result_hash"),
            "classified_at":                     _now(),
            "updated_at":                        _now(),
        })

        # Gate invalidation if gate-critical and now pending review
        if "PENDING_REVIEW" in final_type:
            self._invalidate_gates(event.project_id, doc_id, reason="PENDING_REVIEW")

        return {"action": "CLASSIFICATION_APPLIED", "document_id": doc_id,
                "final_type": final_type, "mismatch": mismatch}

    def _handle_classification_failed(self, event: A0Event) -> dict:
        doc_id = event.payload.get("document_id")
        if not doc_id:
            return {"action": "ERROR", "reason": "No document_id"}
        # Route to DLQ — document stays in registry as PENDING_CLASSIFICATION
        logger.error(f"Classification permanently failed for document {doc_id}")
        return {"action": "DLQ_ROUTED", "document_id": doc_id}

    # ── Classification scheduling ────────────────────────────────────────────

    def _schedule_classification(
        self, doc_id: str, project_id: str, source_path: str,
        content_hash: str, folder_hint: str, byte_size: Optional[int]
    ):
        """
        Run classification synchronously (for simplicity in v1).
        In production: queue to background worker for large files.
        """
        file_name = source_path.split("/")[-1].split("\\")[-1]
        ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

        status, result = self._classifier.classify(
            file_name=file_name,
            folder_hint=folder_hint,
            extension=ext,
            byte_size=byte_size or 0,
        )
        result["folder_hint"] = folder_hint

        if status == ClassificationStatus.FAILED:
            event_type = CLASSIFICATION_FAILED
        elif status == ClassificationStatus.LOW_CONFIDENCE:
            event_type = CLASSIFICATION_LOW_CONFIDENCE
        else:
            event_type = CLASSIFICATION_PROPOSED

        result["status"] = status
        evt = A0Event(
            event_type=event_type,
            project_id=project_id,
            source_type="CLASSIFIER",
            source_path=source_path,
            payload={"document_id": doc_id, "classification_result": result},
        )
        self._event_log.emit(evt)
        self.process_event(evt)  # process immediately in v1

    # ── Supabase helpers ─────────────────────────────────────────────────────

    def _insert_document(self, row: dict):
        r = self._sb.post(
            "/rest/v1/precon_project_documents",
            headers={**self._headers, "Prefer": "return=minimal"},
            json=row,
        )
        r.raise_for_status()

    def _patch_document(self, doc_id: str, patch: dict):
        r = self._sb.patch(
            f"/rest/v1/precon_project_documents?document_id=eq.{doc_id}",
            headers={**self._headers, "Prefer": "return=minimal"},
            json=patch,
        )
        r.raise_for_status()

    def _invalidate_gates(self, project_id: str, doc_id: str, reason: str):
        """
        Write a gate-invalidation record.
        In v1: logs to watcher events with gate_invalidation_triggered=true.
        """
        logger.warning(f"Gate invalidated for project {project_id}, doc {doc_id}: {reason}")
        self._sb.patch(
            f"/rest/v1/precon_a0_watcher_events"
            f"?project_id=eq.{project_id}&document_id=eq.{doc_id}",
            headers={**self._headers, "Prefer": "return=minimal"},
            json={"gate_invalidation_triggered": True},
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_authority_escalation(
    current_type: str, new_folder_hint: str, content_type: str
) -> bool:
    authority_tiers = {
        "ADDENDA": 5, "ADDENDUM_PENDING_REVIEW": 5,
        "BID_FORM": 4, "BID_FORM_PENDING_REVIEW": 4,
        "RFI": 3, "RFI_PENDING_REVIEW": 3,
        "SPECS": 2, "PLANS": 1,
        "VENDOR_QUOTE": 0, "ESTIMATE": 0, "ARCHIVE": 0, "UNKNOWN": 0,
    }
    current_tier = authority_tiers.get(current_type, 0)
    new_tier     = authority_tiers.get(new_folder_hint, 0)
    return new_tier > current_tier
