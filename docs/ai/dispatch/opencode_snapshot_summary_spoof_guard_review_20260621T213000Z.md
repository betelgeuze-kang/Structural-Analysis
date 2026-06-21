# OpenCode Worker Slice: Product Readiness Snapshot Spoof Guard Review

Goal: inspect whether `scripts/build_product_readiness_snapshot.py` can be tricked into marking paid-pilot/release readiness from summary counters alone when per-row or per-receipt evidence is missing.

Scope:
- `scripts/build_product_readiness_snapshot.py`
- `tests/test_build_product_readiness_snapshot.py`
- related current snapshot artifacts only for understanding, no broad evidence refresh.

Questions:
- Can fresh full-validation readiness pass with `lane_count` and summary counts but no `rows`?
- Can customer shadow readiness pass with summary count only while case rows are missing or incomplete?
- Can external benchmark readiness pass with summary attached count only while update rows lack concrete receipts?

Verification criteria:
- Report only candidate gaps, proposed minimal tests, and whether existing tests already cover each path.
- Do not edit files.
- Do not claim any blocker closed.
