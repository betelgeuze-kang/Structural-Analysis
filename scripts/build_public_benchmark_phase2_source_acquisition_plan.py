#!/usr/bin/env python3
"""Build the Public Benchmark Phase 2 source acquisition plan."""

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

from materialize_public_benchmark_enrichment_scorecard import (  # noqa: E402
    ACTIVE_DECOY_POLICY,
    BOOLEAN_LABEL_POLICY as ENRICHMENT_BOOLEAN_LABEL_POLICY,
    NUMERIC_VALUE_POLICY as ENRICHMENT_NUMERIC_VALUE_POLICY,
    REQUIRED_MOLECULE_FIELDS,
    REQUIRED_TARGET_FIELDS,
    ROW_INTEGRITY_POLICY as ENRICHMENT_ROW_INTEGRITY_POLICY,
    SCORE_DIRECTION_POLICY as ENRICHMENT_SCORE_DIRECTION_POLICY,
    SUPPORTED_FAMILIES,
)
from materialize_public_benchmark_posebusters_validity_packet import (  # noqa: E402
    CHECK_DEFINITIONS as POSEBUSTERS_CHECK_DEFINITIONS,
    PACKET_SCHEMA_VERSION as POSEBUSTERS_PACKET_SCHEMA_VERSION,
)
from materialize_public_benchmark_subset_manifest import (  # noqa: E402
    LOCAL_SOURCE_FILE_FIELDS,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    BOOLEAN_VALUE_POLICY as VINA_GNINA_BOOLEAN_VALUE_POLICY,
    ENGINE_PAIR_POLICY,
    NUMERIC_VALUE_POLICY as VINA_GNINA_NUMERIC_VALUE_POLICY,
    POSE_SUCCESS_POLICY,
    REQUIRED_CASE_FIELDS as VINA_GNINA_REQUIRED_CASE_FIELDS,
    REQUIRED_ENGINE_RUN_FIELDS as VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS,
    ROW_INTEGRITY_POLICY as VINA_GNINA_ROW_INTEGRITY_POLICY,
    SCORE_DIRECTION_POLICY as VINA_GNINA_SCORE_DIRECTION_POLICY,
    SUPPORTED_BENCHMARK_SPLITS as VINA_GNINA_SUPPORTED_BENCHMARK_SPLITS,
    SUPPORTED_ENGINES as VINA_GNINA_SUPPORTED_ENGINES,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from validate_public_benchmark_pose_validity import REQUIRED_POSE_FIELDS  # noqa: E402
from validate_public_benchmark_subset_manifest import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_phase2_source_acquisition_plan.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_OPERATOR_BUNDLE = PRODUCTIZATION / "public_benchmark_operator_bundle.json"
DEFAULT_SOURCE_OF_TRUTH = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_PHASE2_ROW_AUDIT = PRODUCTIZATION / "public_benchmark_phase2_row_audit.json"
DEFAULT_PHASE2_ROW_AUDIT_MD = DEFAULT_PHASE2_ROW_AUDIT.with_suffix(".md")
DEFAULT_HARNESS_BUNDLE = PRODUCTIZATION / "public_benchmark_harness_bundle.json"
DEFAULT_VINA_GNINA_EXECUTION_PLAN = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_execution_plan.json"
)
DEFAULT_VINA_GNINA_RUNTIME_READINESS = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_runtime_readiness.json"
)
DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_template.csv"
)
DEFAULT_VINA_GNINA_INPUT_MANIFEST = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest.csv"
)

SCHEMA_VERSION = "public-benchmark-phase2-source-acquisition-plan.v1"
TIER_BETA_MINIMUM_SUBSET_CASE_COUNT = 12
SUPPORTED_ROW_FORMATS = ["csv", "json", "jsonl", "ndjson"]
SOURCE_CHECKSUM_POLICY = {
    "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
    "required_receipt_field": "source_checksum",
}
RECEIPT_PROMOTION_POLICY = {
    "operator_attached_rows_required": True,
    "external_source_receipts_required": True,
    "per_source_bundle_checksum_required": True,
    "license_or_accession_reference_required": True,
    "synthetic_fixture_rows_promote_to_phase2": False,
    "summary_only_metrics_promote_to_phase2": False,
    "redistribution_of_restricted_benchmark_payloads": False,
}
OFFICIAL_SOURCE_CATALOG = [
    {
        "source_id": "pdbbind_plus_casf",
        "source_family": "CASF/PDBBind",
        "source_name": "PDBbind+ CASF data packages",
        "primary_url": "https://www.pdbbind-plus.org.cn/casf",
        "fallback_url": "https://www.pdbbind-plus.org.cn/",
        "access_mode": "operator_download_and_license_or_accession_receipt_required",
        "feeds_row_inputs": ["subset_rows", "pose_rows", "vina_gnina_rows"],
        "feeds_components": [
            "casf_pdbbind_pose_success_harness",
            "symmetry_aware_ligand_rmsd",
            "posebusters_style_pose_validity",
            "vina_gnina_comparison_adapter",
        ],
        "required_operator_receipts": [
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
            "per_case_local_file_checksums",
        ],
    },
    {
        "source_id": "dud_e",
        "source_family": "DUD-E",
        "source_name": "DUD-E targets and active/decoy sets",
        "primary_url": "https://dude.docking.org/targets/",
        "fallback_url": "https://dude.docking.org/",
        "access_mode": "public_download_with_operator_checksum_receipt",
        "feeds_row_inputs": ["enrichment_rows"],
        "feeds_components": ["dud_e_or_lit_pcba_enrichment"],
        "required_operator_receipts": [
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
            "scoring_run_provenance_ref",
        ],
    },
    {
        "source_id": "lit_pcba",
        "source_family": "LIT-PCBA",
        "source_name": "LIT-PCBA virtual screening benchmark",
        "primary_url": "https://drugdesign.unistra.fr/LIT-PCBA/",
        "fallback_url": "https://drugdesign.unistra.fr/LIT-PCBA/index.htm",
        "access_mode": "public_download_with_operator_checksum_receipt",
        "feeds_row_inputs": ["enrichment_rows"],
        "feeds_components": ["dud_e_or_lit_pcba_enrichment"],
        "required_operator_receipts": [
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
            "scoring_run_provenance_ref",
        ],
    },
    {
        "source_id": "autodock_vina",
        "source_family": "Vina",
        "source_name": "AutoDock Vina",
        "primary_url": "https://vina.scripps.edu/",
        "fallback_url": "https://github.com/ccsb-scripps/AutoDock-Vina",
        "access_mode": "engine_install_and_run_receipt_required",
        "feeds_row_inputs": ["vina_gnina_rows"],
        "feeds_components": ["vina_gnina_comparison_adapter"],
        "required_operator_receipts": [
            "engine_version",
            "engine_config_checksum",
            "engine_run_provenance_ref",
            "predicted_ligand_checksum",
        ],
    },
    {
        "source_id": "gnina",
        "source_family": "GNINA",
        "source_name": "GNINA docking engine",
        "primary_url": "https://github.com/gnina/gnina",
        "fallback_url": "https://gnina.github.io/gnina/rsc_workshop2021/",
        "access_mode": "engine_install_and_run_receipt_required",
        "feeds_row_inputs": ["vina_gnina_rows"],
        "feeds_components": ["vina_gnina_comparison_adapter"],
        "required_operator_receipts": [
            "engine_version",
            "engine_config_checksum",
            "engine_run_provenance_ref",
            "predicted_ligand_checksum",
        ],
    },
    {
        "source_id": "posebusters",
        "source_family": "PoseBusters",
        "source_name": "PoseBusters plausibility checks",
        "primary_url": "https://github.com/maabuu/posebusters",
        "fallback_url": "https://zenodo.org/records/8278563",
        "access_mode": "reference_checklist_or_tool_run_receipt_required",
        "feeds_row_inputs": ["pose_rows"],
        "feeds_components": ["posebusters_style_pose_validity"],
        "required_operator_receipts": [
            "pose_preparation_provenance_ref",
            "source_checksum",
            "provenance_ref",
        ],
    },
]
REQUIRED_ROW_INPUTS = [
    "subset_rows",
    "pose_rows",
    "enrichment_rows",
    "vina_gnina_rows",
]
ROW_INPUT_ACQUISITION_BLOCKERS = {
    "subset_rows": "public_benchmark_subset_rows_not_acquired",
    "pose_rows": "public_benchmark_pose_rows_not_acquired",
    "enrichment_rows": "public_benchmark_enrichment_rows_not_acquired",
    "vina_gnina_rows": "public_benchmark_vina_gnina_rows_not_acquired",
}
PHASE2_COMPONENTS = [
    "casf_pdbbind_pose_success_harness",
    "symmetry_aware_ligand_rmsd",
    "posebusters_style_pose_validity",
    "vina_gnina_comparison_adapter",
    "dud_e_or_lit_pcba_enrichment",
]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_acquisition_blockers(
    phase2_row_audit_summary: dict[str, Any],
    vina_gnina_execution_plan_summary: dict[str, Any],
    vina_gnina_runtime_readiness_summary: dict[str, Any],
) -> list[str]:
    missing_row_inputs = {
        str(row_input)
        for row_input in phase2_row_audit_summary.get("missing_row_inputs", [])
        if str(row_input)
    }
    blockers = [
        ROW_INPUT_ACQUISITION_BLOCKERS[row_input]
        for row_input in REQUIRED_ROW_INPUTS
        if row_input in missing_row_inputs
    ]
    required_engine_run_count = int(
        vina_gnina_runtime_readiness_summary.get("required_engine_run_count") or 0
    )
    ready_engine_run_slot_count = int(
        vina_gnina_runtime_readiness_summary.get("ready_engine_run_slot_count") or 0
    )
    missing_engine_count = int(
        vina_gnina_runtime_readiness_summary.get("missing_engine_count") or 0
    )
    if (
        "vina_gnina_rows" in missing_row_inputs
        and not vina_gnina_runtime_readiness_summary.get(
            "runtime_ready_for_engine_execution"
        )
    ):
        if (
            missing_engine_count == 0
            and ready_engine_run_slot_count < required_engine_run_count
        ):
            blockers.append("public_benchmark_vina_gnina_engine_inputs_not_ready")
        else:
            blockers.append("public_benchmark_vina_gnina_engine_runtime_not_ready")
    if not vina_gnina_execution_plan_summary.get("input_manifest_detected"):
        blockers.append("public_benchmark_vina_gnina_input_manifest_not_detected")
    if missing_engine_count > 0:
        blockers.append(
            "public_benchmark_vina_gnina_engine_binaries_or_container_images_missing"
        )
    if int(phase2_row_audit_summary.get("source_actuality_blocker_count") or 0) > 0:
        blockers.append("public_benchmark_provided_row_source_receipts_not_actual")
    blockers.append("public_benchmark_external_receipts_not_attached")
    return blockers


