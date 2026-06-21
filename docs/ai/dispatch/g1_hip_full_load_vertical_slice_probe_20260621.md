# G1 HIP full-load vertical slice probe

Goal: identify the smallest code/test slice that moves G1 toward full-load ROCm/HIP Newton closure without claiming full G1 readiness.

Scope:
- `scripts/run_g1_full_load_hip_newton_lane.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
- `implementation/phase1/release_evidence/productization/g1_checkpoint_retention_manifest.json`
- existing G1 evidence JSONs under `implementation/phase1/release_evidence/productization/`
- tests under `tests/test_run_g1_full_load_hip_newton_lane.py` and any direct probe tests

Constraints:
- Do not edit files.
- Do not promote the 0.656 checkpoint to full-load closure.
- Do not synthesize receipts or mark blockers closed.
- Prefer ROCm/HIP residual residency and material Newton/Jacobian consistency checks.

Deliverable:
- List 1-2 feasible local code slices, candidate files, exact blockers they reduce or make more honest, and focused tests.
- Keep output concise and only use changed-file/test/blocker terminology.
