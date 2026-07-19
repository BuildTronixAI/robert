# Robert Robustness Plan (v1.x)

**Status:** Locked — planning frozen; execute with evidence.  
**Scope:** Canonical roadmap for **Robert v1.x under the current architecture assumptions** (not universal).

### Architecture assumptions (v1.x)

- Single-region
- PostgreSQL / Supabase as state + coordination authority
- LangGraph runtime
- Telegram as primary human interface
- TronixMesh peer with BOB (inbound Ed25519 today; outbound Mesh C transitional HMAC → Ed25519)

If these change (e.g. active-active multi-region, different orchestrator), R4–R6 must be revisited via new ADRs.

### Guiding question

Not “what can Robert do?” — **under what conditions can Robert be trusted?**

---

## Universal Definition of Done (every R-phase)

A phase is **not** closed until all are true:

| # | Requirement |
|---|-------------|
| 1 | Code merged to `main` |
| 2 | Documentation updated (README, runbooks, assumptions) |
| 3 | Rollback tested (N→N−1 works cleanly) where applicable |
| 4 | Monitoring live (metrics + alerts) where the phase introduces signals |
| 5 | Runbook written (operate, failure modes, recovery) |
| 6 | Peer reviewed (external eyes on design) |
| 7 | Production evidence (live results, not simulation only) |

This prevents “90% done forever.”

### Gate owners (every phase)

| Role | Responsibility |
|------|----------------|
| **Builder** | Implements the phase |
| **Reviewer** | Technical verification (design + tests) |
| **Operator** | Production validation on host |
| **Approver** | Authorizes phase closure (Chris / designated) |

Default for Robert v1.x: Builder = Cursor/agent or eng implementer; Reviewer = peer; Operator = BOB/host; Approver = Chris.

---

## SLOs (instrument from R3; enforce from R3+)

| Metric | Target |
|--------|--------|
| Gateway uptime | 99.9% |
| Decision latency (orchestrator stack) | &lt;2 s |
| Recovery after crash | &lt;5 min |
| Duplicate gated execution | 0 |
| Lost approved actions | 0 |
| Alert delivery | &gt;99.5% |
| Validator / internal error leak to Telegram | 0 |
| Load p99 latency (R5.5) | &lt;5 s |

---

## Final roadmap (production-grade)

| Phase | Name | Exit focus |
|-------|------|------------|
| **R0** | Deployment validation | Hard gate: `verify_deploy` + live T1–T6 |
| **R1** | Runtime consistency | Wrapper, secrets, perms, **running** process env |
| **R3** | Observability | Structured logs, DLQ, correlation IDs, SLOs |
| **R3.5** | Chaos / DR drills | LLM/Telegram/disk/crash; no corrupt / no double-exec |
| **R2** | Tool integration | Vision, documents, research, Supabase tools |
| **R4a** | Mesh C activate (HMAC transitional) | Migration plan to R4b required |
| **R5** | Approval workflows | Fail-closed on human/Telegram absence |
| **R5.5** | Performance & load | 1K tasks, 100 concurrent, bursts; p99 &lt;5s; 0 dupes |
| **R4b** | Ed25519 upgrade | Asymmetric peer identity; rollback tested |
| **R6** | Distributed runtime | Locks, leader election, split-brain, clock skew |
| **R6.5** | Upgrade / rollback | N→N+1, rollback, schema compat, version skew |
| **R7** | Construction COO capabilities | RFI/CO/vendor/schedule/financials + ROI |

**Platform:** R0–R6.5 · **Product/ROI:** R7

### Coordination assumption (statement of record)

Distributed coordination (leader election, locking, idempotency) is delegated to **PostgreSQL/Supabase**.

- PostgreSQL is the single source of truth for state  
- Advisory locks provide mutual exclusion  
- RPC functions ensure idempotency  
- Availability depends on Supabase uptime  

**No Redis** for coordination unless a future ADR justifies it.  
**Current scope:** single-region, PostgreSQL as authority. See [ADR-001](docs/adr/ADR-001-postgres-coordination.md).

### R4a → R4b (HMAC must not become permanent)

R4a is **not** complete until:

1. Migration plan to Ed25519 written (ticket, risk, steps)  
2. Robert Ed25519 keypair generation tested (create + export public)  
3. BOB verification endpoint ready  
4. Rollback path documented  

See [ADR-002](docs/adr/ADR-002-hmac-to-ed25519.md).

### R5.5 load scenarios

- 1,000 queued tasks — no crash; DLQ works  
- 100 concurrent Telegram requests — no thundering herd  
- Webhook burst / double-fire — idempotency holds  
- Supabase latency spikes — graceful timeouts, no silent failures  
- LLM rate limiting — retry + queue behavior  

Exit: p99 &lt;5s under load; 0 duplicate executions; queue don’t drop; recovery without manual intervention.

---

## Artifacts per phase

