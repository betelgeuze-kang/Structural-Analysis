# Goal
Review the safe refresh path for the HIP-required residual/Jacobian consistency receipt so it records current-source blocked ROCm/HIP evidence without CPU fallback or G1 promotion.

# Scope
- Inspect only:
  - `implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py`
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `implementation/phase1/release_evidence/productization/mgt_residual_jacobian_consistency_hip_required_probe.json`
  - focused tests for these scripts
- Do not edit files.
- Do not run expensive Newton solves.
- Do not push, fetch, merge, or use network.

# Questions
1. Which command refreshes `mgt_residual_jacobian_consistency_hip_required_probe.json` in HIP-required mode?
2. If `/dev/kfd` and `/dev/dri` are missing, does that command avoid CPU fallback and keep the receipt non-promoting?
3. Which focused tests should be run after refreshing this receipt and the G1 lane wrapper?

# Output format
Use exactly these sections and no prose before the first heading:

## Changed files
None

## Test results
Not run

## Failed tests
None

## Core diff summary
- Answer the three questions briefly.

## Blockers
- Any blocker, or `None`.
