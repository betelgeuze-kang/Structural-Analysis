# OpenCode Worker Slice: G1 Frozen Shell-Material HIP Replay Flag Propagation

## Goal

Propagate the existing `allow_frozen_shell_material_tangent_hip_replay` control from lower G1 residual probes into the higher G1 orchestration controllers without promoting frozen replay as full material Newton closure.

## Scope

- Add a default-false `allow_frozen_shell_material_tangent_hip_replay` parameter/CLI flag to:
  - `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
  - `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- When enabled with shell material tangent replay, forward `--allow-frozen-shell-material-tangent-hip-replay` to child commands:
  - adaptive global -> direct residual probe
  - alternating row lane -> shell material rowcorr controller
  - alternating global lane -> adaptive global controller
- Record the flag in controller JSON/launch/timeout receipts where the surrounding controller already records related HIP/material-tangent settings.
- Preserve claim boundaries: frozen shell-material tangent HIP replay must remain explicitly non-closure for state-dependent material Newton and must not satisfy strict G1 closure by itself.

## Candidate Files

- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

## Verification Criteria

- Focused tests cover:
  - adaptive child command includes the frozen replay flag only when enabled.
  - adaptive controller payload records the flag.
  - alternating row/global child commands include the flag when enabled.
  - alternating controller payload records the flag.
  - strict G1 child audit still blocks receipts whose claim boundary says frozen replay is not material Newton closure.
- Run:
  - `python3 -m py_compile implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
  - `python3 -m pytest -q tests/test_mgt_direct_residual_adaptive_preconditioned_global_newton.py tests/test_mgt_g1_alternating_newton_controller.py`

## Boundaries

- Do not edit PM release evidence, ledgers, support bundle, billing, GitHub state, or deployment/release artifacts.
- Do not mark G1 as closed.
- Do not introduce CPU fallback claims for HIP-required residual replay.
