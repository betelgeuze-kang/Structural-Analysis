# OpenCode worker slice: GitHub sync PM gate visibility

Goal:
- Make the existing read-only GitHub development sync preflight visible in PM/release gate evidence if it is not already represented.
- Do not push, merge, publish, or mutate any remote/external state.

Scope:
- Inspect only the relevant PM gate and sync preflight code/tests/docs.
- Candidate files:
  - `scripts/check_github_development_sync_preflight.py`
  - `scripts/report_pm_release_gate.py`
  - `tests/test_check_github_development_sync_preflight.py`
  - `tests/test_report_pm_release_gate.py`
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `docs/github-documentation-status.md`
- If a low-risk implementation is clear, wire `check_github_development_sync_preflight.py` output into PM release gate as a read-only status/release-area blocker while preserving existing claim boundaries.
- If implementation is too broad, leave files unchanged and summarize the exact recommended follow-up.

Verification criteria:
- Focused pytest for changed tests.
- `git diff --check`.
- `./scripts/ai-verify.sh` if files changed.
- No remote mutation.

Worker output must include only:
- Changed files.
- Tests run and results.
- Failed test names, if any.
- Core diff summary.
- Blockers.
