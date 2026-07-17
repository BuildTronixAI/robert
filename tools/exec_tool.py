"""Execution tool for Robert - running shell commands."""

import subprocess
from typing import Dict
from config import COMMAND_TIMEOUT


def run_command(cmd: str, timeout: int = None) -> Dict:
    """
    Execute a shell command and return stdout, stderr, and return code.
    
    Args:
        cmd: Shell command to execute
        timeout: Timeout in seconds (default from config)
    
    Returns:
        Dictionary with keys: stdout, stderr, returncode
    """
    if timeout is None:
        timeout = COMMAND_TIMEOUT
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }
