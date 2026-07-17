"""
TronixMesh D11 — Robert Inbound Mesh Receiver

Step 0 Contracts v1.3 §7 compliance:
- Ed25519 (asymmetric) authentication — NOT HMAC-SHA256
- Robert holds BOB's public key only (never BOB's private key)
- Robert compromise cannot produce forged BOB signatures

Phase B (default): STAGED terminal state — no external delivery
Phase C (ROBERT_MESH_PHASE=C): may EXTERNALLY_COMMIT by delivering HMAC
result envelope to BOB_INBOX_URL after staging
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# Task TTL: reject tasks older than this (seconds)
TASK_TTL_SECONDS = 300  # 5 minutes
MAX_TTL_SECONDS = TASK_TTL_SECONDS

# Mesh signing contract version — fields covered by Ed25519 signature
MESH_SIGNING_VERSION = 2

# Nonce window: how long nonces are tracked to prevent replay
NONCE_WINDOW_SECONDS = 600  # 10 minutes


class MeshTaskState(str, Enum):
    RECEIVED = "received"
    VERIFIED = "verified"
    QUEUED = "queued"
    RUNNING = "running"
    STAGED = "staged"                         # Phase B terminal / Phase C intermediate
    EXTERNALLY_COMMITTED = "externally_committed"  # Phase C terminal
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

    Signature v2 covers:
      v ‖ task_id ‖ sender_id ‖ task_type ‖ payload_hash ‖ nonce ‖ issued_at ‖ ttl_seconds
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

        ttl = int(data["ttl_seconds"])
        if ttl <= 0:
            raise MeshSchemaError("ttl_seconds must be positive")
        if ttl > MAX_TTL_SECONDS:
            raise MeshSchemaError(
                f"ttl_seconds {ttl} exceeds MAX_TTL_SECONDS={MAX_TTL_SECONDS}"
            )

        return cls(
            task_id=data["task_id"],
            sender_id=data["sender_id"],
            task_type=data["task_type"],
            payload=data["payload"],
            payload_hash=data["payload_hash"],
            nonce=data["nonce"],
            issued_at=float(data["issued_at"]),
            ttl_seconds=ttl,
            signature=data["signature"],
            received_at=time.time(),
        )

    def signing_message(self) -> bytes:
        """Reconstruct the message that was signed (MESH_SIGNING_VERSION=2)."""
        msg = json.dumps({
            "v": MESH_SIGNING_VERSION,
            "task_id": self.task_id,
            "sender_id": self.sender_id,
            "task_type": self.task_type,
            "payload_hash": self.payload_hash,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "ttl_seconds": self.ttl_seconds,
        }, sort_keys=True, separators=(',', ':')).encode()
        return msg

    def is_expired(self) -> bool:
        """Check if task TTL has elapsed (also reject far-future issued_at)."""
        now = time.time()
        if self.issued_at > now + 60:
            return True
        return (now - self.issued_at) > self.ttl_seconds

    def verify_payload_hash(self) -> bool:
        """Verify payload hash matches actual payload."""
        canonical = json.dumps(self.payload, sort_keys=True, separators=(',', ':')).encode()
        computed = hashlib.sha256(canonical).hexdigest()
        return computed == self.payload_hash


class NonceStore:
    """In-memory nonce store for replay prevention (last-resort fallback)."""

    def __init__(self):
        self._seen: dict[str, float] = {}

    def check_and_record(self, nonce: str) -> bool:
        cutoff = time.time() - NONCE_WINDOW_SECONDS
        self._seen = {n: t for n, t in self._seen.items() if t > cutoff}
        if nonce in self._seen:
            raise MeshReplayError(f"Nonce already seen: {nonce[:16]}...")
        self._seen[nonce] = time.time()
        return True


class MeshReceiver:
    """
    Robert's inbound mesh receiver.

    Phase B: validate → execute → STAGED
    Phase C: validate → execute → STAGED → deliver to BOB → EXTERNALLY_COMMITTED
    """

    def __init__(
        self,
        robert_agent_id: str,
        bob_public_key_hex: str,
        witness_log=None,
        nonce_store=None,
    ):
        self.robert_agent_id = robert_agent_id
        self._bob_public_key_hex = bob_public_key_hex
        self.witness_log = witness_log
        if nonce_store is not None:
            self._nonce_store = nonce_store
        else:
            try:
                from mesh_nonce_store import SharedNonceStore
                self._nonce_store = SharedNonceStore(window_seconds=NONCE_WINDOW_SECONDS)
                logger.info("D11 using SharedNonceStore (supabase→sqlite→memory)")
            except Exception as e:
                logger.warning("D11 SharedNonceStore unavailable (%s) — trying local durable", e)
                try:
                    from robert_store import DurableNonceStore
                    self._nonce_store = DurableNonceStore(window_seconds=NONCE_WINDOW_SECONDS)
                except Exception as e2:
                    logger.warning("D11 durable nonce store unavailable (%s) — in-memory", e2)
                    self._nonce_store = NonceStore()
        self._task_handlers: dict[str, callable] = {}

        try:
            self._bob_public_key = bytes.fromhex(bob_public_key_hex)
        except ValueError as e:
            raise ValueError(f"Invalid BOB public key hex: {e}")

    def register_handler(self, task_type: str, handler) -> None:
        """Register an async handler for a task type."""
        self._task_handlers[task_type] = handler

    async def receive(self, raw_payload: bytes) -> dict:
        """Process a raw inbound mesh message. Returns outcome dict."""
        task = None
        try:
            data = json.loads(raw_payload)
            task = MeshTask.from_dict(data)

            await self._witness("MESH_TASK_RECEIVED", {
                "task_id": task.task_id,
                "sender_id": task.sender_id,
                "task_type": task.task_type,
            })

            await self._validate(task)
            task.state = MeshTaskState.VERIFIED
            task.validated_at = time.time()

            await self._witness("MESH_TASK_VERIFIED", {
                "task_id": task.task_id,
                "task_type": task.task_type,
            })

            task.state = MeshTaskState.QUEUED
            task.state = MeshTaskState.RUNNING

            result = await self._execute(task)

            # Always stage first (integrity hash bound before any external side effect)
            task.staged_payload = result
            task.staged_hash = self._compute_staged_hash(result)
            task.state = MeshTaskState.STAGED

            await self._witness("MESH_TASK_STAGED", {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "staged_hash": task.staged_hash,
            })

            outcome = {
                "state": MeshTaskState.STAGED.value,
                "task_id": task.task_id,
                "staged_hash": task.staged_hash,
                "result": result,
            }

            # Phase C: optional external commit to BOB
            from mesh_outbound import external_commit_enabled, deliver_result_to_bob
            wants_commit = bool(
                (isinstance(task.payload, dict) and task.payload.get("commit_external"))
                or (isinstance(result, dict) and result.get("commit_external"))
                or external_commit_enabled()
            )
            if wants_commit and external_commit_enabled():
                delivery = deliver_result_to_bob(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    staged_hash=task.staged_hash,
                    result=result,
                    sender_id=self.robert_agent_id,
                )
                if delivery.get("ok"):
                    task.state = MeshTaskState.EXTERNALLY_COMMITTED
                    await self._witness("MESH_TASK_EXTERNALLY_COMMITTED", {
                        "task_id": task.task_id,
                        "task_type": task.task_type,
                        "staged_hash": task.staged_hash,
                    })
                    outcome["state"] = MeshTaskState.EXTERNALLY_COMMITTED.value
                    outcome["delivery"] = delivery.get("delivery")
                else:
                    # Fail-closed for commit claim — remain STAGED with error
                    await self._witness("MESH_TASK_COMMIT_FAILED", {
                        "task_id": task.task_id,
                        "error": delivery.get("error", "unknown"),
                    })
                    outcome["commit_error"] = delivery.get("error", "unknown")
                    logger.error(
                        "D11 Phase C commit failed — remaining STAGED: %s",
                        delivery.get("error"),
                    )
            elif wants_commit and not external_commit_enabled():
                outcome["commit_error"] = "phase_b_external_commit_disabled"
                logger.warning(
                    "D11 commit_external requested but ROBERT_MESH_PHASE!=C — remaining STAGED"
                )

            return outcome

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
        Validation order is load-bearing:
        1. TTL  2. payload hash  3. Ed25519  4. nonce claim
        """
        if task.is_expired():
            raise MeshTTLError(
                f"Task {task.task_id} TTL expired "
                f"(issued={task.issued_at:.0f} ttl={task.ttl_seconds}s "
                f"age={(time.time()-task.issued_at):.0f}s)"
            )

        if not task.verify_payload_hash():
            raise MeshAuthError(
                f"Payload hash mismatch for task {task.task_id} — "
                "payload may have been tampered in transit"
            )

        self._verify_signature(task)

        # Nonce claim after authenticity
        try:
            self._nonce_store.check_and_record(
                task.nonce, task.task_id, getattr(task, "sender_id", "")
            )  # type: ignore[call-arg]
        except TypeError:
            try:
                self._nonce_store.check_and_record(task.nonce, task.task_id)  # type: ignore[call-arg]
            except TypeError:
                self._nonce_store.check_and_record(task.nonce)
        except MeshReplayError:
            raise
        except Exception as e:
            if e.__class__.__name__ in ("DurableReplayError", "MeshReplayError"):
                raise MeshReplayError(str(e)) from e
            raise

    def _verify_signature(self, task: MeshTask) -> None:
        """Verify Ed25519 signature using BOB's PUBLIC key. Fail-closed."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.exceptions import InvalidSignature
        except ImportError as e:
            raise MeshAuthError(
                "cryptography library not available — Ed25519 verification "
                "is mandatory (fail-closed). Install cryptography."
            ) from e

        public_key = Ed25519PublicKey.from_public_bytes(self._bob_public_key)
        try:
            signature_bytes = base64.b64decode(task.signature, validate=True)
        except Exception as e:
            raise MeshAuthError(f"Invalid signature encoding for task {task.task_id}") from e
        message = task.signing_message()

        try:
            public_key.verify(signature_bytes, message)
        except InvalidSignature:
            raise MeshAuthError(
                f"Ed25519 signature invalid for task {task.task_id} "
                f"from sender {task.sender_id}"
            )

    async def _execute(self, task: MeshTask) -> dict:
        """Execute the task using registered handler."""
        handler = self._task_handlers.get(task.task_type)
        if handler is None:
            raise ValueError(f"No handler registered for task type: {task.task_type}")
        result = await handler(task.task_id, task.payload)
        return result

    def _compute_staged_hash(self, result: dict) -> str:
        """Compute SHA-256 hash of staged result."""
        canonical = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(canonical).hexdigest()

    async def _witness(self, event_type: str, content: dict) -> None:
        """Log to Robert's Witness."""
        if self.witness_log:
            try:
                await self.witness_log(event_type, content)
            except Exception as e:
                logger.error("D11 witness log failed: %s", e)
