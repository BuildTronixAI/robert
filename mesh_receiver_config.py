"""
D11 — Mesh Receiver Config for Robert

BOB's public key goes here. Robert holds the PUBLIC key only.
Private key never leaves BOB's environment.

To generate a new Ed25519 keypair for BOB:
  from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
  private_key = Ed25519PrivateKey.generate()
  public_key = private_key.public_key()
  pub_bytes = public_key.public_bytes_raw()  # 32 bytes
  print(pub_bytes.hex())  # This goes in BOB_PUBLIC_KEY_HEX below
  # Store private_key bytes securely in BOB's environment only

IMPORTANT: Replace PLACEHOLDER below with BOB's actual Ed25519 public key hex.
Run generate_bob_keypair.py on BOB's server to generate, then paste public key here.
"""

import logging

logger = logging.getLogger(__name__)

# BOB's Ed25519 public key (32 bytes = 64 hex chars)
# PLACEHOLDER — replace with actual BOB public key before deploy
BOB_PUBLIC_KEY_HEX = "7915840ab13e8675c94a10b46951bbfaf9f1af1059ea40d5edbec290ec16a44a"  # Generated 2026-06-24, fingerprint 381693e34fb77a79


async def _mesh_witness_log(event_type: str, content: dict) -> None:
    """
    Robert's Witness log function for D11 events.
    Logs to Robert's Witness append-only log.
    """
    import json
    from datetime import datetime, timezone
    try:
        entry = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content,
            "source": "d11_mesh_receiver",
        }
        logger.info("[D11 Witness] %s: %s", event_type, json.dumps(content)[:120])
        # TODO Phase C: wire to Robert's full Witness (append-only Supabase table)
        # For Phase B: log to file as interim Witness
        with open("/var/lib/robert/workspace/output/d11_witness.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error("[D11 Witness] log failed: %s", e)
