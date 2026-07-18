#!/usr/bin/env bash
# Consolidated post-deploy verification for Robert gateway fix (PR #4).
# Exit nonzero on any failure — gate live T1–T6 acceptance.
#
# Host sequence:
#   sudo bash deploy/verify_deploy.sh --phase pre          # BEFORE restart — key must be ***SET***
#   # set ROBERT_RESET_CHAT_HISTORY=1 ; systemctl restart robert
#   sudo bash deploy/verify_deploy.sh --phase post-reset   # after first restart
#   # remove flag ; systemctl restart robert
#   sudo bash deploy/verify_deploy.sh --phase final        # after second restart — gate T1–T6
#
# Aliases: pre=smoke | post-reset=first | final=second | full≈final
#
# Critical: "Cleared conversation_history" must appear EXACTLY ONCE across both
# restarts. A second clear line = stamp not honored = FAIL.
#
# Env overrides:
#   ROBERT_UNIT=robert
#   ROBERT_WORKSPACE=/var/lib/robert/workspace
#   EXPECTED_SHA=0957da5
#   JOURNAL_LINES=200
#   JOURNAL_SINCE=     # optional: journalctl --since (e.g. "10 min ago")
set -euo pipefail

UNIT="${ROBERT_UNIT:-robert}"
WORKSPACE="${ROBERT_WORKSPACE:-/var/lib/robert/workspace}"
STAMP="${ROBERT_CHAT_HISTORY_RESET_STAMP:-$WORKSPACE/.chat_history_reset_done}"
JOURNAL_LINES="${JOURNAL_LINES:-200}"
EXPECTED_SHA="${EXPECTED_SHA:-0957da5}"
JOURNAL_SINCE="${JOURNAL_SINCE:-}"
PHASE="final"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) PHASE="${2:-}"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --workspace) WORKSPACE="${2:-}"; STAMP="$WORKSPACE/.chat_history_reset_done"; shift 2 ;;
    --unit) UNIT="${2:-}"; shift 2 ;;
    --since) JOURNAL_SINCE="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

# Normalize phase aliases
case "$PHASE" in
  pre|smoke) PHASE="pre" ;;
  post-reset|first|post_reset) PHASE="post-reset" ;;
  final|second|full) PHASE="final" ;;
  *)
    echo "Unknown phase '$PHASE' (use: pre | post-reset | final)" >&2
    exit 2
    ;;
esac

PASS=0
FAIL=0
WARN=0

pass() { echo "PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $1"; FAIL=$((FAIL + 1)); }
warn() { echo "WARN  $1"; WARN=$((WARN + 1)); }

mask_set() {
  # Print KEY=***SET*** or KEY=***MISSING*** — never the value
  local key="$1" val="$2"
  if [[ -n "$val" ]]; then
    echo "${key}=***SET***"
  else
    echo "${key}=***MISSING***"
  fi
}

echo "=== Robert deploy verify ==="
echo "unit=$UNIT workspace=$WORKSPACE phase=$PHASE expected_sha=$EXPECTED_SHA"
echo

# ── (a) ANTHROPIC_API_KEY in running unit env (masked) ──────────────────────
check_api_key() {
  local val="" or_val="" environ=""
  if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    local pid
    pid="$(systemctl show -p MainPID --value "$UNIT" 2>/dev/null || echo 0)"
    if [[ -n "$pid" && "$pid" != "0" && -r "/proc/${pid}/environ" ]]; then
      environ="/proc/${pid}/environ"
      val="$(tr '\0' '\n' < "$environ" | awk -F= '$1=="ANTHROPIC_API_KEY"{print substr($0,index($0,"=")+1); exit}')"
      or_val="$(tr '\0' '\n' < "$environ" | awk -F= '$1=="OPENROUTER_API_KEY"{print substr($0,index($0,"=")+1); exit}')"
    else
      fail "ANTHROPIC_API_KEY: unit active but MainPID/environ unreadable (need root?)"
      mask_set "ANTHROPIC_API_KEY" ""
      return
    fi
  else
    # --phase pre must abort if we cannot prove the key will be loaded
    local envf="${ROBERT_SECRETS_ENV:-/etc/robert/secrets.env}"
    if [[ -r "$envf" ]]; then
      warn "unit '$UNIT' not active — checking $envf (masked) for pre-flight"
      val="$(awk -F= '$1=="ANTHROPIC_API_KEY"{print substr($0,index($0,"=")+1); exit}' "$envf" | tr -d '\r')"
      or_val="$(awk -F= '$1=="OPENROUTER_API_KEY"{print substr($0,index($0,"=")+1); exit}' "$envf" | tr -d '\r')"
    else
      fail "systemd unit '$UNIT' is not active and $envf unreadable — abort before restart"
      mask_set "ANTHROPIC_API_KEY" ""
      return
    fi
  fi
  mask_set "ANTHROPIC_API_KEY" "$val"
  if [[ -n "$val" ]]; then
    pass "ANTHROPIC_API_KEY present (masked) — safe to proceed"
  else
    mask_set "OPENROUTER_API_KEY" "$or_val"
    fail "ANTHROPIC_API_KEY=***MISSING*** — ABORT restart (auth trap)"
  fi
}

