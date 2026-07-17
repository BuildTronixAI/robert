"""Memory tools for Robert - reading and writing to memory files."""

import os
import sys
from pathlib import Path
from config import WORKSPACE_PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import atomic_write  # RR-0013: atomic write for all memory files


MEMORY_DIR = os.path.join(WORKSPACE_PATH, "memory")


def read_memory(filename: str) -> str:
    """Read content from a memory file."""
    filepath = os.path.join(MEMORY_DIR, filename)
    
    if not os.path.exists(filepath):
        return ""
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"Failed to read memory file {filename}: {str(e)}")


def write_memory(filename: str, content: str) -> bool:
    """Write content to a memory file atomically (RR-0013)."""
    try:
        Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
        filepath = os.path.join(MEMORY_DIR, filename)
        atomic_write(filepath, content)  # RR-0013: atomic write prevents partial-write corruption
        return True
    except Exception as e:
        raise IOError(f"Failed to write memory file {filename}: {str(e)}")


def append_memory(filename: str, content: str) -> bool:
    """Append content to a memory file."""
    try:
        Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
        filepath = os.path.join(MEMORY_DIR, filename)
        
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        raise IOError(f"Failed to append to memory file {filename}: {str(e)}")
