# Goal
Diagnose the current Phase 3 benchmark factory clean-checkout/git-clean-clone stable checksum mismatch.

# Scope
- Inspect only:
  - `scripts/build_phase3_benchmark_factory_artifacts.py`
  - `scripts/build_phase3_benchmark_acquisition_artifacts.py`
  - `scripts/build_phase3_opensees_source_license_receipt.py`
  - `scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py`
  - `scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py`
  - Phase3 generated JSON artifacts under `implementation/phase1/release_evidence/productization/phase3_*`
- Do not edit files unless a one-line or very small deterministic fix is clearly required.
- Do not read `.env*`.
- Do not run destructive git commands, push, merge, deploy, or mutate remote state.

# Verification Criteria
- Identify whether regenerating local Phase3 artifacts with explicit `--source-commit-sha $(git rev-parse HEAD)` should make the clean-checkout checksum comparison pass.
- If it should not, identify the smallest script-level mismatch.
- Run only focused Phase3 commands/tests needed to prove the diagnosis.

# Output
Return only:
- Changed files
- Test results
- Failed tests
- Core diff summary
- Blockers
