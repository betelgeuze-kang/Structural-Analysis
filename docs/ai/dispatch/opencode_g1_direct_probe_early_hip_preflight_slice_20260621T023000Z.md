# OpenCode slice: G1 direct probe early ROCm/HIP preflight

Goal:
Make `run_mgt_direct_residual_newton_probe.py` stop before any MGT parsing,
checkpoint load, child execution, or CPU residual/tangent assembly when a
HIP-required residual path is selected but the local ROCm/HIP runtime is not
available.

Scope:
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`

Context:
- The alternating G1 controller now has `--strict-hip-residual-engine` and
  preflights HIP before child launches.
- The adaptive global controller now returns a partial receipt with
  `stop_reason=hip_runtime_unavailable` before child launch when
  `--matrix-free-global-krylov-require-hip-batch-replay` is set and HIP is not
  available.
- The direct probe still checks MGT/checkpoint first and can enter expensive CPU
  assembly before discovering HIP is unavailable. For HIP-required G1 closure,
  this should be blocked early.

Implementation requirements:
- Add a small runtime preflight helper, or reuse an equivalent local helper, that
  checks torch importability, torch ROCm build (`torch.version.hip`), and
  `torch.cuda.is_available()`.
- In `run_mgt_direct_residual_newton_probe(...)`, before `mgt_path.is_file()`,
  `checkpoint_npz.is_file()`, `_load_checkpoint`, parser work, or assembly:
  - Normalize the global Krylov batch replay backend and linear solver backend.
  - If global HIP batch replay is required, auto-select `torch_hip_gmres` when
    the requested linear solver is still `scipy_host_gmres`.
  - Normalize the row residual batch replay backend.
  - If either enabled path requires HIP replay, or the global linear solver is
    `torch_hip_gmres`, run the HIP preflight.
  - If HIP is unavailable, write `output_json` if provided and return a partial
    receipt. The receipt must explicitly show:
    - `status=partial`
    - `direct_residual_newton_ready=false`
    - a ROCm/HIP preflight payload
    - no attempted global Krylov or row correction work
    - `gate_assessment.fallback_zero_passed=false`
    - blockers including `rocm_hip_runtime_unavailable` and
      `g1_fallback_zero_audit_not_closed`
    - no claim of G1 closure
- Do not change non-HIP CPU diagnostic behavior.
- Keep changes scoped; do not touch PM evidence, ledgers, or support bundles.

Verification:
- Add focused tests that monkeypatch the preflight helper unavailable and prove
  HIP-required direct probe returns before missing MGT/checkpoint can dominate.
- Add or preserve a focused test proving non-HIP default behavior still reports
  `mgt_missing` for a missing MGT path.
- Run:
  - `python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py`
  - `python3 -m py_compile implementation/phase1/run_mgt_direct_residual_newton_probe.py`

Output summary only:
- changed files
- test commands/results
- blockers, if any
