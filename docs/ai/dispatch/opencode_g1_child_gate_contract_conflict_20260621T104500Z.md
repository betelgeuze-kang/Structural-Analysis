# Goal
Review the G1 full-load HIP Newton lane for the smallest guard that prevents child `residual_contract` booleans from overriding contradictory `gate_assessment` evidence.

# Scope
- Inspect only:
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `tests/test_run_g1_full_load_hip_newton_lane.py`
  - `implementation/phase1/run_mgt_direct_residual_newton_probe.py` only if needed to confirm field semantics
- Do not edit files.
- Do not run broad tests.
- Do not touch evidence JSON.
- Do not push, fetch, merge, or use network.

# Questions
1. Should lane promotion require `gate_assessment.consistent_residual_jacobian_newton_passed is True` instead of accepting only `residual_contract.consistent_residual_jacobian_newton_gate_passed`?
2. Should lane promotion require `gate_assessment.material_newton_breadth_passed is True` instead of accepting only residual contract material flags?
3. Which blocker names and focused tests best fit the existing style?

# Output
Return only:
- recommended code location
- exact blocker names
- focused tests to add or adjust
- risk notes