# ── (b) git HEAD == expected (or current main) ──────────────────────────────
check_git_head() {
  if [[ ! -d "$WORKSPACE/.git" ]]; then
    fail "git HEAD: $WORKSPACE is not a git checkout"
    return
  fi
  local head short
  head="$(git -C "$WORKSPACE" rev-parse HEAD 2>/dev/null || true)"
  short="$(git -C "$WORKSPACE" rev-parse --short=7 HEAD 2>/dev/null || true)"
  echo "git HEAD=$head (short=$short)"

  local want="$EXPECTED_SHA"
  # If origin/main is reachable and EXPECTED_SHA looks like the known merge, allow main tip
  if git -C "$WORKSPACE" rev-parse --verify origin/main >/dev/null 2>&1; then
    local main_sha
    main_sha="$(git -C "$WORKSPACE" rev-parse origin/main)"
    echo "origin/main=$main_sha"
    # Accept exact expected OR current origin/main (forward-compatible)
    if [[ "$head" == "$main_sha"* || "$main_sha" == "$head"* || "$head" == "$main_sha" ]]; then
      if [[ "$head" == "$main_sha" ]]; then
        pass "git HEAD matches origin/main ($short)"
        return
      fi
    fi
  fi

  if [[ "$head" == "$want"* || "$short" == "$want"* || "$head" == "$want" ]]; then
    pass "git HEAD matches expected $want ($short)"
  else
    # Also accept if expected is a prefix of HEAD (full vs short)
    if [[ "$want" == "$short"* || "$short" == "$want"* ]]; then
      pass "git HEAD matches expected $want ($short)"
    else
      fail "git HEAD $short does not match expected $want (pull main / 0957da5)"
    fi
  fi
}

# ── (c) journal greps ───────────────────────────────────────────────────────
journal_blob() {
  local args=(-u "$UNIT" -n "$JOURNAL_LINES" --no-pager)
  if [[ -n "$JOURNAL_SINCE" ]]; then
    args=(--since "$JOURNAL_SINCE" -u "$UNIT" --no-pager)
  fi
  journalctl "${args[@]}" 2>/dev/null \
    || journalctl -n "$JOURNAL_LINES" --no-pager -t robert 2>/dev/null \
    || true
}

check_journal() {
  local blob
  blob="$(journal_blob)"
  if [[ -z "$blob" ]]; then
    # Fallback: robert.service may log to a file instead of journald
    local logfile="${ROBERT_LOG_FILE:-$WORKSPACE/robert.log}"
    if [[ -f "$logfile" ]]; then
      blob="$(tail -n "$JOURNAL_LINES" "$logfile")"
      echo "(using logfile $logfile)"
    else
      if [[ "$PHASE" == "pre" ]]; then
        warn "journal: empty before restart — OK for --phase pre if unit logs to a custom path"
        return
      fi
      fail "journal: no journald lines and no logfile at $logfile"
      return
    fi
  fi

  # Auth failures → hard fail (all phases)
  if echo "$blob" | grep -Eiq 'invalid_api_key|authentication[_ ]?error|\b401\b|Unauthorized|auth error|permission.?denied.*api.?key'; then
    echo "$blob" | grep -Ei 'invalid_api_key|authentication|401|Unauthorized|auth error' | tail -n 5 || true
    fail "journal: auth/401/invalid_api_key signature present"
  else
    pass "journal: no auth/401/invalid_api_key signatures"
  fi

  local clear_count
  clear_count="$(echo "$blob" | grep -c 'Cleared conversation_history' || true)"
  echo "journal: Cleared conversation_history count=$clear_count (must be exactly 1 across deploy restarts)"

  case "$PHASE" in
    pre)
      # Pre-restart: do not require clear/outbound yet
      pass "journal: pre-phase (clear/outbound not required yet)"
      ;;
    post-reset)
      if [[ "$clear_count" -eq 1 ]]; then
        pass "journal: Cleared conversation_history exactly once (post-reset)"
      elif [[ "$clear_count" -eq 0 ]]; then
        fail "journal: expected exactly one Cleared conversation_history after first restart"
      else
        fail "journal: Cleared conversation_history count=$clear_count (want exactly 1) — stamp not honored"
      fi
      ;;
    final)
      # Across both restarts the clear line must appear exactly once.
      if [[ "$clear_count" -eq 1 ]]; then
        pass "journal: Cleared conversation_history exactly once across deploy window"
      elif [[ "$clear_count" -eq 0 ]]; then
        fail "journal: no Cleared conversation_history in window — widen JOURNAL_SINCE or JOURNAL_LINES"
      else
        fail "journal: Cleared conversation_history count=$clear_count (want exactly 1) — stamp FAIL"
      fi
      if echo "$blob" | grep -q 'already consumed'; then
        pass "journal: stamp-consumed reminder seen (second restart did not wipe)"
      else
        warn "journal: 'already consumed' not in window (OK if flag was removed before second start)"
      fi
      ;;
  esac

  if [[ "$PHASE" == "pre" ]]; then
    return
  fi

  if echo "$blob" | grep -q 'OUTBOUND payload roles ok'; then
    pass "journal: OUTBOUND payload roles ok present"
  else
    if [[ "$PHASE" == "post-reset" ]]; then
      warn "journal: OUTBOUND payload roles ok not yet present (send one completion before --phase final)"
    else
      fail "journal: OUTBOUND payload roles ok missing — send one completion before live T1–T6"
    fi
  fi
}

