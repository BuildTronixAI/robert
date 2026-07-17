"""Robert tools package — lazy exports so optional deps don't block imports."""

from typing import Any

__all__ = [
    "read_memory",
    "write_memory",
    "append_memory",
    "run_command",
    "send_telegram",
    "query_table",
    "insert_row",
    "get_supabase_client",
    "send_email",
]


def __getattr__(name: str) -> Any:
    if name in ("read_memory", "write_memory", "append_memory"):
        from .memory import read_memory, write_memory, append_memory
        return {
            "read_memory": read_memory,
            "write_memory": write_memory,
            "append_memory": append_memory,
        }[name]
    if name == "run_command":
        from .exec_tool import run_command
        return run_command
    if name == "send_telegram":
        from .telegram import send_telegram
        return send_telegram
    if name in ("query_table", "insert_row", "get_supabase_client"):
        from .supabase_tool import query_table, insert_row, get_supabase_client
        return {
            "query_table": query_table,
            "insert_row": insert_row,
            "get_supabase_client": get_supabase_client,
        }[name]
    if name == "send_email":
        from .sendgrid import send_email
        return send_email
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
