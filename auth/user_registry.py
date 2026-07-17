"""
auth/user_registry.py — Local user registry cache
==================================================
Caches Supabase profile lookups to avoid hitting the DB on every message.
TTL: 5 minutes. Cleared on Robert restart.

Thread-safe in-memory cache using a Lock.
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)

# In-memory cache: telegram_user_id -> (profile_dict, timestamp_cached)
_cache = {}
_cache_lock = threading.Lock()

# Cache TTL: 5 minutes
CACHE_TTL_SECONDS = 300


def get_cached_profile(telegram_user_id: int) -> dict | None:
    """
    Retrieve cached profile for a Telegram user if present and not expired.
    
    Args:
        telegram_user_id: Integer Telegram user ID
    
    Returns:
        Profile dict if cached and not expired, else None
    """
    with _cache_lock:
        if telegram_user_id not in _cache:
            logger.debug(f"[user_registry] Cache miss: {telegram_user_id}")
            return None
        
        profile, ts_cached = _cache[telegram_user_id]
        now = time.time()
        age = now - ts_cached
        
        if age > CACHE_TTL_SECONDS:
            logger.debug(f"[user_registry] Cache expired (age={age}s): {telegram_user_id}")
            del _cache[telegram_user_id]
            return None
        
        logger.debug(f"[user_registry] Cache hit (age={age}s): {telegram_user_id}")
        return profile


def cache_profile(telegram_user_id: int, profile: dict) -> None:
    """
    Store a profile in the cache.
    
    Args:
        telegram_user_id: Integer Telegram user ID
        profile: Profile dict from resolve_identity (user_id, role, org_id, project_ids, etc.)
    """
    with _cache_lock:
        now = time.time()
        _cache[telegram_user_id] = (profile, now)
        logger.info(f"[user_registry] Cached profile for {telegram_user_id} (expires in {CACHE_TTL_SECONDS}s)")


def invalidate(telegram_user_id: int) -> None:
    """
    Manually invalidate cache entry (e.g., if user role changed).
    
    Args:
        telegram_user_id: Integer Telegram user ID
    """
    with _cache_lock:
        if telegram_user_id in _cache:
            del _cache[telegram_user_id]
            logger.info(f"[user_registry] Invalidated cache for {telegram_user_id}")
        else:
            logger.debug(f"[user_registry] Tried to invalidate non-cached user {telegram_user_id}")


def clear_all() -> None:
    """Clear entire cache (used on shutdown or testing)."""
    with _cache_lock:
        count = len(_cache)
        _cache.clear()
        logger.info(f"[user_registry] Cleared cache ({count} entries)")


def cache_size() -> int:
    """Return current number of cached profiles."""
    with _cache_lock:
        return len(_cache)
