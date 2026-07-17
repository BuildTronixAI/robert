"""
A-0 Local Agent — Office File Share Watcher
============================================
Runs on a machine at the office (Windows or Linux).
Watches a local/SMB file share. Pushes signed events to BOB's server.

Security:
  - Per-agent HMAC-SHA256 authentication
  - Nonce + timestamp + sequence_number + payload_hash
  - Server validates all fields — unsigned/replayed/gapped events rejected

Usage:
  python a0_local_agent.py --agent-id office-naples --secret <HMAC_SECRET> \
      --watch-path "Z:\\Projects" --project-id <UUID> \
      --server-url https://buildtronix.ai/api/precon/agent-push
"""
import argparse
import hashlib
import hmac
import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, \
        FileDeletedEvent, FileMovedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("WARNING: watchdog not installed. Run: pip install watchdog")

logger = logging.getLogger("a0.local_agent")

# ── Event builder ─────────────────────────────────────────────────────────────

def sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, PermissionError):
        return None


def file_size(path: str) -> Optional[int]:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


# ── Signed event sender ───────────────────────────────────────────────────────

class AgentEventSender:
    """
    Sends signed events to BOB's ingest endpoint.
    Authentication: HMAC-SHA256 over (agent_id + nonce + timestamp + sequence + payload_hash).
    """

    def __init__(self, agent_id: str, secret: str, server_url: str, project_id: str):
        self.agent_id   = agent_id
        self.secret     = secret.encode() if isinstance(secret, str) else secret
        self.server_url = server_url
        self.project_id = project_id
        self._sequence  = self._load_sequence()
        self._client    = httpx.Client(timeout=15)
        self._retry_queue: queue.Queue = queue.Queue(maxsize=10000)
        threading.Thread(target=self._retry_loop, daemon=True).start()

    def send(self, event_type: str, source_path: str,
             file_hash_before: Optional[str] = None,
             file_hash_after:  Optional[str] = None,
             byte_size:        Optional[int] = None,
             payload:          dict = None) -> bool:
        """
        Build, sign, and send one event. Returns True on success.
        On failure: queues for retry. Never drops.
        """
        self._sequence += 1
        nonce     = str(uuid.uuid4())
        timestamp = str(int(time.time()))
        sequence  = str(self._sequence)

        body = {
            "event_id":         str(uuid.uuid4()),
            "agent_id":         self.agent_id,
            "project_id":       self.project_id,
            "event_type":       event_type,
            "source_path":      source_path,
            "file_hash_before": file_hash_before,
            "file_hash_after":  file_hash_after,
            "byte_size":        byte_size,
            "payload":          payload or {},
            "nonce":            nonce,
            "timestamp":        timestamp,
            "sequence":         sequence,
            "emitted_at":       datetime.now(timezone.utc).isoformat(),
        }

        payload_hash = hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest()
        body["payload_hash"] = payload_hash

        # Sign: HMAC over agent_id + nonce + timestamp + sequence + payload_hash
        signing_string = f"{self.agent_id}:{nonce}:{timestamp}:{sequence}:{payload_hash}"
        sig = hmac.new(self.secret, signing_string.encode(), hashlib.sha256).hexdigest()
        body["signature"] = sig

        self._save_sequence(self._sequence)

        try:
            r = self._client.post(self.server_url, json=body)
            if r.status_code == 200:
                return True
            else:
                logger.warning(f"Server rejected event: {r.status_code} {r.text[:200]}")
                self._retry_queue.put_nowait(body)
                return False
        except Exception as e:
            logger.warning(f"Send failed: {e} — queuing for retry")
            self._retry_queue.put_nowait(body)
            return False

    def _retry_loop(self):
        while True:
            try:
                body = self._retry_queue.get(timeout=30)
                for attempt in range(5):
                    time.sleep(2 ** attempt)
                    try:
                        r = self._client.post(self.server_url, json=body)
                        if r.status_code == 200:
                            logger.info(f"Retry succeeded: {body['event_id']}")
                            break
                    except Exception:
                        pass
                else:
                    logger.error(f"Retry exhausted for event {body['event_id']} — dropping to local DLQ file")
                    self._write_local_dlq(body)
            except queue.Empty:
                continue

    def _write_local_dlq(self, body: dict):
        dlq_path = Path("a0_local_dlq.jsonl")
        with dlq_path.open("a") as f:
            f.write(json.dumps(body) + "\n")

    def _load_sequence(self) -> int:
        seq_file = Path(f"a0_seq_{self.agent_id}.txt")
        try:
            return int(seq_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_sequence(self, seq: int):
        Path(f"a0_seq_{self.agent_id}.txt").write_text(str(seq))


# ── Filesystem watcher ────────────────────────────────────────────────────────

if WATCHDOG_AVAILABLE:
    class A0FileEventHandler(FileSystemEventHandler):
        def __init__(self, sender: AgentEventSender):
            self._sender = sender
            self._hash_cache: dict[str, str] = {}  # path → last known hash

        def on_created(self, event):
            if event.is_directory:
                return
            path = event.src_path
            h = sha256_file(path)
            sz = file_size(path)
            if h:
                self._hash_cache[path] = h
            self._sender.send("DOCUMENT_DISCOVERED", path,
                               file_hash_after=h, byte_size=sz)

        def on_modified(self, event):
            if event.is_directory:
                return
            path = event.src_path
            old_hash = self._hash_cache.get(path)
            new_hash = sha256_file(path)
            sz = file_size(path)
            if new_hash == old_hash:
                return  # No actual content change
            if new_hash:
                self._hash_cache[path] = new_hash
            self._sender.send("DOCUMENT_MODIFIED", path,
                               file_hash_before=old_hash,
                               file_hash_after=new_hash, byte_size=sz)

        def on_deleted(self, event):
            if event.is_directory:
                return
            path = event.src_path
            old_hash = self._hash_cache.pop(path, None)
            self._sender.send("DOCUMENT_REMOVED", path, file_hash_before=old_hash)

        def on_moved(self, event):
            if event.is_directory:
                return
            old_path = event.src_path
            new_path = event.dest_path
            old_hash = self._hash_cache.pop(old_path, None)
            new_hash = sha256_file(new_path)
            sz = file_size(new_path)
            if new_hash:
                self._hash_cache[new_path] = new_hash
            self._sender.send("DOCUMENT_RENAMED", new_path,
                               file_hash_before=old_hash, file_hash_after=new_hash,
                               byte_size=sz,
                               payload={"old_path": old_path, "new_path": new_path})


def run_local_agent(
    watch_path: str, agent_id: str, secret: str,
    server_url: str, project_id: str
):
    if not WATCHDOG_AVAILABLE:
        raise RuntimeError("watchdog library required: pip install watchdog")

    sender  = AgentEventSender(agent_id, secret, server_url, project_id)
    handler = A0FileEventHandler(sender)
    observer = Observer()
    observer.schedule(handler, watch_path, recursive=True)
    observer.start()
    logger.info(f"Local agent started — watching {watch_path}")

    try:
        while True:
            time.sleep(1)
            if not observer.is_alive():
                logger.error("Observer died — restarting")
                observer = Observer()
                observer.schedule(handler, watch_path, recursive=True)
                observer.start()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# ── Server-side validation (runs on BOB's server) ────────────────────────────

class AgentEventValidator:
    """
    Validates incoming events from local agents.
    Rejects unsigned, replayed, expired, sequence-gapped, or hash-mismatched events.
    Called by the server endpoint before handing events to the ingestor.
    """

    def __init__(self, agents: dict[str, str]):
        """agents: {agent_id: hmac_secret}"""
        self._agents    = {k: v.encode() if isinstance(v, str) else v for k, v in agents.items()}
        self._seen_nonces: dict[str, float] = {}  # nonce → received_at
        self._last_sequences: dict[str, int] = {}  # agent_id → last_seq
        self._nonce_ttl = 300  # seconds

    def validate(self, body: dict) -> tuple[bool, str]:
        """
        Returns (valid, reason).
        Rejects with specific rejection reason for audit logging.
        """
        agent_id  = body.get("agent_id", "")
        nonce     = body.get("nonce", "")
        timestamp = body.get("timestamp", "")
        sequence  = body.get("sequence", "")
        payload_h = body.get("payload_hash", "")
        signature = body.get("signature", "")

        # 1. Known agent
        if agent_id not in self._agents:
            return False, f"UNKNOWN_AGENT:{agent_id}"

        # 2. Timestamp drift
        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            return False, "INVALID_TIMESTAMP"
        drift = abs(time.time() - ts)
        if drift > 60:
            return False, f"TIMESTAMP_EXPIRED:drift={drift:.0f}s"

        # 3. Nonce reuse
        self._prune_nonces()
        if nonce in self._seen_nonces:
            return False, f"NONCE_REPLAYED:{nonce[:16]}"
        self._seen_nonces[nonce] = time.time()

        # 4. Sequence gap detection
        try:
            seq = int(sequence)
        except (ValueError, TypeError):
            return False, "INVALID_SEQUENCE"
        last_seq = self._last_sequences.get(agent_id, seq - 1)
        if seq <= last_seq:
            return False, f"SEQUENCE_REPLAY:expected>{last_seq},got={seq}"
        if seq > last_seq + 5:  # configurable gap tolerance
            return False, f"SEQUENCE_GAP:expected<={last_seq+5},got={seq}"

        # 5. Payload hash
        body_copy = {k: v for k, v in body.items() if k != "signature"}
        expected_payload_hash = hashlib.sha256(
            json.dumps(body_copy, sort_keys=True).encode()
        ).hexdigest()
        # Recompute without payload_hash field for original hash
        body_no_ph = {k: v for k, v in body_copy.items() if k != "payload_hash"}
        expected_ph = hashlib.sha256(
            json.dumps(body_no_ph, sort_keys=True).encode()
        ).hexdigest()
        if payload_h != expected_ph:
            return False, "PAYLOAD_HASH_MISMATCH"

        # 6. Signature
        signing_string = f"{agent_id}:{nonce}:{timestamp}:{sequence}:{payload_h}"
        expected_sig = hmac.new(
            self._agents[agent_id], signing_string.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return False, "SIGNATURE_INVALID"

        # All checks passed
        self._last_sequences[agent_id] = seq
        return True, "OK"

    def _prune_nonces(self):
        cutoff = time.time() - self._nonce_ttl
        self._seen_nonces = {
            k: v for k, v in self._seen_nonces.items() if v > cutoff
        }


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="A-0 Local File Share Agent")
    parser.add_argument("--agent-id",   required=True)
    parser.add_argument("--secret",     required=True)
    parser.add_argument("--watch-path", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--server-url", default="https://buildtronix.ai/api/precon/agent-push")
    args = parser.parse_args()

    run_local_agent(
        watch_path=args.watch_path,
        agent_id=args.agent_id,
        secret=args.secret,
        server_url=args.server_url,
        project_id=args.project_id,
    )
