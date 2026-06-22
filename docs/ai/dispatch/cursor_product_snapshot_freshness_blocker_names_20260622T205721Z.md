# Cursor Worker Slice: Product Snapshot Freshness Blocker Naming

Goal:
Clarify product readiness snapshot blocker naming so assisted-service and solver-product track blockers do not imply that `release_evidence_freshness_report.json` failed when the actual blocking condition is snapshot source-state/worktree consistency.

Scope:
- Inspect `scripts/build_product_readiness_snapshot.py`.
- Candidate tests: `tests/test_build_product_readiness_snapshot.py`.
- Candidate generated artifact after Codex review: `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`.

Expected behavior:
- Keep release freshness report semantics separate from snapshot/source-state consistency.
- If the track blocker currently named `evidence_not_fresh` is driven by `schema_valid and not stale_or_inconsistent`, rename or augment it to describe source-state consistency more accurately.
- Preserve existing blockers for quality, GitHub sync, UX observation, license, G1, external benchmark, customer shadow, and fresh full validation.
- Do not mark any readiness gate closed.
- Do not commit or push.

Verification criteria:
- Add or update focused tests showing that a stale/non-receipt source-state blocker is distinguishable from release freshness PASS.
- Run focused pytest for product readiness snapshot tests if feasible.
- Summarize changed files, tests run, and any blockers only.
