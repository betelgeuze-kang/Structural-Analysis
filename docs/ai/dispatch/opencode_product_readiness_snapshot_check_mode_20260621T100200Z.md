# OpenCode slice: product readiness snapshot check mode

Goal: add a non-mutating check path for the canonical product readiness snapshot so release verification can fail when the stored snapshot is stale or inconsistent without rewriting evidence first.

Scope:
- Inspect only:
  - `scripts/build_product_readiness_snapshot.py`
  - `scripts/verify_quality_gate.py`
  - `tests/test_build_product_readiness_snapshot.py`
  - `tests/test_verify_quality_gate.py`
- Do not edit release evidence JSON, README, ledgers, or generated status docs.
- Do not promote readiness, remove blockers, relax thresholds, or turn stale evidence into PASS.

Candidate work:
- Add `--check` to `build_product_readiness_snapshot.py`.
- In check mode, compare the generated snapshot with the existing `--out` file without writing it.
- Ignore volatile `generated_at` only; semantic fields such as `source_commit_sha`, `status`, `evidence_fresh`, blocker lists, and component statuses must match.
- Return non-zero when the stored snapshot is missing, unreadable, stale, or semantically different.
- Update release mode in `scripts/verify_quality_gate.py` to use the non-mutating check.
- Add focused tests for normal check pass and mismatch failure.

Verification:
- Run focused tests for snapshot builder and verify_quality_gate.
- Output only changed files, test result, and any blocker.
