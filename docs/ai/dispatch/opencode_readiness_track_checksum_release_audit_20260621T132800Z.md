Goal: Audit and, if low-risk, patch the current release/readiness implementation toward the active objective.

Scope:
- Inspect only:
  - scripts/build_product_readiness_snapshot.py
  - scripts/verify_quality_gate.py
  - .github/workflows/release-publish.yml
  - tests/test_build_product_readiness_snapshot.py
  - tests/test_verify_quality_gate.py
  - tests/test_release_publish_workflow.py
  - tests/test_product_readiness_snapshot_doc_sync.py
  - README.md
  - docs/commercialization-gap-current-state.md
  - implementation/phase1/release_evidence/productization/product_readiness_snapshot.json
- Do not edit unrelated G1/HIP files already dirty in the worktree.
- Preserve claim boundaries: do not promote assisted service, solver product, limited commercial, GA, or release readiness with missing external/UX/license/CI/G1 evidence.

Verification criteria:
- Canonical snapshot exposes separated assisted_service_pilot and solver_product gates.
- Missing input checksum metadata is visible as a stale/inconsistent blocker on real HEAD generation.
- Release mode executes full quality before strict readiness checks.
- release-publish workflow gates publication before remote publish.
- Focused tests covering the touched files pass.

Output only:
- Changed files
- Test results
- Core diff summary
- Remaining blockers
