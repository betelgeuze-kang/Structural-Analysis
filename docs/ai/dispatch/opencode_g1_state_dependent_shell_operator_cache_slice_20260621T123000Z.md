# OpenCode worker slice: G1 state-dependent shell operator cache audit

## Goal
Audit and, only if needed, patch the strict HIP direct residual Newton state-dependent shell-material replay path so candidate-state material tangents cannot be masked by shell operator cache reuse.

## Scope
- `implementation/phase1/mgt_shell_force_based_assembly.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`

## Context
- The product goal requires G1 consistent Newton closure using ROCm-HIP residual evaluation, not CPU fallback.
- Current environment may not have a visible HIP device; do not claim G1 closure from local runs.
- `_cached_shell_operator` appears to disable cache read/write when `material_tangent_by_surface_index_mpa` is present. Verify this remains true for the global and row state-dependent HIP replay paths in `run_mgt_direct_residual_newton_probe.py`.
- Frozen tangent replay is allowed only as a non-closure diagnostic. State-dependent shell-material replay must keep host shell CSR refresh boundary visible and must not imply full production ROCm-HIP residency.

## Tasks
1. Inspect whether state-dependent global and row replay paths pass candidate `u` and candidate `material_tangent_by_surface_index_mpa` into `_cached_shell_operator`.
2. Confirm cache reuse cannot return stale shell operators when material tangent override is present.
3. Add focused tests only if the current tests do not already prove this.
4. Do not edit product readiness receipts or ledgers.

## Verification
Run the narrow tests you changed, preferably:

```bash
python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py -k 'state_dependent or shell_material'
```

Return only:
- changed files
- test commands/results
- whether a patch was needed
- any blocker
