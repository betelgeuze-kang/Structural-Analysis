# Phase1 Remaining Work Report (2026-03-02)

## Current Gate Status
- Nightly release gate: `PASS`
- CI gate: `PASS`
- Static artifact validation: `PASS`
- Nonlinear frame validation: `PASS`
- Nonlinear pushover stress gate: `PASS`
- Nightly 10M reproducibility gate: `PASS`
- Pytest: `84 passed`

## P0 Remaining (Commercial Blockers)
1. Real solver fidelity gap
- Current core still mixes physical kernels with simplified/surrogate dynamics in several paths.
- Priority files:
  - `implementation/phase1/winning_ticket_backprop.py`
  - `implementation/phase1/physics_guided_branching.py`
  - `implementation/phase1/generate_track_dynamics_dataset.py`
  - `implementation/phase1/generate_tunnel_dynamics_dataset.py`
- Action:
  - Replace surrogate update loops with consistent force/Jacobian-based kernels.
  - Enforce no surrogate path in `ci-mode=nightly`.

2. Synthetic/virtual communication in scale-out stress
- Sync stress currently includes virtual communication estimation fields (`simulated_comm_gbps`).
- Priority files:
  - `implementation/phase1/virtual_partition_sync_emulator.py`
  - `implementation/phase1/run_sync_stress_gate.py`
- Action:
  - Add real single-GPU async halo scheduling benchmark (stream/event overlap) and make it the default gate path.

3. Real benchmark breadth
- Current open benchmark set is improved but still narrow versus production acceptance.
- Priority files:
  - `implementation/phase1/open_data/megastructure/README.md`
  - `implementation/phase1/build_cases_from_commercial_exports.py`
  - `implementation/phase1/run_megastructure_commercial_readiness.py`
- Action:
  - Expand fixed real-source suites (at least 3 independent families with shell-beam mix and measured dynamic targets).

4. Nonlinear coverage depth
- Pushover/NDTHA gates pass, but broader plastic/collapse pattern diversity is still limited.
- Priority files:
  - `implementation/phase1/run_nonlinear_pushover_stress.py`
  - `implementation/phase1/run_nonlinear_ndtha_stress.py`
- Action:
  - Add mandatory cases for soft-story, torsion-dominant asymmetry, and cyclic degradation.

## P1 Remaining (Reliability/Quality)
1. Runtime schema validation hardening at all solver ingress
- Some scripts validate input contracts, but not all execution paths enforce strict schema at entry.
- Action:
  - Standardize `validate_input_contract(...)` in every runner before compute starts.

2. Logging/observability consistency
- Structured logs and reason-code traces are present but not uniform across all modules.
- Action:
  - Normalize fields (`run_id`, `reason_code`, `gpu_strict`, `real_source`) across reports.

3. Workspace hygiene automation
- Artifact organization exists but can drift with ad-hoc runs.
- Action:
  - Add post-run organizer hook as default in nightly/pr commands.

## Next 5 Steps (Execution Order)
1. Remove surrogate dynamics in top-level training/eval paths and fail gate if detected.
2. Convert sync stress default from virtual emulator to real async stream/event benchmark.
3. Expand real-source benchmark suite and lock shell-beam-mix mandatory policy.
4. Increase nonlinear scenario set for collapse/plastic diversity and tighten thresholds.
5. Standardize strict schema+logging hooks across all phase1 runners.
