# Design: Robert 

Build a Python log parser tool at /root/.openclaw/workspace/scripts/log_parser.py that: scans /root/.openclaw/workspace logs and system journal for ERROR and FATAL events, extracts 20 lines of context around each event, deduplicates repeated errors, formats a clean digest, and sends it to the Buildtronix Board Telegram group via the Robert bot. Set it up as a daily cron at 08:00 UTC. Server is Ubuntu, systemd services: robert, scout, openclaw gateway. Log files in /root/.openclaw/workspace/. Telegram group: -5288262569.

Generated: 2026-04-25T06:46:24.407632

# Design Document: Log Parser & Daily Digest Tool

---

## Problem Restatement

Build a Python script at `/root/.openclaw/workspace/scripts/log_parser.py` that:

1. Scans log files under `/root/.openclaw/workspace/` for `ERROR` and `FATAL` severity events
2. Scans the systemd journal for the three named services (`robert`, `scout`, `openclaw gateway`) for the same severity events
3. Extracts ±10 lines of context around each matching event (20 lines total)
4. Deduplicates repeated/similar errors so the digest is not noisy
5. Formats a clean, readable digest message
6. Delivers the digest to Telegram group `-5288262569` via the Robert bot
7. Runs automatically via cron at 08:00 UTC daily on Ubuntu

The tool must be self-contained, robust to missing logs, and produce actionable output even when nothing is wrong (sends a "clean" summary).

---

## Success Criteria

| # | Criterion | Verification Method |
|---|-----------|-------------------|
| 1 | Script runs without error on a clean system | `python3 log_parser.py --dry-run` exits 0 |
| 2 | Correctly identifies ERROR/FATAL lines in log files | Unit test with fixture log files |
| 3 | Correctly pulls journal entries for all 3 services | `journalctl` output parsed, verified against known injected errors |
| 4 | Context window is exactly ±10 lines per event | Inspect output with known fixture |
| 5 | Duplicate errors collapsed to one entry with count | Two identical errors → one entry showing `(×N)` |
| 6 | Telegram message delivered to group `-5288262569` | Message appears in group; HTTP 200 from Bot API |
| 7 | Cron fires at 08:00 UTC daily | `crontab -l` shows entry; verify with `systemd-cron` or manual trigger |
| 8 | Handles zero errors gracefully | "✅ No errors found" message sent |
| 9 | Script handles permission errors, missing files without crashing | Tested with unreadable log file |
| 10 | Telegram token loaded from env/config, not hardcoded | Code review + grep for token literal |

---

## Proposed Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    log_parser.py                        │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │  FileScanner │    │JournalScanner│                  │
│  │  (glob logs) │    │(journalctl)  │                  │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                           │
│         └─────────┬─────────┘                           │
│                   ▼                                     │
│           ┌───────────────┐                             │
│           │  EventExtract │  (regex match + context)   │
│           └───────┬───────┘                             │
│                   ▼                                     │
│           ┌───────────────┐                             │
│           │  Deduplicator │  (normalize + hash)        │
│           └───────┬───────┘                             │
│                   ▼                                     │
│           ┌───────────────┐                             │
│           │DigestFormatter│  (Markdown/plain text)     │
│           └───────┬───────┘                             │
│                   ▼                                     │
│           ┌───────────────┐                             │
│           │TelegramSender │  (requests + retry)        │
│           └───────────────┘                             │
└─────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**FileScanner**
- Recursively globs `*.log`, `*.txt`, `*.out` under `/root/.openclaw/workspace/`
- Reads files line-by-line (handles large files without loading into RAM)
- Skips unreadable files with a warning logged to stderr

**JournalScanner**
- Invokes `journalctl` via subprocess for each service:
  ```
  journalctl -u robert -u scout -u "openclaw gateway" \
    --since "yesterday 08:00" --until "today 08:00" \
    --no-pager -o short-iso
  ```
- Parses output as lines (same pipeline as FileScanner output)
- Time window: last 24 hours (since previous run)

