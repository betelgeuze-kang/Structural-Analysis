# Structural Scope Origin Report

- `summary_line`: `Structural scope origin report: READY_FOR_OWNER_REVIEW_ORIGIN_EVIDENCE | paths=86 | waves=37 | release_surface=3 | missing_origin=0`
- `contract_pass`: `True`
- `origin_evidence_complete`: `True`
- `quarantined_path_count`: `86`
- `origin_wave_count`: `37`
- `release_surface_origin_path_count`: `3`
- `owner_decision_pending_count`: `86`

## Root Cause

Quarantined non-structural paths entered this structural-analysis repository through tracked molecular runtime and science productization waves, then were later excluded from structural release claims by the scope quarantine manifest.

## Origin Waves

| Wave | Date | Commit | Paths | Areas | Families | Subject |
|---|---|---|---:|---|---|---|
| `initial_bulk_import_with_md3bead_runtime` | `2026-04-26` | `2b655fe3` | 9 | `{'implementation_phase1': 9}` | `{'molecular_dynamics': 9}` | `Import structural analysis workbench implementation` |
| `molecular_public_benchmark_wave` | `2026-06-29` | `02f5738c` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark subset manifest validator` |
| `molecular_public_benchmark_wave` | `2026-06-29` | `0a4c6a6c` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark subset materializer` |
| `molecular_public_benchmark_wave` | `2026-06-29` | `1e750777` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Seed public benchmark harness contracts` |
| `molecular_public_benchmark_wave` | `2026-06-29` | `3e79e84a` | 3 | `{'productization_evidence': 3}` | `{'molecular_docking': 3}` | `Materialize public benchmark source artifacts` |
| `molecular_public_benchmark_wave` | `2026-06-29` | `89be102d` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark pose validity materializer` |
| `molecular_public_benchmark_wave` | `2026-06-29` | `c8ff0a6d` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark pose validity validator` |
| `gpcr_productization_evidence_wave` | `2026-06-30` | `685a32ea` | 1 | `{'productization_evidence': 1}` | `{'molecular_docking': 1}` | `Add GPCR product report artifact` |
| `gpcr_productization_evidence_wave` | `2026-06-30` | `759a6419` | 2 | `{'productization_evidence': 2}` | `{'molecular_docking': 2}` | `Refresh GPCR intake artifacts` |
| `gpcr_productization_evidence_wave` | `2026-06-30` | `92689e28` | 1 | `{'productization_evidence': 1}` | `{'molecular_docking': 1}` | `Materialize blocked GPCR hard-decoy suite report` |
| `gpcr_productization_evidence_wave` | `2026-06-30` | `9c7decd0` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add GPCR hard-decoy operator intake packet` |
| `gpcr_productization_evidence_wave` | `2026-06-30` | `c808ffd2` | 3 | `{'productization_evidence': 1, 'script': 1, 'test': 1}` | `{'molecular_docking': 3}` | `Add GPCR hard-decoy suite materializer` |
| `gpcr_productization_evidence_wave` | `2026-06-30` | `d8e044b6` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add GPCR hard-decoy product report contract` |
| `h_bond_backmap_science_wave` | `2026-06-30` | `572f09fe` | 4 | `{'productization_evidence': 2, 'script': 1, 'test': 1}` | `{'molecular_science_evidence': 4}` | `Add H-bond BackMap operator intake packet` |
| `molecular_public_benchmark_wave` | `2026-06-30` | `0f53c463` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark enrichment materializer` |
| `molecular_public_benchmark_wave` | `2026-06-30` | `26a231ce` | 4 | `{'productization_evidence': 4}` | `{'molecular_docking': 4}` | `Refresh replay parity and operator handoff surfaces` |
| `molecular_public_benchmark_wave` | `2026-06-30` | `3dbea443` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark PoseBusters packet materializer` |
| `molecular_public_benchmark_wave` | `2026-06-30` | `646d358a` | 1 | `{'productization_evidence': 1}` | `{'molecular_docking': 1}` | `Refresh public benchmark Vina GNINA artifacts` |
| `molecular_public_benchmark_wave` | `2026-06-30` | `aedfaf4d` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add public benchmark Vina GNINA comparison adapter` |
| `molecular_public_benchmark_wave` | `2026-06-30` | `c0b779c2` | 1 | `{'productization_evidence': 1}` | `{'molecular_docking': 1}` | `Refresh public benchmark harness artifacts` |
| `pocketmd_productization_evidence_wave` | `2026-06-30` | `0461fa02` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_dynamics': 2}` | `Add PocketMD Lite top-k materializer` |
| `pocketmd_productization_evidence_wave` | `2026-06-30` | `26a231ce` | 1 | `{'productization_evidence': 1}` | `{'molecular_dynamics': 1}` | `Refresh replay parity and operator handoff surfaces` |
| `pocketmd_productization_evidence_wave` | `2026-06-30` | `7e3a5614` | 2 | `{'productization_evidence': 2}` | `{'molecular_dynamics': 2}` | `Refresh PocketMD Lite operator intake artifacts` |
| `pocketmd_productization_evidence_wave` | `2026-06-30` | `bc1c0886` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_dynamics': 2}` | `Add PocketMD Lite product surface contract` |
| `pocketmd_release_surface_materialization` | `2026-06-30` | `01e6fe1b` | 5 | `{'productization_evidence': 4, 'release_surface': 1}` | `{'molecular_dynamics': 5}` | `Materialize PocketMD Lite product surface` |
| `science_release_surface_seed` | `2026-06-30` | `805535fc` | 2 | `{'release_surface': 2}` | `{'molecular_docking': 1, 'molecular_science_evidence': 1}` | `Add locked H-Bond and GPCR evidence surfaces` |
| `gpcr_productization_evidence_wave` | `2026-07-01` | `271e2ce6` | 1 | `{'productization_evidence': 1}` | `{'molecular_docking': 1}` | `Refresh GPCR hard-decoy audit evidence` |
| `gpcr_productization_evidence_wave` | `2026-07-01` | `866f14d3` | 1 | `{'productization_evidence': 1}` | `{'molecular_docking': 1}` | `Add GPCR hard-decoy row starter` |
| `gpcr_productization_evidence_wave` | `2026-07-01` | `dbb6aa6d` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_docking': 2}` | `Add GPCR hard-decoy raw row importer` |
| `molecular_public_benchmark_wave` | `2026-07-01` | `c6fb1fe6` | 4 | `{'productization_evidence': 4}` | `{'molecular_docking': 4}` | `Refresh public benchmark row starter artifacts` |
| `molecular_public_benchmark_wave` | `2026-07-01` | `f516132a` | 3 | `{'productization_evidence': 1, 'script': 1, 'test': 1}` | `{'molecular_docking': 3}` | `Add public benchmark pose success harness` |
| `pocketmd_productization_evidence_wave` | `2026-07-01` | `6b86aa2c` | 2 | `{'script': 1, 'test': 1}` | `{'molecular_dynamics': 2}` | `Add PocketMD Lite raw row importer` |
| `pocketmd_productization_evidence_wave` | `2026-07-01` | `80c81c53` | 1 | `{'productization_evidence': 1}` | `{'molecular_dynamics': 1}` | `Add PocketMD Lite top-k row starter` |
| `pocketmd_productization_evidence_wave` | `2026-07-01` | `df2a47df` | 1 | `{'productization_evidence': 1}` | `{'molecular_dynamics': 1}` | `Refresh PocketMD Lite top-k audit evidence` |
| `science_actual_closure_wave` | `2026-07-01` | `5bde57ae` | 3 | `{'productization_evidence': 1, 'script': 1, 'test': 1}` | `{'molecular_science_evidence': 3}` | `Add science actual closure row runner` |
| `science_actual_closure_wave` | `2026-07-01` | `7d5c52fc` | 4 | `{'productization_evidence': 2, 'script': 1, 'test': 1}` | `{'molecular_science_evidence': 4}` | `Add science closure operator handoff` |
| `science_actual_closure_wave` | `2026-07-01` | `a801661c` | 1 | `{'productization_evidence': 1}` | `{'molecular_science_evidence': 1}` | `Refresh science actual closure audit evidence` |

## Release Surface First

| Path | Origin Wave | First Added | Recommended Primary Decision |
|---|---|---|---|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `science_release_surface_seed` | `805535fc 2026-06-30` | `delete_from_structural_repository` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `science_release_surface_seed` | `805535fc 2026-06-30` | `delete_from_structural_repository` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `pocketmd_release_surface_materialization` | `01e6fe1b 2026-06-30` | `delete_from_structural_repository` |

## Claim Boundary

This report explains how quarantined non-structural paths entered the repository. It does not approve retention, delete files, close owner review, or make any PocketMD/GPCR/MD3Bead artifact eligible for building structural-analysis release claims.
