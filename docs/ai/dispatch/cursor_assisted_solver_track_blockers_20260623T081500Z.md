Goal: Review assisted-service vs solver-product blocker separation in the canonical product readiness snapshot.

Scope:
- Inspect `scripts/build_product_readiness_snapshot.py`.
- Inspect `tests/test_build_product_readiness_snapshot.py`.
- Inspect `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`.

Current observation:
- The snapshot has separate `components.assisted_service_pilot` and `components.solver_product` sections.
- Each section exposes readiness booleans, but not an explicit blocker list scoped to that track.

Expected output:
- Recommend the minimal builder/test change, if any, to expose separate scoped blockers for:
  - assisted_service_pilot
  - solver_product
- Do not promote readiness, remove blockers, relax G1/EB/customer/fresh-validation gates, or mutate git/remotes.
- Keep claim boundaries explicit.
