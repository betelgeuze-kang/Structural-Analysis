# Product readiness snapshot receipt-commit freshness probe

Goal: inspect the canonical product readiness snapshot freshness loop and report a minimal fix/test plan.

Scope:
- `scripts/build_product_readiness_snapshot.py`
- `tests/test_build_product_readiness_snapshot.py`
- `scripts/report_release_evidence_freshness.py`
- `tests/test_report_release_evidence_freshness.py`

Context:
- The snapshot currently marks component evidence stale unless each component `source_commit_sha` equals current HEAD.
- After committing regenerated evidence, HEAD changes and `product_readiness_snapshot.json` can mark itself `stale_or_inconsistent` even when the only changes since the component source commit are committed receipt/status artifacts.
- Do not promote stale evidence when code, docs, tests, or non-receipt inputs changed after the component source commit.

Deliverable:
- Summarize the smallest safe rule and focused regression tests.
- Do not edit files.
- Do not run network or remote commands.

Verification criteria:
- The proposed rule must preserve stale detection when non-evidence code changed after an artifact source commit.
- The proposed rule must allow a receipt-only evidence commit to be treated as fresh.
