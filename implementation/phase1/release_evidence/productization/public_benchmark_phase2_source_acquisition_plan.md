# Public Benchmark Phase 2 Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `phase2_ready`: `False`
- `actual_closure_ready`: `False`
- `blocker_count`: `5`
- `official_source_receipt_plan_status`: `operator_receipts_required`
- `official_source_receipt_role_count`: `4`
- `official_source_catalog_count`: `6`
- `phase2_row_audit`: `implementation/phase1/release_evidence/productization/public_benchmark_phase2_row_audit.json`
- `phase2_row_audit_status`: `operator_evidence_required`
- `phase2_row_audit_missing_row_inputs`: `vina_gnina_rows`
- `phase2_row_audit_source_actuality_scope`: `provided_row_inputs_only`
- `phase2_row_audit_source_actuality_contract_pass`: `True`
- `phase2_row_audit_source_actuality_blocker_count`: `0`
- `missing_row_input_action_count`: `1`
- `vina_gnina_execution_plan`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `vina_gnina_execution_plan_status`: `engine_input_blocked`
- `vina_gnina_required_engine_run_count`: `24`
- `vina_gnina_input_manifest_status`: `not_detected`
- `vina_gnina_input_manifest_row_count`: `0`
- `vina_gnina_runtime_readiness`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `vina_gnina_runtime_readiness_status`: `execution_plan_blocked`
- `vina_gnina_runtime_ready_engine_run_slot_count`: `0`
- `vina_gnina_adapter_row_preflight_status`: `row_artifact_missing`
- `vina_gnina_runtime_missing_engine_ids`: `vina, gnina`

| Row Input | Source Family | Status | Unblocks |
|---|---|---|---|
| `subset_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness` |
| `pose_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness`, `symmetry_aware_ligand_rmsd`, `posebusters_style_pose_validity` |
| `enrichment_rows` | `DUD-E/LIT-PCBA` | `operator_acquisition_required` | `dud_e_or_lit_pcba_enrichment` |
| `vina_gnina_rows` | `CASF/PDBBind + Vina/GNINA` | `operator_acquisition_required` | `vina_gnina_comparison_adapter` |

## Missing Row Input Actions

| Row Input | Action | Unblocks | Materialization |
|---|---|---|---|
| `vina_gnina_rows` | `attach_vina_gnina_rows_then_run_phase2_row_audit` | `vina_gnina_comparison_adapter` | `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --fail-blocked` |

## Vina/GNINA Runtime

- `operator_unblock_status`: `engine_inputs_required`
- `input_manifest_template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv`
- `blocked_case_input_slot_count`: `12`
- `blocked_engine_run_slot_count`: `24`
- `adapter_row_preflight_status`: `row_artifact_missing`

| Engine | Container Status | Docker Daemon | Image Env Var | Image Present |
|---|---|---|---|---|
| `vina` | `container_image_not_configured` | `True` | `PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE` | `False` |
| `gnina` | `container_image_not_configured` | `True` | `PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE` | `False` |

## Source Receipt Roles

| Row Input | Receipt Role | Required Receipt Fields |
|---|---|---|
| `subset_rows` | `casf_pdbbind_subset_source_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref` |
| `pose_rows` | `casf_pdbbind_pose_coordinate_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref`, `pose_preparation_provenance_ref` |
| `enrichment_rows` | `dud_e_or_lit_pcba_enrichment_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref` |
| `vina_gnina_rows` | `vina_gnina_engine_comparison_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref`, `predicted_ligand_checksum`, `engine_config_checksum`, `engine_run_provenance_ref` |

## Official Source Catalog

| Source | Family | Feeds Row Inputs | Primary URL |
|---|---|---|---|
| `pdbbind_plus_casf` | `CASF/PDBBind` | `subset_rows`, `pose_rows`, `vina_gnina_rows` | https://www.pdbbind-plus.org.cn/casf |
| `dud_e` | `DUD-E` | `enrichment_rows` | https://dude.docking.org/targets/ |
| `lit_pcba` | `LIT-PCBA` | `enrichment_rows` | https://drugdesign.unistra.fr/LIT-PCBA/ |
| `autodock_vina` | `Vina` | `vina_gnina_rows` | https://vina.scripps.edu/ |
| `gnina` | `GNINA` | `vina_gnina_rows` | https://github.com/gnina/gnina |
| `posebusters` | `PoseBusters` | `pose_rows` | https://github.com/maabuu/posebusters |

## Commands

- `write_plan`: `python3 scripts/build_public_benchmark_phase2_source_acquisition_plan.py`
- `import_operator_bundle`: `python3 scripts/materialize_public_benchmark_operator_bundle_from_rows.py --subset-rows <operator-casf-pdbbind-subset-rows.jsonl> --pose-rows <operator-pose-coordinate-rows.jsonl> --enrichment-rows <operator-dud-e-lit-pcba-scored-molecule-rows.csv> --vina-gnina-rows <operator-vina-gnina-run-rows.csv> --target-subset-case-count 12 --out implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json`
- `phase2_row_audit`: `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --fail-blocked`
- `build_vina_gnina_execution_plan`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `check_vina_gnina_runtime_readiness`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `materialize_harness_bundle`: `python3 scripts/materialize_public_benchmark_harness_bundle.py --bundle implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json --out-dir implementation/phase1/release_evidence/productization --fail-blocked`
- `refresh_source_of_truth`: `python3 scripts/build_public_benchmark_source_of_truth.py --source-of-truth-out implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json`

This plan records the operator source acquisition contract for Public Benchmark Phase 2. It does not download, redistribute, license, or synthesize CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA evidence, and it does not close external beta until real rows and receipts pass the materializers.
