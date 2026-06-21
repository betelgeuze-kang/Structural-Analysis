# OpenCode worker slice: G1 nested closure evidence aggregation

## Goal
Audit and patch the G1 alternating Newton controller closure assessment so it can use authoritative nested direct-probe evidence from accepted child controller rows.

## Scope
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

## Context
The alternating controller launches row/global child controllers, not always a direct probe. Those child controllers may store direct-probe evidence in accepted rows as:
- `child_gate_assessment`
- `child_residual_contract`
- `child_receipt_path`

Current top-level `g1_closure_assessment` must not require those fields to be duplicated at the child controller top level if an accepted nested direct-probe row has the authoritative evidence.

## Required behavior
- Still never claim closure without strict HIP mode and available HIP preflight.
- Still require strict fallback-zero audit to pass recursively.
- Closure evidence may come from either:
  - top-level child payload `gate_assessment` + `residual_contract`, or
  - an accepted nested row's `child_gate_assessment` + `child_residual_contract`.
- If multiple accepted nested rows exist, use the latest accepted row that has both gate and residual contract evidence.
- Keep `evidence_child_receipt_path`; add an evidence location/path if useful.
- Do not accept frozen-only material tangent replay as material Newton closure.
- Do not treat host shell CSR/operator refresh as production residency closure.
- Do not edit PM receipts/ledgers.

## Verification
Run:

```bash
python3 -m pytest -q tests/test_mgt_g1_alternating_newton_controller.py -k 'closure or nested or state_dependent or strict_hip'
```

Return only changed files, tests/results, and blockers.
