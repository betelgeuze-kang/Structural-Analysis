# Public Benchmark Phase 2 Row Audit

- `status`: `ready`
- `contract_pass`: `True`
- `phase2_ready`: `True`
- `component_ready_count`: `5/5`
- `missing_row_inputs`: `none`
- `source_actuality_scope`: ``
- `source_actuality_contract_pass`: `True`
- `source_actuality_blocker_count`: `0`

| Row Input | Status | Feeds Components | Closes Criteria | Default Path |
|---|---|---|---|---|
| `subset_rows` | `provided` | `casf_pdbbind_pose_success_harness` | `casf_pdbbind_pose_success_harness_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` |
| `pose_rows` | `provided` | `symmetry_aware_ligand_rmsd, posebusters_style_pose_validity, casf_pdbbind_pose_success_harness` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` |
| `enrichment_rows` | `provided` | `dud_e_or_lit_pcba_enrichment` | `dud_e_or_lit_pcba_enrichment_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` |
| `vina_gnina_rows` | `provided` | `vina_gnina_comparison_adapter` | `vina_gnina_comparison_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |

| Component | Status | Failed Criteria | Blocker Count |
|---|---|---|---|
| `casf_pdbbind_pose_success_harness` | `ready` | `none` | `0` |
| `symmetry_aware_ligand_rmsd` | `ready` | `none` | `0` |
| `posebusters_style_pose_validity` | `ready` | `none` | `0` |
| `vina_gnina_comparison_adapter` | `ready` | `none` | `0` |
| `dud_e_or_lit_pcba_enrichment` | `ready` | `none` | `0` |

## Phase 2 Completion Audit

- `status`: `pass`
- `pass`: `True`
- `requirement_pass_count`: `6/6`

| Requirement | Status | Blockers |
|---|---|---|
| `casf_pdbbind_pose_success_harness_ready` | `pass` | `none` |
| `symmetry_aware_ligand_rmsd_ready` | `pass` | `none` |
| `posebusters_style_pose_validity_ready` | `pass` | `none` |
| `vina_gnina_comparison_ready` | `pass` | `none` |
| `dud_e_or_lit_pcba_enrichment_ready` | `pass` | `none` |
| `public_benchmark_source_actuality_ready` | `pass` | `none` |

## Vina/GNINA Unblock

- `status`: `rows_detected_review_adapter`
- `rows_present`: `True`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json`
- `runtime_status`: `adapter_materialization_ready`
- `blocked_case_input_slot_count`: `0`
- `blocked_engine_run_slot_count`: `0`
- `first_operator_blocker_family`: `` / ``
- `first_blocked_case_input_slot`: `` / `none`
- `first_blocked_engine_run_slot`: `` / `` / `none`

This runner only materializes operator-attached public benchmark row files through the existing Public Benchmark harness materializers. It does not download CASF/PDBBind, DUD-E, or LIT-PCBA data, approve licenses, run docking engines, infer chemistry, or treat fixture/proxy rows as actual Phase 2 evidence.
