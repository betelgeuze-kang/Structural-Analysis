## Summary

## CI lane

Pick the lane this PR belongs to (they are verified by different workflows):

- [ ] **Frontend / web** (`prototype/**`, `src/**`, `tests/frontend/**`, `package*.json`) → gated by **Frontend Web CI** (`frontend-web-ci.yml`: build + DOM contract + Playwright). A queued/cancelled **heavy** solver job is NOT the merge gate for this lane.
- [ ] **Heavy / solver** (Python, GPU/HIP, large benchmarks, full validation) → gated by **CI** (`ci.yml`, self-hosted).
- [ ] Both lanes touched (call out which checks must pass).

> Frontend-only PRs should be judged by Frontend Web CI (or the manual fallback in `docs/ai/checklists/frontend-web-pr-review.md`), not by the heavy solver CI.

## Active Codex Goal

- Goal:
- Worker used:
  - [ ] Codex direct edits
  - [ ] Cursor auto
  - [ ] OpenCode Minimax M3

## Verification

- [ ] `./scripts/ai-verify.sh` passed
- [ ] Relevant readiness/status gates passed or remaining gaps are stated
- [ ] Codex reviewed the final diff
- [ ] Acceptance criteria satisfied

## Safety

- [ ] No unauthorized deploy/publish/release/migration/payment/cloud mutation
- [ ] No secrets or PII logged
- [ ] R3/R4 or external-state changes received human approval

## Notes