def _phase2_row_audit_summary(audit: dict[str, Any]) -> dict[str, Any]:
    summary = audit.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    phase2_exit_gate = audit.get("phase2_exit_gate")
    if not isinstance(phase2_exit_gate, dict):
        phase2_exit_gate = {}
    missing_row_inputs = [
        str(row)
        for row in (
            summary.get("missing_row_inputs")
            if isinstance(summary.get("missing_row_inputs"), list)
            else audit.get("missing_row_inputs", [])
        )
        if str(row)
    ]
    blocked_component_ids = [
        str(row)
        for row in (
            summary.get("blocked_component_ids")
            if isinstance(summary.get("blocked_component_ids"), list)
            else []
        )
        if str(row)
    ]
    failed_criteria = [
        str(row)
        for row in (
            summary.get("phase2_failed_criteria")
            if isinstance(summary.get("phase2_failed_criteria"), list)
            else phase2_exit_gate.get("failed_criteria", [])
        )
        if str(row)
    ]
    source_actuality_check = audit.get("partial_operator_source_actuality_check")
    if not isinstance(source_actuality_check, dict):
        source_actuality_check = audit.get("operator_bundle_source_actuality_check")
    if not isinstance(source_actuality_check, dict):
        source_actuality_check = {}
    source_actuality_blockers = [
        str(row)
        for row in source_actuality_check.get("blockers", [])
        if str(row)
    ] if isinstance(source_actuality_check.get("blockers"), list) else []
    return {
        "artifact": str(DEFAULT_PHASE2_ROW_AUDIT),
        "markdown_artifact": str(DEFAULT_PHASE2_ROW_AUDIT_MD),
        "status": str(audit.get("status") or "missing"),
        "contract_pass": audit.get("contract_pass"),
        "phase2_ready": bool(audit.get("phase2_ready")),
        "phase2_exit_gate_status": str(
            summary.get("phase2_exit_gate_status")
            or phase2_exit_gate.get("status")
            or ""
        ),
        "component_count": int(summary.get("component_count") or audit.get("component_count") or 0),
        "component_ready_count": int(
            summary.get("component_ready_count")
            or audit.get("component_ready_count")
            or 0
        ),
        "missing_row_input_count": int(
            summary.get("missing_row_input_count") or len(missing_row_inputs)
        ),
        "missing_row_inputs": missing_row_inputs,
        "blocked_component_ids": blocked_component_ids,
        "phase2_failed_criteria": failed_criteria,
        "phase2_failed_criterion_count": int(
            summary.get("phase2_failed_criterion_count") or len(failed_criteria)
        ),
        "phase2_row_closure_matrix_count": int(
            audit.get("phase2_row_closure_matrix_count") or 0
        ),
        "source_actuality_scope": str(source_actuality_check.get("scope") or ""),
        "source_actuality_contract_pass": source_actuality_check.get("contract_pass"),
        "source_actuality_scope_complete": bool(
            source_actuality_check.get("scope_complete")
        ),
        "source_actuality_phase2_ready": bool(
            source_actuality_check.get("phase2_source_actuality_ready")
        ),
        "source_actuality_blocker_count": int(
            source_actuality_check.get("blocker_count")
            or len(source_actuality_blockers)
        ),
        "source_actuality_blockers": source_actuality_blockers,
        "source_actuality_provided_row_inputs": [
            str(row)
            for row in source_actuality_check.get("provided_row_inputs", [])
            if str(row)
        ] if isinstance(source_actuality_check.get("provided_row_inputs"), list) else [],
        "source_actuality_missing_row_inputs": [
            str(row)
            for row in source_actuality_check.get("missing_row_inputs", [])
            if str(row)
        ] if isinstance(source_actuality_check.get("missing_row_inputs"), list) else [],
        "blocker_count": int(summary.get("blocker_count") or len(audit.get("blockers", []))),
        "command": (
            "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
            f"--out {DEFAULT_PHASE2_ROW_AUDIT} --out-md {DEFAULT_PHASE2_ROW_AUDIT_MD}"
        ),
    }


