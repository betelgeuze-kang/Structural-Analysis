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
    SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS,
    source_material_coverage_summary,
    validate_subset_manifest,
)
from validate_public_benchmark_external_receipts import (  # noqa: E402
    REQUIRED_RECEIPT_FIELDS,
    REQUIRED_SUBSET_RECEIPT_FIELDS,
    SCHEMA_VERSION as EXTERNAL_RECEIPT_VALIDATION_SCHEMA_VERSION,
    validate_external_receipts,
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
from materialize_public_benchmark_posebusters_validity_packet import (  # noqa: E402
    SCHEMA_VERSION as POSEBUSTERS_PACKET_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_rmsd_scorecard import (  # noqa: E402
    SCHEMA_VERSION as RMSD_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_pose_success_harness import (  # noqa: E402
    HARNESS_SCHEMA_VERSION as POSE_SUCCESS_HARNESS_SCHEMA_VERSION,
    SCHEMA_VERSION as POSE_SUCCESS_HARNESS_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_enrichment_scorecard import (  # noqa: E402
    SCHEMA_VERSION as ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
    SUPPORTED_FAMILIES,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    ADAPTER_SCHEMA_VERSION as VINA_GNINA_ADAPTER_SCHEMA_VERSION,
    REQUIRED_CASE_FIELDS as VINA_GNINA_REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS as VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS,
    SCHEMA_VERSION as VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
    SUPPORTED_BENCHMARK_SPLITS as VINA_GNINA_SUPPORTED_BENCHMARK_SPLITS,
    SUPPORTED_ENGINES as VINA_GNINA_SUPPORTED_ENGINES,
)
from build_public_benchmark_operator_intake_packet import (  # noqa: E402
    DEFAULT_HARNESS_BUNDLE as DEFAULT_HARNESS_BUNDLE_OUT,
    DEFAULT_OPERATOR_TEMPLATE_DIR,
    DEFAULT_OUT as DEFAULT_OPERATOR_INTAKE_PACKET_OUT,
    build_public_benchmark_operator_intake_packet,
    write_public_benchmark_operator_template_payloads,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_OF_TRUTH_OUT = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_SUBSET_MANIFEST_OUT = PRODUCTIZATION / "public_benchmark_subset_manifest.json"
DEFAULT_POSE_VALIDITY_PACKET_OUT = (
    PRODUCTIZATION / "public_benchmark_pose_validity_packet.json"
)
DEFAULT_RMSD_SCORECARD_OUT = (
    PRODUCTIZATION / "public_benchmark_symmetry_rmsd_scorecard.json"
)
DEFAULT_POSE_SUCCESS_HARNESS_OUT = (
    PRODUCTIZATION / "public_benchmark_pose_success_harness.json"
)
DEFAULT_ENRICHMENT_SCORECARD_OUT = (
    PRODUCTIZATION / "public_benchmark_enrichment_scorecard.json"
)
DEFAULT_VINA_GNINA_ADAPTER_OUT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_comparison_adapter.json"
)
DEFAULT_EXTERNAL_RECEIPTS_VALIDATION_OUT = (
    PRODUCTIZATION / "public_benchmark_external_receipts_validation.json"
)
DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT = DEFAULT_OPERATOR_INTAKE_PACKET_OUT.with_suffix(
    ".md"
)
SCHEMA_VERSION = "public-benchmark-source-of-truth.v1"
SUBSET_SCHEMA_VERSION = "public-benchmark-subset-manifest.v1"
POSE_PACKET_SCHEMA_VERSION = "public-benchmark-pose-validity-packet.v1"
RMSD_SCORECARD_SCHEMA_VERSION = "public-benchmark-symmetry-rmsd-scorecard.v1"
ENRICHMENT_SCORECARD_SCHEMA_VERSION = "public-benchmark-enrichment-scorecard.v1"

PUBLIC_BENCHMARK_ROUTE = "/product/public-benchmark"
PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE = "/product/public-benchmark/operator-intake"
SOURCE_CHECKSUM_POLICY = {
    "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
    "required_receipt_field": "source_checksum",
}


def _source_input_paths() -> list[Path]:
    return [
        Path("scripts/build_public_benchmark_source_of_truth.py"),
        Path("scripts/materialize_public_benchmark_operator_bundle_from_rows.py"),
        Path("scripts/materialize_public_benchmark_harness_bundle.py"),
        Path("scripts/materialize_public_benchmark_posebusters_validity_packet.py"),
        Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
        Path("scripts/materialize_public_benchmark_pose_success_harness.py"),
        Path("scripts/materialize_public_benchmark_enrichment_scorecard.py"),
        Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
        Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
        Path("scripts/materialize_public_benchmark_subset_manifest.py"),
        Path("scripts/build_public_benchmark_operator_intake_packet.py"),
        Path("scripts/score_symmetry_aware_ligand_rmsd.py"),
        Path("scripts/validate_public_benchmark_external_receipts.py"),
        Path("scripts/validate_public_benchmark_pose_validity.py"),
        Path("scripts/validate_public_benchmark_subset_manifest.py"),
    ]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pose_packet_real_case_count(packet: dict[str, Any]) -> int:
    return max(
        _as_int(packet.get("real_benchmark_case_count")),
        _as_int(
            _as_dict(packet.get("dry_run_validation")).get("real_benchmark_case_count")
        ),
    )


def _pose_packet_validation_ready(packet: dict[str, Any]) -> bool:
    return bool(packet.get("posebusters_validity_ready")) or bool(
        _as_dict(packet.get("dry_run_validation")).get("pose_validity_ready")
    )


def _pose_packet_validator_schema_version(packet: dict[str, Any]) -> str:
    return str(
        _as_dict(packet.get("validator")).get("schema_version")
        or packet.get("validator_schema_version")
        or ""
    )


def _pose_packet_materializer_schema_version(packet: dict[str, Any]) -> str:
    return str(
        _as_dict(packet.get("materializer")).get("schema_version")
        or _as_dict(packet.get("materialization_report")).get("schema_version")
        or ""
    )


def _materializer_schema_version(payload: dict[str, Any]) -> str:
    return str(
        _as_dict(payload.get("materializer")).get("schema_version")
        or _as_dict(payload.get("materialization_report")).get("schema_version")
        or ""
    )


def _nested_materialization_command(
    payload: dict[str, Any],
    nested_key: str,
    fallback: str,
) -> str:
    return str(
        _as_dict(payload.get(nested_key)).get("materialization_command")
        or fallback
    )


def _case_row_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
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
        "provenance_ref": "",
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
            "benchmark_split",
            "protein_structure_path",
            "reference_ligand_path",
            "predicted_ligand_path_or_docking_run_id",
            "ligand_atom_order_contract",
            "symmetry_permutation_contract",
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
            "pose_success_metric",
            "rmsd_threshold_angstrom",
        ],
        "blockers": [
            "public_source_files_not_attached",
            "ligand_atom_order_contract_missing",
            "symmetry_permutation_contract_missing",
        ],
    }


def build_subset_manifest(*, repo_root: Path = ROOT) -> dict[str, Any]:
    source_material_coverage = source_material_coverage_summary(
        [],
        target_subset_case_count=12,
    )
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
        "source_material_coverage": source_material_coverage,
        "case_row_schema": {
            "required_fields": list(REQUIRED_CASE_FIELDS),
            "template": _case_row_template(),
            "supported_benchmark_splits": list(SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS),
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
        "benchmark_split": "synthetic-dry-run",
        "protein_structure_path": "synthetic://public_benchmark/dry_run/protein.pdb",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
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
                "source_family": dry_run_case["source_family"],
                "benchmark_split": dry_run_case["benchmark_split"],
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
    dry_run_validation = validate_pose_validity_payload(
        {"cases": [_dry_run_pose_case()]}
    )
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
        "materializer": {
            "schema_version": POSEBUSTERS_PACKET_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_input",
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_posebusters_validity_packet.py "
                "--pose-validity-input implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_validity_input.json "
                "--out-packet implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_validity_packet.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_posebusters_validity_materialization_report.json "
                "--fail-blocked"
            ),
            "claim_boundary": (
                "The materializer turns validated pose-coordinate input into per-case "
                "PoseBusters-style sanity rows for real benchmark ligands. It does not "
                "vendor PoseBusters, infer chemistry, or close Tier beta."
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
                "check_id": "pose_success_metric_contract",
                "required": True,
                "description": "pose success metric is explicitly symmetry-aware ligand RMSD",
            },
            {
                "check_id": "symmetry_permutation_contract",
                "required": True,
                "description": (
                    "allowed symmetry permutations are explicit zero-based atom-index maps "
                    "and include the identity atom order"
                ),
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


def build_pose_success_harness(
    *,
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    dry_run_row = rmsd_scorecard["rows"][0]
    score = dry_run_row["score"]
    return {
        "schema_version": POSE_SUCCESS_HARNESS_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="public_benchmark_pose_success_harness_seed_from_repo_contract",
            repo_root=repo_root,
        ),
        "status": "ready_for_real_benchmark_rows",
        "contract_pass": True,
        "pose_success_harness_ready": False,
        "real_benchmark_case_count": 0,
        "dry_run_case_count": 1,
        "case_count": 1,
        "pose_validity_pass_count": 1,
        "pose_success_count": 1,
        "pose_failure_count": 0,
        "pose_success_rate": 1.0,
        "materializer": {
            "schema_version": POSE_SUCCESS_HARNESS_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_packet_and_rmsd_scorecard",
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_pose_success_harness.py "
                "--pose-validity-packet implementation/phase1/release_evidence/"
                "productization/public_benchmark_pose_validity_packet.json "
                "--rmsd-scorecard implementation/phase1/release_evidence/productization/"
                "public_benchmark_symmetry_rmsd_scorecard.json "
                "--out-harness implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_success_harness.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_pose_success_harness_materialization_report.json "
                "--fail-blocked"
            ),
            "claim_boundary": (
                "The materializer joins the PoseBusters-style validity packet with the "
                "symmetry-aware RMSD scorecard and emits per-case pose-success rows. "
                "It does not fetch benchmark data or close Tier beta alone."
            ),
        },
        "case_rows": [
            {
                "case_id": str(dry_run_row["case_id"]),
                "source_family": str(dry_run_row["source_family"]),
                "benchmark_split": str(dry_run_row["benchmark_split"]),
                "status": "pass",
                "pose_validity_pass": _pose_packet_validation_ready(
                    pose_validity_packet
                ),
                "pose_success": bool(score["pose_success"]),
                "symmetry_aware_ligand_rmsd_angstrom": score["best_rmsd_angstrom"],
                "rmsd_threshold_angstrom": score["threshold_angstrom"],
                "best_symmetry_permutation": score["best_permutation"],
                "case_boundary": (
                    "Synthetic dry-run only. Real CASF/PDBBind rows must be "
                    "materialized through the operator intake before this harness can "
                    "support a benchmark claim."
                ),
            }
        ],
        "blockers": ["public_benchmark_pose_success_harness_rows_missing"],
        "claim_boundary": (
            "This seed fixes the CASF/PDBBind pose-success harness contract and a "
            "synthetic dry-run row. It does not attach public benchmark source files "
            "or claim real benchmark pose-success performance."
        ),
    }


def build_enrichment_scorecard(*, repo_root: Path = ROOT) -> dict[str, Any]:
    blockers = [
        "dud_e_lit_pcba_enrichment_targets_missing",
        "dud_e_lit_pcba_scored_molecules_missing",
        "dud_e_lit_pcba_active_decoy_labels_missing",
    ]
    return {
        "schema_version": ENRICHMENT_SCORECARD_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="public_benchmark_enrichment_scorecard_seed_from_repo_contract",
            repo_root=repo_root,
        ),
        "status": "operator_evidence_required",
        "contract_pass": False,
        "public_benchmark_enrichment_ready": False,
        "real_enrichment_target_count": 0,
        "benchmark_family_target_counts": {},
        "target_rows": [],
        "summary": {
            "benchmark_family_count": 0,
            "benchmark_families": [],
            "benchmark_family_target_counts": {},
            "covered_supported_family_count": 0,
            "missing_supported_families": list(SUPPORTED_FAMILIES),
            "target_count": 0,
            "ready_target_count": 0,
            "molecule_count": 0,
            "active_count": 0,
            "decoy_count": 0,
            "enrichment_factor_1pct_median": None,
            "enrichment_factor_5pct_median": None,
            "roc_auc_median": None,
            "blocker_count": len(blockers),
        },
        "materializer": {
            "schema_version": ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "intake_target_key": "targets",
            "required_target_fields": [
                "benchmark_family",
                "target_id",
                "score_direction",
                "scored_molecules",
                "source_license_or_accession",
                "source_checksum",
                "provenance_ref",
            ],
            "required_molecule_fields": ["molecule_id", "is_active", "score"],
            "supported_families": list(SUPPORTED_FAMILIES),
            "family_coverage_fields": [
                "benchmark_family_target_counts",
                "covered_supported_family_count",
                "missing_supported_families",
            ],
            "source_checksum_policy": SOURCE_CHECKSUM_POLICY,
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_enrichment_scorecard.py "
                "--intake <operator-dud-e-lit-pcba-enrichment-intake.json> "
                "--out-scorecard implementation/phase1/release_evidence/productization/"
                "public_benchmark_enrichment_scorecard.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_enrichment_materialization_report.json --fail-blocked"
            ),
            "claim_boundary": (
                "The materializer consumes operator-attached DUD-E/LIT-PCBA scored "
                "molecule rows and computes EF@1%, EF@5%, and ROC-AUC. It does not "
                "fetch public benchmark files, infer ligand chemistry, or close Tier beta."
            ),
        },
        "blockers": blockers,
        "claim_boundary": (
            "This seed defines the DUD-E/LIT-PCBA enrichment scorecard shape and "
            "materializer command. With zero operator-attached target rows it is "
            "intentionally blocked and cannot support an enrichment claim."
        ),
    }


def _vina_gnina_case_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "source_family": "CASF/PDBBind",
        "benchmark_split": "CASF-core",
        "complex_id": "SOURCE_COMPLEX_ID",
        "reference_pose_id": "SOURCE_COMPLEX_ID_reference_ligand",
        "engine_runs": [
            {
                "engine_id": "vina",
                "docking_run_id": "SOURCE_COMPLEX_ID_vina_run",
                "predicted_ligand_path_or_pose_ref": (
                    "operator_attached/vina_gnina/SOURCE_COMPLEX_ID/vina_pose.sdf"
                ),
                "symmetry_aware_rmsd_angstrom": None,
                "pose_success": None,
                "score": None,
                "score_direction": "lower_is_better",
            },
            {
                "engine_id": "gnina",
                "docking_run_id": "SOURCE_COMPLEX_ID_gnina_run",
                "predicted_ligand_path_or_pose_ref": (
                    "operator_attached/vina_gnina/SOURCE_COMPLEX_ID/gnina_pose.sdf"
                ),
                "symmetry_aware_rmsd_angstrom": None,
                "pose_success": None,
                "score": None,
                "score_direction": "lower_is_better",
            },
        ],
        "source_license_or_accession": "operator_supplied_casf_pdbbind_accession",
        "source_checksum": "sha256:operator_supplied_vina_gnina_rows_checksum",
        "provenance_ref": "operator_supplied_vina_gnina_run_receipt",
    }


