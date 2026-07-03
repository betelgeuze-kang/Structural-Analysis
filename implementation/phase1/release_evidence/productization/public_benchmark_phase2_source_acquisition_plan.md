# Public Benchmark Phase 2 Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `phase2_ready`: `False`
- `actual_closure_ready`: `False`
- `blocker_count`: `5`

| Row Input | Source Family | Status | Unblocks |
|---|---|---|---|
| `subset_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness` |
| `pose_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness`, `symmetry_aware_ligand_rmsd`, `posebusters_style_pose_validity` |
| `enrichment_rows` | `DUD-E/LIT-PCBA` | `operator_acquisition_required` | `dud_e_or_lit_pcba_enrichment` |
| `vina_gnina_rows` | `CASF/PDBBind + Vina/GNINA` | `operator_acquisition_required` | `vina_gnina_comparison_adapter` |

## Commands

- `write_plan`: `python3 scripts/build_public_benchmark_phase2_source_acquisition_plan.py`
- `import_operator_bundle`: `python3 scripts/materialize_public_benchmark_operator_bundle_from_rows.py --subset-rows <operator-casf-pdbbind-subset-rows.jsonl> --pose-rows <operator-pose-coordinate-rows.jsonl> --enrichment-rows <operator-dud-e-lit-pcba-scored-molecule-rows.csv> --vina-gnina-rows <operator-vina-gnina-run-rows.csv> --target-subset-case-count 12 --out implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json`
- `phase2_row_audit`: `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --fail-blocked`
- `materialize_harness_bundle`: `python3 scripts/materialize_public_benchmark_harness_bundle.py --bundle implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json --out-dir implementation/phase1/release_evidence/productization --fail-blocked`
- `refresh_source_of_truth`: `python3 scripts/build_public_benchmark_source_of_truth.py --source-of-truth-out implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json`

This plan records the operator source acquisition contract for Public Benchmark Phase 2. It does not download, redistribute, license, or synthesize CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA evidence, and it does not close external beta until real rows and receipts pass the materializers.
