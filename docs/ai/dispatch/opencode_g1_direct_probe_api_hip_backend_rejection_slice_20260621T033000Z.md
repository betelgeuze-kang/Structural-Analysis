# OpenCode slice: G1 direct probe API HIP backend rejection

Goal:
Make the direct residual Newton probe Python API reject HIP-required residual
paths when the selected batch replay backend is CPU, matching the CLI behavior.

Scope:
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`

Context:
- CLI parsing already rejects:
  - `--matrix-free-global-krylov-require-hip-batch-replay` with backend `cpu`
  - `--current-tangent-residual-row-require-hip-batch-replay` with backend `cpu`
- The Python function currently normalizes backends and can silently lower the
  effective HIP-required flag to false if called directly with a CPU backend.
- Strict G1/HIP orchestration should not allow that silent downgrade.

Implementation requirements:
- In `run_mgt_direct_residual_newton_probe(...)`, before any MGT/checkpoint work:
  - if `matrix_free_global_krylov_require_hip_batch_replay=True` and the normalized
    global batch replay backend is `cpu`, raise `ValueError` with a clear message.
  - if `current_tangent_residual_row_require_hip_batch_replay=True` and the
    normalized row batch replay backend is `cpu`, raise `ValueError` with a clear
    message.
- Preserve the existing early ROCm/HIP runtime preflight for valid HIP backends.
- Preserve non-HIP CPU diagnostic behavior when no HIP-required flag is set.
- Do not touch PM evidence, ledgers, or support bundles.

Verification:
- Add tests for both Python API rejection paths.
- Run:
  - `python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py`
  - `python3 -m py_compile implementation/phase1/run_mgt_direct_residual_newton_probe.py`

Output summary only:
- changed files
- test commands/results
- blockers, if any