def _vina_gnina_execution_plan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    input_manifest_status = payload.get("input_manifest_status")
    if not isinstance(input_manifest_status, dict):
        input_manifest_status = {}
    manifest_status = str(
        summary.get("input_manifest_status")
        or input_manifest_status.get("status")
        or ("not_detected" if payload else "missing")
    )
    manifest_blockers = [
        str(row)
        for row in input_manifest_status.get("blockers", [])
        if str(row)
    ] if isinstance(input_manifest_status.get("blockers"), list) else []
    if manifest_status == "not_detected" and not manifest_blockers:
        manifest_blockers = [
            "public_benchmark_vina_gnina_input_manifest_not_detected"
        ]
    return {
        "artifact": str(DEFAULT_VINA_GNINA_EXECUTION_PLAN),
        "status": str(payload.get("status") or "missing"),
        "contract_pass": payload.get("contract_pass"),
        "execution_plan_ready": bool(payload.get("execution_plan_ready")),
        "operator_execution_ready": bool(payload.get("operator_execution_ready")),
        "adapter_rows_ready": bool(payload.get("adapter_rows_ready")),
        "case_count": int(summary.get("case_count") or payload.get("case_count") or 0),
        "required_engine_run_count": int(
            summary.get("required_engine_run_count")
            or payload.get("required_engine_run_count")
            or 0
        ),
        "available_engine_count": int(summary.get("available_engine_count") or 0),
        "missing_engine_count": int(summary.get("missing_engine_count") or 0),
        "missing_engine_ids": [
            str(row)
            for row in payload.get("missing_engine_ids", [])
            if str(row)
        ]
        if isinstance(payload.get("missing_engine_ids"), list)
        else [],
        "blocker_count": len(payload.get("blockers", []))
        if isinstance(payload.get("blockers"), list)
        else 0,
        "input_manifest_status": manifest_status,
        "input_manifest_detected": bool(
            summary.get("input_manifest_detected")
            or input_manifest_status.get("detected_manifest_artifact_count")
        ),
        "input_manifest_row_count": int(
            summary.get("input_manifest_row_count")
            or input_manifest_status.get("row_count")
            or 0
        ),
        "input_manifest_selected_path": str(
            input_manifest_status.get("selected_manifest_path") or ""
        ),
        "input_manifest_blockers": manifest_blockers,
        "engine_input_manifest_template": str(
            DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE
        ),
        "required_engine_input_fields": [
            "case_id",
            "complex_id",
            "protein_structure_path",
            "protein_structure_checksum",
            "reference_ligand_path",
            "reference_ligand_checksum",
            "prepared_receptor_path",
            "prepared_receptor_checksum",
            "prepared_ligand_path",
            "prepared_ligand_checksum",
        ],
        "command": (
            "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
            f"--out {DEFAULT_VINA_GNINA_EXECUTION_PLAN}"
        ),
    }


def _vina_gnina_runtime_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        blockers = []
    row_candidate_status = payload.get("row_candidate_status")
    if not isinstance(row_candidate_status, dict):
        row_candidate_status = {}
    container_runtime_status = payload.get("container_runtime_status")
    if not isinstance(container_runtime_status, dict):
        container_runtime_status = {}
    engine_container_statuses = payload.get("current_engine_container_statuses")
    if not isinstance(engine_container_statuses, list):
        engine_container_statuses = []
    operator_unblock_packet = payload.get("operator_unblock_packet")
    if not isinstance(operator_unblock_packet, dict):
        operator_unblock_packet = {}
    return {
        "artifact": str(DEFAULT_VINA_GNINA_RUNTIME_READINESS),
        "status": str(payload.get("status") or "missing"),
        "contract_pass": payload.get("contract_pass"),
        "execution_plan_ready": bool(payload.get("execution_plan_ready")),
        "runtime_ready_for_engine_execution": bool(
            payload.get("runtime_ready_for_engine_execution")
        ),
        "operator_execution_ready": bool(payload.get("operator_execution_ready")),
        "adapter_rows_ready": bool(payload.get("adapter_rows_ready")),
        "case_count": int(summary.get("case_count") or 0),
        "required_engine_run_count": int(
            summary.get("required_engine_run_count") or 0
        ),
        "ready_engine_run_slot_count": int(
            summary.get("ready_engine_run_slot_count") or 0
        ),
        "available_engine_count": int(summary.get("available_engine_count") or 0),
        "missing_engine_count": int(summary.get("missing_engine_count") or 0),
        "detected_row_artifact_count": int(
            summary.get("detected_row_artifact_count") or 0
        ),
        "selected_row_count": int(summary.get("selected_row_count") or 0),
        "adapter_case_count": int(summary.get("adapter_case_count") or 0),
        "adapter_row_preflight_status": str(
            summary.get("adapter_row_preflight_status")
            or row_candidate_status.get("status")
            or ""
        ),
        "adapter_row_preflight_blocker": str(
            row_candidate_status.get("blocker") or ""
        ),
        "missing_engine_ids": [
            str(row) for row in payload.get("missing_engine_ids", []) if str(row)
        ]
        if isinstance(payload.get("missing_engine_ids"), list)
        else [],
        "container_runtime_status": {
            "available": bool(container_runtime_status.get("available")),
            "executable": str(container_runtime_status.get("executable") or ""),
            "binary_source": str(container_runtime_status.get("binary_source") or ""),
            "blocker": str(container_runtime_status.get("blocker") or ""),
        },
        "engine_container_statuses": [
            {
                "engine_id": str(row.get("engine_id") or ""),
                "status": str(row.get("status") or ""),
                "available": bool(row.get("available")),
                "image_env_var": str(row.get("image_env_var") or ""),
                "image": str(row.get("image") or ""),
                "image_present": bool(row.get("image_present")),
                "docker_binary_available": bool(row.get("docker_binary_available")),
                "docker_daemon_available": bool(row.get("docker_daemon_available")),
                "docker_server_version": str(row.get("docker_server_version") or ""),
                "blocker": str(row.get("blocker") or ""),
            }
            for row in engine_container_statuses
            if isinstance(row, dict)
        ],
        "operator_unblock_packet": operator_unblock_packet,
        "blocker_count": len(blockers),
        "blockers": [str(row) for row in blockers],
        "command": (
            "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
            f"--out {DEFAULT_VINA_GNINA_RUNTIME_READINESS}"
        ),
    }


