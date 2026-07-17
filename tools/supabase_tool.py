"""
Supabase tool for Robert — database operations.
v1.3: write_with_audit RPC for all writes, sanitize_error on all exceptions,
      fetch-before-write handled server-side in write_with_audit.
Phase 1: No deletes. Duplicates/cancellations flagged for human review.
"""
from typing import Dict, List, Optional
from config import SUPABASE_URL, SUPABASE_KEY, ROBERT_AUDITED_WRITES_ENABLED
from tools.base import sanitize_error


class AuditedWritesDisabledError(RuntimeError):
    """
    Raised when a write to an audited table is attempted but
    ROBERT_AUDITED_WRITES_ENABLED=false.

    This is the correct failure mode while write_with_audit RPC and
    FieldOps schema are not yet deployed to Supabase.

    DO NOT catch and fall back to direct inserts. The flag exists
    precisely to prevent unaudited writes to audited tables.

    To enable: set ROBERT_AUDITED_WRITES_ENABLED=true in
    /etc/robert/secrets.env after completing the deployment checklist
    in config.py.
    """
    pass

_client = None

# Tables that must go through write_with_audit (enforced at call sites)
AUDITED_TABLES = {
    'deficiencies',
    'daily_field_reports',
    'roll_call',
    'attachments',
    'override_events',
    'meeting_records',
    'inspection_records',
    'notifications',
    'attendance_records',
}


def get_supabase_client():
    """Get or create Supabase client."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def query_table(
    table: str,
    filters: Optional[Dict] = None,
    *,
    use_actor_jwt: bool = True,
) -> List[Dict]:
    """
    Query a Supabase table.

    Prefer actor JWT (RLS) when available; fall back to service client for
    system/CLI paths without an actor.
    """
    try:
        if use_actor_jwt:
            from tools.actor_context import get_actor_jwt
            jwt = get_actor_jwt()
            if jwt:
                from auth.user_client import get_user_client
                return get_user_client(jwt).select(table, filters=filters)

        client = get_supabase_client()
        query = client.table(table).select("*")

        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)

        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        raise RuntimeError(sanitize_error(f"Failed to query table {table}: {str(e)}"))


def insert_row(
    table: str,
    data: Dict,
    actor_id: str = None,
    project_id: str = None,
    *,
    skip_gate: bool = False,
) -> Dict:
    """
    Insert a row into a Supabase table.
    For audited tables (AUDITED_TABLES), routes through write_with_audit RPC.
    For non-audited tables, inserts directly.
    """
    try:
        from tools.actor_context import get_actor_user_id, require_gate
        if not actor_id:
            actor_id = get_actor_user_id() or None
        if not skip_gate:
            require_gate(
                "create_record" if table not in AUDITED_TABLES else "write_database",
                target=table,
                reversible=True,
                execution_payload={
                    "table": table,
                    "keys": sorted(list(data.keys()))[:40],
                    "actor_id": actor_id or "",
                    "project_id": project_id or "",
                },
            )

        client = get_supabase_client()

        if table in AUDITED_TABLES:
            if not ROBERT_AUDITED_WRITES_ENABLED:
                raise AuditedWritesDisabledError(
                    f"Audited write to '{table}' rejected: ROBERT_AUDITED_WRITES_ENABLED=false. "
                    f"write_with_audit RPC not yet deployed. See config.py for promotion checklist."
                )
            if not actor_id:
                raise ValueError(f"actor_id required for audited table: {table}")
            response = client.rpc("write_with_audit", {
                "p_table_name": table,
                "p_row_data": data,
                "p_actor_id": actor_id,
                "p_action": "create",
                "p_project_id": project_id
            }).execute()
            return {"id": response.data} if response.data else {}
        else:
            response = client.table(table).insert(data).execute()
            return response.data[0] if response.data else {}

    except AuditedWritesDisabledError:
        raise  # never swallow this
    except Exception as e:
        raise RuntimeError(sanitize_error(f"Failed to insert into table {table}: {str(e)}"))


def update_row(
    table: str,
    row_id: str,
    data: Dict,
    actor_id: str = None,
    project_id: str = None,
    *,
    skip_gate: bool = False,
) -> Dict:
    """
    Update a row in a Supabase table.
    For audited tables, routes through write_with_audit RPC (old_value captured server-side).
    """
    try:
        from tools.actor_context import get_actor_user_id, require_gate
        if not actor_id:
            actor_id = get_actor_user_id() or None
        if not skip_gate:
            require_gate(
                "update_record",
                target=f"{table}:{row_id}",
                reversible=True,
                execution_payload={
                    "table": table,
                    "row_id": row_id,
                    "keys": sorted(list(data.keys()))[:40],
                    "actor_id": actor_id or "",
                    "project_id": project_id or "",
                },
            )

        client = get_supabase_client()

        if table in AUDITED_TABLES:
            if not ROBERT_AUDITED_WRITES_ENABLED:
                raise AuditedWritesDisabledError(
                    f"Audited update to '{table}' rejected: ROBERT_AUDITED_WRITES_ENABLED=false. "
                    f"write_with_audit RPC not yet deployed. See config.py for promotion checklist."
                )
            if not actor_id:
                raise ValueError(f"actor_id required for audited table: {table}")
            row_data = {**data, "id": row_id}
            response = client.rpc("write_with_audit", {
                "p_table_name": table,
                "p_row_data": row_data,
                "p_actor_id": actor_id,
                "p_action": "update",
                "p_project_id": project_id
            }).execute()
            return {"id": response.data} if response.data else {}
        else:
            response = client.table(table).update(data).eq("id", row_id).execute()
            return response.data[0] if response.data else {}

    except AuditedWritesDisabledError:
        raise  # never swallow this
    except Exception as e:
        raise RuntimeError(sanitize_error(f"Failed to update row in table {table}: {str(e)}"))


def flag_for_review(table: str, row_id: str, reason: str, actor_id: str, project_id: str = None) -> Dict:
    """
    Flag a record for human review instead of deleting it.
    Phase 1: No deletes. Duplicates and cancellations are flagged.
    Creates a notification for PM/Super review.

    Args:
        table: Source table name
        row_id: UUID of the record to flag
        reason: Reason for flagging (e.g., "potential_duplicate", "cancellation_request")
        actor_id: UUID of the actor flagging the record
        project_id: UUID of the project (optional)

    Returns:
        Created notification record
    """
    notification = {
        "entity_type": table,
        "entity_id": row_id,
        "notification_type": "review_required",
        "reason": reason,
        "status": "pending",
        "project_id": project_id,
    }
    return insert_row("notifications", notification, actor_id=actor_id, project_id=project_id)