**EventExtractor**
- Regex: `re.compile(r'\b(ERROR|FATAL)\b', re.IGNORECASE)`
- For each matching line, captures `[line_index-10 : line_index+11]` from the source line buffer
- Produces `RawEvent` objects

**Deduplicator**
- Normalizes each error message: strips timestamps, PIDs, hex addresses, UUIDs, line numbers
- Normalization regex: `re.sub(r'\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\.\d]*Z?|\d+|0x[0-9a-f]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b', 'X', msg)`
- Groups by `(source_name, normalized_message_hash)`
- Keeps the first occurrence's context; appends count if >1

**DigestFormatter**
- Produces a Telegram-safe message (≤4096 chars per message; splits if needed)
- Format: plain text with emoji markers (avoids MarkdownV2 escaping complexity)
- Sections: header, per-source error groups, footer with timestamp

**TelegramSender**
- Uses `requests` library (stdlib + requests, no heavy deps)
- Endpoint: `https://api.telegram.org/bot{TOKEN}/sendMessage`
- Retry: 3 attempts with exponential backoff (2s, 4s, 8s)
- Long messages split into chunks ≤4096 chars at newline boundaries

### Configuration

Config loaded from `/root/.openclaw/workspace/scripts/.env` or environment variables:

```
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=-5288262569
LOG_ROOT=/root/.openclaw/workspace
LOOKBACK_HOURS=24
```

---

## Key Interfaces & Data Structures

### Data Models

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class RawEvent:
    source: str          # filename or "journal:service_name"
    line_number: int     # 1-based line number of the matching line
    severity: str        # "ERROR" or "FATAL"
    match_line: str      # the exact matching line
    context_before: List[str]   # up to 10 lines before
    context_after: List[str]    # up to 10 lines after
    timestamp: Optional[datetime] = None  # parsed if available

@dataclass
class DeduplicatedEvent:
    source: str
    severity: str
    match_line: str          # first occurrence
    context_before: List[str]
    context_after: List[str]
    count: int = 1           # how many times this pattern appeared
    first_seen_line: int = 0
    normalized_key: str = ""  # the dedup hash key

@dataclass
class Digest:
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    events: List[DeduplicatedEvent]
    sources_scanned: List[str]
    sources_failed: List[str]   # files we couldn't read
    total_raw_events: int
```

### Function Signatures

```python
# --- Scanner layer ---
def scan_log_files(
    root_dir: str,
    patterns: List[str] = ["**/*.log", "**/*.txt", "**/*.out"]
) -> Iterator[Tuple[str, List[str]]]:
    """Yields (filepath, lines) for each readable log file."""

def scan_journal(
    services: List[str],
    since: datetime,
    until: datetime
) -> Iterator[Tuple[str, List[str]]]:
    """Yields (source_label, lines) from journalctl output per service."""

# --- Extraction layer ---
def extract_events(
    source: str,
    lines: List[str],
    context_window: int = 10
) -> List[RawEvent]:
    """Find all ERROR/FATAL lines and return RawEvent objects with context."""

# --- Deduplication layer ---
def normalize_message(line: str) -> str:
    """Strip volatile tokens (timestamps, PIDs, addresses) for comparison."""

def deduplicate_events(events: List[RawEvent]) -> List[DeduplicatedEvent]:
    """Group by (source_basename, normalized_hash), keep first, count rest."""

# --- Formatting layer ---
def format_digest(digest: Digest, max_chars: int = 4096) -> List[str]:
    """Return list of message chunks, each ≤ max_chars."""

# --- Delivery layer ---
def send_telegram(
    token: str,
    chat_id: str,
    messages: List[str],
    retries: int = 3
) -> bool:
    """Send each message chunk. Returns True if all succeeded."""

# --- Orchestration ---
def build_digest(config: Config) -> Digest:
    """Top-level: scan → extract → deduplicate → return Digest."""

def main() -> int:
    """Entry point. Returns exit code 0=success, 1=partial failure, 2=fatal."""
