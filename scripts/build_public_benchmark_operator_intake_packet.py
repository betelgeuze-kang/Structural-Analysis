#!/usr/bin/env python3
"""Build the operator intake packet for the public benchmark harness."""

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
from validate_public_benchmark_subset_manifest import REQUIRED_CASE_FIELDS  # noqa: E402
from validate_public_benchmark_pose_validity import REQUIRED_POSE_FIELDS  # noqa: E402
from materialize_public_benchmark_subset_manifest import (  # noqa: E402
    LOCAL_SOURCE_FILE_FIELDS,
    SCHEMA_VERSION as SUBSET_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_pose_validity_input import (  # noqa: E402
    SCHEMA_VERSION as POSE_INPUT_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_posebusters_validity_packet import (  # noqa: E402
    SCHEMA_VERSION as POSEBUSTERS_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_rmsd_scorecard import (  # noqa: E402
    SCHEMA_VERSION as RMSD_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_enrichment_scorecard import (  # noqa: E402
    REQUIRED_MOLECULE_FIELDS,
    REQUIRED_TARGET_FIELDS,
    SCHEMA_VERSION as ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
    SUPPORTED_FAMILIES,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    DEFAULT_ADAPTER_OUT as DEFAULT_VINA_GNINA_COMPARISON_ADAPTER,
    REQUIRED_CASE_FIELDS as VINA_GNINA_REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS as VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS,
    SCHEMA_VERSION as VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
    SUPPORTED_ENGINES as VINA_GNINA_SUPPORTED_ENGINES,
)
from validate_public_benchmark_external_receipts import (  # noqa: E402
    SCHEMA_VERSION as EXTERNAL_RECEIPT_VALIDATION_SCHEMA_VERSION,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_OF_TRUTH = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_SUBSET_MANIFEST = PRODUCTIZATION / "public_benchmark_subset_manifest.json"
DEFAULT_POSE_VALIDITY_INPUT = (
    PRODUCTIZATION / "public_benchmark_pose_validity_input.json"
)
DEFAULT_POSE_VALIDITY_PACKET = (
    PRODUCTIZATION / "public_benchmark_pose_validity_packet.json"
)
DEFAULT_RMSD_SCORECARD = (
    PRODUCTIZATION / "public_benchmark_symmetry_rmsd_scorecard.json"
)
DEFAULT_ENRICHMENT_SCORECARD = (
    PRODUCTIZATION / "public_benchmark_enrichment_scorecard.json"
)
DEFAULT_EXTERNAL_RECEIPTS_VALIDATION = (
    PRODUCTIZATION / "public_benchmark_external_receipts_validation.json"
)
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_operator_intake_packet.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_OPERATOR_TEMPLATE_DIR = PRODUCTIZATION
DEFAULT_CASF_PDBBIND_OPERATOR_TEMPLATE = (
    DEFAULT_OPERATOR_TEMPLATE_DIR / "public_benchmark_casf_pdbbind_operator_template.json"
)
DEFAULT_POSE_COORDINATE_OPERATOR_TEMPLATE = (
    DEFAULT_OPERATOR_TEMPLATE_DIR / "public_benchmark_pose_coordinate_operator_template.json"
)
DEFAULT_ENRICHMENT_OPERATOR_TEMPLATE = (
    DEFAULT_OPERATOR_TEMPLATE_DIR / "public_benchmark_enrichment_operator_template.json"
)
DEFAULT_VINA_GNINA_OPERATOR_TEMPLATE = (
    DEFAULT_OPERATOR_TEMPLATE_DIR / "public_benchmark_vina_gnina_operator_template.json"
)

SCHEMA_VERSION = "public-benchmark-operator-intake-packet.v1"
OPERATOR_TEMPLATE_SCHEMA_VERSION = "public-benchmark-operator-template.v1"
PUBLIC_BENCHMARK_ROUTE = "/product/public-benchmark"
PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE = "/product/public-benchmark/operator-intake"
TIER_BETA_MINIMUM_SUBSET_CASE_COUNT = 12


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _input_paths(source_of_truth_path: Path) -> list[Path]:
    return [
        Path("scripts/build_public_benchmark_operator_intake_packet.py"),
        Path("scripts/materialize_public_benchmark_subset_manifest.py"),
        Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
        Path("scripts/materialize_public_benchmark_posebusters_validity_packet.py"),
        Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
        Path("scripts/materialize_public_benchmark_enrichment_scorecard.py"),
        Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
        Path("scripts/validate_public_benchmark_external_receipts.py"),
        Path("scripts/validate_public_benchmark_subset_manifest.py"),
        Path("scripts/validate_public_benchmark_pose_validity.py"),
        source_of_truth_path,
    ]


def _default_operator_template_paths(template_dir: Path) -> dict[str, Path]:
    return {
        "casf_pdbbind_subset_intake": template_dir
        / "public_benchmark_casf_pdbbind_operator_template.json",
        "pose_coordinate_intake": template_dir
        / "public_benchmark_pose_coordinate_operator_template.json",
        "dud_e_lit_pcba_enrichment_intake": template_dir
        / "public_benchmark_enrichment_operator_template.json",
        "vina_gnina_comparison_intake": template_dir
        / "public_benchmark_vina_gnina_operator_template.json",
    }


def _subset_case_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "source_family": "CASF/PDBBind",
        "complex_id": "SOURCE_COMPLEX_ID",
        "protein_structure_path": "operator_attached/casf_pdbbind/SOURCE_COMPLEX_ID/protein.pdb",
        "reference_ligand_path": "operator_attached/casf_pdbbind/SOURCE_COMPLEX_ID/reference_ligand.sdf",
        "predicted_ligand_path_or_docking_run_id": (
            "operator_attached/casf_pdbbind/SOURCE_COMPLEX_ID/predicted_pose.sdf"
        ),
        "ligand_atom_order_contract": {
            "atom_count": 0,
            "atom_ids": [],
            "atom_id_basis": "reference_ligand_atom_order",
        },
        "symmetry_permutation_contract": {
            "permutations": [],
            "permutation_basis": "zero_based_indices_into_ligand_atom_order_contract.atom_ids",
        },
        "source_license_or_accession": "operator_supplied_accession_or_license_ref",
        "source_checksum": "sha256:operator_supplied_source_bundle_checksum",
        "provenance_ref": "operator_supplied_subset_preparation_receipt",
        "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
        "rmsd_threshold_angstrom": 2.0,
    }


def _pose_case_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "reference_atoms": [
            {"element": "C", "x": 0.0, "y": 0.0, "z": 0.0},
            {"element": "O", "x": 1.2, "y": 0.0, "z": 0.0},
        ],
        "predicted_atoms": [
            {"element": "C", "x": 0.1, "y": 0.0, "z": 0.0},
            {"element": "O", "x": 1.3, "y": 0.0, "z": 0.0},
        ],
        "ligand_atom_order_contract": {
            "atom_count": 2,
            "atom_ids": ["C1", "O1"],
        },
        "symmetry_permutation_contract": {
            "permutations": [[0, 1]],
        },
        "protein_structure_path": "operator_attached/casf_pdbbind/SOURCE_COMPLEX_ID/protein.pdb",
        "receptor_context": {
            "binding_site_frame": "operator_supplied_receptor_frame",
            "provenance_ref": "operator_supplied_pose_preparation_receipt",
        },
    }


def _enrichment_target_template() -> dict[str, Any]:
    return {
        "benchmark_family": "DUD-E",
        "target_id": "SOURCE_TARGET_ID",
        "score_direction": "higher_is_better",
        "scored_molecules": [
            {"molecule_id": "active_001", "is_active": True, "score": 0.0},
            {"molecule_id": "decoy_001", "is_active": False, "score": 0.0},
        ],
        "source_license_or_accession": "operator_supplied_dud_e_or_lit_pcba_accession",
        "source_checksum": "sha256:operator_supplied_scored_rows_checksum",
        "provenance_ref": "operator_supplied_scoring_receipt",
    }


def _vina_gnina_case_template() -> dict[str, Any]:
    return {
        "case_id": "casf_pdbbind_subset_001",
        "source_family": "CASF/PDBBind",
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


def _casf_pdbbind_subset_manifest_contract(
    *,
    materialization_command: str,
    validation_command: str,
) -> dict[str, Any]:
    return {
        "contract_id": "casf_pdbbind_subset_manifest_contract",
        "status": "operator_input_required",
        "source_family": "CASF/PDBBind",
        "intake_artifact": "<operator-casf-pdbbind-intake.json>",
        "intake_case_key": "cases",
        "produces": str(DEFAULT_SUBSET_MANIFEST),
        "target_subset_case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "required_local_source_file_fields": [
            str(row) for row in LOCAL_SOURCE_FILE_FIELDS
        ],
        "nested_contracts": [
            {
                "field": "ligand_atom_order_contract",
                "required_fields": ["atom_count", "atom_ids"],
                "validation_rules": [
                    "atom_count > 0",
                    "len(atom_ids) == atom_count",
                    "atom_ids are unique within each case",
                ],
            },
            {
                "field": "symmetry_permutation_contract",
                "required_fields": ["permutations"],
                "validation_rules": [
                    "permutations is non-empty",
                    "each permutation is zero-based over ligand_atom_order_contract.atom_ids",
                    "sorted(permutation) == list(range(atom_count))",
                ],
            },
        ],
        "receipt_fields": [
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
        ],
        "checksum_policy": {
            "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
            "source_checksum": (
                "Operator may provide a source bundle checksum; otherwise the materializer "
                "derives a stable checksum from computed local source-file checksums."
            ),
            "source_file_checksums": (
                "Materializer computes one checksum per local protein/reference-ligand/"
                "predicted-pose file and writes them to each manifest case row."
            ),
            "required_manifest_field": "source_file_checksums",
        },
        "unblocks_tier_beta_criteria": [
            "casf_pdbbind_subset_materialized",
            "external_receipts_attached",
        ],
        "materialization_command": materialization_command,
        "validation_command": validation_command,
        "claim_boundary": (
            "This contract describes the local operator intake needed to materialize the "
            "CASF/PDBBind subset manifest. It does not fetch, redistribute, or license "
            "public benchmark data."
        ),
    }


def _slot(
    *,
    slot_id: str,
    title: str,
    status: str,
    required: bool,
    intake_artifact: str,
    template_artifact: str,
    required_fields: list[str],
    template: dict[str, Any],
    materialization_command: str,
    validation_command: str = "",
    depends_on: list[str] | None = None,
    local_source_file_fields: list[str] | None = None,
    owner_actions: list[str] | None = None,
    unblocks_tier_beta_criteria: list[str] | None = None,
    minimum_evidence: dict[str, Any] | None = None,
    materialization_steps: list[str] | None = None,
    manifest_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "title": title,
        "status": status,
        "required": required,
        "intake_artifact": intake_artifact,
        "template_artifact": template_artifact,
        "depends_on": depends_on or [],
        "required_fields": required_fields,
        "local_source_file_fields": local_source_file_fields or [],
        "template": template,
        "owner_actions": owner_actions or [],
        "unblocks_tier_beta_criteria": unblocks_tier_beta_criteria or [],
        "minimum_evidence": minimum_evidence or {},
        "materialization_steps": materialization_steps or [],
        "manifest_contract": manifest_contract or {},
        "validation_command": validation_command,
        "materialization_command": materialization_command,
    }


def _gate_unblock_plan(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in slots:
        manifest_contract = _as_dict(slot.get("manifest_contract"))
        rows.append(
            {
                "slot_id": str(slot["slot_id"]),
                "title": str(slot["title"]),
                "status": str(slot["status"]),
                "unblocks_tier_beta_criteria": list(
                    slot["unblocks_tier_beta_criteria"]
                ),
                "minimum_evidence": dict(slot["minimum_evidence"]),
                "template_artifact": str(slot.get("template_artifact") or ""),
                "materialization_steps": list(slot["materialization_steps"]),
                "manifest_contract_id": str(manifest_contract.get("contract_id") or ""),
            }
        )
    return rows


def _operator_evidence_gap_register(
    slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, slot in enumerate(slots, start=1):
        owner_actions = [str(action) for action in _as_list(slot.get("owner_actions"))]
        manifest_contract = _as_dict(slot.get("manifest_contract"))
        rows.append(
            {
                "slot_priority": index,
                "slot_id": str(slot.get("slot_id") or ""),
                "status": str(slot.get("status") or ""),
                "manifest_contract_id": str(manifest_contract.get("contract_id") or ""),
                "tier_beta_blocked": True,
                "blocked_tier_beta_criteria": [
                    str(row)
                    for row in _as_list(slot.get("unblocks_tier_beta_criteria"))
                ],
                "first_next_action": owner_actions[0] if owner_actions else "",
                "template_artifact": str(slot.get("template_artifact") or ""),
                "minimum_evidence": _as_dict(slot.get("minimum_evidence")),
                "materialization_steps": [
                    str(row) for row in _as_list(slot.get("materialization_steps"))
                ],
                "depends_on": [
                    str(path) for path in _as_list(slot.get("depends_on")) if str(path)
                ],
                "materialization_command": str(
                    slot.get("materialization_command") or ""
                ),
                "validation_command": str(slot.get("validation_command") or ""),
            }
        )
    return rows


def build_public_benchmark_operator_intake_packet(
    *,
    repo_root: Path = ROOT,
    source_of_truth_path: Path = DEFAULT_SOURCE_OF_TRUTH,
    operator_template_dir: Path = DEFAULT_OPERATOR_TEMPLATE_DIR,
) -> dict[str, Any]:
    source_of_truth = _load_json(repo_root, source_of_truth_path)
    source_blockers = [str(row) for row in _as_list(source_of_truth.get("blockers"))]
    source_next_actions = [
        str(row) for row in _as_list(source_of_truth.get("next_actions"))
    ]

    subset_materialization = (
        "python3 scripts/materialize_public_benchmark_subset_manifest.py "
        "--intake <operator-casf-pdbbind-intake.json> "
        f"--out-manifest {DEFAULT_SUBSET_MANIFEST} "
        f"--out-report {PRODUCTIZATION / 'public_benchmark_subset_materialization_report.json'} "
        "--fail-blocked"
    )
    subset_validation = (
        "python3 scripts/validate_public_benchmark_subset_manifest.py "
        f"--manifest {DEFAULT_SUBSET_MANIFEST} --fail-blocked"
    )
    pose_input_materialization = (
        "python3 scripts/materialize_public_benchmark_pose_validity_input.py "
        f"--subset-manifest {DEFAULT_SUBSET_MANIFEST} "
        "--pose-intake <operator-pose-coordinate-intake.json> "
        f"--out-input {DEFAULT_POSE_VALIDITY_INPUT} "
        f"--out-report {PRODUCTIZATION / 'public_benchmark_pose_validity_materialization_report.json'} "
        "--fail-blocked"
    )
    posebusters_materialization = (
        "python3 scripts/materialize_public_benchmark_posebusters_validity_packet.py "
        f"--pose-validity-input {DEFAULT_POSE_VALIDITY_INPUT} "
        f"--out-packet {DEFAULT_POSE_VALIDITY_PACKET} "
        f"--out-report {PRODUCTIZATION / 'public_benchmark_posebusters_validity_materialization_report.json'} "
        "--fail-blocked"
    )
    rmsd_materialization = (
        "python3 scripts/materialize_public_benchmark_rmsd_scorecard.py "
        f"--pose-validity-input {DEFAULT_POSE_VALIDITY_INPUT} "
        f"--out-scorecard {DEFAULT_RMSD_SCORECARD} "
        f"--out-report {PRODUCTIZATION / 'public_benchmark_symmetry_rmsd_materialization_report.json'} "
        "--fail-blocked"
    )
    enrichment_materialization = (
        "python3 scripts/materialize_public_benchmark_enrichment_scorecard.py "
        "--intake <operator-dud-e-lit-pcba-enrichment-intake.json> "
        f"--out-scorecard {DEFAULT_ENRICHMENT_SCORECARD} "
        f"--out-report {PRODUCTIZATION / 'public_benchmark_enrichment_materialization_report.json'} "
        "--fail-blocked"
    )
    vina_gnina_materialization = (
        "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
        "--intake <operator-vina-gnina-comparison-intake.json> "
        f"--out-adapter {DEFAULT_VINA_GNINA_COMPARISON_ADAPTER} "
        f"--out-report {PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
        "--fail-blocked"
    )
    external_receipt_validation = (
        "python3 scripts/validate_public_benchmark_external_receipts.py "
        f"--subset-manifest {DEFAULT_SUBSET_MANIFEST} "
        f"--enrichment-scorecard {DEFAULT_ENRICHMENT_SCORECARD} "
        f"--vina-gnina-comparison-adapter {DEFAULT_VINA_GNINA_COMPARISON_ADAPTER} "
        f"--out {DEFAULT_EXTERNAL_RECEIPTS_VALIDATION} --fail-blocked"
    )
    refresh_source = (
        "python3 scripts/build_public_benchmark_source_of_truth.py "
        f"--source-of-truth-out {DEFAULT_SOURCE_OF_TRUTH} "
        f"--subset-manifest-out {DEFAULT_SUBSET_MANIFEST} "
        f"--pose-validity-packet-out {DEFAULT_POSE_VALIDITY_PACKET} "
        f"--rmsd-scorecard-out {DEFAULT_RMSD_SCORECARD} "
        f"--enrichment-scorecard-out {DEFAULT_ENRICHMENT_SCORECARD} "
        f"--vina-gnina-comparison-adapter-out {DEFAULT_VINA_GNINA_COMPARISON_ADAPTER} "
        f"--external-receipts-validation-out {DEFAULT_EXTERNAL_RECEIPTS_VALIDATION}"
    )
    casf_pdbbind_manifest_contract = _casf_pdbbind_subset_manifest_contract(
        materialization_command=subset_materialization,
        validation_command=subset_validation,
    )
    template_paths = _default_operator_template_paths(operator_template_dir)

    slots = [
        _slot(
            slot_id="casf_pdbbind_subset_intake",
            title="CASF/PDBBind subset source files and case descriptors",
            status="operator_input_required",
            required=True,
            intake_artifact="<operator-casf-pdbbind-intake.json>",
            template_artifact=str(template_paths["casf_pdbbind_subset_intake"]),
            required_fields=[
                *list(REQUIRED_CASE_FIELDS),
                "ligand_atom_order_contract.atom_count",
                "ligand_atom_order_contract.atom_ids",
                "symmetry_permutation_contract.permutations",
            ],
            local_source_file_fields=[str(row) for row in LOCAL_SOURCE_FILE_FIELDS],
            template={
                "target_subset_case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
                "cases": [_subset_case_template()],
            },
            owner_actions=[
                "attach at least 12 local CASF/PDBBind case descriptors",
                "attach protein, reference ligand, and predicted pose or docking-run files",
                "declare license or accession references without redistributing restricted source data",
                "declare ligand atom order and symmetry permutations for every case",
                "declare pose_success_metric=symmetry_aware_ligand_rmsd_angstrom and a positive RMSD threshold",
                "run the subset materializer with --fail-blocked",
            ],
            validation_command=subset_validation,
            materialization_command=subset_materialization,
            unblocks_tier_beta_criteria=[
                "casf_pdbbind_subset_materialized",
                "external_receipts_attached",
            ],
            minimum_evidence={
                "case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
                "source_family": "CASF/PDBBind",
                "local_source_file_fields": [
                    str(row) for row in LOCAL_SOURCE_FILE_FIELDS
                ],
                "ligand_atom_order_contract_fields": ["atom_count", "atom_ids"],
                "symmetry_permutation_contract_fields": ["permutations"],
                "materialized_manifest_fields": ["source_file_checksums"],
                "receipt_fields": [
                    "source_license_or_accession",
                    "source_checksum",
                    "provenance_ref",
                ],
            },
            materialization_steps=["materialize_subset_manifest"],
            manifest_contract=casf_pdbbind_manifest_contract,
        ),
        _slot(
            slot_id="pose_coordinate_intake",
            title="Pose coordinate intake for PoseBusters-style validity and RMSD",
            status="operator_input_required",
            required=True,
            intake_artifact="<operator-pose-coordinate-intake.json>",
            template_artifact=str(template_paths["pose_coordinate_intake"]),
            depends_on=[str(DEFAULT_SUBSET_MANIFEST)],
            required_fields=list(REQUIRED_POSE_FIELDS),
            template={"cases": [_pose_case_template()]},
            owner_actions=[
                "use case_id values from the materialized CASF/PDBBind subset manifest",
                "attach reference and predicted ligand atom coordinates in the declared atom order",
                "keep receptor context and symmetry permutation contracts explicit",
                "run pose-validity input materialization, PoseBusters-style packet, and RMSD scorecard",
            ],
            validation_command=(
                "python3 scripts/validate_public_benchmark_pose_validity.py "
                f"--input {DEFAULT_POSE_VALIDITY_INPUT} --fail-blocked"
            ),
            materialization_command=pose_input_materialization,
            unblocks_tier_beta_criteria=[
                "real_pose_validity_packet_materialized",
                "symmetry_rmsd_scorecard_real_cases",
                "posebusters_style_validity_real_ligands",
            ],
            minimum_evidence={
                "case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
                "case_id_source": str(DEFAULT_SUBSET_MANIFEST),
                "coordinate_contract": (
                    "reference_atoms and predicted_atoms in the declared ligand atom order"
                ),
            },
            materialization_steps=[
                "materialize_pose_validity_input",
                "materialize_posebusters_validity_packet",
                "materialize_symmetry_rmsd_scorecard",
            ],
        ),
        _slot(
            slot_id="dud_e_lit_pcba_enrichment_intake",
            title="DUD-E/LIT-PCBA scored molecule enrichment rows",
            status="operator_input_required",
            required=True,
            intake_artifact="<operator-dud-e-lit-pcba-enrichment-intake.json>",
            template_artifact=str(template_paths["dud_e_lit_pcba_enrichment_intake"]),
            required_fields=list(REQUIRED_TARGET_FIELDS),
            template={"targets": [_enrichment_target_template()]},
            owner_actions=[
                "attach at least one DUD-E or LIT-PCBA target with active and decoy labels",
                "preserve score direction and source accession or license references",
                "include scored_molecules rows with molecule_id, is_active, and score",
                "run the enrichment materializer with --fail-blocked",
            ],
            validation_command=enrichment_materialization,
            materialization_command=enrichment_materialization,
            unblocks_tier_beta_criteria=[
                "dud_e_lit_pcba_enrichment_ready",
                "external_receipts_attached",
            ],
            minimum_evidence={
                "ready_target_count": 1,
                "supported_families": list(SUPPORTED_FAMILIES),
                "required_molecule_fields": list(REQUIRED_MOLECULE_FIELDS),
                "receipt_fields": [
                    "source_license_or_accession",
                    "source_checksum",
                    "provenance_ref",
                ],
            },
            materialization_steps=["materialize_enrichment_scorecard"],
        ),
        _slot(
            slot_id="vina_gnina_comparison_intake",
            title="Vina/GNINA docking engine comparison rows",
            status="operator_input_required",
            required=True,
            intake_artifact="<operator-vina-gnina-comparison-intake.json>",
            template_artifact=str(template_paths["vina_gnina_comparison_intake"]),
            depends_on=[str(DEFAULT_SUBSET_MANIFEST), str(DEFAULT_RMSD_SCORECARD)],
            required_fields=list(VINA_GNINA_REQUIRED_CASE_FIELDS),
            template={"cases": [_vina_gnina_case_template()]},
            owner_actions=[
                "attach Vina and GNINA run rows for the same materialized benchmark cases",
                "include symmetry-aware RMSD and pose_success values for every engine run",
                "preserve docking run receipts, source accession or license references, and checksums",
                "run the Vina/GNINA comparison materializer with --fail-blocked",
            ],
            validation_command=vina_gnina_materialization,
            materialization_command=vina_gnina_materialization,
            unblocks_tier_beta_criteria=[
                "vina_gnina_comparison_ready",
                "external_receipts_attached",
            ],
            minimum_evidence={
                "comparison_case_count": 1,
                "required_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
                "required_engine_run_fields": list(
                    VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS
                ),
                "receipt_fields": [
                    "source_license_or_accession",
                    "source_checksum",
                    "provenance_ref",
                ],
            },
            materialization_steps=["materialize_vina_gnina_comparison_adapter"],
        ),
    ]
    gate_unblock_plan = _gate_unblock_plan(slots)
    operator_evidence_gap_register = _operator_evidence_gap_register(slots)
    first_operator_evidence_gap = operator_evidence_gap_register[0]
    manifest_contracts = [casf_pdbbind_manifest_contract]
    operator_template_artifacts = {
        str(slot["slot_id"]): str(slot["template_artifact"]) for slot in slots
    }

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(source_of_truth_path),
            reused_evidence=True,
            reuse_policy="public_benchmark_operator_intake_packet_from_materializer_contracts",
            repo_root=repo_root,
        ),
        "packet_id": "public_benchmark_operator_intake_packet",
        "status": "ready_for_operator_input",
        "reason_code": "PASS_INTAKE_PACKET",
        "contract_pass": True,
        "read_model_ready": True,
        "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
        "read_model": {
            "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
            "alternate_routes": [PUBLIC_BENCHMARK_ROUTE, "/product/capabilities"],
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "public_benchmark_ready": False,
        "tier_beta_ready": False,
        "owner_input_required": True,
        "source_of_truth_status": str(source_of_truth.get("status") or ""),
        "source_of_truth_blockers": source_blockers,
        "source_of_truth_next_actions": source_next_actions,
        "input_slots": slots,
        "required_slot_count": len([slot for slot in slots if slot["required"]]),
        "manifest_contracts": manifest_contracts,
        "manifest_contract_count": len(manifest_contracts),
        "first_manifest_contract_id": casf_pdbbind_manifest_contract["contract_id"],
        "first_manifest_contract": casf_pdbbind_manifest_contract,
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "first_blocked_target": first_operator_evidence_gap["slot_id"],
        "root_cause_tags": [
            "operator_source_material_required",
            "operator_receipts_required",
        ],
        "operator_evidence_gap_count": len(operator_evidence_gap_register),
        "first_operator_evidence_gap": first_operator_evidence_gap,
        "operator_evidence_gap_register": operator_evidence_gap_register,
        "operator_template_schema_version": OPERATOR_TEMPLATE_SCHEMA_VERSION,
        "operator_template_artifact_count": len(operator_template_artifacts),
        "operator_template_artifacts": operator_template_artifacts,
        "minimum_subset_case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
        "materialization_sequence": [
            {
                "step_id": "materialize_subset_manifest",
                "schema_version": SUBSET_MATERIALIZER_SCHEMA_VERSION,
                "command": subset_materialization,
                "produces": str(DEFAULT_SUBSET_MANIFEST),
            },
            {
                "step_id": "materialize_pose_validity_input",
                "schema_version": POSE_INPUT_MATERIALIZER_SCHEMA_VERSION,
                "command": pose_input_materialization,
                "produces": str(DEFAULT_POSE_VALIDITY_INPUT),
            },
            {
                "step_id": "materialize_posebusters_validity_packet",
                "schema_version": POSEBUSTERS_MATERIALIZER_SCHEMA_VERSION,
                "command": posebusters_materialization,
                "produces": str(DEFAULT_POSE_VALIDITY_PACKET),
            },
            {
                "step_id": "materialize_symmetry_rmsd_scorecard",
                "schema_version": RMSD_MATERIALIZER_SCHEMA_VERSION,
                "command": rmsd_materialization,
                "produces": str(DEFAULT_RMSD_SCORECARD),
            },
            {
                "step_id": "materialize_enrichment_scorecard",
                "schema_version": ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
                "command": enrichment_materialization,
                "produces": str(DEFAULT_ENRICHMENT_SCORECARD),
            },
            {
                "step_id": "materialize_vina_gnina_comparison_adapter",
                "schema_version": VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
                "command": vina_gnina_materialization,
                "produces": str(DEFAULT_VINA_GNINA_COMPARISON_ADAPTER),
            },
            {
                "step_id": "validate_external_receipts",
                "schema_version": EXTERNAL_RECEIPT_VALIDATION_SCHEMA_VERSION,
                "command": external_receipt_validation,
                "produces": str(DEFAULT_EXTERNAL_RECEIPTS_VALIDATION),
            },
            {
                "step_id": "refresh_public_benchmark_source_of_truth",
                "schema_version": "public-benchmark-source-of-truth.v1",
                "command": refresh_source,
                "produces": str(DEFAULT_SOURCE_OF_TRUTH),
            },
        ],
        "acceptance_criteria": [
            "public_benchmark_subset_manifest.materialized_case_count >= 12",
            "public_benchmark_subset_manifest.public_benchmark_ready == true",
            "public_benchmark_pose_validity_input.pose_validity_ready == true",
            "public_benchmark_pose_validity_packet.real_benchmark_case_count >= 12",
            "public_benchmark_symmetry_rmsd_scorecard.real_benchmark_case_count >= 12",
            "public_benchmark_enrichment_scorecard.public_benchmark_enrichment_ready == true",
            "public_benchmark_vina_gnina_comparison_adapter.public_benchmark_engine_comparison_ready == true",
            "public_benchmark_external_receipts_validation.public_benchmark_external_receipts_ready == true",
            "public_benchmark_source_of_truth.public_benchmark_ready == true",
        ],
        "supported_enrichment_families": list(SUPPORTED_FAMILIES),
        "required_molecule_fields": list(REQUIRED_MOLECULE_FIELDS),
        "supported_comparison_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
        "required_engine_run_fields": list(VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS),
        "linked_artifacts": {
            "source_of_truth": str(DEFAULT_SOURCE_OF_TRUTH),
            "subset_manifest": str(DEFAULT_SUBSET_MANIFEST),
            "pose_validity_input": str(DEFAULT_POSE_VALIDITY_INPUT),
            "pose_validity_packet": str(DEFAULT_POSE_VALIDITY_PACKET),
            "rmsd_scorecard": str(DEFAULT_RMSD_SCORECARD),
            "enrichment_scorecard": str(DEFAULT_ENRICHMENT_SCORECARD),
            "vina_gnina_comparison_adapter": str(DEFAULT_VINA_GNINA_COMPARISON_ADAPTER),
            "external_receipts_validation": str(DEFAULT_EXTERNAL_RECEIPTS_VALIDATION),
            "operator_templates": operator_template_artifacts,
        },
        "next_actions": [
            "fill_public_benchmark_operator_intake_packet",
            "run_public_benchmark_subset_materializer",
            "run_public_benchmark_pose_validity_materializer",
            "run_public_benchmark_rmsd_scorecard_materializer",
            "run_public_benchmark_enrichment_materializer",
            "run_public_benchmark_vina_gnina_comparison_materializer",
            "validate_public_benchmark_external_receipts",
            "refresh_public_benchmark_source_of_truth",
            "regenerate_goal_bottleneck_roadmap_surface",
        ],
        "summary": {
            "required_slot_count": len([slot for slot in slots if slot["required"]]),
            "gate_unblock_plan_count": len(gate_unblock_plan),
            "first_blocked_target": first_operator_evidence_gap["slot_id"],
            "root_cause_tags": [
                "operator_source_material_required",
                "operator_receipts_required",
            ],
            "operator_evidence_gap_count": len(operator_evidence_gap_register),
            "first_operator_evidence_gap": first_operator_evidence_gap,
            "operator_template_artifact_count": len(operator_template_artifacts),
            "operator_template_artifacts": operator_template_artifacts,
            "first_manifest_contract_id": casf_pdbbind_manifest_contract["contract_id"],
            "minimum_subset_case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
            "source_of_truth_blocker_count": len(source_blockers),
            "source_of_truth_status": str(source_of_truth.get("status") or ""),
            "public_benchmark_ready": False,
        },
        "summary_line": (
            "Public benchmark operator intake packet: READY | "
            f"slots={len(slots)} | source_blockers={len(source_blockers)}"
        ),
        "claim_boundary": (
            "This packet is an owner-facing intake contract for public benchmark evidence. "
            "It does not attach CASF/PDBBind, DUD-E, or LIT-PCBA source files, does not "
            "redistribute benchmark data, does not infer ligand chemistry, and does not "
            "close Tier beta without materialized real benchmark rows."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Benchmark Operator Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `status`: `{payload['status']}`",
        f"- `public_benchmark_ready`: `{payload['public_benchmark_ready']}`",
        f"- `source_of_truth_status`: `{payload['source_of_truth_status']}`",
        f"- `source_of_truth_blocker_count`: `{len(payload['source_of_truth_blockers'])}`",
        f"- `claim_boundary`: {payload['claim_boundary']}",
        "",
        "| Slot | Status | Intake Artifact | Validation Command |",
        "|---|---|---|---|",
    ]
    for slot in payload["input_slots"]:
        lines.append(
            f"| `{slot['slot_id']}` | `{slot['status']}` | "
            f"`{slot['intake_artifact']}` | `{slot['validation_command']}` |"
        )
    lines.extend(
        ["", "## Gate Unblock Plan", "", "| Slot | Criteria | Minimum Evidence |"]
    )
    lines.append("|---|---|---|")
    for row in payload["gate_unblock_plan"]:
        criteria = ", ".join(
            f"`{criterion}`" for criterion in row["unblocks_tier_beta_criteria"]
        )
        minimum = json.dumps(
            row["minimum_evidence"], ensure_ascii=False, sort_keys=True
        )
        lines.append(f"| `{row['slot_id']}` | {criteria} | `{minimum}` |")
    lines.extend(["", "## Materialization Sequence", ""])
    for step in payload["materialization_sequence"]:
        lines.append(f"- `{step['step_id']}`: `{step['command']}`")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in payload["acceptance_criteria"]:
        lines.append(f"- `{criterion}`")
    lines.append("")
    return "\n".join(lines)


def _operator_template_payload(
    *,
    slot: dict[str, Any],
    repo_root: Path,
    source_of_truth_path: Path,
) -> dict[str, Any]:
    slot_id = str(slot.get("slot_id") or "")
    template = _as_dict(slot.get("template"))
    case_key = next((key for key in ("cases", "targets") if key in template), "")
    return {
        "schema_version": OPERATOR_TEMPLATE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(source_of_truth_path),
            reused_evidence=True,
            reuse_policy="public_benchmark_operator_template_seed_from_intake_packet",
            repo_root=repo_root,
        ),
        "template_id": f"{slot_id}_operator_template",
        "status": "operator_template_seed",
        "contract_pass": True,
        "owner_input_required": True,
        "operator_values_filled": False,
        "materialization_ready": False,
        "slot_id": slot_id,
        "title": str(slot.get("title") or ""),
        "template_artifact": str(slot.get("template_artifact") or ""),
        "intake_artifact": str(slot.get("intake_artifact") or ""),
        "case_key": case_key,
        "required_fields": [str(row) for row in _as_list(slot.get("required_fields"))],
        "local_source_file_fields": [
            str(row) for row in _as_list(slot.get("local_source_file_fields"))
        ],
        "depends_on": [str(row) for row in _as_list(slot.get("depends_on"))],
        "minimum_evidence": _as_dict(slot.get("minimum_evidence")),
        "template": template,
        "materialization_command": str(slot.get("materialization_command") or ""),
        "validation_command": str(slot.get("validation_command") or ""),
        "claim_boundary": (
            "This is a fillable operator template seed. It is not benchmark evidence, "
            "does not attach restricted public benchmark source data, and does not "
            "close Tier beta until an operator supplies real rows and receipts."
        ),
    }


def public_benchmark_operator_template_payloads(
    *,
    packet: dict[str, Any],
    repo_root: Path = ROOT,
    source_of_truth_path: Path = DEFAULT_SOURCE_OF_TRUTH,
) -> dict[str, dict[str, Any]]:
    return {
        str(slot.get("slot_id") or ""): _operator_template_payload(
            slot=slot,
            repo_root=repo_root,
            source_of_truth_path=source_of_truth_path,
        )
        for slot in _as_list(packet.get("input_slots"))
        if isinstance(slot, dict)
    }


def write_public_benchmark_operator_template_payloads(
    *,
    packet: dict[str, Any],
    repo_root: Path = ROOT,
    source_of_truth_path: Path = DEFAULT_SOURCE_OF_TRUTH,
) -> dict[str, Path]:
    payloads = public_benchmark_operator_template_payloads(
        packet=packet,
        repo_root=repo_root,
        source_of_truth_path=source_of_truth_path,
    )
    written: dict[str, Path] = {}
    for slot_id, payload in payloads.items():
        raw_path = Path(str(payload.get("template_artifact") or ""))
        if not raw_path:
            continue
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(payload), encoding="utf-8")
        written[slot_id] = path
    return written


def write_public_benchmark_operator_intake_packet(
    *,
    repo_root: Path = ROOT,
    source_of_truth_path: Path = DEFAULT_SOURCE_OF_TRUTH,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    operator_template_dir: Path = DEFAULT_OPERATOR_TEMPLATE_DIR,
) -> dict[str, Any]:
    payload = build_public_benchmark_operator_intake_packet(
        repo_root=repo_root,
        source_of_truth_path=source_of_truth_path,
        operator_template_dir=operator_template_dir,
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(_markdown(payload), encoding="utf-8")
    write_public_benchmark_operator_template_payloads(
        packet=payload,
        repo_root=repo_root,
        source_of_truth_path=source_of_truth_path,
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-of-truth", type=Path, default=DEFAULT_SOURCE_OF_TRUTH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument(
        "--operator-template-dir", type=Path, default=DEFAULT_OPERATOR_TEMPLATE_DIR
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_public_benchmark_operator_intake_packet(
        repo_root=args.repo_root,
        source_of_truth_path=args.source_of_truth,
        out=args.out,
        out_md=args.out_md,
        operator_template_dir=args.operator_template_dir,
    )
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
