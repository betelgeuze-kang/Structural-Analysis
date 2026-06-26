# Goal
Separate the Phase 6 Developer Preview RC deliverable "sample acquisition command" from the blocked Phase 3 external acquisition corpus readiness.

# Scope
- Add machine-readable acquisition command surface metadata to the Phase 3 acquisition plan artifact.
- The command surface should be ready if the repo has a documented local command that prints/writes the acquisition policy without downloading or bundling external data, e.g. `python3 scripts/build_phase3_benchmark_acquisition_artifacts.py --json`.
- Keep the acquisition plan `status=blocked` and `contract_pass=false` while license/checksum/expected-output/download/execution blockers remain.
- Update `scripts/build_developer_preview_rc_status.py` so the `sample_acquisition_command` deliverable uses the command-surface contract, not the full acquisition corpus readiness contract.
- Do not reduce or remove acquisition blockers.
- Do not mark Phase 3 closure, Developer Preview RC, or any external corpus lane ready.

# Candidate files
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `tests/test_build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- generated:
  - `implementation/phase1/release_evidence/productization/phase3_benchmark_acquisition_plan.json`
  - `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
  - `implementation/phase1/release_evidence/productization/developer_preview_rc_status.md`
  - `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json`
  - `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.md`

# Verification criteria
- `python3 -m pytest -q tests/test_build_phase3_benchmark_acquisition_artifacts.py tests/test_build_developer_preview_rc_status.py tests/test_report_release_evidence_freshness.py`
- `python3 scripts/build_phase3_benchmark_acquisition_artifacts.py --check`
- `python3 scripts/build_developer_preview_rc_status.py --check`
- `python3 scripts/report_release_evidence_freshness.py --fail-blocked`
- `python3 -m ruff check src/structural_analysis/benchmark/acquisition.py scripts/build_phase3_benchmark_acquisition_artifacts.py scripts/build_developer_preview_rc_status.py tests/test_build_phase3_benchmark_acquisition_artifacts.py tests/test_build_developer_preview_rc_status.py`
- RC deliverables should improve by one only if the command surface is ready; final gates and corpus blockers must remain blocked.
