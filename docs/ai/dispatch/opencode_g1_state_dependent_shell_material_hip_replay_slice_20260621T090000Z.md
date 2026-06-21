# OpenCode Worker Slice: G1 State-Dependent Shell-Material HIP Residual Replay

## Goal

Move G1 residual replay beyond frozen shell-material tangent HIP replay by adding an explicit state-dependent shell-material tangent HIP replay path. Residual evaluation must stay on the configured HIP full-residual backend when HIP is required; do not fall back to CPU residual replay.

## Background

Current direct probe behavior:

- `apply_shell_material_tangent=True` with HIP batch replay is blocked unless `allow_frozen_shell_material_tangent_hip_replay=True`.
- The frozen path computes shell material tangent at the current accepted state, builds one shell CSR, and reuses it for candidate residual replay.
- That avoids CPU residual fallback, but it is intentionally not state-dependent material Newton closure.

The next useful implementation is a candidate-state refresh mode:

- For each candidate state requiring shell material tangent, compute the shell material tangent from that candidate state.
- Build the candidate shell CSR from that tangent.
- Evaluate that candidate residual through the selected HIP backend (`hip_full_residual`, `hip_full_residual_resident`, or `rust_hip_full_residual_ffi`).
- If HIP is required and candidate-specific HIP prepare/evaluate fails, record `hip_batch_replay_required_unavailable` and suppress CPU fallback.

## Scope

- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `tests/test_mgt_direct_residual_newton_probe.py`
- Update upper controllers only if a new CLI/API flag must be propagated:
  - `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
  - `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
  - `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
  - corresponding focused tests

## Suggested API

Add a default-false flag such as:

- Python parameter: `allow_state_dependent_shell_material_tangent_hip_replay`
- CLI: `--allow-state-dependent-shell-material-tangent-hip-replay`

Semantics:

- When `apply_shell_material_tangent=True` and a HIP backend is selected:
  - state-dependent flag wins over frozen flag.
  - frozen flag remains available as the cheaper non-closing path.
  - if neither flag is enabled, keep the existing blocked/disabled reason.
- Receipts should clearly distinguish:
  - `state_dependent_shell_material_tangent_hip_replay=True`
  - `state_dependent_shell_material_tangent_operator_refresh_backend="host_shell_operator_refresh"`
  - residual evaluation backend remains HIP.
- Claim boundary must not say full commercial ROCm/HIP residency is closed if shell CSR/operator refresh still happens on host. It may say this is state-dependent material tangent HIP residual replay but not full production residency closure.

## Implementation Notes

- Prefer small helpers inside the direct probe to avoid duplicating global and row HIP code.
- For row batch candidate replay, candidate-specific material tangent means a single reusable backend may not be valid for the whole batch. It is acceptable for this slice to evaluate candidates one-by-one through candidate-specific HIP backends, as long as HIP-required mode suppresses CPU fallback on prepare/evaluate failure.
- Preserve the existing frozen path and tests.
- Do not edit PM release evidence or promote G1 status.

## Verification Criteria

- Add tests proving:
  - state-dependent flag suppresses the frozen-disabled reason for shell material tangent HIP replay.
  - state-dependent path computes shell material tangent using the candidate state, not the current accepted/base state.
  - HIP-required state-dependent prepare/evaluate failure records unavailable and suppresses CPU fallback.
  - frozen path remains explicitly non-closure.
  - claim boundary remains conservative for host operator refresh / production residency.
- Run focused tests:
  - `python3 -m py_compile implementation/phase1/run_mgt_direct_residual_newton_probe.py`
  - `python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py`

## Boundaries

- Do not claim representative full-mesh G1 PASS.
- Do not replace HIP residual evaluation with CPU residual replay in HIP-required mode.
- Do not touch billing, GitHub remote state, deployment, release publication, or external benchmark submission.
