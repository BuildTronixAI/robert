#!/usr/bin/env bash
# Ensure the permanent ROBERT_RESET_CHAT_HISTORY guard comment exists in a
# live EnvironmentFile (default: /etc/robert/secrets.env). Idempotent.
set -euo pipefail

ENV_FILE="${1:-/etc/robert/secrets.env}"

GUARD_BLOCK='# ROBERT_RESET_CHAT_HISTORY: leave UNSET. Only set =1 (one-shot,
# stamp-guarded) or =force (override stamp) for an intentional
# history wipe. Remove after the deploy restart. Never bake into
# templates or config sync.'

if [[ ! -f "$ENV_FILE" ]]; then
  echo "FAIL: env file not found: $ENV_FILE" >&2
  echo "Create it from deploy/secrets.env.example first." >&2
  exit 1
fi

if grep -q 'ROBERT_RESET_CHAT_HISTORY: leave UNSET' "$ENV_FILE"; then
  echo "PASS: guard comment already present in $ENV_FILE"
  # Ensure the flag is not actively set to a sticky default
  if grep -Eq '^[[:space:]]*ROBERT_RESET_CHAT_HISTORY[[:space:]]*=' "$ENV_FILE"; then
    echo "WARN: ROBERT_RESET_CHAT_HISTORY is currently set in $ENV_FILE — remove after deploy restart" >&2
  fi
  exit 0
fi

# Insert before any existing ROBERT_RESET line, else append at end
if grep -Eq '^[[:space:]]*#?[[:space:]]*ROBERT_RESET_CHAT_HISTORY' "$ENV_FILE"; then
  tmp="$(mktemp)"
  awk -v block="$GUARD_BLOCK" '
    !done && $0 ~ /^[[:space:]]*#?[[:space:]]*ROBERT_RESET_CHAT_HISTORY/ {
      print block
      done=1
    }
    { print }
    END {
      if (!done) print block
    }
  ' "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
else
  printf '\n%s\n# ROBERT_RESET_CHAT_HISTORY=\n' "$GUARD_BLOCK" >> "$ENV_FILE"
fi

echo "PASS: inserted guard comment into $ENV_FILE"
