# OpenCode Worker Slice: HIP Proof No-CPU Structured Guard

Goal: review whether the canonical product readiness snapshot should require explicit structured no-CPU evidence from the G1 HIP consistency proof.

Scope:
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- `scripts/build_product_readiness_snapshot.py`
- `tests/test_mgt_residual_jacobian_consistency_probe.py`
- `tests/test_build_product_readiness_snapshot.py`

Questions:
- Should HIP-required receipts include `cpu_diagnostic_assembler_used=false` and a HIP proof execution-mode field?
- Should `build_product_readiness_snapshot.py` reject otherwise green HIP consistency proof summaries when that no-CPU field is missing or true?

Constraints:
- Do not edit files.
- Do not claim G1 closure.
- Keep output limited to candidate files/tests/blockers.
