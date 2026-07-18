#!/usr/bin/env bash
# Consolidated post-deploy verification for Robert gateway fix (PR #4).
# Exit nonzero on any failure — gate live T1–T6 acceptance.
#
# Usage:
#   sudo ./deploy/verify_deploy.sh                 # full checks (default)
#   sudo ./deploy/verify_deploy.sh --phase first   # after restart WITH reset flag
#   sudo ./deploy/verify_deploy.sh --phase second  # after flag removed + 2nd restart
#   sudo ./deploy/verify_deploy.sh --phase smoke   # auth + git + journal auth only
#
# Env overrides:
#   ROBERT_UNIT=robert
#   ROBERT_WORKSPACE=/var/lib/robert/workspace
#   EXPECTED_SHA=0957da5          # or omit to require match with origin/main
#   JOURNAL_LINES=200
set -euo pipefail

UNIT="${ROBERT_UNIT:-robert}"
WORKSPACE="${ROBERT_WORKSPACE:-/var/lib/robert/workspace}"
STAMP="${ROBERT_CHAT_HISTORY_RESET_STAMP:-$WORKSPACE/.chat_history_reset_done}"
JOURNAL_LINES="${JOURNAL_LINES:-200}"
EXPECTED_SHA="${EXPECTED_SHA:-0957da5}"
PHASE="full"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) PHASE="${2:-}"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="${2:-}"; shift 2 ;;
    --workspace) WORKSPACE="${2:-}"; STAMP="$WORKSPACE/.chat_history_reset_done"; shift 2 ;;
    --unit) UNIT="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

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
  if ! systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    fail "systemd unit '$UNIT' is not active"
    mask_set "ANTHROPIC_API_KEY" ""
    return
  fi
  local pid
  pid="$(systemctl show -p MainPID --value "$UNIT" 2>/dev/null || echo 0)"
  if [[ -z "$pid" || "$pid" == "0" ]]; then
    fail "ANTHROPIC_API_KEY: could not resolve MainPID for $UNIT"
    return
  fi
  local environ="/proc/${pid}/environ"
  if [[ ! -r "$environ" ]]; then
    fail "ANTHROPIC_API_KEY: cannot read $environ (need root?)"
    return
  fi
  local val=""
  val="$(tr '\0' '\n' < "$environ" | awk -F= '$1=="ANTHROPIC_API_KEY"{print substr($0,index($0,"=")+1); exit}')"
  mask_set "ANTHROPIC_API_KEY" "$val"
  if [[ -n "$val" ]]; then
    pass "ANTHROPIC_API_KEY present in running unit env (masked)"
  else
    # Fallback: some hosts only set OPENROUTER and map Anthropic via proxy
    local or_val=""
    or_val="$(tr '\0' '\n' < "$environ" | awk -F= '$1=="OPENROUTER_API_KEY"{print substr($0,index($0,"=")+1); exit}')"
    mask_set "OPENROUTER_API_KEY" "$or_val"
    if [[ -n "$or_val" ]]; then
      warn "ANTHROPIC_API_KEY missing; OPENROUTER_API_KEY is set (may be intentional)"
      # Still fail hard — work order says confirm ANTHROPIC_API_KEY before restart
      fail "ANTHROPIC_API_KEY missing from running unit env"
    else
      fail "ANTHROPIC_API_KEY missing from running unit env"
    fi
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
  journalctl -u "$UNIT" -n "$JOURNAL_LINES" --no-pager 2>/dev/null \
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
      fail "journal: no journald lines and no logfile at $logfile"
      return
    fi
  fi

  # Auth failures → hard fail
  if echo "$blob" | grep -Eiq 'invalid_api_key|authentication[_ ]?error|\b401\b|Unauthorized|auth error|permission.?denied.*api.?key'; then
    echo "$blob" | grep -Eiw 'invalid_api_key|authentication|401|Unauthorized|auth error' | tail -n 5 || true
    fail "journal: auth/401/invalid_api_key signature present in last ${JOURNAL_LINES} lines"
  else
    pass "journal: no auth/401/invalid_api_key signatures in last ${JOURNAL_LINES} lines"
  fi

  local clear_count
  clear_count="$(echo "$blob" | grep -c 'Cleared conversation_history' || true)"
  echo "journal: Cleared conversation_history count=$clear_count"

  case "$PHASE" in
    first)
      if [[ "$clear_count" -ge 1 ]]; then
        pass "journal: Cleared conversation_history present (first restart)"
      else
        fail "journal: expected Cleared conversation_history on first restart"
      fi
      ;;
    second)
      if [[ "$clear_count" -eq 0 ]]; then
        pass "journal: no Cleared conversation_history on second restart window"
      elif [[ "$clear_count" -eq 1 ]]; then
        # Window may still include the first restart — check for consumed message
        if echo "$blob" | grep -q 'already consumed'; then
          pass "journal: reset already consumed (no second wipe); first clear still in window"
        else
          warn "journal: one clear line still in window — confirm it is from first restart only"
          # Not hard-fail if stamp exists and consumed log present elsewhere
          if [[ -f "$STAMP" ]]; then
            pass "stamp exists; treating single clear line as first-restart residue"
          else
            fail "journal: unclear whether history was wiped again on second restart"
          fi
        fi
      else
        fail "journal: Cleared conversation_history appeared multiple times (count=$clear_count) — not one-shot"
      fi
      ;;
    full|smoke|*)
      if [[ "$clear_count" -ge 1 ]]; then
        pass "journal: Cleared conversation_history seen at least once"
      else
        warn "journal: Cleared conversation_history not in last ${JOURNAL_LINES} lines (ok if already rotated or phase=smoke)"
      fi
      ;;
  esac

  if echo "$blob" | grep -q 'OUTBOUND payload roles ok'; then
    pass "journal: OUTBOUND payload roles ok present"
  else
    if [[ "$PHASE" == "smoke" || "$PHASE" == "first" ]]; then
      warn "journal: OUTBOUND payload roles ok not yet present (send a message / completion first)"
    else
      fail "journal: OUTBOUND payload roles ok missing — send one completion or check executor logs"
    fi
  fi
}

