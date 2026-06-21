# OpenCode slice: fresh validation lane probe

Goal: Identify the smallest honest fresh full-validation lane that can be run locally without synthesizing external/customer/UX/license/CI evidence.

Scope:
- Inspect only these files unless clearly needed:
  - `scripts/build_fresh_validation_receipt.py`
  - `scripts/build_fresh_full_validation_lane_status.py`
  - `implementation/phase1/run_design_optimization_solver_loop_long.py`
  - `implementation/phase1/run_midas_exact_roundtrip_closure_gate.py`
  - `implementation/phase1/run_performance_profiling_gate.py`
  - related artifact path constants imported by those scripts
- Do not edit files.
- Do not create fresh receipts.
- Do not run long/heavy commands. `--help` or short static inspection is fine.

Questions to answer:
1. Which lane is the safest first local fresh receipt candidate?
2. What exact validation command should Codex run?
3. Which real input path(s) and receipt artifact path(s) should the receipt builder record?
4. What claim-boundary risk remains?

Verification criteria:
- Candidate must use a registered runner command prefix from `build_fresh_validation_receipt.py`.
- Candidate must not claim external benchmark submission, customer shadow completion, human UX observation, license approval, CI streak, or full G1 closure.
- Summary must include only changed files (expected: none), proposed command, proposed receipt builder invocation, and blockers/risks.
