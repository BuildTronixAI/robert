"""
auth/__init__.py — Phase 1 + Phase 2 Exports
==============================================
Central export point for all auth modules.

Phase 1 (Identity Resolution):
  - resolve_identity_and_mint()
  - IdentityNotFoundError
  - JWTMintError

Phase 2 (Role-Based Permissions):
  - check_permission()
  - is_owner()
  - get_cached_profile()
  - cache_profile()
  - invalidate()
"""

from .jwt_minter import (
    resolve_identity_and_mint,
    IdentityNotFoundError,
    JWTMintError,
)

from .permissions import (
    check_permission,
    is_owner,
    get_role_label,
    role_for_level,
)

from .user_registry import (
    get_cached_profile,
    cache_profile,
    invalidate,
    clear_all,
    cache_size,
)

__all__ = [
    # Phase 1
    "resolve_identity_and_mint",
    "IdentityNotFoundError",
    "JWTMintError",
    
    # Phase 2
    "check_permission",
    "is_owner",
    "get_role_label",
    "role_for_level",
    "get_cached_profile",
    "cache_profile",
    "invalidate",
    "clear_all",
    "cache_size",
]
