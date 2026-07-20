# Runbook: Robert startup / restart (R0)

## Purpose

Safe start/restart after secrets or code changes. Prevents the auth/env crash-loop class.

## Preconditions

- Checkout at `/var/lib/robert/workspace` (or documented path) on `main`
- Secrets in `/etc/robert/secrets.env` (wrapper must source this file exclusively)
- Required keys present:
  - `OPENROUTER_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_KEY` (not `SUPABASE_KEY`)
  - `SUPABASE_JWT_SECRET` (**required** — without it Robert refuses to listen)
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `/etc/robert` traversable by service user (`chmod 750`, `chown root:robert`)
- **Exactly one** Telegram poller — never manual `listener.py` while systemd is active

## Restart procedure

1. Confirm unit: `systemctl cat robert` — note `EnvironmentFile` and/or `ExecStart` wrapper
2. Masked file check: `grep KEY= /etc/robert/secrets.env | sed 's/=.*/=***SET***/'`
3. Stop unit and kill stray pollers:
   `sudo systemctl stop robert; pkill -f 'listener.py' || true`
4. `sudo systemctl start robert`
5. `sudo systemctl is-active robert`
6. **Running process env** (mandatory):
   `tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value robert)/environ | grep -E '^(ANTHROPIC|SUPABASE|TELEGRAM)' | sed 's/=.*/=***SET***/'`
7. Confirm `SUPABASE_JWT_SECRET=***SET***` in process env
8. `sudo bash deploy/verify_deploy.sh --phase pre`
9. Abort if any required key is `***MISSING***`, crash-loop, or 409 dual-poller

## Single poller

Robert acquires `robert_listener.lock` (fcntl) at startup. A second instance exits immediately instead of thrashing Telegram getUpdates (HTTP 409).

## History reset (one-shot)

- Set `ROBERT_RESET_CHAT_HISTORY=1` only for intentional wipe
- Stamp-guarded; remove flag after first successful restart

## Failure modes

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Crash loop exit 1 | Missing env / wrong key name | Fix secrets; verify **process** env |
| Boots then JWT alert / drops messages | `SUPABASE_JWT_SECRET` missing | Add secret; restart; verify process env |
| Auth trap after restart | `ANTHROPIC_API_KEY` absent | Restore key before restart |
| HTTP 409 / immediate crash | Two getUpdates pollers | Stop unit + kill manual; start one only |
| DEGRADED on lock files only | Runtime `*.lock` | Filtered + `.gitignore`; commit real dirt |
| Clear history twice | Stamp not honored | FAIL — investigate stamp path |

## Recovery

- `systemctl stop robert` to halt storm
- Kill stray `listener.py` / `run_robert.sh`
- Fix secrets/perms
- Ensure `git status --porcelain` is clean of real code changes
- Manual test **only with unit stopped**
- Only then `systemctl start robert`
