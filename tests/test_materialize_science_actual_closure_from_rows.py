from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_science_actual_closure_from_rows.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("materialize_science_actual_closure_from_rows", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(case_id: str, candidate_id: str) -> str:
    return (
        "https://zenodo.org/records/2468135/files/"
        f"pocketmd-lite-{case_id}-{candidate_id}.json#row"
    )


def _upstream_top_k_provenance_ref(case_id: str, candidate_id: str) -> str:
    return (
        "https://zenodo.org/records/2468135/files/"
        f"pocketmd-lite-upstream-topk-{case_id}-{candidate_id}.json#row"
    )


def _write_gpcr_rows(path: Path) -> None:
    fieldnames = [
        "target_id",
        "score_direction",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
        "source_checksum",
        "provenance_ref",
    ]
    rows = []
    for target_id in ("DRD2", "HTR2A", "OPRM1"):
        for index in range(1, 5):
            molecule_id = f"{target_id}_positive_{index}"
            rows.append(
                [
                    target_id,
                    "higher_is_better",
                    molecule_id,
                    f"{1.0 - index / 100:.2f}",
                    "true",
                    "false",
                    _sha(f"{target_id}:{molecule_id}"),
                    (
                        "https://zenodo.org/records/2468135/files/"
                        f"gpcr-hard-decoy-{target_id}-{molecule_id}.json#row"
                    ),
                ]
            )
        for index in range(1, 21):
            molecule_id = f"{target_id}_decoy_{index}"
            rows.append(
                [
                    target_id,
                    "higher_is_better",
                    molecule_id,
                    f"{0.50 - index / 100:.2f}",
                    "false",
                    "true",
                    _sha(f"{target_id}:{molecule_id}"),
                    (
                        "https://zenodo.org/records/2468135/files/"
                        f"gpcr-hard-decoy-{target_id}-{molecule_id}.json#row"
                    ),
                ]
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        writer.writerows(rows)


def _pocketmd_row(
    *,
    case_id: str,
    candidate_id: str,
    rank: int,
    local_min_survived: bool,
    contact_rate: float,
    h_bond_rate: float,
    clash_before: int,
    clash_after: int,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "source_family": "CASF/PDBBind operator intake",
        "top_k_rank": rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": -8.0 + rank,
        "post_refinement_energy_proxy": -8.5 + rank,
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "uncertainty_low": -0.2 + rank / 10,
        "uncertainty_high": 0.2 + rank / 10,
        "uncertainty_unit": "energy_proxy_delta",
        "upstream_top_k_provenance_ref": _upstream_top_k_provenance_ref(
            case_id,
            candidate_id,
        ),
        "upstream_top_k_source_checksum": _sha(
            f"upstream-topk:{case_id}:{candidate_id}"
        ),
        "provenance_ref": _provenance_ref(case_id, candidate_id),
        "source_checksum": _sha(f"{case_id}:{candidate_id}"),
    }


def _write_pocketmd_rows(path: Path) -> None:
    payload = {
        "top_k_refinement_rows": [
            _pocketmd_row(
                case_id="case_a",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=0.8,
                h_bond_rate=0.6,
                clash_before=4,
                clash_after=1,
            ),
            _pocketmd_row(
                case_id="case_a",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
            _pocketmd_row(
                case_id="case_b",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=1.0,
                h_bond_rate=0.9,
                clash_before=5,
                clash_after=3,
            ),
            _pocketmd_row(
                case_id="case_b",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
            _pocketmd_row(
                case_id="case_c",
                candidate_id="pose_1",
                rank=1,
                local_min_survived=True,
                contact_rate=0.8,
                h_bond_rate=0.6,
                clash_before=4,
                clash_after=1,
            ),
            _pocketmd_row(
                case_id="case_c",
                candidate_id="pose_2",
                rank=2,
                local_min_survived=False,
                contact_rate=0.7,
                h_bond_rate=0.4,
                clash_before=2,
                clash_after=2,
            ),
        ]
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _write_case_files(root: Path, case_id: str) -> dict[str, str]:
    case_dir = root / "benchmarks" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "protein_structure_path": case_dir / "protein.pdb",
        "reference_ligand_path": case_dir / "ligand_ref.sdf",
        "predicted_ligand_path_or_docking_run_id": case_dir / "pose_pred.sdf",
    }
    for field, path in files.items():
        path.write_text(f"{case_id}:{field}\n", encoding="utf-8")
    return {field: path.relative_to(root).as_posix() for field, path in files.items()}


def _write_public_phase2_rows(root: Path) -> dict[str, Path]:
    case_count = module.public_phase2.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
    case_ids = [f"case_{index:02d}" for index in range(1, case_count + 1)]
    ligand_contract = {"atom_count": 2, "atom_ids": ["C1", "O1"]}
    symmetry_contract = {"permutations": [[0, 1]]}
    reference_atoms = [
        {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 1.2, "y": 0.0, "z": 0.0},
    ]
    predicted_atoms = [
        {"element": "C", "x": 0.1, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 1.3, "y": 0.0, "z": 0.0},
    ]
    subset_rows = root / "public_benchmark_subset_rows.json"
    pose_rows = root / "public_benchmark_pose_rows.json"
    enrichment_rows = root / "public_benchmark_enrichment_rows.json"
    vina_gnina_rows = root / "public_benchmark_vina_gnina_rows.json"

    subset_rows.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "case_id": case_id,
                        "source_family": "CASF/PDBBind",
                        "benchmark_split": "CASF-core",
                        "complex_id": f"{case_id}_complex",
                        **_write_case_files(root, case_id),
                        "ligand_atom_order_contract": ligand_contract,
                        "symmetry_permutation_contract": symmetry_contract,
                        "source_license_or_accession": (
                            f"PDBBind-CASF-2016-core:{case_id}"
                        ),
                        "source_checksum": _sha(
                            f"PDBBind-CASF-2016-core:{case_id}"
                        ),
                        "provenance_ref": (
                            "https://zenodo.org/records/2468135/files/"
                            f"public-benchmark/casf-pdbbind/{case_id}.json"
                        ),
                        "pose_success_metric": (
                            "symmetry_aware_ligand_rmsd_angstrom"
                        ),
                        "rmsd_threshold_angstrom": 2.0,
                    }
                    for case_id in case_ids
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    pose_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": case_id,
                        "benchmark_split": "CASF-core",
                        "pose_success_metric": (
                            "symmetry_aware_ligand_rmsd_angstrom"
                        ),
                        "reference_atoms": reference_atoms,
                        "predicted_atoms": predicted_atoms,
                        "ligand_atom_order_contract": ligand_contract,
                        "symmetry_permutation_contract": symmetry_contract,
                        "protein_structure_path": f"benchmarks/{case_id}/protein.pdb",
                        "receptor_context": {
                            "binding_site_frame": "validated_receptor_frame",
                            "provenance_ref": (
                                "https://zenodo.org/records/2468135/files/"
                                f"public-benchmark/pose/{case_id}.json"
                            ),
                        },
                    }
                    for case_id in case_ids
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    enrichment_rows.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "benchmark_family": "DUD-E",
                        "target_id": "AA2AR",
                        "score_direction": "higher_is_better",
                        "source_license_or_accession": "DUD-E:AA2AR:release-2015",
                        "source_checksum": _sha("DUD-E:AA2AR:release-2015"),
                        "provenance_ref": (
                            "https://zenodo.org/records/2468135/files/"
                            "public-benchmark/dud-e/AA2AR.json"
                        ),
                        "scored_molecules": [
                            {"molecule_id": "active_1", "is_active": True, "score": 0.9},
                            {"molecule_id": "decoy_1", "is_active": False, "score": 0.1},
                        ],
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    vina_gnina_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": case_ids[0],
                        "source_family": "CASF/PDBBind",
                        "benchmark_split": "CASF-core",
                        "complex_id": f"{case_ids[0]}_complex",
                        "reference_pose_id": f"{case_ids[0]}_reference",
                        "source_license_or_accession": (
                            f"PDBBind-CASF-2016-core:{case_ids[0]}"
                        ),
                        "source_checksum": _sha("vina-gnina-case-a"),
                        "provenance_ref": (
                            "https://zenodo.org/records/2468135/files/"
                            f"public-benchmark/vina-gnina/{case_ids[0]}.json"
                        ),
                        "engine_runs": [
                            {
                                "engine_id": "vina",
                                "docking_run_id": f"{case_ids[0]}_vina",
                                "predicted_ligand_path_or_pose_ref": (
                                    "https://zenodo.org/records/2468135/files/"
                                    f"public-benchmark/vina-gnina/{case_ids[0]}/vina.sdf"
                                ),
                                "predicted_ligand_checksum": _sha(
                                    f"{case_ids[0]}-vina-pose"
                                ),
                                "engine_version": "vina 1.2.5",
                                "engine_config_checksum": _sha(
                                    f"{case_ids[0]}-vina-config"
                                ),
                                "engine_run_provenance_ref": (
                                    "https://zenodo.org/records/2468135/files/"
                                    f"public-benchmark/vina-gnina/{case_ids[0]}/vina-run.json"
                                ),
                                "symmetry_aware_rmsd_angstrom": 1.4,
                                "pose_success": True,
                                "score": -7.2,
                                "score_direction": "lower_is_better",
                            },
                            {
                                "engine_id": "gnina",
                                "docking_run_id": f"{case_ids[0]}_gnina",
                                "predicted_ligand_path_or_pose_ref": (
                                    "https://zenodo.org/records/2468135/files/"
                                    f"public-benchmark/vina-gnina/{case_ids[0]}/gnina.sdf"
                                ),
                                "predicted_ligand_checksum": _sha(
                                    f"{case_ids[0]}-gnina-pose"
                                ),
                                "engine_version": "gnina 1.3.0",
                                "engine_config_checksum": _sha(
                                    f"{case_ids[0]}-gnina-config"
                                ),
                                "engine_run_provenance_ref": (
                                    "https://zenodo.org/records/2468135/files/"
                                    f"public-benchmark/vina-gnina/{case_ids[0]}/gnina-run.json"
                                ),
                                "symmetry_aware_rmsd_angstrom": 1.6,
                                "pose_success": True,
                                "score": -7.8,
                                "score_direction": "lower_is_better",
                            },
                        ],
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "subset": subset_rows,
        "pose": pose_rows,
        "enrichment": enrichment_rows,
        "vina_gnina": vina_gnina_rows,
    }


def _public_output_kwargs(tmp_path: Path) -> dict[str, Path]:
    return {
        "public_phase2_audit_out": tmp_path / "public_phase2_audit.json",
        "public_operator_bundle_out": tmp_path / "public_operator_bundle.json",
        "public_out_dir": tmp_path / "public_out",
        "public_harness_report_out": tmp_path / "public_harness_report.json",
        "public_artifact_bundle_out": tmp_path / "public_artifact_bundle.json",
    }


def test_science_actual_closure_audit_blocks_without_operator_rows(tmp_path: Path) -> None:
    audit = module.build_science_actual_closure_audit(
        repo_root=tmp_path,
        **_public_output_kwargs(tmp_path),
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["component_ready_count"] == 0
    assert audit["blockers"] == [
        "public_benchmark_phase2_actual_closure::casf_pdbbind_pose_success_harness::subset_rows_not_provided",
        "public_benchmark_phase2_actual_closure::casf_pdbbind_pose_success_harness::pose_rows_not_provided",
        "public_benchmark_phase2_actual_closure::symmetry_aware_ligand_rmsd::pose_rows_not_provided",
        "public_benchmark_phase2_actual_closure::posebusters_style_pose_validity::pose_rows_not_provided",
        "public_benchmark_phase2_actual_closure::vina_gnina_comparison_adapter::vina_gnina_rows_not_provided",
        "public_benchmark_phase2_actual_closure::dud_e_or_lit_pcba_enrichment::enrichment_rows_not_provided",
        "gpcr_hard_decoy_actual_closure::gpcr_hard_decoy_rows_not_provided",
        "pocketmd_lite_topk_actual_closure::pocketmd_lite_topk_rows_not_provided",
    ]
    assert audit["summary"]["requirement_count"] == 19
    assert audit["summary"]["blocked_requirement_count"] == 18
    assert audit["summary"]["passing_requirement_count"] == 1
    assert audit["summary"]["actual_closure_ready"] is False
    assert audit["missing_row_inputs"] == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
        "gpcr_rows",
        "pocketmd_rows",
    ]
    assert audit["row_input_resolution"]["subset_rows"]["missing"] is True
    assert audit["row_input_resolution"]["pose_rows"]["missing"] is True
    assert audit["row_input_resolution"]["enrichment_rows"]["missing"] is True
    assert audit["row_input_resolution"]["vina_gnina_rows"]["missing"] is True
    assert audit["row_input_resolution"]["gpcr_rows"]["missing"] is True
    assert audit["row_input_resolution"]["pocketmd_rows"]["missing"] is True
    requirement_summary = audit["actual_closure_requirement_summary"]
    assert requirement_summary["public_benchmark_phase2_requirement_count"] == 5
    assert requirement_summary["public_benchmark_phase2_passing_requirement_count"] == 0
    assert requirement_summary["gpcr_phase3_requirement_count"] == 5
    assert requirement_summary["gpcr_phase3_passing_requirement_count"] == 0
    assert requirement_summary["pocketmd_phase4_requirement_count"] == 9
    assert requirement_summary["pocketmd_phase4_passing_requirement_count"] == 1
    assert requirement_summary["blocked_component_ids"] == [
        "gpcr_hard_decoy_actual_closure",
        "pocketmd_lite_topk_actual_closure",
        "public_benchmark_phase2_actual_closure",
    ]
    assert audit["required_actual_closures"] == [
        "public_benchmark_phase2_actual_closure",
        "gpcr_hard_decoy_actual_closure",
        "pocketmd_lite_topk_actual_closure",
    ]
    component_summaries = {
        row["component_id"]: row["requirement_summary"]
        for row in audit["components"]
    }
    assert audit["component_requirement_summaries"] == [
        component_summaries["public_benchmark_phase2_actual_closure"],
        component_summaries["gpcr_hard_decoy_actual_closure"],
        component_summaries["pocketmd_lite_topk_actual_closure"],
    ]
    assert component_summaries["public_benchmark_phase2_actual_closure"] == {
        "actual_closure_ready": False,
        "blocked_requirement_count": 5,
        "blocker_count": 6,
        "component_id": "public_benchmark_phase2_actual_closure",
        "failed_criteria": [
            "casf_pdbbind_pose_success_harness_ready",
            "symmetry_aware_ligand_rmsd_ready",
            "posebusters_style_pose_validity_ready",
            "vina_gnina_comparison_ready",
            "dud_e_or_lit_pcba_enrichment_ready",
        ],
        "failed_criterion_count": 5,
        "passing_requirement_count": 0,
        "requirement_count": 5,
    }
    assert component_summaries["gpcr_hard_decoy_actual_closure"] == {
        "actual_closure_ready": False,
        "blocked_requirement_count": 5,
        "blocker_count": 15,
        "component_id": "gpcr_hard_decoy_actual_closure",
        "failed_criteria": [
            "ranking_pr_auc_ci_low_min",
            "top20_hit_rate_min",
            "decoys_above_positive_count_max",
            "no_positive_out_anchored_by_top_decoys",
            "raw_hard_decoy_rows_actual_closure",
        ],
        "failed_criterion_count": 5,
        "passing_requirement_count": 0,
        "requirement_count": 5,
    }
    assert audit["components"][0]["actual_closure_ready"] is False
    assert audit["components"][0]["failed_criteria"] == [
        "casf_pdbbind_pose_success_harness_ready",
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
        "vina_gnina_comparison_ready",
        "dud_e_or_lit_pcba_enrichment_ready",
    ]
    assert audit["components"][1]["actual_closure_ready"] is False
    assert audit["components"][1]["failed_criteria"] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
        "raw_hard_decoy_rows_actual_closure",
    ]
    assert component_summaries["pocketmd_lite_topk_actual_closure"] == {
        "actual_closure_ready": False,
        "blocked_requirement_count": 8,
        "blocker_count": 13,
        "component_id": "pocketmd_lite_topk_actual_closure",
        "failed_criteria": [
            "top_k_refinement_rows_present",
            "top_k_refinement_case_coverage",
            "local_min_survival_materialized",
            "contact_persistence_materialized",
            "h_bond_persistence_materialized",
            "clash_relief_materialized",
            "uncertainty_summary_materialized",
            "report_blockers_resolved",
        ],
        "failed_criterion_count": 8,
        "passing_requirement_count": 1,
        "requirement_count": 9,
    }
    assert audit["components"][2]["actual_closure_ready"] is False
    assert audit["components"][2]["failed_criteria"] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
    ]
    gpcr_requirements = [
        row
        for row in audit["actual_closure_requirements"]
        if row["component_id"] == "gpcr_hard_decoy_actual_closure"
    ]
    assert [row["criterion_id"] for row in gpcr_requirements] == [
        "ranking_pr_auc_ci_low_min",
        "top20_hit_rate_min",
        "decoys_above_positive_count_max",
        "no_positive_out_anchored_by_top_decoys",
        "raw_hard_decoy_rows_actual_closure",
    ]
    assert gpcr_requirements[0]["required"] == ">=0.45"
    assert gpcr_requirements[0]["failed_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert gpcr_requirements[-1]["current_by_target"] == {
        "DRD2": "missing",
        "HTR2A": "missing",
        "OPRM1": "missing",
    }
    pocketmd_requirements = [
        row
        for row in audit["actual_closure_requirements"]
        if row["component_id"] == "pocketmd_lite_topk_actual_closure"
    ]
    assert [row["criterion_id"] for row in pocketmd_requirements] == [
        "top_k_refinement_rows_present",
        "top_k_refinement_case_coverage",
        "local_min_survival_materialized",
        "contact_persistence_materialized",
        "h_bond_persistence_materialized",
        "clash_relief_materialized",
        "uncertainty_summary_materialized",
        "report_blockers_resolved",
        "broad_all_atom_fep_claims_locked",
    ]
    assert pocketmd_requirements[0]["required"] == ">=6"
    assert pocketmd_requirements[-1]["pass"] is True
    assert "broad_all_atom_md_claim" in (
        pocketmd_requirements[-1]["blocked_claims_that_remain_locked"]
    )
    gpcr_contract = audit["row_intake_contracts"]["gpcr_rows"]
    assert gpcr_contract["required_targets"] == ["DRD2", "HTR2A", "OPRM1"]
    assert gpcr_contract["default_row_path_candidates"][0].endswith(
        "gpcr_hard_decoy_rows.json"
    )
    assert gpcr_contract["phase3_exit_criteria"] == {
        "decoys_above_positive_count_max": 0,
        "positive_out_anchored_by_top_decoys_allowed": False,
        "ranking_pr_auc_ci_low_min": 0.45,
        "top20_hit_rate_min": 0.2,
    }
    assert gpcr_contract["raw_row_quality_minimums"] == {
        "min_decoy_count_per_target": 20,
        "min_positive_count_per_target": 4,
        "min_total_row_count_per_target": 24,
    }
    assert gpcr_contract["numeric_value_policy"] == {
        "score": "must parse to a finite float; NaN and Infinity are rejected",
    }
    assert gpcr_contract["boolean_label_policy"] == {
        "is_decoy": (
            "must parse to a boolean; exactly one of is_positive/is_decoy "
            "must be true per molecule row"
        ),
        "is_positive": (
            "must parse to a boolean; exactly one of is_positive/is_decoy "
            "must be true per molecule row"
        ),
    }
    assert gpcr_contract["score_direction_policy"].startswith(
        "Each target must use one consistent score_direction value"
    )
    assert gpcr_contract["unexpected_target_policy"].startswith(
        "Rows for targets outside the required DRD2/HTR2A/OPRM1 set"
    )
    assert gpcr_contract["row_integrity_policy"]["required_unique_row_keys"] == {
        "raw_hard_decoy_rows": ["target_id", "molecule_id"],
    }
    assert gpcr_contract["required_flat_row_fields"] == [
        "target_id",
        "molecule_id",
        "score",
        "is_positive",
        "is_decoy",
    ]
    assert gpcr_contract["source_receipt_required_fields"] == [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact_sha256",
    ]
    assert gpcr_contract["source_actuality_policy"][
        "placeholder_source_url_prefixes_rejected"
    ] == [
        "operator://",
        "local-evidence://",
        "local://",
        "fixture://",
        "mock://",
        "synthetic://",
        "placeholder://",
        "test://",
        "unit-test://",
        "file://",
    ]
    assert "fixture" in gpcr_contract["source_actuality_policy"][
        "placeholder_source_text_markers_rejected"
    ]
    assert gpcr_contract["source_actuality_policy"][
        "source_artifact_sha256_policy"
    ] == (
        "sha256:<64 hex> and must match the attached raw hard-decoy row artifact"
    )
    pocketmd_contract = audit["row_intake_contracts"]["pocketmd_rows"]
    assert pocketmd_contract["default_row_path_candidates"][0].endswith(
        "pocketmd_lite_topk_rows.json"
    )
    assert "h_bond_persistence_rate" in pocketmd_contract["required_case_fields"]
    assert "uncertainty_width_median" in (
        pocketmd_contract["required_component_metrics"]
    )
    assert pocketmd_contract["top_k_row_quality_minimums"] == {
        "min_candidate_count_per_case": 2,
        "min_real_refinement_case_count": 3,
        "min_top_k_rank_coverage_per_case": 2,
        "min_total_top_k_candidate_count": 6,
    }
    assert pocketmd_contract["top_k_rank_prefix_policy"].startswith(
        "For each case, supplied ranks must form a contiguous prefix"
    )
    assert pocketmd_contract["numeric_value_policy"] == {
        "contact_persistence_rate": (
            "must parse to a finite float in [0, 1]; NaN and Infinity are rejected"
        ),
        "h_bond_persistence_rate": (
            "must parse to a finite float in [0, 1]; NaN and Infinity are rejected"
        ),
        "post_refinement_energy_proxy": (
            "must parse to a finite float; NaN and Infinity are rejected"
        ),
        "pre_refinement_energy_proxy": (
            "must parse to a finite float; NaN and Infinity are rejected"
        ),
        "uncertainty_interval.high": (
            "must parse to a finite float and be >= low; NaN and Infinity are rejected"
        ),
        "uncertainty_interval.low": (
            "must parse to a finite float; NaN and Infinity are rejected"
        ),
    }
    assert pocketmd_contract["integer_value_policy"] == {
        "clash_count_after": "must parse to a non-negative integer",
        "clash_count_before": "must parse to a non-negative integer",
        "top_k_rank": (
            "must parse to a positive integer <= max_top_k and form a "
            "contiguous rank prefix starting at 1 for each case"
        ),
    }
    assert pocketmd_contract["boolean_value_policy"] == {
        "local_min_survived": "must parse to a boolean value",
    }
    assert pocketmd_contract["row_integrity_policy"]["required_unique_row_keys"] == {
        "top_k_refinement_rows": [
            ["case_id", "top_k_rank"],
            ["case_id", "candidate_id"],
        ],
    }
    assert pocketmd_contract["source_receipt_required_fields"] == [
        "source_id",
        "source_url",
        "source_license",
        "source_artifact_sha256",
        "per_row_source_checksum",
        "per_row_provenance_ref",
    ]
    assert pocketmd_contract["per_row_source_actuality_policy"][
        "placeholder_provenance_prefixes_rejected"
    ] == [
        "operator://",
        "local-evidence://",
        "local://",
        "fixture://",
        "mock://",
        "synthetic://",
        "placeholder://",
        "test://",
        "unit-test://",
    ]
    assert "broad_all_atom_md_claim" in (
        pocketmd_contract["blocked_claims_that_remain_locked"]
    )
    subset_contract = audit["row_intake_contracts"]["subset_rows"]
    assert subset_contract["default_row_path_candidates"][0].endswith(
        "public_benchmark_subset_rows.json"
    )
    assert "casf_pdbbind_pose_success_harness" in subset_contract["feeds_components"]
    assert not (tmp_path / "gpcr_report.json").exists()
    assert not (tmp_path / "pocketmd_report.json").exists()