def _row_input_contracts() -> list[dict[str, Any]]:
    required_posebuster_check_ids = [
        str(row["check_id"])
        for row in POSEBUSTERS_CHECK_DEFINITIONS
        if bool(row.get("required"))
    ]
    return [
        {
            "row_input_id": "subset_rows",
            "source_family": "CASF/PDBBind",
            "status": "operator_acquisition_required",
            "minimum_rows_required": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
            "accepted_formats": list(SUPPORTED_ROW_FORMATS),
            "required_fields": [
                *list(REQUIRED_CASE_FIELDS),
                "ligand_atom_order_contract.atom_count",
                "ligand_atom_order_contract.atom_ids",
                "symmetry_permutation_contract.permutations",
            ],
            "supported_benchmark_splits": list(
                SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS
            ),
            "local_source_file_fields": [str(row) for row in LOCAL_SOURCE_FILE_FIELDS],
            "receipt_fields": [
                "source_license_or_accession",
                "source_checksum",
                "provenance_ref",
            ],
            "source_checksum_policy": dict(SOURCE_CHECKSUM_POLICY),
            "unblocks_components": ["casf_pdbbind_pose_success_harness"],
            "closure_boundary": (
                "Subset rows identify local operator-attached CASF/PDBBind cases and "
                "checksums; they do not redistribute restricted benchmark data or close "
                "pose-success without pose-coordinate rows."
            ),
        },
        {
            "row_input_id": "pose_rows",
            "source_family": "CASF/PDBBind",
            "status": "operator_acquisition_required",
            "minimum_rows_required": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
            "accepted_formats": list(SUPPORTED_ROW_FORMATS),
            "depends_on_row_inputs": ["subset_rows"],
            "required_fields": list(REQUIRED_POSE_FIELDS),
            "receipt_fields": [
                "source_license_or_accession",
                "source_checksum",
                "provenance_ref",
                "pose_preparation_provenance_ref",
            ],
            "source_checksum_policy": dict(SOURCE_CHECKSUM_POLICY),
            "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
            "posebusters_style_check_contract": {
                "packet_schema_version": POSEBUSTERS_PACKET_SCHEMA_VERSION,
                "required_check_ids": required_posebuster_check_ids,
                "all_checks_required": True,
            },
            "symmetry_rmsd_contract": {
                "requires_ligand_atom_order_contract": True,
                "requires_symmetry_permutation_contract": True,
                "success_threshold_angstrom": 2.0,
            },
            "unblocks_components": [
                "casf_pdbbind_pose_success_harness",
                "symmetry_aware_ligand_rmsd",
                "posebusters_style_pose_validity",
            ],
            "closure_boundary": (
                "Pose rows must carry real reference/predicted ligand coordinates in "
                "the declared atom order; placeholder coordinates or fixture ligands do "
                "not close the Phase 2 gate."
            ),
        },
        {
            "row_input_id": "enrichment_rows",
            "source_family": "DUD-E/LIT-PCBA",
            "status": "operator_acquisition_required",
            "minimum_target_count_required": 1,
            "accepted_formats": list(SUPPORTED_ROW_FORMATS),
            "supported_families": list(SUPPORTED_FAMILIES),
            "required_target_fields": list(REQUIRED_TARGET_FIELDS),
            "required_molecule_fields": list(REQUIRED_MOLECULE_FIELDS),
            "receipt_fields": [
                "source_license_or_accession",
                "source_checksum",
                "provenance_ref",
            ],
            "source_checksum_policy": dict(SOURCE_CHECKSUM_POLICY),
            "row_validation_policies": {
                "score_direction_policy": ENRICHMENT_SCORE_DIRECTION_POLICY,
                "boolean_label_policy": ENRICHMENT_BOOLEAN_LABEL_POLICY,
                "numeric_value_policy": ENRICHMENT_NUMERIC_VALUE_POLICY,
                "active_decoy_policy": ACTIVE_DECOY_POLICY,
                "row_integrity_policy": ENRICHMENT_ROW_INTEGRITY_POLICY,
            },
            "unblocks_components": ["dud_e_or_lit_pcba_enrichment"],
            "closure_boundary": (
                "At least one DUD-E or LIT-PCBA target must include scored active and "
                "decoy molecule rows with source receipts; summary-only enrichment "
                "metrics are not closure evidence."
            ),
        },
        {
            "row_input_id": "vina_gnina_rows",
            "source_family": "CASF/PDBBind + Vina/GNINA",
            "status": "operator_acquisition_required",
            "minimum_comparison_case_count_required": 1,
            "accepted_formats": list(SUPPORTED_ROW_FORMATS),
            "depends_on_row_inputs": ["subset_rows", "pose_rows"],
            "required_case_fields": list(VINA_GNINA_REQUIRED_CASE_FIELDS),
            "required_engine_run_fields": list(VINA_GNINA_REQUIRED_ENGINE_RUN_FIELDS),
            "required_engines": list(VINA_GNINA_SUPPORTED_ENGINES),
            "supported_benchmark_splits": list(VINA_GNINA_SUPPORTED_BENCHMARK_SPLITS),
            "engine_input_manifest_template": str(
                DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE
            ),
            "required_engine_input_fields": [
                "case_id",
                "complex_id",
                "protein_structure_path",
                "protein_structure_checksum",
                "reference_ligand_path",
                "reference_ligand_checksum",
                "prepared_receptor_path",
                "prepared_receptor_checksum",
                "prepared_ligand_path",
                "prepared_ligand_checksum",
            ],
            "receipt_fields": [
                "source_license_or_accession",
                "source_checksum",
                "provenance_ref",
                "predicted_ligand_checksum",
                "engine_config_checksum",
                "engine_run_provenance_ref",
            ],
            "source_checksum_policy": dict(SOURCE_CHECKSUM_POLICY),
            "row_validation_policies": {
                "score_direction_policy": VINA_GNINA_SCORE_DIRECTION_POLICY,
                "boolean_value_policy": VINA_GNINA_BOOLEAN_VALUE_POLICY,
                "numeric_value_policy": VINA_GNINA_NUMERIC_VALUE_POLICY,
                "pose_success_policy": POSE_SUCCESS_POLICY,
                "engine_pair_policy": ENGINE_PAIR_POLICY,
                "row_integrity_policy": VINA_GNINA_ROW_INTEGRITY_POLICY,
            },
            "unblocks_components": ["vina_gnina_comparison_adapter"],
            "closure_boundary": (
                "Vina and GNINA rows must describe comparable engine runs over the "
                "same benchmark cases with receipts and computed pose-success fields; "
                "adapter shape alone is not an engine comparison result."
            ),
        },
    ]


