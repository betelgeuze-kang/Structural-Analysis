# OpenCode worker slice: direct probe active HIP ack guard

## Goal
Audit and patch the direct residual Newton probe CLI guard so `--allow-cpu-diagnostic` is skipped only when an actually enabled lane is HIP-required.

## Scope
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`

## Required behavior
- `--enable-matrix-free-global-krylov` plus HIP backend plus `--matrix-free-global-krylov-require-hip-batch-replay` may run without `--allow-cpu-diagnostic`.
- `--enable-current-tangent-residual-row-correction` plus HIP backend plus `--current-tangent-residual-row-require-hip-batch-replay` may run without `--allow-cpu-diagnostic`.
- A HIP require flag for a disabled lane must not bypass `--allow-cpu-diagnostic`.
- If any enabled lane remains CPU diagnostic, `--allow-cpu-diagnostic` is still required.
- Do not weaken parser errors for `require_hip` with CPU backend.
- Do not claim G1 closure when HIP runtime is unavailable.

## Verification
Run:

```bash
python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py -k 'cpu_diagnostic or allow_cpu or require_hip'
```

Return only changed files, tests/results, and blockers.
