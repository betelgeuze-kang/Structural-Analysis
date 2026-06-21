Goal: Add a G1 direct-residual fallback-zero audit that aggregates hidden CPU/host fallback boundaries into one receipt field and gates direct_residual_newton_ready on that audit.

Scope: Work only in implementation/phase1/run_mgt_direct_residual_newton_probe.py and tests/test_mgt_direct_residual_newton_probe.py. Preserve existing claim boundaries and partial/blocker behavior. Add a small helper if useful. The audit should mark fallback_zero_passed false when a promoted or attempted HIP-required global Krylov path used host GMRES, required HIP replay was unavailable, CPU linear fallback was suppressed, CPU residual/acceptance refresh was used, CPU tangent refresh was used, or row HIP replay required/unavailable. Do not edit release evidence, ledgers, status JSON, support bundles, or unrelated files.

Candidate files: implementation/phase1/run_mgt_direct_residual_newton_probe.py, tests/test_mgt_direct_residual_newton_probe.py.

Verification criteria: Run python3 -m py_compile implementation/phase1/run_mgt_direct_residual_newton_probe.py and python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py. Worker output must be a concise summary only: changed files, test results, failed tests if any, core diff summary, blockers. Do not include unified diffs, patch hunks, raw file dumps, secrets, or long logs.
