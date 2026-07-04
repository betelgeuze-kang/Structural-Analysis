# Public Benchmark Phase 2 Row Audit

- `status`: `operator_evidence_required`
- `contract_pass`: `False`
- `phase2_ready`: `False`
- `component_ready_count`: `4/5`
- `missing_row_inputs`: `vina_gnina_rows`
- `source_actuality_scope`: `provided_row_inputs_only`
- `source_actuality_contract_pass`: `True`
- `source_actuality_blocker_count`: `0`

| Row Input | Status | Feeds Components | Closes Criteria | Default Path |
|---|---|---|---|---|
| `subset_rows` | `provided` | `casf_pdbbind_pose_success_harness` | `casf_pdbbind_pose_success_harness_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` |
| `pose_rows` | `provided` | `symmetry_aware_ligand_rmsd, posebusters_style_pose_validity, casf_pdbbind_pose_success_harness` | `casf_pdbbind_pose_success_harness_ready, symmetry_aware_ligand_rmsd_ready, posebusters_style_pose_validity_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` |
| `enrichment_rows` | `provided` | `dud_e_or_lit_pcba_enrichment` | `dud_e_or_lit_pcba_enrichment_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` |
| `vina_gnina_rows` | `missing` | `vina_gnina_comparison_adapter` | `vina_gnina_comparison_ready` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` |

| Component | Status | Failed Criteria | Blocker Count |
|---|---|---|---|
| `casf_pdbbind_pose_success_harness` | `ready` | `none` | `0` |
| `symmetry_aware_ligand_rmsd` | `ready` | `none` | `0` |
| `posebusters_style_pose_validity` | `ready` | `none` | `0` |
| `vina_gnina_comparison_adapter` | `operator_evidence_required` | `vina_gnina_comparison_ready` | `1` |
| `dud_e_or_lit_pcba_enrichment` | `ready` | `none` | `0` |

## Phase 2 Completion Audit

- `status`: `blocked`
- `pass`: `False`
- `requirement_pass_count`: `4/6`

| Requirement | Status | Blockers |
|---|---|---|
| `casf_pdbbind_pose_success_harness_ready` | `pass` | `none` |
| `symmetry_aware_ligand_rmsd_ready` | `pass` | `none` |
| `posebusters_style_pose_validity_ready` | `pass` | `none` |
| `vina_gnina_comparison_ready` | `blocked` | `vina_gnina_rows_not_provided` |
| `dud_e_or_lit_pcba_enrichment_ready` | `pass` | `none` |
| `public_benchmark_source_actuality_ready` | `blocked` | `source_actuality_scope_incomplete:vina_gnina_rows` |

## Vina/GNINA Unblock

- `status`: `operator_runtime_or_rows_required`
- `rows_present`: `False`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json`
- `runtime_status`: `ready_for_engine_execution`
- `blocked_case_input_slot_count`: `0`
- `blocked_engine_run_slot_count`: `0`
- `first_operator_blocker_family`: `adapter_rows` / `attach_or_materialize_public_benchmark_vina_gnina_rows`
- `first_blocked_case_input_slot`: `` / `none`
- `first_blocked_engine_run_slot`: `` / `` / `none`

This runner only materializes operator-attached public benchmark row files through the existing Public Benchmark harness materializers. It does not download CASF/PDBBind, DUD-E, or LIT-PCBA data, approve licenses, run docking engines, infer chemistry, or treat fixture/proxy rows as actual Phase 2 evidence.
