# Local-free structural scope release-surface decision pack

Purpose: preserve the release-surface-first preparation record that preceded the completed structural-scope cleanup.

This packet is **superseded** by `structural_scope_owner_decisions.json` and GitHub issue #181. It remains non-promoting: the completed repository-scope cleanup does not provide legal approval, independent engineering review, or product-release authorization.

## Current state

- Historical quarantine-manifest paths: `86`.
- Current matching paths in the Git index and worktree: `0/86`.
- Owner delete decisions recorded: `86/86`.
- Post-decision cleanup applied: `86/86`.
- Historical release-surface-first paths deleted: `3/3`; current release-surface paths: `0`.
- Structural-scope evidence closure: `true` with no pending owner or cleanup rows.

Authoritative artifacts:

- `implementation/phase1/release_evidence/productization/structural_scope_contamination_audit.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_review_packet.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decision_application_plan.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.json`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.csv`
- `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.md`

## Historical release-surface-first paths

The three paths below were the original first batch and are now absent from the repository:

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

## Completed execution sequence

1. PR #168 removed all 86 manifest paths.
2. The repository owner selected `delete_from_structural_repository` for all 86 rows in issue #181.
3. The canonical decision artifact recorded and validated those rows.
4. The owner-review and application-plan builders verified all 86 paths remain absent.
5. The product snapshot and roadmap were regenerated without a structural-scope blocker.

## Acceptance criteria

This track is closed because:

- all 86 historical paths have delete decisions and are absent;
- the structural scope audit passes after cleanup;
- owner-review evidence reports decision pending `0`, cleanup pending `0`, and applied `86`;
- the product readiness snapshot no longer reports structural-scope blockers.

## Claim boundary

The correct current claim is:

> The 86 historical non-structural paths were removed and their repository-owner delete decisions are recorded; broader product readiness remains blocked by independent external gates.

Do not claim:

- product readiness or commercial release solely from this cleanup;
- legal approval, independent V&V, engineering signoff, or customer validation;
- that the historical quarantine manifest describes paths still present in the current tree.
