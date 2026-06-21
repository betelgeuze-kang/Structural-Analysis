# OpenCode Worker Slice: G1 Budgeted Controllers HIP Contract Promotion Guard

Goal:
- Audit the G1 budgeted continuation controllers so a child direct-residual receipt cannot promote a frontier under HIP-required mode unless the child `residual_contract.hip_residual_engine_contract_passed` is true.

Scope:
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- Focused tests in:
  - `tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
  - `tests/test_mgt_shell_material_rowcorr_budget_controller.py`

Candidate checks:
- Adaptive global controller currently promotes based on relative improvement and accepted components. Verify whether it also blocks promotion when `matrix_free_global_krylov_require_hip_batch_replay=True` and the child residual contract is missing/false.
- Shell material row-correction budget controller currently promotes based on row correction acceptance and frontier improvement. Verify whether it also blocks promotion when `row_require_hip_batch_replay=True` and the child residual contract is missing/false.
- Preserve CPU-diagnostic mode behavior when HIP is not required.
- Do not promote docs/status claims. Keep G1 partial unless real full-load/full-mesh HIP evidence exists.

Expected implementation direction:
- Add small helper(s) to extract and require child HIP residual engine contract only in HIP-required lanes.
- Annotate controller rows with `child_hip_residual_engine_contract_passed` and a clear non-promotion reason/blocker when blocked.
- Add focused tests using monkeypatched child receipts, not long solver runs.

Verification:
- Run the two focused test modules or targeted `-k hip`.
- Run `py_compile` on the two controller scripts.

Output summary only:
- Changed files.
- Tests run.
- Any blockers.
