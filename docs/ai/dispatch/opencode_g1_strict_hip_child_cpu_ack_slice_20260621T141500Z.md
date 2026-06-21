# OpenCode worker slice: G1 strict HIP child CPU ack removal

## Goal
Audit and patch the strict HIP child execution chain so HIP-required child controllers/direct probes do not require or receive `--allow-cpu-diagnostic` when the selected residual replay backend is HIP-only.

## Scope
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- matching focused tests

## Desired behavior
- Non-strict CPU diagnostic CLI runs still require `--allow-cpu-diagnostic`.
- HIP-required CLI runs may proceed without `--allow-cpu-diagnostic` after backend validation passes.
- Top-level strict alternating child commands should omit `--allow-cpu-diagnostic` when they invoke HIP-required row/global child controllers.
- Row/global child controllers should omit `--allow-cpu-diagnostic` when invoking direct probe with `--current-tangent-residual-row-require-hip-batch-replay` or `--matrix-free-global-krylov-require-hip-batch-replay`.
- Do not weaken existing fallback-zero or claim-boundary checks.
- Do not claim G1 closure when HIP runtime is unavailable.

## Verification
Run focused tests you touch, preferably:

```bash
python3 -m pytest -q \
  tests/test_mgt_g1_alternating_newton_controller.py \
  tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py \
  tests/test_mgt_shell_material_rowcorr_budget_controller.py \
  tests/test_mgt_direct_residual_newton_probe.py \
  -k 'cpu_diagnostic or allow_cpu or require_hip or strict_hip'
```

Return only changed files, tests/results, and blockers.
