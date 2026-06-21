# OpenCode slice: G1 full-load HIP lane safety probe

Goal: inspect the existing G1 full-load HIP Newton lane and identify the smallest local safety improvement that prevents diagnostic or fallback evidence from being promoted as full G1 closure.

Scope:
- `scripts/run_g1_full_load_hip_newton_lane.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `scripts/build_product_readiness_snapshot.py`
- `tests/test_run_g1_full_load_hip_newton_lane.py`
- `tests/test_mgt_direct_residual_newton_probe.py`
- `tests/test_build_product_readiness_snapshot.py`

Constraints:
- Do not claim full G1 closure.
- Do not relax thresholds.
- Do not synthesize ROCm/HIP, customer, validation, EB, UX, license, or CI evidence.
- Keep the change small. Prefer tests or a narrow gate check.

Questions to answer:
- Does the lane currently reject child evidence that is sub-full-load, CPU/fallback-backed, reused, or missing explicit HIP residency metadata?
- If one small implementation change is warranted, make it and add focused tests.

Verification:
- Run the most focused pytest for changed behavior.
- Run ruff on changed Python files.

Output only:
- changed files
- tests run and pass/fail
- concise diff summary
- blockers or no-change reason
