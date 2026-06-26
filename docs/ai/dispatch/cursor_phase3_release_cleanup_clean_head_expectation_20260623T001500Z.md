# Cursor worker slice: Phase 3 release cleanup clean-HEAD expectation

Goal:
- Diagnose and fix the focused test failure after regenerating readiness artifacts at the current clean pushed HEAD.

Failure:
- `python3 -m pytest -q tests/test_build_phase3_release_control_cleanup_plan.py::test_phase3_release_control_cleanup_plan_keeps_git_gate_blocked`
- Current failure: expected `candidate_release_control_commit_set_count == 45`, actual `13`.

Scope:
- Candidate files:
  - `scripts/build_phase3_release_control_cleanup_plan.py`
  - `tests/test_build_phase3_release_control_cleanup_plan.py`
  - `implementation/phase1/release_evidence/productization/phase3_release_control_cleanup_plan.json`
  - any directly related Phase 3 benchmark reproduction receipt only if needed

Constraints:
- Do not broaden readiness claims.
- Keep externally blocked, dirty-worktree, and human-git-action states visible.
- If 13 is the correct clean-HEAD count, update the test expectation and assertions to verify the intended clean-HEAD semantics rather than stale pre-commit counts.
- If 45 is still required, identify the missing candidate classification and fix the generator without fabricating blockers.

Verification:
- Run the focused failing test.
- Run `python3 scripts/build_phase3_release_control_cleanup_plan.py --check`.
- Summarize changed files, test result, and the reason 13 vs 45 is correct.
