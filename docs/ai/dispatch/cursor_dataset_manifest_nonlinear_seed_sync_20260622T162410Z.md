# Goal
Synchronize the Developer Preview dataset/license manifest with the new repo-generated `nonlinear-material-mesh` Phase 3 seed lane, without reducing or hiding external/operator pending blockers.

# Scope
- Inspect:
  - `src/structural_analysis/benchmark/factory.py`
  - `scripts/build_developer_preview_readiness.py`
  - `tests/test_build_developer_preview_readiness.py`
  - `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_manifest.json`
  - `implementation/phase1/release_evidence/productization/developer_preview_dataset_license_manifest.json`
- Update the dataset/license manifest builder so the repo-generated bundle policy covers all repo-generated seed lanes now present in the Phase 3 seed manifest:
  - `analytic-small`
  - `element-patch`
  - `nonlinear-material-mesh`
- Keep the source identity conservative. It is acceptable to keep one repo-generated source row if its selected lanes and policy text explicitly cover the nonlinear material-mesh seed.
- Do not add `nonlinear-material-mesh` to the required external Phase 3 corpus lane list unless the existing contract clearly wants generated seed lanes in that list.
- Do not lower pending external/operator counts:
  - authoritative checksum pending should remain `4`
  - license/redistribution pending should remain `4`
  - expected outputs pending should remain `4`
- Do not mark Developer Preview ready, Phase 3 closed, or G1/full nonlinear full-mesh closed.

# Candidate files
- `scripts/build_developer_preview_readiness.py`
- `tests/test_build_developer_preview_readiness.py`
- `implementation/phase1/release_evidence/productization/developer_preview_dataset_license_manifest.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.md`

# Verification criteria
- `python3 -m pytest -q tests/test_build_developer_preview_readiness.py`
- `python3 scripts/build_developer_preview_readiness.py --check`
- `python3 -m ruff check scripts/build_developer_preview_readiness.py tests/test_build_developer_preview_readiness.py`
- The generated dataset/license manifest source row for repo-generated seeds includes `nonlinear-material-mesh`.
- Pending external/operator blocker counts remain visible and unchanged.
- Summarize changed files, test results, and blockers only.
