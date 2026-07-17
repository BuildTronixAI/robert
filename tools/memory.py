"""Memory tools for Robert - reading and writing to memory files."""

import os
import sys
from pathlib import Path
from config import WORKSPACE_PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import atomic_write  # RR-0013: atomic write for all memory files


MEMORY_DIR = os.path.join(WORKSPACE_PATH, "memory")


def _resolve_memory_path(filename: str) -> Path:
    """
    Resolve a memory filename strictly inside MEMORY_DIR.
    Rejects absolute paths, .. traversal, and symlink escapes.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Memory filename must be a non-empty string")
    if filename.startswith("/") or filename.startswith("\\") or ":" in filename[:3]:
        raise ValueError(f"Absolute memory paths are not allowed: {filename!r}")

    base = Path(MEMORY_DIR).resolve()
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError(f"Memory path escapes MEMORY_DIR: {filename!r}") from e
    return candidate


def read_memory(filename: str) -> str:
    """Read content from a memory file."""
    filepath = _resolve_memory_path(filename)

    if not filepath.exists():
        return ""

    try:
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        raise IOError(f"Failed to read memory file {filename}: {str(e)}")


def write_memory(filename: str, content: str) -> bool:
    """Write content to a memory file atomically (RR-0013)."""
    try:
        Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
        filepath = _resolve_memory_path(filename)
        atomic_write(str(filepath), content)
        return True
    except Exception as e:
        raise IOError(f"Failed to write memory file {filename}: {str(e)}")


def append_memory(filename: str, content: str) -> bool:
    """Append content to a memory file via read-modify-atomic-write."""
    try:
        Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
        filepath = _resolve_memory_path(filename)
        existing = ""
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
        atomic_write(str(filepath), existing + content)
        return True
    except Exception as e:
        raise IOError(f"Failed to append to memory file {filename}: {str(e)}")
