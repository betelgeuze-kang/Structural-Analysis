# OpenCode worker slice: Phase 3 acquisition manifest

Goal:
- Add a machine-readable Phase 3 non-seed benchmark acquisition plan/receipt.
- Do not download data, grant license approval, or promote Phase 3 closure.

Scope:
- Inspect:
  - `scripts/build_phase3_benchmark_factory_artifacts.py`
  - `src/structural_analysis/benchmark/`
  - Phase 3 productization receipts
  - Phase 3 tests

Expected behavior:
- Represent non-seed lanes: opensees-medium, opensees-megatall, buildingsmart-clean-ifc, buildingsmart-dirty-ifc, ifc-query-and-gui, commercial-cross-solver, large-model-performance.
- Each row must expose source id, acquisition mode, truth class, license state, checksum state, expected-output state, redistribution/commercial-use state, blocker list, and claim boundary.
- Overall status must remain blocked until licenses/checksums/expected outputs are attached.
- Existing generated analytic/element-patch scorecard must remain ready but full Phase 3 closure false.

Verification:
- Focused pytest for new acquisition artifact behavior and existing Phase 3 builder tests.
- Ruff on touched files.

Output:
- Changed files.
- Test results.
- Any claim-boundary concerns.
