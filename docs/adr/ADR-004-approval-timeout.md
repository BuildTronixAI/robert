# ADR-004: Approval timeout / fail-closed policy

**Status:** Proposed (fill in during R5)  
**Date:** 2026-07-19

## Context

Gate level 2 depends on humans. Telegram down, lost phone, missing quorum, or never-arriving callbacks must not auto-approve mutators.

## Decision

*(To be completed in R5)* Specify:

- Timeout duration per risk class (YELLOW / RED)
- Behavior on timeout: **fail closed** (block mutator; notify; DLQ/escalate)
- Quorum incomplete behavior
- Operator unavailable / Telegram down behavior
- Recovery when approver returns

## Consequences

- R5 DoD requires timeout drills with evidence  
- Lost approved actions SLO target remains 0  
