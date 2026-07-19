# Runbook: Robert startup / restart (R0)

## Purpose

Safe start/restart after secrets or code changes. Prevents the auth/env crash-loop class.

## Preconditions

- Checkout at `/var/lib/robert/workspace` (or documented path) on `main`
- Secrets in `/etc/robert/secrets.env` (and wrapper source of truth if using `run_robert.sh`)
- Required keys present: `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (not `SUPABASE_KEY`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `/etc/robert` traversable by service user (`chmod 750`, `chown root:robert` preferred over world-execute)

## Restart procedure

1. Confirm unit: `systemctl cat robert` — note `EnvironmentFile` and/or `ExecStart` wrapper  
2. Masked file check: `grep KEY= /etc/robert/secrets.env | sed 's/=.*/=***SET***/'`  
3. `sudo systemctl restart robert`  
4. `sudo systemctl is-active robert`  
5. **Running process env** (mandatory):  
   `tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value robert)/environ | grep -E '^(ANTHROPIC|SUPABASE|TELEGRAM)' | sed 's/=.*/=***SET***/'`  
6. `sudo bash deploy/verify_deploy.sh --phase pre` (or `final` if mid-deploy sequence)  
7. Abort if any required key is `***MISSING***` or unit crash-loops  

## History reset (one-shot)

- Set `ROBERT_RESET_CHAT_HISTORY=1` only for intentional wipe  
- Stamp-guarded: see listener + `deploy/secrets.env.example` comment  
- Remove flag after first successful restart; never bake into templates  

## Failure modes

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Crash loop exit 1 | Missing env / wrong key name | Fix secrets; verify **process** env |
| `SUPABASE_URL` missing at runtime | EnvironmentFile/wrapper not loading | Fix perms + wrapper; don’t add dotenv as primary |
| Auth trap after restart | `ANTHROPIC_API_KEY` absent | Restore key before restart |
| Clear history twice | Stamp not honored | FAIL — stop; investigate stamp path |

## Recovery

- `systemctl stop robert` to halt storm  
- Fix secrets/perms  
- Manual `run_robert.sh` or `python3 listener.py` once with env loaded  
- Only then `systemctl start robert`  
