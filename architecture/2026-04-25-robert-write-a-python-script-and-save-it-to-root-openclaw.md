# Design: Robert

Write a Python script and save it to /root/.openclaw/workspace/scripts/log_parser.py. The script should: scan the system journal (journalctl) for ERROR and FATAL level events from the last 24 hours, extract up to 20 lines of context around each event, deduplicate repeated identical errors, and print a clean formatted digest to stdout. No Telegram sending, no cron setup — just the script file. Confirm the file path when done.

Generated: 2026-04-25T08:20:26.472843

## Problem Restatement

Write a standalone Python script at `/root/.openclaw/workspace/scripts/log_parser.py` that:
1. Queries `journalctl` for log entries from the last 24 hours
2. Identifies entries at ERROR or FATAL severity levels
3. Extracts up to 20 lines of surrounding context for each matching event
4. Deduplicates repeated identical error messages
5. Prints a clean, human-readable digest to stdout
6. Does nothing else (no network calls, no cron, no side effects)

---

## Success Criteria

- Script exists at `/root/.openclaw/workspace/scripts/log_parser.py` and is executable
- Running `python3 log_parser.py` produces output without crashing on a standard Linux system with systemd
- ERROR and FATAL level events from the last 24 hours are captured (journalctl priority levels 3=err, 2=crit, 1=alert, 0=emerg — we include ≤3; FATAL maps to priority 2 or lower in most implementations)
- Each unique error appears once in the digest regardless of repetition count; suppressed duplicates are noted with a count
- Context window: up to 20 lines before+after each event (capped by available log data)
- Output is clearly formatted: timestamp, unit/service, message, context block, dedup count if >1
- Graceful degradation if journalctl is unavailable or returns no results

---

## Proposed Approach

### Architecture

Single-file Python 3 script. No third-party dependencies — stdlib only (`subprocess`, `json`, `collections`, `datetime`, `textwrap`, `sys`).

### Data Flow

```
journalctl (subprocess) 
    → JSON lines output 
    → parse into structured LogEntry objects 
    → collect all entries into ordered list 
    → identify ERROR/FATAL entries (priority ≤ 3) 
    → for each match, slice context window from full entry list 
    → deduplicate by normalized message fingerprint 
    → render formatted digest to stdout
```

### Why JSON output from journalctl

`journalctl -o json` gives us structured fields (`PRIORITY`, `MESSAGE`, `_SYSTEMD_UNIT`, `__REALTIME_TIMESTAMP`, `SYSLOG_IDENTIFIER`) without fragile regex parsing of human-readable log lines. Reliable and machine-stable.

### Context Window Strategy

- Fetch **all** entries for the last 24 hours in one call (not just errors), preserving sequence
- Build an index: `{entry_index: LogEntry}`
- For each error entry at index `i`, slice `[max(0, i-20) : i+21]` from the full list
- This gives true surrounding context (mix of INFO, DEBUG, ERROR lines around the error)

### Deduplication

- Fingerprint = normalized MESSAGE string: strip timestamps, hex addresses, PIDs, line numbers using regex substitution, then hash with MD5
- Group error entries by fingerprint
- For each group, keep the **first occurrence** as the representative; record total count
- Display count badge if count > 1: `[repeated ×N]`

### Output Format

```
══════════════════════════════════════════════════════
LOG DIGEST — Last 24 Hours  |  2024-01-15 14:32:00 UTC
Errors found: 7  |  Unique: 4
══════════════════════════════════════════════════════

[1/4] ── ERROR ── 2024-01-15 13:45:22 UTC  [repeated ×3]
Service : nginx.service
Message : connect() failed (111: Connection refused)
─────────────────────────── context ───────────────────────────
  [13:45:20] nginx: worker process started
  [13:45:21] nginx: accepting connections
▶ [13:45:22] nginx: connect() failed (111: Connection refused)
  [13:45:22] nginx: upstream timed out
─────────────────────────────────────────────────────────────
```

---

## Key Interfaces & Data Structures

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class LogEntry:
    index: int                    # position in full 24h log sequence
    timestamp: datetime           # parsed from __REALTIME_TIMESTAMP (microseconds)
    priority: int                 # 0-7 (syslog levels)
    message: str                  # MESSAGE field
    unit: str                     # _SYSTEMD_UNIT or SYSLOG_IDENTIFIER
    raw: dict                     # full JSON record for reference

@dataclass
class ErrorGroup:
    fingerprint: str              # MD5 of normalized message
    representative: LogEntry      # first occurrence
    count: int                    # total occurrences
    context: List[LogEntry]       # up to 20 lines before+after representative
```

```python
# Core function signatures

def fetch_journal_entries(hours: int = 24) -> List[dict]:
    """Run journalctl, return list of raw JSON dicts. Raises RuntimeError if unavailable."""

def parse_entry(raw: dict, index: int) -> Optional[LogEntry]:
    """Parse a raw JSON dict into LogEntry. Returns None if malformed."""

def is_error(entry: LogEntry) -> bool:
    """True if priority <= 3 (ERROR, CRIT, ALERT, EMERG) or message contains FATAL."""

