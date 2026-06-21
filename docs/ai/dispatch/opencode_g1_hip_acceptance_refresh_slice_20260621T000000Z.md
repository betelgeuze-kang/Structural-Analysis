Goal: Move the G1 matrix-free global Krylov accepted-state residual refresh closer to the ROCm/HIP path without overstating closure.

Scope: Inspect and, if straightforward, implement a narrow change in the direct residual probe so that when --matrix-free-global-krylov-require-hip-batch-replay is active and a global Krylov candidate is promoted, the accepted current_residual/current_rhs/current_free can be refreshed from the already evaluated HIP residual replay result instead of a CPU full assembly refresh. Preserve claim boundaries: if tangent/stiffness refresh is still CPU or stale, record that explicitly and do not mark direct_residual_newton_ready unless all existing gates and fallback blockers are clear. Do not edit release evidence, ledgers, or unrelated files.

Candidate files: implementation/phase1/run_mgt_direct_residual_newton_probe.py, tests/test_mgt_direct_residual_newton_probe.py.

Verification criteria: python3 -m py_compile implementation/phase1/run_mgt_direct_residual_newton_probe.py; python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py. Worker summary must list changed files, test results, failed tests if any, core diff summary, and blockers.
