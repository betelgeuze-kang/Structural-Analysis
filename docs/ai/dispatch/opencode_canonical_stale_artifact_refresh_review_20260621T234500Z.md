# OpenCode Worker Slice: Canonical Stale Artifact Refresh Review

Goal: identify which stale readiness artifacts can be safely regenerated from local status scripts without creating synthetic PASS evidence or closing external blockers.

Scope:
- `scripts/build_product_readiness_snapshot.py`
- `scripts/report_pm_release_gate.py`
- `scripts/check_independent_product_readiness.py`
- `implementation/phase1/*customer_shadow*`
- `implementation/phase1/release_evidence/productization/*status*.json`
- `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
- README/current-state canonical snapshot lines.

Questions:
- Which current snapshot `stale_or_inconsistent:source_commit_mismatch:*` blockers correspond to deterministic local status reporters?
- Which reporters should not be refreshed because they need external evidence, human input, or network state?
- What focused verification should follow any blocked/stale receipt refresh?

Constraints:
- Do not edit files.
- Do not synthesize external benchmark receipts, customer shadow cases, UX observations, license approval, CI streak, or G1 closure.
- Keep output limited to candidate commands, files, tests, and blockers.
