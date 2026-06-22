Goal: Audit the Phase 3 IFC source/license receipt claim boundary.

Scope:
- Review only these files if present:
  - src/structural_analysis/benchmark/acquisition.py
  - scripts/build_phase3_ifc_source_license_receipt.py
  - tests/test_build_phase3_ifc_source_license_receipt.py
  - scripts/build_developer_preview_readiness.py
  - implementation/phase1/release_evidence/productization/phase3_ifc_source_license_receipt.json
  - implementation/phase1/release_evidence/productization/developer_preview_dataset_license_manifest.json

Verification criteria:
- Report unsupported claims that source URL evidence closes checksum, expected outputs, redistribution, commercial use, or Phase 3 quantity credit.
- Report missing blockers for buildingSMART clean/dirty IFC or ifc-query-and-gui sources.
- Do not edit files.

Output only changed-risk findings, failed/missing tests, and blockers.