def normalize_message(msg: str) -> str:
    """Strip volatile tokens (PIDs, addresses, timestamps) for fingerprinting."""

def fingerprint(msg: str) -> str:
    """MD5 hex digest of normalize_message(msg)."""

def extract_context(entry: LogEntry, all_entries: List[LogEntry], window: int = 20) -> List[LogEntry]:
    """Return up to window entries before and after entry in all_entries."""

def deduplicate(error_entries: List[LogEntry], all_entries: List[LogEntry]) -> List[ErrorGroup]:
    """Group errors by fingerprint, return one ErrorGroup per unique error."""

def format_digest(groups: List[ErrorGroup], total_errors: int) -> str:
    """Render the full digest string."""

def main() -> None:
    """Entry point. Exits with code 0 on success, 1 on fatal error."""
```

---

## Failure Modes & Mitigations

| Failure | Mitigation |
|---|---|
| `journalctl` not found / not systemd system | Catch `FileNotFoundError`, print clear message, exit 1 |
| `journalctl` returns non-zero exit code | Capture stderr, print it, exit 1 |
| Malformed JSON line from journalctl | Skip line, increment `parse_errors` counter, report at end |
| `MESSAGE` field is binary/bytes | Decode with `errors='replace'`, strip non-printable chars |
| Zero errors found | Print "No ERROR/FATAL events found in last 24 hours." and exit 0 |
| Extremely large log volume (millions of lines) | `journalctl --since` already limits to 24h; add `--lines=50000` safety cap with warning |
| Missing fields in JSON record | Default to `"unknown"` for unit, skip entry if no MESSAGE |
| Context window overlaps between adjacent errors | Allowed — context is per-error, not deduplicated across errors |
| Running as non-root (limited journal access) | Script works with user journal; note in output if `_SYSTEMD_UNIT` is sparse |

---

## Alternatives Considered

### 1. Parse `/var/log/syslog` or `/var/log/messages` directly
- **Rejected**: Not universally present on systemd systems; format varies by distro; no structured fields; journalctl is the canonical interface.

### 2. `journalctl -o short` with regex parsing
- **Rejected**: Fragile. Human-readable format has no stable schema. JSON output is purpose-built for programmatic consumption.

### 3. Use `systemd.journal` Python bindings (`python3-systemd`)
- **Rejected**: Not available in stdlib; requires package installation; adds deployment friction. `subprocess` + JSON is sufficient and dependency-free.

### 4. Stream journalctl line-by-line (avoid loading all entries into memory)
- **Considered**: Better for huge logs. Rejected for simplicity — 24h of logs is typically <100MB; loading into memory is fine. The `--lines=50000` cap provides safety.

### 5. Deduplicate by exact message string
- **Rejected**: Identical errors with different PIDs/timestamps would not be grouped. Normalization is necessary for useful deduplication.

---

## Implementation Plan

**Step 1**: Create directory and file skeleton
- `mkdir -p /root/.openclaw/workspace/scripts/`
- Create `log_parser.py` with shebang, imports, and `main()` stub
- Verify: file exists, `python3 log_parser.py --help` doesn't crash

**Step 2**: Implement `fetch_journal_entries()`
- `subprocess.run(['journalctl', '--since', '24 hours ago', '-o', 'json', '--no-pager', '--lines=50000'], capture_output=True)`
- Parse stdout line-by-line as JSON
- Verify: returns list of dicts on a live system

**Step 3**: Implement `parse_entry()` and `LogEntry` dataclass
- Handle `__REALTIME_TIMESTAMP` (microseconds since epoch → datetime)
- Handle missing/binary MESSAGE fields
- Verify: all entries parse without exception on sample data

**Step 4**: Implement `is_error()` filter
- Priority ≤ 3 OR message contains case-insensitive "FATAL"
- Verify: correctly identifies test entries at various priority levels

**Step 5**: Implement `normalize_message()` and `fingerprint()`
- Regex strip: `\b\d+\b` (standalone numbers), `0x[0-9a-f]+` (hex), `\d{4}-\d{2}-\d{2}` (dates)
- Verify: two messages differing only by PID produce same fingerprint

**Step 6**: Implement `extract_context()` and `deduplicate()`
- Use `entry.index` for O(1) slicing
- Verify: context window correctly bounded at list edges

**Step 7**: Implement `format_digest()`
- Header, per-group blocks with context, footer summary
- Verify: output is readable, arrow marks the error line in context

**Step 8**: Wire `main()`, add error handling, test end-to-end
- Test: no errors found, journalctl unavailable, normal operation
- Verify: exit codes correct, output matches spec

**Step 9**: Set file permissions, confirm path
- `chmod +x /root/.openclaw/workspace/scripts/log_parser.py`
- Print confirmed path

---

## Confidence Score

**9/10**

The design is complete, dependency-free, handles all specified requirements, and accounts for realistic failure modes. The one point deducted: on systems with very high log volume or unusual journald configurations (e.g., rate-limiting, remote journals), the `--lines=50000` cap may silently truncate context — this is a known, documented tradeoff rather than a design flaw. The JSON output mode from journalctl is stable across systemd versions ≥ 209 (2013), so compatibility risk is negligible.