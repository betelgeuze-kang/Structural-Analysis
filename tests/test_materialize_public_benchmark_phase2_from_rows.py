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


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


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
                    "source_license_or_accession": "CASF/PDBBind:test-accession",
                    "provenance_ref": f"operator://casf-pdbbind/{case_id}",
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
                        "provenance_ref": f"operator://pose/{case_id}",
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
                    "source_license_or_accession": "DUD-E:AA2AR",
                    "source_checksum": _checksum("DUD-E:AA2AR"),
                    "provenance_ref": "operator://dud-e/AA2AR",
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
                    "source_license_or_accession": "CASF/PDBBind:test-accession",
                    "source_checksum": _checksum("vina-gnina-case-a"),
                    "provenance_ref": f"operator://vina-gnina/{case_ids[0]}",
                    "engine_runs": [
                        {
                            "engine_id": "vina",
                            "docking_run_id": f"{case_ids[0]}_vina",
                            "predicted_ligand_path_or_pose_ref": "operator://vina.sdf",
                            "symmetry_aware_rmsd_angstrom": 1.4,
                            "pose_success": True,
                            "score": -7.2,
                            "score_direction": "lower_is_better",
                        },
                        {
                            "engine_id": "gnina",
                            "docking_run_id": f"{case_ids[0]}_gnina",
                            "predicted_ligand_path_or_pose_ref": "operator://gnina.sdf",
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
    contracts = audit["row_intake_contracts"]
    subset_contract = contracts["subset_rows"]
    assert subset_contract["supported_source_families"] == ["CASF/PDBBind"]
    assert subset_contract["supported_benchmark_splits"] == [
        "CASF-core",
        "PDBBind-core",
        "PDBBind-refined",
        "PDBBind-general",
    ]
    assert "protein_structure_path" in (
        subset_contract["required_local_source_file_fields"]
    )
    pose_contract = contracts["pose_rows"]
    assert pose_contract["paired_row_inputs_required"] == ["subset_rows"]
    assert pose_contract["coordinate_payload_fields"] == [
        "reference_atoms",
        "predicted_atoms",
    ]
    assert pose_contract["default_rmsd_threshold_angstrom"] == 2.0
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
    assert enrichment_contract["supported_benchmark_families"] == [
        "DUD-E",
        "LIT-PCBA",
    ]
    assert "scored_molecules" in enrichment_contract["required_target_fields"]
    vina_contract = contracts["vina_gnina_rows"]
    assert vina_contract["supported_engines"] == ["vina", "gnina"]
    assert "engine_runs" in vina_contract["required_case_fields"]
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

    assert (tmp_path / "operator_bundle.json").exists()
    assert (tmp_path / "harness_report.json").exists()
    assert (tmp_path / "artifact_bundle.json").exists()
    artifact_bundle = json.loads((tmp_path / "artifact_bundle.json").read_text())
    assert artifact_bundle["phase2_ready"] is True
    assert artifact_bundle["phase2_exit_gate"]["status"] == "ready"


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
    assert "phase2_exit_gate::casf_pdbbind_pose_success_harness_ready" in audit[
        "blockers"
    ]
    assert any(
        blocker.endswith("real_benchmark_case_count_below_required:1<12")
        for blocker in audit["blockers"]
    )
