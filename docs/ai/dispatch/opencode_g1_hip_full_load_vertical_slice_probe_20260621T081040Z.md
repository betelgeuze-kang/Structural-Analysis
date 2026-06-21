# OpenCode task: G1 HIP full-load vertical-slice probe

## Goal
Find the smallest implementation change that moves the G1 full-load HIP Newton lane toward real closure without weakening blockers or promoting sub-full/reused evidence.

## Scope
- Inspect only:
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
  - `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
  - `tests/test_run_g1_full_load_hip_newton_lane.py`
  - related focused tests if directly needed
- Do not edit docs, README, PM ledgers, or release receipts.
- Do not synthesize HIP, customer, benchmark, CI, UX, or license evidence.
- Do not relax thresholds, remove blockers, or treat the 0.656 checkpoint as full G1 closure.

## Questions to answer
1. Is there a real child-probe field or CLI gap that prevents the wrapper from recognizing material Newton breadth, fallback-zero, HIP residual residency, or consistent Jacobian evidence when it is actually produced?
2. Is there a missing guard where the wrapper could accidentally promote a child probe that reports `fallback_zero_passed=True` but also includes nonzero fallback details?
3. Is there a small testable implementation improvement, preferably under 50 LOC, that tightens G1 claim boundaries or records actionable blocker detail?

## Verification
- Run only focused tests needed for the touched files.
- Report:
  - changed files
  - exact test commands and results
  - proposed or applied diff summary
  - blockers

## Output constraints
Keep the summary concise. Do not include full unified diffs.