def _official_source_receipt_rows(
    row_input_contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contracts = {
        str(row.get("row_input_id")): row
        for row in row_input_contracts
        if isinstance(row, dict)
    }
    common_receipt_fields = [
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
    ]
    return [
        {
            "row_input_id": "subset_rows",
            "receipt_role_id": "casf_pdbbind_subset_source_receipt",
            "status": "operator_receipt_required",
            "source_family": "CASF/PDBBind",
            "accepted_source_identities": [
                "CASF/PDBBind subset membership",
                "CASF/PDBBind protein structure files",
                "CASF/PDBBind co-crystal/reference ligand coordinate files",
            ],
            "required_source_material": [
                "selected complex identifiers from a supported CASF/PDBBind split",
                "local protein structure path for every selected case",
                "local reference ligand path for every selected case",
                "local predicted pose path or docking run id for every selected case",
                "ligand atom-order contract for every selected case",
                "symmetry permutation contract for every selected case",
            ],
            "required_receipt_fields": common_receipt_fields,
            "required_local_checksum_fields": [str(row) for row in LOCAL_SOURCE_FILE_FIELDS],
            "minimum_rows_required": contracts["subset_rows"][
                "minimum_rows_required"
            ],
            "unblocks_components": contracts["subset_rows"][
                "unblocks_components"
            ],
            "operator_must_attach": [
                "source access/license or accession reference",
                "source bundle checksum",
                "per-case local source file checksums",
                "subset preparation provenance reference",
            ],
        },
        {
            "row_input_id": "pose_rows",
            "receipt_role_id": "casf_pdbbind_pose_coordinate_receipt",
            "status": "operator_receipt_required",
            "source_family": "CASF/PDBBind",
            "accepted_source_identities": [
                "CASF/PDBBind reference ligand coordinates",
                "operator-produced predicted ligand coordinates",
                "operator-produced receptor/binding-site preparation context",
            ],
            "required_source_material": [
                "reference ligand atoms in the declared atom order",
                "predicted ligand atoms in the same declared atom order",
                "protein structure path matching the subset manifest case",
                "receptor context for pose sanity checks",
                "symmetry permutation contract used by RMSD scoring",
                "pose preparation provenance for every predicted pose",
            ],
            "required_receipt_fields": [
                *common_receipt_fields,
                "pose_preparation_provenance_ref",
            ],
            "minimum_rows_required": contracts["pose_rows"]["minimum_rows_required"],
            "unblocks_components": contracts["pose_rows"][
                "unblocks_components"
            ],
            "operator_must_attach": [
                "coordinate extraction or conversion receipt",
                "pose preparation provenance reference",
                "row checksum for reference and predicted coordinate payloads",
                "symmetry contract source or derivation note",
            ],
        },
        {
            "row_input_id": "enrichment_rows",
            "receipt_role_id": "dud_e_or_lit_pcba_enrichment_receipt",
            "status": "operator_receipt_required",
            "source_family": "DUD-E/LIT-PCBA",
            "accepted_source_identities": [
                "DUD-E target active/decoy benchmark rows",
                "LIT-PCBA target active/decoy benchmark rows",
                "operator-produced score rows over one supported family",
            ],
            "required_source_material": [
                "benchmark family label for every target",
                "target identifier",
                "scored molecule identifier",
                "active/decoy label",
                "score and score direction",
                "source receipt for active/decoy set and scoring run",
            ],
            "required_receipt_fields": common_receipt_fields,
            "minimum_target_count_required": contracts["enrichment_rows"][
                "minimum_target_count_required"
            ],
            "supported_families": contracts["enrichment_rows"][
                "supported_families"
            ],
            "unblocks_components": contracts["enrichment_rows"][
                "unblocks_components"
            ],
            "operator_must_attach": [
                "active/decoy source receipt",
                "scoring run provenance reference",
                "scored rows checksum",
                "family coverage declaration",
            ],
        },
        {
            "row_input_id": "vina_gnina_rows",
            "receipt_role_id": "vina_gnina_engine_comparison_receipt",
            "status": "operator_receipt_required",
            "source_family": "CASF/PDBBind + Vina/GNINA",
            "accepted_source_identities": [
                "CASF/PDBBind case identifiers already present in subset rows",
                "AutoDock Vina engine run rows",
                "GNINA engine run rows",
            ],
            "required_source_material": [
                "case identifiers matching subset and pose rows",
                "one Vina engine run per comparison case",
                "one GNINA engine run per comparison case",
                "predicted ligand checksum for each engine run",
                "engine version and engine config checksum",
                "symmetry-aware RMSD and pose-success fields per engine run",
            ],
            "required_receipt_fields": [
                *common_receipt_fields,
                "predicted_ligand_checksum",
                "engine_config_checksum",
                "engine_run_provenance_ref",
            ],
            "minimum_comparison_case_count_required": contracts[
                "vina_gnina_rows"
            ]["minimum_comparison_case_count_required"],
            "required_engines": contracts["vina_gnina_rows"][
                "required_engines"
            ],
            "unblocks_components": contracts["vina_gnina_rows"][
                "unblocks_components"
            ],
            "operator_must_attach": [
                "Vina run receipt",
                "GNINA run receipt",
                "engine version and configuration checksums",
                "per-engine predicted ligand checksums",
            ],
        },
    ]


def _official_source_receipt_plan(
    row_input_contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    receipt_rows = _official_source_receipt_rows(row_input_contracts)
    source_catalog = [dict(row) for row in OFFICIAL_SOURCE_CATALOG]
    return {
        "plan_id": "public_benchmark_phase2_official_source_receipt_plan",
        "status": "operator_receipts_required",
        "receipt_role_count": len(receipt_rows),
        "source_catalog_count": len(source_catalog),
        "official_source_catalog": source_catalog,
        "row_input_count": len(REQUIRED_ROW_INPUTS),
        "row_input_receipt_roles": receipt_rows,
        "receipt_promotion_policy": dict(RECEIPT_PROMOTION_POLICY),
        "required_receipt_fields": [
            "source_license_or_accession",
            "source_checksum",
            "provenance_ref",
        ],
        "required_engine_receipt_fields": [
            "engine_version",
            "engine_config_checksum",
            "engine_run_provenance_ref",
            "predicted_ligand_checksum",
        ],
        "operator_review_order": [
            "casf_pdbbind_subset_source_receipt",
            "casf_pdbbind_pose_coordinate_receipt",
            "dud_e_or_lit_pcba_enrichment_receipt",
            "vina_gnina_engine_comparison_receipt",
        ],
        "source_review_order": [row["source_id"] for row in source_catalog],
        "claim_boundary": (
            "Receipt rows identify the authoritative source and operator-produced "
            "evidence needed for Phase 2. They are not source payloads, licenses, "
            "benchmark redistribution, or benchmark results."
        ),
    }


def _row_input_contract_map(
    row_input_contracts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("row_input_id") or ""): row
        for row in row_input_contracts
        if isinstance(row, dict) and str(row.get("row_input_id") or "")
    }


def _missing_row_input_actions(
    *,
    missing_row_inputs: list[str],
    row_input_contracts: list[dict[str, Any]],
    commands: dict[str, str],
    vina_gnina_execution_plan_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts = _row_input_contract_map(row_input_contracts)
    actions: list[dict[str, Any]] = []
    for row_input_id in missing_row_inputs:
        contract = contracts.get(row_input_id, {})
        action = {
            "row_input_id": row_input_id,
            "status": "operator_input_required",
            "source_family": str(contract.get("source_family") or ""),
            "accepted_formats": list(contract.get("accepted_formats") or []),
            "depends_on_row_inputs": list(contract.get("depends_on_row_inputs") or []),
            "unblocks_components": list(contract.get("unblocks_components") or []),
            "receipt_fields": list(contract.get("receipt_fields") or []),
            "source_checksum_policy": dict(
                contract.get("source_checksum_policy") or {}
            ),
            "closure_boundary": str(contract.get("closure_boundary") or ""),
            "operator_action": f"attach_{row_input_id}_then_run_phase2_row_audit",
            "materialization_command": str(commands.get("phase2_row_audit") or ""),
            "bundle_import_command": str(commands.get("import_operator_bundle") or ""),
            "claim_boundary": (
                "This action identifies the missing operator-attached row input. "
                "It is not benchmark evidence until the materializer validates "
                "the row file and receipts."
            ),
        }
        if row_input_id == "vina_gnina_rows":
            action.update(
                {
                    "engine_input_manifest_template": str(
                        contract.get("engine_input_manifest_template") or ""
                    ),
                    "engine_input_manifest_expected_path": str(
                        DEFAULT_VINA_GNINA_INPUT_MANIFEST
                    ),
                    "engine_input_manifest_current_status": str(
                        vina_gnina_execution_plan_summary.get(
                            "input_manifest_status"
                        )
                        or ""
                    ),
                    "engine_input_manifest_current_blockers": list(
                        vina_gnina_execution_plan_summary.get(
                            "input_manifest_blockers"
                        )
                        or []
                    ),
                    "engine_input_manifest_action_packet": {
                        "status": "operator_manifest_required",
                        "template_artifact": str(
                            contract.get("engine_input_manifest_template") or ""
                        ),
                        "expected_manifest_artifact": str(
                            DEFAULT_VINA_GNINA_INPUT_MANIFEST
                        ),
                        "template_to_manifest_command": (
                            "cp "
                            f"{DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE} "
                            f"{DEFAULT_VINA_GNINA_INPUT_MANIFEST}"
                        ),
                        "review_template_command": (
                            "sed -n '1,20p' "
                            f"{DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE}"
                        ),
                        "verify_execution_plan_command": str(
                            commands.get("build_vina_gnina_execution_plan") or ""
                        ),
                        "verify_runtime_readiness_command": str(
                            commands.get("check_vina_gnina_runtime_readiness") or ""
                        ),
                        "operator_must_fill_or_verify": [
                            "prepared_receptor_path",
                            "prepared_receptor_checksum",
                            "prepared_ligand_path",
                            "prepared_ligand_checksum",
                            "vina_config_ref",
                            "gnina_config_ref",
                            "vina_run_receipt_ref",
                            "gnina_run_receipt_ref",
                            "input_preparation_provenance_ref",
                        ],
                        "template_safety_policy": {
                            "template_is_not_evidence": True,
                            "expected_manifest_must_be_operator_reviewed": True,
                            "do_not_treat_blank_prepared_checksums_as_ready": True,
                            "no_engine_rows_are_synthesized_by_manifest": True,
                        },
                        "claim_boundary": (
                            "The scaffold manifest is an operator checklist for "
                            "case inputs. It does not prove engine execution or "
                            "Vina/GNINA adapter row actuality until the execution "
                            "plan, runtime readiness, and adapter rows pass."
                        ),
                    },
                    "required_engine_input_fields": list(
                        contract.get("required_engine_input_fields") or []
                    ),
                    "required_engine_run_fields": list(
                        contract.get("required_engine_run_fields") or []
                    ),
                    "required_engines": list(contract.get("required_engines") or []),
                    "build_execution_plan_command": str(
                        commands.get("build_vina_gnina_execution_plan") or ""
                    ),
                    "runtime_readiness_command": str(
                        commands.get("check_vina_gnina_runtime_readiness") or ""
                    ),
                }
            )
        actions.append(action)
    return actions


def build_public_benchmark_phase2_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    row_input_contracts = _row_input_contracts()
    official_source_receipt_plan = _official_source_receipt_plan(
        row_input_contracts
    )
    phase2_row_audit = _load_json(repo_root, DEFAULT_PHASE2_ROW_AUDIT)
    phase2_row_audit_summary = _phase2_row_audit_summary(phase2_row_audit)
    vina_gnina_execution_plan = _load_json(repo_root, DEFAULT_VINA_GNINA_EXECUTION_PLAN)
    vina_gnina_execution_plan_summary = _vina_gnina_execution_plan_summary(
        vina_gnina_execution_plan
    )
    vina_gnina_runtime_readiness = _load_json(
        repo_root,
        DEFAULT_VINA_GNINA_RUNTIME_READINESS,
    )
    vina_gnina_runtime_readiness_summary = _vina_gnina_runtime_readiness_summary(
        vina_gnina_runtime_readiness
    )
    blockers = _source_acquisition_blockers(
        phase2_row_audit_summary,
        vina_gnina_execution_plan_summary,
        vina_gnina_runtime_readiness_summary,
    )
    commands = {
        "write_plan": (
            "python3 scripts/build_public_benchmark_phase2_source_acquisition_plan.py"
        ),
        "import_operator_bundle": (
            "python3 scripts/materialize_public_benchmark_operator_bundle_from_rows.py "
            "--subset-rows <operator-casf-pdbbind-subset-rows.jsonl> "
            "--pose-rows <operator-pose-coordinate-rows.jsonl> "
            "--enrichment-rows <operator-dud-e-lit-pcba-scored-molecule-rows.csv> "
            "--vina-gnina-rows <operator-vina-gnina-run-rows.csv> "
            "--target-subset-case-count 12 "
            f"--out {DEFAULT_OPERATOR_BUNDLE}"
        ),
        "phase2_row_audit": (
            "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
            "--fail-blocked"
        ),
        "build_vina_gnina_execution_plan": (
            "python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py "
            f"--out {DEFAULT_VINA_GNINA_EXECUTION_PLAN}"
        ),
        "check_vina_gnina_runtime_readiness": (
            "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
            f"--out {DEFAULT_VINA_GNINA_RUNTIME_READINESS}"
        ),
        "materialize_harness_bundle": (
            "python3 scripts/materialize_public_benchmark_harness_bundle.py "
            f"--bundle {DEFAULT_OPERATOR_BUNDLE} --out-dir {PRODUCTIZATION} "
            "--fail-blocked"
        ),
        "refresh_source_of_truth": (
            "python3 scripts/build_public_benchmark_source_of_truth.py "
            f"--source-of-truth-out {DEFAULT_SOURCE_OF_TRUTH}"
        ),
    }
    missing_row_input_actions = _missing_row_input_actions(
        missing_row_inputs=phase2_row_audit_summary["missing_row_inputs"],
        row_input_contracts=row_input_contracts,
        commands=commands,
        vina_gnina_execution_plan_summary=vina_gnina_execution_plan_summary,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_phase2_source_acquisition_plan.py"),
                Path("scripts/materialize_public_benchmark_operator_bundle_from_rows.py"),
                Path("scripts/materialize_public_benchmark_phase2_from_rows.py"),
                Path("scripts/materialize_public_benchmark_harness_bundle.py"),
                DEFAULT_PHASE2_ROW_AUDIT,
                Path("scripts/materialize_public_benchmark_subset_manifest.py"),
                Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
                Path("scripts/materialize_public_benchmark_posebusters_validity_packet.py"),
                Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
                Path("scripts/materialize_public_benchmark_pose_success_harness.py"),
                Path("scripts/materialize_public_benchmark_enrichment_scorecard.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
                Path("scripts/build_public_benchmark_vina_gnina_execution_plan.py"),
                Path("scripts/build_public_benchmark_vina_gnina_runtime_readiness.py"),
                DEFAULT_VINA_GNINA_EXECUTION_PLAN,
                DEFAULT_VINA_GNINA_RUNTIME_READINESS,
                Path("scripts/validate_public_benchmark_external_receipts.py"),
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_phase2_source_acquisition_plan",
            repo_root=repo_root,
        ),
        "status": "operator_acquisition_required",
        "contract_pass": True,
        "phase2_ready": False,
        "actual_closure_ready": False,
        "required_component_count": len(PHASE2_COMPONENTS),
        "required_components": list(PHASE2_COMPONENTS),
        "required_row_input_count": len(REQUIRED_ROW_INPUTS),
        "required_row_inputs": list(REQUIRED_ROW_INPUTS),
        "row_input_contracts": row_input_contracts,
        "official_source_receipt_plan": official_source_receipt_plan,
        "receipt_promotion_policy": dict(RECEIPT_PROMOTION_POLICY),
        "phase2_row_audit": phase2_row_audit_summary,
        "vina_gnina_execution_plan": vina_gnina_execution_plan_summary,
        "vina_gnina_runtime_readiness": vina_gnina_runtime_readiness_summary,
        "missing_row_input_actions": missing_row_input_actions,
        "missing_row_input_action_count": len(missing_row_input_actions),
        "operator_acquisition_checklist": [
            "review_official_source_receipt_plan",
            "attach_casf_pdbbind_subset_rows_with_local_file_checksums",
            "attach_pose_coordinate_rows_with_symmetry_contracts",
            "attach_dud_e_or_lit_pcba_scored_molecule_rows",
            "build_vina_gnina_execution_plan_from_materialized_cases",
            "fill_public_benchmark_vina_gnina_input_manifest",
            "run_vina_gnina_runtime_readiness_check",
            "attach_vina_gnina_engine_run_rows",
            "attach_external_source_receipts_and_license_or_accession_refs",
            "run_public_benchmark_operator_bundle_from_rows",
            "run_public_benchmark_phase2_row_audit",
            "run_public_benchmark_harness_bundle_materializer",
            "refresh_public_benchmark_source_of_truth",
        ],
        "commands": commands,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "required_component_count": len(PHASE2_COMPONENTS),
            "required_row_input_count": len(REQUIRED_ROW_INPUTS),
            "minimum_subset_case_count": TIER_BETA_MINIMUM_SUBSET_CASE_COUNT,
            "minimum_enrichment_target_count": 1,
            "minimum_vina_gnina_comparison_case_count": 1,
            "official_source_receipt_plan_status": official_source_receipt_plan[
                "status"
            ],
            "official_source_receipt_role_count": official_source_receipt_plan[
                "receipt_role_count"
            ],
            "official_source_catalog_count": official_source_receipt_plan[
                "source_catalog_count"
            ],
            "phase2_row_audit_status": phase2_row_audit_summary["status"],
            "phase2_row_audit_blocker_count": phase2_row_audit_summary[
                "blocker_count"
            ],
            "phase2_row_audit_missing_row_input_count": phase2_row_audit_summary[
                "missing_row_input_count"
            ],
            "phase2_row_audit_missing_row_inputs": phase2_row_audit_summary[
                "missing_row_inputs"
            ],
            "phase2_row_audit_failed_criteria": phase2_row_audit_summary[
                "phase2_failed_criteria"
            ],
            "phase2_row_audit_source_actuality_scope": phase2_row_audit_summary[
                "source_actuality_scope"
            ],
            "phase2_row_audit_source_actuality_contract_pass": (
                phase2_row_audit_summary["source_actuality_contract_pass"]
            ),
            "phase2_row_audit_source_actuality_scope_complete": (
                phase2_row_audit_summary["source_actuality_scope_complete"]
            ),
            "phase2_row_audit_source_actuality_blocker_count": (
                phase2_row_audit_summary["source_actuality_blocker_count"]
            ),
            "missing_row_input_action_count": len(missing_row_input_actions),
            "vina_gnina_execution_plan_status": vina_gnina_execution_plan_summary[
                "status"
            ],
            "vina_gnina_execution_plan_ready": vina_gnina_execution_plan_summary[
                "execution_plan_ready"
            ],
            "vina_gnina_required_engine_run_count": vina_gnina_execution_plan_summary[
                "required_engine_run_count"
            ],
            "vina_gnina_input_manifest_status": (
                vina_gnina_execution_plan_summary["input_manifest_status"]
            ),
            "vina_gnina_input_manifest_detected": (
                vina_gnina_execution_plan_summary["input_manifest_detected"]
            ),
            "vina_gnina_input_manifest_row_count": (
                vina_gnina_execution_plan_summary["input_manifest_row_count"]
            ),
            "vina_gnina_missing_engine_count": vina_gnina_execution_plan_summary[
                "missing_engine_count"
            ],
            "vina_gnina_runtime_readiness_status": (
                vina_gnina_runtime_readiness_summary["status"]
            ),
            "vina_gnina_runtime_ready_for_engine_execution": (
                vina_gnina_runtime_readiness_summary[
                    "runtime_ready_for_engine_execution"
                ]
            ),
            "vina_gnina_runtime_ready_engine_run_slot_count": (
                vina_gnina_runtime_readiness_summary["ready_engine_run_slot_count"]
            ),
            "vina_gnina_runtime_detected_row_artifact_count": (
                vina_gnina_runtime_readiness_summary[
                    "detected_row_artifact_count"
                ]
            ),
            "vina_gnina_runtime_adapter_case_count": (
                vina_gnina_runtime_readiness_summary["adapter_case_count"]
            ),
            "vina_gnina_runtime_adapter_row_preflight_status": (
                vina_gnina_runtime_readiness_summary[
                    "adapter_row_preflight_status"
                ]
            ),
            "vina_gnina_runtime_missing_engine_ids": (
                vina_gnina_runtime_readiness_summary["missing_engine_ids"]
            ),
            "vina_gnina_runtime_container_daemon_available": any(
                row["docker_daemon_available"]
                for row in vina_gnina_runtime_readiness_summary[
                    "engine_container_statuses"
                ]
            ),
            "phase2_ready": False,
            "actual_closure_ready": False,
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This plan records the operator source acquisition contract for Public "
            "Benchmark Phase 2. It does not download, redistribute, license, or "
            "synthesize CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA evidence, and "
            "it does not close external beta until real rows and receipts pass the "
            "materializers."
        ),
    }


def render_public_benchmark_phase2_source_acquisition_markdown(
    payload: dict[str, Any],
) -> str:
    lines = [
        "# Public Benchmark Phase 2 Source Acquisition Plan",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `phase2_ready`: `{payload['phase2_ready']}`",
        f"- `actual_closure_ready`: `{payload['actual_closure_ready']}`",
        f"- `blocker_count`: `{payload['blocker_count']}`",
        f"- `official_source_receipt_plan_status`: `{payload['official_source_receipt_plan']['status']}`",
        f"- `official_source_receipt_role_count`: `{payload['official_source_receipt_plan']['receipt_role_count']}`",
        f"- `official_source_catalog_count`: `{payload['official_source_receipt_plan']['source_catalog_count']}`",
        f"- `phase2_row_audit`: `{payload['phase2_row_audit']['artifact']}`",
        f"- `phase2_row_audit_status`: `{payload['phase2_row_audit']['status']}`",
        f"- `phase2_row_audit_missing_row_inputs`: `{', '.join(payload['phase2_row_audit']['missing_row_inputs'])}`",
        f"- `phase2_row_audit_source_actuality_scope`: `{payload['phase2_row_audit']['source_actuality_scope']}`",
        f"- `phase2_row_audit_source_actuality_contract_pass`: `{payload['phase2_row_audit']['source_actuality_contract_pass']}`",
        f"- `phase2_row_audit_source_actuality_blocker_count`: `{payload['phase2_row_audit']['source_actuality_blocker_count']}`",
        f"- `missing_row_input_action_count`: `{payload['missing_row_input_action_count']}`",
        f"- `vina_gnina_execution_plan`: `{payload['vina_gnina_execution_plan']['artifact']}`",
        f"- `vina_gnina_execution_plan_status`: `{payload['vina_gnina_execution_plan']['status']}`",
        f"- `vina_gnina_required_engine_run_count`: `{payload['vina_gnina_execution_plan']['required_engine_run_count']}`",
        f"- `vina_gnina_input_manifest_status`: `{payload['vina_gnina_execution_plan']['input_manifest_status']}`",
        f"- `vina_gnina_input_manifest_row_count`: `{payload['vina_gnina_execution_plan']['input_manifest_row_count']}`",
        f"- `vina_gnina_runtime_readiness`: `{payload['vina_gnina_runtime_readiness']['artifact']}`",
        f"- `vina_gnina_runtime_readiness_status`: `{payload['vina_gnina_runtime_readiness']['status']}`",
        f"- `vina_gnina_runtime_ready_engine_run_slot_count`: `{payload['vina_gnina_runtime_readiness']['ready_engine_run_slot_count']}`",
        f"- `vina_gnina_adapter_row_preflight_status`: `{payload['vina_gnina_runtime_readiness']['adapter_row_preflight_status']}`",
        f"- `vina_gnina_runtime_missing_engine_ids`: `{', '.join(payload['vina_gnina_runtime_readiness']['missing_engine_ids'])}`",
        "",
        "| Row Input | Source Family | Status | Unblocks |",
        "|---|---|---|---|",
    ]
    for row in payload["row_input_contracts"]:
        unblocks = ", ".join(
            f"`{component}`" for component in row["unblocks_components"]
        )
        lines.append(
            f"| `{row['row_input_id']}` | `{row['source_family']}` | "
            f"`{row['status']}` | {unblocks} |"
        )
    missing_actions = [
        row
        for row in payload.get("missing_row_input_actions", [])
        if isinstance(row, dict)
    ]
    if missing_actions:
        lines.extend(["", "## Missing Row Input Actions", ""])
        lines.extend(
            [
                "| Row Input | Action | Unblocks | Materialization |",
                "|---|---|---|---|",
            ]
        )
        for row in missing_actions:
            unblocks = ", ".join(
                f"`{component}`" for component in row.get("unblocks_components", [])
            )
            lines.append(
                f"| `{row.get('row_input_id', '')}` | "
                f"`{row.get('operator_action', '')}` | {unblocks} | "
                f"`{row.get('materialization_command', '')}` |"
            )
        manifest_actions = [
            row.get("engine_input_manifest_action_packet")
            for row in missing_actions
            if isinstance(row.get("engine_input_manifest_action_packet"), dict)
        ]
        if manifest_actions:
            lines.extend(["", "### Vina/GNINA Input Manifest Action", ""])
            for action in manifest_actions:
                if not isinstance(action, dict):
                    continue
                safety_policy = action.get("template_safety_policy")
                if not isinstance(safety_policy, dict):
                    safety_policy = {}
                required_fields = ", ".join(
                    f"`{field}`"
                    for field in action.get("operator_must_fill_or_verify", [])
                )
                lines.extend(
                    [
                        f"- `status`: `{action.get('status')}`",
                        f"- `template_artifact`: `{action.get('template_artifact')}`",
                        f"- `expected_manifest_artifact`: `{action.get('expected_manifest_artifact')}`",
                        f"- `template_to_manifest_command`: `{action.get('template_to_manifest_command')}`",
                        f"- `verify_execution_plan_command`: `{action.get('verify_execution_plan_command')}`",
                        f"- `verify_runtime_readiness_command`: `{action.get('verify_runtime_readiness_command')}`",
                        f"- `operator_must_fill_or_verify`: {required_fields}",
                        f"- `template_is_not_evidence`: `{safety_policy.get('template_is_not_evidence')}`",
                        f"- `do_not_treat_blank_prepared_checksums_as_ready`: `{safety_policy.get('do_not_treat_blank_prepared_checksums_as_ready')}`",
                    ]
                )
    lines.extend(["", "## Vina/GNINA Runtime", ""])
    runtime_unblock = payload["vina_gnina_runtime_readiness"].get(
        "operator_unblock_packet"
    )
    if isinstance(runtime_unblock, dict) and runtime_unblock:
        lines.extend(
            [
                f"- `operator_unblock_status`: `{runtime_unblock.get('status')}`",
                f"- `input_manifest_template_artifact`: `{runtime_unblock.get('input_manifest_template_artifact')}`",
                f"- `blocked_case_input_slot_count`: `{runtime_unblock.get('blocked_case_input_slot_count')}`",
                f"- `blocked_engine_run_slot_count`: `{runtime_unblock.get('blocked_engine_run_slot_count')}`",
                f"- `adapter_row_preflight_status`: `{runtime_unblock.get('adapter_row_preflight_status')}`",
                "",
            ]
        )
    lines.extend(
        [
            "| Engine | Container Status | Docker Daemon | Image Env Var | Image Present |",
            "|---|---|---|---|---|",
        ]
    )
    for row in payload["vina_gnina_runtime_readiness"][
        "engine_container_statuses"
    ]:
        lines.append(
            f"| `{row['engine_id']}` | `{row['status']}` | "
            f"`{row['docker_daemon_available']}` | `{row['image_env_var']}` | "
            f"`{row['image_present']}` |"
        )
    lines.extend(["", "## Source Receipt Roles", ""])
    lines.extend(["| Row Input | Receipt Role | Required Receipt Fields |", "|---|---|---|"])
    for row in payload["official_source_receipt_plan"][
        "row_input_receipt_roles"
    ]:
        receipt_fields = ", ".join(
            f"`{field}`" for field in row["required_receipt_fields"]
        )
        lines.append(
            f"| `{row['row_input_id']}` | `{row['receipt_role_id']}` | "
            f"{receipt_fields} |"
        )
    lines.extend(["", "## Official Source Catalog", ""])
    lines.extend(["| Source | Family | Feeds Row Inputs | Primary URL |", "|---|---|---|---|"])
    for row in payload["official_source_receipt_plan"][
        "official_source_catalog"
    ]:
        feeds = ", ".join(f"`{row_input}`" for row_input in row["feeds_row_inputs"])
        lines.append(
            f"| `{row['source_id']}` | `{row['source_family']}` | "
            f"{feeds} | {row['primary_url']} |"
        )
    lines.extend(["", "## Commands", ""])
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_public_benchmark_phase2_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_public_benchmark_phase2_source_acquisition_plan(
        repo_root=repo_root
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_public_benchmark_phase2_source_acquisition_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_public_benchmark_phase2_source_acquisition_plan(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-phase2-source-acquisition-plan: "
            f"{payload['status']} | row_inputs={payload['required_row_input_count']} | "
            f"components={payload['required_component_count']} | "
            f"blockers={payload['blocker_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
