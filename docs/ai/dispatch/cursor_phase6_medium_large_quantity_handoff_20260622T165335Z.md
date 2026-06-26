# Cursor worker task: Phase 6 medium/large benchmark quantity handoff audit

Goal: Audit the Developer Preview RC final-gate handoff for medium and large benchmark quantity gaps.

Scope:
- Do not add fake medium/large benchmark cases.
- Do not promote `selected_medium_models_pass_or_approved_review` or `large_models_crash_oom_free`.
- Inspect the Phase 3 seed summary, acquisition plan, RC status builder, and RC tests.

Candidate files:
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_summary.json`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_acquisition_plan.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

Verification criteria:
- Medium remains blocked at current/required target count.
- Large remains blocked at current/required target count.
- RC status exposes owner-action style handoff with acquisition blockers and required evidence, without claiming full Phase 3 corpus closure.
- RC pass counts do not increase.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
