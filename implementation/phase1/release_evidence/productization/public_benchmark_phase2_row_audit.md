# Public Benchmark Phase 2 Row Audit

- `status`: `operator_evidence_required`
- `contract_pass`: `False`
- `phase2_ready`: `False`
- `component_ready_count`: `0/5`
- `missing_row_inputs`: `subset_rows, pose_rows, enrichment_rows, vina_gnina_rows`

| Row Input | Status | Feeds Components | Closes Criteria | Default Path |
|---|---|---|---|---|
| `subset_rows` | `missing` | `casf_pdbbind_pose_success_harness` | `casf_pdbbind_pose_success_harness_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` |
| `pose_rows` | `missing` | `symmetry_aware_ligand_rmsd, posebusters_style_pose_validity, casf_pdbbind_pose_success_harness` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` |
| `enrichment_rows` | `missing` | `dud_e_or_lit_pcba_enrichment` | `dud_e_or_lit_pcba_enrichment_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` |
| `vina_gnina_rows` | `missing` | `vina_gnina_comparison_adapter` | `vina_gnina_comparison_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |

| Component | Status | Failed Criteria | Blocker Count |
|---|---|---|---|
| `casf_pdbbind_pose_success_harness` | `operator_evidence_required` | `casf_pdbbind_pose_success_harness_ready` | `2` |
| `symmetry_aware_ligand_rmsd` | `operator_evidence_required` | `symmetry_aware_ligand_rmsd_ready` | `1` |
| `posebusters_style_pose_validity` | `operator_evidence_required` | `posebusters_style_pose_validity_ready` | `1` |
| `vina_gnina_comparison_adapter` | `operator_evidence_required` | `vina_gnina_comparison_ready` | `1` |
| `dud_e_or_lit_pcba_enrichment` | `operator_evidence_required` | `dud_e_or_lit_pcba_enrichment_ready` | `1` |

This runner only materializes operator-attached public benchmark row files through the existing Public Benchmark harness materializers. It does not download CASF/PDBBind, DUD-E, or LIT-PCBA data, approve licenses, run docking engines, infer chemistry, or treat fixture/proxy rows as actual Phase 2 evidence.
