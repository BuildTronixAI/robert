#!/usr/bin/env python3
"""
utils.py — Robert Shared Safety Utilities
==========================================
# Mirror of bob/scripts/utils.py::atomic_write — keep in sync manually.
# If you change atomic_write() or startup_cleanup_tmp() here, update
# /root/.openclaw/workspace/scripts/utils.py and vice versa.
# Changes to this file require a new Review Request per protocol.
# See RR-0013 (2026-04-24) and the April 23 memory corruption incident.

Functions:
  atomic_write()         — Write a file atomically via temp-then-rename with fsync hardening
  startup_cleanup_tmp()  — Remove orphaned .tmp files on startup
"""

import os
import tempfile
import glob
import logging
from datetime import datetime, timezone


def atomic_write(filepath, content, mode="w", encoding="utf-8"):
    """
    Write content to filepath atomically using temp-then-rename with fsync hardening.

    This pattern prevents partial-write corruption on crash or power loss.
    Pattern is LOAD-BEARING — do not simplify. See RR-0013 (2026-04-24) and the
    April 23 memory corruption incident for full context.

    Why this works:
    - Writes to a .tmp file in the same directory (same filesystem = rename is atomic)
    - os.fsync() before rename guarantees contents are flushed to disk, not just OS buffer
    - os.rename() is atomic at filesystem metadata level on POSIX
    - Directory fsync after rename ensures directory entry is flushed (power-loss safety)
    - On crash mid-write, only the .tmp file is left; the target file is intact

    Note: scope is text files (.md, .json). For binary files, pass mode="wb" and encoding=None.
    """
    dirpath = os.path.dirname(os.path.abspath(filepath))
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
    try:
        with os.fdopen(fd, mode, encoding=encoding if "b" not in mode else None) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # Force contents to disk before rename
        os.rename(tmp_path, filepath)
        # Flush directory entry — belt-and-suspenders for power loss / kernel panic
        dir_fd = os.open(dirpath, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


# ── Backup constants (Robert-specific) ───────────────────────────────────────
BACKUP_DIR_ROBERT = "/var/lib/robert/backups"
CRITICAL_RETENTION_DAYS = 14   # robert_memory.json, limits.json
STANDARD_RETENTION_DAYS = 7    # all other files
CRITICAL_FILES = {"robert_memory.json", "limits.json"}  # Robert's critical state
CRITICAL_MODULES = set()  # Robert has no .md modules

_backup_failure_counts = {}


def backup_before_write(filepath, backup_dir, retention_days=STANDARD_RETENTION_DAYS):
    """
    Copy filepath to backup_dir with timestamp suffix before any write.
    Then prune backups older than retention_days for this file.

    NON-FATAL: on any failure, logs a warning and returns without raising.
    The calling write MUST proceed regardless of backup outcome.

    Uses atomic_write() for the backup file itself — a corrupted backup that
    appears complete is worse than no backup. (RR-0014-rev2)

    # Text files only (.md, .json) under a few MB.
    # Reads entire file into memory before atomic_write;
    # not suitable for streaming large files or binaries.

    # Mirror of bob/scripts/utils.py::backup_before_write — keep in sync manually.
    # If you change this function, update /root/.openclaw/workspace/scripts/utils.py
    # and vice versa. Changes require a new RR per the Review Request Protocol.

    See RR-0014 (2026-04-24). Two-layer write safety:
    Layer 1: atomic_write() (RR-0013) — prevents partial writes on crash
    Layer 2: backup_before_write() (this) — rollback if write completes with bad content
    """
    # Guard: nothing to backup on first-time write
    if not os.path.exists(filepath):
        return

    os.makedirs(backup_dir, exist_ok=True)
    basename = os.path.basename(filepath)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    backup_path = os.path.join(backup_dir, f"{basename}.{ts}.bak")

    try:
        with open(filepath, "r", encoding="utf-8") as src:
            content = src.read()
        atomic_write(backup_path, content)
        logging.debug(f"backup_before_write: backed up {filepath} → {backup_path}")
        reset_backup_failure_count(filepath)
    except Exception as e:
        logging.warning(f"BACKUP_WARN: Failed to backup {filepath} → {backup_path}: {e}")
        _record_backup_failure(filepath)
        return  # Non-fatal — write proceeds regardless

    # Prune old backups for this file only
    cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 86400)
    for old_backup in glob.glob(os.path.join(backup_dir, f"{basename}.*.bak")):
        try:
            if os.path.getmtime(old_backup) < cutoff:
                os.remove(old_backup)
                logging.debug(f"backup_before_write: pruned {old_backup}")
        except Exception:
            pass  # Non-fatal


def _record_backup_failure(filepath):
    """Track consecutive backup failures. Alert at ERROR level after 3."""
    _backup_failure_counts[filepath] = _backup_failure_counts.get(filepath, 0) + 1
    if _backup_failure_counts[filepath] >= 3:
        logging.error(
            f"BACKUP_ALERT: {_backup_failure_counts[filepath]} consecutive backup failures "
            f"for {filepath}. Disk may be full or backup directory unwritable. Alert Chris."
        )


def reset_backup_failure_count(filepath):
    """Reset consecutive-failure counter after a successful backup."""
    _backup_failure_counts.pop(filepath, None)


def startup_cleanup_tmp(directories):
    """
    On startup: scan directories for orphaned .tmp files and delete them.

    Orphaned .tmp files represent interrupted atomic writes (crash mid-write).
    The target file is always intact when this happens — .tmp files are safe to delete.

    Logs at DEBUG level only. These are expected after ungraceful shutdowns
    and should not generate noise in normal operation.
    """
    for directory in directories:
        for tmp_file in glob.glob(os.path.join(directory, "*.tmp")):
            try:
                os.remove(tmp_file)
                logging.debug(f"startup_cleanup_tmp: removed orphaned {tmp_file}")
            except OSError as e:
                logging.debug(f"startup_cleanup_tmp: could not remove {tmp_file}: {e}")