| Phase | Gate report | Evidence | Runbook |
|-------|-------------|----------|---------|
| R0 | `verify_deploy` + T1–T6 pass | Live test output | Startup/restart procedure |
| R1 | Runtime consistency checklist | File permissions audit | Secrets management guide |
| R3 | Observability spec | Sample logs + DLQ records | How to debug failures |
| R3.5 | Chaos test results | All failure modes survived | Failure response procedures |
| R2 | Tool integration tests | Monitoring dashboard | How to add new tools |
| R4a | HMAC→Ed25519 migration plan | Keypair generation tests | Mesh C activation steps |
| R5 | Approval gate spec | Timeout drills | Approval gate operations |
| R5.5 | Load test results | p99 latency graphs | Performance tuning guide |
| R4b | Ed25519 deployment | Signature verification tests | Crypto key rotation |
| R6 | Distributed systems tests | Leader election verified | Multi-host operations |
| R6.5 | Upgrade validation | Rollback success logs | Zero-downtime deployment |
| R7 | Construction domain review | End-to-end workflow tests | COO feature operations |

---

## Architecture Decision Records

| ADR | Decision |
|-----|----------|
| [ADR-001](docs/adr/ADR-001-postgres-coordination.md) | PostgreSQL is coordination authority |
| [ADR-002](docs/adr/ADR-002-hmac-to-ed25519.md) | HMAC → Ed25519 migration for Mesh C outbound |
| [ADR-003](docs/adr/ADR-003-observability-schema.md) | Observability schema (placeholder until R3) |
| [ADR-004](docs/adr/ADR-004-approval-timeout.md) | Approval timeout / fail-closed policy (placeholder until R5) |
| [ADR-005](docs/adr/ADR-005-leader-election.md) | Leader election strategy (placeholder until R6) |

---

## R0 — Immediate execution (hard gate)

**Do not start R1 until R0 is closed with production evidence.**

### Operator checklist (host)

```bash
# 1) Secrets — filesystem
sudo grep -E '^(ANTHROPIC_API_KEY|OPENROUTER_API_KEY|SUPABASE_SERVICE_KEY|SUPABASE_URL)=' \
  /etc/robert/secrets.env | sed 's/=.*/=***SET***/'
# Ensure SUPABASE_SERVICE_KEY (not SUPABASE_KEY). Ensure ANTHROPIC_API_KEY is set.

# 2) Restart
sudo systemctl restart robert
sudo systemctl is-active robert

# 3) Running process env (not just the file) — closes config drift
PID=$(systemctl show -p MainPID --value robert)
sudo tr '\0' '\n' < /proc/$PID/environ \
  | grep -E '^(ANTHROPIC_API_KEY|SUPABASE_SERVICE_KEY|SUPABASE_URL)=' \
  | sed 's/=.*/=***SET***/'

# 4) Deploy verify
cd /var/lib/robert/workspace   # or actual checkout
sudo git pull origin main
sudo bash deploy/ensure_reset_guard_comment.sh /etc/robert/secrets.env
sudo bash deploy/verify_deploy.sh --phase pre
# If history reset still needed for this deploy cycle:
#   set ROBERT_RESET_CHAT_HISTORY=1 → restart → --phase post-reset
#   remove flag → restart → --phase final
# Else if already reset previously: --phase final after one healthy completion

# 5) Live T1–T6 in a FRESH Telegram thread
# T1 Robert, status report
# T2 What is today's date
# T3 Check again
# T4 Are you Claude?
# T5 Tell me a one-sentence joke
# T6 one real executable task

# 6) Gate report → Approver closes R0 only with verbatim replies + verify_deploy PASS
```

### R0 grading (strict)

| Test | Pass criteria |
|------|----------------|
| T1 | In persona; no identity disclaimer; no stale “today” dates |
| T2 | Correct current date (Eastern / `current_datetime`) |
| T3 | Re-confirms date; **zero** identity content |
| T4 | Access Model deflect; stay in persona; commercial-AI ack OK if pressed; no Claude-disclaimer collapse |
| T5 | Plain chat; no validator error; no `##` sections |
| T6 | Full `## Task Output` + `## Completion Report`; validator pass |

On any FAIL: diagnosis only (which fix 1–5 / which R-item); no second deploy cycle without Approver OK.

### R0 artifacts

- `deploy/verify_deploy` PASS summary (pre / post-reset / final as applicable)  
- Verbatim T1–T6 replies  
- Gate report (Approver sign-off)  
- Runbook: [deploy/runbooks/robert-startup-restart.md](deploy/runbooks/robert-startup-restart.md)

---

## Related docs

- Gateway work order: `ROBERT-GATEWAY-FIX-WORKORDER-P0.md`  
- Env template: `deploy/secrets.env.example`  
- Verify script: `deploy/verify_deploy.sh`  
- Closure (after R0 pass): `ROBERT-GATEWAY-FIX-CLOSURE.md` (to be written on full T1–T6 pass)
