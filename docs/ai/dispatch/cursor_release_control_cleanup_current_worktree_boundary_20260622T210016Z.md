# Cursor Worker Slice: Release-Control Cleanup Current Worktree Boundary

Goal:
Clarify the boundary between the Phase 3 seed git-clean-clone cleanup candidate set and the current product snapshot worktree/source-state blocker.

Scope:
- Inspect `scripts/build_phase3_release_control_cleanup_plan.py`.
- Inspect `scripts/build_product_readiness_snapshot.py` only if needed for field naming.
- Candidate tests: `tests/test_build_phase3_release_control_cleanup_plan.py`, `tests/test_build_product_readiness_snapshot.py`.
- Candidate generated artifacts after Codex review: `phase3_release_control_cleanup_plan.json`, `product_readiness_snapshot.json`.

Expected behavior:
- Do not mark release-control cleanup ready.
- Do not add commit, push, or release commands.
- Make it explicit that `candidate_release_control_commit_set_count` comes from the Phase 3 seed git-clean-clone reproduction receipt, while `dirty_path_count`/`non_receipt_dirty_path_count` in product snapshot are current worktree diagnostics.
- Preserve human handoff wording and owner-review requirement.
- Do not claim Developer Preview, Phase 3, or Commercial Release closure.

Verification criteria:
- Add focused tests for the claim boundary/field naming if changed.
- Run focused pytest for the touched builders if feasible.
- Summarize changed files, tests run, and blockers only.
