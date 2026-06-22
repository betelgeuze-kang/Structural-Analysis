# Cursor Worker Slice: Product Snapshot Gap Ledger Split Counts

Goal:
Add commercial-solver vs AI-engine split counts to the product readiness snapshot gap-ledger component, without changing readiness decisions.

Scope:
- Inspect `scripts/build_product_readiness_snapshot.py`.
- Candidate tests: `tests/test_build_product_readiness_snapshot.py`.
- Candidate generated artifact after Codex review: `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`.

Expected behavior:
- `components.commercial_gap_ledger_status` should expose per-ledger row counts by status for `commercial_solver` and `ai_engine`.
- It should expose nonclosed row IDs and next locally closable gap IDs, so G1-G10 and AI-G1-AI-G10 coverage is visible without reading the full row list.
- Do not promote readiness and do not close any row.
- Do not add these blockers to assisted-service or solver-product blockers unless already represented.
- Do not commit or push.

Verification criteria:
- Add/update focused tests for split counts and non-promoting behavior.
- Run focused pytest for product readiness snapshot tests if feasible.
- Summarize changed files, tests run, and blockers only.
