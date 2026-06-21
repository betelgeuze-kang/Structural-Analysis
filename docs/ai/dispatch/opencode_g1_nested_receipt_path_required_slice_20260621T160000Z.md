# OpenCode worker slice: nested closure evidence must have child receipt path

## Goal
Audit and patch G1 alternating closure assessment so nested row evidence is used only when the accepted row has an authoritative `child_receipt_path` for the direct-probe receipt.

## Scope
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

## Required behavior
- Top-level child payload `gate_assessment` + `residual_contract` remains valid evidence.
- Nested evidence from accepted rows requires all three:
  - `child_gate_assessment` dict
  - `child_residual_contract` dict
  - non-empty `child_receipt_path`
- Prefer latest accepted nested row with all required evidence.
- If `child_gate_assessment`/`child_residual_contract` exist but `child_receipt_path` is missing, do not claim closure; record a blocker or evidence gap if useful.
- Preserve recursive strict fallback-zero audit behavior.
- Do not accept frozen-only material tangent replay as material Newton closure.
- Do not edit PM receipts/ledgers.

## Verification
Run:

```bash
python3 -m pytest -q tests/test_mgt_g1_alternating_newton_controller.py -k 'closure or nested or evidence or strict_hip'
```

Return only changed files, tests/results, and blockers.
