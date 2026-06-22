# Goal
Preserve per-case convergence history in the generated Phase 3 benchmark factory scorecard so the Developer Preview RC final gate `residual_and_convergence_history_present` can be evidence-backed for generated seed benchmarks.

# Scope
- Update `src/structural_analysis/benchmark/factory.py` so `run_benchmark_case()` includes the API result `convergence_history` in each scorecard row.
- Keep residual formula, fallback, regularization, and nonlinear checks unchanged.
- Update tests:
  - `tests/test_build_phase3_benchmark_factory_artifacts.py`
  - `tests/test_structural_analysis_benchmark_cli.py` if needed
  - `tests/test_build_developer_preview_rc_status.py` so the RC final gate moves from blocked to ready only for this generated-scorecard condition.
- Update `scripts/build_developer_preview_rc_status.py` to check all scorecard rows have non-empty convergence history with residual/increment fields.
- Regenerate affected receipts:
  - `phase3_benchmark_factory_seed_scorecard.json`
  - `phase3_benchmark_factory_seed_summary.json`
  - reproducibility bundle if checksum changes
  - `developer_preview_rc_status.json/.md`
  - `release_evidence_freshness_report.json/.md`
- Do not mark full RC ready. Medium/large/IFC/Linux-Windows/new-user/git-clean-clone blockers must remain.
- Do not claim G1/full nonlinear full-mesh closure.

# Verification criteria
- `python3 -m pytest -q tests/test_build_phase3_benchmark_factory_artifacts.py tests/test_structural_analysis_benchmark_cli.py tests/test_build_developer_preview_rc_status.py tests/test_report_release_evidence_freshness.py`
- `python3 scripts/build_phase3_benchmark_factory_artifacts.py --check`
- `python3 scripts/build_developer_preview_rc_status.py --check`
- `python3 scripts/report_release_evidence_freshness.py --fail-blocked`
- `python3 -m ruff check src/structural_analysis/benchmark/factory.py scripts/build_developer_preview_rc_status.py tests/test_build_phase3_benchmark_factory_artifacts.py tests/test_structural_analysis_benchmark_cli.py tests/test_build_developer_preview_rc_status.py`
- Summarize changed files, final RC pass counts, tests, and blockers only.
