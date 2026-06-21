# OpenCode worker slice: G1 alternating strict closure aggregation

## Goal
Audit and patch, only if needed, the G1 alternating Newton controller so a strict HIP run can produce a top-level closure assessment only when authoritative child receipts prove all G1 exit gates:

- full-load direct residual gate passed
- relative increment gate verified and passed
- material Newton path is state-dependent shell-material tangent replay, not frozen-only replay
- fallback-zero audit passed with no CPU/fallback boundary

## Scope
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

## Constraints
- Do not edit PM release ledgers or productization receipts.
- Do not claim G1 closure when HIP runtime is unavailable.
- Do not weaken existing strict claim-boundary or fallback-zero tests.
- Frozen shell-material tangent replay must remain non-closure.
- Host shell CSR/operator refresh boundary for state-dependent replay must remain visible and must not be treated as full production ROCm-HIP residency.

## Expected Shape
If missing, add a focused helper and receipt fields such as `gate_assessment` or `g1_closure_assessment` at the alternating controller top level. It should report `g1_closure_claimed=false` unless all strict child evidence above is true. If true in a mocked test, top-level `status` may become `passed`; otherwise keep `partial`.

## Verification
Run:

```bash
python3 -m pytest -q tests/test_mgt_g1_alternating_newton_controller.py -k 'closure or strict_hip or fallback_zero or state_dependent'
```

Return only:
- changed files
- test commands/results
- core decision logic
- blockers
