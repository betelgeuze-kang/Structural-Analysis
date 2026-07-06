# Local-free structural scope release-surface decision pack

Purpose: close as much of the structural-scope cleanup preparation as possible without local workstation, protected-evidence refresh, destructive file deletion, or owner-signoff mutation.

This packet is **non-promoting**. It does not close `structural_scope::owner_decision_pending_count=86`, does not delete files, and does not convert quarantine into release readiness. It prepares owner decisions so the owner can execute the next local/CI-backed closure step.

## Current state

- Non-structural tracked paths are quarantined: `86/86`.
- Unquarantined non-structural tracked paths: `0`.
- Owner decisions recorded: `0/86`.
- Release-surface cleanup decisions: `0/3`.
- Release-surface retain exceptions are not allowed for the first release-surface batch.

Authoritative artifacts:

- `implementation/phase1/release_evidence/productization/structural_scope_contamination_audit.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_review_packet.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decision_application_plan.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.csv`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.md`

## Release-surface-first paths

The release-surface-first batch should be handled before feature expansion:

1. `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json`
2. `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json`
3. `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json`

Recommended owner decisions:

| Path family | Recommended decision | Reason |
| --- | --- | --- |
| GPCR / hard-decoy evidence surface | `extract_to_molecular_or_science_repository` | Domain belongs to molecular/science product surface, not structural solver release surface. |
| H-bond backmap evidence surface | `extract_to_molecular_or_science_repository` | Hydrogen-bond/backmapping semantics are non-structural and should not affect structural solver release readiness. |
| PocketMD lite science product surface | `extract_to_molecular_or_science_repository` | PocketMD is a separate molecular/science product family and should remain outside structural release evidence. |

Fallback decision if extraction target is unavailable:

- `delete_from_structural_repository`, provided owner confirms no structural release artifact depends on the file.

Disallowed decision for the three release-surface-first paths:

- `retain_quarantined_with_signed_owner_exception`

## Required owner fields

Each decision row should include:

- `path`
- `decision`
- `owner_identity`
- `owner_role`
- `decision_timestamp_utc`
- `evidence_ref`
- `rationale`
- `cleanup_action_required`

Recommended `owner_role` values:

- `product_owner`
- `repository_owner`
- `technical_owner`
- `delegated_release_owner`

## Suggested execution sequence

1. Fill the release-surface-first template.
2. Validate the owner decision batch.
3. Merge the filled batch into the candidate owner-decision artifact.
4. Apply owner-approved delete/extract cleanup manually.
5. Rerun structural scope contamination audit.
6. Rerun structural scope owner review packet.
7. Rerun structural scope owner decision application plan.
8. Rerun product readiness snapshot in check mode.
9. Rerun roadmap generation.

## Acceptance criteria

This track is closed only when:

- release-surface owner decisions are `3/3`;
- all 86 quarantined non-structural paths have owner decisions;
- owner-approved delete/extract cleanup is manually applied;
- structural scope audit passes after cleanup;
- product readiness snapshot no longer reports structural-scope blockers.

## Claim boundary

Until the acceptance criteria pass, the correct claim is:

> Non-structural artifacts are quarantined from the structural release surface, but owner decisions and delete/extract cleanup are not complete.

Do not claim:

- structural scope cleanup closed;
- repository contamination fully removed;
- release-surface owner decisions complete;
- product readiness promoted by quarantine alone.
