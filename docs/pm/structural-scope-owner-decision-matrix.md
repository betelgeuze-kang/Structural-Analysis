# Structural Scope Owner Decision Matrix

> Status: **non-promoting PM handoff**  
> Scope: structural release-surface hygiene only  
> This document does **not** delete files, extract files, change solver behavior, refresh protected evidence, or promote `release_ready`, `paid_pilot_ready`, `solver_product_pilot_ready`, G1, or any commercial claim.

## 1. Why this exists

The current structural roadmap identifies release-surface owner decisions as a near-term blocker. The structural scope audit already detects and quarantines non-structural molecular / GPCR / PocketMD / molecular-dynamics paths outside the structural solver release surface, but owner decisions are not yet recorded for the quarantined paths.

Current evidence summary:

| Evidence item | Current signal | PM interpretation |
|---|---:|---|
| Quarantined non-structural tracked paths | 86 | Scope contamination is identified and isolated, but not owner-closed. |
| Molecular docking rows | 48 | Science/ligand/GPCR assets should not count as structural solver release evidence. |
| Molecular dynamics rows | 25 | MD/PocketMD assets should remain outside structural release. |
| Molecular science evidence rows | 13 | H-bond/backmap/science closure assets should remain outside structural release. |
| First unquarantined non-structural path | empty | Quarantine works; owner decision closure remains. |
| Structural release-surface first batch | 3 paths | These are the first owner-decision rows to close. |

## 2. Decision policy

Allowed owner decisions for non-structural paths:

| Decision | Meaning | When to use | Release effect |
|---|---|---|---|
| `delete_from_structural_repository` | Remove path from this structural repo after owner approval. | Path has no structural release value and history is not required here. | Preferred for release-surface science artifacts. |
| `extract_to_molecular_or_science_repository` | Preserve path externally, then remove it here after owner approval. | Path has independent science value and should be maintained elsewhere. | Valid only with external archive/repo reference. |
| `keep_quarantined_outside_structural_release` | Keep tracked for now but permanently exclude from structural release evidence. | Temporary holding pattern for lower-priority productization evidence pending owner review. | Does not close owner-decision blocker unless the release policy explicitly accepts the quarantine as final. |

Forbidden decisions:

- Count molecular, GPCR, PocketMD, ligand, H-bond, or MD artifacts as structural solver release evidence.
- Treat quarantine as solver readiness.
- Promote `release_ready`, G1, paid pilot, limited commercial, or GA because scope artifacts are classified.
- Delete or extract files without explicit owner approval and post-action audit refresh.

## 3. Family-level matrix

| Family | Count | Current treatment | Primary owner decision recommendation | Rationale | Required evidence before closure |
|---|---:|---|---|---|---|
| `molecular_docking` | 48 | Quarantined outside structural release | Extract or delete; release-surface rows should prefer delete | GPCR/ligand benchmark surfaces are not structural analysis release evidence. | Owner identity, decision timestamp, evidence reference, optional external archive reference. |
| `molecular_dynamics` | 25 | Quarantined outside structural release | Extract or delete; PocketMD release-surface row should prefer delete | MD/PocketMD artifacts are not part of building structural solver release scope. | Owner identity, decision timestamp, evidence reference, optional external archive reference. |
| `molecular_science_evidence` | 13 | Quarantined outside structural release | Extract or delete; release-surface row should prefer delete | H-bond/backmap science evidence is not structural solver evidence. | Owner identity, decision timestamp, evidence reference, optional external archive reference. |

## 4. Priority-1 release-surface owner decisions

These three rows are the first release-surface cleanup batch. They should be closed before lower-priority quarantined productization artifacts.

| Row ID | Path | Family | Recommended owner decision | Allowed alternatives | Post-decision action |
|---|---|---|---|---|---|
| `release_surface_first-001` | `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `molecular_docking` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | Delete or extract, then rerun structural scope audit and readiness snapshot. |
| `release_surface_first-002` | `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `molecular_science_evidence` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | Delete or extract, then rerun structural scope audit and readiness snapshot. |
| `release_surface_first-003` | `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `molecular_dynamics` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | Delete or extract, then rerun structural scope audit and readiness snapshot. |

## 5. Owner decision record template

Use this structure in `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.json` or in a CSV consumed by the owner-decision tooling.

```json
{
  "row_id": "release_surface_first-001",
  "path": "implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json",
  "owner_decision": "delete_from_structural_repository",
  "owner_identity": "<GitHub user or accountable owner>",
  "owner_role": "PM|CTO|Release owner|Repo owner",
  "decision_timestamp_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "evidence_reference": "<issue/pr/approval reference>",
  "external_archive_reference": "",
  "signed_owner_exception_reference": ""
}
```

## 6. Closure sequence

1. Fill the owner decision rows for the priority-1 release-surface batch.
2. For delete/extract decisions, require human confirmation before any destructive operation.
3. If extraction is chosen, record the external archive/repository reference before removing paths here.
4. Apply cleanup manually or through an explicitly approved script.
5. Rerun:

```bash
python3 scripts/check_structural_scope_contamination.py --tracked-only --check --fail-blocked
python3 scripts/build_structural_scope_owner_review_packet.py
python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-blocked
python3 scripts/build_product_readiness_snapshot.py --check
```

## 7. Exit criteria

| Exit criterion | Target |
|---|---|
| Release-surface owner decisions | `3/3` recorded |
| Overall quarantined path owner decisions | `86/86` recorded or explicitly accepted as keep-quarantined by policy |
| First unquarantined non-structural path | empty |
| Structural release surface | no molecular / GPCR / PocketMD / MD rows counted as structural evidence |
| Solver readiness | unchanged unless separate solver receipts pass |

## 8. Claim boundary

Closing this matrix only means the structural release surface is cleaner. It does not mean:

- G1 is closed.
- Developer Preview is ready.
- The product is release-ready.
- The product is paid-pilot-ready.
- The product is a commercial solver replacement.
