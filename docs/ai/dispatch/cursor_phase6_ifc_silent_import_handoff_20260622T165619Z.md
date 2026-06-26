# Cursor worker task: Phase 6 IFC silent import handoff audit

Goal: Audit the Developer Preview RC final-gate handoff for `silent_import_loss_zero`.

Scope:
- Do not download or fabricate IFC files.
- Do not promote `silent_import_loss_zero`.
- Inspect the IFC import-health execution receipt, buildingSMART clean/dirty acquisition receipts, source-license receipt, RC status builder, and RC tests.

Candidate files:
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/phase3_ifc_import_health_execution_receipt.json`
- `implementation/phase1/release_evidence/productization/phase3_buildingsmart_ifc_acquisition_receipt.json`
- `implementation/phase1/release_evidence/productization/phase3_buildingsmart_dirty_ifc_acquisition_receipt.json`
- `implementation/phase1/release_evidence/productization/phase3_ifc_source_license_receipt.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

Verification criteria:
- `silent_import_loss_zero` remains blocked until selected IFC files are acquired, checksummed, license-reviewed, and import-health/negative contracts are executed.
- RC status exposes clean/dirty selected counts, expected contract counts, execution counts, and blockers.
- RC pass counts do not increase.
- Claim boundary says IFC import-health evidence is not solver accuracy or full Phase 3 closure.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
