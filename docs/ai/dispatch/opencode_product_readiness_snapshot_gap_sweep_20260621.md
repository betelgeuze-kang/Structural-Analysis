# OpenCode slice: product readiness snapshot gap sweep

## Goal
Inspect the current product readiness canonicalization work for small, local fail-open gaps against the active paid-pilot readiness objective.

## Scope
- Read-only exploration only. Do not edit files.
- Candidate files:
  - `scripts/build_product_readiness_snapshot.py`
  - `scripts/verify_quality_gate.py`
  - `tests/test_build_product_readiness_snapshot.py`
  - `tests/test_verify_quality_gate.py`
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `tests/test_pm_canonical_release_area_sync.py`
  - `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
  - `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
  - `implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json`
  - `implementation/phase1/customer_shadow_evidence_status.json`

## Questions
1. Does the snapshot directly expose all release blockers named by the objective: CI streak, human UX, license, customer shadow, fresh validation, external benchmark receipts, G1?
2. Is there any easy fail-open path where an upstream `contract_pass=true` could still make `paid_pilot_ready` or `release_ready` true while one of those blocker classes remains open?
3. Do README/current-state docs have a test-backed sync point to the canonical snapshot, beyond PM release area and action-register counts?

## Output
Return only:
- top 3 concrete gaps, if any
- exact file/function/test names involved
- one recommended small local fix
- commands you ran

Do not include long logs.
