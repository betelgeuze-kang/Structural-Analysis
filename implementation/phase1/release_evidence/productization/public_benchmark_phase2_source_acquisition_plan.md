# Public Benchmark Phase 2 Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `phase2_ready`: `False`
- `actual_closure_ready`: `False`
- `blocker_count`: `4`
- `official_source_receipt_plan_status`: `operator_receipts_required`
- `official_source_receipt_role_count`: `4`
- `official_source_catalog_count`: `6`
- `phase2_row_audit`: `implementation/phase1/release_evidence/productization/public_benchmark_phase2_row_audit.json`
- `phase2_row_audit_status`: `operator_evidence_required`
- `phase2_row_audit_missing_row_inputs`: `subset_rows, pose_rows, vina_gnina_rows`

| Row Input | Source Family | Status | Unblocks |
|---|---|---|---|
| `subset_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness` |
| `pose_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness`, `symmetry_aware_ligand_rmsd`, `posebusters_style_pose_validity` |
| `enrichment_rows` | `DUD-E/LIT-PCBA` | `operator_acquisition_required` | `dud_e_or_lit_pcba_enrichment` |
| `vina_gnina_rows` | `CASF/PDBBind + Vina/GNINA` | `operator_acquisition_required` | `vina_gnina_comparison_adapter` |

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
- `materialize_harness_bundle`: `python3 scripts/materialize_public_benchmark_harness_bundle.py --bundle implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json --out-dir implementation/phase1/release_evidence/productization --fail-blocked`
- `refresh_source_of_truth`: `python3 scripts/build_public_benchmark_source_of_truth.py --source-of-truth-out implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json`

This plan records the operator source acquisition contract for Public Benchmark Phase 2. It does not download, redistribute, license, or synthesize CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA evidence, and it does not close external beta until real rows and receipts pass the materializers.
