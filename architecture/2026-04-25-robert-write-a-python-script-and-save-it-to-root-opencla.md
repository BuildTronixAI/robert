# Design: Robert 

Write a Python script and save it to /root/.openclaw/workspace/scripts/log_parser.py. The script should: scan the system journal (journalctl) for ERROR and FATAL level events from the last 24 hours, extract up to 20 lines of context around each event, deduplicate repeated identical errors, and print a clean formatted digest to stdout. No Telegram sending, no cron setup — just the script file. Confirm the file path when done.

Generated: 2026-04-25T07:53:35.653445

## Problem Restatement

Write a standalone Python script at `/root/.openclaw/workspace/scripts/log_parser.py` that:
1. Queries `journalctl` for log entries from the last 24 hours
2. Identifies entries at ERROR or FATAL severity levels
3. Extracts up to 20 lines of surrounding context for each matching event
4. Deduplicates identical repeated errors (same message text)
5. Prints a clean, human-readable digest to stdout
6. No side effects: no network calls, no cron, no file writes beyond the script itself

---

## Success Criteria

- Script exists at `/root/.openclaw/workspace/scripts/log_parser.py` and is executable
- Running `python3 /root/.openclaw/workspace/scripts/log_parser.py` produces output without crashing
- Output contains only ERROR/FATAL events from the last 24 hours
- Each unique error appears once, with up to 20 lines of context shown
- Duplicate errors are collapsed with a count indicator (e.g., `[repeated 5x]`)
- Output is clearly sectioned and readable in a terminal
- Script handles edge cases: no errors found, journalctl unavailable, permission issues

---

## Proposed Approach

### Architecture

Single-file Python 3 script. No third-party dependencies — stdlib only (`subprocess`, `json`, `textwrap`, `datetime`, `collections`, `hashlib`).

### Data Flow

```
journalctl (subprocess) 
    → raw JSON lines 
    → parse into LogEntry objects 
    → filter ERROR/FATAL 
    → fetch context window (±10 lines) per event 
    → deduplicate by message fingerprint 
    → render formatted digest to stdout
```

### Key Design Decisions

**JSON output from journalctl**: Use `journalctl -o json` to get structured fields (`PRIORITY`, `MESSAGE`, `_SYSTEMD_UNIT`, `__REALTIME_TIMESTAMP`, `SYSLOG_IDENTIFIER`). This is more reliable than regex-parsing human-readable output.

**Priority mapping**: journalctl uses syslog priority integers:
- 0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug
- We target PRIORITY ≤ 3 (err and above), which covers FATAL/CRIT/ALERT/EMERG as well as ERROR

**Context window**: journalctl supports `--output-fields` but not a native "context lines" flag like `grep -C`. Strategy: fetch all entries for the last 24 hours in a single call, keep them in an ordered list, then slice ±10 entries around each ERROR hit by index. This avoids N+1 subprocess calls.

**Deduplication key**: `hashlib.md5(MESSAGE.strip().encode()).hexdigest()` — identical message text maps to the same bucket. First occurrence is kept for display; subsequent occurrences increment a counter.

**Output format**:
```
══════════════════════════════════════════════════════
 LOG DIGEST — Last 24h  |  2024-01-15 14:32:00 UTC
 Errors found: 7 unique (23 total occurrences)
══════════════════════════════════════════════════════

[ERROR #1]  ● kernel  —  2024-01-15 13:01:44 UTC  [repeated 3x]
Unit: NetworkManager.service
────────────────────────────────────────────────────
  ... context line -2
  ... context line -1
▶ ERROR: connection refused on eth0
  ... context line +1
  ... context line +2
────────────────────────────────────────────────────
```

---

## Key Interfaces & Data Structures

### Data Models

```python
@dataclass
class LogEntry:
    timestamp: datetime          # parsed from __REALTIME_TIMESTAMP (microseconds)
    priority: int                # syslog integer 0-7
    message: str                 # MESSAGE field
    unit: str                    # _SYSTEMD_UNIT or SYSLOG_IDENTIFIER
    raw: dict                    # full JSON record for context rendering

@dataclass  
class ErrorEvent:
    entry: LogEntry              # the triggering ERROR/FATAL entry
    context_before: list[LogEntry]   # up to 10 entries before
    context_after: list[LogEntry]    # up to 10 entries after
    fingerprint: str             # md5 of stripped message
    count: int = 1               # deduplicated occurrence count
```

### Key Functions

```python
def fetch_journal_entries(hours: int = 24) -> list[LogEntry]:
    """
    Runs: journalctl --since '24 hours ago' -o json --no-pager
    Returns parsed list of LogEntry, sorted by timestamp ascending.
    Raises: RuntimeError if journalctl unavailable or returns non-zero.
    """

def is_error_level(entry: LogEntry) -> bool:
    """Returns True if priority <= 3 (err/crit/alert/emerg)."""

def extract_context(
    all_entries: list[LogEntry], 
    error_idx: int, 
    window: int = 10
) -> tuple[list[LogEntry], list[LogEntry]]:
    """
    Slices all_entries[max(0, error_idx-window) : error_idx] and
    all_entries[error_idx+1 : error_idx+window+1].
    Returns (before, after).
    """

def fingerprint(message: str) -> str:
    """md5 hex digest of message.strip().lower()"""

def deduplicate(events: list[ErrorEvent]) -> list[ErrorEvent]:
    """
    Preserves first occurrence per fingerprint.
    Accumulates count. Returns ordered list of unique ErrorEvents.
    """

def render_digest(events: list[ErrorEvent], total_count: int) -> str:
    """Formats and returns the full digest string for stdout."""

def main() -> None:
    """Entry point. Calls fetch → filter → context → dedup → render → print."""
```

