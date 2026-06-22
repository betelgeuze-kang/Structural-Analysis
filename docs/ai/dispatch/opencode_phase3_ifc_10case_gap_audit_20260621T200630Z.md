Goal: Audit the current Phase 3 IFC benchmark acquisition state against the active roadmap requirement: at least 10 clean/dirty IFC import cases, each with truth class, license status, checksum/provenance boundary, and expected outputs. Do not close or promote readiness without authoritative evidence.

Scope:
- Inspect current Phase 3 IFC/buildingSMART acquisition receipts and benchmark acquisition/factory wiring.
- Identify the smallest safe implementation slice that moves the IFC corpus toward the 10-case requirement without downloading external files or inventing licenses/checksums.
- If the slice is clear and small, implement it with tests; otherwise leave a concise recommendation.

Candidate files:
- scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py
- scripts/build_phase3_ifc_source_license_receipt.py
- scripts/build_phase3_benchmark_acquisition_artifacts.py
- scripts/build_phase3_benchmark_factory_artifacts.py
- src/structural_analysis/benchmark/acquisition.py
- tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py
- tests/test_build_phase3_ifc_source_license_receipt.py
- tests/test_build_phase3_benchmark_acquisition_artifacts.py
- tests/test_build_phase3_benchmark_factory_artifacts.py
- implementation/phase1/release_evidence/productization/phase3_*ifc*.json

Verification criteria:
- No external downloads.
- No PASS/ready promotion for source files that are not acquired, checksummed, license-reviewed, and import-health executed.
- Expected-output contracts may be authored, but execution must remain blocked until real local files exist.
- Tests should prove drift/missing-output detection and that claim boundaries stay blocked.
- Summary must include changed files, tests run, blockers that remain, and any files intentionally not touched.
