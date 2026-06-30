# Public Benchmark Operator Intake Packet

- `contract_pass`: `True`
- `status`: `ready_for_operator_input`
- `public_benchmark_ready`: `False`
- `source_of_truth_status`: `seed_ready_materialization_blocked`
- `source_of_truth_blocker_count`: `10`
- `claim_boundary`: This packet is an owner-facing intake contract for public benchmark evidence. It does not attach CASF/PDBBind, DUD-E, or LIT-PCBA source files, does not redistribute benchmark data, does not infer ligand chemistry, and does not close Tier beta without materialized real benchmark rows.

| Slot | Status | Intake Artifact | Validation Command |
|---|---|---|---|
| `casf_pdbbind_subset_intake` | `operator_input_required` | `<operator-casf-pdbbind-intake.json>` | `python3 scripts/validate_public_benchmark_subset_manifest.py --manifest implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json --fail-blocked` |
| `pose_coordinate_intake` | `operator_input_required` | `<operator-pose-coordinate-intake.json>` | `python3 scripts/validate_public_benchmark_pose_validity.py --input implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_input.json --fail-blocked` |
| `dud_e_lit_pcba_enrichment_intake` | `operator_input_required` | `<operator-dud-e-lit-pcba-enrichment-intake.json>` | `python3 scripts/materialize_public_benchmark_enrichment_scorecard.py --intake <operator-dud-e-lit-pcba-enrichment-intake.json> --out-scorecard implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_enrichment_materialization_report.json --fail-blocked` |
| `vina_gnina_comparison_intake` | `operator_input_required` | `<operator-vina-gnina-comparison-intake.json>` | `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-comparison-intake.json> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked` |

## Gate Unblock Plan

| Slot | Criteria | Minimum Evidence |
|---|---|---|
| `casf_pdbbind_subset_intake` | `casf_pdbbind_subset_materialized`, `external_receipts_attached` | `{"case_count": 12, "ligand_atom_order_contract_fields": ["atom_count", "atom_ids"], "local_source_file_fields": ["protein_structure_path", "reference_ligand_path", "predicted_ligand_path_or_docking_run_id"], "materialized_manifest_fields": ["source_file_checksums"], "receipt_fields": ["source_license_or_accession", "source_checksum", "provenance_ref"], "source_family": "CASF/PDBBind", "supported_benchmark_splits": ["CASF-core", "PDBBind-core", "PDBBind-refined", "PDBBind-general"], "symmetry_permutation_contract_fields": ["permutations"]}` |
| `pose_coordinate_intake` | `real_pose_validity_packet_materialized`, `symmetry_rmsd_scorecard_real_cases`, `posebusters_style_validity_real_ligands`, `casf_pdbbind_pose_success_harness_ready` | `{"benchmark_split_source": "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json", "case_count": 12, "case_id_source": "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json", "coordinate_contract": "reference_atoms and predicted_atoms in the declared ligand atom order"}` |
| `dud_e_lit_pcba_enrichment_intake` | `dud_e_lit_pcba_enrichment_ready`, `external_receipts_attached` | `{"family_coverage_fields": ["benchmark_family_target_counts", "covered_supported_family_count", "missing_supported_families"], "ready_target_count": 1, "receipt_fields": ["source_license_or_accession", "source_checksum", "provenance_ref"], "required_molecule_fields": ["molecule_id", "is_active", "score"], "source_checksum_policy": {"accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>", "required_receipt_field": "source_checksum"}, "supported_families": ["DUD-E", "LIT-PCBA"]}` |
| `vina_gnina_comparison_intake` | `vina_gnina_comparison_ready`, `external_receipts_attached` | `{"benchmark_split_source": "implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json", "comparison_case_count": 1, "receipt_fields": ["source_license_or_accession", "source_checksum", "provenance_ref"], "required_engine_run_fields": ["engine_id", "docking_run_id", "predicted_ligand_path_or_pose_ref", "symmetry_aware_rmsd_angstrom", "pose_success", "score", "score_direction"], "required_engines": ["vina", "gnina"], "source_checksum_policy": {"accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>", "required_receipt_field": "source_checksum"}, "supported_benchmark_splits": ["CASF-core", "PDBBind-core", "PDBBind-refined", "PDBBind-general"]}` |

## Execution Preflight

