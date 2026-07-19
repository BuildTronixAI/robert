# ADR-005: Leader election strategy

**Status:** Proposed (fill in during R6)  
**Date:** 2026-07-19

## Context

Multi-host Robert must avoid split-brain double execution. Coordination is PostgreSQL per ADR-001.

## Decision

*(To be completed in R6)* Specify:

- Leader election mechanism (e.g. advisory lock lease / session)
- Fencing tokens / generation numbers
- Behavior on network partition
- Clock skew tolerance
- Node resurrection after mid-commit
- Duplicate webhook / replay handling

## Consequences

- R6 cannot close without proven single-leader under partition tests  
- Ties to R6.5 upgrade/rollback and version-skew rules  