### CLI Behavior

```
python3 log_parser.py [--hours N] [--window N] [--max-errors N]
```
- `--hours`: lookback window (default 24)
- `--window`: context lines each side (default 10, max 20)
- `--max-errors`: cap unique errors shown (default 50)

All optional; sensible defaults mean zero-argument invocation works.

---

## Failure Modes & Mitigations

| Failure Mode | Detection | Mitigation |
|---|---|---|
| `journalctl` not found | `FileNotFoundError` on subprocess | Catch, print clear error: "journalctl not available on this system" |
| Permission denied (no journal access) | Non-zero returncode + stderr contains "permission" | Print actionable message: "Run as root or add user to `systemd-journal` group" |
| Empty journal / no entries | Empty list returned | Print "No log entries found in last 24h" and exit 0 |
| No ERROR/FATAL events | Empty events list after filter | Print "✓ No ERROR or FATAL events in last 24h" and exit 0 |
| Malformed JSON line | `json.JSONDecodeError` | Skip line, increment a `skipped_lines` counter, report at end |
| Missing MESSAGE field | KeyError | Use empty string; still fingerprint and show context |
| Very large journal (millions of lines) | Memory pressure | Stream JSON line-by-line rather than loading all at once; use `iter(process.stdout)` |
| journalctl hangs | Subprocess blocks | Set `timeout=120` on subprocess call |
| Duplicate context overlap | Two errors close together share context lines | Render as-is; overlap is acceptable and informative |

---

## Alternatives Considered

### 1. Parse `/var/log/syslog` or `/var/log/messages` directly
**Rejected**: Not universal. systemd-based systems may not write these files. journalctl is the canonical interface. Format varies by distro.

### 2. Use `journalctl -o json-pretty`
**Rejected**: Multi-line JSON per entry breaks line-by-line streaming. `json` (one JSON object per line) is simpler to stream.

### 3. Use `journalctl -p err` to pre-filter, then separate calls for context
**Rejected**: Requires N subprocess calls (one per error event) to fetch context. Fetching all entries once and slicing in Python is O(1) subprocess calls and simpler.

### 4. Regex on human-readable `journalctl` output
**Rejected**: Brittle. Field extraction (unit name, timestamp, priority) requires fragile regex. JSON gives us structured data for free.

### 5. Use `systemd.journal` Python bindings (`python3-systemd`)
**Rejected**: Not always installed. Adds a dependency. subprocess + JSON achieves the same result with zero deps.

### 6. Dedup by (unit, message) composite key
**Considered**: More granular than message-only. Rejected in favor of message-only because the same error from the same service restarting would have different units if the unit name includes an instance ID. Message-only dedup is more aggressive and produces a cleaner digest.

---

## Implementation Plan

### Step 1 — Directory and file scaffolding
Create `/root/.openclaw/workspace/scripts/` if it doesn't exist. Create `log_parser.py` with shebang, module docstring, and imports. Verify file exists.

### Step 2 — `fetch_journal_entries()`
Implement subprocess call to `journalctl --since "24 hours ago" -o json --no-pager -q`. Stream stdout line by line, parse JSON, construct `LogEntry` objects. Handle all error cases. Unit-testable by mocking subprocess output.

### Step 3 — `is_error_level()` + priority constants
Define `PRIORITY_LABELS = {0:'EMERG',1:'ALERT',2:'CRIT',3:'ERROR',4:'WARNING',...}`. Implement filter. Verify with test cases: priority=3 → True, priority=4 → False.

### Step 4 — `extract_context()`
Implement index-based slicing. Verify boundary conditions: error at index 0 (no before), error at last index (no after), window larger than available entries.

### Step 5 — `fingerprint()` + `deduplicate()`
Implement md5 fingerprinting. Implement dedup loop preserving insertion order. Verify: 5 identical messages → 1 event with count=5.

### Step 6 — `render_digest()`
Implement formatted output. Header with timestamp and counts. Per-event block with priority label, unit, timestamp, repeat count, context lines with `▶` marker on the error line. Footer separator.

### Step 7 — `main()` + `argparse`
Wire everything together. Add `--hours`, `--window`, `--max-errors` args. Add `if __name__ == '__main__': main()`.

### Step 8 — End-to-end test
Run the script on the target system. Verify output format. Test with `--hours 1` to exercise the no-errors path if the system is clean.

### Step 9 — Confirm file path
Print confirmation of file location.

---

## Confidence Score

**9/10**

**Rationale**: The design is complete, dependency-free, handles all specified requirements, and anticipates realistic failure modes. The single-fetch-then-slice approach is efficient and correct. The JSON output format from journalctl is stable and well-documented. 

The one point deducted: on systems with extremely high log volume (>500k entries/24h), memory usage could be significant even with line-by-line streaming into a list. A production hardening step would add a `--max-entries` guard or use a sliding window buffer — but for the stated use case (a diagnostic script run on demand), this is acceptable and not worth complicating the design.