Goal: Audit a small Phase 3 seed reproducibility-bundle addition before implementation.

Scope:
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `tests/test_build_phase3_benchmark_factory_artifacts.py`
- generated `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_*`

Proposed change:
- Add a fourth generated artifact, `phase3_benchmark_factory_seed_reproducibility_bundle.json`.
- It should record regeneration/check commands, manifest/scorecard/summary paths and checksums, lane/case/pass counts, environment notes, and a claim boundary that it proves only generated analytic-small + element-patch seed reproducibility, not full Phase 3 or Developer Preview RC closure.
- Add it to the script's `--check` semantic drift checks and focused tests.

Verification criteria:
- Identify any claim-overstatement risk.
- Identify any missing test expectations.
- Recommend the smallest aligned implementation shape.
- Do not edit files. Keep output concise.