| Step | Ready | Dependency Ready | First Blocker |
|---|---|---|---|
| `materialize_subset_manifest` | `False` | `True` | `casf_pdbbind_source_material_not_attached` |
| `materialize_pose_validity_input` | `False` | `False` | `public_benchmark_real_pose_predictions_missing` |
| `materialize_posebusters_validity_packet` | `False` | `False` | `public_benchmark_real_pose_predictions_missing` |
| `materialize_symmetry_rmsd_scorecard` | `False` | `False` | `public_benchmark_real_pose_predictions_missing` |
| `materialize_pose_success_harness` | `False` | `False` | `public_benchmark_real_pose_predictions_missing` |
| `materialize_enrichment_scorecard` | `False` | `True` | `dud_e_lit_pcba_enrichment_targets_missing` |
| `materialize_vina_gnina_comparison_adapter` | `False` | `False` | `vina_gnina_comparison_cases_missing` |
| `validate_external_receipts` | `False` | `False` | `public_benchmark_external_receipts_missing` |
| `refresh_public_benchmark_source_of_truth` | `False` | `False` | `casf_pdbbind_source_material_not_attached` |

## Materialization Sequence

- `materialize_subset_manifest`: `python3 scripts/materialize_public_benchmark_subset_manifest.py --intake <operator-casf-pdbbind-intake.json> --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_subset_materialization_report.json --fail-blocked`
- `materialize_pose_validity_input`: `python3 scripts/materialize_public_benchmark_pose_validity_input.py --subset-manifest implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json --pose-intake <operator-pose-coordinate-intake.json> --out-input implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_input.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_materialization_report.json --fail-blocked`
- `materialize_posebusters_validity_packet`: `python3 scripts/materialize_public_benchmark_posebusters_validity_packet.py --pose-validity-input implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_input.json --out-packet implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_posebusters_validity_materialization_report.json --fail-blocked`
- `materialize_symmetry_rmsd_scorecard`: `python3 scripts/materialize_public_benchmark_rmsd_scorecard.py --pose-validity-input implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_input.json --out-scorecard implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_materialization_report.json --fail-blocked`
- `materialize_pose_success_harness`: `python3 scripts/materialize_public_benchmark_pose_success_harness.py --pose-validity-packet implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json --rmsd-scorecard implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json --out-harness implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness_materialization_report.json --fail-blocked`
- `materialize_enrichment_scorecard`: `python3 scripts/materialize_public_benchmark_enrichment_scorecard.py --intake <operator-dud-e-lit-pcba-enrichment-intake.json> --out-scorecard implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_enrichment_materialization_report.json --fail-blocked`
- `materialize_vina_gnina_comparison_adapter`: `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-comparison-intake.json> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked`
- `validate_external_receipts`: `python3 scripts/validate_public_benchmark_external_receipts.py --subset-manifest implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json --enrichment-scorecard implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json --vina-gnina-comparison-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out implementation/phase1/release_evidence/productization/public_benchmark_external_receipts_validation.json --fail-blocked`
- `refresh_public_benchmark_source_of_truth`: `python3 scripts/build_public_benchmark_source_of_truth.py --source-of-truth-out implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json --subset-manifest-out implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json --pose-validity-packet-out implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json --rmsd-scorecard-out implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json --pose-success-harness-out implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness.json --enrichment-scorecard-out implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json --vina-gnina-comparison-adapter-out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --external-receipts-validation-out implementation/phase1/release_evidence/productization/public_benchmark_external_receipts_validation.json`

## Acceptance Criteria

- `public_benchmark_subset_manifest.materialized_case_count >= 12`
- `public_benchmark_subset_manifest.public_benchmark_ready == true`
- `public_benchmark_pose_validity_input.pose_validity_ready == true`
- `public_benchmark_pose_validity_input.real_benchmark_case_count >= 12`
- `public_benchmark_pose_validity_packet.real_benchmark_case_count >= 12`
- `public_benchmark_pose_validity_packet.posebusters_validity_ready == true`
- `public_benchmark_symmetry_rmsd_scorecard.real_benchmark_case_count >= 12`
- `public_benchmark_symmetry_rmsd_scorecard.scorecard_ready == true`
- `public_benchmark_pose_success_harness.real_benchmark_case_count >= 12`
- `public_benchmark_pose_success_harness.pose_success_harness_ready == true`
- `public_benchmark_enrichment_scorecard.public_benchmark_enrichment_ready == true`
- `public_benchmark_vina_gnina_comparison_adapter.public_benchmark_engine_comparison_ready == true`
- `public_benchmark_external_receipts_validation.public_benchmark_external_receipts_ready == true`
- `public_benchmark_source_of_truth.public_benchmark_ready == true`