```

### Config Object

```python
@dataclass
class Config:
    telegram_token: str
    telegram_chat_id: str
    log_root: str = "/root/.openclaw/workspace"
    lookback_hours: int = 24
    context_window: int = 10
    services: List[str] = field(default_factory=lambda: ["robert", "scout", "openclaw gateway"])
    dry_run: bool = False
    log_patterns: List[str] = field(default_factory=lambda: ["**/*.log", "**/*.txt", "**/*.out"])
```

### Digest Message Format

```
🔍 Log Digest — 2025-01-15 08:00 UTC
Period: 2025-01-14 08:00 → 2025-01-15 08:00
Sources: 7 files + 3 journal units
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 ERROR × 3 — journal:robert [line 142]
  ... context line -2
  ... context line -1
→ 2025-01-15T07:23:11 ERROR Failed to connect to upstream: timeout
  ... context line +1
  ... context line +2
  (pattern repeated 3 times)

🔴 FATAL × 1 — /root/.openclaw/workspace/gateway.log [line 891]
  ...
→ FATAL Segmentation fault in handler
  ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total: 2 unique error patterns (4 raw occurrences)
⚠️ Unreadable: /root/.openclaw/workspace/locked.log
Generated: 2025-01-15 08:00:03 UTC
```

---

## Failure Modes & Mitigations

| Failure Mode | Likelihood | Mitigation |
|---|---|---|
| Log file unreadable (permissions) | Medium | `try/except PermissionError` → add to `sources_failed`, continue |
| Log file too large (>500MB) | Low | Stream line-by-line with `open()` iterator; never load full file |
| `journalctl` not available / fails | Low | `subprocess.run` with `check=False`; log warning, continue with file logs |
| Telegram API rate limit (429) | Low | Exponential backoff + respect `retry_after` header |
| Telegram message >4096 chars | Medium | Pre-split in `format_digest()` at newline boundaries |
| Bot token missing/invalid | Medium | Validate at startup; exit with clear error message before scanning |
| No errors found | Certain (daily) | Send "✅ All clear" message — never silently skip |
| Script itself crashes | Low | Wrap `main()` in top-level `try/except`; write failure to `/tmp/log_parser_crash.log` |
| Cron environment missing PATH/env | Medium | Use absolute paths everywhere; source `.env` explicitly in script |
| Duplicate runs (cron overlap) | Low | Lockfile at `/tmp/log_parser.lock` using `fcntl.flock` |
| Journal entries from before lookback window | Low | `--since` flag on `journalctl` enforces window |
| Unicode/binary garbage in logs | Medium | Open files with `errors='replace'`; skip non-decodable lines |

---

## Alternatives Considered

### 1. Use `systemd-journald` Python bindings (`systemd.journal`)
- **Pro:** Native, no subprocess overhead
- **Con:** Requires `python3-systemd` package (not always installed); adds a non-stdlib dependency; subprocess to `journalctl` is universally available and simpler
- **Decision:** Rejected in favor of `journalctl` subprocess

### 2. Use `loguru` or `structlog` for parsing
- **Pro:** Rich parsing features
- **Con:** External dependency; overkill for line-based regex scanning; adds install complexity in cron context
- **Decision:** Rejected; stdlib `re` + `open()` is sufficient

### 3. Store state in SQLite to track "already reported" errors across runs
- **Pro:** Avoids re-reporting old errors
- **Con:** Adds complexity; the `--since yesterday 08:00` journal flag and file mtime filtering already scope to the last 24h window; state DB can corrupt
- **Decision:** Rejected for v1; time-window scoping is sufficient

### 4. Use `python-telegram-bot` library
- **Pro:** Cleaner API, handles chunking
- **Con:** Heavy dependency; `requests` + direct Bot API is 20 lines and zero install friction
- **Decision:** Rejected; raw `requests` preferred

### 5. Send digest as a file attachment instead of inline message
- **Pro:** No 4096-char limit
- **Con:** Harder to read in Telegram mobile; inline text with splitting is more actionable
- **Decision:** Rejected; message splitting preferred

### 6. `logwatch` or `fail2ban` style existing tools
- **Pro:** Battle-tested
- **Con:** Not Python, not customizable to these exact services/format/Telegram delivery, not in scope
- **Decision:** Out of scope

---

## Implementation Plan

### Step 1 — Project scaffold & config loader
- Create `/root/.openclaw/workspace/scripts/log_parser.py`
- Create `/root/.openclaw/workspace/scripts/.env` template
- Implement `Config` dataclass + `load_config()` from env/file
- Implement `--dry-run` and `--help` CLI args via `argparse`
- **Verify:** `python3 log_parser.py --help` works; `load_config()` raises clear error if token missing

### Step 2 — FileScanner
- Implement `scan_log_files()` with `pathlib.Path.rglob()`
- Handle `PermissionError`, `UnicodeDecodeError`, binary files
- **Verify:** Run against workspace dir; prints list of files found; skips unreadable ones

### Step 3 — JournalScanner
- Implement `scan_journal()` using `subprocess.run(['journalctl', ...])`
- Parse `--since` / `--until` from `Config.lookback_hours`
- **Verify:** `journalctl -u robert --since "1 hour ago"` equivalent works; output is list of strings

### Step 4 — EventExtractor
- Implement `extract_events()` with regex and context window slicing
- Handle edge cases: match on first line (no before-context), match on last line (no after-context)
- **Verify:** Unit test with 50-line fixture containing ERROR at line 3 and line 48

### Step 5 — Deduplicator
- Implement `normalize_message()` with volatile-token stripping regex
- Implement `deduplicate_events()` using `dict` keyed on `(source_basename, sha256(normalized)[:16])`
- **Verify:** Two identical errors with different timestamps → one `DeduplicatedEvent` with `count=2`

### Step 6 — DigestFormatter
- Implement `format_digest()` producing the message format defined above
- Implement message splitting at ≤4096 chars on newline boundaries
- Handle zero-error case (clean digest message)
- **Verify:** `--dry-run` prints formatted output to stdout

### Step 7 — TelegramSender
- Implement `send_telegram()` with retry logic
- Test with `--dry-run` flag bypassing actual send
- **Verify:** Send a test message to the group; confirm receipt

### Step 8 — Orchestration & error handling
- Implement `build_digest()` and `main()`
- Add lockfile logic
- Add top-level crash handler writing to `/tmp/log_parser_crash.log`
- **Verify:** Full end-to-end run with real logs; message appears in Telegram group

### Step 9 — Cron installation
- Add cron entry:
  ```
  0 8 * * * /usr/bin/python3 /root/.openclaw/workspace/scripts/log_parser.py >> /var/log/log_parser_cron.log 2>&1
  ```
- Ensure cron runs as root (required for journal access and workspace read)
- **Verify:** `crontab -l` shows entry; manually trigger with `run-parts` or time-shift test

### Step 10 — Hardening & documentation
- Add `#!/usr/bin/env python3` shebang + `chmod +x`
- Add module-level docstring with usage, config, and cron setup instructions
- Verify all absolute paths used (no relative path assumptions)
- Final end-to-end test: inject a known ERROR into a test log file, run script, confirm Telegram message

---

## Confidence Score

**9 / 10**

**Rationale:**
- All components are well-scoped with clear interfaces and no ambiguous ownership
- The technology choices (stdlib + `requests`) minimize dependency risk in a cron context
- The 24-hour time window via `journalctl --since` is the correct scoping mechanism and avoids state management complexity
- The deduplication approach (normalize + hash) is proven and handles the most common noise patterns
- The one point deducted: the exact `journalctl` service name for `openclaw gateway` (with a space) needs verification — it may be `openclaw-gateway` or `openclaw_gateway` in systemd unit naming convention. This must be confirmed before Step 3 is implemented by running `systemctl list-units | grep openclaw` on the target server. If the name differs, the `services` list in `Config` must be updated accordingly.