def build_vina_gnina_comparison_adapter(*, repo_root: Path = ROOT) -> dict[str, Any]:
    blockers = [
        "vina_gnina_comparison_cases_missing",
        "vina_gnina_engine_runs_missing",
        "vina_gnina_external_receipts_missing",
    ]
    return {
        "schema_version": VINA_GNINA_ADAPTER_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_source_input_paths(),
            reused_evidence=False,
            reuse_policy="public_benchmark_vina_gnina_comparison_adapter_seed_from_repo_contract",
            repo_root=repo_root,
        ),
        "status": "operator_evidence_required",
        "contract_pass": False,
        "public_benchmark_engine_comparison_ready": False,
        "real_comparison_case_count": 0,
        "case_rows": [],
        "engine_summaries": [
            {
                "engine_id": engine_id,
                "run_count": 0,
                "pose_success_count": 0,
                "pose_success_rate": None,
                "symmetry_aware_rmsd_median_angstrom": None,
            }
            for engine_id in VINA_GNINA_SUPPORTED_ENGINES
        ],
        "benchmark_split_counts": {},
        "summary": {
            "case_count": 0,
            "ready_case_count": 0,
            "engine_count": len(VINA_GNINA_SUPPORTED_ENGINES),
            "supported_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
            "supported_benchmark_splits": list(VINA_GNINA_SUPPORTED_BENCHMARK_SPLITS),
            "benchmark_split_counts": {},
            "blocker_count": len(blockers),
        },
        "materializer": {
            "schema_version": VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "intake_case_key": "cases",
            "required_case_fields": list(VINA_GNINA_REQUIRED_CASE_FIELDS),
            "required_engine_run_fields": list(VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS),
            "supported_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
            "supported_benchmark_splits": list(VINA_GNINA_SUPPORTED_BENCHMARK_SPLITS),
            "source_checksum_policy": SOURCE_CHECKSUM_POLICY,
            "template": {"cases": [_vina_gnina_case_template()]},
            "materialization_command": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                "--intake <operator-vina-gnina-comparison-intake.json> "
                "--out-adapter implementation/phase1/release_evidence/productization/"
                "public_benchmark_vina_gnina_comparison_adapter.json "
                "--out-report implementation/phase1/release_evidence/productization/"
                "public_benchmark_vina_gnina_materialization_report.json --fail-blocked"
            ),
            "claim_boundary": (
                "The adapter consumes operator-attached Vina/GNINA comparison rows. It "
                "does not run docking engines, fetch public benchmark files, infer ligand "
                "chemistry, or close Tier beta."
            ),
        },
        "supported_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
        "supported_benchmark_splits": list(VINA_GNINA_SUPPORTED_BENCHMARK_SPLITS),
        "blockers": blockers,
        "claim_boundary": (
            "This seed defines the Vina/GNINA comparison adapter shape and materializer "
            "command. With zero operator-attached engine comparison rows it is "
            "intentionally blocked and cannot support engine comparison claims."
        ),
    }


