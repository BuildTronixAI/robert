# ADR-003: Observability schema

**Status:** Proposed (fill in during R3)  
**Date:** 2026-07-19

## Context

R3 requires structured logs, DLQ records, correlation IDs, and SLO instrumentation before adding more tools (R2).

## Decision

*(To be completed in R3)* Define:

- Log field schema (task_id, message_kind, correlation_id, decision, latency_ms, error_class)
- DLQ payload format and retention
- Metrics exported and alert thresholds aligned to plan SLOs
- Replay mechanism for failed tasks

## Consequences

- No R2 tool expansion until this ADR is Accepted with production sample evidence  
