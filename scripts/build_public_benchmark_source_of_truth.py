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
from materialize_public_benchmark_posebusters_validity_packet import (  # noqa: E402
    SCHEMA_VERSION as POSEBUSTERS_PACKET_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_rmsd_scorecard import (  # noqa: E402
    SCHEMA_VERSION as RMSD_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_enrichment_scorecard import (  # noqa: E402
    SCHEMA_VERSION as ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    ADAPTER_SCHEMA_VERSION as VINA_GNINA_ADAPTER_SCHEMA_VERSION,
    REQUIRED_CASE_FIELDS as VINA_GNINA_REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS as VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS,
    SCHEMA_VERSION as VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
    SUPPORTED_ENGINES as VINA_GNINA_SUPPORTED_ENGINES,
)
from build_public_benchmark_operator_intake_packet import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_OPERATOR_INTAKE_PACKET_OUT,
    SCHEMA_VERSION as OPERATOR_INTAKE_PACKET_SCHEMA_VERSION,
    build_public_benchmark_operator_intake_packet,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_OF_TRUTH_OUT = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_SUBSET_MANIFEST_OUT = PRODUCTIZATION / "public_benchmark_subset_manifest.json"
DEFAULT_POSE_VALIDITY_PACKET_OUT = PRODUCTIZATION / "public_benchmark_pose_validity_packet.json"
DEFAULT_RMSD_SCORECARD_OUT = PRODUCTIZATION / "public_benchmark_symmetry_rmsd_scorecard.json"
DEFAULT_ENRICHMENT_SCORECARD_OUT = PRODUCTIZATION / "public_benchmark_enrichment_scorecard.json"
DEFAULT_VINA_GNINA_ADAPTER_OUT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_comparison_adapter.json"
)
DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT = DEFAULT_OPERATOR_INTAKE_PACKET_OUT.with_suffix(".md")
SCHEMA_VERSION = "public-benchmark-source-of-truth.v1"
SUBSET_SCHEMA_VERSION = "public-benchmark-subset-manifest.v1"
POSE_PACKET_SCHEMA_VERSION = "public-benchmark-pose-validity-packet.v1"
RMSD_SCORECARD_SCHEMA_VERSION = "public-benchmark-symmetry-rmsd-scorecard.v1"
ENRICHMENT_SCORECARD_SCHEMA_VERSION = "public-benchmark-enrichment-scorecard.v1"

PUBLIC_BENCHMARK_ROUTE = "/product/public-benchmark"
PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE = "/product/public-benchmark/operator-intake"


def _source_input_paths() -> list[Path]:
    return [
        Path("scripts/build_public_benchmark_source_of_truth.py"),
        Path("scripts/materialize_public_benchmark_posebusters_validity_packet.py"),
        Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
        Path("scripts/materialize_public_benchmark_enrichment_scorecard.py"),
        Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
        Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
        Path("scripts/materialize_public_benchmark_subset_manifest.py"),
        Path("scripts/build_public_benchmark_operator_intake_packet.py"),
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
                "check_id": "symmetry_permutation_contract",
                "required": True,
                "description": "allowed symmetry permutations are explicit zero-based atom-index maps",
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
        "target_rows": [],
        "summary": {
            "benchmark_family_count": 0,
            "benchmark_families": [],
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
        "summary": {
            "case_count": 0,
            "ready_case_count": 0,
            "engine_count": len(VINA_GNINA_SUPPORTED_ENGINES),
            "supported_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
            "blocker_count": len(blockers),
        },
        "materializer": {
            "schema_version": VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "intake_case_key": "cases",
            "required_case_fields": list(VINA_GNINA_REQUIRED_CASE_FIELDS),
            "required_engine_run_fields": list(VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS),
            "supported_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
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
    for index, slot in enumerate(operator_intake_packet.get("input_slots", []), start=1):
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
        rows.append(
            {
                "slot_priority": index,
                "slot_id": slot_id,
                "status": str(slot.get("status") or ""),
                "tier_beta_blocked": bool(blocked_criteria),
                "blocked_tier_beta_criteria": blocked_criteria,
                "criterion_gates": criterion_gates,
                "first_next_action": owner_actions[0] if owner_actions else "",
                "owner_actions": owner_actions,
                "depends_on": [
                    str(path) for path in slot.get("depends_on", []) if str(path)
                ],
                "minimum_evidence": dict(plan.get("minimum_evidence") or {}),
                "materialization_steps": [
                    str(step)
                    for step in plan.get("materialization_steps", [])
                    if str(step)
                ],
                "materialization_command": str(slot.get("materialization_command") or ""),
                "validation_command": str(slot.get("validation_command") or ""),
            }
        )
    return rows


def build_source_of_truth(
    *,
    subset_manifest: dict[str, Any],
    pose_validity_packet: dict[str, Any],
    rmsd_scorecard: dict[str, Any],
    enrichment_scorecard: dict[str, Any],
    vina_gnina_comparison_adapter: dict[str, Any],
    operator_intake_packet: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    target_subset_case_count = int(subset_manifest["target_subset_case_count"])
    subset_materialized_count = int(subset_manifest["materialized_case_count"])
    pose_real_case_count = int(
        pose_validity_packet["dry_run_validation"]["real_benchmark_case_count"]
    )
    rmsd_real_case_count = int(rmsd_scorecard["real_benchmark_case_count"])
    enrichment_ready = bool(enrichment_scorecard["public_benchmark_enrichment_ready"])
    engine_comparison_ready = bool(
        vina_gnina_comparison_adapter["public_benchmark_engine_comparison_ready"]
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
                "pass": False,
                "current": 0,
                "required": "source_license_or_accession_and_provenance_receipts_for_all_materialized_rows",
                "blockers": ["public_benchmark_external_receipts_missing"],
            },
        ],
    }
    failed_gate_criteria = [
        row["criterion_id"] for row in tier_beta_gate["criteria"] if not row["pass"]
    ]
    tier_beta_gate["failed_criterion_count"] = len(failed_gate_criteria)
    tier_beta_gate["failed_criteria"] = failed_gate_criteria
    symmetry_rmsd_scorecard_summary = {
        "status": rmsd_scorecard["status"],
        "dry_run_case_count": rmsd_scorecard["dry_run_case_count"],
        "real_benchmark_case_count": rmsd_scorecard["real_benchmark_case_count"],
        "dry_run_pose_success": bool(rmsd_scorecard["rows"][0]["score"]["pose_success"]),
    }
    operator_evidence_gap_register = _operator_evidence_gap_register(
        tier_beta_gate=tier_beta_gate,
        operator_intake_packet=operator_intake_packet,
    )
    first_operator_evidence_gap = next(
        (
            row
            for row in operator_evidence_gap_register
            if row["tier_beta_blocked"]
        ),
        {},
    )
    first_blocked_target = str(first_operator_evidence_gap.get("slot_id") or "")
    root_cause_tags = [
        "operator_source_material_required",
        "operator_receipts_required",
    ]
    blockers = [
        "casf_pdbbind_source_material_not_attached",
        "public_benchmark_real_pose_predictions_missing",
        "dud_e_lit_pcba_enrichment_rows_missing",
        "vina_gnina_comparison_rows_missing",
        "public_benchmark_external_receipts_missing",
    ]
    blocked_operator_slot_count = sum(
        1 for row in operator_evidence_gap_register if row["tier_beta_blocked"]
    )
    operator_handoff_summary = {
        "route": PUBLIC_BENCHMARK_OPERATOR_INTAKE_ROUTE,
        "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET_OUT),
        "first_blocker": blockers[0] if blockers else "",
        "first_blocked_target": first_blocked_target,
        "first_next_action": str(
            first_operator_evidence_gap.get("first_next_action") or ""
        ),
        "required_slot_count": int(operator_intake_packet["required_slot_count"]),
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
    }
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
        "tier_beta_ready": False,
        "public_benchmark_ready": False,
        "blocker_count": len(blockers),
        "first_blocker": blockers[0] if blockers else "",
        "first_blocked_target": first_blocked_target,
        "first_required_operator_slot": first_blocked_target,
        "required_slot_count": int(operator_intake_packet["required_slot_count"]),
        "blocked_operator_slot_count": blocked_operator_slot_count,
        "root_cause_tags": root_cause_tags,
        "operator_handoff_summary": operator_handoff_summary,
        "tier_beta_gate": tier_beta_gate,
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
            "blockers": subset_manifest["blockers"],
        },
        "pose_validity_packet_summary": {
            "status": pose_validity_packet["status"],
            "check_count": len(pose_validity_packet["checks"]),
            "required_check_count": sum(1 for row in pose_validity_packet["checks"] if row["required"]),
            "validator_schema_version": pose_validity_packet["validator"]["schema_version"],
            "materializer_schema_version": pose_validity_packet["materializer"][
                "schema_version"
            ],
            "dry_run_pose_validity_ready": pose_validity_packet["dry_run_validation"][
                "pose_validity_ready"
            ],
            "real_benchmark_case_count": pose_validity_packet["dry_run_validation"][
                "real_benchmark_case_count"
            ],
        },
        "symmetry_rmsd_scorecard_summary": symmetry_rmsd_scorecard_summary,
        "symmetry_rmsd_summary": symmetry_rmsd_scorecard_summary,
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
            "input_slot_ids": [row["slot_id"] for row in operator_intake_packet["input_slots"]],
            "gate_unblock_plan_count": operator_intake_packet["gate_unblock_plan_count"],
            "minimum_subset_case_count": operator_intake_packet["minimum_subset_case_count"],
            "first_blocked_target": str(
                operator_intake_packet.get("first_blocked_target") or first_blocked_target
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
        "posebusters_validity_packet_materializer": {
            "schema_version": POSEBUSTERS_PACKET_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_pose_validity_input",
            "materialization_command": pose_validity_packet["materializer"][
                "materialization_command"
            ],
            "claim_boundary": (
                "The PoseBusters-style packet materializer consumes validated "
                "pose-coordinate input and emits per-case sanity-check rows for real "
                "benchmark ligands. It does not infer chemistry or close Tier beta."
            ),
        },
        "enrichment_scorecard_materializer": {
            "schema_version": ENRICHMENT_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "materialization_command": enrichment_scorecard["materializer"][
                "materialization_command"
            ],
            "claim_boundary": (
                "The enrichment materializer consumes DUD-E/LIT-PCBA scored molecule "
                "rows and reports EF@1%, EF@5%, and ROC-AUC per target. It does not "
                "download benchmark data, validate chemistry, or close Tier beta alone."
            ),
        },
        "vina_gnina_comparison_materializer": {
            "schema_version": VINA_GNINA_MATERIALIZER_SCHEMA_VERSION,
            "status": "ready_for_operator_intake",
            "materialization_command": vina_gnina_comparison_adapter["materializer"][
                "materialization_command"
            ],
            "claim_boundary": (
                "The Vina/GNINA adapter materializer consumes operator-attached engine "
                "comparison rows and reports per-engine pose-success summaries. It does "
                "not run docking engines, fetch benchmark data, or close Tier beta alone."
            ),
        },
        "blockers": blockers,
        "next_actions": [
            "fill_public_benchmark_operator_intake_packet",
            "attach_checked_casf_pdbbind_subset_source_files",
            "run_public_benchmark_subset_materializer",
            "fill_ligand_atom_order_and_symmetry_permutation_contracts",
            "attach_public_benchmark_pose_coordinate_intake",
            "run_public_benchmark_pose_validity_materializer",
            "run_symmetry_aware_rmsd_on_real_subset",
            "run_public_benchmark_rmsd_scorecard_materializer",
            "materialize_posebusters_style_validity_packet_for_real_ligands",
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


def build_public_benchmark_artifacts(*, repo_root: Path = ROOT) -> dict[str, dict[str, Any]]:
    subset_manifest = build_subset_manifest(repo_root=repo_root)
    pose_validity_packet = build_pose_validity_packet(repo_root=repo_root)
    rmsd_scorecard = build_rmsd_scorecard(repo_root=repo_root)
    enrichment_scorecard = build_enrichment_scorecard(repo_root=repo_root)
    vina_gnina_comparison_adapter = build_vina_gnina_comparison_adapter(repo_root=repo_root)
    operator_intake_packet = build_public_benchmark_operator_intake_packet(repo_root=repo_root)
    source_of_truth = build_source_of_truth(
        subset_manifest=subset_manifest,
        pose_validity_packet=pose_validity_packet,
        rmsd_scorecard=rmsd_scorecard,
        enrichment_scorecard=enrichment_scorecard,
        vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
        operator_intake_packet=operator_intake_packet,
        repo_root=repo_root,
    )
    return {
        "source_of_truth": source_of_truth,
        "subset_manifest": subset_manifest,
        "pose_validity_packet": pose_validity_packet,
        "rmsd_scorecard": rmsd_scorecard,
        "enrichment_scorecard": enrichment_scorecard,
        "vina_gnina_comparison_adapter": vina_gnina_comparison_adapter,
        "operator_intake_packet": operator_intake_packet,
    }


def write_public_benchmark_artifacts(
    *,
    repo_root: Path = ROOT,
    source_of_truth_out: Path = DEFAULT_SOURCE_OF_TRUTH_OUT,
    subset_manifest_out: Path = DEFAULT_SUBSET_MANIFEST_OUT,
    pose_validity_packet_out: Path = DEFAULT_POSE_VALIDITY_PACKET_OUT,
    rmsd_scorecard_out: Path = DEFAULT_RMSD_SCORECARD_OUT,
    enrichment_scorecard_out: Path = DEFAULT_ENRICHMENT_SCORECARD_OUT,
    vina_gnina_comparison_adapter_out: Path = DEFAULT_VINA_GNINA_ADAPTER_OUT,
    operator_intake_packet_out: Path = DEFAULT_OPERATOR_INTAKE_PACKET_OUT,
    operator_intake_packet_md_out: Path = DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_public_benchmark_artifacts(repo_root=repo_root)
    outputs = {
        "source_of_truth": source_of_truth_out,
        "subset_manifest": subset_manifest_out,
        "pose_validity_packet": pose_validity_packet_out,
        "rmsd_scorecard": rmsd_scorecard_out,
        "enrichment_scorecard": enrichment_scorecard_out,
        "vina_gnina_comparison_adapter": vina_gnina_comparison_adapter_out,
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
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-of-truth-out", type=Path, default=DEFAULT_SOURCE_OF_TRUTH_OUT)
    parser.add_argument("--subset-manifest-out", type=Path, default=DEFAULT_SUBSET_MANIFEST_OUT)
    parser.add_argument("--pose-validity-packet-out", type=Path, default=DEFAULT_POSE_VALIDITY_PACKET_OUT)
    parser.add_argument("--rmsd-scorecard-out", type=Path, default=DEFAULT_RMSD_SCORECARD_OUT)
    parser.add_argument("--enrichment-scorecard-out", type=Path, default=DEFAULT_ENRICHMENT_SCORECARD_OUT)
    parser.add_argument(
        "--vina-gnina-comparison-adapter-out",
        type=Path,
        default=DEFAULT_VINA_GNINA_ADAPTER_OUT,
    )
    parser.add_argument("--operator-intake-packet-out", type=Path, default=DEFAULT_OPERATOR_INTAKE_PACKET_OUT)
    parser.add_argument("--operator-intake-packet-md-out", type=Path, default=DEFAULT_OPERATOR_INTAKE_PACKET_MD_OUT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    artifacts = write_public_benchmark_artifacts(
        source_of_truth_out=args.source_of_truth_out,
        subset_manifest_out=args.subset_manifest_out,
        pose_validity_packet_out=args.pose_validity_packet_out,
        rmsd_scorecard_out=args.rmsd_scorecard_out,
        enrichment_scorecard_out=args.enrichment_scorecard_out,
        vina_gnina_comparison_adapter_out=args.vina_gnina_comparison_adapter_out,
        operator_intake_packet_out=args.operator_intake_packet_out,
        operator_intake_packet_md_out=args.operator_intake_packet_md_out,
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
