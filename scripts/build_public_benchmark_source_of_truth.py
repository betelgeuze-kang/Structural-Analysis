#!/usr/bin/env python3
"""Build the public benchmark harness source-of-truth seed artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from score_symmetry_aware_ligand_rmsd import (  # noqa: E402
    DEFAULT_THRESHOLD_ANGSTROM,
    score_symmetry_aware_rmsd,
)
from validate_public_benchmark_subset_manifest import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    validate_subset_manifest,
)
from validate_public_benchmark_pose_validity import (  # noqa: E402
    REQUIRED_POSE_FIELDS,
    validate_pose_validity_payload,
)
from materialize_public_benchmark_subset_manifest import (  # noqa: E402
    SCHEMA_VERSION as MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_pose_validity_input import (  # noqa: E402
    SCHEMA_VERSION as POSE_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_rmsd_scorecard import (  # noqa: E402
    SCHEMA_VERSION as RMSD_MATERIALIZER_SCHEMA_VERSION,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_OF_TRUTH_OUT = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_SUBSET_MANIFEST_OUT = PRODUCTIZATION / "public_benchmark_subset_manifest.json"
DEFAULT_POSE_VALIDITY_PACKET_OUT = PRODUCTIZATION / "public_benchmark_pose_validity_packet.json"
DEFAULT_RMSD_SCORECARD_OUT = PRODUCTIZATION / "public_benchmark_symmetry_rmsd_scorecard.json"
SCHEMA_VERSION = "public-benchmark-source-of-truth.v1"
SUBSET_SCHEMA_VERSION = "public-benchmark-subset-manifest.v1"
POSE_PACKET_SCHEMA_VERSION = "public-benchmark-pose-validity-packet.v1"
RMSD_SCORECARD_SCHEMA_VERSION = "public-benchmark-symmetry-rmsd-scorecard.v1"


def _source_input_paths() -> list[Path]:
    return [
        Path("scripts/build_public_benchmark_source_of_truth.py"),
        Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
        Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
        Path("scripts/materialize_public_benchmark_subset_manifest.py"),
        Path("scripts/score_symmetry_aware_ligand_rmsd.py"),
        Path("scripts/validate_public_benchmark_pose_validity.py"),
        Path("scripts/validate_public_benchmark_subset_manifest.py"),
    ]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _case_row_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "source_family": "CASF/PDBBind",
        "complex_id": "",
        "protein_structure_path": "",
        "reference_ligand_path": "",
        "predicted_ligand_path_or_docking_run_id": "",
        "ligand_atom_order_contract": {
            "atom_count": 0,
            "atom_ids": [],
            "atom_id_basis": "reference_ligand_atom_order",
        },
        "symmetry_permutation_contract": {
            "permutations": [],
            "permutation_basis": "zero_based_indices_into_ligand_atom_order_contract.atom_ids",
        },
        "source_license_or_accession": "",
        "source_checksum": "",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
        "rmsd_threshold_angstrom": DEFAULT_THRESHOLD_ANGSTROM,
    }


def _operator_slot(
    *,
    slot_id: str,
    source_family: str,
    required_case_count: int,
    selection_rule: str,
    metric_role: str,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "source_family": source_family,
        "required_case_count": required_case_count,
        "materialized_case_count": 0,
        "status": "source_material_required",
        "selection_rule": selection_rule,
        "metric_role": metric_role,
        "required_fields": [
            "complex_id",
            "protein_structure_path",
            "reference_ligand_path",
            "predicted_ligand_path_or_docking_run_id",
            "ligand_atom_order_contract",
            "symmetry_permutation_contract",
            "source_license_or_accession",
            "source_checksum",
        ],
        "blockers": [
            "public_source_files_not_attached",
            "ligand_atom_order_contract_missing",
            "symmetry_permutation_contract_missing",
        ],
    }


def build_subset_manifest(*, repo_root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema_version": SUBSET_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="source_of_truth_seed_manifest_generated_from_repo_contract",
            repo_root=repo_root,
        ),
        "status": "source_material_required",
        "contract_pass": True,
        "public_benchmark_ready": False,
        "target_subset_case_count": 12,
        "materialized_case_count": 0,
        "source_families": ["CASF/PDBBind"],
        "case_row_schema": {
            "required_fields": list(REQUIRED_CASE_FIELDS),
            "template": _case_row_template(),
            "validation_command": (
                "python3 scripts/validate_public_benchmark_subset_manifest.py "
                "--manifest implementation/phase1/release_evidence/productization/"
                "public_benchmark_subset_manifest.json --fail-blocked"
            ),
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_subset_manifest.py "
                "--intake <operator-casf-pdbbind-intake.json> "
                "--out-manifest implementation/phase1/release_evidence/productization/"
                "public_benchmark_subset_manifest.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_subset_materialization_report.json --fail-blocked"
            ),
        },
        "case_rows": [],
        "slots": [
            _operator_slot(
                slot_id="casf_pdbbind_pose_success_seed",
                source_family="CASF/PDBBind",
                required_case_count=6,
                selection_rule=(
                    "Select protein-ligand complexes from a CASF/PDBBind core-set style "
                    "source with receptor structure, reference ligand coordinates, and "
                    "a reproducible docking-pose input or prediction artifact."
                ),
                metric_role="pose_success_symmetry_aware_ligand_rmsd",
            ),
            _operator_slot(
                slot_id="casf_pdbbind_affinity_control_seed",
                source_family="CASF/PDBBind",
                required_case_count=6,
                selection_rule=(
                    "Select affinity-annotated complexes that overlap the pose-success "
                    "preparation contract only when source licensing, checksums, and "
                    "ligand atom-order mapping are present."
                ),
                metric_role="scorecard_traceability_affinity_context_only",
            ),
        ],
        "blockers": [
            "casf_pdbbind_source_material_not_attached",
            "casf_pdbbind_case_checksums_missing",
            "casf_pdbbind_ligand_symmetry_contracts_missing",
        ],
        "claim_boundary": (
            "This manifest is a Tier beta source-of-truth seed. It defines the minimum "
            "CASF/PDBBind subset contract, operator slots, case-row schema, and validation "
            "command, but it does not attach or redistribute public benchmark source files "
            "and does not claim benchmark results."
        ),
    }


def _dry_run_pose_case() -> dict[str, Any]:
    reference_atoms = [
        {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 2.0, "y": 0.0, "z": 0.0},
        {"element": "O", "x": 0.0, "y": 1.0, "z": 0.0},
        {"element": "N", "x": 0.0, "y": 0.0, "z": 3.0},
    ]
    predicted_atoms = [
        {"element": "C", "x": 5.0, "y": -2.0, "z": 1.0},
        {"element": "O", "x": 5.0, "y": -1.0, "z": 1.0},
        {"element": "O", "x": 7.0, "y": -2.0, "z": 1.0},
        {"element": "N", "x": 5.0, "y": -2.0, "z": 4.0},
    ]
    return {
        "case_id": "dry_run_symmetry_swap_pose",
        "source_family": "synthetic",
        "protein_structure_path": "synthetic://public_benchmark/dry_run/protein.pdb",
        "receptor_context": {
            "binding_site_frame": "synthetic_identity_frame",
            "context_boundary": "synthetic receptor context for validator dry-run only",
        },
        "reference_atoms": reference_atoms,
        "predicted_atoms": predicted_atoms,
        "ligand_atom_order_contract": {
            "atom_count": len(reference_atoms),
            "atom_ids": ["C1", "O1", "O2", "N1"],
        },
        "symmetry_permutation_contract": {
            "permutations": [
                [0, 1, 2, 3],
                [0, 2, 1, 3],
            ],
        },
        "symmetry_permutations": [
            [0, 1, 2, 3],
            [0, 2, 1, 3],
        ],
        "rmsd_threshold_angstrom": DEFAULT_THRESHOLD_ANGSTROM,
        "case_boundary": (
            "Synthetic dry-run only. The equivalent O atoms demonstrate explicit symmetry "
            "permutation handling without claiming a real CASF/PDBBind result."
        ),
    }


def build_rmsd_scorecard(*, repo_root: Path = ROOT) -> dict[str, Any]:
    dry_run_case = _dry_run_pose_case()
    score = score_symmetry_aware_rmsd(
        reference_atoms=dry_run_case["reference_atoms"],
        predicted_atoms=dry_run_case["predicted_atoms"],
        symmetry_permutations=dry_run_case["symmetry_permutations"],
        threshold_angstrom=float(dry_run_case["rmsd_threshold_angstrom"]),
    )
    return {
        "schema_version": RMSD_SCORECARD_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="synthetic_dry_run_recomputes_symmetry_aware_rmsd",
            repo_root=repo_root,
        ),
        "status": "ready",
        "contract_pass": True,
        "real_benchmark_case_count": 0,
        "dry_run_case_count": 1,
        "materializer": {
            "schema_version": RMSD_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_input",
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_rmsd_scorecard.py "
                "--pose-validity-input implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_validity_input.json "
                "--out-scorecard implementation/phase1/release_evidence/productization/"
                "public_benchmark_symmetry_rmsd_scorecard.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_symmetry_rmsd_materialization_report.json --fail-blocked"
            ),
            "claim_boundary": (
                "The materializer computes per-case symmetry-aware RMSD from pose-validity "
                "input and reports pose-success counts. It does not infer chemistry or "
                "claim Tier beta."
            ),
        },
        "rows": [
            {
                "case_id": dry_run_case["case_id"],
                "score": score,
                "case_boundary": dry_run_case["case_boundary"],
            }
        ],
        "claim_boundary": (
            "This scorecard verifies the symmetry-aware RMSD implementation on a synthetic "
            "coordinate fixture only. It does not claim public benchmark pose success."
        ),
    }


def build_pose_validity_packet(*, repo_root: Path = ROOT) -> dict[str, Any]:
    dry_run_validation = validate_pose_validity_payload({"cases": [_dry_run_pose_case()]})
    return {
        "schema_version": POSE_PACKET_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="pose_validity_packet_generated_from_repo_contract",
            repo_root=repo_root,
        ),
        "status": "ready_for_dry_run",
        "contract_pass": True,
        "real_benchmark_case_count": 0,
        "validator": {
            "schema_version": "public-benchmark-pose-validity-validation.v1",
            "required_pose_fields": list(REQUIRED_POSE_FIELDS),
            "validation_command": (
                "python3 scripts/validate_public_benchmark_pose_validity.py "
                "--input <pose-validity-input.json> --fail-blocked"
            ),
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_pose_validity_input.py "
                "--subset-manifest implementation/phase1/release_evidence/productization/"
                "public_benchmark_subset_manifest.json "
                "--pose-intake <operator-pose-coordinate-intake.json> "
                "--out-input implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_validity_input.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_validity_materialization_report.json --fail-blocked"
            ),
        },
        "dry_run_validation": dry_run_validation,
        "checks": [
            {
                "check_id": "coordinate_finiteness",
                "required": True,
                "description": "reference and predicted ligand coordinates are finite 3D values",
            },
            {
                "check_id": "atom_count_and_order_contract",
                "required": True,
                "description": "reference/predicted ligand atoms share a declared atom-order contract",
            },
            {
                "check_id": "symmetry_aware_ligand_rmsd_angstrom",
                "required": True,
                "description": "pose success uses the best rigid-aligned RMSD over allowed symmetry permutations",
                "threshold_angstrom": DEFAULT_THRESHOLD_ANGSTROM,
            },
            {
                "check_id": "minimum_interatomic_distance_guard",
                "required": True,
                "description": "predicted ligand coordinates must not contain impossible self-clashes",
            },
            {
                "check_id": "receptor_ligand_context_present",
                "required": True,
                "description": "protein structure, binding-site frame, and ligand provenance are present",
            },
        ],
        "posebusters_style_boundary": (
            "The packet defines PoseBusters-style sanity checks for a local harness. It "
            "does not vendor PoseBusters, infer chemistry, or replace toolkit-backed "
            "bond/order/protonation validation once real ligands are attached."
        ),
    }


def build_source_of_truth(
    *,
    subset_manifest: dict[str, Any],
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="public_benchmark_contract_generated_from_repo_code",
            repo_root=repo_root,
        ),
        "status": "seed_ready_materialization_blocked",
        "contract_pass": True,
        "tier_beta_ready": False,
        "public_benchmark_ready": False,
        "source_families": [
            {
                "family_id": "casf_pdbbind",
                "role": "pose_success_and_affinity_context",
                "materialization_status": "source_material_required",
            },
            {
                "family_id": "posebusters_style_validity",
                "role": "pose_sanity_packet",
                "materialization_status": "dry_run_ready_real_ligands_required",
            },
            {
                "family_id": "dud_e_lit_pcba",
                "role": "future_enrichment",
                "materialization_status": "planned_later",
            },
            {
                "family_id": "vina_gnina",
                "role": "future_comparison_adapter",
                "materialization_status": "planned_later",
            },
        ],
        "subset_manifest_summary": {
            "target_subset_case_count": subset_manifest["target_subset_case_count"],
            "materialized_case_count": subset_manifest["materialized_case_count"],
            "blockers": subset_manifest["blockers"],
        },
        "pose_validity_packet_summary": {
            "status": pose_validity_packet["status"],
            "check_count": len(pose_validity_packet["checks"]),
            "required_check_count": sum(1 for row in pose_validity_packet["checks"] if row["required"]),
            "validator_schema_version": pose_validity_packet["validator"]["schema_version"],
            "dry_run_pose_validity_ready": pose_validity_packet["dry_run_validation"][
                "pose_validity_ready"
            ],
            "real_benchmark_case_count": pose_validity_packet["dry_run_validation"][
                "real_benchmark_case_count"
            ],
        },
        "symmetry_rmsd_summary": {
            "status": rmsd_scorecard["status"],
            "dry_run_case_count": rmsd_scorecard["dry_run_case_count"],
            "real_benchmark_case_count": rmsd_scorecard["real_benchmark_case_count"],
            "dry_run_pose_success": bool(rmsd_scorecard["rows"][0]["score"]["pose_success"]),
        },
        "subset_manifest_validation": validate_subset_manifest(subset_manifest),
        "subset_materializer": {
            "schema_version": MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "intake_case_key": "cases",
            "required_case_fields": list(REQUIRED_CASE_FIELDS),
            "local_source_file_fields": [
                "protein_structure_path",
                "reference_ligand_path",
                "predicted_ligand_path_or_docking_run_id",
            ],
            "materialization_command": subset_manifest["case_row_schema"][
                "materialization_command"
            ],
            "claim_boundary": (
                "The materializer consumes operator-attached local CASF/PDBBind case "
                "descriptors and files, computes checksums, and validates the subset "
                "manifest. It does not fetch, redistribute, or license benchmark data."
            ),
        },
        "pose_validity_materializer": {
            "schema_version": POSE_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "required_pose_fields": list(REQUIRED_POSE_FIELDS),
            "pose_intake_case_key": "cases",
            "materialization_command": pose_validity_packet["validator"][
                "materialization_command"
            ],
            "claim_boundary": (
                "The pose materializer joins a materialized subset manifest with "
                "operator-attached reference/predicted ligand coordinates and receptor "
                "context, then runs the local PoseBusters-style validator. It does not "
                "parse chemistry files or claim benchmark performance."
            ),
        },
        "rmsd_scorecard_materializer": {
            "schema_version": RMSD_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_input",
            "materialization_command": rmsd_scorecard["materializer"][
                "materialization_command"
            ],
            "claim_boundary": (
                "The RMSD scorecard materializer consumes validated pose-coordinate input "
                "and produces per-case symmetry-aware ligand RMSD rows plus pose-success "
                "counts. It does not compare docking engines or close Tier beta alone."
            ),
        },
        "blockers": [
            "casf_pdbbind_source_material_not_attached",
            "public_benchmark_real_pose_predictions_missing",
            "public_benchmark_external_receipts_missing",
        ],
        "next_actions": [
            "attach_checked_casf_pdbbind_subset_source_files",
            "run_public_benchmark_subset_materializer",
            "fill_ligand_atom_order_and_symmetry_permutation_contracts",
            "attach_public_benchmark_pose_coordinate_intake",
            "run_public_benchmark_pose_validity_materializer",
            "run_symmetry_aware_rmsd_on_real_subset",
            "run_public_benchmark_rmsd_scorecard_materializer",
            "materialize_posebusters_style_validity_packet_for_real_ligands",
        ],
        "claim_boundary": (
            "This is the Phase 2 public benchmark harness seed. It closes source-of-truth "
            "shape, subset contract, RMSD scorer dry-run, and pose-validity packet shape. "
            "It does not close Tier beta, public benchmark results, Vina/GNINA comparison, "
            "or DUD-E/LIT-PCBA enrichment."
        ),
    }


def build_public_benchmark_artifacts(*, repo_root: Path = ROOT) -> dict[str, dict[str, Any]]:
    subset_manifest = build_subset_manifest(repo_root=repo_root)
    pose_validity_packet = build_pose_validity_packet(repo_root=repo_root)
    rmsd_scorecard = build_rmsd_scorecard(repo_root=repo_root)
    source_of_truth = build_source_of_truth(
        subset_manifest=subset_manifest,
        pose_validity_packet=pose_validity_packet,
        rmsd_scorecard=rmsd_scorecard,
        repo_root=repo_root,
    )
    return {
        "source_of_truth": source_of_truth,
        "subset_manifest": subset_manifest,
        "pose_validity_packet": pose_validity_packet,
        "rmsd_scorecard": rmsd_scorecard,
    }


def write_public_benchmark_artifacts(
    *,
    repo_root: Path = ROOT,
    source_of_truth_out: Path = DEFAULT_SOURCE_OF_TRUTH_OUT,
    subset_manifest_out: Path = DEFAULT_SUBSET_MANIFEST_OUT,
    pose_validity_packet_out: Path = DEFAULT_POSE_VALIDITY_PACKET_OUT,
    rmsd_scorecard_out: Path = DEFAULT_RMSD_SCORECARD_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_public_benchmark_artifacts(repo_root=repo_root)
    outputs = {
        "source_of_truth": source_of_truth_out,
        "subset_manifest": subset_manifest_out,
        "pose_validity_packet": pose_validity_packet_out,
        "rmsd_scorecard": rmsd_scorecard_out,
    }
    for key, out_path in outputs.items():
        resolved = out_path if out_path.is_absolute() else repo_root / out_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-of-truth-out", type=Path, default=DEFAULT_SOURCE_OF_TRUTH_OUT)
    parser.add_argument("--subset-manifest-out", type=Path, default=DEFAULT_SUBSET_MANIFEST_OUT)
    parser.add_argument("--pose-validity-packet-out", type=Path, default=DEFAULT_POSE_VALIDITY_PACKET_OUT)
    parser.add_argument("--rmsd-scorecard-out", type=Path, default=DEFAULT_RMSD_SCORECARD_OUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    artifacts = write_public_benchmark_artifacts(
        source_of_truth_out=args.source_of_truth_out,
        subset_manifest_out=args.subset_manifest_out,
        pose_validity_packet_out=args.pose_validity_packet_out,
        rmsd_scorecard_out=args.rmsd_scorecard_out,
    )
    summary = artifacts["source_of_truth"]
    if args.json:
        print(_json_text(summary), end="")
    else:
        print(
            "public-benchmark-source-of-truth: "
            f"{summary['status']} | subset={summary['subset_manifest_summary']['materialized_case_count']}/"
            f"{summary['subset_manifest_summary']['target_subset_case_count']} | "
            f"dry_run_pose_success={summary['symmetry_rmsd_summary']['dry_run_pose_success']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
