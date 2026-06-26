# Cursor worker task: Phase 3 reproduction dirty-gate diagnosis

Goal:
Diagnose the current failures in Phase 3 release-control cleanup and clean-checkout reproduction tests without committing, pushing, or mutating external state.

Scope:
- `scripts/build_phase3_release_control_cleanup_plan.py`
- `scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py`
- `scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
- `tests/test_build_phase3_release_control_cleanup_plan.py`
- `tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py`
- `tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
- Generated Phase 3 productization receipts only as read-only evidence.

Context:
- Full `python3 -m pytest` currently has failures in:
  - `tests/test_build_phase3_release_control_cleanup_plan.py::test_phase3_release_control_cleanup_plan_keeps_git_gate_blocked`
  - `tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py::test_phase3_clean_checkout_reproduction_runs_isolated_seed_contract`
  - `tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py::test_git_clean_clone_reproduction_runs_local_clone_replay`
  - one tmp-path setup error in the git clean clone reproduction suite.
- The active product goal requires conservative readiness evidence. Do not turn a dirty or blocked reproduction gate into a pass unless the evidence really proves it.

Verification criteria:
- Identify whether failures are caused by stale test constants, generated artifact drift, current worktree dirtiness, temp-dir exhaustion, or real script regressions.
- Recommend the smallest aligned patch.
- If editing, keep tests claim-boundary aware: dirty or blocked evidence must remain visible rather than being hidden.

Output:
- Changed files, if any.
- Focused test command results.
- Concise diagnosis and remaining blockers.
