"""
Supabase tool for Robert — database operations.
v1.3: write_with_audit RPC for all writes, sanitize_error on all exceptions,
      fetch-before-write handled server-side in write_with_audit.
Phase 1: No deletes. Duplicates/cancellations flagged for human review.
"""
from typing import Dict, List, Optional
from supabase import create_client
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
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def query_table(table: str, filters: Optional[Dict] = None) -> List[Dict]:
    """
    Query a Supabase table.

    Args:
        table: Table name
        filters: Optional filter dictionary (e.g., {"column": "value"})

    Returns:
        List of rows matching the query
    """
    try:
        client = get_supabase_client()
        query = client.table(table).select("*")

        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)

        response = query.execute()
        return response.data if response.data else []
    except Exception as e:
        raise RuntimeError(sanitize_error(f"Failed to query table {table}: {str(e)}"))


def insert_row(table: str, data: Dict, actor_id: str = None, project_id: str = None) -> Dict:
    """
    Insert a row into a Supabase table.
    For audited tables (AUDITED_TABLES), routes through write_with_audit RPC.
    For non-audited tables, inserts directly.

    Args:
        table: Table name
        data: Row data dictionary
        actor_id: UUID of the actor performing the insert (required for audited tables)
        project_id: UUID of the project (optional)

    Returns:
        Inserted row data
    """
    try:
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


def update_row(table: str, row_id: str, data: Dict, actor_id: str = None, project_id: str = None) -> Dict:
    """
    Update a row in a Supabase table.
    For audited tables, routes through write_with_audit RPC (old_value captured server-side).

    Args:
        table: Table name
        row_id: UUID of the row to update
        data: Updated fields
        actor_id: UUID of the actor performing the update (required for audited tables)
        project_id: UUID of the project (optional)

    Returns:
        Updated row data
    """
    try:
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
