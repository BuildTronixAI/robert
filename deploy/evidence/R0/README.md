# R0 Evidence Package

Fill this directory (or attach equivalents) before Approver marks **R0 = COMPLETE**.  
Do **not** commit real secrets. Mask all key values as `***SET***` / `***MISSING***`.

## Checklist

Copy into `GATE_REPORT.md` and tick:

### Deployment
- [ ] Cold restart clean
- [ ] Documented steps only (no ad-hoc hacks left in place)
- [ ] `verify_deploy` PASS (attach `verify_deploy.log`)

### Runtime
- [ ] Process env matches secrets source (`process_env_masked.txt`)
- [ ] Wrapper is sole config source (note path in `RUNTIME_NOTES.md`)
- [ ] No shadow env vars
- [ ] Workspace path exact (`pwd` / `WORKSPACE_PATH`)

### Functional
- [ ] T1–T6 fresh thread — paste verbatim into `T1_T6_REPLIES.md`
- [ ] No regressions noted
- [ ] Each test has evidence

### Operational
- [ ] Startup time UTC recorded
- [ ] Restart runbook followed (`deploy/runbooks/robert-startup-restart.md`)
- [ ] Rollback verified (note how: previous unit/commit or secrets revert)
- [ ] Gate report signed below

## Files to capture

| File | Contents |
|------|----------|
| `verify_deploy.log` | Full `--phase pre` (and post-reset/final if used) |
| `process_env_masked.txt` | Masked running environ keys |
| `RUNTIME_NOTES.md` | Wrapper path, workspace path, single secrets source |
| `T1_T6_REPLIES.md` | Verbatim Robert replies |
| `GATE_REPORT.md` | Sign-off |
| `startup_timing.txt` | Cold start timestamps |

## Sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| Builder | | | |
| Reviewer | | | |
| Operator | | | |
| Approver | | | R0 COMPLETE / FAIL |
