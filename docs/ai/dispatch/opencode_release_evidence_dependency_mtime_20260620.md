# OpenCode Worker Slice: Release Evidence Dependency Mtime

Goal: tighten the release evidence freshness gate so `dependency_mtime_pass` covers producer scripts and declared input-checksum file dependencies, not only the producer script.

Scope:
- Inspect and edit only the smallest needed set around:
  - `scripts/report_release_evidence_freshness.py`
  - `tests/test_report_release_evidence_freshness.py`
  - generated `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json`
  - generated `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.md`
- Do not read `.env*` files.
- Do not read `.betelgeuze/worker_outputs/*.raw.md`.
- Preserve the claim boundary: this freshness gate is metadata/dependency-recency only and must not imply heavy validation reruns.

Implementation criteria:
- If `input_checksum` / `input_checksums` is a dict whose keys are repository paths, include existing file paths in the dependency mtime comparison.
- Mark the row blocked if any existing declared dependency file is newer than the artifact.
- Include enough row detail to identify which dependencies were checked and which were newer.
- Keep non-path checksum keys or missing optional input files from producing noisy false blockers unless the existing source-commit diff logic already treats them as blockers.
- Update tests for producer-newer and input-dependency-newer behavior.

Verification criteria:
- `python3 -m pytest -q tests/test_report_release_evidence_freshness.py`
- `python3 -m ruff check scripts/report_release_evidence_freshness.py tests/test_report_release_evidence_freshness.py`
- `python3 scripts/report_release_evidence_freshness.py --out implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json --out-md implementation/phase1/release_evidence/productization/release_evidence_freshness_report.md --fail-blocked`

Worker output must be concise:
- changed files
- test results
- core diff summary
- blockers, if any
