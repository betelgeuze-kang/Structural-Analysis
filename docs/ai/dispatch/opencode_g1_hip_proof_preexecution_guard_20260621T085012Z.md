# OpenCode slice: G1 HIP proof pre-execution guard

Goal: tighten `scripts/run_g1_full_load_hip_newton_lane.py` so a blocked or stale external HIP residual/Jacobian consistency proof blocks the lane before launching the child direct residual probe.

Scope:
- `scripts/run_g1_full_load_hip_newton_lane.py`
- `tests/test_run_g1_full_load_hip_newton_lane.py`

Expected behavior:
- If checkpoint/load-path blockers exist, keep existing blocked behavior and include HIP proof blockers.
- If checkpoint and load-path inputs are otherwise runnable but the HIP consistency proof has blockers, return `status=blocked`, `contract_pass=false`, `child_exit_code=null`, and do not call `subprocess.run`.
- `dry_run=True` should also report blocked when the HIP proof is blocked; it should only return `ready_to_run` when full-load input, load-path provenance, and HIP proof preflight all pass.
- Do not create new readiness claims or synthesize HIP/customer/external evidence.

Verification:
- Add focused pytest coverage proving blocked HIP proof does not execute the child probe.
- Run `python3 -m pytest tests/test_run_g1_full_load_hip_newton_lane.py -q`.
- Run ruff on touched Python files.
