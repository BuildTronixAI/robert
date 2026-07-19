# ADR-002: Mesh C outbound HMAC → Ed25519

**Status:** Accepted transition plan (v1.x)  
**Date:** 2026-07-19

## Context

Inbound BOB→Robert mesh already uses Ed25519. Outbound Robert→BOB Mesh C currently plans HMAC to `BOB_INBOX_URL`. HMAC allows any party with the shared secret to impersonate the sender — acceptable short-term, weak for multi-agent peers.

## Decision

- **R4a:** May activate Mesh C with HMAC **only if** a written migration plan to Ed25519 exists, Robert keypair generation is tested, BOB verification endpoint is ready (or scheduled with owner), and rollback is documented.  
- **R4b:** Robert signs outbound with Ed25519; BOB verifies; HMAC path retired.  
- HMAC must **not** become permanent without a new ADR reversing this.

## Consequences

- R4a cannot close without R4b migration artifacts  
- Key rotation runbook required at R4b  
- Aligns inbound and outbound cryptographic identity over time  
