# OpenCode slice: self-hosted runner status check mode

Goal: make release verification avoid rewriting self-hosted runner evidence while still failing when the stored status is stale or blocked.

Scope:
- Inspect only:
  - `scripts/check_github_actions_self_hosted_runner_status.py`
  - `scripts/verify_quality_gate.py`
  - `tests/test_check_github_actions_self_hosted_runner_status.py`
  - `tests/test_verify_quality_gate.py`
- Do not edit release evidence JSON, README, ledgers, or generated docs.
- Do not relax runner requirements or turn missing/offline runners into PASS.

Candidate work:
- Add a non-mutating `--check` mode to `check_github_actions_self_hosted_runner_status.py`.
- In check mode, compute current status, compare it with existing `--out`, ignore `generated_at` only, and return non-zero when missing/unreadable/semantic mismatch.
- Keep `--fail-blocked` behavior strict.
- Update release mode in `scripts/verify_quality_gate.py` to call runner status with `--check`.
- Add focused tests for check pass, mismatch/missing failure, and release dry-run command shape.

Verification:
- Run focused tests for the runner status script and quality gate.
- Output only changed files, test result, and any blocker.
