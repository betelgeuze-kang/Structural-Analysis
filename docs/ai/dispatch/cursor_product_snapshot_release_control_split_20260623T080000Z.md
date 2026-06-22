Goal: Review whether the product readiness snapshot clearly separates local worktree cleanup from remote GitHub sync blockers.

Scope:
- Inspect `scripts/build_product_readiness_snapshot.py`.
- Inspect `tests/test_build_product_readiness_snapshot.py`.
- Inspect `implementation/phase1/release_evidence/productization/phase3_release_control_cleanup_plan.json`.
- Inspect `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`.

Current observation:
- Root blocker stream `release freshness/sync` includes both local `stale_or_inconsistent:worktree_dirty` and remote sync blockers.
- `state_consistency.worktree.phase3_release_control_cleanup_plan` already summarizes local cleanup, but this is easy to miss.

Expected output:
- Recommend the minimal snapshot/test change, if any, to expose local release-control cleanup separately from remote GitHub sync without increasing readiness.
- Do not change readiness flags, do not remove blockers, do not push/commit.
- Keep claim boundaries explicit: suggested local git commands are human handoff only.
