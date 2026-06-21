Goal: Tighten G1 closure assessment so full residual/increment/material Newton closure requires authoritative child evidence that the residual engine was ROCm/HIP, not just gate booleans copied into a receipt.

Scope: Inspect and, if needed, update only G1 controller/direct-probe contract code and tests. Do not edit PM reports, release ledgers, environment files, or unrelated solvers. Do not claim G1 closure in docs or receipts.

Candidate files:
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

Verification criteria:
- G1 closure assessment must require child receipt `residual_contract` evidence that the full residual path used a HIP backend (`hip_full_residual`, `hip_full_residual_resident`, or `rust_hip_full_residual_ffi`) for enabled residual replay lanes.
- CPU diagnostic evidence or missing residual-engine contract must keep `g1_closure_claimed=false`, even if direct residual/increment/material gate booleans are true.
- Existing strict HIP preflight-unavailable behavior remains partial with no child launch.
- Run focused G1 closure/direct-probe tests and report exact command results.
- Worker summary only: changed files, test results, failed test names, core diff summary, blockers.
