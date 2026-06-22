# Cursor Worker Slice: Phase 3 IFC Silent Import Loss Gate Audit

Goal:
Audit whether Phase 3 IFC import-health receipts explicitly prove or block the Developer Preview RC final gate `silent_import_loss_zero`.

Scope:
- Inspect only:
  - `scripts/build_phase3_ifc_import_health_execution_receipt.py`
  - `scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py`
  - `scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py`
  - `scripts/build_phase3_ifc_source_license_receipt.py`
  - `tests/test_build_phase3_ifc_import_health_execution_receipt.py`
- Do not download IFC files.
- Do not claim Phase 3 or RC closure.

Report:
- Missing explicit fields needed to show silent import loss was checked.
- Exact test assertions for missing-file and acquired-file cases.
- Claim-boundary risks if text-scan import health is mistaken for solver-ready geometry.

Verification criteria:
- Missing source files must block `silent_import_loss_zero`.
- Acquired/executed cases must expose entity accounting and unsupported-feature visibility.
- Quantity credit remains false until 10 clean/dirty IFC cases are acquired, checksummed, license-reviewed, executed, and visibly accounted.
- No solver accuracy or Phase 3 closure claim.
