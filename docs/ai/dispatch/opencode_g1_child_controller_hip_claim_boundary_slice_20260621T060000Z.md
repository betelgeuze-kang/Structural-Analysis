# OpenCode Worker Slice: G1 child controller HIP claim-boundary hardening

Goal:
Tighten G1 ROCm/HIP residual-engine orchestration so strict HIP alternating Newton can distinguish a child controller that actually required HIP replay from a CPU-diagnostic controller receipt. Do not claim G1 closure.

Scope:
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- Matching focused tests:
  - `tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
  - `tests/test_mgt_shell_material_rowcorr_budget_controller.py`
  - `tests/test_mgt_g1_alternating_newton_controller.py` only if needed

Current issue:
- The strict alternating controller now rejects child receipts whose `claim_boundary` says `cpu_diagnostic_only=true` or `official_rocm_hip_closure_required=true`.
- Adaptive global and shell material rowcorr controllers always emit those claim-boundary flags, even when their configuration requires HIP replay and suppresses CPU fallback.
- This can make strict HIP promotion structurally impossible even for a child receipt whose direct child evidence has `gate_assessment.fallback_zero_passed=true`.

Required behavior:
- Keep default/non-HIP controller receipts conservative: `cpu_diagnostic_only=true`, `official_rocm_hip_closure_required=true`.
- Keep timeout, preflight-blocked, missing child evidence, or CPU fallback boundary cases conservative.
- For HIP-required controller runs, only allow the controller-level `claim_boundary` to set `cpu_diagnostic_only=false` and `official_rocm_hip_closure_required=false` when:
  - the configured backend is a HIP residual replay backend,
  - the HIP required flag is true,
  - HIP runtime/preflight is available if that controller has a preflight,
  - no controller preflight blockers exist,
  - at least one accepted/promoted child receipt exists,
  - every accepted/promoted child receipt has `gate_assessment.fallback_zero_passed=true`,
  - no accepted/promoted child receipt has CPU/host/fallback/hip-required blockers or claim-boundary flags that strict alternating would reject.
- Add a small helper if useful to avoid duplicating child audit logic, but keep the change narrow.
- Do not alter evidence JSON in `implementation/phase1/release_evidence/productization/` during this slice.

Verification criteria:
- Focused unit tests prove:
  - HIP-required adaptive global controller with accepted child fallback-zero pass emits non-CPU/non-pending-HIP claim boundary.
  - adaptive global controller keeps conservative claim boundary on timeout or child fallback-zero fail.
  - shell rowcorr controller keeps conservative claim boundary while its current HIP material-tangent preflight blocker exists.
  - if shell rowcorr has a simulated no-preflight-blocker HIP-required accepted child with fallback-zero pass, its controller claim boundary can become non-CPU/non-pending-HIP.
  - strict alternating controller can accept a nested controller receipt with the non-CPU/non-pending-HIP claim boundary and fallback-zero pass.
- Run:
  - `python3 -m pytest -q tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py tests/test_mgt_shell_material_rowcorr_budget_controller.py tests/test_mgt_g1_alternating_newton_controller.py`

Output:
- Concise summary only: changed files, tests run, failures/blockers.
- Do not include full unified diffs in the worker response.
