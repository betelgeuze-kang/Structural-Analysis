# OpenCode worker slice: G1 top-level strict HIP boundary

Goal:
- Review the top-level G1 alternating controller strict-HIP unavailable path after the fresh `followup400` run.
- Keep the boundary aligned with the child rowcorr receipt: no CPU fallback, no G1 closure, explicit ROCm/HIP runtime unavailable.

Scope:
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`
- `implementation/phase1/release_evidence/productization/mgt_g1_followup400_strict_hip_target_rows_alternating_smoke.json`
- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup399_target_rows_strict_hip_smoke.json`

Work requested:
- Check whether the current G1 claim boundary and closure assessment expose `rocm_hip_runtime_available=false` clearly when strict HIP preflight fails.
- If a small code/test fix is needed, implement it.
- Do not edit PM release reports or ledgers.
- Do not claim G1 closure.

Verification criteria:
- Report changed files only.
- Report exact tests run and failed test names if any.
- Summarize the remaining blocker in strict HIP terms.
