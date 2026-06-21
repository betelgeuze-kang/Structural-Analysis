# Goal
Review the current release gate and readiness snapshot check behavior for a small fail-open gap. This is review-only.

# Scope
- Inspect only:
  - `scripts/verify_quality_gate.py`
  - `tests/test_verify_quality_gate.py`
  - `scripts/build_product_readiness_snapshot.py`
  - `scripts/check_github_actions_self_hosted_runner_status.py`
  - their focused tests
- Do not edit files.
- Do not run broad tests.
- Do not touch evidence JSON.
- Do not push, fetch, merge, or use network.

# Questions
1. Does release mode continue after runner status or snapshot failure and return non-zero?
2. Does check mode avoid rewriting tracked evidence?
3. Is there one small missing test that would prevent a release-readiness fail-open?

# Output format
Use exactly these sections and no prose before the first heading:

## Changed files
None

## Test results
Not run

## Failed tests
None

## Core diff summary
- Recommended missing test, or `None`.

## Blockers
- Any blocker, or `None`.
