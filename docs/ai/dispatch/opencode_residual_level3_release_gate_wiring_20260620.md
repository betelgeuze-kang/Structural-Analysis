# OpenCode Worker Slice: Residual Level 3 Release Gate Wiring

Goal:
- Wire `implementation/phase1/release_evidence/productization/residual_level3_status.json` into release evidence freshness and the PM release-area residual gate.

Scope:
- `scripts/report_release_evidence_freshness.py`
- `scripts/report_pm_release_gate.py`
- Focused tests covering those reports
- Regenerated release evidence JSON/MD only when required by the changed generators

Candidate files:
- `tests/test_report_release_evidence_freshness.py`
- `tests/test_report_pm_release_gate.py`
- `implementation/phase1/release_evidence/productization/residual_level3_status.json`
- `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json`
- `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.md`
- `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `implementation/phase1/release_evidence/productization/pm_release_gate_report.md`

Verification criteria:
- Freshness default artifacts include `residual_level3_status`.
- PM release-area matrix residual area directly consumes `residual_level3_status`, includes it in artifacts, and blocks when the Level 3 status is not green.
- Existing residual M1 milestone behavior remains compatible.
- Run focused pytest for freshness/PM residual tests.
- Run ruff for touched Python files.

Constraints:
- Do not read or print `.env*`.
- Do not read or print `.betelgeuze/worker_outputs/*.raw.md`.
- Do not push, merge, or run destructive git commands.
- Keep output concise: changed files, test results, failed tests, core diff summary, blockers.