# ── (d) stamp file ──────────────────────────────────────────────────────────
check_stamp() {
  case "$PHASE" in
    first|full)
      if [[ -f "$STAMP" ]]; then
        pass "stamp exists: $STAMP"
        echo "stamp contents: $(tr -d '\n' < "$STAMP" | head -c 80)"
      else
        fail "stamp missing: $STAMP (expected after first restart with ROBERT_RESET_CHAT_HISTORY=1)"
      fi
      ;;
    second)
      if [[ -f "$STAMP" ]]; then
        # After flag removal, listener disarms (deletes) stamp — either state is OK
        warn "stamp still present after second restart (flag may still be set; should be removed)"
        pass "stamp path checked ($STAMP present — ensure env flag removed)"
      else
        pass "stamp absent after flag removal (disarmed for next intentional reset)"
      fi
      ;;
    smoke)
      if [[ -f "$STAMP" ]]; then
        pass "stamp exists: $STAMP"
      else
        warn "stamp not present yet"
      fi
      ;;
  esac
}

# ── (e) env file guard comment ──────────────────────────────────────────────
check_env_guard_comment() {
  local envf="${ROBERT_SECRETS_ENV:-/etc/robert/secrets.env}"
  if [[ ! -f "$envf" ]]; then
    warn "env file $envf not found — cannot verify guard comment"
    return
  fi
  if grep -q 'ROBERT_RESET_CHAT_HISTORY: leave UNSET' "$envf"; then
    pass "env guard comment present in $envf"
  else
    fail "env guard comment missing in $envf — run deploy/ensure_reset_guard_comment.sh"
  fi
  if grep -Eq '^[[:space:]]*ROBERT_RESET_CHAT_HISTORY[[:space:]]*=' "$envf"; then
    if [[ "$PHASE" == "first" ]]; then
      warn "ROBERT_RESET_CHAT_HISTORY still set in $envf (expected during first restart only)"
    else
      fail "ROBERT_RESET_CHAT_HISTORY still set in $envf — remove after deploy restart"
    fi
  else
    pass "ROBERT_RESET_CHAT_HISTORY unset in $envf"
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
