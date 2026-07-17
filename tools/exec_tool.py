"""Execution tool for Robert — constrained subprocess runner.

Hardening:
- Prefer argv lists (no shell) for generated code paths
- Optional workspace cwd confinement
- Credential scrubbing on stdout/stderr
- Process-group kill on timeout
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from config import COMMAND_TIMEOUT, WORKSPACE_PATH

try:
    from tools.base import sanitize_error
except Exception:  # pragma: no cover - fallback if base unavailable
    def sanitize_error(text: str) -> str:
        return text


Cmd = Union[str, Sequence[str]]


def _scrub(text: str) -> str:
    if not text:
        return ""
    try:
        return sanitize_error(text)
    except Exception:
        return text


def run_command(
    cmd: Cmd,
    timeout: Optional[int] = None,
    *,
    cwd: Optional[str] = None,
    shell: Optional[bool] = None,
    env: Optional[dict] = None,
) -> Dict:
    """
    Execute a command and return stdout, stderr, and return code.

    Prefer passing an argv list. String commands with shell=True are allowed
    only for legacy callers; coder paths should use argv.
    """
    if timeout is None:
        timeout = COMMAND_TIMEOUT

    use_shell = shell if shell is not None else isinstance(cmd, str)
    workdir = cwd or WORKSPACE_PATH
    try:
        Path(workdir).mkdir(parents=True, exist_ok=True)
    except OSError:
        workdir = None

    # Prevent runaway env inheritance of secrets into child when not needed —
    # still inherit by default so python/path work; callers may pass env=.
    child_env = env if env is not None else os.environ.copy()

    try:
        result = subprocess.run(
            cmd,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            env=child_env,
            start_new_session=True,
        )
        return {
            "stdout": _scrub(result.stdout),
            "stderr": _scrub(result.stderr),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired as e:
        # Best-effort kill of the process group started via start_new_session.
        if e.process is not None:
            try:
                os.killpg(e.process.pid, signal.SIGKILL)
            except Exception:
                pass
        return {
            "stdout": _scrub(e.stdout or "") if isinstance(e.stdout, str) else "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": _scrub(str(e)),
            "returncode": -1,
        }


def run_argv(argv: List[str], timeout: Optional[int] = None, cwd: Optional[str] = None) -> Dict:
    """Execute an argv list with shell disabled."""
    return run_command(argv, timeout=timeout, cwd=cwd, shell=False)