def test_science_actual_closure_audit_materializes_both_ready_surfaces(
    tmp_path: Path,
) -> None:
    public_rows = _write_public_phase2_rows(tmp_path)
    gpcr_rows = tmp_path / "gpcr_rows.csv"
    pocketmd_rows = tmp_path / "pocketmd_rows.json"
    pocketmd_contract = tmp_path / "pocketmd_contract.json"
    _write_gpcr_rows(gpcr_rows)
    _write_pocketmd_rows(pocketmd_rows)
    pocketmd_contract.write_text(
        json.dumps({"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True}),
        encoding="utf-8",
    )

    audit = module.build_science_actual_closure_audit(
        repo_root=tmp_path,
        subset_rows_path=public_rows["subset"],
        pose_rows_path=public_rows["pose"],
        enrichment_rows_path=public_rows["enrichment"],
        vina_gnina_rows_path=public_rows["vina_gnina"],
        **_public_output_kwargs(tmp_path),
        gpcr_rows_path=gpcr_rows,
        pocketmd_rows_path=pocketmd_rows,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
        pocketmd_contract_path=pocketmd_contract,
        source_id="operator_attached_science_actual_closure_rows",
        source_url="https://zenodo.org/records/2468135",
        source_license="CC-BY-4.0",
    )

    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["component_ready_count"] == 3
    assert audit["blockers"] == []
    assert audit["missing_row_inputs"] == []
    assert audit["actual_closure_requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_component_ids": [],
        "blocked_requirement_count": 0,
        "gpcr_phase3_passing_requirement_count": 5,
        "gpcr_phase3_requirement_count": 5,
        "missing_row_input_count": 0,
        "missing_row_inputs": [],
        "passing_requirement_count": 19,
        "pocketmd_phase4_passing_requirement_count": 9,
        "pocketmd_phase4_requirement_count": 9,
        "public_benchmark_phase2_passing_requirement_count": 5,
        "public_benchmark_phase2_requirement_count": 5,
        "ready_component_count": 3,
        "required_component_count": 3,
        "requirement_count": 19,
    }
    assert audit["row_intake_contracts"]["subset_rows"]["accepted_formats"] == [
        "json",
        "jsonl",
        "ndjson",
        "csv",
    ]
    assert audit["row_intake_contracts"]["pocketmd_rows"]["max_top_k"] == 20

    public = audit["components"][0]
    gpcr = audit["components"][1]
    pocketmd = audit["components"][2]
    assert public["phase2_ready"] is True
    assert public["phase2_exit_gate_status"] == "ready"
    assert len(public["phase2_requirements"]) == 5
    assert public["actual_closure_ready"] is True
    assert public["failed_criteria"] == []
    assert public["requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_requirement_count": 0,
        "blocker_count": 0,
        "component_id": "public_benchmark_phase2_actual_closure",
        "failed_criteria": [],
        "failed_criterion_count": 0,
        "passing_requirement_count": 5,
        "requirement_count": 5,
    }
    assert gpcr["phase3_exit_gate_status"] == "ready"
    assert len(gpcr["phase3_exit_gate_criteria"]) == 5
    assert gpcr["target_pass_count"] == 3
    assert gpcr["actual_closure_ready"] is True
    assert gpcr["failed_criteria"] == []
    assert gpcr["requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_requirement_count": 0,
        "blocker_count": 0,
        "component_id": "gpcr_hard_decoy_actual_closure",
        "failed_criteria": [],
        "failed_criterion_count": 0,
        "passing_requirement_count": 5,
        "requirement_count": 5,
    }
    assert pocketmd["phase4_exit_gate_status"] == "ready"
    assert len(pocketmd["phase4_exit_gate_criteria"]) == 9
    assert pocketmd["real_refinement_case_count"] == 3
    assert pocketmd["actual_closure_ready"] is True
    assert pocketmd["failed_criteria"] == []
    assert pocketmd["requirement_summary"] == {
        "actual_closure_ready": True,
        "blocked_requirement_count": 0,
        "blocker_count": 0,
        "component_id": "pocketmd_lite_topk_actual_closure",
        "failed_criteria": [],
        "failed_criterion_count": 0,
        "passing_requirement_count": 9,
        "requirement_count": 9,
    }
    assert audit["component_requirement_summaries"] == [
        public["requirement_summary"],
        gpcr["requirement_summary"],
        pocketmd["requirement_summary"],
    ]
    assert (tmp_path / "public_phase2_audit.json").exists()
    assert (tmp_path / "public_operator_bundle.json").exists()
    assert (tmp_path / "gpcr_surface.json").exists()
    assert (tmp_path / "pocketmd_surface.json").exists()


def test_science_actual_closure_audit_blocks_placeholder_source_receipts(
    tmp_path: Path,
) -> None:
    public_rows = _write_public_phase2_rows(tmp_path)
    gpcr_rows = tmp_path / "gpcr_rows.csv"
    pocketmd_rows = tmp_path / "pocketmd_rows.json"
    pocketmd_contract = tmp_path / "pocketmd_contract.json"
    _write_gpcr_rows(gpcr_rows)
    _write_pocketmd_rows(pocketmd_rows)
    pocketmd_contract.write_text(
        json.dumps(
            {"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True}
        ),
        encoding="utf-8",
    )

    audit = module.build_science_actual_closure_audit(
        repo_root=tmp_path,
        subset_rows_path=public_rows["subset"],
        pose_rows_path=public_rows["pose"],
        enrichment_rows_path=public_rows["enrichment"],
        vina_gnina_rows_path=public_rows["vina_gnina"],
        **_public_output_kwargs(tmp_path),
        gpcr_rows_path=gpcr_rows,
        pocketmd_rows_path=pocketmd_rows,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
        pocketmd_contract_path=pocketmd_contract,
        source_id="fixture_science_actual_closure_rows",
        source_url="local-evidence://science-actual-closure/rows",
        source_license="fixture-only",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["missing_row_inputs"] == []
    assert audit["component_ready_count"] == 1
    assert any(
        blocker.startswith(
            "gpcr_hard_decoy_actual_closure::DRD2:"
            "operator_input_source_source_url_placeholder"
        )
        for blocker in audit["blockers"]
    )
    assert any(
        blocker.startswith(
            "pocketmd_lite_topk_actual_closure::"
            "operator_input_source_source_url_placeholder"
        )
        for blocker in audit["blockers"]
    )
    public = audit["components"][0]
    gpcr = audit["components"][1]
    pocketmd = audit["components"][2]
    assert public["contract_pass"] is True
    assert gpcr["contract_pass"] is False
    assert pocketmd["contract_pass"] is False
    assert "raw_hard_decoy_rows_actual_closure" in gpcr["failed_criteria"]
    assert "report_blockers_resolved" in pocketmd["failed_criteria"]


def test_science_actual_closure_audit_blocks_invalid_actual_rows(
    tmp_path: Path,
) -> None:
    public_rows = _write_public_phase2_rows(tmp_path)
    gpcr_rows = tmp_path / "gpcr_rows.csv"
    pocketmd_rows = tmp_path / "pocketmd_rows.json"
    pocketmd_contract = tmp_path / "pocketmd_contract.json"
    _write_gpcr_rows(gpcr_rows)
    _write_pocketmd_rows(pocketmd_rows)
    pocketmd_contract.write_text(
        json.dumps(
            {"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True}
        ),
        encoding="utf-8",
    )

    with gpcr_rows.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    rows[0]["score"] = "nan"
    with gpcr_rows.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    pocketmd_payload = json.loads(pocketmd_rows.read_text(encoding="utf-8"))
    pocketmd_payload["top_k_refinement_rows"][0]["top_k_rank"] = 21
    pocketmd_rows.write_text(json.dumps(pocketmd_payload), encoding="utf-8")

    audit = module.build_science_actual_closure_audit(
        repo_root=tmp_path,
        subset_rows_path=public_rows["subset"],
        pose_rows_path=public_rows["pose"],
        enrichment_rows_path=public_rows["enrichment"],
        vina_gnina_rows_path=public_rows["vina_gnina"],
        **_public_output_kwargs(tmp_path),
        gpcr_rows_path=gpcr_rows,
        pocketmd_rows_path=pocketmd_rows,
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
        pocketmd_contract_path=pocketmd_contract,
        source_id="operator_attached_science_actual_closure_rows",
        source_url="https://zenodo.org/records/2468135",
        source_license="CC-BY-4.0",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["component_ready_count"] == 1
    assert any("score_invalid" in blocker for blocker in audit["blockers"])
    assert any("top_k_rank_exceeds_max:20" in blocker for blocker in audit["blockers"])
    assert audit["components"][0]["materialized"] is True
    assert audit["components"][1]["materialized"] is False
    assert audit["components"][2]["materialized"] is False
    assert audit["actual_closure_requirement_summary"]["actual_closure_ready"] is False


def test_science_actual_closure_audit_autodetects_default_row_paths(
    tmp_path: Path,
) -> None:
    default_dir = tmp_path / "implementation/phase1/release_evidence/productization"
    default_dir.mkdir(parents=True)
    public_rows = _write_public_phase2_rows(tmp_path)
    public_default_paths = {
        "subset": default_dir / "public_benchmark_subset_rows.json",
        "pose": default_dir / "public_benchmark_pose_rows.json",
        "enrichment": default_dir / "public_benchmark_enrichment_rows.json",
        "vina_gnina": default_dir / "public_benchmark_vina_gnina_rows.json",
    }
    for key, destination in public_default_paths.items():
        destination.write_text(
            public_rows[key].read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    gpcr_rows = default_dir / "gpcr_hard_decoy_rows.csv"
    pocketmd_rows = default_dir / "pocketmd_lite_topk_rows.json"
    pocketmd_contract = tmp_path / "pocketmd_contract.json"
    _write_gpcr_rows(gpcr_rows)
    _write_pocketmd_rows(pocketmd_rows)
    pocketmd_contract.write_text(
        json.dumps({"schema_version": "pocketmd-lite-contract.v1", "contract_pass": True}),
        encoding="utf-8",
    )

    audit = module.build_science_actual_closure_audit(
        repo_root=tmp_path,
        **_public_output_kwargs(tmp_path),
        gpcr_template_out=tmp_path / "gpcr_template.json",
        gpcr_report_out=tmp_path / "gpcr_report.json",
        gpcr_surface_out=tmp_path / "gpcr_surface.json",
        pocketmd_intake_out=tmp_path / "pocketmd_intake.json",
        pocketmd_report_out=tmp_path / "pocketmd_report.json",
        pocketmd_surface_out=tmp_path / "pocketmd_surface.json",
        pocketmd_contract_path=pocketmd_contract,
        source_id="operator_attached_science_actual_closure_rows",
        source_url="https://zenodo.org/records/2468135",
        source_license="CC-BY-4.0",
    )

    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["missing_row_inputs"] == []
    assert audit["row_input_resolution"]["subset_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["subset_rows"]["resolved_path"] == (
        "implementation/phase1/release_evidence/productization/"
        "public_benchmark_subset_rows.json"
    )
    assert audit["row_input_resolution"]["pose_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["enrichment_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["vina_gnina_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["gpcr_rows"] == {
        "auto_detected": True,
        "candidate_paths": [
            "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json",
            "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.jsonl",
            "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.ndjson",
            "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.csv",
            "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.tsv",
        ],
        "explicit_path": "",
        "missing": False,
        "resolved_path": "implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.csv",
        "row_input_id": "gpcr_rows",
    }
    assert audit["row_input_resolution"]["pocketmd_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["pocketmd_rows"]["resolved_path"] == (
        "implementation/phase1/release_evidence/productization/"
        "pocketmd_lite_topk_rows.json"
    )
