# OpenCode slice: G1 adaptive global controller HIP API hardening

Goal:
Make `run_mgt_direct_residual_adaptive_preconditioned_global_newton.py` enforce
the same HIP-required boundaries in its Python API that the CLI already enforces,
and preflight explicit `torch_hip_gmres` before launching child probes.

Scope:
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py`

Context:
- Direct probe now rejects Python API calls where a HIP-required residual path
  uses backend `cpu`.
- Adaptive controller CLI already returns code 2 for
  `--matrix-free-global-krylov-require-hip-batch-replay` with backend `cpu`.
- The Python API should not silently launch or downgrade that invalid state.
- The controller already has `_collect_hip_preflight()` and partial receipt logic
  for `matrix_free_global_krylov_require_hip_batch_replay=True`.

Implementation requirements:
- Early in `run_adaptive_preconditioned_global_newton(...)`, normalize
  `matrix_free_global_krylov_batch_replay_backend`.
- If `matrix_free_global_krylov_require_hip_batch_replay=True` and normalized
  backend is `cpu`, raise `ValueError` with a clear message.
- Treat explicit `matrix_free_global_krylov_linear_solver_backend="torch_hip_gmres"`
  as a HIP-runtime-required path for controller preflight even when batch replay
  is not required.
- If HIP preflight fails for either HIP batch replay required or explicit
  `torch_hip_gmres`, return the existing partial receipt shape before child launch.
- Preserve non-HIP CPU diagnostic behavior.
- Do not edit PM evidence, ledgers, or support bundles.

Verification:
- Add tests:
  - Python API rejects HIP-required global CPU backend.
  - explicit `torch_hip_gmres` with HIP unavailable returns partial receipt with
    `attempted=false`, rows empty, no child launch.
- Run:
  - `python3 -m pytest -q tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
  - `python3 -m py_compile implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`

Output summary only:
- changed files
- test commands/results
- blockers, if any
