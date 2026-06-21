# OpenCode slice: G1 full-load gate gap sweep

## Goal
Find the smallest local G1 strictness improvement that moves toward full-mesh/full-load nonlinear Newton closure without claiming closure.

## Scope
Read-only exploration only. Do not edit files.

Candidate files:
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/release_evidence/productization/mgt_g1_direct_residual_terminal_gate_report.json`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/commercialization-gap-current-state.md`

## Questions
1. Does the direct residual probe expose an explicit full-load closure gate, or only a checkpoint load-scale in metadata?
2. Could a future residual/increment pass at load_scale < 1.0 be misread as G1 closure?
3. What one small test-backed change would best prevent 0.656/reused evidence from being promoted to full G1?

## Output limit
Keep output under 2500 characters.

## Output format
- gaps: up to 3 bullets
- recommended_fix: one bullet
- commands: one line

Do not include long logs or file listings.
