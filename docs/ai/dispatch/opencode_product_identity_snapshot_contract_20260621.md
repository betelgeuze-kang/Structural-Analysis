# Product identity snapshot contract slice

Goal: tighten product identity readiness so package.json and pyproject.toml name/version mismatches are surfaced by canonical product_readiness_snapshot.json with precise blockers.

Scope:
- scripts/build_product_readiness_snapshot.py
- tests/test_build_product_readiness_snapshot.py

Constraints:
- Do not change product name/version values unless current authoritative files are actually mismatched.
- Do not promote readiness or remove existing blockers.
- Preserve current happy path where package.json and pyproject.toml both say structural-optimization-workbench 1.0.0.
- Prefer explicit blockers for name mismatch and version mismatch over one generic product_identity_mismatch blocker.

Deliverable:
- Identify exact blocker names and tests to add.
- Keep output concise; no file edits.
