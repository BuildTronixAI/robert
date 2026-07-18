"""ROBERT_RESET_CHAT_HISTORY is stamp-consumed (one-shot), not every restart."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def apply_reset(flag: str, stamp: Path, clear_fn) -> str:
    """Mirror listener.run() stamp semantics. Returns action: cleared|skipped|disarmed|noop."""
    flag_l = flag.strip().lower()
    if flag_l in ("0", "false", "no", "off", ""):
        if stamp.exists():
            stamp.unlink()
            return "disarmed"
        return "noop"
    if flag_l in ("1", "true", "yes", "on", "force"):
        if flag_l == "force" or not stamp.exists():
            clear_fn()
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text("done\n", encoding="utf-8")
            return "cleared"
        return "skipped"
    return "noop"


def test_one_shot_then_skip(tmp_path):
    stamp = tmp_path / ".chat_history_reset_done"
    calls = {"n": 0}

    def clear_fn():
        calls["n"] += 1

    assert apply_reset("1", stamp, clear_fn) == "cleared"
    assert calls["n"] == 1
    assert stamp.exists()

    assert apply_reset("1", stamp, clear_fn) == "skipped"
    assert calls["n"] == 1  # not cleared again

    assert apply_reset("force", stamp, clear_fn) == "cleared"
    assert calls["n"] == 2


def test_removing_flag_disarms_for_next_intentional_reset(tmp_path):
    stamp = tmp_path / ".chat_history_reset_done"
    calls = {"n": 0}

    def clear_fn():
        calls["n"] += 1

    apply_reset("1", stamp, clear_fn)
    assert apply_reset("0", stamp, clear_fn) == "disarmed"
    assert not stamp.exists()
    assert apply_reset("1", stamp, clear_fn) == "cleared"
    assert calls["n"] == 2
