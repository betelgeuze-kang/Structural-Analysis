# Cursor worker slice: Developer Preview dataset/license manifest audit

Goal:
- Audit `developer_preview_dataset_license_manifest.json` and its builder for Phase 0 manifest finalization evidence.

Scope:
- `scripts/build_developer_preview_readiness.py`
- `implementation/phase1/release_evidence/productization/developer_preview_dataset_license_manifest.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.md`
- `tests/test_build_developer_preview_readiness.py`

Questions to answer:
- Does the manifest distinguish fixed policy coverage from still-pending license/checksum/expected-output gates?
- Are pending source ids/counts machine-readable instead of only embedded in blocker strings?
- Can any local repo-generated source be marked complete without implying upstream OpenSees/buildingSMART/commercial redistribution rights?

Constraints:
- Do not fabricate license approval, source checksums, expected outputs, external receipts, or commercial redistribution permission.
- Do not remove pending blockers unless the manifest has authoritative evidence for that gate.
- Keep Developer Preview distinct from Commercial Release.

Verification:
- If a narrow manifest schema/test improvement is useful, implement it.
- Run `python3 -m pytest -q tests/test_build_developer_preview_readiness.py`.
- Run `python3 scripts/build_developer_preview_readiness.py --write-dataset-license-manifest`, then `--check`.
- Summarize changed files, tests, and remaining blockers.
