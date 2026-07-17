"""
tronix_human_protection.py
RR-0056 Phase 1 — Gap 2: Human Node Protection
Constitutional requirement: BOB v3.5 §19

Deploy to: /var/lib/robert/workspace/tronix_human_protection.py
Import in: policy_gate.py (add reject_if_human() call at gate entry)
"""

import time
import logging
import os

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------------------------
NODE_TYPE_CACHE: dict = {}
_cache_loaded_at: float = 0.0  # starts at 0 so first call always triggers refresh
_CACHE_TTL: int = 300  # 5-minute TTL

# COLD-START NOTE: If the first refresh fails (transient Supabase blip at startup),
# cache stays empty and every node returns UNKNOWN → HumanEscalationRequired.
# This is fail-safe by design. A startup network failure escalates ALL operations
# to Chris until the cache is successfully populated.
# Phase 2: add retry-with-backoff on startup refresh.

# STALENESS BOUND: A node reclassified as HUMAN mid-session receives AGENT
# treatment for up to 300 seconds until the next successful cache refresh.
# Phase 2: add Supabase realtime subscription to invalidate immediately.

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ---------------------------------------------------------------------------
# Operations blocked on HUMAN nodes (BOB v3.5 §19)
# ---------------------------------------------------------------------------
BLOCKED_ON_HUMAN = frozenset([
    "confidence_score_calculation",
    "autonomous_task_reassignment",
    "deadline_enforcement",
    "revision_loop_enforcement",
    "authority_tier_escalation",
    "behavioral_prediction",
    "compensation_recommendation",
])

# Operations explicitly permitted on HUMAN nodes
PERMITTED_ON_HUMAN = frozenset([
    "send_notification",
    "assign_hitl_approval",
    "read_profile",
    "log_interaction",
])

# ---------------------------------------------------------------------------
# Custom exceptions — three explicit enforcement states
# ---------------------------------------------------------------------------
class TronixHumanNodeViolation(Exception):
    """DENY state: operation is constitutionally blocked on a HUMAN node."""
    pass

class HumanEscalationRequired(Exception):
    """ESCALATE state: operation requires human decision before proceeding."""
    pass


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------
def _refresh_human_node_cache() -> None:
    """Refresh node type cache from tronix_node_registry."""
    global NODE_TYPE_CACHE, _cache_loaded_at
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = client.table("tronix_node_registry").select("node_id, node_type").eq("status", "active").execute()
        NODE_TYPE_CACHE = {row["node_id"]: row["node_type"] for row in response.data}
        _cache_loaded_at = time.time()
        _log.info(f"Human node cache refreshed: {len(NODE_TYPE_CACHE)} entries")
    except Exception as e:
        _log.error(f"Failed to refresh human node cache: {e}")
        # Cache remains stale until next successful refresh.
        # STALENESS BOUND: up to _CACHE_TTL seconds (300s).
        # A node reclassified as HUMAN stays AGENT-treated until next success.


def get_node_type(node_id: str) -> str:
    """Return node type from cache with TTL refresh. Returns 'UNKNOWN' if not found."""
    global _cache_loaded_at

    # Refresh if TTL expired (or cold start: _cache_loaded_at = 0)
    if time.time() - _cache_loaded_at > _CACHE_TTL:
        _refresh_human_node_cache()

    # Fail-safe default: UNKNOWN (not AGENT)
    # Unknown nodes NEVER default to AGENT — that would bypass human protection
    return NODE_TYPE_CACHE.get(node_id, "UNKNOWN")


# ---------------------------------------------------------------------------
# Core enforcement function
# ---------------------------------------------------------------------------
def reject_if_human(node_id: str, operation: str, agent_id: str = None) -> None:
    """
    Enforce human node protection for a given operation.

    Three explicit states — no None returns, no silent passes:
      PERMIT  — returns normally (no exception)
      DENY    — raises TronixHumanNodeViolation
      ESCALATE — raises HumanEscalationRequired

    Args:
        node_id:    Target node identifier
        operation:  Operation being attempted
        agent_id:   Agent performing the operation (for audit logging)

    Raises:
        TronixHumanNodeViolation:  DENY — operation constitutionally blocked on HUMAN
        HumanEscalationRequired:   ESCALATE — unclassified operation or unknown node
    """
    node_type = get_node_type(node_id)

    # UNKNOWN node → fail-safe escalation (never treat as AGENT)
    if node_type == "UNKNOWN":
        _log.warning(
            f"ESCALATE: node_id={node_id!r} has no classification. "
            f"operation={operation!r}, agent_id={agent_id!r}"
        )
        raise HumanEscalationRequired(
            f"Node '{node_id}' has no classification in tronix_node_registry. "
            f"Operation '{operation}' blocked pending Chris Leiser classification. "
            f"Unknown nodes are constitutionally protected by default."
        )

    # AGENT node → permit all operations (no restriction)
    if node_type == "AGENT":
        return  # PERMIT

    # HUMAN node — evaluate operation
    if node_type == "HUMAN":

        if operation in BLOCKED_ON_HUMAN:
            # DENY state
            _log.warning(
                f"DENY [HUMAN_NODE_PROTECTION]: node_id={node_id!r}, "
                f"operation={operation!r}, agent_id={agent_id!r}"
            )
            raise TronixHumanNodeViolation(
                f"Operation '{operation}' is constitutionally blocked on HUMAN node '{node_id}'. "
                f"BOB v3.5 §19 prohibits this operation on human participants."
            )

        if operation in PERMITTED_ON_HUMAN:
            # PERMIT state — explicitly allowed on humans
            _log.debug(
                f"PERMIT [HUMAN_ALLOWED]: node_id={node_id!r}, "
                f"operation={operation!r}, agent_id={agent_id!r}"
            )
            return  # PERMIT

        # Operation not in either list → ESCALATE (unclassified)
        _log.warning(
            f"ESCALATE [UNCLASSIFIED_OP]: node_id={node_id!r} is HUMAN, "
            f"operation={operation!r} is not in BLOCKED or PERMITTED list. "
            f"agent_id={agent_id!r}"
        )
        raise HumanEscalationRequired(
            f"Operation '{operation}' on HUMAN node '{node_id}' is unclassified. "
            f"Not in BLOCKED_ON_HUMAN or PERMITTED_ON_HUMAN lists. "
            f"Escalating to Chris Leiser for classification before proceeding."
        )

    # Unexpected node_type value — fail-safe
    _log.error(f"Unexpected node_type={node_type!r} for node_id={node_id!r}. Escalating.")
    raise HumanEscalationRequired(
        f"Unexpected node type '{node_type}' for node '{node_id}'. Escalating."
    )
