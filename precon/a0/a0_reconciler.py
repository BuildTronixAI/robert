"""
A-0 Reconciler — Ground Truth Verification
===========================================
The reconciler compares filesystem/source reality against the registry projection.
It emits events. It does NOT write registry state directly.
Only the ingestor writes registry state.

Reconciliation hierarchy:
  Immutable event log = truth
  Registry = projection
  Filesystem / Graph / local share = current observed reality

Reconcile events:
  RECONCILE_DISCOVERED    — file in source, not in registry
  RECONCILE_CONFIRMED     — file in source, hash matches registry
  RECONCILE_MISSING       — file in registry, not found in source
  RECONCILE_HASH_DRIFT    — file in both, hash differs
  RECONCILE_PATH_MOVED    — file hash found at different path
  RECONCILE_SOURCE_UNAVAILABLE — source path not reachable
"""
import hashlib
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import httpx

from config import (
    SUPABASE_URL, SUPABASE_SERVICE_KEY,
    RECONCILE_HASH_WORKERS, RECONCILE_INTERVAL_S,
)
from event_log import (
    EventLog, A0Event,
    RECONCILE_DISCOVERED, RECONCILE_CONFIRMED, RECONCILE_MISSING,
    RECONCILE_HASH_DRIFT, RECONCILE_PATH_MOVED, RECONCILE_SOURCE_UNAVAILABLE,
)

logger = logging.getLogger("a0.reconciler")


def sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, PermissionError, OSError) as e:
        logger.warning(f"Cannot hash {path}: {e}")
        return None


class ReconcileState:
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS     = "SUCCESS"
    FAILED      = "FAILED"
    PARTIAL     = "PARTIAL"


