# Goal
Create a machine-readable Developer Preview Release Candidate status receipt that aggregates Phase 6 deliverables and final gates without promoting RC readiness.

# Scope
- Add a narrow builder, preferably `scripts/build_developer_preview_rc_status.py`.
- Add focused tests.
- Generate JSON and Markdown under `implementation/phase1/release_evidence/productization/`.
- Aggregate existing authoritative receipts only. Do not synthesize external evidence.
- Required deliverables to classify:
  - installable Python package
  - `structural-analysis` CLI
  - local web GUI surface
  - sample acquisition command
  - benchmark runner
  - benchmark scorecard
  - known limitations
  - reproducibility bundle
  - dataset/license manifest
  - commercial comparison import template
- Required final gates to classify:
  - analytic/component benchmark all PASS
  - selected medium models PASS or approved REVIEW
  - large model crash/OOM-free completion
  - silent import loss 0
  - residual/convergence history present
  - unsupported features explicitly blocked
  - Linux/Windows reproducibility
  - new-user workflow observation
  - clean-checkout benchmark regeneration
- Keep customer shadow, 30-run CI, product license, and external approval receipts out of Developer Preview RC blocking if the objective says they move to later Commercial Release. They may remain visible as future commercial gates.

# Candidate files
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.md`
- possibly `scripts/report_release_evidence_freshness.py` only if the repo already tracks all RC status receipts there; otherwise avoid broad changes.

# Verification criteria
- `python3 -m pytest -q tests/test_build_developer_preview_rc_status.py`
- `python3 scripts/build_developer_preview_rc_status.py --check`
- `python3 -m ruff check scripts/build_developer_preview_rc_status.py tests/test_build_developer_preview_rc_status.py`
- Receipt status must be blocked, `developer_preview_release_candidate_ready=false`, and claim boundary must say it does not close Commercial Release, Phase 3 full corpus, G1 full nonlinear full-mesh, or external evidence gates.
- Summarize changed files, tests, and blockers only.
