"""R0 runtime fixes: dirty-noise filter, JWT precondition, listener lock."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_runtime_lock_files_do_not_count_as_dirty():
    from startup_preconditions import _is_runtime_noise, _porcelain_path

    assert _porcelain_path("?? robert_memory.json.lock") == "robert_memory.json.lock"
    assert _is_runtime_noise("robert_memory.json.lock")
    assert _is_runtime_noise("robert_listener.lock")
    assert _is_runtime_noise("foo/bar.lock")
    assert not _is_runtime_noise("listener.py")
    assert not _is_runtime_noise("nodes/executor.py")


def test_check_git_dirty_filters_locks(tmp_path, monkeypatch):
    from startup_preconditions import _check_git_dirty

    class _Result:
        returncode = 0
        stdout = "?? robert_memory.json.lock\n?? robert_listener.lock\n M listener.py\n"

    with patch("startup_preconditions.subprocess.run", return_value=_Result()):
        dirty, files = _check_git_dirty(str(tmp_path))
    assert dirty is True
    assert any("listener.py" in f for f in files)
    assert not any(".lock" in f for f in files)


def test_check_git_dirty_locks_only_is_clean(tmp_path):
    from startup_preconditions import _check_git_dirty

    class _Result:
        returncode = 0
        stdout = "?? robert_memory.json.lock\n?? .chat_history_reset_done\n"

    with patch("startup_preconditions.subprocess.run", return_value=_Result()):
        dirty, files = _check_git_dirty(str(tmp_path))
    assert dirty is False
    assert files == []


def test_jwt_missing_marks_degraded(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv("ROBERT_AUDITED_WRITES_ENABLED", "false")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test")

    from startup_preconditions import check_startup_preconditions

    with patch("startup_preconditions._check_git_dirty", return_value=(False, [])):
        with patch("startup_preconditions._notify_chris_degraded"):
            state = check_startup_preconditions()
    assert state.degraded is True
    assert "SUPABASE_JWT_SECRET" in (state.degraded_reason or "")


def test_jwt_present_with_clean_tree_not_degraded_for_jwt(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("ROBERT_AUDITED_WRITES_ENABLED", "false")

    from startup_preconditions import check_startup_preconditions

    with patch("startup_preconditions._check_git_dirty", return_value=(False, [])):
        with patch("startup_preconditions._notify_chris_degraded"):
            state = check_startup_preconditions()
    assert "SUPABASE_JWT_SECRET" not in (state.degraded_reason or "")


def test_listener_lock_blocks_second_instance(tmp_path, monkeypatch):
    import listener as lis

    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    lis._LISTENER_LOCK_FD = None
    lis.acquire_listener_lock()
    try:
        raised = False
        try:
            # Second acquire in same process would also fail on LOCK_NB against same path
            # Use a fresh module-level path by opening manually
            import fcntl
            fd = os.open(str(tmp_path / "robert_listener.lock"), os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                raised = False
            except BlockingIOError:
                raised = True
            finally:
                os.close(fd)
        finally:
            pass
        assert raised is True
    finally:
        if lis._LISTENER_LOCK_FD is not None:
            fcntl.flock(lis._LISTENER_LOCK_FD, fcntl.LOCK_UN)
            os.close(lis._LISTENER_LOCK_FD)
            lis._LISTENER_LOCK_FD = None
