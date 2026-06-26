# Cursor worker slice: Phase 6 benchmark scale status audit

Goal:
Audit the Phase 6 benchmark-scale status receipt integration for Developer Preview RC readiness without promoting any blocked gate.

Scope:
- Review the new benchmark-scale status receipt builder and tests.
- Review the Developer Preview RC status integration for medium/large final gates and known-limitations handoffs.
- Confirm claim boundaries remain conservative: parser-only topology is not medium pass evidence, and policy-only acquisition rows are not large execution evidence.

Candidate files:
- `scripts/build_phase6_benchmark_scale_status.py`
- `tests/test_build_phase6_benchmark_scale_status.py`
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/phase6_benchmark_scale_status.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.md`

Verification criteria:
- Do not edit unrelated files.
- Do not mark medium or large benchmark gates ready unless authoritative evidence exists.
- Run or report these focused commands if possible:
  - `python3 -m pytest -q tests/test_build_phase6_benchmark_scale_status.py tests/test_build_developer_preview_rc_status.py`
  - `python3 scripts/build_phase6_benchmark_scale_status.py --check`
  - `python3 scripts/build_developer_preview_rc_status.py --check`

Worker output:
- Changed files, if any.
- Test/check results.
- Any unsupported closure claim or missing receipt linkage.
- Blockers only if this slice cannot be safely accepted.
