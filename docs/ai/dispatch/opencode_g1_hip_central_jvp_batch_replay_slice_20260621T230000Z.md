# OpenCode Worker Slice: G1 HIP Central JVP Batch Replay

Goal:
- Improve the actual G1 HIP residual/JVP path by batching central-difference `+/-` matvec probes through the HIP full-residual backend when the operator is not state-dependent.

Scope:
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`

Expected direction:
- Reuse the existing `_evaluate_global_residual_candidates` helper.
- For `matrix_free_global_krylov_difference_scheme=central`, evaluate `+direction` and `-direction` in one HIP batch when `matrix_free_global_krylov_require_hip_batch_replay=True` and the residual backend is HIP.
- Preserve state-dependent shell-material behavior: candidate-state material tangent refresh may still require per-state backend preparation.
- Expose receipt metadata showing the JVP probe pair was batch replayed, without claiming G1 closure.

Constraints:
- Do not weaken fallback-zero or HIP residual engine contracts.
- Do not promote CPU-diagnostic evidence.
- Prefer focused tests with the existing mock HIP backend and mock HIP GMRES.

Verification:
- Focused direct-probe tests for central JVP batch replay.
- G1/HIP focused suite if changes are nontrivial.

Output summary only:
- Changed files.
- Tests run.
- Blockers.
