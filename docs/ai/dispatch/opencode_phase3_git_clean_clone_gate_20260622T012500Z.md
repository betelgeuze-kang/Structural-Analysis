# OpenCode worker slice: Phase 3 git clean clone gate

Goal:
- Add an honest Phase 3 benchmark factory git-clean-clone reproduction gate.
- It must not promote Developer Preview or Phase 3 closure when current required seed files are untracked/dirty.

Scope:
- Inspect only:
  - `scripts/build_phase3_benchmark_factory_artifacts.py`
  - `scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py`
  - new `scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
  - related Phase 3 tests
  - generated Phase 3 productization receipts

Expected behavior:
- Preflight required Phase 3 paths with git.
- If required paths are not tracked or have uncommitted changes, write a `blocked` receipt with explicit blockers.
- Do not claim full git clean clone execution unless the preflight passes and an actual local clone replay succeeds.
- Keep claim boundaries: not Linux/Windows parity, not DP RC closure, not full Phase 3.

Verification criteria:
- Focused pytest for the new runner and existing Phase 3 artifact tests.
- Ruff on touched Phase 3 scripts/tests.
- `scripts/build_phase3_benchmark_factory_artifacts.py --check` remains consistent after regeneration.

Output:
- Changed files only.
- Test results.
- Blockers and claim-boundary concerns.
