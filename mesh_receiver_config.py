"""
D11 — Mesh Receiver Config for Robert

BOB's public key goes here. Robert holds the PUBLIC key only.
Private key never leaves BOB's environment.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# BOB's Ed25519 public key (32 bytes = 64 hex chars)
BOB_PUBLIC_KEY_HEX = os.environ.get(
    "BOB_PUBLIC_KEY_HEX",
    "7915840ab13e8675c94a10b46951bbfaf9f1af1059ea40d5edbec290ec16a44a",
)


async def _mesh_witness_log(event_type: str, content: dict) -> None:
    """
    Robert's Witness log for D11 events.
    Writes local JSONL always; optionally mirrors to Supabase when configured.
    """
    import json
    from datetime import datetime, timezone

    entry = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": content,
        "source": "d11_mesh_receiver",
    }
    try:
        logger.info("[D11 Witness] %s: %s", event_type, json.dumps(content)[:120])
        workspace = os.environ.get("WORKSPACE_PATH", "/var/lib/robert/workspace")
        out_dir = Path(workspace) / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "d11_witness.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error("[D11 Witness] local log failed: %s", e)

    # Optional append-only mirror (Phase C+)
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if url and key and os.environ.get("ROBERT_MESH_WITNESS_SUPABASE", "").lower() in ("1", "true", "yes"):
        try:
            from tools.safe_fetch import safe_fetch
            safe_fetch(
                f"{url}/rest/v1/mesh_witness_events",
                method="POST",
                data=json.dumps(entry).encode(),
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                timeout=5,
            )
        except Exception as e:
            logger.error("[D11 Witness] supabase mirror failed: %s", e)
