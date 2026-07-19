# ADR-001: PostgreSQL / Supabase as coordination authority

**Status:** Accepted (v1.x)  
**Date:** 2026-07-19

## Context

Robert needs mutual exclusion, idempotency, and (later) leader election for multi-host. Options include Redis, etcd, or PostgreSQL advisory locks / RPCs on existing Supabase.

## Decision

Use **PostgreSQL (Supabase)** as the single coordination authority for v1.x. Do **not** introduce Redis for locking/idempotency unless a future ADR justifies it on measured need.

## Consequences

- Simpler ops: one datastore for state + coordination  
- Availability coupled to Supabase uptime (explicit assumption)  
- Single-region scope; active-active multi-region requires a new ADR  
- R6 implements advisory locks / RPCs against this decision  
