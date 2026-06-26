Goal: Add a Phase 4 commercial operator reference output contract artifact without promoting readiness.

Scope:
- Add a builder script and focused tests for an operator reference output package contract.
- The artifact must stay blocked until real operator files, permission, SHA256 checksums, and two independent reference solver outputs are attached.
- Connect the new artifact to Phase 3 acquisition, Developer Preview dataset/license manifest, benchmark factory reproducibility bundle, clean-checkout/git-clean-clone reproduction contracts, and cleanup plan expectations.

Candidate files:
- scripts/build_phase4_commercial_operator_reference_contract.py
- tests/test_build_phase4_commercial_operator_reference_contract.py
- src/structural_analysis/benchmark/acquisition.py
- scripts/build_phase3_benchmark_acquisition_artifacts.py
- scripts/build_developer_preview_readiness.py
- scripts/build_phase3_benchmark_factory_artifacts.py
- scripts/phase3_benchmark_reproduction_contract.py
- scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py
- scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py
- tests/test_build_phase3_benchmark_acquisition_artifacts.py
- tests/test_build_developer_preview_readiness.py
- tests/test_build_phase3_benchmark_factory_artifacts.py
- tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py
- tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py
- tests/test_build_phase3_release_control_cleanup_plan.py

Verification criteria:
- The new artifact has schema version, source commit, input checksums, required package fields, validation rules, remaining blockers, and claim boundary.
- It must not bundle or synthesize operator data and must not close Phase 3, Phase 4, Phase 6, or Developer Preview Release Candidate.
- Existing checks must be updated so generated artifacts are reproducible.
- Run focused pytest for the new/affected tests and the relevant builder --check commands.