def _operator_evidence_gap_register(
    *,
    tier_beta_gate: dict[str, Any],
    operator_intake_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    criteria_by_id = {
        str(row.get("criterion_id") or ""): row
        for row in tier_beta_gate.get("criteria", [])
        if isinstance(row, dict)
    }
    plan_by_slot = {
        str(row.get("slot_id") or ""): row
        for row in operator_intake_packet.get("gate_unblock_plan", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for index, slot in enumerate(
        operator_intake_packet.get("input_slots", []), start=1
    ):
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("slot_id") or "")
        plan = plan_by_slot.get(slot_id, {})
        criterion_gates = []
        for criterion_id in plan.get("unblocks_tier_beta_criteria", []):
            criterion = criteria_by_id.get(str(criterion_id), {})
            criterion_gates.append(
                {
                    "criterion_id": str(criterion_id),
                    "pass": bool(criterion.get("pass")),
                    "current": criterion.get("current"),
                    "required": criterion.get("required"),
                    "blockers": [
                        str(blocker) for blocker in criterion.get("blockers", [])
                    ],
                }
            )
        blocked_criteria = [
            row["criterion_id"] for row in criterion_gates if not row["pass"]
        ]
        owner_actions = [
            str(action) for action in slot.get("owner_actions", []) if str(action)
        ]
        manifest_contract = slot.get("manifest_contract")
        if not isinstance(manifest_contract, dict):
            manifest_contract = {}
        rows.append(
            {
                "slot_priority": index,
                "slot_id": slot_id,
                "status": str(slot.get("status") or ""),
                "manifest_contract_id": str(manifest_contract.get("contract_id") or ""),
                "manifest_contract": manifest_contract,
                "tier_beta_blocked": bool(blocked_criteria),
                "blocked_tier_beta_criteria": blocked_criteria,
                "criterion_gates": criterion_gates,
                "first_next_action": owner_actions[0] if owner_actions else "",
                "owner_actions": owner_actions,
                "template_artifact": str(slot.get("template_artifact") or ""),
                "depends_on": [
                    str(path) for path in slot.get("depends_on", []) if str(path)
                ],
                "minimum_evidence": dict(plan.get("minimum_evidence") or {}),
                "materialization_steps": [
                    str(step)
                    for step in plan.get("materialization_steps", [])
                    if str(step)
                ],
                "materialization_command": str(
                    slot.get("materialization_command") or ""
                ),
                "validation_command": str(slot.get("validation_command") or ""),
            }
        )
    return rows


def _operator_blocker_detail_register(
    *,
    tier_beta_gate: dict[str, Any],
    operator_evidence_gap_register: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    criteria_by_id = {
        str(row.get("criterion_id") or ""): row
        for row in tier_beta_gate.get("criteria", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for gap in operator_evidence_gap_register:
        if not gap.get("tier_beta_blocked"):
            continue
        criteria: list[dict[str, Any]] = []
        blockers: list[str] = []
        for criterion_id in gap.get("blocked_tier_beta_criteria", []):
            criterion = criteria_by_id.get(str(criterion_id), {})
            criterion_blockers = [
                str(blocker) for blocker in criterion.get("blockers", []) if str(blocker)
            ]
            blockers.extend(criterion_blockers)
            criteria.append(
                {
                    "criterion_id": str(criterion_id),
                    "current": criterion.get("current"),
                    "required": criterion.get("required"),
                    "blockers": criterion_blockers,
                }
            )
        unique_blockers = list(dict.fromkeys(blockers))
        rows.append(
            {
                "slot_priority": int(gap.get("slot_priority") or 0),
                "slot_id": str(gap.get("slot_id") or ""),
                "status": str(gap.get("status") or ""),
                "blocked_tier_beta_criteria": [
                    str(item) for item in gap.get("blocked_tier_beta_criteria", [])
                ],
                "criterion_details": criteria,
                "blocker_count": len(unique_blockers),
                "blockers": unique_blockers,
                "first_blocker": unique_blockers[0] if unique_blockers else "",
                "first_next_action": str(gap.get("first_next_action") or ""),
                "minimum_evidence": dict(gap.get("minimum_evidence") or {}),
                "template_artifact": str(gap.get("template_artifact") or ""),
                "depends_on": [
                    str(path) for path in gap.get("depends_on", []) if str(path)
                ],
                "materialization_steps": [
                    str(step) for step in gap.get("materialization_steps", []) if str(step)
                ],
                "materialization_command": str(gap.get("materialization_command") or ""),
                "validation_command": str(gap.get("validation_command") or ""),
            }
        )
    return rows


PHASE2_SLICE_OPERATOR_SLOT_IDS = {
    "casf_pdbbind_subset_materialization": ["casf_pdbbind_subset_intake"],
    "real_pose_coordinate_materialization": ["pose_coordinate_intake"],
    "dud_e_lit_pcba_enrichment_materialization": [
        "dud_e_lit_pcba_enrichment_intake"
    ],
    "vina_gnina_comparison_materialization": ["vina_gnina_comparison_intake"],
    "public_benchmark_external_receipts_validation": [
        "casf_pdbbind_subset_intake",
        "dud_e_lit_pcba_enrichment_intake",
        "vina_gnina_comparison_intake",
    ],
}

PHASE2_SLICE_ROOT_CAUSE_TAGS = {
    "casf_pdbbind_subset_materialization": [
        "operator_source_material_required",
        "operator_receipts_required",
    ],
    "real_pose_coordinate_materialization": ["operator_pose_coordinates_required"],
    "dud_e_lit_pcba_enrichment_materialization": [
        "operator_enrichment_rows_required",
        "operator_receipts_required",
    ],
    "vina_gnina_comparison_materialization": [
        "operator_engine_comparison_rows_required",
        "operator_receipts_required",
    ],
    "public_benchmark_external_receipts_validation": ["operator_receipts_required"],
}

PHASE2_SLICE_TIER_BETA_CRITERIA = {
    "casf_pdbbind_subset_materialization": [
        "casf_pdbbind_subset_materialized",
        "external_receipts_attached",
    ],
    "real_pose_coordinate_materialization": [
        "real_pose_validity_packet_materialized",
        "symmetry_rmsd_scorecard_real_cases",
        "posebusters_style_validity_real_ligands",
        "casf_pdbbind_pose_success_harness_ready",
    ],
    "dud_e_lit_pcba_enrichment_materialization": [
        "dud_e_lit_pcba_enrichment_ready",
        "external_receipts_attached",
    ],
    "vina_gnina_comparison_materialization": [
        "vina_gnina_comparison_ready",
        "external_receipts_attached",
    ],
    "public_benchmark_external_receipts_validation": ["external_receipts_attached"],
}

PHASE2_SLICE_NEXT_ACTION = {
    "public_benchmark_external_receipts_validation": (
        "attach source_license_or_accession, source_checksum, and provenance_ref "
        "receipts for the missing public benchmark artifact roles"
    )
}

PHASE2_REQUIREMENT_ROWS = (
    {
        "component_id": "casf_pdbbind_pose_success_harness",
        "requirement": "CASF/PDBBind pose-success harness",
        "criterion_id": "casf_pdbbind_pose_success_harness_ready",
        "artifact_role": "pose_success_harness",
        "ready_field": "pose_success_harness_ready",
        "count_field": "real_benchmark_case_count",
        "required_row_inputs": ["subset_rows", "pose_rows"],
        "related_operator_slot_ids": [
            "casf_pdbbind_subset_intake",
            "pose_coordinate_intake",
        ],
    },
    {
        "component_id": "symmetry_aware_ligand_rmsd",
        "requirement": "Symmetry-aware ligand RMSD scorecard",
        "criterion_id": "symmetry_aware_ligand_rmsd_ready",
        "artifact_role": "rmsd_scorecard",
        "ready_field": "scorecard_ready",
        "count_field": "real_benchmark_case_count",
        "required_row_inputs": ["pose_rows"],
        "related_operator_slot_ids": ["pose_coordinate_intake"],
    },
    {
        "component_id": "posebusters_style_pose_validity",
        "requirement": "PoseBusters-style pose validity packet",
        "criterion_id": "posebusters_style_pose_validity_ready",
        "artifact_role": "pose_validity_packet",
        "ready_field": "posebusters_validity_ready",
        "count_field": "real_benchmark_case_count",
        "required_row_inputs": ["pose_rows"],
        "related_operator_slot_ids": ["pose_coordinate_intake"],
    },
    {
        "component_id": "vina_gnina_comparison_adapter",
        "requirement": "Vina/GNINA comparison adapter",
        "criterion_id": "vina_gnina_comparison_ready",
        "artifact_role": "vina_gnina_comparison_adapter",
        "ready_field": "public_benchmark_engine_comparison_ready",
        "count_field": "real_comparison_case_count",
        "required_minimum_count": 1,
        "required_row_inputs": ["vina_gnina_rows"],
        "related_operator_slot_ids": ["vina_gnina_comparison_intake"],
    },
    {
        "component_id": "dud_e_or_lit_pcba_enrichment",
        "requirement": "DUD-E or LIT-PCBA enrichment scorecard",
        "criterion_id": "dud_e_or_lit_pcba_enrichment_ready",
        "artifact_role": "enrichment_scorecard",
        "ready_field": "public_benchmark_enrichment_ready",
        "count_field": "real_enrichment_target_count",
        "required_minimum_count": 1,
        "required_row_inputs": ["enrichment_rows"],
        "related_operator_slot_ids": ["dud_e_lit_pcba_enrichment_intake"],
    },
)


def _ready_field_value(payload: dict[str, Any], ready_field: str) -> bool:
    if ready_field in payload:
        return bool(payload.get(ready_field))
    if payload.get("contract_pass") is False:
        return False
    return str(payload.get("status") or "") == "ready"


def _phase2_requirement_rows(
    *,
    target_subset_case_count: int,
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    pose_success_harness: dict[str, Any],
    enrichment_scorecard: dict[str, Any],
    vina_gnina_comparison_adapter: dict[str, Any],
) -> list[dict[str, Any]]:
    payload_by_role = {
        "pose_validity_packet": pose_validity_packet,
        "rmsd_scorecard": rmsd_scorecard,
        "pose_success_harness": pose_success_harness,
        "enrichment_scorecard": enrichment_scorecard,
        "vina_gnina_comparison_adapter": vina_gnina_comparison_adapter,
    }
    rows: list[dict[str, Any]] = []
    for requirement in PHASE2_REQUIREMENT_ROWS:
        role = str(requirement["artifact_role"])
        payload = payload_by_role.get(role, {})
        count_field = str(requirement["count_field"])
        current_count = _as_int(payload.get(count_field))
        if role == "pose_validity_packet":
            current_count = _pose_packet_real_case_count(payload)
        required_minimum_count = _as_int(
            requirement.get("required_minimum_count"),
            default=target_subset_case_count,
        )
        source_artifact_contract_pass = payload.get("contract_pass") is True
        source_artifact_ready = _ready_field_value(
            payload,
            str(requirement["ready_field"]),
        )
        if role == "pose_validity_packet":
            source_artifact_ready = bool(
                source_artifact_contract_pass or _pose_packet_validation_ready(payload)
            )
        blockers = [
            str(blocker) for blocker in _as_list(payload.get("blockers")) if str(blocker)
        ]
        if current_count < required_minimum_count:
            blockers.append(
                f"{count_field}_below_required:"
                f"{current_count}<{required_minimum_count}"
            )
        blockers = list(dict.fromkeys(blockers))
        ready = bool(
            source_artifact_ready
            and source_artifact_contract_pass
            and current_count >= required_minimum_count
            and not blockers
        )
        missing_row_inputs = (
            [] if ready else [str(row) for row in requirement["required_row_inputs"]]
        )
        status = str(payload.get("status") or "operator_evidence_required")
        if blockers and any(
            blocker.startswith(f"{count_field}_below_required:")
            for blocker in blockers
        ):
            status = "phase2_count_incomplete"
        elif blockers:
            status = "operator_evidence_required"
        rows.append(
            {
                "component_id": str(requirement["component_id"]),
                "requirement": str(requirement["requirement"]),
                "criterion_id": str(requirement["criterion_id"]),
                "artifact_role": role,
                "status": status,
                "contract_pass": ready,
                "source_artifact_contract_pass": source_artifact_contract_pass,
                "source_artifact_ready": source_artifact_ready,
                "ready_field": str(requirement["ready_field"]),
                "ready": ready,
                "materialized": True,
                "operator_evidence_required": not ready,
                "count_field": count_field,
                "current_count": current_count,
                "required_minimum_count": required_minimum_count,
                "required_row_inputs": [
                    str(row) for row in requirement["required_row_inputs"]
                ],
                "missing_row_inputs": missing_row_inputs,
                "expected_rows_mode": "operator_attached_public_benchmark_rows",
                "related_operator_slot_ids": [
                    str(row) for row in requirement["related_operator_slot_ids"]
                ],
                "blocker_count": len(blockers),
                "blockers": blockers,
            }
        )
    return rows


def _phase2_requirement_summary(
    requirement_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    blocked_component_ids = [
        str(row["component_id"]) for row in requirement_rows if not row["ready"]
    ]
    missing_row_inputs = sorted(
        {
            str(input_id)
            for row in requirement_rows
            for input_id in _as_list(row.get("missing_row_inputs"))
        }
    )
    ready_component_count = sum(1 for row in requirement_rows if row["ready"])
    return {
        "required_component_count": len(requirement_rows),
        "ready_component_count": ready_component_count,
        "blocked_component_count": len(blocked_component_ids),
        "materialized_component_count": sum(
            1 for row in requirement_rows if row.get("materialized")
        ),
        "operator_evidence_required_count": sum(
            1 for row in requirement_rows if row.get("operator_evidence_required")
        ),
        "missing_row_input_count": len(missing_row_inputs),
        "missing_row_inputs": missing_row_inputs,
        "phase2_ready": bool(requirement_rows)
        and ready_component_count == len(requirement_rows),
        "blocked_component_ids": blocked_component_ids,
    }


def _operator_context_by_slice(
    *,
    blocked_slice: dict[str, Any],
    operator_evidence_gap_register: list[dict[str, Any]],
    operator_blocker_detail_register: list[dict[str, Any]],
) -> dict[str, Any]:
    slice_id = str(blocked_slice.get("slice_id") or "")
    slot_ids = PHASE2_SLICE_OPERATOR_SLOT_IDS.get(slice_id, [])
    criteria_ids = PHASE2_SLICE_TIER_BETA_CRITERIA.get(slice_id, [])
    detail_by_slot = {
        str(row.get("slot_id") or ""): row
        for row in operator_blocker_detail_register
        if isinstance(row, dict)
    }
    gap_by_slot = {
        str(row.get("slot_id") or ""): row
        for row in operator_evidence_gap_register
        if isinstance(row, dict)
    }
    related_details = [
        detail_by_slot[slot_id] for slot_id in slot_ids if slot_id in detail_by_slot
    ]
    related_gaps = [
        gap_by_slot[slot_id] for slot_id in slot_ids if slot_id in gap_by_slot
    ]
    first_detail = related_details[0] if related_details else {}
    first_gap = related_gaps[0] if related_gaps else {}
    first_blocked_target = str(first_detail.get("slot_id") or "")
    if not first_blocked_target and slot_ids:
        first_blocked_target = slot_ids[0]
    blockers = [str(blocker) for blocker in blocked_slice.get("blockers", [])]
    operator_blockers = []
    for detail in related_details:
        operator_blockers.extend(
            str(blocker) for blocker in detail.get("blockers", []) if str(blocker)
        )
    operator_blockers = list(dict.fromkeys(operator_blockers))
    first_blocker = blockers[0] if blockers else ""
    first_operator_blocker = str(first_detail.get("first_blocker") or "")
    next_action = PHASE2_SLICE_NEXT_ACTION.get(slice_id) or str(
        first_detail.get("first_next_action") or first_gap.get("first_next_action") or ""
    )
    return {
        "operator_slot_id": first_blocked_target,
        "related_operator_slot_ids": list(slot_ids),
        "operator_handoff_id": (
            f"public_benchmark::{first_blocked_target}"
            if first_blocked_target
            else ""
        ),
        "operator_handoff_ids": [
            f"public_benchmark::{slot_id}" for slot_id in slot_ids if slot_id
        ],
        "first_blocker": first_blocker,
        "first_operator_blocker": first_operator_blocker,
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": list(PHASE2_SLICE_ROOT_CAUSE_TAGS.get(slice_id, [])),
        "blocked_tier_beta_criteria": list(criteria_ids),
        "operator_blockers": operator_blockers,
        "next_action": next_action,
        "template_artifact": str(
            first_detail.get("template_artifact")
            or first_gap.get("template_artifact")
            or ""
        ),
        "materialization_command": str(
            first_detail.get("materialization_command")
            or first_gap.get("materialization_command")
            or ""
        ),
        "validation_command": str(
            first_detail.get("validation_command")
            or first_gap.get("validation_command")
            or ""
        ),
        "minimum_evidence": dict(
            first_detail.get("minimum_evidence")
            or first_gap.get("minimum_evidence")
            or {}
        ),
    }


def _attach_operator_context_to_blocked_slices(
    *,
    blocked_slices: list[dict[str, Any]],
    operator_evidence_gap_register: list[dict[str, Any]],
    operator_blocker_detail_register: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched_slices = []
    for blocked_slice in blocked_slices:
        enriched_slice = dict(blocked_slice)
        enriched_slice.update(
            _operator_context_by_slice(
                blocked_slice=blocked_slice,
                operator_evidence_gap_register=operator_evidence_gap_register,
                operator_blocker_detail_register=operator_blocker_detail_register,
            )
        )
        enriched_slices.append(enriched_slice)
    return enriched_slices


def _source_tracking_contract(
    *, metadata: dict[str, Any], source_paths: list[Path]
) -> dict[str, Any]:
    input_checksums = metadata.get("input_checksums")
    if not isinstance(input_checksums, dict):
        input_checksums = {}
    source_artifacts = [path.as_posix() for path in source_paths]
    missing_source_artifacts = [
        path for path in source_artifacts if input_checksums.get(path) == "missing"
    ]
    return {
        "mode": "direct_builder_source_tracking",
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "input_checksum_count": len(input_checksums),
        "missing_source_artifact_count": len(missing_source_artifacts),
        "missing_source_artifacts": missing_source_artifacts,
        "claim_boundary": (
            "This source-of-truth seed is generated from local builder and validator "
            "code only. Checksums cover those direct source artifacts, not external "
            "CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA benchmark data."
        ),
    }


def _phase2_slice_progress(
    *,
    subset_manifest: dict[str, Any],
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    pose_success_harness: dict[str, Any],
    enrichment_scorecard: dict[str, Any],
    vina_gnina_comparison_adapter: dict[str, Any],
    external_receipts_validation: dict[str, Any],
    operator_intake_packet: dict[str, Any],
    tier_beta_gate: dict[str, Any],
    operator_evidence_gap_register: list[dict[str, Any]],
    operator_blocker_detail_register: list[dict[str, Any]],
) -> dict[str, Any]:
    target_subset_case_count = int(subset_manifest["target_subset_case_count"])
    subset_materialized_count = int(subset_manifest["materialized_case_count"])
    pose_real_case_count = _pose_packet_real_case_count(pose_validity_packet)
    rmsd_real_case_count = int(rmsd_scorecard["real_benchmark_case_count"])
    pose_success_harness_real_case_count = int(
        pose_success_harness["real_benchmark_case_count"]
    )
    enrichment_target_count = int(enrichment_scorecard["real_enrichment_target_count"])
    vina_gnina_case_count = int(
        vina_gnina_comparison_adapter["real_comparison_case_count"]
    )
    receipt_coverage = (
        external_receipts_validation.get("receipt_coverage")
        if isinstance(external_receipts_validation.get("receipt_coverage"), dict)
        else {}
    )
    receipt_complete_artifact_role_count = int(
        receipt_coverage.get("receipt_complete_artifact_role_count") or 0
    )
    receipt_missing_artifact_role_count = int(
        receipt_coverage.get("missing_expected_artifact_role_count") or 0
    )
    missing_receipt_artifact_roles = [
        str(role)
        for role in receipt_coverage.get("missing_expected_artifact_roles", [])
    ]
    pose_coordinate_blockers = []
    if pose_real_case_count < target_subset_case_count:
        pose_coordinate_blockers.append("public_benchmark_real_pose_predictions_missing")
        pose_coordinate_blockers.append(
            "public_benchmark_real_pose_validity_rows_missing"
        )
    if rmsd_real_case_count < target_subset_case_count:
        pose_coordinate_blockers.append("public_benchmark_real_rmsd_rows_missing")
    if pose_success_harness_real_case_count < target_subset_case_count:
        pose_coordinate_blockers.append(
            "public_benchmark_pose_success_harness_rows_missing"
        )
    completed_slices = [
        {
            "slice_id": "public_benchmark_source_of_truth_spec",
            "status": "contract_ready",
            "artifact": str(DEFAULT_SOURCE_OF_TRUTH_OUT),
            "evidence": [
                "schema_version",
                "tier_beta_gate",
                "operator_handoff_queue",
                "source_tracking",
            ],
        },
        {
            "slice_id": "casf_pdbbind_subset_manifest_contract",
            "status": "contract_ready",
            "artifact": str(DEFAULT_SUBSET_MANIFEST_OUT),
            "target_subset_case_count": target_subset_case_count,
            "materialized_case_count": subset_materialized_count,
        },
        {
            "slice_id": "symmetry_aware_rmsd_scorer_dry_run",
            "status": "dry_run_ready",
            "artifact": str(DEFAULT_RMSD_SCORECARD_OUT),
            "dry_run_case_count": int(rmsd_scorecard["dry_run_case_count"]),
            "real_benchmark_case_count": rmsd_real_case_count,
        },
        {
            "slice_id": "posebusters_style_validity_packet_shape",
            "status": "dry_run_ready",
            "artifact": str(DEFAULT_POSE_VALIDITY_PACKET_OUT),
            "check_count": len(pose_validity_packet["checks"]),
            "real_benchmark_case_count": pose_real_case_count,
        },
        {
            "slice_id": "casf_pdbbind_pose_success_harness_contract",
            "status": "contract_ready",
            "artifact": str(DEFAULT_POSE_SUCCESS_HARNESS_OUT),
            "materializer_schema_version": _materializer_schema_version(
                pose_success_harness
            ),
            "dry_run_case_count": int(pose_success_harness["dry_run_case_count"]),
            "real_benchmark_case_count": pose_success_harness_real_case_count,
        },
        {
            "slice_id": "operator_intake_handoff_packet",
            "status": "ready_for_operator_input",
            "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
            "required_slot_count": int(operator_intake_packet["required_slot_count"]),
        },
        {
            "slice_id": "public_benchmark_external_receipt_contract",
            "status": "contract_ready",
            "artifact": str(DEFAULT_EXTERNAL_RECEIPTS_VALIDATION_OUT),
            "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
            "required_subset_receipt_fields": list(REQUIRED_SUBSET_RECEIPT_FIELDS),
            "materialized_row_count": int(
                external_receipts_validation["materialized_row_count"]
            ),
            "receipt_complete_row_count": int(
                external_receipts_validation["receipt_complete_row_count"]
            ),
        },
    ]
    blocked_slices = []
    if subset_materialized_count < target_subset_case_count:
        blocked_slices.append(
            {
                "slice_id": "casf_pdbbind_subset_materialization",
                "status": "operator_source_material_required",
                "current": subset_materialized_count,
                "required": target_subset_case_count,
                "blockers": list(subset_manifest["blockers"]),
            }
        )
    if pose_coordinate_blockers:
        blocked_slices.append(
            {
                "slice_id": "real_pose_coordinate_materialization",
                "status": "operator_pose_coordinates_required",
                "current": {
                    "real_pose_case_count": pose_real_case_count,
                    "real_rmsd_case_count": rmsd_real_case_count,
                    "real_pose_success_harness_case_count": (
                        pose_success_harness_real_case_count
                    ),
                },
                "required": target_subset_case_count,
                "blockers": pose_coordinate_blockers,
            }
        )
    if not bool(enrichment_scorecard["public_benchmark_enrichment_ready"]):
        blocked_slices.append(
            {
                "slice_id": "dud_e_lit_pcba_enrichment_materialization",
                "status": "operator_enrichment_rows_required",
                "current": enrichment_target_count,
                "required": ">=1_ready_target_with_active_decoy_labels",
                "blockers": list(enrichment_scorecard["blockers"]),
            }
        )
    if not bool(
        vina_gnina_comparison_adapter["public_benchmark_engine_comparison_ready"]
    ):
        blocked_slices.append(
            {
                "slice_id": "vina_gnina_comparison_materialization",
                "status": "operator_engine_comparison_rows_required",
                "current": vina_gnina_case_count,
                "required": ">=1_case_with_vina_and_gnina_engine_runs",
                "blockers": list(vina_gnina_comparison_adapter["blockers"]),
            }
        )
    if not bool(
        external_receipts_validation["public_benchmark_external_receipts_ready"]
    ):
        blocked_slices.append(
            {
                "slice_id": "public_benchmark_external_receipts_validation",
                "status": "operator_receipts_required",
                "current": {
                    "materialized_row_count": int(
                        external_receipts_validation["materialized_row_count"]
                    ),
                    "receipt_complete_row_count": int(
                        external_receipts_validation["receipt_complete_row_count"]
                    ),
                    "receipt_complete_artifact_role_count": (
                        receipt_complete_artifact_role_count
                    ),
                },
                "required": {
                    "receipt_complete_artifact_role_count": int(
                        receipt_coverage.get("expected_artifact_role_count") or 0
                    ),
                    "artifact_roles": list(
                        receipt_coverage.get("expected_artifact_roles", [])
                    ),
                },
                "missing_artifact_roles": missing_receipt_artifact_roles,
                "blockers": list(external_receipts_validation["blockers"]),
            }
        )
    blocked_slices = _attach_operator_context_to_blocked_slices(
        blocked_slices=blocked_slices,
        operator_evidence_gap_register=operator_evidence_gap_register,
        operator_blocker_detail_register=operator_blocker_detail_register,
    )
    return {
        "completed_slices": completed_slices,
        "blocked_slices": blocked_slices,
        "materialization_progress": {
            "completed_slice_count": len(completed_slices),
            "blocked_slice_count": len(blocked_slices),
            "target_subset_case_count": target_subset_case_count,
            "materialized_subset_case_count": subset_materialized_count,
            "real_pose_case_count": pose_real_case_count,
            "real_rmsd_case_count": rmsd_real_case_count,
            "real_pose_success_harness_case_count": (
                pose_success_harness_real_case_count
            ),
            "real_enrichment_target_count": enrichment_target_count,
            "real_vina_gnina_comparison_case_count": vina_gnina_case_count,
            "external_receipt_complete_row_count": int(
                external_receipts_validation["receipt_complete_row_count"]
            ),
            "external_receipt_complete_artifact_role_count": (
                receipt_complete_artifact_role_count
            ),
            "external_receipt_missing_artifact_role_count": (
                receipt_missing_artifact_role_count
            ),
            "tier_beta_failed_criterion_count": int(
                tier_beta_gate["failed_criterion_count"]
            ),
            "next_unblock_slice_id": (
                blocked_slices[0]["slice_id"] if blocked_slices else ""
            ),
            "claim_boundary": (
                "Completed slices are repo-local contracts or synthetic dry-runs. "
                "Blocked slices require operator-attached public benchmark rows and "
                "external receipts before Tier beta can be claimed."
            ),
        },
    }


def build_source_of_truth(
    *,
    subset_manifest: dict[str, Any],
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    pose_success_harness: dict[str, Any],
    enrichment_scorecard: dict[str, Any],
    vina_gnina_comparison_adapter: dict[str, Any],
    external_receipts_validation: dict[str, Any],
    operator_intake_packet: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    target_subset_case_count = int(subset_manifest["target_subset_case_count"])
    subset_materialized_count = int(subset_manifest["materialized_case_count"])
    subset_case_rows = [
        row for row in subset_manifest.get("case_rows", []) if isinstance(row, dict)
    ]
    subset_source_material_coverage = source_material_coverage_summary(
        subset_case_rows,
        target_subset_case_count=target_subset_case_count,
    )
    pose_real_case_count = _pose_packet_real_case_count(pose_validity_packet)
    rmsd_real_case_count = int(rmsd_scorecard["real_benchmark_case_count"])
    pose_success_harness_real_case_count = int(
        pose_success_harness["real_benchmark_case_count"]
    )
    pose_success_harness_ready = bool(
        pose_success_harness["pose_success_harness_ready"]
    )
    enrichment_ready = bool(enrichment_scorecard["public_benchmark_enrichment_ready"])
    engine_comparison_ready = bool(
        vina_gnina_comparison_adapter["public_benchmark_engine_comparison_ready"]
    )
    external_receipts_ready = bool(
        external_receipts_validation["public_benchmark_external_receipts_ready"]
    )
    tier_beta_gate = {
        "status": "blocked",
        "claim": "tier_beta_public_benchmark_harness",
        "minimum_subset_case_count": target_subset_case_count,
        "criteria": [
            {
                "criterion_id": "casf_pdbbind_subset_materialized",
                "pass": bool(subset_materialized_count >= target_subset_case_count),
                "current": subset_materialized_count,
                "required": target_subset_case_count,
                "blockers": subset_manifest["blockers"],
            },
            {
                "criterion_id": "real_pose_validity_packet_materialized",
                "pass": bool(pose_real_case_count >= target_subset_case_count),
                "current": pose_real_case_count,
                "required": target_subset_case_count,
                "blockers": ["public_benchmark_real_pose_predictions_missing"]
                if pose_real_case_count < target_subset_case_count
                else [],
            },
            {
                "criterion_id": "symmetry_rmsd_scorecard_real_cases",
                "pass": bool(rmsd_real_case_count >= target_subset_case_count),
                "current": rmsd_real_case_count,
                "required": target_subset_case_count,
                "blockers": ["public_benchmark_real_rmsd_rows_missing"]
                if rmsd_real_case_count < target_subset_case_count
                else [],
            },
            {
                "criterion_id": "posebusters_style_validity_real_ligands",
                "pass": bool(pose_real_case_count >= target_subset_case_count),
                "current": pose_real_case_count,
                "required": target_subset_case_count,
                "blockers": ["public_benchmark_real_pose_validity_rows_missing"]
                if pose_real_case_count < target_subset_case_count
                else [],
            },
            {
                "criterion_id": "casf_pdbbind_pose_success_harness_ready",
                "pass": bool(
                    pose_success_harness_ready
                    and pose_success_harness_real_case_count >= target_subset_case_count
                ),
                "current": {
                    "real_benchmark_case_count": pose_success_harness_real_case_count,
                    "pose_success_harness_ready": pose_success_harness_ready,
                },
                "required": {
                    "real_benchmark_case_count": target_subset_case_count,
                    "pose_success_harness_ready": True,
                },
                "blockers": ["public_benchmark_pose_success_harness_rows_missing"]
                if (
                    not pose_success_harness_ready
                    or pose_success_harness_real_case_count < target_subset_case_count
                )
                else [],
            },
            {
                "criterion_id": "dud_e_lit_pcba_enrichment_ready",
                "pass": enrichment_ready,
                "current": enrichment_scorecard["real_enrichment_target_count"],
                "required": ">=1_ready_target_with_active_decoy_labels",
                "blockers": enrichment_scorecard["blockers"],
            },
            {
                "criterion_id": "vina_gnina_comparison_ready",
                "pass": engine_comparison_ready,
                "current": vina_gnina_comparison_adapter["real_comparison_case_count"],
                "required": ">=1_case_with_vina_and_gnina_engine_runs",
                "blockers": vina_gnina_comparison_adapter["blockers"],
            },
            {
                "criterion_id": "external_receipts_attached",
                "pass": external_receipts_ready,
                "current": external_receipts_validation["receipt_complete_row_count"],
                "required": "source_license_or_accession_and_provenance_receipts_for_all_materialized_rows",
                "blockers": external_receipts_validation["blockers"]
                if not external_receipts_ready
                else [],
            },
        ],
    }
    failed_gate_criteria = [
        row["criterion_id"] for row in tier_beta_gate["criteria"] if not row["pass"]
    ]
    tier_beta_gate["failed_criterion_count"] = len(failed_gate_criteria)
    tier_beta_gate["failed_criteria"] = failed_gate_criteria
    tier_beta_ready = not failed_gate_criteria
    tier_beta_gate["status"] = "ready" if tier_beta_ready else "blocked"
    first_rmsd_row = next(
        (row for row in rmsd_scorecard.get("rows", []) if isinstance(row, dict)),
        {},
    )
    first_rmsd_score = _as_dict(first_rmsd_row.get("score"))
    symmetry_rmsd_scorecard_summary = {
        "status": rmsd_scorecard["status"],
        "dry_run_case_count": rmsd_scorecard["dry_run_case_count"],
        "real_benchmark_case_count": rmsd_scorecard["real_benchmark_case_count"],
        "dry_run_pose_success": (
            bool(first_rmsd_score["pose_success"])
            if "pose_success" in first_rmsd_score
            else None
        ),
    }
    operator_evidence_gap_register = _operator_evidence_gap_register(
        tier_beta_gate=tier_beta_gate,
        operator_intake_packet=operator_intake_packet,
    )
    operator_blocker_detail_register = _operator_blocker_detail_register(
        tier_beta_gate=tier_beta_gate,
        operator_evidence_gap_register=operator_evidence_gap_register,
    )
    first_operator_evidence_gap = next(
        (row for row in operator_evidence_gap_register if row["tier_beta_blocked"]),
        {},
    )
    first_blocked_target = str(first_operator_evidence_gap.get("slot_id") or "")
    first_manifest_contract: dict[str, Any] = {}
    for slot in operator_intake_packet.get("input_slots", []):
        if not isinstance(slot, dict):
            continue
        if str(slot.get("slot_id") or "") != first_blocked_target:
            continue
        candidate = slot.get("manifest_contract")
        if isinstance(candidate, dict):
            first_manifest_contract = candidate
        break
    first_manifest_contract_id = str(first_manifest_contract.get("contract_id") or "")
    blockers = []
    if subset_materialized_count < target_subset_case_count:
        blockers.extend(str(blocker) for blocker in subset_manifest["blockers"])
    if pose_real_case_count < target_subset_case_count:
        blockers.append("public_benchmark_real_pose_predictions_missing")
        blockers.append("public_benchmark_real_pose_validity_rows_missing")
    if rmsd_real_case_count < target_subset_case_count:
        blockers.append("public_benchmark_real_rmsd_rows_missing")
    if (
        not pose_success_harness_ready
        or pose_success_harness_real_case_count < target_subset_case_count
    ):
        blockers.append("public_benchmark_pose_success_harness_rows_missing")
    if not enrichment_ready:
        blockers.append("dud_e_lit_pcba_enrichment_rows_missing")
    if not engine_comparison_ready:
        blockers.append("vina_gnina_comparison_rows_missing")
    if not external_receipts_ready:
        blockers.append("public_benchmark_external_receipts_missing")
    root_cause_tags = (
        ["operator_source_material_required", "operator_receipts_required"]
        if blockers
        else []
    )
    blocked_operator_slot_count = sum(
        1 for row in operator_evidence_gap_register if row["tier_beta_blocked"]
    )
    operator_handoff_summary = {
        "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
        "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
        "first_blocker": blockers[0] if blockers else "",
        "first_blocked_target": first_blocked_target,
        "manifest_contract_id": first_manifest_contract_id,
        "first_next_action": str(
            first_operator_evidence_gap.get("first_next_action") or ""
        ),
        "required_slot_count": int(operator_intake_packet["required_slot_count"]),
        "operator_template_schema_version": str(
            operator_intake_packet.get("operator_template_schema_version") or ""
        ),
        "operator_template_artifact_count": int(
            operator_intake_packet.get("operator_template_artifact_count") or 0
        ),
        "operator_template_artifacts": dict(
            operator_intake_packet.get("operator_template_artifacts") or {}
        ),
        "blocked_operator_slot_count": blocked_operator_slot_count,
        "minimum_evidence": dict(
            first_operator_evidence_gap.get("minimum_evidence") or {}
        ),
        "materialization_command": str(
            first_operator_evidence_gap.get("materialization_command") or ""
        ),
        "validation_command": str(
            first_operator_evidence_gap.get("validation_command") or ""
        ),
        "template_artifact": str(
            first_operator_evidence_gap.get("template_artifact") or ""
        ),
    }
    operator_handoff_queue = [
        {
            "queue_priority": int(row["slot_priority"]),
            "handoff_id": f"public_benchmark::{row['slot_id']}",
            "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
            "operator_intake_artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
            "operator_intake_markdown_artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT),
            "slot_id": str(row.get("slot_id") or ""),
            "status": str(row.get("status") or ""),
            "first_next_action": str(row.get("first_next_action") or ""),
            "template_artifact": str(row.get("template_artifact") or ""),
            "blocked_tier_beta_criteria": [
                str(item) for item in row.get("blocked_tier_beta_criteria", [])
            ],
            "minimum_evidence": dict(row.get("minimum_evidence") or {}),
            "materialization_steps": [
                str(step) for step in row.get("materialization_steps", [])
            ],
            "materialization_command": str(row.get("materialization_command") or ""),
            "validation_command": str(row.get("validation_command") or ""),
            "depends_on": [str(path) for path in row.get("depends_on", [])],
        }
        for row in operator_evidence_gap_register
        if row.get("tier_beta_blocked")
    ]
    linked_operator_artifacts = dict(operator_intake_packet.get("linked_artifacts") or {})
    operator_bundle_materialization = dict(
        operator_intake_packet.get("operator_bundle_materialization") or {}
    )
    operator_bundle_outputs = dict(operator_bundle_materialization.get("produces") or {})
    harness_bundle_artifact = str(
        linked_operator_artifacts.get("harness_bundle")
        or operator_bundle_outputs.get("artifact_bundle")
        or DEFAULT_HARNESS_BUNDLE_OUT
    )
    source_input_paths = _source_input_paths()
    metadata = release_evidence_metadata(
        input_paths=source_input_paths,
        reused_evidence=False,
        reuse_policy="public_benchmark_contract_generated_from_repo_code",
        repo_root=repo_root,
    )
    source_tracking = _source_tracking_contract(
        metadata=metadata,
        source_paths=source_input_paths,
    )
    slice_progress = _phase2_slice_progress(
        subset_manifest=subset_manifest,
        pose_validity_packet=pose_validity_packet,
        rmsd_scorecard=rmsd_scorecard,
        pose_success_harness=pose_success_harness,
        enrichment_scorecard=enrichment_scorecard,
        vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
        external_receipts_validation=external_receipts_validation,
        operator_intake_packet=operator_intake_packet,
        tier_beta_gate=tier_beta_gate,
        operator_evidence_gap_register=operator_evidence_gap_register,
        operator_blocker_detail_register=operator_blocker_detail_register,
    )
    phase2_requirements = _phase2_requirement_rows(
        target_subset_case_count=target_subset_case_count,
        pose_validity_packet=pose_validity_packet,
        rmsd_scorecard=rmsd_scorecard,
        pose_success_harness=pose_success_harness,
        enrichment_scorecard=enrichment_scorecard,
        vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
    )
    phase2_requirement_summary = _phase2_requirement_summary(phase2_requirements)
    return {
        "schema_version": SCHEMA_VERSION,
        **metadata,
        "status": "ready" if tier_beta_ready else "seed_ready_materialization_blocked",
        "summary_line": (
            "Public benchmark source-of-truth: "
            f"{'READY' if tier_beta_ready else 'BLOCKED'} | "
            f"completed_slices={slice_progress['materialization_progress']['completed_slice_count']} | "
            f"blocked_slices={slice_progress['materialization_progress']['blocked_slice_count']} | "
            f"first_blocker={blockers[0] if blockers else 'none'}"
        ),
        "contract_pass": True,
        "read_model_ready": True,
        "route": PUBLIC_BENCHMARK_ROUTE,
        "read_model": {
            "route": PUBLIC_BENCHMARK_ROUTE,
            "alternate_routes": [
                PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
                "/product/capabilities",
                "/goal/bottleneck",
            ],
            "artifact": str(DEFAULT_SOURCE_OF_TRUTH_OUT),
            "mutation_allowed": False,
        },
        "tier_beta_ready": tier_beta_ready,
        "public_benchmark_ready": tier_beta_ready,
        "blocker_count": len(blockers),
        "first_blocker": blockers[0] if blockers else "",
        "first_blocked_target": first_blocked_target,
        "first_required_operator_slot": first_blocked_target,
        "first_manifest_contract_id": first_manifest_contract_id,
        "first_manifest_contract": first_manifest_contract,
        "casf_pdbbind_subset_manifest_contract": first_manifest_contract,
        "required_slot_count": int(operator_intake_packet["required_slot_count"]),
        "operator_template_schema_version": str(
            operator_intake_packet.get("operator_template_schema_version") or ""
        ),
        "operator_template_artifact_count": int(
            operator_intake_packet.get("operator_template_artifact_count") or 0
        ),
        "operator_template_artifacts": dict(
            operator_intake_packet.get("operator_template_artifacts") or {}
        ),
        "blocked_operator_slot_count": blocked_operator_slot_count,
        "root_cause_tags": root_cause_tags,
        "source_tracking": source_tracking,
        "completed_slices": slice_progress["completed_slices"],
        "blocked_slices": slice_progress["blocked_slices"],
        "materialization_progress": slice_progress["materialization_progress"],
        "phase2_requirements": phase2_requirements,
        "phase2_requirement_summary": phase2_requirement_summary,
        "operator_handoff_summary": operator_handoff_summary,
        "operator_handoff_queue_count": len(operator_handoff_queue),
        "first_operator_handoff": (
            operator_handoff_queue[0] if operator_handoff_queue else {}
        ),
        "operator_handoff_queue": operator_handoff_queue,
        "operator_blocker_detail_count": len(operator_blocker_detail_register),
        "first_operator_blocker_detail": (
            operator_blocker_detail_register[0]
            if operator_blocker_detail_register
            else {}
        ),
        "operator_blocker_detail_register": operator_blocker_detail_register,
        "tier_beta_gate": tier_beta_gate,
        "harness_bundle_index": {
            "schema_version": "public-benchmark-harness-bundle.v1",
            "artifact": harness_bundle_artifact,
            "status": "ready_for_local_artifact_index",
            "artifact_index_command": str(
                operator_bundle_materialization.get("artifact_index_command") or ""
            ),
            "materialization_report": str(
                operator_bundle_outputs.get("bundle_report") or ""
            ),
            "claim_boundary": (
                "Indexes local public-benchmark harness artifacts only; it does not "
                "fetch, license, redistribute, or approve external benchmark data."
            ),
        },
        "linked_artifacts": {
            "harness_bundle": harness_bundle_artifact,
            "operator_intake_packet": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
            "operator_intake_packet_markdown": str(DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT),
        },
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
                "family_id": "casf_pdbbind_pose_success_harness",
                "role": "case_level_pose_success_harness",
                "materialization_status": "real_pose_rows_required",
            },
            {
                "family_id": "dud_e_lit_pcba",
                "role": "enrichment_scorecard",
                "materialization_status": "operator_intake_required",
            },
            {
                "family_id": "vina_gnina",
                "role": "docking_engine_comparison_adapter",
                "materialization_status": "operator_intake_required",
            },
        ],
        "subset_manifest_summary": {
            "target_subset_case_count": subset_manifest["target_subset_case_count"],
            "materialized_case_count": subset_manifest["materialized_case_count"],
            "source_material_coverage": subset_source_material_coverage,
            "blockers": subset_manifest["blockers"],
        },
        "pose_validity_packet_summary": {
            "status": pose_validity_packet["status"],
            "check_count": len(pose_validity_packet["checks"]),
            "required_check_count": sum(
                1 for row in pose_validity_packet["checks"] if row["required"]
            ),
            "validator_schema_version": _pose_packet_validator_schema_version(
                pose_validity_packet
            ),
            "materializer_schema_version": _pose_packet_materializer_schema_version(
                pose_validity_packet
            ),
            "dry_run_pose_validity_ready": _pose_packet_validation_ready(
                pose_validity_packet
            ),
            "real_benchmark_case_count": pose_real_case_count,
        },
        "symmetry_rmsd_scorecard_summary": symmetry_rmsd_scorecard_summary,
        "symmetry_rmsd_summary": symmetry_rmsd_scorecard_summary,
        "pose_success_harness_summary": {
            "status": pose_success_harness["status"],
            "pose_success_harness_ready": pose_success_harness[
                "pose_success_harness_ready"
            ],
            "case_count": pose_success_harness["case_count"],
            "dry_run_case_count": pose_success_harness["dry_run_case_count"],
            "real_benchmark_case_count": pose_success_harness[
                "real_benchmark_case_count"
            ],
            "pose_success_count": pose_success_harness["pose_success_count"],
            "pose_success_rate": pose_success_harness["pose_success_rate"],
            "blockers": pose_success_harness["blockers"],
        },
        "enrichment_scorecard_summary": {
            "status": enrichment_scorecard["status"],
            "public_benchmark_enrichment_ready": enrichment_scorecard[
                "public_benchmark_enrichment_ready"
            ],
            "real_enrichment_target_count": enrichment_scorecard[
                "real_enrichment_target_count"
            ],
            "blockers": enrichment_scorecard["blockers"],
        },
        "vina_gnina_comparison_adapter_summary": {
            "status": vina_gnina_comparison_adapter["status"],
            "public_benchmark_engine_comparison_ready": vina_gnina_comparison_adapter[
                "public_benchmark_engine_comparison_ready"
            ],
            "real_comparison_case_count": vina_gnina_comparison_adapter[
                "real_comparison_case_count"
            ],
            "supported_engines": vina_gnina_comparison_adapter["supported_engines"],
            "blockers": vina_gnina_comparison_adapter["blockers"],
        },
        "external_receipts_summary": {
            "status": external_receipts_validation["status"],
            "public_benchmark_external_receipts_ready": external_receipts_validation[
                "public_benchmark_external_receipts_ready"
            ],
            "materialized_row_count": external_receipts_validation[
                "materialized_row_count"
            ],
            "receipt_complete_row_count": external_receipts_validation[
                "receipt_complete_row_count"
            ],
            "receipt_blocked_row_count": external_receipts_validation[
                "receipt_blocked_row_count"
            ],
            "receipt_coverage": dict(
                external_receipts_validation.get("receipt_coverage") or {}
            ),
            "blockers": external_receipts_validation["blockers"],
        },
        "external_receipts_validation": external_receipts_validation,
        "external_receipts_validator": {
            "schema_version": EXTERNAL_RECEIPT_VALIDATION_SCHEMA_VERSION,
            "status": "ready_for_materialized_rows",
            "required_receipt_fields": list(REQUIRED_RECEIPT_FIELDS),
            "required_subset_receipt_fields": list(REQUIRED_SUBSET_RECEIPT_FIELDS),
            "validation_command": (
                "python3 scripts/validate_public_benchmark_external_receipts.py "
                "--subset-manifest implementation/phase1/release_evidence/"
                "productization/public_benchmark_subset_manifest.json "
                "--enrichment-scorecard implementation/phase1/release_evidence/"
                "productization/public_benchmark_enrichment_scorecard.json "
                "--vina-gnina-comparison-adapter implementation/phase1/"
                "release_evidence/productization/"
                "public_benchmark_vina_gnina_comparison_adapter.json "
                "--out implementation/phase1/release_evidence/productization/"
                "public_benchmark_external_receipts_validation.json --fail-blocked"
            ),
            "claim_boundary": external_receipts_validation["claim_boundary"],
        },
        "operator_intake_packet": {
            "schema_version": operator_intake_packet["schema_version"],
            "status": operator_intake_packet["status"],
            "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
            "markdown_artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT),
            "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
            "read_model": {
                "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
                "alternate_routes": [PUBLIC_BENCHMARK_ROUTE, "/product/capabilities"],
                "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
                "mutation_allowed": False,
            },
            "required_slot_count": operator_intake_packet["required_slot_count"],
            "input_slot_ids": [
                row["slot_id"] for row in operator_intake_packet["input_slots"]
            ],
            "manifest_contract_count": int(
                operator_intake_packet.get("manifest_contract_count") or 0
            ),
            "manifest_contracts": [
                row
                for row in operator_intake_packet.get("manifest_contracts", [])
                if isinstance(row, dict)
            ],
            "first_manifest_contract_id": str(
                operator_intake_packet.get("first_manifest_contract_id")
                or first_manifest_contract_id
            ),
            "first_manifest_contract": dict(
                operator_intake_packet.get("first_manifest_contract")
                or first_manifest_contract
            ),
            "gate_unblock_plan_count": operator_intake_packet[
                "gate_unblock_plan_count"
            ],
            "operator_template_schema_version": str(
                operator_intake_packet.get("operator_template_schema_version") or ""
            ),
            "operator_template_artifact_count": int(
                operator_intake_packet.get("operator_template_artifact_count") or 0
            ),
            "operator_template_artifacts": dict(
                operator_intake_packet.get("operator_template_artifacts") or {}
            ),
            "linked_artifacts": linked_operator_artifacts,
            "operator_bundle_materialization": operator_bundle_materialization,
            "minimum_subset_case_count": operator_intake_packet[
                "minimum_subset_case_count"
            ],
            "first_blocked_target": str(
                operator_intake_packet.get("first_blocked_target")
                or first_blocked_target
            ),
            "root_cause_tags": [
                str(row)
                for row in (
                    operator_intake_packet.get("root_cause_tags") or root_cause_tags
                )
            ],
            "operator_evidence_gap_count": int(
                operator_intake_packet.get("operator_evidence_gap_count")
                or len(operator_evidence_gap_register)
            ),
            "first_operator_evidence_gap": dict(
                operator_intake_packet.get("first_operator_evidence_gap")
                or first_operator_evidence_gap
            ),
            "source_of_truth_blocker_detail_count": len(operator_blocker_detail_register),
            "source_of_truth_first_blocker_detail": (
                operator_blocker_detail_register[0]
                if operator_blocker_detail_register
                else {}
            ),
            "gate_unblock_plan": operator_intake_packet["gate_unblock_plan"],
            "acceptance_criteria": operator_intake_packet["acceptance_criteria"],
            "materialization_sequence": [
                {
                    "step_id": row["step_id"],
                    "schema_version": row["schema_version"],
                    "produces": row["produces"],
                }
                for row in operator_intake_packet["materialization_sequence"]
            ],
            "claim_boundary": operator_intake_packet["claim_boundary"],
        },
        "operator_gate_unblock_plan": operator_intake_packet["gate_unblock_plan"],
        "operator_evidence_gap_register": operator_evidence_gap_register,
        "operator_evidence_gap_count": len(operator_evidence_gap_register),
        "first_operator_evidence_gap": first_operator_evidence_gap,
        "subset_manifest_validation": validate_subset_manifest(subset_manifest),
        "subset_materializer": {
            "schema_version": MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "intake_case_key": "cases",
            "required_case_fields": list(REQUIRED_CASE_FIELDS),
            "supported_benchmark_splits": list(SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS),
            "local_source_file_fields": [
                "protein_structure_path",
                "reference_ligand_path",
                "predicted_ligand_path_or_docking_run_id",
            ],
            "materialization_command": _nested_materialization_command(
                subset_manifest,
                "case_row_schema",
                (
                    "python3 scripts/materialize_public_benchmark_subset_manifest.py "
                    "--intake <operator-casf-pdbbind-intake.json> "
                    f"--out-manifest {DEFAULT_SUBSET_MANIFEST_OUT} "
                    f"--out-report {PRODUCTIZATION / 'public_benchmark_subset_materialization_report.json'} "
                    "--fail-blocked"
                ),
            ),
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
            "materialization_command": _nested_materialization_command(
                pose_validity_packet,
                "validator",
                (
                    "python3 scripts/materialize_public_benchmark_pose_validity_input.py "
                    f"--subset-manifest {DEFAULT_SUBSET_MANIFEST_OUT} "
                    "--pose-intake <operator-pose-coordinate-intake.json> "
                    f"--out-input {PRODUCTIZATION / 'public_benchmark_pose_validity_input.json'} "
                    f"--out-report {PRODUCTIZATION / 'public_benchmark_pose_validity_materialization_report.json'} "
                    "--fail-blocked"
                ),
            ),
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
            "materialization_command": _nested_materialization_command(
                rmsd_scorecard,
                "materializer",
                "python3 scripts/materialize_public_benchmark_rmsd_scorecard.py",
            ),
            "claim_boundary": (
                "The RMSD scorecard materializer consumes validated pose-coordinate input "
                "and produces per-case symmetry-aware ligand RMSD rows plus pose-success "
                "counts. It does not compare docking engines or close Tier beta alone."
            ),
        },
        "posebusters_validity_packet_materializer": {
            "schema_version": POSEBUSTERS_PACKET_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_input",
            "materialization_command": _nested_materialization_command(
                pose_validity_packet,
                "materializer",
                "python3 scripts/materialize_public_benchmark_posebusters_validity_packet.py",
            ),
            "claim_boundary": (
                "The PoseBusters-style packet materializer consumes validated "
                "pose-coordinate input and emits per-case sanity-check rows for real "
                "benchmark ligands. It does not infer chemistry or close Tier beta."
            ),
        },
        "pose_success_harness_materializer": {
            "schema_version": POSE_SUCCESS_HARNESS_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_packet_and_rmsd_scorecard",
            "materialization_command": _nested_materialization_command(
                pose_success_harness,
                "materializer",
                "python3 scripts/materialize_public_benchmark_pose_success_harness.py",
            ),
            "claim_boundary": (
                "The pose-success harness materializer joins per-case "
                "PoseBusters-style validity rows with symmetry-aware RMSD rows. It "
                "does not fetch benchmark data, run docking engines, or close Tier "
                "beta alone."
            ),
        },
        "enrichment_scorecard_materializer": {
            "schema_version": ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "materialization_command": _nested_materialization_command(
                enrichment_scorecard,
                "materializer",
                "python3 scripts/materialize_public_benchmark_enrichment_scorecard.py",
            ),
            "claim_boundary": (
                "The enrichment materializer consumes DUD-E/LIT-PCBA scored molecule "
                "rows and reports EF@1%, EF@5%, and ROC-AUC per target. It does not "
                "download benchmark data, validate chemistry, or close Tier beta alone."
            ),
        },
        "vina_gnina_comparison_materializer": {
            "schema_version": VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "materialization_command": _nested_materialization_command(
                vina_gnina_comparison_adapter,
                "materializer",
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py",
            ),
            "claim_boundary": (
                "The Vina/GNINA adapter materializer consumes operator-attached engine "
                "comparison rows and reports per-engine pose-success summaries. It does "
                "not run docking engines, fetch benchmark data, or close Tier beta alone."
            ),
        },
        "blockers": blockers,
        "next_actions": [
            "fill_public_benchmark_operator_intake_packet",
            "materialize_public_benchmark_operator_bundle_from_rows",
            "attach_checked_casf_pdbbind_subset_source_files",
            "run_public_benchmark_subset_materializer",
            "fill_ligand_atom_order_and_symmetry_permutation_contracts",
            "attach_public_benchmark_pose_coordinate_intake",
            "run_public_benchmark_pose_validity_materializer",
            "run_symmetry_aware_rmsd_on_real_subset",
            "run_public_benchmark_rmsd_scorecard_materializer",
            "materialize_posebusters_style_validity_packet_for_real_ligands",
            "materialize_casf_pdbbind_pose_success_harness",
            "attach_dud_e_lit_pcba_enrichment_intake",
            "run_public_benchmark_enrichment_materializer",
            "attach_vina_gnina_comparison_intake",
            "run_public_benchmark_vina_gnina_comparison_materializer",
        ],
        "claim_boundary": (
            "This is the Phase 2 public benchmark harness seed. It closes source-of-truth "
            "shape, subset contract, RMSD scorer dry-run, and pose-validity packet shape. "
            "It does not close Tier beta, public benchmark results, Vina/GNINA comparison, "
            "or DUD-E/LIT-PCBA enrichment results."
        ),
    }


def build_public_benchmark_artifacts(
    *, repo_root: Path = ROOT, operator_template_dir: Path = DEFAULT_OPERATOR_TEMPLATE_DIR
) -> dict[str, dict[str, Any]]:
    subset_manifest = build_subset_manifest(repo_root=repo_root)
    pose_validity_packet = build_pose_validity_packet(repo_root=repo_root)
    rmsd_scorecard = build_rmsd_scorecard(repo_root=repo_root)
    pose_success_harness = build_pose_success_harness(
        pose_validity_packet=pose_validity_packet,
        rmsd_scorecard=rmsd_scorecard,
        repo_root=repo_root,
    )
    enrichment_scorecard = build_enrichment_scorecard(repo_root=repo_root)
    vina_gnina_comparison_adapter = build_vina_gnina_comparison_adapter(
        repo_root=repo_root
    )
    external_receipts_validation = validate_external_receipts(
        subset_manifest=subset_manifest,
        enrichment_scorecard=enrichment_scorecard,
        vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
    )
    operator_intake_packet = build_public_benchmark_operator_intake_packet(
        repo_root=repo_root,
        operator_template_dir=operator_template_dir,
    )
    source_of_truth = build_source_of_truth(
        subset_manifest=subset_manifest,
        pose_validity_packet=pose_validity_packet,
        rmsd_scorecard=rmsd_scorecard,
        pose_success_harness=pose_success_harness,
        enrichment_scorecard=enrichment_scorecard,
        vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
        external_receipts_validation=external_receipts_validation,
        operator_intake_packet=operator_intake_packet,
        repo_root=repo_root,
    )
    source_blocker_detail_register = [
        row
        for row in source_of_truth.get("operator_blocker_detail_register", [])
        if isinstance(row, dict)
    ]
    operator_intake_packet = {
        **operator_intake_packet,
        "source_of_truth_blocker_detail_count": len(source_blocker_detail_register),
        "source_of_truth_first_blocker_detail": (
            source_blocker_detail_register[0]
            if source_blocker_detail_register
            else {}
        ),
        "source_of_truth_blocker_detail_register": source_blocker_detail_register,
        "summary": {
            **dict(operator_intake_packet.get("summary") or {}),
            "source_of_truth_blocker_detail_count": len(source_blocker_detail_register),
        },
    }
    return {
        "source_of_truth": source_of_truth,
        "subset_manifest": subset_manifest,
        "pose_validity_packet": pose_validity_packet,
        "rmsd_scorecard": rmsd_scorecard,
        "pose_success_harness": pose_success_harness,
        "enrichment_scorecard": enrichment_scorecard,
        "vina_gnina_comparison_adapter": vina_gnina_comparison_adapter,
        "external_receipts_validation": external_receipts_validation,
        "operator_intake_packet": operator_intake_packet,
    }


def write_public_benchmark_artifacts(
    *,
    repo_root: Path = ROOT,
    source_of_truth_out: Path = DEFAULT_SOURCE_OF_TRUTH_OUT,
    subset_manifest_out: Path = DEFAULT_SUBSET_MANIFEST_OUT,
    pose_validity_packet_out: Path = DEFAULT_POSE_VALIDITY_PACKET_OUT,
    rmsd_scorecard_out: Path = DEFAULT_RMSD_SCORECARD_OUT,
    pose_success_harness_out: Path = DEFAULT_POSE_SUCCESS_HARNESS_OUT,
    enrichment_scorecard_out: Path = DEFAULT_ENRICHMENT_SCORECARD_OUT,
    vina_gnina_comparison_adapter_out: Path = DEFAULT_VINA_GNINA_ADAPTER_OUT,
    external_receipts_validation_out: Path = DEFAULT_EXTERNAL_RECEIPTS_VALIDATION_OUT,
    operator_intake_packet_out: Path = DEFAULT_OPERATOR_INTAKE_PACKET_OUT,
    operator_intake_packet_md_out: Path = DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT,
    operator_template_dir: Path = DEFAULT_OPERATOR_TEMPLATE_DIR,
) -> dict[str, dict[str, Any]]:
    artifacts = build_public_benchmark_artifacts(
        repo_root=repo_root,
        operator_template_dir=operator_template_dir,
    )
    outputs = {
        "source_of_truth": source_of_truth_out,
        "subset_manifest": subset_manifest_out,
        "pose_validity_packet": pose_validity_packet_out,
        "rmsd_scorecard": rmsd_scorecard_out,
        "pose_success_harness": pose_success_harness_out,
        "enrichment_scorecard": enrichment_scorecard_out,
        "vina_gnina_comparison_adapter": vina_gnina_comparison_adapter_out,
        "external_receipts_validation": external_receipts_validation_out,
        "operator_intake_packet": operator_intake_packet_out,
    }
    for key, out_path in outputs.items():
        resolved = out_path if out_path.is_absolute() else repo_root / out_path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    resolved_md = (
        operator_intake_packet_md_out
        if operator_intake_packet_md_out.is_absolute()
        else repo_root / operator_intake_packet_md_out
    )
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Public Benchmark Operator Intake Packet",
        "",
        f"- `contract_pass`: `{artifacts['operator_intake_packet']['contract_pass']}`",
        f"- `status`: `{artifacts['operator_intake_packet']['status']}`",
        f"- `public_benchmark_ready`: `{artifacts['operator_intake_packet']['public_benchmark_ready']}`",
        f"- `claim_boundary`: {artifacts['operator_intake_packet']['claim_boundary']}",
        "",
        "| Slot | Status | Intake Artifact |",
        "|---|---|---|",
    ]
    for slot in artifacts["operator_intake_packet"]["input_slots"]:
        lines.append(
            f"| `{slot['slot_id']}` | `{slot['status']}` | `{slot['intake_artifact']}` |"
        )
    lines.append("")
    resolved_md.write_text("\n".join(lines), encoding="utf-8")
    write_public_benchmark_operator_template_payloads(
        packet=artifacts["operator_intake_packet"],
        repo_root=repo_root,
    )
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-of-truth-out", type=Path, default=DEFAULT_SOURCE_OF_TRUTH_OUT
    )
    parser.add_argument(
        "--subset-manifest-out", type=Path, default=DEFAULT_SUBSET_MANIFEST_OUT
    )
    parser.add_argument(
        "--pose-validity-packet-out",
        type=Path,
        default=DEFAULT_POSE_VALIDITY_PACKET_OUT,
    )
    parser.add_argument(
        "--rmsd-scorecard-out", type=Path, default=DEFAULT_RMSD_SCORECARD_OUT
    )
    parser.add_argument(
        "--pose-success-harness-out",
        type=Path,
        default=DEFAULT_POSE_SUCCESS_HARNESS_OUT,
    )
    parser.add_argument(
        "--enrichment-scorecard-out",
        type=Path,
        default=DEFAULT_ENRICHMENT_SCORECARD_OUT,
    )
    parser.add_argument(
        "--vina-gnina-comparison-adapter-out",
        type=Path,
        default=DEFAULT_VINA_GNINA_ADAPTER_OUT,
    )
    parser.add_argument(
        "--external-receipts-validation-out",
        type=Path,
        default=DEFAULT_EXTERNAL_RECEIPTS_VALIDATION_OUT,
    )
    parser.add_argument(
        "--operator-intake-packet-out",
        type=Path,
        default=DEFAULT_OPERATOR_INTAKE_PACKET_OUT,
    )
    parser.add_argument(
        "--operator-intake-packet-md-out",
        type=Path,
        default=DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT,
    )
    parser.add_argument(
        "--operator-template-dir", type=Path, default=DEFAULT_OPERATOR_TEMPLATE_DIR
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    artifacts = write_public_benchmark_artifacts(
        source_of_truth_out=args.source_of_truth_out,
        subset_manifest_out=args.subset_manifest_out,
        pose_validity_packet_out=args.pose_validity_packet_out,
        rmsd_scorecard_out=args.rmsd_scorecard_out,
        pose_success_harness_out=args.pose_success_harness_out,
        enrichment_scorecard_out=args.enrichment_scorecard_out,
        vina_gnina_comparison_adapter_out=args.vina_gnina_comparison_adapter_out,
        external_receipts_validation_out=args.external_receipts_validation_out,
        operator_intake_packet_out=args.operator_intake_packet_out,
        operator_intake_packet_md_out=args.operator_intake_packet_md_out,
        operator_template_dir=args.operator_template_dir,
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
