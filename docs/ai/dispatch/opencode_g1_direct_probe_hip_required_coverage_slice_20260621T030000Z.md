# OpenCode slice: G1 direct probe HIP-required coverage hardening

Goal:
Harden tests for the direct residual Newton probe early ROCm/HIP preflight so
all HIP-required entry paths stop before MGT parsing, checkpoint loading, child
execution, or CPU residual/tangent assembly when the local HIP runtime is not
available.

Scope:
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`

Context:
- The direct probe now has `_rocm_hip_runtime_preflight()` and returns a
  `status=partial` receipt with `rocm_hip_runtime_unavailable` before file checks
  when global HIP replay is required.
- Existing focused coverage proves global HIP batch replay stops before missing
  MGT/checkpoint dominate.
- G1 strict closure needs the same early boundary for:
  - explicit `matrix_free_global_krylov_linear_solver_backend="torch_hip_gmres"`
  - current-tangent residual row correction with HIP batch replay required

Implementation requirements:
- Add focused tests that monkeypatch `_rocm_hip_runtime_preflight` unavailable.
- Prove explicit `torch_hip_gmres` with `enable_matrix_free_global_krylov=True`
  returns the same early partial receipt even if batch replay is not required.
- Prove `enable_current_tangent_residual_row_correction=True` plus
  `current_tangent_residual_row_batch_replay_backend="hip_full_residual"` and
  `current_tangent_residual_row_require_hip_batch_replay=True` returns the same
  early partial receipt before missing MGT/checkpoint.
- Ensure these tests assert no `mgt_missing` or `checkpoint_missing` blocker in
  the HIP-unavailable early receipt.
- If implementation gaps are found, patch only the direct probe to satisfy these
  boundaries. Do not edit PM evidence, ledgers, or support bundle files.

Verification:
- `python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py`
- `python3 -m py_compile implementation/phase1/run_mgt_direct_residual_newton_probe.py`

Output summary only:
- changed files
- test commands/results
- blockers, if any
