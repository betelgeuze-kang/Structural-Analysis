# Structural Scope Owner Decision Application Plan

- `status`: `pending_owner_decisions`
- `contract_pass`: `True`
- `application_ready`: `False`
- `evidence_closure_pass`: `False`
- `owner_decision_validation_pass`: `False`
- `owner_decision_pending_count`: `86`
- `post_decision_cleanup_pending_count`: `0`
- `post_decision_cleanup_applied_count`: `0`
- `cleanup_required_count`: `0`
- `release_surface_cleanup_required_count`: `0`
- `delete_decision_count`: `0`
- `extract_decision_count`: `0`
- `retain_quarantined_exception_count`: `0`

## Owner Decision Validation Blockers

- `owner_decisions_missing`
- `owner_decision_pending_count=86`

## Plan Blockers

- `owner_decision_pending_count=86`

## Cleanup Rows

| Path | Decision | Required Action |
|---|---|---|

## Cleanup Command Manifest

- `safe_to_auto_apply`: `False`
- `manual_application_required`: `False`
- `delete_from_structural_repository.path_count`: `0`
- `extract_to_molecular_or_science_repository.path_count`: `0`

## Claim Boundary

This application plan is non-mutating. It never deletes or extracts files. It only classifies owner decisions into manual follow-up actions and keeps quarantined non-structural artifacts outside the building structural-analysis release surface until owner evidence and post-decision scope audit closure are present.
