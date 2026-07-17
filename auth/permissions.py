"""
auth/permissions.py — Robert Role-Based Permission System
=========================================================
Phase 2: Enforce role-based access control on commands and actions.

Roles (from Supabase profiles table):
  OWNER       — Chris Leiser. Full access. No restrictions.
  ADMIN       — Trusted team member. Most access, no billing/config.
  PM          — Project Manager. Project-scoped access only.
  FIELD_SUPER — Field Supervisor. Read-only + task submission.
  CLIENT      — End client. Read-only status queries only.
  GUEST       — Unknown/unverified. Minimal access.
"""

import logging

logger = logging.getLogger(__name__)

# Role hierarchy: higher number = more permissions
ROLE_HIERARCHY = {
    "OWNER":       100,
    "ADMIN":       80,
    "PM":          60,
    "FIELD_SUPER": 40,
    "CLIENT":      20,
    "GUEST":       0,
}

# Command permission matrix: command prefix → minimum role level required
COMMAND_PERMISSIONS = {
    "/admin":    100,  # OWNER only
    "/config":   100,  # OWNER only
    "/kill":     100,  # OWNER only
    "/reboot":   100,  # OWNER only
    "/report":   80,   # ADMIN+
    "/summary":  80,   # ADMIN+
    "/status":   80,   # ADMIN+
    "/project":  60,   # PM+
    "/task":     60,   # PM+
    "/bid":      60,   # PM+
    "/update":   40,   # FIELD_SUPER+
    "/checkin":  40,   # FIELD_SUPER+
    "/help":     20,   # CLIENT+
    "/info":     20,   # CLIENT+
}

# Free-text (no / prefix) — Phase 2: OWNER only
FREE_TEXT_MIN_ROLE = 100  # OWNER


def check_permission(role: str, command: str) -> tuple[bool, str]:
    """
    Check if a role can execute a command.
    
    Args:
        role:    User's buildtronix_role (e.g., "OWNER", "PM")
        command: Raw message text (e.g., "/admin status" or "write a spec")
    
    Returns:
        Tuple of (allowed: bool, reason: str)
        - (True, "")                           if allowed
        - (False, "reason for denial")         if denied
    """
    # Normalize role
    if role not in ROLE_HIERARCHY:
        logger.warning(f"[permissions] Unknown role: {role}")
        return False, f"Unknown role: {role}"
    
    role_level = ROLE_HIERARCHY[role]
    
    # Extract command (first word if starts with /)
    cmd = command.strip().lower()
    
    if cmd.startswith("/"):
        # Find the command prefix (e.g., "/admin" from "/admin status")
        cmd_prefix = cmd.split()[0]  # "/admin", "/status", etc.
        
        # Check explicit command permission
        if cmd_prefix in COMMAND_PERMISSIONS:
            required_level = COMMAND_PERMISSIONS[cmd_prefix]
            if role_level >= required_level:
                logger.info(f"[permissions] ALLOWED: role={role} ({role_level}) command={cmd_prefix} (requires {required_level})")
                return True, ""
            else:
                reason = f"{cmd_prefix} requires {get_role_label(role_for_level(required_level))} or higher"
                logger.info(f"[permissions] DENIED: role={role} ({role_level}) command={cmd_prefix} (requires {required_level})")
                return False, reason
        else:
            # Unknown command — allow OWNER, deny others
            if role_level >= 100:
                logger.info(f"[permissions] ALLOWED: role={role} ({role_level}) unknown command={cmd_prefix}")
                return True, ""
            else:
                logger.info(f"[permissions] DENIED: role={role} ({role_level}) unknown command={cmd_prefix} not in whitelist")
                return False, f"Command {cmd_prefix} not recognized or not available to {role}"
    else:
        # Free-text task (no / prefix)
        # Phase 2: OWNER only
        if role_level >= FREE_TEXT_MIN_ROLE:
            logger.info(f"[permissions] ALLOWED: role={role} ({role_level}) free-text task")
            return True, ""
        else:
            logger.info(f"[permissions] DENIED: role={role} ({role_level}) free-text task (Phase 2: OWNER only)")
            return False, "Free-text tasks are restricted to OWNER. Use /help for available commands."


def get_role_label(role: str) -> str:
    """Return human-readable label for a role."""
    labels = {
        "OWNER":       "Owner",
        "ADMIN":       "Administrator",
        "PM":          "Project Manager",
        "FIELD_SUPER": "Field Supervisor",
        "CLIENT":      "Client",
        "GUEST":       "Guest",
    }
    return labels.get(role, role)


def role_for_level(level: int) -> str:
    """Given a role level, return the role name (lowest role at that level)."""
    for role, role_level in sorted(ROLE_HIERARCHY.items(), key=lambda x: -x[1]):
        if role_level <= level:
            return role
    return "GUEST"


def is_owner(role: str) -> bool:
    """Convenience check: is this role the OWNER?"""
    return role == "OWNER"
