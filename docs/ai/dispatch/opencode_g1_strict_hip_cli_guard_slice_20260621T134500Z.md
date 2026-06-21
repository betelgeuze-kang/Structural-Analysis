# OpenCode worker slice: G1 strict HIP CLI guard

## Goal
Audit the G1 alternating Newton controller CLI guard. In strict HIP residual-engine mode, the CLI should not require `--allow-cpu-diagnostic` after the row/global HIP backend requirements have passed. Non-strict diagnostic runs should still require the explicit CPU diagnostic acknowledgment.

## Scope
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

## Constraints
- Do not weaken HIP backend validation.
- Do not allow strict HIP mode with CPU row/global replay backends.
- Do not change child commands to CPU fallback.
- Do not edit productization receipts or PM ledgers.
- Do not claim G1 closure when HIP runtime is unavailable.

## Verification
Run:

```bash
python3 -m pytest -q tests/test_mgt_g1_alternating_newton_controller.py -k 'cli or cpu_diagnostic or strict_hip'
```

Return only changed files, test results, and any blocker.
