from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_public_benchmark_phase2_from_rows.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_phase2_from_rows",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

PHASE2_COMPONENT_IDS = {
    "casf_pdbbind_pose_success_harness",
    "symmetry_aware_ligand_rmsd",
    "posebusters_style_pose_validity",
    "vina_gnina_comparison_adapter",
    "dud_e_or_lit_pcba_enrichment",
}

PHASE2_FAILED_CRITERIA = [
    "casf_pdbbind_pose_success_harness_ready",
    "symmetry_aware_ligand_rmsd_ready",
    "posebusters_style_pose_validity_ready",
    "vina_gnina_comparison_ready",
    "dud_e_or_lit_pcba_enrichment_ready",
]


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(*parts: str) -> str:
    return "https://zenodo.org/records/2468024/files/" + "/".join(parts)


def _write_json(path: Path, payload: object) -> None:
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


def _write_phase2_rows(root: Path, *, case_count: int | None = None) -> dict[str, Path]:
    resolved_case_count = (
        case_count or module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
    )
    case_ids = [
        f"case_{index:02d}"
        for index in range(1, resolved_case_count + 1)
    ]
    ligand_contract = {
        "atom_count": 2,
        "atom_ids": ["C1", "O1"],
    }
    symmetry_contract = {"permutations": [[0, 1]]}
    reference_atoms = [
        {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 1.2, "y": 0.0, "z": 0.0},
    ]
    predicted_atoms = [
        {"element": "C", "x": 0.1, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 1.3, "y": 0.0, "z": 0.0},
    ]
    subset_rows = root / "subset_rows.json"
    pose_rows = root / "pose_rows.json"
    enrichment_rows = root / "enrichment_rows.json"
    vina_gnina_rows = root / "vina_gnina_rows.json"

    _write_json(
        subset_rows,
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
                    "source_license_or_accession": f"PDBBind-CASF-2016-core:{case_id}",
                    "source_checksum": _checksum(f"PDBBind-CASF-2016-core:{case_id}"),
                    "provenance_ref": _provenance_ref(
                        "public-benchmark", "casf-pdbbind", f"{case_id}.json"
                    ),
                    "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                    "rmsd_threshold_angstrom": 2.0,
                }
                for case_id in case_ids
            ]
        },
    )
    _write_json(
        pose_rows,
        {
            "cases": [
                {
                    "case_id": case_id,
                    "benchmark_split": "CASF-core",
                    "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                    "reference_atoms": reference_atoms,
                    "predicted_atoms": predicted_atoms,
                    "ligand_atom_order_contract": ligand_contract,
                    "symmetry_permutation_contract": symmetry_contract,
                    "protein_structure_path": f"benchmarks/{case_id}/protein.pdb",
                    "receptor_context": {
                        "binding_site_frame": "operator_supplied_receptor_frame",
                        "provenance_ref": _provenance_ref(
                            "public-benchmark", "pose", f"{case_id}.json"
                        ),
                    },
                }
                for case_id in case_ids
            ]
        },
    )
    _write_json(
        enrichment_rows,
        {
            "targets": [
                {
                    "benchmark_family": "DUD-E",
                    "target_id": "AA2AR",
                    "score_direction": "higher_is_better",
                    "source_license_or_accession": "DUD-E:AA2AR:release-2015",
                    "source_checksum": _checksum("DUD-E:AA2AR:release-2015"),
                    "provenance_ref": _provenance_ref(
                        "public-benchmark", "dud-e", "AA2AR.json"
                    ),
                    "scored_molecules": [
                        {"molecule_id": "active_1", "is_active": True, "score": 0.9},
                        {"molecule_id": "decoy_1", "is_active": False, "score": 0.1},
                    ],
                }
            ]
        },
    )
    _write_json(
        vina_gnina_rows,
        {
            "cases": [
                {
                    "case_id": case_ids[0],
                    "source_family": "CASF/PDBBind",
                    "benchmark_split": "CASF-core",
                    "complex_id": f"{case_ids[0]}_complex",
                    "reference_pose_id": f"{case_ids[0]}_reference",
                    "source_license_or_accession": f"PDBBind-CASF-2016-core:{case_ids[0]}",
                    "source_checksum": _checksum("vina-gnina-case-a"),
                    "provenance_ref": _provenance_ref(
                        "public-benchmark", "vina-gnina", f"{case_ids[0]}.json"
                    ),
                    "engine_runs": [
                        {
                            "engine_id": "vina",
                            "docking_run_id": f"{case_ids[0]}_vina",
                            "predicted_ligand_path_or_pose_ref": (
                                _provenance_ref(
                                    "public-benchmark",
                                    "vina-gnina",
                                    case_ids[0],
                                    "vina.sdf",
                                )
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
                                _provenance_ref(
                                    "public-benchmark",
                                    "vina-gnina",
                                    case_ids[0],
                                    "gnina.sdf",
                                )
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
    )
    return {
        "subset": subset_rows,
        "pose": pose_rows,
        "enrichment": enrichment_rows,
        "vina_gnina": vina_gnina_rows,
    }


def test_public_benchmark_phase2_row_audit_blocks_without_rows(
    tmp_path: Path,
) -> None:
    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=REPO_ROOT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["phase2_ready"] is False
    assert audit["component_ready_count"] == 0
    assert audit["missing_row_inputs"] == [
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
    ]
    assert audit["row_input_resolution"]["subset_rows"]["missing"] is True
    assert audit["row_input_resolution"]["pose_rows"]["missing"] is True
    assert audit["row_input_resolution"]["enrichment_rows"]["missing"] is True
    assert audit["row_input_resolution"]["vina_gnina_rows"]["missing"] is True
    assert {row["component_id"] for row in audit["phase2_requirements"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert audit["phase2_requirement_summary"] == {
        "required_component_count": 5,
        "ready_component_count": 0,
        "blocked_component_count": 5,
        "materialized_component_count": 0,
        "operator_evidence_required_count": 5,
        "missing_row_input_count": 4,
        "missing_row_inputs": [
            "enrichment_rows",
            "pose_rows",
            "subset_rows",
            "vina_gnina_rows",
        ],
        "phase2_ready": False,
        "blocked_component_ids": [
            "casf_pdbbind_pose_success_harness",
            "symmetry_aware_ligand_rmsd",
            "posebusters_style_pose_validity",
            "vina_gnina_comparison_adapter",
            "dud_e_or_lit_pcba_enrichment",
        ],
    }
    assert audit["summary"] == {
        "phase2_ready": False,
        "component_count": 5,
        "component_ready_count": 0,
        "component_blocked_count": 5,
        "requirement_count": 5,
        "ready_requirement_count": 0,
        "blocked_requirement_count": 5,
        "blocked_component_ids": [
            "casf_pdbbind_pose_success_harness",
            "symmetry_aware_ligand_rmsd",
            "posebusters_style_pose_validity",
            "vina_gnina_comparison_adapter",
            "dud_e_or_lit_pcba_enrichment",
        ],
        "missing_row_input_count": 4,
        "missing_row_inputs": [
            "subset_rows",
            "pose_rows",
            "enrichment_rows",
            "vina_gnina_rows",
        ],
        "phase2_exit_gate_status": "blocked",
        "phase2_failed_criterion_count": 5,
        "phase2_failed_criteria": PHASE2_FAILED_CRITERIA,
        "blocker_count": 6,
    }
    assert audit["phase2_exit_gate"]["claim"] == (
        "public_benchmark_harness_phase2_exit_gate"
    )
    assert audit["phase2_exit_gate"]["status"] == "blocked"
    assert audit["phase2_exit_gate"]["failed_criteria"] == PHASE2_FAILED_CRITERIA
    phase2_exit_criteria = {
        row["component_id"]: row for row in audit["phase2_exit_gate"]["criteria"]
    }
    assert phase2_exit_criteria["casf_pdbbind_pose_success_harness"][
        "blockers"
    ] == ["subset_rows_not_provided", "pose_rows_not_provided"]
    assert phase2_exit_criteria["symmetry_aware_ligand_rmsd"]["blockers"] == [
        "pose_rows_not_provided"
    ]
    assert phase2_exit_criteria["posebusters_style_pose_validity"]["blockers"] == [
        "pose_rows_not_provided"
    ]
    assert phase2_exit_criteria["vina_gnina_comparison_adapter"]["blockers"] == [
        "vina_gnina_rows_not_provided"
    ]
    assert phase2_exit_criteria["dud_e_or_lit_pcba_enrichment"]["blockers"] == [
        "enrichment_rows_not_provided"
    ]
    missing_requirement = {
        row["component_id"]: row for row in audit["phase2_requirements"]
    }
    assert missing_requirement["casf_pdbbind_pose_success_harness"][
        "required_row_inputs"
    ] == ["subset_rows", "pose_rows"]
    assert missing_requirement["casf_pdbbind_pose_success_harness"][
        "missing_row_inputs"
    ] == ["subset_rows", "pose_rows"]
    component_summaries = {
        row["component_id"]: row["requirement_summary"]
        for row in audit["components"]
    }
    assert audit["component_requirement_summaries"] == [
        component_summaries[row["component_id"]]
        for row in audit["components"]
    ]
    assert component_summaries["casf_pdbbind_pose_success_harness"] == {
        "component_id": "casf_pdbbind_pose_success_harness",
        "requirement_count": 1,
        "ready_requirement_count": 0,
        "blocked_requirement_count": 1,
        "failed_criteria": ["casf_pdbbind_pose_success_harness_ready"],
        "failed_criterion_count": 1,
        "blocker_count": 2,
        "required_row_inputs": ["subset_rows", "pose_rows"],
        "missing_row_inputs": ["subset_rows", "pose_rows"],
        "missing_row_input_count": 2,
        "phase2_component_ready": False,
    }
    assert component_summaries["symmetry_aware_ligand_rmsd"] == {
        "component_id": "symmetry_aware_ligand_rmsd",
        "requirement_count": 1,
        "ready_requirement_count": 0,
        "blocked_requirement_count": 1,
        "failed_criteria": ["symmetry_aware_ligand_rmsd_ready"],
        "failed_criterion_count": 1,
        "blocker_count": 1,
        "required_row_inputs": ["pose_rows"],
        "missing_row_inputs": ["pose_rows"],
        "missing_row_input_count": 1,
        "phase2_component_ready": False,
    }
    assert component_summaries["posebusters_style_pose_validity"][
        "failed_criteria"
    ] == ["posebusters_style_pose_validity_ready"]
    assert component_summaries["vina_gnina_comparison_adapter"][
        "failed_criteria"
    ] == ["vina_gnina_comparison_ready"]
    assert component_summaries["dud_e_or_lit_pcba_enrichment"][
        "failed_criteria"
    ] == ["dud_e_or_lit_pcba_enrichment_ready"]
    assert audit["components"][0]["phase2_component_ready"] is False
    assert audit["components"][0]["failed_criteria"] == [
        "casf_pdbbind_pose_success_harness_ready"
    ]
    contracts = audit["row_intake_contracts"]
    subset_contract = contracts["subset_rows"]
    assert subset_contract["supported_source_families"] == ["CASF/PDBBind"]
    assert subset_contract["default_row_path_candidates"][0].endswith(
        "public_benchmark_subset_rows.json"
    )
    assert subset_contract["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    assert "protein_structure_path" in (
        subset_contract["required_local_source_file_fields"]
    )
    assert subset_contract["source_actuality_policy"][
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
        "file://",
    ]
    assert subset_contract["source_actuality_policy"][
        "row_file_artifact_sha256_policy"
    ].startswith("Every operator row file materialized by this importer")
    pose_contract = contracts["pose_rows"]
    assert pose_contract["default_row_path_candidates"][0].endswith(
        "public_benchmark_pose_rows.json"
    )
    assert pose_contract["paired_row_inputs_required"] == ["subset_rows"]
    assert pose_contract["coordinate_payload_fields"] == [
        "reference_atoms",
        "predicted_atoms",
    ]
    assert pose_contract["numeric_value_policy"] == {
        "reference_atoms": (
            "x/y/z coordinates must parse to finite floats; NaN and Infinity "
            "are rejected"
        ),
        "predicted_atoms": (
            "x/y/z coordinates must parse to finite floats; NaN and Infinity "
            "are rejected"
        ),
        "rmsd_threshold_angstrom": (
            "must parse to a finite positive float; NaN, Infinity, zero, and "
            "negative thresholds are rejected"
        ),
    }
    assert pose_contract["default_rmsd_threshold_angstrom"] == 2.0
    assert pose_contract["posebusters_style_check_contract"][
        "packet_schema_version"
    ] == "public-benchmark-pose-validity-packet.v1"
    assert pose_contract["posebusters_style_check_contract"][
        "all_checks_required"
    ] is True
    assert pose_contract["posebusters_style_check_contract"]["required_check_ids"] == [
        "coordinate_finiteness",
        "atom_count_and_order_contract",
        "pose_success_metric_contract",
        "symmetry_permutation_contract",
        "minimum_interatomic_distance_guard",
        "receptor_ligand_context_present",
        "symmetry_aware_ligand_rmsd_angstrom",
    ]
    assert pose_contract["source_actuality_policy"][
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
        "file://",
    ]
    assert subset_contract["minimum_phase2_component_counts"][
        "casf_pdbbind_pose_success_harness"
    ] == {
        "real_benchmark_case_count": (
            module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
        )
    }
    assert pose_contract["minimum_phase2_component_counts"][
        "symmetry_aware_ligand_rmsd"
    ] == {
        "real_benchmark_case_count": (
            module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT
        )
    }
    enrichment_contract = contracts["enrichment_rows"]
    assert enrichment_contract["default_row_path_candidates"][0].endswith(
        "public_benchmark_enrichment_rows.json"
    )
    assert enrichment_contract["supported_benchmark_families"] == [
        "DUD-E",
        "LIT-PCBA",
    ]
    assert "scored_molecules" in enrichment_contract["required_target_fields"]
    assert enrichment_contract["score_direction_policy"] == {
        "required": True,
        "accepted_values": ["higher_is_better", "lower_is_better"],
        "accepted_aliases": {
            "higher_is_better": ["higher", "higher_is_better", "descending"],
            "lower_is_better": ["lower", "lower_is_better", "ascending"],
        },
        "blank_values": "rejected; no implicit default is applied",
    }
    assert enrichment_contract["boolean_label_policy"] == {
        "is_active": (
            "must be a JSON boolean true/false; strings and numbers are rejected"
        )
    }
    assert enrichment_contract["numeric_value_policy"] == {
        "score": "must parse to a finite float; NaN and Infinity are rejected"
    }
    assert enrichment_contract["active_decoy_policy"] == {
        "per_target_requirement": (
            "each target must contain at least one active molecule and one decoy "
            "molecule"
        )
    }
    assert enrichment_contract["row_integrity_policy"]["required_unique_row_keys"] == {
        "targets": ["target_id"],
        "target_scored_molecules": ["molecule_id"],
    }
    vina_contract = contracts["vina_gnina_rows"]
    assert vina_contract["default_row_path_candidates"][0].endswith(
        "public_benchmark_vina_gnina_rows.json"
    )
    assert vina_contract["supported_engines"] == ["vina", "gnina"]
    assert "engine_runs" in vina_contract["required_case_fields"]
    assert vina_contract["score_direction_policy"] == {
        "required": True,
        "accepted_values": ["higher_is_better", "lower_is_better"],
        "accepted_aliases": {
            "higher_is_better": ["higher", "higher_is_better", "descending"],
            "lower_is_better": ["lower", "lower_is_better", "ascending"],
        },
        "blank_values": "rejected; no implicit default is applied",
    }
    assert vina_contract["boolean_value_policy"] == {
        "pose_success": (
            "must be a JSON boolean true/false; strings and numbers are rejected"
        )
    }
    assert vina_contract["numeric_value_policy"] == {
        "symmetry_aware_rmsd_angstrom": (
            "must parse to a finite non-negative float; NaN, Infinity, and "
            "negative RMSD values are rejected"
        ),
        "score": "must parse to a finite float; NaN and Infinity are rejected",
        "pose_success_rmsd_threshold_angstrom": (
            "must parse to a finite positive float; NaN, Infinity, zero, and "
            "negative thresholds are rejected"
        ),
    }
    assert vina_contract["pose_success_policy"] == {
        "threshold_default_angstrom": 2.0,
        "consistency_rule": (
            "pose_success must equal symmetry_aware_rmsd_angstrom <= "
            "pose_success_rmsd_threshold_angstrom"
        ),
    }
    assert vina_contract["engine_pair_policy"] == {
        "per_case_required_engines": ["vina", "gnina"],
        "duplicate_engine_ids_rejected": True,
        "duplicate_docking_run_ids_rejected": True,
    }
    assert vina_contract["row_integrity_policy"]["required_unique_row_keys"] == {
        "cases": ["case_id"],
        "case_engine_runs": ["engine_id", "docking_run_id"],
    }
    assert "casf_pdbbind_pose_success_harness::subset_rows_not_provided" in audit["blockers"]
    assert "dud_e_or_lit_pcba_enrichment::enrichment_rows_not_provided" in audit["blockers"]
    assert not (tmp_path / "operator_bundle.json").exists()
    assert not (tmp_path / "harness_report.json").exists()
    assert not (tmp_path / "artifact_bundle.json").exists()


def test_public_benchmark_phase2_row_audit_materializes_ready_gate(
    tmp_path: Path,
) -> None:
    rows = _write_phase2_rows(tmp_path)

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        subset_rows_path=rows["subset"],
        pose_rows_path=rows["pose"],
        enrichment_rows_path=rows["enrichment"],
        vina_gnina_rows_path=rows["vina_gnina"],
        target_subset_case_count=module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["phase2_ready"] is True
    assert audit["component_ready_count"] == 5
    assert audit["blockers"] == []
    assert {row["component_id"] for row in audit["phase2_requirements"]} == (
        PHASE2_COMPONENT_IDS
    )
    assert audit["phase2_requirement_summary"] == {
        "required_component_count": 5,
        "ready_component_count": 5,
        "blocked_component_count": 0,
        "materialized_component_count": 5,
        "operator_evidence_required_count": 0,
        "missing_row_input_count": 0,
        "missing_row_inputs": [],
        "phase2_ready": True,
        "blocked_component_ids": [],
    }
    assert audit["summary"]["phase2_ready"] is True
    assert audit["summary"]["ready_requirement_count"] == 5
    assert audit["summary"]["blocked_requirement_count"] == 0
    assert audit["summary"]["phase2_failed_criteria"] == []
    assert audit["summary"]["blocker_count"] == 0
    assert all(row["ready"] for row in audit["phase2_requirements"])
    assert all(row["phase2_component_ready"] for row in audit["components"])
    assert all(row["failed_criteria"] == [] for row in audit["components"])
    assert audit["component_requirement_summaries"] == [
        row["requirement_summary"] for row in audit["components"]
    ]
    assert {
        row["component_id"]: row["requirement_summary"]["ready_requirement_count"]
        for row in audit["components"]
    } == {
        "casf_pdbbind_pose_success_harness": 1,
        "symmetry_aware_ligand_rmsd": 1,
        "posebusters_style_pose_validity": 1,
        "vina_gnina_comparison_adapter": 1,
        "dud_e_or_lit_pcba_enrichment": 1,
    }
    assert all(
        row["requirement_summary"]["blocker_count"] == 0
        for row in audit["components"]
    )
    assert audit["row_intake_contracts"]["phase2_outputs"]["operator_bundle"] == (
        str(tmp_path / "operator_bundle.json")
    )
    assert audit["phase2_exit_gate"]["status"] == "ready"
    assert audit["operator_bundle_materialization_report"]["phase2_harness_inputs"] == {
        "casf_pdbbind_pose_success_harness": True,
        "symmetry_aware_ligand_rmsd": True,
        "posebusters_style_pose_validity": True,
        "vina_gnina_comparison_adapter": True,
        "dud_e_lit_pcba_enrichment": True,
    }
    assert audit["operator_bundle_source_actuality_check"]["contract_pass"] is True
    assert audit["operator_bundle_source_actuality_check"]["blockers"] == []
    row_file_receipts = audit["operator_bundle_materialization_report"][
        "row_file_artifact_receipts"
    ]
    assert row_file_receipts["subset_rows"]["source_artifact_sha256"] == (
        module.row_bundle.file_sha256(rows["subset"])
    )
    assert row_file_receipts["pose_rows"]["source_artifact_sha256"] == (
        module.row_bundle.file_sha256(rows["pose"])
    )
    assert row_file_receipts["enrichment_rows"]["source_artifact_sha256"] == (
        module.row_bundle.file_sha256(rows["enrichment"])
    )
    assert row_file_receipts["vina_gnina_rows"]["source_artifact_sha256"] == (
        module.row_bundle.file_sha256(rows["vina_gnina"])
    )

    assert (tmp_path / "operator_bundle.json").exists()
    assert (tmp_path / "harness_report.json").exists()
    assert (tmp_path / "artifact_bundle.json").exists()
    artifact_bundle = json.loads((tmp_path / "artifact_bundle.json").read_text())
    assert artifact_bundle["phase2_ready"] is True
    assert artifact_bundle["phase2_exit_gate"]["status"] == "ready"


def test_public_benchmark_phase2_row_audit_blocks_non_finite_numeric_rows(
    tmp_path: Path,
) -> None:
    rows = _write_phase2_rows(tmp_path)
    pose_payload = json.loads(rows["pose"].read_text(encoding="utf-8"))
    enrichment_payload = json.loads(rows["enrichment"].read_text(encoding="utf-8"))
    vina_payload = json.loads(rows["vina_gnina"].read_text(encoding="utf-8"))
    pose_payload["cases"][0]["rmsd_threshold_angstrom"] = float("inf")
    enrichment_payload["targets"][0]["scored_molecules"][0]["score"] = float("nan")
    vina_payload["cases"][0]["engine_runs"][0][
        "symmetry_aware_rmsd_angstrom"
    ] = float("inf")
    vina_payload["cases"][0]["engine_runs"][0]["score"] = float("-inf")
    vina_payload["cases"][0]["engine_runs"][0][
        "pose_success_rmsd_threshold_angstrom"
    ] = float("nan")
    _write_json(rows["pose"], pose_payload)
    _write_json(rows["enrichment"], enrichment_payload)
    _write_json(rows["vina_gnina"], vina_payload)

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        subset_rows_path=rows["subset"],
        pose_rows_path=rows["pose"],
        enrichment_rows_path=rows["enrichment"],
        vina_gnina_rows_path=rows["vina_gnina"],
        target_subset_case_count=module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["phase2_ready"] is False
    blocked_components = {
        row["component_id"]: row for row in audit["components"] if not row["ready"]
    }
    assert "symmetry_aware_ligand_rmsd" in blocked_components
    assert "posebusters_style_pose_validity" in blocked_components
    assert "dud_e_or_lit_pcba_enrichment" in blocked_components
    assert "vina_gnina_comparison_adapter" in blocked_components
    assert any(
        "rmsd_threshold_angstrom_invalid" in blocker
        for blocker in audit["blockers"]
    )
    assert (
        "enrichment_scorecard:AA2AR:molecule_0:score_invalid"
        in audit["blockers"]
    )
    assert (
        "vina_gnina_comparison_adapter:case_01:engine_run_0:"
        "symmetry_aware_rmsd_angstrom_invalid"
    ) in audit["blockers"]
    assert (
        "vina_gnina_comparison_adapter:case_01:engine_run_0:score_invalid"
        in audit["blockers"]
    )
    assert (
        "vina_gnina_comparison_adapter:case_01:engine_run_0:"
        "pose_success_rmsd_threshold_angstrom_invalid"
    ) in audit["blockers"]
    operator_bundle = json.loads((tmp_path / "operator_bundle.json").read_text())
    assert (
        operator_bundle["dud_e_lit_pcba_enrichment_intake"]["targets"][0][
            "scored_molecules"
        ][0]["score"]
        == "nan"
    )
    assert (
        operator_bundle["vina_gnina_comparison_intake"]["cases"][0]["engine_runs"][0][
            "symmetry_aware_rmsd_angstrom"
        ]
        == "inf"
    )


def test_public_benchmark_phase2_row_audit_blocks_failed_source_actuality_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rows = _write_phase2_rows(tmp_path)

    def failed_source_actuality_check(**_: object) -> dict[str, object]:
        return {
            "contract_pass": False,
            "blocker_count": 0,
            "blockers": [],
            "checked_row_counts": {},
            "policy": module.row_bundle.SOURCE_ACTUALITY_POLICY,
            "claim_boundary": "Injected failed contract for Phase 2 audit coverage.",
        }

    monkeypatch.setattr(
        module.row_bundle,
        "_source_actuality_check",
        failed_source_actuality_check,
    )

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        subset_rows_path=rows["subset"],
        pose_rows_path=rows["pose"],
        enrichment_rows_path=rows["enrichment"],
        vina_gnina_rows_path=rows["vina_gnina"],
        target_subset_case_count=module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["phase2_ready"] is False
    assert audit["phase2_exit_gate"]["status"] == "blocked"
    assert audit["phase2_exit_gate"]["source_actuality_ready"] is False
    assert audit["phase2_exit_gate"]["source_actuality_criterion_id"] == (
        "public_benchmark_source_actuality_ready"
    )
    assert audit["phase2_exit_gate"]["failed_criteria"] == [
        "public_benchmark_source_actuality_ready"
    ]
    assert audit["operator_bundle_source_actuality_check"]["contract_pass"] is False
    assert audit["operator_bundle_source_actuality_check"]["blockers"] == []
    assert audit["blockers"] == [
        "operator_bundle_source_actuality::source_actuality_contract_failed",
        "phase2_exit_gate::public_benchmark_source_actuality_ready",
    ]
    assert audit["summary"]["phase2_exit_gate_status"] == "blocked"
    assert audit["summary"]["phase2_failed_criteria"] == [
        "public_benchmark_source_actuality_ready"
    ]
    assert audit["summary"]["blocker_count"] == 2


def test_public_benchmark_phase2_row_audit_blocks_duplicate_case_rows(
    tmp_path: Path,
) -> None:
    rows = _write_phase2_rows(tmp_path)
    subset_payload = json.loads(rows["subset"].read_text(encoding="utf-8"))
    pose_payload = json.loads(rows["pose"].read_text(encoding="utf-8"))
    subset_payload["rows"][1]["case_id"] = subset_payload["rows"][0]["case_id"]
    pose_payload["cases"][1]["case_id"] = pose_payload["cases"][0]["case_id"]
    rows["subset"].write_text(json.dumps(subset_payload), encoding="utf-8")
    rows["pose"].write_text(json.dumps(pose_payload), encoding="utf-8")

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        subset_rows_path=rows["subset"],
        pose_rows_path=rows["pose"],
        enrichment_rows_path=rows["enrichment"],
        vina_gnina_rows_path=rows["vina_gnina"],
        target_subset_case_count=module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["phase2_ready"] is False
    assert audit["operator_bundle_source_actuality_check"]["contract_pass"] is False
    assert (
        "subset_rows:case_01:case_id_duplicate"
        in audit["operator_bundle_source_actuality_check"]["blockers"]
    )
    assert (
        "pose_rows:case_01:case_id_duplicate"
        in audit["operator_bundle_source_actuality_check"]["blockers"]
    )
    assert (
        "operator_bundle_source_actuality::subset_rows:case_01:case_id_duplicate"
        in audit["blockers"]
    )
    assert (
        "operator_bundle_source_actuality::pose_rows:case_01:case_id_duplicate"
        in audit["blockers"]
    )


def test_public_benchmark_phase2_row_audit_autodetects_default_row_paths(
    tmp_path: Path,
) -> None:
    rows = _write_phase2_rows(tmp_path)
    default_dir = tmp_path / "implementation/phase1/release_evidence/productization"
    default_dir.mkdir(parents=True)
    defaults = {
        "subset": default_dir / "public_benchmark_subset_rows.json",
        "pose": default_dir / "public_benchmark_pose_rows.json",
        "enrichment": default_dir / "public_benchmark_enrichment_rows.json",
        "vina_gnina": default_dir / "public_benchmark_vina_gnina_rows.json",
    }
    for key, path in defaults.items():
        path.write_text(rows[key].read_text(encoding="utf-8"), encoding="utf-8")

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        target_subset_case_count=module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "ready"
    assert audit["contract_pass"] is True
    assert audit["phase2_ready"] is True
    assert audit["missing_row_inputs"] == []
    assert audit["row_input_resolution"]["subset_rows"] == {
        "auto_detected": True,
        "candidate_paths": [
            "implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json",
            "implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.jsonl",
            "implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.ndjson",
            "implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.csv",
        ],
        "explicit_path": "",
        "missing": False,
        "resolved_path": (
            "implementation/phase1/release_evidence/productization/"
            "public_benchmark_subset_rows.json"
        ),
        "row_input_id": "subset_rows",
    }
    assert audit["row_input_resolution"]["pose_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["enrichment_rows"]["auto_detected"] is True
    assert audit["row_input_resolution"]["vina_gnina_rows"]["auto_detected"] is True
    assert audit["phase2_exit_gate"]["status"] == "ready"


def test_public_benchmark_phase2_row_audit_blocks_one_case_smoke_rows(
    tmp_path: Path,
) -> None:
    rows = _write_phase2_rows(tmp_path, case_count=1)

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        subset_rows_path=rows["subset"],
        pose_rows_path=rows["pose"],
        enrichment_rows_path=rows["enrichment"],
        vina_gnina_rows_path=rows["vina_gnina"],
        target_subset_case_count=1,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["phase2_ready"] is False
    assert audit["component_ready_count"] == 2
    assert audit["phase2_requirement_summary"]["ready_component_count"] == 2
    assert audit["phase2_requirement_summary"]["blocked_component_count"] == 3
    assert audit["phase2_requirement_summary"]["blocked_component_ids"] == [
        "casf_pdbbind_pose_success_harness",
        "symmetry_aware_ligand_rmsd",
        "posebusters_style_pose_validity",
    ]
    assert audit["phase2_exit_gate"]["failed_criteria"] == [
        "casf_pdbbind_pose_success_harness_ready",
        "symmetry_aware_ligand_rmsd_ready",
        "posebusters_style_pose_validity_ready",
    ]
    blocked_components = {
        row["component_id"]: row
        for row in audit["components"]
        if not row["ready"]
    }
    assert {
        component_id: row["contract_pass"]
        for component_id, row in blocked_components.items()
    } == {
        "casf_pdbbind_pose_success_harness": False,
        "symmetry_aware_ligand_rmsd": False,
        "posebusters_style_pose_validity": False,
    }
    assert {
        component_id: row["source_artifact_contract_pass"]
        for component_id, row in blocked_components.items()
    } == {
        "casf_pdbbind_pose_success_harness": True,
        "symmetry_aware_ligand_rmsd": True,
        "posebusters_style_pose_validity": True,
    }
    assert {
        component_id: row["status"]
        for component_id, row in blocked_components.items()
    } == {
        "casf_pdbbind_pose_success_harness": "phase2_count_incomplete",
        "symmetry_aware_ligand_rmsd": "phase2_count_incomplete",
        "posebusters_style_pose_validity": "phase2_count_incomplete",
    }
    assert {
        component_id: row["failed_criteria"]
        for component_id, row in blocked_components.items()
    } == {
        "casf_pdbbind_pose_success_harness": [
            "casf_pdbbind_pose_success_harness_ready"
        ],
        "symmetry_aware_ligand_rmsd": ["symmetry_aware_ligand_rmsd_ready"],
        "posebusters_style_pose_validity": [
            "posebusters_style_pose_validity_ready"
        ],
    }
    assert all(
        row["requirement_summary"]["blocked_requirement_count"] == 1
        for row in blocked_components.values()
    )
    assert {
        row["component_id"]: row["requirement_summary"]["phase2_component_ready"]
        for row in audit["components"]
    } == {
        "casf_pdbbind_pose_success_harness": False,
        "symmetry_aware_ligand_rmsd": False,
        "posebusters_style_pose_validity": False,
        "vina_gnina_comparison_adapter": True,
        "dud_e_or_lit_pcba_enrichment": True,
    }
    assert "phase2_exit_gate::casf_pdbbind_pose_success_harness_ready" in audit[
        "blockers"
    ]
    assert any(
        blocker.endswith("real_benchmark_case_count_below_required:1<12")
        for blocker in audit["blockers"]
    )


def test_public_benchmark_phase2_row_audit_blocks_placeholder_source_receipts(
    tmp_path: Path,
) -> None:
    rows = _write_phase2_rows(tmp_path)
    subset_payload = json.loads(rows["subset"].read_text(encoding="utf-8"))
    subset_payload["rows"][0]["source_license_or_accession"] = "CASF/PDBBind:test-accession"
    subset_payload["rows"][0]["source_checksum"] = "sha256:" + "a" * 64
    subset_payload["rows"][0]["provenance_ref"] = "operator://casf-pdbbind/case_01"
    _write_json(rows["subset"], subset_payload)

    audit = module.build_public_benchmark_phase2_row_audit(
        repo_root=tmp_path,
        subset_rows_path=rows["subset"],
        pose_rows_path=rows["pose"],
        enrichment_rows_path=rows["enrichment"],
        vina_gnina_rows_path=rows["vina_gnina"],
        target_subset_case_count=module.harness_bundle.TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        operator_bundle_out=tmp_path / "operator_bundle.json",
        out_dir=tmp_path / "out",
        harness_report_out=tmp_path / "harness_report.json",
        artifact_bundle_out=tmp_path / "artifact_bundle.json",
    )

    assert audit["status"] == "operator_evidence_required"
    assert audit["contract_pass"] is False
    assert audit["phase2_ready"] is False
    source_check = audit["operator_bundle_source_actuality_check"]
    assert source_check["contract_pass"] is False
    assert "subset_rows:case_01:source_license_or_accession_placeholder" in source_check["blockers"]
    assert "subset_rows:case_01:source_checksum_placeholder_digest" in source_check["blockers"]
    assert "subset_rows:case_01:provenance_ref_placeholder" in source_check["blockers"]
    assert any(
        blocker.startswith("operator_bundle_source_actuality::subset_rows:case_01:")
        for blocker in audit["blockers"]
    )
