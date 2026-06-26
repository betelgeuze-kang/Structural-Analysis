# OpenCode Worker Slice: Phase 3 Git Clean Clone Required Path Roles

## Goal
Audit and suggest a small classification for Phase 3 git-clean-clone required path blockers.

## Scope
- `scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
- `tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
- Current receipt: `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`

## Desired outcome
The receipt should keep git clean clone reproduction `blocked` when required inputs are untracked or dirty, but it should distinguish path roles such as:
- source input/report
- generated productization evidence
- reproduction/build script
- package/config/core package
- focused test

Do not remove blockers just to make the gate pass. Do not claim Phase 3 or Developer Preview closure.

## Verification criteria
- Report whether the classification is complete and claim-safe.
- If editing, keep changes small and report changed files.
- Run focused tests if possible.
