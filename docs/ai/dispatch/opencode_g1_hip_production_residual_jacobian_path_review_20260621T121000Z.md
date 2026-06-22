# OpenCode Worker Slice: G1 HIP Production Residual/Jacobian Path Review

Goal: find the smallest implementable, non-promoting step toward a production ROCm/HIP residual-Jacobian consistency proof in `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`.

Scope:
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- existing HIP residual/replay helpers in `implementation/phase1/` and `scripts/`
- `tests/test_mgt_residual_jacobian_consistency_probe.py`
- `tests/test_run_g1_full_load_hip_newton_lane.py` only if proof-intake fields change

Questions:
- Is there an existing HIP full residual replay backend or torch HIP helper that can be reused without CPU fallback?
- What is the smallest new function/flag/contract that proves a production HIP residual/Jacobian path is wired, while still blocking when `/dev/kfd` or `/dev/dri` are unavailable?
- Which fields should the receipt expose so `product_readiness_snapshot` can distinguish “runtime unavailable” from “HIP proof path implemented but not yet G1-closed”?
- What focused tests should cover the new path without claiming full G1 closure?

Constraints:
- Do not edit files.
- Do not mark full-load/full-mesh G1, material Newton breadth, customer evidence, fresh validation, or EB receipts closed.
- Do not allow CPU diagnostic assembler fallback when `--require-hip-residual-engine` is set.
- Prefer a small vertical slice over broad solver refactors.

Deliverable:
- Candidate implementation files/functions.
- Candidate test names/assertions.
- Expected receipt fields/blockers.
- Any blocker that cannot be solved without a real ROCm/HIP runtime.
