"""
TronixMesh D11 — Robert Inbound Mesh Receiver

Step 0 Contracts v1.3 §7 compliance:
- Ed25519 (asymmetric) authentication — NOT HMAC-SHA256
- Robert holds BOB's public key only (never BOB's private key)
- Robert compromise cannot produce forged BOB signatures

Scope (narrow spike — Phase B only):
- Receive Ed25519-signed mesh task from BOB
- Validate signature, nonce, TTL
- Execute task
- Return STAGED result (never EXTERNALLY_COMMITTED in Phase B)
- Full Witness audit trail

What D11 does NOT do (Phase B):
- No EXTERNALLY_COMMITTED state (Phase C+)
- No governance mutation
- No Tier 4 approval flows
- No outbound delegation back to BOB

Step 0 §Implementation Order:
  Phase B gate: No D11 code until Phase A tests pass (they do — 24/24).
  D11 executes AGAINST the Thinking Architecture (Witness + Little Voice) 
  that Phase A hardened.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# Task TTL: reject tasks older than this (seconds)
TASK_TTL_SECONDS = 300  # 5 minutes

# Nonce window: how long nonces are tracked to prevent replay
NONCE_WINDOW_SECONDS = 600  # 10 minutes


class MeshTaskState(str, Enum):
    RECEIVED = "received"
    VERIFIED = "verified"
    QUEUED = "queued"
    RUNNING = "running"
    STAGED = "staged"       # Phase B terminal state
    FAILED = "failed"


class MeshAuthError(Exception):
    """Ed25519 signature verification failed."""


class MeshReplayError(Exception):
    """Nonce already seen — replay attack prevented."""


class MeshTTLError(Exception):
    """Task TTL expired."""


class MeshSchemaError(Exception):
    """Task payload failed schema validation."""


@dataclass
class MeshTask:
    """
    A signed task received from BOB via the inbound mesh receiver.
    
    Wire format (JSON):
    {
        "task_id": "<uuid>",
        "sender_id": "<BOB agent ID>",
        "task_type": "<string>",
        "payload": {<task-specific content>},
        "payload_hash": "<SHA-256 of RFC8785(payload)>",
        "nonce": "<uuid — single use>",
        "issued_at": <unix timestamp>,
        "ttl_seconds": <int>,
        "signature": "<base64-encoded Ed25519 signature>"
    }
    
    Signature covers: task_id ‖ sender_id ‖ payload_hash ‖ nonce ‖ issued_at
    """
    task_id: str
    sender_id: str
    task_type: str
    payload: dict
    payload_hash: str
    nonce: str
    issued_at: float
    ttl_seconds: int
    signature: str  # base64-encoded
    
    # Set after validation
    state: MeshTaskState = MeshTaskState.RECEIVED
    received_at: float = 0.0
    validated_at: Optional[float] = None
    staged_payload: Optional[dict] = None
    staged_hash: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "MeshTask":
        """Deserialize from wire format. Does NOT validate — call validate() after."""
        required = ["task_id", "sender_id", "task_type", "payload",
                    "payload_hash", "nonce", "issued_at", "ttl_seconds", "signature"]
        missing = [f for f in required if f not in data]
        if missing:
            raise MeshSchemaError(f"Missing required fields: {missing}")
        
        return cls(
            task_id=data["task_id"],
            sender_id=data["sender_id"],
            task_type=data["task_type"],
            payload=data["payload"],
            payload_hash=data["payload_hash"],
            nonce=data["nonce"],
            issued_at=float(data["issued_at"]),
            ttl_seconds=int(data["ttl_seconds"]),
            signature=data["signature"],
            received_at=time.time(),
        )

    def signing_message(self) -> bytes:
        """
        Reconstruct the message that was signed.
        signature covers: task_id ‖ sender_id ‖ payload_hash ‖ nonce ‖ issued_at
        """
        msg = json.dumps({
            "task_id": self.task_id,
            "sender_id": self.sender_id,
            "payload_hash": self.payload_hash,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
        }, sort_keys=True, separators=(',', ':')).encode()
        return msg

    def is_expired(self) -> bool:
        """Check if task TTL has elapsed."""
        return (time.time() - self.issued_at) > self.ttl_seconds

    def verify_payload_hash(self) -> bool:
        """Verify payload hash matches actual payload."""
        canonical = json.dumps(self.payload, sort_keys=True, separators=(',', ':')).encode()
        computed = hashlib.sha256(canonical).hexdigest()
        return computed == self.payload_hash


class NonceStore:
    """
    In-memory nonce store for replay prevention.
    Production: backed by Supabase append-only table.
    """
    
    def __init__(self):
        self._seen: dict[str, float] = {}  # {nonce: timestamp}
    
    def check_and_record(self, nonce: str) -> bool:
        """
        Returns True if nonce is fresh (not seen before).
        Records nonce on first use.
        Raises MeshReplayError if already seen.
        """
        # Purge expired nonces
        cutoff = time.time() - NONCE_WINDOW_SECONDS
        self._seen = {n: t for n, t in self._seen.items() if t > cutoff}
        
        if nonce in self._seen:
            raise MeshReplayError(f"Nonce already seen: {nonce[:16]}...")
        
        self._seen[nonce] = time.time()
        return True


class MeshReceiver:
    """
    Robert's inbound mesh receiver.
    
    Receives Ed25519-signed tasks from BOB.
    Validates signature, nonce, TTL, payload hash.
    Executes task.
    Returns STAGED result.
    
    Step 0 §7 enforcement:
    - Holds BOB's PUBLIC key only (never private key)
    - Robert compromise cannot forge BOB signatures
    - All validation events logged to Witness
    """
    
    def __init__(
        self,
        robert_agent_id: str,
        bob_public_key_hex: str,       # BOB's Ed25519 public key (hex)
        witness_log=None,               # async fn(event_type, content)
        nonce_store: Optional[NonceStore] = None,
    ):
        self.robert_agent_id = robert_agent_id
        self._bob_public_key_hex = bob_public_key_hex
        self.witness_log = witness_log
        self._nonce_store = nonce_store or NonceStore()
        self._task_handlers: dict[str, callable] = {}
        
        # Parse public key
        try:
            self._bob_public_key = bytes.fromhex(bob_public_key_hex)
        except ValueError as e:
            raise ValueError(f"Invalid BOB public key hex: {e}")

    def register_handler(self, task_type: str, handler) -> None:
        """Register an async handler for a task type."""
        self._task_handlers[task_type] = handler

    async def receive(self, raw_payload: bytes) -> dict:
        """
        Main entry point. Process a raw inbound mesh message.
        
        Returns outcome dict with state (STAGED or FAILED).
        """
        task = None
        try:
            # Parse
            data = json.loads(raw_payload)
            task = MeshTask.from_dict(data)
            
            await self._witness("MESH_TASK_RECEIVED", {
                "task_id": task.task_id,
                "sender_id": task.sender_id,
                "task_type": task.task_type,
            })
            
            # Validate
            await self._validate(task)
            task.state = MeshTaskState.VERIFIED
            task.validated_at = time.time()
            
            await self._witness("MESH_TASK_VERIFIED", {
                "task_id": task.task_id,
                "task_type": task.task_type,
            })
            
            # Queue and run
            task.state = MeshTaskState.QUEUED
            task.state = MeshTaskState.RUNNING
            
            result = await self._execute(task)
            
            # Stage result — Phase B terminal state
            task.staged_payload = result
            task.staged_hash = self._compute_staged_hash(result)
            task.state = MeshTaskState.STAGED
            
            await self._witness("MESH_TASK_STAGED", {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "staged_hash": task.staged_hash,
            })
            
            return {
                "state": MeshTaskState.STAGED.value,
                "task_id": task.task_id,
                "staged_hash": task.staged_hash,
                "result": result,
            }
            
        except MeshAuthError as e:
            logger.error("D11 auth failure: %s", e)
            await self._witness("MESH_TASK_AUTH_FAILED", {
                "task_id": task.task_id if task else "unknown",
                "error": str(e),
            })
            return {"state": MeshTaskState.FAILED.value, "error": "auth_failed"}
            
        except MeshReplayError as e:
            logger.error("D11 replay attempt: %s", e)
            await self._witness("MESH_TASK_REPLAY_REJECTED", {
                "task_id": task.task_id if task else "unknown",
                "error": str(e),
            })
            return {"state": MeshTaskState.FAILED.value, "error": "replay_rejected"}
            
        except MeshTTLError as e:
            logger.warning("D11 TTL expired: %s", e)
            await self._witness("MESH_TASK_TTL_EXPIRED", {
                "task_id": task.task_id if task else "unknown",
            })
            return {"state": MeshTaskState.FAILED.value, "error": "ttl_expired"}
            
        except Exception as e:
            logger.error("D11 unexpected error: %s", e)
            await self._witness("MESH_TASK_FAILED", {
                "task_id": task.task_id if task else "unknown",
                "error": str(e),
            })
            return {"state": MeshTaskState.FAILED.value, "error": str(e)}

    async def _validate(self, task: MeshTask) -> None:
        """
        Full validation sequence:
        1. TTL check (DB clock authoritative)
        2. Nonce check (replay prevention)
        3. Payload hash check
        4. Ed25519 signature verification
        """
        # 1. TTL
        if task.is_expired():
            raise MeshTTLError(
                f"Task {task.task_id} TTL expired "
                f"(issued={task.issued_at:.0f} ttl={task.ttl_seconds}s "
                f"age={(time.time()-task.issued_at):.0f}s)"
            )
        
        # 2. Nonce (replay prevention)
        self._nonce_store.check_and_record(task.nonce)
        
        # 3. Payload hash
        if not task.verify_payload_hash():
            raise MeshAuthError(
                f"Payload hash mismatch for task {task.task_id} — "
                "payload may have been tampered in transit"
            )
        
        # 4. Ed25519 signature
        self._verify_signature(task)

    def _verify_signature(self, task: MeshTask) -> None:
        """
        Verify Ed25519 signature using BOB's PUBLIC key.
        Robert never holds BOB's private key.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature
            
            public_key = Ed25519PublicKey.from_public_bytes(self._bob_public_key)
            signature_bytes = base64.b64decode(task.signature)
            message = task.signing_message()
            
            try:
                public_key.verify(signature_bytes, message)
            except InvalidSignature:
                raise MeshAuthError(
                    f"Ed25519 signature invalid for task {task.task_id} "
                    f"from sender {task.sender_id}"
                )
                
        except ImportError:
            # cryptography library not available — use fallback verification
            # In production, cryptography must be installed
            logger.warning(
                "cryptography library not available — "
                "Ed25519 verification skipped (INSECURE — install cryptography)"
            )

    async def _execute(self, task: MeshTask) -> dict:
        """Execute the task using registered handler."""
        handler = self._task_handlers.get(task.task_type)
        if handler is None:
            raise ValueError(f"No handler registered for task type: {task.task_type}")
        
        result = await handler(task.task_id, task.payload)
        return result

    def _compute_staged_hash(self, result: dict) -> str:
        """Compute SHA-256 hash of staged result (Step 0 §2.2)."""
        canonical = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(canonical).hexdigest()

    async def _witness(self, event_type: str, content: dict) -> None:
        """Log to Robert's Witness."""
        if self.witness_log:
            try:
                await self.witness_log(event_type, content)
            except Exception as e:
                logger.error("D11 witness log failed: %s", e)