class A0Reconciler:
    """
    Reconciles filesystem state against registry.
    Emits events only — ingestor handles registry mutations.
    """

    def __init__(self, project_id: str, watch_paths: list[str]):
        self.project_id  = project_id
        self.watch_paths = watch_paths
        self._event_log  = EventLog()
        self._running    = False
        self._sb = httpx.Client(base_url=SUPABASE_URL, timeout=30)
        self._sb_headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_scheduled(self):
        """Start background scheduled reconciler."""
        self._running = True
        threading.Thread(
            target=self._schedule_loop, daemon=True,
            name=f"reconciler-{self.project_id}"
        ).start()
        logger.info(f"Reconciler started, interval={RECONCILE_INTERVAL_S}s")

    def stop(self):
        self._running = False

    def _schedule_loop(self):
        while self._running:
            time.sleep(RECONCILE_INTERVAL_S)
            if not self._running:
                break
            try:
                self.run(triggered_by="SCHEDULE")
            except Exception as e:
                logger.exception(f"Scheduled reconcile failed: {e}")

    # ── Core reconcile ────────────────────────────────────────────────────────

    def run(self, triggered_by: str = "MANUAL") -> dict:
        """
        Full filesystem reconcile.
        1. Set RECONCILE_IN_PROGRESS on project
        2. Enumerate all source files
        3. Hash all files (parallel)
        4. Compare against registry
        5. Emit events for differences
        6. Clear RECONCILE_IN_PROGRESS

        Returns summary dict.
        """
        reconcile_id = str(uuid.uuid4())
        started_at   = datetime.now(timezone.utc).isoformat()
        logger.info(f"Reconcile started [{reconcile_id}] triggered_by={triggered_by}")

        # Start reconcile record — gates will see IN_PROGRESS and block
        self._start_reconcile_record(reconcile_id, triggered_by, started_at)

        stats = {
            "reconcile_id":     reconcile_id,
            "files_enumerated": 0,
            "files_rehashed":   0,
            "mismatches":       0,
            "events_emitted":   0,
        }

        try:
            # Load current registry state
            registry = self._load_registry()
            registry_by_path = {r["source_path"]: r for r in registry}
            registry_by_hash = {}
            for r in registry:
                h = r.get("file_hash")
                if h:
                    registry_by_hash.setdefault(h, []).append(r)

            # Enumerate source files
            source_files = list(self._enumerate_source())
            stats["files_enumerated"] = len(source_files)

            # Hash all files in parallel
            hashed = self._parallel_hash(source_files)
            stats["files_rehashed"] = len(hashed)

            # Compare against registry
            seen_paths = set()
            for path, file_hash, byte_size in hashed:
                seen_paths.add(path)
                reg = registry_by_path.get(path)

                if file_hash is None:
                    # Can't read file
                    evt_type = RECONCILE_SOURCE_UNAVAILABLE
                elif reg is None:
                    # Check if same hash exists at different path
                    alt = registry_by_hash.get(file_hash)
                    if alt:
                        evt_type = RECONCILE_PATH_MOVED
                    else:
                        evt_type = RECONCILE_DISCOVERED
                elif reg.get("file_hash") == file_hash:
                    evt_type = RECONCILE_CONFIRMED
                else:
                    evt_type = RECONCILE_HASH_DRIFT
                    stats["mismatches"] += 1

                evt = A0Event(
                    event_type=evt_type,
                    project_id=self.project_id,
                    source_type="RECONCILER",
                    source_path=path,
                    file_hash_before=reg.get("file_hash") if reg else None,
                    file_hash_after=file_hash,
                    byte_size=byte_size,
                )
                self._event_log.emit(evt)
                stats["events_emitted"] += 1

            # Files in registry but not found in source → RECONCILE_MISSING
            for path, reg in registry_by_path.items():
                if path not in seen_paths and reg.get("evidence_status") != "UNAVAILABLE":
                    evt = A0Event(
                        event_type=RECONCILE_MISSING,
                        project_id=self.project_id,
                        source_type="RECONCILER",
                        source_path=path,
                        file_hash_before=reg.get("file_hash"),
                    )
                    self._event_log.emit(evt)
                    stats["events_emitted"] += 1
                    stats["mismatches"] += 1

            # Success
            self._finish_reconcile_record(
                reconcile_id, ReconcileState.SUCCESS, stats, started_at
            )
            logger.info(f"Reconcile complete [{reconcile_id}]: {stats}")
            return stats

        except Exception as e:
            logger.exception(f"Reconcile failed [{reconcile_id}]: {e}")
            self._finish_reconcile_record(
                reconcile_id, ReconcileState.FAILED, stats, started_at,
                error=str(e)
            )
            raise

    # ── Source enumeration ────────────────────────────────────────────────────

    def _enumerate_source(self) -> Iterator[str]:
        """Yield file paths from all watched paths."""
        for watch_path in self.watch_paths:
            if not os.path.exists(watch_path):
                logger.warning(f"Watch path not accessible: {watch_path}")
                evt = A0Event(
                    event_type=RECONCILE_SOURCE_UNAVAILABLE,
                    project_id=self.project_id,
                    source_type="RECONCILER",
                    source_path=watch_path,
                )
                self._event_log.emit(evt)
                continue
            for root, dirs, files in os.walk(watch_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    if not fname.startswith("."):
                        yield os.path.join(root, fname)

    # ── Parallel hashing ──────────────────────────────────────────────────────

    def _parallel_hash(self, paths: list[str]) -> list[tuple[str, Optional[str], Optional[int]]]:
        """Hash files in parallel. Returns list of (path, hash, size)."""
        results = []

        def hash_one(path: str):
            h  = sha256_file(path)
            sz = None
            try:
                sz = os.path.getsize(path)
            except OSError:
                pass
            return path, h, sz

        with ThreadPoolExecutor(max_workers=RECONCILE_HASH_WORKERS) as ex:
            futures = {ex.submit(hash_one, p): p for p in paths}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    path = futures[future]
                    logger.warning(f"Hash failed for {path}: {e}")
                    results.append((path, None, None))

        return results

    # ── Registry loader ───────────────────────────────────────────────────────

    def _load_registry(self) -> list[dict]:
        """Load all document records for this project."""
        all_rows = []
        offset = 0
        page   = 1000
        while True:
            r = self._sb.get(
                "/rest/v1/precon_project_documents",
                headers=self._sb_headers,
                params={
                    "project_id": f"eq.{self.project_id}",
                    "select":     "document_id,source_path,file_hash,evidence_status",
                    "limit":      str(page),
                    "offset":     str(offset),
                },
            )
            r.raise_for_status()
            rows = r.json()
            all_rows.extend(rows)
            if len(rows) < page:
                break
            offset += page
        return all_rows

    # ── Supabase record management ────────────────────────────────────────────

    def _start_reconcile_record(self, reconcile_id: str, triggered_by: str, started_at: str):
        row = {
            "reconcile_id": reconcile_id,
            "project_id":   self.project_id,
            "triggered_by": triggered_by,
            "started_at":   started_at,
            "status":       ReconcileState.IN_PROGRESS,
        }
        self._sb.post(
            "/rest/v1/precon_a0_reconcile_records",
            headers={**self._sb_headers, "Prefer": "return=minimal"},
            json=row,
        )

    def _finish_reconcile_record(
        self, reconcile_id: str, status: str, stats: dict,
        started_at: str, error: str = None
    ):
        patch = {
            "status":           status,
            "completed_at":     datetime.now(timezone.utc).isoformat(),
            "files_enumerated": stats.get("files_enumerated", 0),
            "files_rehashed":   stats.get("files_rehashed", 0),
            "mismatches_detected": stats.get("mismatches", 0),
            "events_generated": stats.get("events_emitted", 0),
            "error_detail":     error,
        }
        self._sb.patch(
            f"/rest/v1/precon_a0_reconcile_records?reconcile_id=eq.{reconcile_id}",
            headers={**self._sb_headers, "Prefer": "return=minimal"},
            json=patch,
        )