# ── (d) stamp file ──────────────────────────────────────────────────────────
check_stamp() {
  case "$PHASE" in
    pre)
      warn "stamp: not required at --phase pre"
      ;;
    post-reset)
      if [[ -f "$STAMP" ]]; then
        pass "stamp exists: $STAMP"
        echo "stamp contents: $(tr -d '\n' < "$STAMP" | head -c 80)"
      else
        fail "stamp missing: $STAMP (expected after first restart with ROBERT_RESET_CHAT_HISTORY=1)"
      fi
      ;;
    final)
      # Flag removed → listener disarms stamp; presence with flag still set is WARN
      if [[ -f "$STAMP" ]]; then
        warn "stamp still present ($STAMP) — OK if flag was left set (consumed); prefer remove flag"
        pass "stamp path checked"
      else
        pass "stamp absent after flag removal (disarmed)"
      fi
      ;;
  esac
}

# ── (e) env file guard comment ──────────────────────────────────────────────
check_env_guard_comment() {
  local envf="${ROBERT_SECRETS_ENV:-/etc/robert/secrets.env}"
  if [[ ! -f "$envf" ]]; then
    if [[ "$PHASE" == "pre" ]]; then
      fail "env file $envf not found — create from deploy/secrets.env.example before deploy"
    else
      warn "env file $envf not found — cannot verify guard comment"
    fi
    return
  fi
  if grep -q 'ROBERT_RESET_CHAT_HISTORY: leave UNSET' "$envf"; then
    pass "env guard comment present in $envf"
  else
    fail "env guard comment missing in $envf — run deploy/ensure_reset_guard_comment.sh"
  fi
  if grep -Eq '^[[:space:]]*ROBERT_RESET_CHAT_HISTORY[[:space:]]*=' "$envf"; then
    if [[ "$PHASE" == "post-reset" ]]; then
      warn "ROBERT_RESET_CHAT_HISTORY still set in $envf — remove before final restart"
    elif [[ "$PHASE" == "pre" ]]; then
      warn "ROBERT_RESET_CHAT_HISTORY set in $envf before intentional reset — OK if about to restart"
    else
      fail "ROBERT_RESET_CHAT_HISTORY still set in $envf — remove after deploy restart"
    fi
  else
    if [[ "$PHASE" == "post-reset" ]]; then
      warn "ROBERT_RESET_CHAT_HISTORY already unset at post-reset (OK if removed immediately)"
    else
      pass "ROBERT_RESET_CHAT_HISTORY unset in $envf"
    fi
  fi
}

# ── run ─────────────────────────────────────────────────────────────────────
check_api_key
check_git_head
check_journal
check_stamp
check_env_guard_comment

echo
echo "=== SUMMARY ==="
echo "PASS=$PASS FAIL=$FAIL WARN=$WARN phase=$PHASE"
if [[ "$FAIL" -gt 0 ]]; then
  echo "RESULT: FAIL — do not start live T1–T6 until green"
  exit 1
fi
echo "RESULT: PASS — safe to run live T1–T6 in a fresh Telegram thread"
exit 0
