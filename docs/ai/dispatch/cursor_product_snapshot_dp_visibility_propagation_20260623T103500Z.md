# Cursor worker slice: product snapshot Developer Preview visibility propagation

Goal:
- Propagate `developer_preview_readiness.gap_ledger_closure_requirement_visibility` and relevant `scope_boundary_sync` GUI closure contract summary into the `product_readiness_snapshot.components.developer_preview_readiness` component.

Scope:
- Inspect/edit:
  - `scripts/build_product_readiness_snapshot.py`
  - `tests/test_build_product_readiness_snapshot.py`
  - `tests/test_product_readiness_snapshot_doc_sync.py` only if needed
- Preferred behavior:
  - Add compact fields under the Developer Preview component, not root blockers.
  - Preserve status/readiness/blocker counts.
  - Keep claim boundaries: visibility only, no G1/G6/G7 closure, no commercial promotion.

Verification criteria:
- Focused tests pass:
  - `python3 -m pytest -q tests/test_build_product_readiness_snapshot.py tests/test_product_readiness_snapshot_doc_sync.py`
- `python3 scripts/build_product_readiness_snapshot.py --check` passes after regeneration.
- `git diff --check` passes.

Worker output:
- Return only changed files, core diff summary, tests run, failed tests, and blockers.
