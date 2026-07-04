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
    SUPPORTED_INTAKE_FORMATS as VINA_GNINA_SUPPORTED_INTAKE_FORMATS,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from validate_public_benchmark_pose_validity import REQUIRED_POSE_FIELDS  # noqa: E402
from validate_public_benchmark_subset_manifest import (  # noqa: E402
    REQUIRED_CASE_FIELDS,
    SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS,
)
from validate_public_benchmark_external_receipts import (  # noqa: E402
    validate_external_receipts,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_phase2_source_acquisition_plan.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_OPERATOR_BUNDLE = PRODUCTIZATION / "public_benchmark_operator_bundle.json"
DEFAULT_SOURCE_OF_TRUTH = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_SUBSET_MANIFEST = PRODUCTIZATION / "public_benchmark_subset_manifest.json"
DEFAULT_ENRICHMENT_SCORECARD = (
    PRODUCTIZATION / "public_benchmark_enrichment_scorecard.json"
)
DEFAULT_VINA_GNINA_COMPARISON_ADAPTER = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_comparison_adapter.json"
)
DEFAULT_PHASE2_ROW_AUDIT = PRODUCTIZATION / "public_benchmark_phase2_row_audit.json"
DEFAULT_PHASE2_ROW_AUDIT_MD = DEFAULT_PHASE2_ROW_AUDIT.with_suffix(".md")
DEFAULT_HARNESS_BUNDLE = PRODUCTIZATION / "public_benchmark_harness_bundle.json"
DEFAULT_VINA_GNINA_EXECUTION_PLAN = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_execution_plan.json"
)
DEFAULT_VINA_GNINA_RUNTIME_READINESS = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_runtime_readiness.json"
)
DEFAULT_VINA_GNINA_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_VINA_GNINA_ROWS_TEMPLATE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template.csv"
)
DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template_preflight.json"
)
DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD = (
    DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT.with_suffix(".md")
)
DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_template.csv"
)
DEFAULT_VINA_GNINA_INPUT_MANIFEST = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest.csv"
)
DEFAULT_VINA_GNINA_INPUT_MANIFEST_FROM_TEMPLATE_REPORT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_input_manifest_from_template_report.json"
)
DEFAULT_VINA_GNINA_INPUT_MANIFEST_FROM_CASF_ARCHIVE_REPORT = (
    PRODUCTIZATION
    / "public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json"
)
DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT = (
    PRODUCTIZATION / "public_benchmark_source_access_preflight_receipt.json"
)
DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT_MD = (
    DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT.with_suffix(".md")
)
DEFAULT_EXTERNAL_RECEIPTS_VALIDATION = (
    PRODUCTIZATION / "public_benchmark_external_receipts_validation.json"
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
SOURCE_ACCESS_PREFLIGHT_POLICY = {
    "network_probe_only": True,
    "raw_payload_downloaded_by_plan": False,
    "raw_payload_committed_by_plan": False,
    "license_or_accession_review_required_before_payload_use": True,
    "source_checksum_required_after_operator_acquisition": True,
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
PHASE2_HARNESS_REQUIREMENTS = [
    {
        "requirement_id": "casf_pdbbind_pose_success_harness",
        "criterion_id": "casf_pdbbind_pose_success_harness_ready",
        "component_id": "casf_pdbbind_pose_success_harness",
        "product_requirement": "CASF/PDBBind pose-success harness",
    },
    {
        "requirement_id": "symmetry_aware_ligand_rmsd",
        "criterion_id": "symmetry_aware_ligand_rmsd_ready",
        "component_id": "symmetry_aware_ligand_rmsd",
        "product_requirement": "symmetry-aware ligand RMSD",
    },
    {
        "requirement_id": "posebusters_style_pose_validity_checks",
        "criterion_id": "posebusters_style_pose_validity_ready",
        "component_id": "posebusters_style_pose_validity",
        "product_requirement": "PoseBusters-style pose validity checks",
    },
    {
        "requirement_id": "vina_gnina_comparison_adapter",
        "criterion_id": "vina_gnina_comparison_ready",
        "component_id": "vina_gnina_comparison_adapter",
        "product_requirement": "Vina/GNINA comparison adapter",
    },
    {
        "requirement_id": "dud_e_or_lit_pcba_enrichment",
        "criterion_id": "dud_e_or_lit_pcba_enrichment_ready",
        "component_id": "dud_e_or_lit_pcba_enrichment",
        "product_requirement": "DUD-E or LIT-PCBA enrichment",
    },
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _compact_operator_blocker_family(
    row: dict[str, Any],
    *,
    commands: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not row:
        return {}
    command_key = str(row.get("command_key") or "")
    return {
        "family_id": str(row.get("family_id") or ""),
        "description": str(row.get("description") or ""),
        "status": str(row.get("status") or ""),
        "missing_item_count": _as_int(row.get("missing_item_count")),
        "blocked_case_count": _as_int(row.get("blocked_case_count")),
        "first_missing_item": _as_dict(row.get("first_missing_item")),
        "operator_action": str(row.get("operator_action") or ""),
        "next_action": str(
            row.get("next_action") or row.get("operator_action") or ""
        ),
        "command_key": command_key,
        "materialization_command": str(
            row.get("materialization_command")
            or _as_dict(commands or {}).get(command_key)
            or ""
        ),
    }


def _operator_blocker_family_row(
    *,
    family_id: str,
    description: str,
    missing_item_count: int,
    blocked_case_count: int,
    first_missing_item: dict[str, Any],
    operator_action: str,
    command_key: str,
    commands: dict[str, Any] | None = None,
) -> dict[str, Any]:
    materialization_command = str(_as_dict(commands or {}).get(command_key) or "")
    return {
        "family_id": family_id,
        "description": description,
        "status": "blocked" if missing_item_count else "ready",
        "missing_item_count": missing_item_count,
        "blocked_case_count": blocked_case_count,
        "first_missing_item": first_missing_item if missing_item_count else {},
        "operator_action": operator_action,
        "next_action": operator_action,
        "command_key": command_key,
        "materialization_command": materialization_command,
    }


def _case_count(rows: list[dict[str, Any]]) -> int:
    return len({str(row.get("case_id") or "") for row in rows if row.get("case_id")})


def _fallback_vina_gnina_operator_blocker_family_plan(
    packet: dict[str, Any],
) -> list[dict[str, Any]]:
    commands = _as_dict(packet.get("commands"))
    preflight_summary = _as_dict(packet.get("input_manifest_template_preflight_summary"))
    completion_actions = [
        row
        for row in _as_list(
            packet.get("input_manifest_completion_action_plan")
            or preflight_summary.get("input_manifest_completion_action_plan")
        )
        if isinstance(row, dict)
    ]
    missing_required_values = [
        {
            "case_id": str(row.get("case_id") or ""),
            "complex_id": str(row.get("complex_id") or ""),
            "field": str(field),
            "operator_action": str(row.get("operator_completion_action") or ""),
        }
        for row in completion_actions
        for field in _as_list(row.get("missing_required_fields"))
        if str(field)
    ]
    local_file_requirements = [
        requirement
        for row in completion_actions
        for requirement in _as_list(row.get("missing_local_file_requirements"))
        if isinstance(requirement, dict)
    ]
    official_source_files = [
        row
        for row in local_file_requirements
        if str(row.get("file_group") or "") == "official_source_file"
    ]
    prepared_input_files = [
        row
        for row in local_file_requirements
        if str(row.get("file_group") or "") == "prepared_input_file"
    ]
    receipt_refs = [
        requirement
        for row in completion_actions
        for requirement in _as_list(row.get("missing_receipt_ref_requirements"))
        if isinstance(requirement, dict)
    ]
    missing_engine_ids = [str(row) for row in _as_list(packet.get("missing_engine_ids")) if str(row)]
    engine_runtime_items = [
        {
            "engine_id": engine_id,
            "operator_action": f"configure_{engine_id}_runtime",
        }
        for engine_id in missing_engine_ids
    ]
    blocked_engine_run_slot_count = _as_int(packet.get("blocked_engine_run_slot_count"))
    first_blocked_engine_run_slot = _as_dict(packet.get("first_blocked_engine_run_slot"))
    adapter_missing_count = (
        0
        if str(packet.get("adapter_row_preflight_status") or "") == "row_artifact_detected_validated"
        else max(_as_int(packet.get("case_input_slot_count")), 1)
    )
    adapter_first_item = {
        "artifact": str(packet.get("expected_rows_artifact") or DEFAULT_VINA_GNINA_ROWS),
        "status": str(packet.get("adapter_row_preflight_status") or ""),
        "detected_row_artifact_count": _as_int(packet.get("detected_row_artifact_count")),
        "operator_action": "attach_or_materialize_public_benchmark_vina_gnina_rows",
    }
    return [
        _operator_blocker_family_row(
            family_id="manifest_required_values",
            description="Required manifest scalar values and checksums are missing.",
            missing_item_count=len(missing_required_values),
            blocked_case_count=_case_count(missing_required_values),
            first_missing_item=missing_required_values[0]
            if missing_required_values
            else {},
            operator_action="complete_vina_gnina_input_manifest_required_values",
            command_key="build_input_manifest_template_preflight",
            commands=commands,
        ),
        _operator_blocker_family_row(
            family_id="official_source_files",
            description="Official CASF/PDBBind source protein and ligand files are missing or unverified.",
            missing_item_count=len(official_source_files),
            blocked_case_count=_case_count(official_source_files),
            first_missing_item=official_source_files[0] if official_source_files else {},
            operator_action="materialize_source_files_from_casf_archive_and_verify_checksum",
            command_key="materialize_input_manifest_from_casf_archive",
            commands=commands,
        ),
        _operator_blocker_family_row(
            family_id="prepared_input_files",
            description="Prepared receptor and ligand inputs for Vina/GNINA are missing or unverified.",
            missing_item_count=len(prepared_input_files),
            blocked_case_count=_case_count(prepared_input_files),
            first_missing_item=prepared_input_files[0] if prepared_input_files else {},
            operator_action="prepare_vina_gnina_inputs_and_record_checksums",
            command_key="build_input_manifest_template_preflight",
            commands=commands,
        ),
        _operator_blocker_family_row(
            family_id="input_and_engine_receipt_refs",
            description="Input preparation, engine config, and engine run receipt refs are missing.",
            missing_item_count=len(receipt_refs),
            blocked_case_count=_case_count(receipt_refs),
            first_missing_item=receipt_refs[0] if receipt_refs else {},
            operator_action="attach_vina_gnina_input_and_engine_receipt_refs",
            command_key="build_input_manifest_template_preflight",
            commands=commands,
        ),
        _operator_blocker_family_row(
            family_id="engine_runtime",
            description="Vina/GNINA binaries or local container images are not configured.",
            missing_item_count=len(engine_runtime_items),
            blocked_case_count=0,
            first_missing_item=engine_runtime_items[0] if engine_runtime_items else {},
            operator_action="configure_vina_gnina_binary_or_container_runtime",
            command_key="rerun_runtime_readiness",
            commands=commands,
        ),
        _operator_blocker_family_row(
            family_id="engine_run_slots",
            description="Required Vina/GNINA engine run slots are not ready for execution.",
            missing_item_count=blocked_engine_run_slot_count,
            blocked_case_count=_as_int(packet.get("blocked_case_input_slot_count")),
            first_missing_item=first_blocked_engine_run_slot,
            operator_action="rerun_runtime_readiness_until_engine_run_slots_ready",
            command_key="rerun_runtime_readiness",
            commands=commands,
        ),
        _operator_blocker_family_row(
            family_id="adapter_rows",
            description="The Vina/GNINA comparison adapter rows artifact is missing or blocked.",
            missing_item_count=adapter_missing_count,
            blocked_case_count=adapter_missing_count,
            first_missing_item=adapter_first_item,
            operator_action="attach_or_materialize_public_benchmark_vina_gnina_rows",
            command_key="materialize_rows_from_engine_run_bundle",
            commands=commands,
        ),
    ]


def _compact_vina_gnina_operator_unblock_packet(
    packet: dict[str, Any],
) -> dict[str, Any]:
    if not packet:
        return {}
    compact = dict(packet)
    commands = _as_dict(packet.get("commands"))
    compact["first_operator_blocker_family"] = _compact_operator_blocker_family(
        _as_dict(packet.get("first_operator_blocker_family")),
        commands=commands,
    )
    family_plan = [
        _compact_operator_blocker_family(row, commands=commands)
        for row in _as_list(packet.get("operator_blocker_family_plan"))
        if isinstance(row, dict)
    ]
    if not family_plan:
        family_plan = _fallback_vina_gnina_operator_blocker_family_plan(packet)
        blocked_families = [
            row for row in family_plan if str(row.get("status") or "") != "ready"
        ]
        compact["operator_blocker_family_count"] = len(family_plan)
        compact["operator_blocker_family_blocked_count"] = len(blocked_families)
        compact["operator_blocker_family_missing_item_count"] = sum(
            _as_int(row.get("missing_item_count")) for row in blocked_families
        )
        compact["first_operator_blocker_family"] = (
            blocked_families[0] if blocked_families else {}
        )
    compact["operator_blocker_family_plan"] = family_plan
    return compact


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


def _phase2_row_closure_matrix(audit: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_rows = audit.get("phase2_row_closure_matrix")
    if not isinstance(raw_rows, list):
        raw_rows = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        required_by_components = [
            {
                "component_id": str(item.get("component_id") or ""),
                "criterion_id": str(item.get("criterion_id") or ""),
                "artifact_role": str(item.get("artifact_role") or ""),
                "ready_field": str(item.get("ready_field") or ""),
                "count_field": str(item.get("count_field") or ""),
                "required_minimum_count": int(
                    item.get("required_minimum_count") or 0
                ),
            }
            for item in row.get("required_by_components", [])
            if isinstance(item, dict)
        ]
        rows.append(
            {
                "row_input_id": str(row.get("row_input_id") or ""),
                "description": str(row.get("description") or ""),
                "status": str(row.get("status") or ""),
                "missing": bool(row.get("missing")),
                "auto_detected": bool(row.get("auto_detected")),
                "resolved_path": str(row.get("resolved_path") or ""),
                "provided_path": str(row.get("provided_path") or ""),
                "default_row_path_candidates": [
                    str(item)
                    for item in row.get("default_row_path_candidates", [])
                    if str(item)
                ]
                if isinstance(row.get("default_row_path_candidates"), list)
                else [],
                "accepted_formats": [
                    str(item) for item in row.get("accepted_formats", []) if str(item)
                ]
                if isinstance(row.get("accepted_formats"), list)
                else [],
                "feeds_components": [
                    str(item) for item in row.get("feeds_components", []) if str(item)
                ]
                if isinstance(row.get("feeds_components"), list)
                else [],
                "closes_phase2_criteria": [
                    str(item)
                    for item in row.get("closes_phase2_criteria", [])
                    if str(item)
                ]
                if isinstance(row.get("closes_phase2_criteria"), list)
                else [],
                "required_by_components": required_by_components,
                "operator_blockers_if_missing": [
                    str(item)
                    for item in row.get("operator_blockers_if_missing", [])
                    if str(item)
                ]
                if isinstance(row.get("operator_blockers_if_missing"), list)
                else [],
                "materialization_chain": [
                    str(item)
                    for item in row.get("materialization_chain", [])
                    if str(item)
                ]
                if isinstance(row.get("materialization_chain"), list)
                else [],
                "row_contract_ref": str(row.get("row_contract_ref") or ""),
                "claim_boundary": str(row.get("claim_boundary") or ""),
            }
        )
    return rows


def _phase2_exit_criteria(audit: dict[str, Any]) -> list[dict[str, Any]]:
    phase2_exit_gate = audit.get("phase2_exit_gate")
    if not isinstance(phase2_exit_gate, dict):
        phase2_exit_gate = {}
    raw_criteria = phase2_exit_gate.get("criteria")
    if not isinstance(raw_criteria, list):
        raw_criteria = []
    criteria: list[dict[str, Any]] = []
    for row in raw_criteria:
        if not isinstance(row, dict):
            continue
        blockers = row.get("blockers")
        if not isinstance(blockers, list):
            blockers = []
        current = row.get("current")
        if not isinstance(current, dict):
            current = {}
        required = row.get("required")
        if not isinstance(required, dict):
            required = {}
        criteria.append(
            {
                "criterion_id": str(row.get("criterion_id") or ""),
                "component_id": str(row.get("component_id") or ""),
                "artifact_role": str(row.get("artifact_role") or ""),
                "pass": bool(row.get("pass")),
                "current": current,
                "required": required,
                "blockers": [str(item) for item in blockers if str(item)],
            }
        )
    return criteria


def _criterion_row_inputs(
    criterion_id: str,
    phase2_row_closure_matrix: list[dict[str, Any]],
) -> list[str]:
    row_inputs: list[str] = []
    for row in phase2_row_closure_matrix:
        closes = row.get("closes_phase2_criteria")
        if not isinstance(closes, list) or criterion_id not in closes:
            continue
        row_input_id = str(row.get("row_input_id") or "")
        if row_input_id:
            row_inputs.append(row_input_id)
    return row_inputs


def _phase2_harness_completion_audit(
    *,
    phase2_exit_criteria: list[dict[str, Any]],
    phase2_row_closure_matrix: list[dict[str, Any]],
    phase2_row_audit_summary: dict[str, Any],
    vina_gnina_execution_plan_summary: dict[str, Any],
    vina_gnina_runtime_readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    criteria_by_id = {
        str(row.get("criterion_id") or ""): row
        for row in phase2_exit_criteria
        if isinstance(row, dict)
    }
    missing_row_inputs = [
        str(row)
        for row in phase2_row_audit_summary.get("missing_row_inputs", [])
        if str(row)
    ]
    missing_row_input_set = set(missing_row_inputs)
    requirement_rows: list[dict[str, Any]] = []
    for requirement in PHASE2_HARNESS_REQUIREMENTS:
        criterion_id = str(requirement["criterion_id"])
        criterion = criteria_by_id.get(criterion_id, {})
        row_inputs = _criterion_row_inputs(criterion_id, phase2_row_closure_matrix)
        row_input_status = {
            row_input: (
                "missing" if row_input in missing_row_input_set else "provided"
            )
            for row_input in row_inputs
        }
        blockers = [
            str(blocker)
            for blocker in criterion.get("blockers", [])
            if str(blocker)
        ] if isinstance(criterion.get("blockers"), list) else []
        status = "ready" if bool(criterion.get("pass")) else "blocked"
        if (
            criterion_id == "vina_gnina_comparison_ready"
            and not bool(criterion.get("pass"))
        ):
            status = "blocked_pending_actual_vina_gnina_rows"
        requirement_rows.append(
            {
                **requirement,
                "status": status,
                "pass": bool(criterion.get("pass")),
                "row_inputs": row_inputs,
                "row_input_status": row_input_status,
                "current": _as_dict(criterion.get("current")),
                "required": _as_dict(criterion.get("required")),
                "blockers": blockers,
                "claim_boundary": (
                    "This row audits Phase 2 harness readiness from the "
                    "materialized row audit. It does not replace the underlying "
                    "benchmark materializers or external source receipts."
                ),
            }
        )
    ready_count = sum(1 for row in requirement_rows if bool(row["pass"]))
    blocked_rows = [row for row in requirement_rows if not bool(row["pass"])]
    only_vina_gnina_rows_blocked = (
        ready_count == len(PHASE2_HARNESS_REQUIREMENTS) - 1
        and [row["criterion_id"] for row in blocked_rows]
        == ["vina_gnina_comparison_ready"]
        and missing_row_inputs == ["vina_gnina_rows"]
    )
    return {
        "status": (
            "ready_except_vina_gnina_actual_rows"
            if only_vina_gnina_rows_blocked
            else "harness_inputs_blocked"
        ),
        "pass": only_vina_gnina_rows_blocked,
        "phase2_ready": bool(phase2_row_audit_summary.get("phase2_ready")),
        "harness_contract_complete_except_vina_gnina_actual_rows": (
            only_vina_gnina_rows_blocked
        ),
        "requirement_count": len(requirement_rows),
        "ready_requirement_count": ready_count,
        "blocked_requirement_count": len(blocked_rows),
        "blocked_requirement_ids": [
            str(row["requirement_id"]) for row in blocked_rows
        ],
        "remaining_row_inputs": missing_row_inputs,
        "remaining_blockers": [
            str(blocker)
            for row in blocked_rows
            for blocker in row.get("blockers", [])
            if str(blocker)
        ],
        "remaining_operator_action": (
            "attach_vina_gnina_rows_then_run_phase2_row_audit"
            if only_vina_gnina_rows_blocked
            else "review_public_benchmark_phase2_row_audit_blockers"
        ),
        "vina_gnina_runtime_status": str(
            vina_gnina_runtime_readiness_summary.get("status") or ""
        ),
        "vina_gnina_input_manifest_status": str(
            vina_gnina_execution_plan_summary.get("input_manifest_status") or ""
        ),
        "vina_gnina_runtime_missing_engine_ids": [
            str(row)
            for row in vina_gnina_runtime_readiness_summary.get(
                "missing_engine_ids", []
            )
            if str(row)
        ],
        "requirements": requirement_rows,
        "claim_boundary": (
            "This audit proves the harness surface is complete only up to the "
            "explicit Vina/GNINA actual-row boundary. Full Phase 2 still requires "
            "real Vina/GNINA engine rows, input manifest receipts, runtime "
            "evidence, and refreshed row audit/source-of-truth artifacts."
        ),
    }


def _vina_gnina_execution_plan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    input_manifest_status = payload.get("input_manifest_status")
    if not isinstance(input_manifest_status, dict):
        input_manifest_status = {}
    manifest_candidate_rows = (
        [
            row
            for row in input_manifest_status.get("candidate_paths", [])
            if isinstance(row, dict)
        ]
        if isinstance(input_manifest_status.get("candidate_paths"), list)
        else []
    )
    manifest_candidate_paths = [
        str(row.get("path") or "")
        for row in manifest_candidate_rows
        if str(row.get("path") or "")
    ]
    manifest_load_errors = [
        {
            "path": str(row.get("path") or ""),
            "format": str(row.get("format") or ""),
            "load_error": str(row.get("load_error") or ""),
        }
        for row in manifest_candidate_rows
        if str(row.get("load_error") or "")
    ]
    accepted_manifest_formats = (
        [
            str(row)
            for row in input_manifest_status.get("accepted_formats", [])
            if str(row)
        ]
        if isinstance(input_manifest_status.get("accepted_formats"), list)
        else []
    )
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
        "input_manifest_selected_format": str(
            input_manifest_status.get("selected_manifest_format") or ""
        ),
        "input_manifest_default_manifest_path": str(
            input_manifest_status.get("default_manifest_path") or ""
        ),
        "input_manifest_detected_manifest_artifact_count": int(
            input_manifest_status.get("detected_manifest_artifact_count") or 0
        ),
        "input_manifest_accepted_formats": accepted_manifest_formats,
        "input_manifest_candidate_paths": manifest_candidate_paths,
        "input_manifest_load_errors": manifest_load_errors,
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


def _vina_gnina_engine_run_slot_matrix(
    engine_run_slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in engine_run_slots:
        if not isinstance(slot, dict):
            continue
        case_id = str(slot.get("case_id") or "")
        engine_id = str(slot.get("engine_id") or "")
        blockers = [
            str(row) for row in slot.get("blockers", []) if str(row)
        ] if isinstance(slot.get("blockers"), list) else []
        rows.append(
            {
                "slot_id": f"{case_id}_{engine_id}" if case_id and engine_id else "",
                "case_id": case_id,
                "complex_id": str(slot.get("complex_id") or ""),
                "engine_id": engine_id,
                "status": str(slot.get("status") or ""),
                "case_inputs_ready": bool(slot.get("case_inputs_ready")),
                "engine_available": bool(slot.get("engine_available")),
                "docking_box_ready": bool(slot.get("docking_box_ready")),
                "blockers": blockers,
                "docking_run_id": str(slot.get("docking_run_id") or ""),
                "expected_predicted_ligand_path_or_pose_ref": str(
                    slot.get("expected_predicted_ligand_path_or_pose_ref") or ""
                ),
                "expected_engine_config_ref": str(
                    slot.get("expected_engine_config_ref") or ""
                ),
                "expected_engine_run_provenance_ref": str(
                    slot.get("expected_engine_run_provenance_ref") or ""
                ),
                "required_adapter_engine_run_fields": [
                    str(row)
                    for row in slot.get("required_adapter_engine_run_fields", [])
                    if str(row)
                ]
                if isinstance(slot.get("required_adapter_engine_run_fields"), list)
                else [],
                "operator_actions": [
                    f"resolve_vina_gnina_case_inputs_for_{case_id}",
                    f"configure_{engine_id}_runtime",
                    f"attach_vina_gnina_adapter_row_for_{case_id}_{engine_id}",
                ],
                "claim_boundary": (
                    "This slot maps one required Vina/GNINA engine run to the "
                    "operator inputs and adapter row fields it must produce. It "
                    "does not prove engine execution or synthesize adapter rows."
                ),
            }
        )
    return rows


def _vina_gnina_case_input_slot_matrix(
    engine_run_slot_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_case: dict[str, dict[str, Any]] = {}
    for slot in engine_run_slot_matrix:
        case_id = str(slot.get("case_id") or "")
        if not case_id or case_id in rows_by_case:
            continue
        case_blockers = [
            str(blocker)
            for blocker in slot.get("blockers", [])
            if str(blocker).endswith("_path_missing")
            or str(blocker).endswith("_checksum_missing")
        ]
        rows_by_case[case_id] = {
            "slot_id": f"{case_id}_case_inputs",
            "case_id": case_id,
            "complex_id": str(slot.get("complex_id") or ""),
            "status": "ready" if bool(slot.get("case_inputs_ready")) else "blocked",
            "case_inputs_ready": bool(slot.get("case_inputs_ready")),
            "input_manifest_template_artifact": str(
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
            "blockers": case_blockers,
            "operator_action": (
                f"review_vina_gnina_case_inputs_for_{case_id}"
                if bool(slot.get("case_inputs_ready"))
                else f"fill_vina_gnina_input_manifest_row_for_{case_id}"
            ),
            "claim_boundary": (
                "This slot maps one CASF/PDBBind case to the local source and "
                "prepared input paths required before Vina/GNINA execution. It "
                "does not prove engine execution or adapter rows."
            ),
        }
    return [rows_by_case[key] for key in sorted(rows_by_case)]


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
    row_candidate_paths = row_candidate_status.get("candidate_paths")
    if not isinstance(row_candidate_paths, list):
        row_candidate_paths = []
    adapter_preflight = row_candidate_status.get("adapter_preflight")
    if not isinstance(adapter_preflight, dict):
        adapter_preflight = {}
    container_runtime_status = payload.get("container_runtime_status")
    if not isinstance(container_runtime_status, dict):
        container_runtime_status = {}
    engine_container_statuses = payload.get("current_engine_container_statuses")
    if not isinstance(engine_container_statuses, list):
        engine_container_statuses = []
    operator_unblock_packet = payload.get("operator_unblock_packet")
    if not isinstance(operator_unblock_packet, dict):
        operator_unblock_packet = {}
    operator_unblock_packet = _compact_vina_gnina_operator_unblock_packet(
        operator_unblock_packet
    )
    engine_run_bundle_summary = _as_dict(payload.get("engine_run_bundle_summary"))
    rows_from_engine_run_bundle_report_summary = _as_dict(
        payload.get("rows_from_engine_run_bundle_report_summary")
    )
    engine_run_slots = payload.get("engine_run_slots")
    if not isinstance(engine_run_slots, list):
        engine_run_slots = []
    engine_run_slot_matrix = _vina_gnina_engine_run_slot_matrix(engine_run_slots)
    case_input_slot_matrix = _vina_gnina_case_input_slot_matrix(
        engine_run_slot_matrix
    )
    blocked_case_input_slot_count = sum(
        1 for row in case_input_slot_matrix if row["status"] != "ready"
    )
    blocked_engine_run_slot_count = sum(
        1 for row in engine_run_slot_matrix if row["status"] != "ready_for_engine_execution"
    )
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
        "row_candidate_status": {
            "status": str(row_candidate_status.get("status") or ""),
            "default_rows_path": str(row_candidate_status.get("default_rows_path") or ""),
            "candidate_paths": [
                {
                    "path": str(row.get("path") or ""),
                    "exists": bool(row.get("exists")),
                    "is_file": bool(row.get("is_file")),
                }
                for row in row_candidate_paths
                if isinstance(row, dict)
            ],
            "detected_row_artifact_count": int(
                row_candidate_status.get("detected_row_artifact_count") or 0
            ),
            "selected_path": str(row_candidate_status.get("selected_path") or ""),
            "selected_row_count": int(
                row_candidate_status.get("selected_row_count") or 0
            ),
            "adapter_case_count": int(
                row_candidate_status.get("adapter_case_count") or 0
            ),
            "adapter_rows_ready": bool(row_candidate_status.get("adapter_rows_ready")),
            "adapter_preflight": {
                "status": str(adapter_preflight.get("status") or ""),
                "contract_pass": bool(adapter_preflight.get("contract_pass")),
                "blocker_count": int(adapter_preflight.get("blocker_count") or 0),
                "first_blocked_target": str(
                    adapter_preflight.get("first_blocked_target") or ""
                ),
                "blockers": [
                    str(row)
                    for row in adapter_preflight.get("blockers", [])
                    if str(row)
                ]
                if isinstance(adapter_preflight.get("blockers"), list)
                else [],
            },
            "load_error": str(row_candidate_status.get("load_error") or ""),
            "blocker": str(row_candidate_status.get("blocker") or ""),
        },
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
        "engine_run_bundle_summary": engine_run_bundle_summary,
        "rows_from_engine_run_bundle_report_summary": (
            rows_from_engine_run_bundle_report_summary
        ),
        "case_input_slot_matrix": case_input_slot_matrix,
        "case_input_slot_matrix_count": len(case_input_slot_matrix),
        "blocked_case_input_slot_count": blocked_case_input_slot_count,
        "engine_run_slot_matrix": engine_run_slot_matrix,
        "engine_run_slot_matrix_count": len(engine_run_slot_matrix),
        "blocked_engine_run_slot_count": blocked_engine_run_slot_count,
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


def _source_access_preflight_rows(
    source_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in source_catalog:
        primary_url = str(source.get("primary_url") or "")
        fallback_url = str(source.get("fallback_url") or "")
        rows.append(
            {
                "source_id": str(source.get("source_id") or ""),
                "source_family": str(source.get("source_family") or ""),
                "access_mode": str(source.get("access_mode") or ""),
                "primary_url": primary_url,
                "fallback_url": fallback_url,
                "primary_head_command": (
                    f"curl --head --location --max-time 20 '{primary_url}'"
                ),
                "fallback_head_command": (
                    f"curl --head --location --max-time 20 '{fallback_url}'"
                ),
                "operator_success_criteria": [
                    "primary_or_fallback_url_resolves",
                    "http_status_is_2xx_3xx_or_documented_auth_gate",
                    "license_or_accession_review_recorded_before_payload_use",
                    "source_checksum_recorded_after_operator_acquisition",
                ],
                "source_payload_policy": dict(SOURCE_ACCESS_PREFLIGHT_POLICY),
                "claim_boundary": (
                    "This preflight checks source access path readiness only. It "
                    "does not download benchmark payloads, grant license rights, "
                    "or count as Phase 2 source evidence."
                ),
            }
        )
    return rows


def _official_source_receipt_plan(
    row_input_contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    receipt_rows = _official_source_receipt_rows(row_input_contracts)
    source_catalog = [dict(row) for row in OFFICIAL_SOURCE_CATALOG]
    source_access_preflight_rows = _source_access_preflight_rows(source_catalog)
    source_access_preflight_receipt_command = (
        "python3 scripts/build_public_benchmark_source_access_preflight_receipt.py "
        f"--out {DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT} "
        f"--out-md {DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT_MD}"
    )
    return {
        "plan_id": "public_benchmark_phase2_official_source_receipt_plan",
        "status": "operator_receipts_required",
        "receipt_role_count": len(receipt_rows),
        "source_catalog_count": len(source_catalog),
        "source_access_preflight_count": len(source_access_preflight_rows),
        "official_source_catalog": source_catalog,
        "source_access_preflight_rows": source_access_preflight_rows,
        "source_access_preflight_policy": dict(SOURCE_ACCESS_PREFLIGHT_POLICY),
        "source_access_preflight_receipt_artifact": str(
            DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT
        ),
        "source_access_preflight_receipt_markdown_artifact": str(
            DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT_MD
        ),
        "source_access_preflight_receipt_command": (
            source_access_preflight_receipt_command
        ),
        "source_access_network_probe_command": (
            f"{source_access_preflight_receipt_command} --probe-network"
        ),
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


def _source_access_preflight_receipt_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT)
    summary = _as_dict(payload.get("summary"))
    probe_rows = [
        row
        for row in payload.get("source_access_probe_rows", [])
        if isinstance(row, dict)
    ] if isinstance(payload.get("source_access_probe_rows"), list) else []
    row_statuses = [
        {
            "source_id": str(row.get("source_id") or ""),
            "source_family": str(row.get("source_family") or ""),
            "status": str(row.get("status") or ""),
            "blockers": [
                str(blocker)
                for blocker in row.get("blockers", [])
                if str(blocker)
            ]
            if isinstance(row.get("blockers"), list)
            else [],
            "primary_http_status": int(
                _as_dict(row.get("primary_probe")).get("http_status") or 0
            ),
            "fallback_http_status": int(
                _as_dict(row.get("fallback_probe")).get("http_status") or 0
            ),
        }
        for row in probe_rows
    ]
    blocked_rows = [
        row for row in row_statuses if row["status"] not in {
            "primary_reachable",
            "fallback_reachable",
        }
    ]
    return {
        "artifact": str(DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT),
        "markdown_artifact": str(DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT_MD),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "contract_pass": bool(payload.get("contract_pass")),
        "network_probe_performed": bool(payload.get("network_probe_performed")),
        "source_access_ready": bool(payload.get("source_access_ready")),
        "source_access_probe_row_count": int(
            summary.get("source_access_probe_row_count") or len(probe_rows)
        ),
        "reachable_count": int(summary.get("reachable_count") or 0),
        "blocked_count": int(summary.get("blocked_count") or len(blocked_rows)),
        "not_run_count": int(summary.get("not_run_count") or 0),
        "blocked_source_ids": [
            str(row["source_id"]) for row in blocked_rows if row["source_id"]
        ],
        "row_statuses": row_statuses,
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _external_receipts_validation_summary(repo_root: Path) -> dict[str, Any]:
    persisted_payload = _load_json(repo_root, DEFAULT_EXTERNAL_RECEIPTS_VALIDATION)
    materialized_artifact_paths = [
        DEFAULT_SUBSET_MANIFEST,
        DEFAULT_ENRICHMENT_SCORECARD,
        DEFAULT_VINA_GNINA_COMPARISON_ADAPTER,
    ]
    resolved_materialized_artifact_paths = [
        path if path.is_absolute() else repo_root / path
        for path in materialized_artifact_paths
    ]
    computed_from_materialized_artifacts = all(
        path.exists() for path in resolved_materialized_artifact_paths
    )
    if computed_from_materialized_artifacts:
        payload = validate_external_receipts(
            subset_manifest=_load_json(repo_root, DEFAULT_SUBSET_MANIFEST),
            enrichment_scorecard=_load_json(repo_root, DEFAULT_ENRICHMENT_SCORECARD),
            vina_gnina_comparison_adapter=_load_json(
                repo_root,
                DEFAULT_VINA_GNINA_COMPARISON_ADAPTER,
            ),
        )
    else:
        payload = persisted_payload
    receipt_coverage = _as_dict(payload.get("receipt_coverage"))
    role_summaries = [
        {
            "artifact_role": str(row.get("artifact_role") or ""),
            "materialized_row_count": _as_int(row.get("materialized_row_count")),
            "receipt_complete_row_count": _as_int(
                row.get("receipt_complete_row_count")
            ),
            "receipt_blocked_row_count": _as_int(
                row.get("receipt_blocked_row_count")
            ),
            "required_receipt_fields": [
                str(field)
                for field in _as_list(row.get("required_receipt_fields"))
                if str(field)
            ],
            "blocker_count": _as_int(row.get("blocker_count")),
            "blockers": [
                str(blocker)
                for blocker in _as_list(row.get("blockers"))
                if str(blocker)
            ],
        }
        for row in _as_list(receipt_coverage.get("role_summaries"))
        if isinstance(row, dict)
    ]
    blockers = [
        str(blocker)
        for blocker in _as_list(payload.get("blockers"))
        if str(blocker)
    ]
    if not payload:
        blockers = ["public_benchmark_external_receipts_validation_missing"]
    return {
        "artifact": str(DEFAULT_EXTERNAL_RECEIPTS_VALIDATION),
        "present": bool(persisted_payload),
        "computed_from_materialized_artifacts": computed_from_materialized_artifacts,
        "persisted_artifact_status": str(
            persisted_payload.get("status") or "missing"
        ),
        "persisted_artifact_materialized_row_count": _as_int(
            persisted_payload.get("materialized_row_count")
        ),
        "materialized_artifact_inputs": [
            str(path) for path in materialized_artifact_paths
        ],
        "status": str(payload.get("status") or "missing"),
        "contract_pass": payload.get("contract_pass"),
        "public_benchmark_external_receipts_ready": bool(
            payload.get("public_benchmark_external_receipts_ready")
        ),
        "materialized_row_count": _as_int(payload.get("materialized_row_count")),
        "receipt_complete_row_count": _as_int(
            payload.get("receipt_complete_row_count")
        ),
        "receipt_blocked_row_count": _as_int(
            payload.get("receipt_blocked_row_count")
        ),
        "expected_artifact_role_count": _as_int(
            receipt_coverage.get("expected_artifact_role_count")
        ),
        "materialized_artifact_role_count": _as_int(
            receipt_coverage.get("materialized_artifact_role_count")
        ),
        "receipt_complete_artifact_role_count": _as_int(
            receipt_coverage.get("receipt_complete_artifact_role_count")
        ),
        "missing_expected_artifact_role_count": _as_int(
            receipt_coverage.get("missing_expected_artifact_role_count")
        ),
        "missing_expected_artifact_roles": [
            str(role)
            for role in _as_list(
                receipt_coverage.get("missing_expected_artifact_roles")
            )
            if str(role)
        ],
        "role_summaries": role_summaries,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "command": (
            "python3 scripts/validate_public_benchmark_external_receipts.py "
            "--subset-manifest "
            f"{DEFAULT_SUBSET_MANIFEST} "
            "--enrichment-scorecard "
            f"{DEFAULT_ENRICHMENT_SCORECARD} "
            "--vina-gnina-comparison-adapter "
            f"{DEFAULT_VINA_GNINA_COMPARISON_ADAPTER} "
            f"--out {DEFAULT_EXTERNAL_RECEIPTS_VALIDATION}"
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _external_receipt_completion_audit(
    *,
    official_source_receipt_plan: dict[str, Any],
    source_access_preflight_receipt_summary: dict[str, Any],
    external_receipts_validation_summary: dict[str, Any],
    phase2_row_audit_summary: dict[str, Any],
    phase2_row_closure_matrix: list[dict[str, Any]],
    vina_gnina_execution_plan_summary: dict[str, Any],
    vina_gnina_runtime_readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    source_catalog = [
        row
        for row in _as_list(official_source_receipt_plan.get("official_source_catalog"))
        if isinstance(row, dict)
    ]
    receipt_roles = [
        row
        for row in _as_list(official_source_receipt_plan.get("row_input_receipt_roles"))
        if isinstance(row, dict)
    ]
    source_status_by_id = {
        str(row.get("source_id") or ""): row
        for row in _as_list(source_access_preflight_receipt_summary.get("row_statuses"))
        if isinstance(row, dict)
    }
    closure_by_row_input = {
        str(row.get("row_input_id") or ""): row
        for row in phase2_row_closure_matrix
        if isinstance(row, dict)
    }
    role_summary_by_artifact = {
        str(row.get("artifact_role") or ""): row
        for row in _as_list(external_receipts_validation_summary.get("role_summaries"))
        if isinstance(row, dict)
    }
    artifact_role_by_row_input = {
        "subset_rows": "casf_pdbbind_subset_manifest",
        "enrichment_rows": "dud_e_lit_pcba_enrichment_scorecard",
        "vina_gnina_rows": "vina_gnina_comparison_adapter",
    }
    missing_row_inputs = {
        str(row)
        for row in phase2_row_audit_summary.get("missing_row_inputs", [])
        if str(row)
    }
    provided_row_inputs = {
        str(row)
        for row in phase2_row_audit_summary.get(
            "source_actuality_provided_row_inputs", []
        )
        if str(row)
    }
    rows: list[dict[str, Any]] = []
    for role in receipt_roles:
        row_input_id = str(role.get("row_input_id") or "")
        source_ids = [
            str(source.get("source_id") or "")
            for source in source_catalog
            if row_input_id in _as_list(source.get("feeds_row_inputs"))
        ]
        source_access_rows = [
            {
                "source_id": source_id,
                "status": str(source_status_by_id.get(source_id, {}).get("status") or ""),
                "primary_http_status": _as_int(
                    source_status_by_id.get(source_id, {}).get("primary_http_status")
                ),
                "fallback_http_status": _as_int(
                    source_status_by_id.get(source_id, {}).get("fallback_http_status")
                ),
                "blockers": [
                    str(blocker)
                    for blocker in _as_list(
                        source_status_by_id.get(source_id, {}).get("blockers")
                    )
                    if str(blocker)
                ],
            }
            for source_id in source_ids
        ]
        source_access_ready = bool(source_access_rows) and all(
            row["status"] in {"primary_reachable", "fallback_reachable"}
            for row in source_access_rows
        )
        closure = closure_by_row_input.get(row_input_id, {})
        row_input_status = str(closure.get("status") or "")
        if not row_input_status:
            row_input_status = (
                "missing" if row_input_id in missing_row_inputs else "provided"
            )
        artifact_role = artifact_role_by_row_input.get(row_input_id, "")
        artifact_role_summary = role_summary_by_artifact.get(artifact_role, {})
        artifact_receipts_complete = bool(
            artifact_role
            and _as_int(artifact_role_summary.get("materialized_row_count")) > 0
            and _as_int(artifact_role_summary.get("receipt_blocked_row_count")) == 0
        )
        row_source_actuality_ready = row_input_id in provided_row_inputs and int(
            phase2_row_audit_summary.get("source_actuality_blocker_count") or 0
        ) == 0
        blockers: list[str] = []
        if not source_access_ready:
            blockers.append("source_access_preflight_not_ready")
        if row_input_id in missing_row_inputs:
            blockers.append(f"{row_input_id}_not_provided")
        if artifact_role:
            if not artifact_receipts_complete:
                blockers.append(
                    f"public_benchmark_external_receipt_role_missing:{artifact_role}"
                )
        elif not row_source_actuality_ready:
            blockers.append(f"{row_input_id}_source_actuality_not_ready")
        if row_input_id == "vina_gnina_rows":
            if not vina_gnina_execution_plan_summary.get("input_manifest_detected"):
                blockers.append(
                    "public_benchmark_vina_gnina_input_manifest_not_detected"
                )
            if not vina_gnina_runtime_readiness_summary.get(
                "runtime_ready_for_engine_execution"
            ):
                blockers.append(
                    "public_benchmark_vina_gnina_engine_runtime_not_ready"
                )
        rows.append(
            {
                "row_input_id": row_input_id,
                "receipt_role_id": str(role.get("receipt_role_id") or ""),
                "status": "ready" if not blockers else "operator_receipt_required",
                "source_family": str(role.get("source_family") or ""),
                "row_input_status": row_input_status,
                "row_input_resolved_path": str(closure.get("resolved_path") or ""),
                "source_ids": source_ids,
                "source_access_ready": source_access_ready,
                "source_access_rows": source_access_rows,
                "validator_artifact_role": artifact_role,
                "validator_artifact_role_summary": artifact_role_summary,
                "artifact_receipts_complete": artifact_receipts_complete,
                "row_source_actuality_ready": row_source_actuality_ready,
                "required_receipt_fields": [
                    str(field)
                    for field in _as_list(role.get("required_receipt_fields"))
                    if str(field)
                ],
                "operator_must_attach": [
                    str(item)
                    for item in _as_list(role.get("operator_must_attach"))
                    if str(item)
                ],
                "blockers": blockers,
                "claim_boundary": (
                    "This row ties official source access, row-input presence, "
                    "and receipt validation coverage to one receipt role. It "
                    "does not approve licenses or replace the row materializers."
                ),
            }
        )
    ready_rows = [row for row in rows if row["status"] == "ready"]
    blocked_rows = [row for row in rows if row["status"] != "ready"]
    all_expected_artifact_roles_complete = (
        external_receipts_validation_summary["expected_artifact_role_count"] > 0
        and external_receipts_validation_summary[
            "receipt_complete_artifact_role_count"
        ]
        == external_receipts_validation_summary["expected_artifact_role_count"]
        and external_receipts_validation_summary[
            "missing_expected_artifact_role_count"
        ]
        == 0
    )
    status = "ready" if not blocked_rows and all_expected_artifact_roles_complete else (
        "blocked_pending_vina_gnina_receipts"
        if external_receipts_validation_summary["missing_expected_artifact_roles"]
        == ["vina_gnina_comparison_adapter"]
        else "operator_external_receipts_required"
    )
    return {
        "status": status,
        "pass": status == "ready",
        "source_access_ready": bool(
            source_access_preflight_receipt_summary.get("source_access_ready")
        ),
        "source_access_reachable_count": _as_int(
            source_access_preflight_receipt_summary.get("reachable_count")
        ),
        "external_receipts_validation_artifact": str(
            DEFAULT_EXTERNAL_RECEIPTS_VALIDATION
        ),
        "external_receipts_validation_status": str(
            external_receipts_validation_summary.get("status") or ""
        ),
        "external_receipts_ready_for_materialized_rows": bool(
            external_receipts_validation_summary.get(
                "public_benchmark_external_receipts_ready"
            )
        ),
        "all_expected_artifact_roles_complete": (
            all_expected_artifact_roles_complete
        ),
        "expected_artifact_role_count": external_receipts_validation_summary[
            "expected_artifact_role_count"
        ],
        "receipt_complete_artifact_role_count": (
            external_receipts_validation_summary[
                "receipt_complete_artifact_role_count"
            ]
        ),
        "missing_expected_artifact_role_count": (
            external_receipts_validation_summary[
                "missing_expected_artifact_role_count"
            ]
        ),
        "missing_expected_artifact_roles": external_receipts_validation_summary[
            "missing_expected_artifact_roles"
        ],
        "official_receipt_role_count": len(rows),
        "ready_official_receipt_role_count": len(ready_rows),
        "blocked_official_receipt_role_count": len(blocked_rows),
        "blocked_receipt_role_ids": [
            str(row["receipt_role_id"]) for row in blocked_rows
        ],
        "remaining_row_inputs": sorted(missing_row_inputs),
        "remaining_blockers": [
            str(blocker)
            for row in blocked_rows
            for blocker in row.get("blockers", [])
            if str(blocker)
        ],
        "operator_action": (
            "attach_vina_gnina_rows_and_receipts_then_refresh_external_receipts"
            if status == "blocked_pending_vina_gnina_receipts"
            else "attach_external_source_receipts_and_license_or_accession_refs"
        ),
        "receipt_roles": rows,
        "claim_boundary": (
            "This audit distinguishes source-access reachability from official "
            "receipt completion. It can show materialized-row receipts that are "
            "valid while still blocking full Phase 2 until every expected "
            "artifact role, especially Vina/GNINA, is present."
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


def _vina_gnina_runtime_action_packet(
    vina_gnina_runtime_readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    unblock = _as_dict(
        vina_gnina_runtime_readiness_summary.get("operator_unblock_packet")
    )
    commands = _as_dict(unblock.get("commands"))
    if not vina_gnina_runtime_readiness_summary and not unblock:
        return {}
    preflight_summary = _as_dict(
        unblock.get("input_manifest_template_preflight_summary")
        or vina_gnina_runtime_readiness_summary.get(
            "input_manifest_template_preflight"
        )
    )
    input_manifest_completion_action_plan = [
        row
        for row in _as_list(
            unblock.get("input_manifest_completion_action_plan")
            or preflight_summary.get("input_manifest_completion_action_plan")
        )
        if isinstance(row, dict)
    ]
    operator_blocker_family_plan = [
        _compact_operator_blocker_family(row, commands=commands)
        for row in _as_list(
            unblock.get("operator_blocker_family_plan")
            or vina_gnina_runtime_readiness_summary.get(
                "operator_blocker_family_plan"
            )
        )
        if isinstance(row, dict)
    ]
    operator_blocker_family_blocked_count = _as_int(
        unblock.get("operator_blocker_family_blocked_count")
        or vina_gnina_runtime_readiness_summary.get(
            "operator_blocker_family_blocked_count"
        )
    )
    if not operator_blocker_family_blocked_count and operator_blocker_family_plan:
        operator_blocker_family_blocked_count = sum(
            1
            for row in operator_blocker_family_plan
            if str(row.get("status") or "") != "ready"
        )
    operator_blocker_family_missing_item_count = _as_int(
        unblock.get("operator_blocker_family_missing_item_count")
        or vina_gnina_runtime_readiness_summary.get(
            "operator_blocker_family_missing_item_count"
        )
    )
    if not operator_blocker_family_missing_item_count:
        operator_blocker_family_missing_item_count = sum(
            _as_int(row.get("missing_item_count"))
            for row in operator_blocker_family_plan
            if str(row.get("status") or "") != "ready"
        )
    first_operator_blocker_family = _compact_operator_blocker_family(
        _as_dict(
            unblock.get("first_operator_blocker_family")
            or vina_gnina_runtime_readiness_summary.get(
                "first_operator_blocker_family"
            )
        ),
        commands=commands,
    )
    if not first_operator_blocker_family and operator_blocker_family_plan:
        first_operator_blocker_family = next(
            (
                row
                for row in operator_blocker_family_plan
                if str(row.get("status") or "") != "ready"
            ),
            {},
        )
    return {
        "artifact": str(
            vina_gnina_runtime_readiness_summary.get("artifact") or ""
        ),
        "status": str(
            unblock.get("status")
            or vina_gnina_runtime_readiness_summary.get("status")
            or ""
        ),
        "runtime_ready_for_engine_execution": bool(
            vina_gnina_runtime_readiness_summary.get(
                "runtime_ready_for_engine_execution"
            )
        ),
        "operator_execution_ready": bool(
            vina_gnina_runtime_readiness_summary.get("operator_execution_ready")
        ),
        "adapter_rows_ready": bool(
            vina_gnina_runtime_readiness_summary.get("adapter_rows_ready")
        ),
        "case_input_slot_count": _as_int(
            unblock.get("case_input_slot_count")
            or vina_gnina_runtime_readiness_summary.get(
                "case_input_slot_matrix_count"
            )
        ),
        "blocked_case_input_slot_count": _as_int(
            unblock.get("blocked_case_input_slot_count")
            or vina_gnina_runtime_readiness_summary.get(
                "blocked_case_input_slot_count"
            )
        ),
        "first_blocked_case_input_slot": _as_dict(
            unblock.get("first_blocked_case_input_slot")
            or vina_gnina_runtime_readiness_summary.get(
                "first_blocked_case_input_slot"
            )
        ),
        "required_engine_run_count": _as_int(
            unblock.get("required_engine_run_count")
            or vina_gnina_runtime_readiness_summary.get(
                "required_engine_run_count"
            )
        ),
        "ready_engine_run_slot_count": _as_int(
            unblock.get("ready_engine_run_slot_count")
            or vina_gnina_runtime_readiness_summary.get(
                "ready_engine_run_slot_count"
            )
        ),
        "blocked_engine_run_slot_count": _as_int(
            unblock.get("blocked_engine_run_slot_count")
            or vina_gnina_runtime_readiness_summary.get(
                "blocked_engine_run_slot_count"
            )
        ),
        "first_blocked_engine_run_slot": _as_dict(
            unblock.get("first_blocked_engine_run_slot")
            or vina_gnina_runtime_readiness_summary.get(
                "first_blocked_engine_run_slot"
            )
        ),
        "operator_blocker_family_plan": operator_blocker_family_plan,
        "operator_blocker_family_count": len(operator_blocker_family_plan),
        "operator_blocker_family_blocked_count": (
            operator_blocker_family_blocked_count
        ),
        "operator_blocker_family_missing_item_count": (
            operator_blocker_family_missing_item_count
        ),
        "first_operator_blocker_family": first_operator_blocker_family,
        "expected_rows_artifact": str(
            unblock.get("expected_rows_artifact") or DEFAULT_VINA_GNINA_ROWS
        ),
        "engine_run_bundle_summary": _as_dict(
            unblock.get("engine_run_bundle_summary")
            or vina_gnina_runtime_readiness_summary.get("engine_run_bundle_summary")
        ),
        "engine_run_bundle_status": str(
            unblock.get("engine_run_bundle_status")
            or _as_dict(
                vina_gnina_runtime_readiness_summary.get("engine_run_bundle_summary")
            ).get("status")
            or ""
        ),
        "engine_run_bundle_materialized": bool(
            unblock.get("engine_run_bundle_materialized")
            or _as_dict(
                vina_gnina_runtime_readiness_summary.get("engine_run_bundle_summary")
            ).get("bundle_materialized")
        ),
        "rows_from_engine_run_bundle_report_summary": _as_dict(
            unblock.get("rows_from_engine_run_bundle_report_summary")
            or vina_gnina_runtime_readiness_summary.get(
                "rows_from_engine_run_bundle_report_summary"
            )
        ),
        "rows_from_engine_run_bundle_status": str(
            unblock.get("rows_from_engine_run_bundle_status")
            or _as_dict(
                vina_gnina_runtime_readiness_summary.get(
                    "rows_from_engine_run_bundle_report_summary"
                )
            ).get("status")
            or ""
        ),
        "rows_from_engine_run_bundle_materialized": bool(
            unblock.get("rows_from_engine_run_bundle_materialized")
            or _as_dict(
                vina_gnina_runtime_readiness_summary.get(
                    "rows_from_engine_run_bundle_report_summary"
                )
            ).get("rows_materialized")
        ),
        "input_manifest_template_artifact": str(
            unblock.get("input_manifest_template_artifact")
            or DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE
        ),
        "input_manifest_template_preflight_artifact": str(
            unblock.get("input_manifest_template_preflight_artifact") or ""
        ),
        "input_manifest_template_preflight_status": str(
            unblock.get("input_manifest_template_preflight_status")
            or vina_gnina_runtime_readiness_summary.get(
                "input_manifest_template_preflight_status"
            )
            or ""
        ),
        "input_manifest_template_manifest_ready": bool(
            unblock.get("input_manifest_template_manifest_ready")
            or vina_gnina_runtime_readiness_summary.get(
                "input_manifest_template_manifest_ready"
            )
        ),
        "input_manifest_template_preflight_summary": _as_dict(
            unblock.get("input_manifest_template_preflight_summary")
            or vina_gnina_runtime_readiness_summary.get(
                "input_manifest_template_preflight"
            )
        ),
        "input_manifest_completion_action_case_count": _as_int(
            unblock.get("input_manifest_completion_action_case_count")
            or preflight_summary.get("input_manifest_completion_action_case_count")
            or len(input_manifest_completion_action_plan)
        ),
        "input_manifest_completion_blocked_case_count": _as_int(
            unblock.get("input_manifest_completion_blocked_case_count")
            or preflight_summary.get("input_manifest_completion_blocked_case_count")
            or len(input_manifest_completion_action_plan)
        ),
        "input_manifest_completion_action_plan": (
            input_manifest_completion_action_plan
        ),
        "rows_template_artifact": str(
            unblock.get("rows_template_artifact")
            or DEFAULT_VINA_GNINA_ROWS_TEMPLATE
        ),
        "rows_template_preflight_artifact": str(
            unblock.get("rows_template_preflight_artifact") or ""
        ),
        "operator_sequence": [
            str(row) for row in _as_list(unblock.get("operator_sequence")) if str(row)
        ],
        "commands": commands,
        "claim_boundary": (
            "This packet mirrors the Vina/GNINA runtime unblock path for the "
            "missing source-acquisition action. It does not run engines or "
            "synthesize comparison rows."
        ),
    }


def _first_blocked_row(rows: list[Any]) -> dict[str, Any]:
    for row in rows:
        if isinstance(row, dict) and row.get("status") != "ready":
            return row
    return {}


def _vina_gnina_rows_template_preflight_summary(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT)
    if not payload:
        return {
            "present": False,
            "artifact": str(DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT),
            "markdown_artifact": str(DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD),
            "status": "missing",
            "adapter_template_ready": False,
            "expected_rows_detected": False,
            "template_row_count": 0,
            "expected_engine_run_slot_count": 0,
            "missing_engine_run_receipt_value_count": 0,
            "missing_local_ref_count": 0,
            "missing_numeric_value_count": 0,
            "invalid_pose_success_count": 0,
            "role_receipt_plan_count": 0,
            "role_receipt_blocked_count": 0,
            "first_blocked_role_receipt": {},
        }
    role_receipt_plan = [
        row for row in payload.get("role_receipt_plan", []) if isinstance(row, dict)
    ]
    summary = _as_dict(payload.get("summary"))
    return {
        "present": True,
        "artifact": str(DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT),
        "markdown_artifact": str(DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD),
        "status": str(payload.get("status") or ""),
        "adapter_template_ready": bool(payload.get("adapter_template_ready")),
        "expected_rows_detected": bool(payload.get("expected_rows_detected")),
        "template_row_count": _as_int(summary.get("template_row_count")),
        "expected_engine_run_slot_count": _as_int(
            summary.get("expected_engine_run_slot_count")
        ),
        "missing_engine_run_receipt_value_count": _as_int(
            summary.get("missing_engine_run_receipt_value_count")
        ),
        "missing_local_ref_count": _as_int(summary.get("missing_local_ref_count")),
        "missing_numeric_value_count": _as_int(
            summary.get("missing_numeric_value_count")
        ),
        "invalid_pose_success_count": _as_int(
            summary.get("invalid_pose_success_count")
        ),
        "role_receipt_plan_count": _as_int(
            summary.get("role_receipt_plan_count") or len(role_receipt_plan)
        ),
        "role_receipt_blocked_count": _as_int(
            summary.get("role_receipt_blocked_count")
            or sum(1 for row in role_receipt_plan if row.get("status") != "ready")
        ),
        "first_blocked_role_receipt": _first_blocked_row(role_receipt_plan),
    }


def _vina_gnina_actual_evidence_audit(
    *,
    phase2_row_audit_summary: dict[str, Any],
    vina_gnina_execution_plan_summary: dict[str, Any],
    vina_gnina_runtime_readiness_summary: dict[str, Any],
    vina_gnina_rows_template_preflight_summary: dict[str, Any],
    external_receipt_completion_audit: dict[str, Any],
) -> dict[str, Any]:
    runtime_unblock = _as_dict(
        vina_gnina_runtime_readiness_summary.get("operator_unblock_packet")
    )
    input_manifest_preflight = _as_dict(
        runtime_unblock.get("input_manifest_template_preflight_summary")
    )
    row_candidate_status = _as_dict(
        vina_gnina_runtime_readiness_summary.get("row_candidate_status")
    )
    adapter_preflight = _as_dict(row_candidate_status.get("adapter_preflight"))
    required_case_count = _as_int(vina_gnina_runtime_readiness_summary.get("case_count"))
    required_engine_run_count = _as_int(
        vina_gnina_runtime_readiness_summary.get("required_engine_run_count")
    )
    if required_engine_run_count == 0:
        required_engine_run_count = _as_int(
            vina_gnina_execution_plan_summary.get("required_engine_run_count")
        )
    minimum_comparison_case_count = 1
    input_manifest_detected = bool(
        vina_gnina_execution_plan_summary.get("input_manifest_detected")
    )
    input_manifest_row_count = _as_int(
        vina_gnina_execution_plan_summary.get("input_manifest_row_count")
    )
    blocked_case_input_slot_count = _as_int(
        vina_gnina_runtime_readiness_summary.get("blocked_case_input_slot_count")
    )
    case_input_slot_count = _as_int(
        vina_gnina_runtime_readiness_summary.get("case_input_slot_matrix_count")
    )
    verified_case_input_count = max(
        0,
        case_input_slot_count - blocked_case_input_slot_count,
    )
    input_manifest_syntax_ready = (
        input_manifest_detected and input_manifest_row_count >= required_case_count
    )
    input_manifest_template_ready = bool(
        input_manifest_preflight.get("manifest_ready")
    )
    input_manifest_ready = (
        input_manifest_syntax_ready
        and input_manifest_template_ready
        and blocked_case_input_slot_count == 0
    )
    if input_manifest_ready:
        input_manifest_verification_status = "case_inputs_verified"
    elif input_manifest_syntax_ready:
        input_manifest_verification_status = (
            "syntactic_manifest_detected_but_case_inputs_unverified"
        )
    else:
        input_manifest_verification_status = (
            "input_manifest_missing_or_case_coverage_incomplete"
        )
    runtime_ready = bool(
        vina_gnina_runtime_readiness_summary.get(
            "runtime_ready_for_engine_execution"
        )
    )
    engine_slots_ready = (
        required_engine_run_count > 0
        and _as_int(
            vina_gnina_runtime_readiness_summary.get("ready_engine_run_slot_count")
        )
        >= required_engine_run_count
        and _as_int(
            vina_gnina_runtime_readiness_summary.get("blocked_engine_run_slot_count")
        )
        == 0
    )
    adapter_rows_ready = (
        bool(vina_gnina_runtime_readiness_summary.get("adapter_rows_ready"))
        and _as_int(vina_gnina_runtime_readiness_summary.get("adapter_case_count"))
        >= minimum_comparison_case_count
        and bool(adapter_preflight.get("contract_pass"))
    )
    row_receipts_ready = (
        bool(vina_gnina_rows_template_preflight_summary.get("expected_rows_detected"))
        and bool(
            vina_gnina_rows_template_preflight_summary.get("adapter_template_ready")
        )
        and _as_int(
            vina_gnina_rows_template_preflight_summary.get(
                "role_receipt_blocked_count"
            )
        )
        == 0
    )
    external_receipts_ready = bool(
        external_receipt_completion_audit.get("all_expected_artifact_roles_complete")
    )
    missing_row_inputs = [
        str(row)
        for row in phase2_row_audit_summary.get("missing_row_inputs", [])
        if str(row)
    ]
    external_receipt_blockers = [
        str(blocker)
        for blocker in external_receipt_completion_audit.get(
            "remaining_blockers", []
        )
        if str(blocker)
    ]
    components = [
        {
            "component_id": "engine_input_manifest",
            "status": "ready" if input_manifest_ready else "blocked",
            "pass": input_manifest_ready,
            "current": {
                "input_manifest_status": str(
                    vina_gnina_execution_plan_summary.get("input_manifest_status")
                    or ""
                ),
                "input_manifest_detected": input_manifest_detected,
                "input_manifest_row_count": input_manifest_row_count,
                "input_manifest_syntax_ready": input_manifest_syntax_ready,
                "input_manifest_verification_status": (
                    input_manifest_verification_status
                ),
                "required_case_count": required_case_count,
                "case_input_slot_count": case_input_slot_count,
                "verified_case_input_count": verified_case_input_count,
                "blocked_case_input_slot_count": blocked_case_input_slot_count,
                "template_preflight_status": str(
                    input_manifest_preflight.get("status") or ""
                ),
                "template_manifest_ready": input_manifest_template_ready,
                "template_missing_local_file_count": _as_int(
                    input_manifest_preflight.get("missing_local_file_count")
                ),
                "template_missing_receipt_ref_count": _as_int(
                    input_manifest_preflight.get("missing_receipt_ref_count")
                ),
                "template_completion_blocked_case_count": _as_int(
                    input_manifest_preflight.get(
                        "input_manifest_completion_blocked_case_count"
                    )
                ),
            },
            "required": {
                "input_manifest_detected": True,
                "input_manifest_row_count": f">={required_case_count}",
                "input_manifest_syntax_ready": True,
                "template_manifest_ready": True,
                "verified_case_input_count": f">={required_case_count}",
                "blocked_case_input_slot_count": 0,
            },
            "blockers": list(
                dict.fromkeys(
                    [
                        *[
                            str(row)
                            for row in vina_gnina_execution_plan_summary.get(
                                "input_manifest_blockers", []
                            )
                            if str(row)
                        ],
                        *(
                            ["public_benchmark_vina_gnina_case_inputs_incomplete"]
                            if not input_manifest_ready
                            else []
                        ),
                        *(
                            [
                                "public_benchmark_vina_gnina_input_manifest_template_completion_required"
                            ]
                            if input_manifest_syntax_ready
                            and not input_manifest_template_ready
                            else []
                        ),
                        *(
                            [
                                "public_benchmark_vina_gnina_case_input_files_or_receipts_unverified"
                            ]
                            if blocked_case_input_slot_count > 0
                            else []
                        ),
                    ]
                )
            ),
        },
        {
            "component_id": "engine_runtime",
            "status": "ready" if runtime_ready else "blocked",
            "pass": runtime_ready,
            "current": {
                "runtime_status": str(
                    vina_gnina_runtime_readiness_summary.get("status") or ""
                ),
                "runtime_ready_for_engine_execution": runtime_ready,
                "available_engine_count": _as_int(
                    vina_gnina_runtime_readiness_summary.get(
                        "available_engine_count"
                    )
                ),
                "missing_engine_count": _as_int(
                    vina_gnina_runtime_readiness_summary.get("missing_engine_count")
                ),
                "missing_engine_ids": [
                    str(row)
                    for row in vina_gnina_runtime_readiness_summary.get(
                        "missing_engine_ids", []
                    )
                    if str(row)
                ],
            },
            "required": {
                "runtime_ready_for_engine_execution": True,
                "missing_engine_count": 0,
            },
            "blockers": [
                str(row)
                for row in vina_gnina_runtime_readiness_summary.get("blockers", [])
                if "::" not in str(row)
                and (
                    str(row).endswith("_binary_missing")
                    or "container_image" in str(row)
                    or str(row) == "vina_gnina_execution_plan_not_ready"
                )
            ],
        },
        {
            "component_id": "engine_run_slots",
            "status": "ready" if engine_slots_ready else "blocked",
            "pass": engine_slots_ready,
            "current": {
                "ready_engine_run_slot_count": _as_int(
                    vina_gnina_runtime_readiness_summary.get(
                        "ready_engine_run_slot_count"
                    )
                ),
                "required_engine_run_count": required_engine_run_count,
                "blocked_engine_run_slot_count": _as_int(
                    vina_gnina_runtime_readiness_summary.get(
                        "blocked_engine_run_slot_count"
                    )
                ),
            },
            "required": {
                "ready_engine_run_slot_count": required_engine_run_count,
                "blocked_engine_run_slot_count": 0,
            },
            "blockers": (
                []
                if engine_slots_ready
                else ["public_benchmark_vina_gnina_engine_run_slots_incomplete"]
            ),
        },
        {
            "component_id": "adapter_rows",
            "status": "ready" if adapter_rows_ready else "blocked",
            "pass": adapter_rows_ready,
            "current": {
                "row_candidate_status": str(row_candidate_status.get("status") or ""),
                "detected_row_artifact_count": _as_int(
                    row_candidate_status.get("detected_row_artifact_count")
                ),
                "selected_row_count": _as_int(
                    row_candidate_status.get("selected_row_count")
                ),
                "adapter_case_count": _as_int(
                    vina_gnina_runtime_readiness_summary.get("adapter_case_count")
                ),
                "adapter_rows_ready": bool(
                    vina_gnina_runtime_readiness_summary.get("adapter_rows_ready")
                ),
                "adapter_preflight_status": str(
                    adapter_preflight.get("status") or ""
                ),
                "adapter_preflight_contract_pass": bool(
                    adapter_preflight.get("contract_pass")
                ),
            },
            "required": {
                "detected_row_artifact_count": ">=1",
                "adapter_case_count": f">={minimum_comparison_case_count}",
                "adapter_preflight_contract_pass": True,
            },
            "blockers": list(
                dict.fromkeys(
                    [
                        str(row_candidate_status.get("blocker") or ""),
                        *[
                            str(row)
                            for row in adapter_preflight.get("blockers", [])
                            if str(row)
                        ],
                        *(
                            ["vina_gnina_rows_not_provided"]
                            if "vina_gnina_rows" in missing_row_inputs
                            else []
                        ),
                    ]
                )
            ),
        },
        {
            "component_id": "per_engine_run_receipts",
            "status": "ready" if row_receipts_ready else "blocked",
            "pass": row_receipts_ready,
            "current": {
                "rows_template_preflight_status": str(
                    vina_gnina_rows_template_preflight_summary.get("status") or ""
                ),
                "expected_rows_detected": bool(
                    vina_gnina_rows_template_preflight_summary.get(
                        "expected_rows_detected"
                    )
                ),
                "adapter_template_ready": bool(
                    vina_gnina_rows_template_preflight_summary.get(
                        "adapter_template_ready"
                    )
                ),
                "role_receipt_plan_count": _as_int(
                    vina_gnina_rows_template_preflight_summary.get(
                        "role_receipt_plan_count"
                    )
                ),
                "role_receipt_blocked_count": _as_int(
                    vina_gnina_rows_template_preflight_summary.get(
                        "role_receipt_blocked_count"
                    )
                ),
                "missing_engine_run_receipt_value_count": _as_int(
                    vina_gnina_rows_template_preflight_summary.get(
                        "missing_engine_run_receipt_value_count"
                    )
                ),
            },
            "required": {
                "expected_rows_detected": True,
                "adapter_template_ready": True,
                "role_receipt_blocked_count": 0,
            },
            "blockers": (
                []
                if row_receipts_ready
                else ["public_benchmark_vina_gnina_engine_run_receipts_incomplete"]
            ),
        },
        {
            "component_id": "external_receipts",
            "status": "ready" if external_receipts_ready else "blocked",
            "pass": external_receipts_ready,
            "current": {
                "external_receipt_completion_status": str(
                    external_receipt_completion_audit.get("status") or ""
                ),
                "all_expected_artifact_roles_complete": external_receipts_ready,
                "missing_expected_artifact_roles": [
                    str(role)
                    for role in external_receipt_completion_audit.get(
                        "missing_expected_artifact_roles", []
                    )
                    if str(role)
                ],
                "blocked_official_receipt_role_count": _as_int(
                    external_receipt_completion_audit.get(
                        "blocked_official_receipt_role_count"
                    )
                ),
            },
            "required": {
                "all_expected_artifact_roles_complete": True,
                "blocked_official_receipt_role_count": 0,
            },
            "blockers": external_receipt_blockers,
        },
    ]
    components = [
        {
            **row,
            "blockers": list(
                dict.fromkeys(
                    str(blocker)
                    for blocker in row.get("blockers", [])
                    if str(blocker)
                )
            ),
        }
        for row in components
    ]
    blocked_components = [row for row in components if not bool(row["pass"])]
    if not blocked_components:
        status = "ready"
    elif not input_manifest_ready:
        status = "engine_input_manifest_required"
    elif not runtime_ready:
        status = "engine_runtime_required"
    elif not adapter_rows_ready:
        status = "adapter_rows_required"
    elif not row_receipts_ready or not external_receipts_ready:
        status = "external_receipts_required"
    else:
        status = "operator_evidence_required"
    remaining_blockers = list(
        dict.fromkeys(
            str(blocker)
            for row in blocked_components
            for blocker in row.get("blockers", [])
            if str(blocker)
        )
    )
    operator_blocker_family_plan = [
        row
        for row in _as_list(runtime_unblock.get("operator_blocker_family_plan"))
        if isinstance(row, dict)
    ]
    blocked_operator_blocker_families = [
        row
        for row in operator_blocker_family_plan
        if str(row.get("status") or "") != "ready"
    ]
    operator_blocker_family_missing_item_count = sum(
        _as_int(row.get("missing_item_count"))
        for row in blocked_operator_blocker_families
    )
    return {
        "status": status,
        "pass": not blocked_components,
        "actual_closure_ready": not blocked_components,
        "component_count": len(components),
        "ready_component_count": len(components) - len(blocked_components),
        "blocked_component_count": len(blocked_components),
        "blocked_component_ids": [
            str(row["component_id"]) for row in blocked_components
        ],
        "remaining_blockers": remaining_blockers,
        "remaining_evidence": [
            str(row["component_id"]) for row in blocked_components
        ],
        "required_case_count": required_case_count,
        "required_engine_run_count": required_engine_run_count,
        "minimum_comparison_case_count": minimum_comparison_case_count,
        "operator_blocker_family_count": len(operator_blocker_family_plan),
        "operator_blocker_family_blocked_count": len(
            blocked_operator_blocker_families
        ),
        "operator_blocker_family_missing_item_count": (
            operator_blocker_family_missing_item_count
        ),
        "first_operator_blocker_family": (
            blocked_operator_blocker_families[0]
            if blocked_operator_blocker_families
            else {}
        ),
        "operator_blocker_family_plan": operator_blocker_family_plan,
        "first_blocked_case_input_slot": _as_dict(
            vina_gnina_runtime_readiness_summary.get("operator_unblock_packet")
        ).get("first_blocked_case_input_slot")
        or _as_dict(
            vina_gnina_runtime_readiness_summary.get("first_blocked_case_input_slot")
        ),
        "first_blocked_engine_run_slot": _as_dict(
            vina_gnina_runtime_readiness_summary.get("operator_unblock_packet")
        ).get("first_blocked_engine_run_slot")
        or _as_dict(
            vina_gnina_runtime_readiness_summary.get("first_blocked_engine_run_slot")
        ),
        "first_blocked_role_receipt": _as_dict(
            vina_gnina_rows_template_preflight_summary.get(
                "first_blocked_role_receipt"
            )
        ),
        "components": components,
        "claim_boundary": (
            "This audit summarizes actual Vina/GNINA Phase 2 closure evidence. "
            "It does not run docking engines, fill manifests, synthesize adapter "
            "rows, or replace external source receipts."
        ),
    }


def _missing_row_input_actions(
    *,
    missing_row_inputs: list[str],
    row_input_contracts: list[dict[str, Any]],
    phase2_row_closure_matrix: list[dict[str, Any]],
    commands: dict[str, str],
    vina_gnina_execution_plan_summary: dict[str, Any],
    vina_gnina_runtime_readiness_summary: dict[str, Any],
    vina_gnina_rows_template_preflight_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts = _row_input_contract_map(row_input_contracts)
    closure_by_row_input = {
        str(row.get("row_input_id") or ""): row
        for row in phase2_row_closure_matrix
        if isinstance(row, dict)
    }
    actions: list[dict[str, Any]] = []
    for row_input_id in missing_row_inputs:
        contract = contracts.get(row_input_id, {})
        row_closure = closure_by_row_input.get(row_input_id, {})
        action = {
            "row_input_id": row_input_id,
            "status": "operator_input_required",
            "source_family": str(contract.get("source_family") or ""),
            "accepted_formats": list(contract.get("accepted_formats") or []),
            "depends_on_row_inputs": list(contract.get("depends_on_row_inputs") or []),
            "unblocks_components": list(contract.get("unblocks_components") or []),
            "closes_phase2_criteria": list(
                row_closure.get("closes_phase2_criteria") or []
            ),
            "phase2_required_by_components": list(
                row_closure.get("required_by_components") or []
            ),
            "phase2_materialization_chain": list(
                row_closure.get("materialization_chain") or []
            ),
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
            row_candidate_status = vina_gnina_runtime_readiness_summary.get(
                "row_candidate_status"
            )
            if not isinstance(row_candidate_status, dict):
                row_candidate_status = {}
            adapter_preflight = row_candidate_status.get("adapter_preflight")
            if not isinstance(adapter_preflight, dict):
                adapter_preflight = {}
            manifest_candidate_paths = [
                str(path)
                for path in vina_gnina_execution_plan_summary.get(
                    "input_manifest_candidate_paths", []
                )
                if str(path)
            ]
            action.update(
                {
                    "engine_input_manifest_template": str(
                        contract.get("engine_input_manifest_template") or ""
                    ),
                    "runtime_action_packet": _vina_gnina_runtime_action_packet(
                        vina_gnina_runtime_readiness_summary
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
                        "default_execution_plan_manifest_path": str(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_default_manifest_path"
                            )
                            or ""
                        ),
                        "recommended_template_dropzone": str(
                            DEFAULT_VINA_GNINA_INPUT_MANIFEST
                        ),
                        "recommended_template_dropzone_is_supported_candidate_path": (
                            str(DEFAULT_VINA_GNINA_INPUT_MANIFEST)
                            in manifest_candidate_paths
                        ),
                        "accepted_manifest_formats": list(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_accepted_formats"
                            )
                            or []
                        ),
                        "supported_manifest_candidate_paths": manifest_candidate_paths,
                        "detected_manifest_artifact_count": int(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_detected_manifest_artifact_count"
                            )
                            or 0
                        ),
                        "selected_manifest_path": str(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_selected_path"
                            )
                            or ""
                        ),
                        "selected_manifest_format": str(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_selected_format"
                            )
                            or ""
                        ),
                        "input_manifest_row_count": int(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_row_count"
                            )
                            or 0
                        ),
                        "input_manifest_load_errors": list(
                            vina_gnina_execution_plan_summary.get(
                                "input_manifest_load_errors"
                            )
                            or []
                        ),
                        "template_to_manifest_command": (
                            "cp "
                            f"{DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE} "
                            f"{DEFAULT_VINA_GNINA_INPUT_MANIFEST}"
                        ),
                        "source_archive_operator_artifact": "<CASF-2016.tar.gz>",
                        "source_archive_extraction_command": str(
                            commands.get("materialize_input_manifest_from_casf_archive")
                            or ""
                        ),
                        "source_archive_extraction_report_artifact": str(
                            DEFAULT_VINA_GNINA_INPUT_MANIFEST_FROM_CASF_ARCHIVE_REPORT
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
                    "adapter_intake_formats": list(
                        VINA_GNINA_SUPPORTED_INTAKE_FORMATS
                    ),
                    "direct_adapter_materialization_command": str(
                        commands.get("materialize_vina_gnina_adapter") or ""
                    ),
                    "adapter_row_preflight_action_packet": {
                        "status": str(
                            row_candidate_status.get("status")
                            or "row_artifact_missing"
                        ),
                        "expected_rows_artifact": str(DEFAULT_VINA_GNINA_ROWS),
                        "row_template_artifact": str(
                            DEFAULT_VINA_GNINA_ROWS_TEMPLATE
                        ),
                        "row_template_preflight_artifact": str(
                            DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT
                        ),
                        "row_template_preflight_markdown_artifact": str(
                            DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD
                        ),
                        "template_preflight_summary": (
                            vina_gnina_rows_template_preflight_summary
                        ),
                        "role_receipt_plan_summary": {
                            "role_receipt_plan_count": int(
                                vina_gnina_rows_template_preflight_summary.get(
                                    "role_receipt_plan_count"
                                )
                                or 0
                            ),
                            "role_receipt_blocked_count": int(
                                vina_gnina_rows_template_preflight_summary.get(
                                    "role_receipt_blocked_count"
                                )
                                or 0
                            ),
                            "first_blocked_role_receipt": dict(
                                vina_gnina_rows_template_preflight_summary.get(
                                    "first_blocked_role_receipt"
                                )
                                or {}
                            ),
                        },
                        "build_row_template_preflight_command": str(
                            commands.get("build_vina_gnina_rows_template_preflight")
                            or ""
                        ),
                        "supported_candidate_paths": [
                            str(row.get("path") or "")
                            for row in row_candidate_status.get(
                                "candidate_paths", []
                            )
                            if isinstance(row, dict)
                        ],
                        "detected_row_artifact_count": int(
                            row_candidate_status.get(
                                "detected_row_artifact_count"
                            )
                            or 0
                        ),
                        "selected_path": str(
                            row_candidate_status.get("selected_path") or ""
                        ),
                        "selected_row_count": int(
                            row_candidate_status.get("selected_row_count") or 0
                        ),
                        "adapter_case_count": int(
                            row_candidate_status.get("adapter_case_count") or 0
                        ),
                        "adapter_rows_ready": bool(
                            row_candidate_status.get("adapter_rows_ready")
                        ),
                        "adapter_preflight_status": str(
                            adapter_preflight.get("status") or ""
                        ),
                        "adapter_preflight_contract_pass": bool(
                            adapter_preflight.get("contract_pass")
                        ),
                        "adapter_preflight_blockers": [
                            str(row)
                            for row in adapter_preflight.get("blockers", [])
                            if str(row)
                        ]
                        if isinstance(adapter_preflight.get("blockers"), list)
                        else [],
                        "load_error": str(
                            row_candidate_status.get("load_error") or ""
                        ),
                        "blocker": str(row_candidate_status.get("blocker") or ""),
                        "direct_adapter_materialization_command": str(
                            commands.get("materialize_vina_gnina_adapter") or ""
                        ),
                        "template_safety_policy": {
                            "template_is_not_evidence": True,
                            "operator_rows_must_be_real_engine_outputs": True,
                            "placeholder_or_fixture_rows_do_not_promote": True,
                            "preflight_does_not_run_engines": True,
                        },
                    },
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
    source_access_preflight_receipt_summary = (
        _source_access_preflight_receipt_summary(repo_root)
    )
    external_receipts_validation_summary = (
        _external_receipts_validation_summary(repo_root)
    )
    phase2_row_audit = _load_json(repo_root, DEFAULT_PHASE2_ROW_AUDIT)
    phase2_row_audit_summary = _phase2_row_audit_summary(phase2_row_audit)
    phase2_row_closure_matrix = _phase2_row_closure_matrix(phase2_row_audit)
    phase2_exit_criteria = _phase2_exit_criteria(phase2_row_audit)
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
    vina_gnina_rows_template_preflight_summary = (
        _vina_gnina_rows_template_preflight_summary(repo_root)
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
        "materialize_vina_gnina_input_manifest_from_template": (
            "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py "
            f"--template {DEFAULT_VINA_GNINA_INPUT_MANIFEST_TEMPLATE} "
            f"--out-manifest {DEFAULT_VINA_GNINA_INPUT_MANIFEST} "
            f"--out-report {DEFAULT_VINA_GNINA_INPUT_MANIFEST_FROM_TEMPLATE_REPORT}"
        ),
        "materialize_input_manifest_from_casf_archive": (
            "python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py "
            "--archive <CASF-2016.tar.gz> "
            f"--out-manifest {DEFAULT_VINA_GNINA_INPUT_MANIFEST} "
            f"--out-report {DEFAULT_VINA_GNINA_INPUT_MANIFEST_FROM_CASF_ARCHIVE_REPORT} "
            "--fail-blocked"
        ),
        "check_vina_gnina_runtime_readiness": (
            "python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py "
            f"--out {DEFAULT_VINA_GNINA_RUNTIME_READINESS}"
        ),
        "build_vina_gnina_rows_template_preflight": (
            "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py "
            f"--out {DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT} "
            f"--out-md {DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT_MD}"
        ),
        "build_source_access_preflight_receipt": (
            "python3 scripts/build_public_benchmark_source_access_preflight_receipt.py "
            f"--out {DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT} "
            f"--out-md {DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT_MD}"
        ),
        "probe_source_access_preflight": (
            "python3 scripts/build_public_benchmark_source_access_preflight_receipt.py "
            f"--out {DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT} "
            f"--out-md {DEFAULT_SOURCE_ACCESS_PREFLIGHT_RECEIPT_MD} "
            "--probe-network"
        ),
        "materialize_vina_gnina_adapter": (
            "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
            "--intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson> "
            f"--out-adapter {PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
            f"--out-report {PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
            "--fail-blocked"
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
        phase2_row_closure_matrix=phase2_row_closure_matrix,
        commands=commands,
        vina_gnina_execution_plan_summary=vina_gnina_execution_plan_summary,
        vina_gnina_runtime_readiness_summary=vina_gnina_runtime_readiness_summary,
        vina_gnina_rows_template_preflight_summary=(
            vina_gnina_rows_template_preflight_summary
        ),
    )
    phase2_harness_completion_audit = _phase2_harness_completion_audit(
        phase2_exit_criteria=phase2_exit_criteria,
        phase2_row_closure_matrix=phase2_row_closure_matrix,
        phase2_row_audit_summary=phase2_row_audit_summary,
        vina_gnina_execution_plan_summary=vina_gnina_execution_plan_summary,
        vina_gnina_runtime_readiness_summary=(
            vina_gnina_runtime_readiness_summary
        ),
    )
    external_receipt_completion_audit = _external_receipt_completion_audit(
        official_source_receipt_plan=official_source_receipt_plan,
        source_access_preflight_receipt_summary=(
            source_access_preflight_receipt_summary
        ),
        external_receipts_validation_summary=(
            external_receipts_validation_summary
        ),
        phase2_row_audit_summary=phase2_row_audit_summary,
        phase2_row_closure_matrix=phase2_row_closure_matrix,
        vina_gnina_execution_plan_summary=vina_gnina_execution_plan_summary,
        vina_gnina_runtime_readiness_summary=(
            vina_gnina_runtime_readiness_summary
        ),
    )
    vina_gnina_actual_evidence_audit = _vina_gnina_actual_evidence_audit(
        phase2_row_audit_summary=phase2_row_audit_summary,
        vina_gnina_execution_plan_summary=vina_gnina_execution_plan_summary,
        vina_gnina_runtime_readiness_summary=vina_gnina_runtime_readiness_summary,
        vina_gnina_rows_template_preflight_summary=(
            vina_gnina_rows_template_preflight_summary
        ),
        external_receipt_completion_audit=external_receipt_completion_audit,
    )
    operator_next_actions = [
        "review_official_source_receipt_plan",
        "attach_casf_pdbbind_subset_rows_with_local_file_checksums",
        "attach_pose_coordinate_rows_with_symmetry_contracts",
        "attach_dud_e_or_lit_pcba_scored_molecule_rows",
        "build_vina_gnina_execution_plan_from_materialized_cases",
        "fill_public_benchmark_vina_gnina_input_manifest",
        "run_vina_gnina_runtime_readiness_check",
        "attach_vina_gnina_engine_run_rows",
        "build_source_access_preflight_receipt",
        "attach_external_source_receipts_and_license_or_accession_refs",
        "run_public_benchmark_operator_bundle_from_rows",
        "run_public_benchmark_phase2_row_audit",
        "run_public_benchmark_harness_bundle_materializer",
        "refresh_public_benchmark_source_of_truth",
    ]
    vina_gnina_input_manifest_component = next(
        (
            row
            for row in vina_gnina_actual_evidence_audit["components"]
            if row.get("component_id") == "engine_input_manifest"
        ),
        {},
    )
    vina_gnina_input_manifest_current = _as_dict(
        vina_gnina_input_manifest_component.get("current")
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
                DEFAULT_SUBSET_MANIFEST,
                DEFAULT_ENRICHMENT_SCORECARD,
                DEFAULT_VINA_GNINA_COMPARISON_ADAPTER,
                Path("scripts/materialize_public_benchmark_subset_manifest.py"),
                Path("scripts/materialize_public_benchmark_pose_validity_input.py"),
                Path("scripts/materialize_public_benchmark_posebusters_validity_packet.py"),
                Path("scripts/materialize_public_benchmark_rmsd_scorecard.py"),
                Path("scripts/materialize_public_benchmark_pose_success_harness.py"),
                Path("scripts/materialize_public_benchmark_enrichment_scorecard.py"),
                Path("scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"),
                Path("scripts/build_public_benchmark_vina_gnina_execution_plan.py"),
                Path("scripts/build_public_benchmark_vina_gnina_runtime_readiness.py"),
                Path(
                    "scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py"
                ),
                Path("scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"),
                DEFAULT_VINA_GNINA_ROWS_TEMPLATE,
                DEFAULT_VINA_GNINA_ROWS_TEMPLATE_PREFLIGHT,
                DEFAULT_VINA_GNINA_INPUT_MANIFEST,
                DEFAULT_VINA_GNINA_INPUT_MANIFEST_FROM_TEMPLATE_REPORT,
                Path("scripts/build_public_benchmark_source_access_preflight_receipt.py"),
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
        "source_access_preflight_receipt": (
            source_access_preflight_receipt_summary
        ),
        "external_receipts_validation": external_receipts_validation_summary,
        "external_receipt_completion_audit": (
            external_receipt_completion_audit
        ),
        "receipt_promotion_policy": dict(RECEIPT_PROMOTION_POLICY),
        "phase2_row_audit": phase2_row_audit_summary,
        "phase2_exit_criteria": phase2_exit_criteria,
        "phase2_exit_criterion_count": len(phase2_exit_criteria),
        "phase2_harness_completion_audit": phase2_harness_completion_audit,
        "phase2_row_closure_matrix": phase2_row_closure_matrix,
        "phase2_row_closure_matrix_count": len(phase2_row_closure_matrix),
        "vina_gnina_actual_evidence_audit": vina_gnina_actual_evidence_audit,
        "vina_gnina_execution_plan": vina_gnina_execution_plan_summary,
        "vina_gnina_runtime_readiness": vina_gnina_runtime_readiness_summary,
        "vina_gnina_rows_template_preflight_summary": (
            vina_gnina_rows_template_preflight_summary
        ),
        "missing_row_input_actions": missing_row_input_actions,
        "missing_row_input_action_count": len(missing_row_input_actions),
        "operator_acquisition_checklist": operator_next_actions,
        "operator_next_actions": operator_next_actions,
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
            "official_source_access_preflight_count": official_source_receipt_plan[
                "source_access_preflight_count"
            ],
            "source_access_preflight_receipt_status": (
                source_access_preflight_receipt_summary["status"]
            ),
            "source_access_preflight_receipt_ready": (
                source_access_preflight_receipt_summary["source_access_ready"]
            ),
            "source_access_preflight_reachable_count": (
                source_access_preflight_receipt_summary["reachable_count"]
            ),
            "source_access_preflight_blocked_count": (
                source_access_preflight_receipt_summary["blocked_count"]
            ),
            "source_access_preflight_network_probe_performed": (
                source_access_preflight_receipt_summary[
                    "network_probe_performed"
                ]
            ),
            "external_receipts_validation_status": (
                external_receipts_validation_summary["status"]
            ),
            "external_receipts_ready_for_materialized_rows": (
                external_receipts_validation_summary[
                    "public_benchmark_external_receipts_ready"
                ]
            ),
            "external_receipts_expected_artifact_role_count": (
                external_receipts_validation_summary[
                    "expected_artifact_role_count"
                ]
            ),
            "external_receipts_complete_artifact_role_count": (
                external_receipts_validation_summary[
                    "receipt_complete_artifact_role_count"
                ]
            ),
            "external_receipts_missing_expected_artifact_roles": (
                external_receipts_validation_summary[
                    "missing_expected_artifact_roles"
                ]
            ),
            "external_receipt_completion_audit_status": (
                external_receipt_completion_audit["status"]
            ),
            "external_receipt_ready_official_role_count": (
                external_receipt_completion_audit[
                    "ready_official_receipt_role_count"
                ]
            ),
            "external_receipt_blocked_official_role_count": (
                external_receipt_completion_audit[
                    "blocked_official_receipt_role_count"
                ]
            ),
            "external_receipt_all_expected_artifact_roles_complete": (
                external_receipt_completion_audit[
                    "all_expected_artifact_roles_complete"
                ]
            ),
            "phase2_row_audit_status": phase2_row_audit_summary["status"],
            "phase2_exit_criterion_count": len(phase2_exit_criteria),
            "phase2_passing_exit_criterion_count": len(
                [row for row in phase2_exit_criteria if row["pass"]]
            ),
            "phase2_blocked_exit_criterion_count": len(
                [row for row in phase2_exit_criteria if not row["pass"]]
            ),
            "phase2_harness_completion_audit_status": (
                phase2_harness_completion_audit["status"]
            ),
            "phase2_harness_requirement_count": (
                phase2_harness_completion_audit["requirement_count"]
            ),
            "phase2_harness_ready_requirement_count": (
                phase2_harness_completion_audit["ready_requirement_count"]
            ),
            "phase2_harness_blocked_requirement_count": (
                phase2_harness_completion_audit["blocked_requirement_count"]
            ),
            "phase2_harness_complete_except_vina_gnina_actual_rows": (
                phase2_harness_completion_audit[
                    "harness_contract_complete_except_vina_gnina_actual_rows"
                ]
            ),
            "phase2_row_closure_matrix_count": len(phase2_row_closure_matrix),
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
            "vina_gnina_actual_evidence_audit_status": (
                vina_gnina_actual_evidence_audit["status"]
            ),
            "vina_gnina_actual_evidence_ready_component_count": (
                vina_gnina_actual_evidence_audit["ready_component_count"]
            ),
            "vina_gnina_actual_evidence_blocked_component_count": (
                vina_gnina_actual_evidence_audit["blocked_component_count"]
            ),
            "vina_gnina_actual_evidence_required_engine_run_count": (
                vina_gnina_actual_evidence_audit["required_engine_run_count"]
            ),
            "vina_gnina_actual_operator_blocker_family_count": (
                vina_gnina_actual_evidence_audit["operator_blocker_family_count"]
            ),
            "vina_gnina_actual_operator_blocker_family_blocked_count": (
                vina_gnina_actual_evidence_audit[
                    "operator_blocker_family_blocked_count"
                ]
            ),
            "vina_gnina_actual_operator_blocker_family_missing_item_count": (
                vina_gnina_actual_evidence_audit[
                    "operator_blocker_family_missing_item_count"
                ]
            ),
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
            "vina_gnina_input_manifest_syntax_ready": (
                vina_gnina_input_manifest_current.get(
                    "input_manifest_syntax_ready"
                )
            ),
            "vina_gnina_input_manifest_verification_status": (
                vina_gnina_input_manifest_current.get(
                    "input_manifest_verification_status"
                )
            ),
            "vina_gnina_input_manifest_verified_case_input_count": (
                vina_gnina_input_manifest_current.get("verified_case_input_count")
            ),
            "vina_gnina_input_manifest_template_manifest_ready": (
                vina_gnina_input_manifest_current.get("template_manifest_ready")
            ),
            "vina_gnina_input_manifest_template_completion_blocked_case_count": (
                vina_gnina_input_manifest_current.get(
                    "template_completion_blocked_case_count"
                )
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
            "vina_gnina_runtime_case_input_slot_count": (
                vina_gnina_runtime_readiness_summary["case_input_slot_matrix_count"]
            ),
            "vina_gnina_runtime_blocked_case_input_slot_count": (
                vina_gnina_runtime_readiness_summary[
                    "blocked_case_input_slot_count"
                ]
            ),
            "vina_gnina_runtime_engine_run_slot_count": (
                vina_gnina_runtime_readiness_summary["engine_run_slot_matrix_count"]
            ),
            "vina_gnina_runtime_blocked_engine_run_slot_count": (
                vina_gnina_runtime_readiness_summary[
                    "blocked_engine_run_slot_count"
                ]
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
            "vina_gnina_engine_run_bundle_status": (
                _as_dict(
                    vina_gnina_runtime_readiness_summary.get(
                        "engine_run_bundle_summary"
                    )
                ).get("status")
            ),
            "vina_gnina_engine_run_bundle_materialized": (
                _as_dict(
                    vina_gnina_runtime_readiness_summary.get(
                        "engine_run_bundle_summary"
                    )
                ).get("bundle_materialized")
            ),
            "vina_gnina_rows_from_engine_run_bundle_status": (
                _as_dict(
                    vina_gnina_runtime_readiness_summary.get(
                        "rows_from_engine_run_bundle_report_summary"
                    )
                ).get("status")
            ),
            "vina_gnina_rows_from_engine_run_bundle_materialized": (
                _as_dict(
                    vina_gnina_runtime_readiness_summary.get(
                        "rows_from_engine_run_bundle_report_summary"
                    )
                ).get("rows_materialized")
            ),
            "vina_gnina_rows_template_preflight_status": (
                vina_gnina_rows_template_preflight_summary["status"]
            ),
            "vina_gnina_rows_template_role_receipt_plan_count": (
                vina_gnina_rows_template_preflight_summary[
                    "role_receipt_plan_count"
                ]
            ),
            "vina_gnina_rows_template_role_receipt_blocked_count": (
                vina_gnina_rows_template_preflight_summary[
                    "role_receipt_blocked_count"
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
        f"- `official_source_access_preflight_count`: `{payload['official_source_receipt_plan']['source_access_preflight_count']}`",
        "- `source_access_preflight_receipt_status`: "
        f"`{payload['source_access_preflight_receipt']['status']}`",
        "- `source_access_preflight_receipt_ready`: "
        f"`{payload['source_access_preflight_receipt']['source_access_ready']}`",
        "- `source_access_preflight_reachable_count`: "
        f"`{payload['source_access_preflight_receipt']['reachable_count']}`",
        "- `source_access_preflight_blocked_count`: "
        f"`{payload['source_access_preflight_receipt']['blocked_count']}`",
        "- `external_receipts_validation_status`: "
        f"`{payload['external_receipts_validation']['status']}`",
        "- `external_receipts_complete_artifact_roles`: "
        f"`{payload['external_receipts_validation']['receipt_complete_artifact_role_count']}/"
        f"{payload['external_receipts_validation']['expected_artifact_role_count']}`",
        "- `external_receipt_completion_audit_status`: "
        f"`{payload['external_receipt_completion_audit']['status']}`",
        "- `external_receipt_blocked_official_role_count`: "
        f"`{payload['external_receipt_completion_audit']['blocked_official_receipt_role_count']}`",
        f"- `phase2_row_audit`: `{payload['phase2_row_audit']['artifact']}`",
        f"- `phase2_row_audit_status`: `{payload['phase2_row_audit']['status']}`",
        f"- `phase2_row_audit_missing_row_inputs`: `{', '.join(payload['phase2_row_audit']['missing_row_inputs'])}`",
        f"- `phase2_row_audit_source_actuality_scope`: `{payload['phase2_row_audit']['source_actuality_scope']}`",
        f"- `phase2_row_audit_source_actuality_contract_pass`: `{payload['phase2_row_audit']['source_actuality_contract_pass']}`",
        f"- `phase2_row_audit_source_actuality_blocker_count`: `{payload['phase2_row_audit']['source_actuality_blocker_count']}`",
        f"- `phase2_exit_criterion_count`: `{payload['phase2_exit_criterion_count']}`",
        f"- `phase2_row_closure_matrix_count`: `{payload['phase2_row_closure_matrix_count']}`",
        "- `phase2_harness_completion_audit_status`: "
        f"`{payload['phase2_harness_completion_audit']['status']}`",
        "- `phase2_harness_ready_requirement_count`: "
        f"`{payload['phase2_harness_completion_audit']['ready_requirement_count']}`",
        "- `phase2_harness_blocked_requirement_count`: "
        f"`{payload['phase2_harness_completion_audit']['blocked_requirement_count']}`",
        "- `phase2_harness_complete_except_vina_gnina_actual_rows`: "
        "`"
        f"{payload['phase2_harness_completion_audit']['harness_contract_complete_except_vina_gnina_actual_rows']}"
        "`",
        f"- `missing_row_input_action_count`: `{payload['missing_row_input_action_count']}`",
        "- `vina_gnina_actual_evidence_audit_status`: "
        f"`{payload['vina_gnina_actual_evidence_audit']['status']}`",
        "- `vina_gnina_actual_evidence_blocked_component_count`: "
        f"`{payload['vina_gnina_actual_evidence_audit']['blocked_component_count']}`",
        f"- `vina_gnina_execution_plan`: `{payload['vina_gnina_execution_plan']['artifact']}`",
        f"- `vina_gnina_execution_plan_status`: `{payload['vina_gnina_execution_plan']['status']}`",
        f"- `vina_gnina_required_engine_run_count`: `{payload['vina_gnina_execution_plan']['required_engine_run_count']}`",
        f"- `vina_gnina_input_manifest_status`: `{payload['vina_gnina_execution_plan']['input_manifest_status']}`",
        f"- `vina_gnina_input_manifest_row_count`: `{payload['vina_gnina_execution_plan']['input_manifest_row_count']}`",
        "- `vina_gnina_input_manifest_verification_status`: "
        f"`{payload['summary'].get('vina_gnina_input_manifest_verification_status')}`",
        "- `vina_gnina_input_manifest_verified_case_input_count`: "
        f"`{payload['summary'].get('vina_gnina_input_manifest_verified_case_input_count')}`",
        "- `vina_gnina_input_manifest_template_completion_blocked_case_count`: "
        f"`{payload['summary'].get('vina_gnina_input_manifest_template_completion_blocked_case_count')}`",
        f"- `vina_gnina_runtime_readiness`: `{payload['vina_gnina_runtime_readiness']['artifact']}`",
        f"- `vina_gnina_runtime_readiness_status`: `{payload['vina_gnina_runtime_readiness']['status']}`",
        f"- `vina_gnina_runtime_ready_engine_run_slot_count`: `{payload['vina_gnina_runtime_readiness']['ready_engine_run_slot_count']}`",
        f"- `vina_gnina_runtime_case_input_slot_count`: `{payload['vina_gnina_runtime_readiness']['case_input_slot_matrix_count']}`",
        f"- `vina_gnina_runtime_blocked_case_input_slot_count`: `{payload['vina_gnina_runtime_readiness']['blocked_case_input_slot_count']}`",
        f"- `vina_gnina_runtime_engine_run_slot_count`: `{payload['vina_gnina_runtime_readiness']['engine_run_slot_matrix_count']}`",
        f"- `vina_gnina_runtime_blocked_engine_run_slot_count`: `{payload['vina_gnina_runtime_readiness']['blocked_engine_run_slot_count']}`",
        f"- `vina_gnina_adapter_row_preflight_status`: `{payload['vina_gnina_runtime_readiness']['adapter_row_preflight_status']}`",
        "- `vina_gnina_engine_run_bundle_status`: "
        f"`{_as_dict(payload['vina_gnina_runtime_readiness'].get('engine_run_bundle_summary')).get('status')}`",
        "- `vina_gnina_engine_run_bundle_materialized`: "
        f"`{_as_dict(payload['vina_gnina_runtime_readiness'].get('engine_run_bundle_summary')).get('bundle_materialized')}`",
        "- `vina_gnina_rows_from_engine_run_bundle_status`: "
        f"`{_as_dict(payload['vina_gnina_runtime_readiness'].get('rows_from_engine_run_bundle_report_summary')).get('status')}`",
        "- `vina_gnina_rows_from_engine_run_bundle_materialized`: "
        f"`{_as_dict(payload['vina_gnina_runtime_readiness'].get('rows_from_engine_run_bundle_report_summary')).get('rows_materialized')}`",
        "- `vina_gnina_rows_template_role_receipt_blocked_count`: "
        f"`{payload['vina_gnina_rows_template_preflight_summary']['role_receipt_blocked_count']}`",
        f"- `vina_gnina_runtime_missing_engine_ids`: `{', '.join(payload['vina_gnina_runtime_readiness']['missing_engine_ids'])}`",
        "",
        "## Operator Next Actions",
        "",
        "| Step | Action |",
        "|---:|---|",
    ]
    for index, action in enumerate(payload.get("operator_next_actions", []), start=1):
        lines.append(f"| {index} | `{action}` |")
    source_access_receipt = _as_dict(
        payload.get("source_access_preflight_receipt")
    )
    source_access_rows = [
        row
        for row in source_access_receipt.get("row_statuses", [])
        if isinstance(row, dict)
    ] if isinstance(source_access_receipt.get("row_statuses"), list) else []
    if source_access_receipt:
        lines.extend(
            [
                "",
                "## Source Access Preflight Receipt",
                "",
                f"- `artifact`: `{source_access_receipt.get('artifact')}`",
                f"- `status`: `{source_access_receipt.get('status')}`",
                f"- `network_probe_performed`: `{source_access_receipt.get('network_probe_performed')}`",
                f"- `source_access_ready`: `{source_access_receipt.get('source_access_ready')}`",
                f"- `reachable_count`: `{source_access_receipt.get('reachable_count')}`",
                f"- `blocked_count`: `{source_access_receipt.get('blocked_count')}`",
                "",
                "| Source | Family | Status | Primary HTTP | Fallback HTTP | Blockers |",
                "|---|---|---|---:|---:|---|",
            ]
        )
        for row in source_access_rows:
            blockers = ", ".join(
                f"`{blocker}`"
                for blocker in row.get("blockers", [])
                if str(blocker)
            )
            lines.append(
                f"| `{row.get('source_id', '')}` | "
                f"`{row.get('source_family', '')}` | "
                f"`{row.get('status', '')}` | "
                f"{row.get('primary_http_status', 0)} | "
                f"{row.get('fallback_http_status', 0)} | "
                f"{blockers or '`none`'} |"
            )
    external_receipt_audit = _as_dict(
        payload.get("external_receipt_completion_audit")
    )
    external_receipt_roles = [
        row
        for row in external_receipt_audit.get("receipt_roles", [])
        if isinstance(row, dict)
    ] if isinstance(external_receipt_audit.get("receipt_roles"), list) else []
    if external_receipt_audit:
        missing_artifact_roles = ", ".join(
            f"`{role}`"
            for role in external_receipt_audit.get(
                "missing_expected_artifact_roles", []
            )
            if str(role)
        )
        lines.extend(
            [
                "",
                "## External Receipt Completion Audit",
                "",
                f"- `status`: `{external_receipt_audit.get('status')}`",
                "- `source_access_ready`: "
                f"`{external_receipt_audit.get('source_access_ready')}`",
                "- `external_receipts_validation_status`: "
                f"`{external_receipt_audit.get('external_receipts_validation_status')}`",
                "- `external_receipts_ready_for_materialized_rows`: "
                f"`{external_receipt_audit.get('external_receipts_ready_for_materialized_rows')}`",
                "- `complete_artifact_roles`: "
                f"`{external_receipt_audit.get('receipt_complete_artifact_role_count')}/"
                f"{external_receipt_audit.get('expected_artifact_role_count')}`",
                "- `all_expected_artifact_roles_complete`: "
                f"`{external_receipt_audit.get('all_expected_artifact_roles_complete')}`",
                "- `missing_expected_artifact_roles`: "
                f"{missing_artifact_roles or '`none`'}",
                "- `blocked_official_receipt_role_count`: "
                f"`{external_receipt_audit.get('blocked_official_receipt_role_count')}`",
                f"- `operator_action`: `{external_receipt_audit.get('operator_action')}`",
                "",
                "| Receipt Role | Row Input | Status | Row Status | Sources Ready | Validator Role | Blockers |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in external_receipt_roles:
            blockers = ", ".join(
                f"`{blocker}`"
                for blocker in row.get("blockers", [])
                if str(blocker)
            )
            validator_role = row.get("validator_artifact_role") or "row_actuality"
            lines.append(
                f"| `{row.get('receipt_role_id', '')}` | "
                f"`{row.get('row_input_id', '')}` | "
                f"`{row.get('status', '')}` | "
                f"`{row.get('row_input_status', '')}` | "
                f"`{row.get('source_access_ready')}` | "
                f"`{validator_role}` | "
                f"{blockers or '`none`'} |"
            )
    harness_audit = _as_dict(payload.get("phase2_harness_completion_audit"))
    harness_requirements = [
        row for row in harness_audit.get("requirements", []) if isinstance(row, dict)
    ] if isinstance(harness_audit.get("requirements"), list) else []
    if harness_audit:
        lines.extend(
            [
                "",
                "## Phase 2 Harness Completion Audit",
                "",
                f"- `status`: `{harness_audit.get('status')}`",
                "- `harness_contract_complete_except_vina_gnina_actual_rows`: "
                "`"
                f"{harness_audit.get('harness_contract_complete_except_vina_gnina_actual_rows')}"
                "`",
                f"- `remaining_row_inputs`: `{', '.join(harness_audit.get('remaining_row_inputs', []))}`",
                f"- `remaining_operator_action`: `{harness_audit.get('remaining_operator_action')}`",
                f"- `vina_gnina_runtime_status`: `{harness_audit.get('vina_gnina_runtime_status')}`",
                f"- `vina_gnina_input_manifest_status`: `{harness_audit.get('vina_gnina_input_manifest_status')}`",
                "",
                "| Requirement | Product Requirement | Status | Pass | Row Inputs | Blockers |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in harness_requirements:
            row_inputs = ", ".join(
                f"`{row_input}`" for row_input in row.get("row_inputs", [])
            )
            blockers = ", ".join(
                f"`{blocker}`"
                for blocker in row.get("blockers", [])
                if str(blocker)
            )
            lines.append(
                f"| `{row.get('requirement_id', '')}` | "
                f"{row.get('product_requirement', '')} | "
                f"`{row.get('status', '')}` | "
                f"`{row.get('pass')}` | "
                f"{row_inputs or '`none`'} | "
                f"{blockers or '`none`'} |"
            )
    vina_gnina_actual_audit = _as_dict(
        payload.get("vina_gnina_actual_evidence_audit")
    )
    vina_gnina_actual_components = [
        row
        for row in vina_gnina_actual_audit.get("components", [])
        if isinstance(row, dict)
    ] if isinstance(vina_gnina_actual_audit.get("components"), list) else []
    vina_gnina_operator_blocker_families = [
        row
        for row in _as_list(
            vina_gnina_actual_audit.get("operator_blocker_family_plan")
        )
        if isinstance(row, dict)
    ]
    if vina_gnina_actual_audit:
        lines.extend(
            [
                "",
                "## Vina/GNINA Actual Evidence Audit",
                "",
                f"- `status`: `{vina_gnina_actual_audit.get('status')}`",
                "- `actual_closure_ready`: "
                f"`{vina_gnina_actual_audit.get('actual_closure_ready')}`",
                "- `ready_component_count`: "
                f"`{vina_gnina_actual_audit.get('ready_component_count')}`",
                "- `blocked_component_count`: "
                f"`{vina_gnina_actual_audit.get('blocked_component_count')}`",
                "- `remaining_evidence`: "
                f"`{', '.join(vina_gnina_actual_audit.get('remaining_evidence', []))}`",
                "- `operator_blocker_family_count`: "
                f"`{vina_gnina_actual_audit.get('operator_blocker_family_count', 0)}`",
                "- `operator_blocker_family_missing_item_count`: "
                f"`{vina_gnina_actual_audit.get('operator_blocker_family_missing_item_count', 0)}`",
                "",
                "| Component | Status | Pass | Current | Required | Blockers |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in vina_gnina_actual_components:
            current = json.dumps(
                _as_dict(row.get("current")),
                ensure_ascii=False,
                sort_keys=True,
            )
            required = json.dumps(
                _as_dict(row.get("required")),
                ensure_ascii=False,
                sort_keys=True,
            )
            blockers = ", ".join(
                f"`{blocker}`"
                for blocker in row.get("blockers", [])
                if str(blocker)
            )
            lines.append(
                f"| `{row.get('component_id', '')}` | "
                f"`{row.get('status', '')}` | `{row.get('pass')}` | "
                f"`{current}` | `{required}` | {blockers or '`none`'} |"
            )
        if vina_gnina_operator_blocker_families:
            lines.extend(
                [
                    "",
                    "### Vina/GNINA Operator Blocker Families",
                    "",
                    "| Family | Status | Missing Items | Blocked Cases | Operator Action | Command Key | Materialization Command |",
                    "|---|---|---:|---:|---|---|---|",
                ]
            )
            for row in vina_gnina_operator_blocker_families:
                lines.append(
                    f"| `{row.get('family_id', '')}` | "
                    f"`{row.get('status', '')}` | "
                    f"{_as_int(row.get('missing_item_count'))} | "
                    f"{_as_int(row.get('blocked_case_count'))} | "
                    f"`{row.get('operator_action', '')}` | "
                    f"`{row.get('command_key', '')}` | "
                    f"`{row.get('materialization_command', '')}` |"
                )
    lines.extend(
        [
            "",
            "| Row Input | Source Family | Status | Unblocks |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["row_input_contracts"]:
        unblocks = ", ".join(
            f"`{component}`" for component in row["unblocks_components"]
        )
        lines.append(
            f"| `{row['row_input_id']}` | `{row['source_family']}` | "
            f"`{row['status']}` | {unblocks} |"
        )
    phase2_exit_criteria = [
        row
        for row in payload.get("phase2_exit_criteria", [])
        if isinstance(row, dict)
    ]
    if phase2_exit_criteria:
        lines.extend(
            [
                "",
                "## Phase 2 Exit Criteria",
                "",
                "| Criterion | Component | Pass | Current | Required | Blockers |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in phase2_exit_criteria:
            blockers = ", ".join(
                f"`{blocker}`" for blocker in row.get("blockers", []) if str(blocker)
            )
            lines.append(
                f"| `{row.get('criterion_id', '')}` | "
                f"`{row.get('component_id', '')}` | "
                f"`{row.get('pass')}` | "
                f"`{json.dumps(row.get('current', {}), ensure_ascii=False, sort_keys=True)}` | "
                f"`{json.dumps(row.get('required', {}), ensure_ascii=False, sort_keys=True)}` | "
                f"{blockers or '`none`'} |"
            )
    phase2_row_closure_matrix = [
        row
        for row in payload.get("phase2_row_closure_matrix", [])
        if isinstance(row, dict)
    ]
    if phase2_row_closure_matrix:
        lines.extend(
            [
                "",
                "## Phase 2 Row Closure Matrix",
                "",
                "| Row Input | Status | Closes Criteria | Components | Materialization Chain |",
                "|---|---|---|---|---|",
            ]
        )
        for row in phase2_row_closure_matrix:
            criteria = ", ".join(
                f"`{criterion}`"
                for criterion in row.get("closes_phase2_criteria", [])
                if str(criterion)
            )
            components = ", ".join(
                f"`{component}`"
                for component in row.get("feeds_components", [])
                if str(component)
            )
            chain = ", ".join(
                f"`{step}`"
                for step in row.get("materialization_chain", [])
                if str(step)
            )
            lines.append(
                f"| `{row.get('row_input_id', '')}` | "
                f"`{row.get('status', '')}` | {criteria} | {components} | "
                f"{chain} |"
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
                "| Row Input | Action | Closes Phase 2 Criteria | Unblocks | Materialization | Direct Adapter |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in missing_actions:
            unblocks = ", ".join(
                f"`{component}`" for component in row.get("unblocks_components", [])
            )
            criteria = ", ".join(
                f"`{criterion}`"
                for criterion in row.get("closes_phase2_criteria", [])
                if str(criterion)
            )
            lines.append(
                f"| `{row.get('row_input_id', '')}` | "
                f"`{row.get('operator_action', '')}` | {criteria} | {unblocks} | "
                f"`{row.get('materialization_command', '')}` | "
                f"`{row.get('direct_adapter_materialization_command', '')}` |"
            )
        runtime_actions = [
            row.get("runtime_action_packet")
            for row in missing_actions
            if isinstance(row.get("runtime_action_packet"), dict)
        ]
        if runtime_actions:
            lines.extend(["", "### Vina/GNINA Runtime Action Packet", ""])
            for action in runtime_actions:
                if not isinstance(action, dict):
                    continue
                commands = action.get("commands")
                if not isinstance(commands, dict):
                    commands = {}
                operator_sequence = ", ".join(
                    f"`{step}`"
                    for step in action.get("operator_sequence", [])
                    if str(step)
                )
                first_case_slot = _as_dict(
                    action.get("first_blocked_case_input_slot")
                )
                first_engine_slot = _as_dict(
                    action.get("first_blocked_engine_run_slot")
                )
                first_operator_blocker_family = _as_dict(
                    action.get("first_operator_blocker_family")
                )
                operator_blocker_families = [
                    row
                    for row in _as_list(action.get("operator_blocker_family_plan"))
                    if isinstance(row, dict)
                ]
                manifest_completion_plan = [
                    row
                    for row in action.get(
                        "input_manifest_completion_action_plan", []
                    )
                    if isinstance(row, dict)
                ]
                first_manifest_completion_action = (
                    manifest_completion_plan[0] if manifest_completion_plan else {}
                )
                lines.extend(
                    [
                        f"- `status`: `{action.get('status')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `input_manifest_template_preflight_artifact`: `{action.get('input_manifest_template_preflight_artifact')}`",
                        f"- `rows_template_preflight_artifact`: `{action.get('rows_template_preflight_artifact')}`",
                        f"- `input_manifest_completion_action_case_count`: `{action.get('input_manifest_completion_action_case_count')}`",
                        f"- `input_manifest_completion_blocked_case_count`: `{action.get('input_manifest_completion_blocked_case_count')}`",
                        f"- `first_input_manifest_completion_action`: `{first_manifest_completion_action.get('case_id', '')}` / `{first_manifest_completion_action.get('operator_completion_action', '')}`",
                        f"- `blocked_case_input_slot_count`: `{action.get('blocked_case_input_slot_count')}`",
                        f"- `first_blocked_case_input_slot`: `{first_case_slot.get('case_id', '')}` / `{first_case_slot.get('operator_action', '')}`",
                        f"- `blocked_engine_run_slot_count`: `{action.get('blocked_engine_run_slot_count')}`",
                        f"- `first_blocked_engine_run_slot`: `{first_engine_slot.get('case_id', '')}` / `{first_engine_slot.get('engine_id', '')}` / `{first_engine_slot.get('docking_run_id', '')}`",
                        f"- `operator_blocker_family_count`: `{action.get('operator_blocker_family_count', 0)}`",
                        f"- `operator_blocker_family_missing_item_count`: `{action.get('operator_blocker_family_missing_item_count', 0)}`",
                        f"- `first_operator_blocker_family`: `{first_operator_blocker_family.get('family_id', '')}` / `{first_operator_blocker_family.get('missing_item_count', '')}`",
                        f"- `first_operator_sequence_step`: `{(action.get('operator_sequence') or [''])[0]}`",
                        f"- `operator_sequence`: {operator_sequence or '`none`'}",
                        f"- `build_input_manifest_template_preflight_command`: `{commands.get('build_input_manifest_template_preflight', '')}`",
                        f"- `build_rows_template_preflight_command`: `{commands.get('build_rows_template_preflight', '')}`",
                        f"- `materialize_adapter_command`: `{commands.get('materialize_adapter', '')}`",
                    ]
                )
                if operator_blocker_families:
                    lines.extend(
                        [
                            "",
                            "#### Vina/GNINA Runtime Blocker Families",
                            "",
                            "| Family | Status | Missing Items | Blocked Cases | Command Key | Materialization Command |",
                            "|---|---|---:|---:|---|---|",
                        ]
                    )
                    for row in operator_blocker_families:
                        lines.append(
                            f"| `{row.get('family_id', '')}` | "
                            f"`{row.get('status', '')}` | "
                            f"{_as_int(row.get('missing_item_count'))} | "
                            f"{_as_int(row.get('blocked_case_count'))} | "
                            f"`{row.get('command_key', '')}` | "
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
                accepted_manifest_formats = ", ".join(
                    f"`{manifest_format}`"
                    for manifest_format in action.get(
                        "accepted_manifest_formats", []
                    )
                    if str(manifest_format)
                )
                supported_manifest_paths = ", ".join(
                    f"`{path}`"
                    for path in action.get("supported_manifest_candidate_paths", [])
                    if str(path)
                )
                manifest_load_errors = ", ".join(
                    f"`{row.get('path')}: {row.get('load_error')}`"
                    for row in action.get("input_manifest_load_errors", [])
                    if isinstance(row, dict) and str(row.get("load_error") or "")
                )
                lines.extend(
                    [
                        f"- `status`: `{action.get('status')}`",
                        f"- `template_artifact`: `{action.get('template_artifact')}`",
                        f"- `expected_manifest_artifact`: `{action.get('expected_manifest_artifact')}`",
                        f"- `default_execution_plan_manifest_path`: `{action.get('default_execution_plan_manifest_path')}`",
                        f"- `recommended_template_dropzone`: `{action.get('recommended_template_dropzone')}`",
                        f"- `recommended_template_dropzone_is_supported_candidate_path`: `{action.get('recommended_template_dropzone_is_supported_candidate_path')}`",
                        f"- `accepted_manifest_formats`: {accepted_manifest_formats or '`none`'}",
                        f"- `supported_manifest_candidate_paths`: {supported_manifest_paths or '`none`'}",
                        f"- `detected_manifest_artifact_count`: `{action.get('detected_manifest_artifact_count')}`",
                        f"- `selected_manifest_path`: `{action.get('selected_manifest_path')}`",
                        f"- `selected_manifest_format`: `{action.get('selected_manifest_format')}`",
                        f"- `input_manifest_row_count`: `{action.get('input_manifest_row_count')}`",
                        f"- `input_manifest_load_errors`: {manifest_load_errors or '`none`'}",
                        f"- `template_to_manifest_command`: `{action.get('template_to_manifest_command')}`",
                        f"- `source_archive_operator_artifact`: `{action.get('source_archive_operator_artifact')}`",
                        f"- `source_archive_extraction_command`: `{action.get('source_archive_extraction_command')}`",
                        f"- `source_archive_extraction_report_artifact`: `{action.get('source_archive_extraction_report_artifact')}`",
                        f"- `verify_execution_plan_command`: `{action.get('verify_execution_plan_command')}`",
                        f"- `verify_runtime_readiness_command`: `{action.get('verify_runtime_readiness_command')}`",
                        f"- `operator_must_fill_or_verify`: {required_fields}",
                        f"- `template_is_not_evidence`: `{safety_policy.get('template_is_not_evidence')}`",
                        f"- `do_not_treat_blank_prepared_checksums_as_ready`: `{safety_policy.get('do_not_treat_blank_prepared_checksums_as_ready')}`",
                    ]
                )
        adapter_preflight_actions = [
            row.get("adapter_row_preflight_action_packet")
            for row in missing_actions
            if isinstance(row.get("adapter_row_preflight_action_packet"), dict)
        ]
        if adapter_preflight_actions:
            lines.extend(["", "### Vina/GNINA Adapter Row Preflight Action", ""])
            for action in adapter_preflight_actions:
                if not isinstance(action, dict):
                    continue
                safety_policy = action.get("template_safety_policy")
                if not isinstance(safety_policy, dict):
                    safety_policy = {}
                supported_paths = ", ".join(
                    f"`{path}`"
                    for path in action.get("supported_candidate_paths", [])
                    if str(path)
                )
                preflight_blockers = ", ".join(
                    f"`{blocker}`"
                    for blocker in action.get("adapter_preflight_blockers", [])
                    if str(blocker)
                )
                role_receipt_summary = action.get("role_receipt_plan_summary")
                if not isinstance(role_receipt_summary, dict):
                    role_receipt_summary = {}
                first_blocked_role = role_receipt_summary.get(
                    "first_blocked_role_receipt"
                )
                if not isinstance(first_blocked_role, dict):
                    first_blocked_role = {}
                lines.extend(
                    [
                        f"- `status`: `{action.get('status')}`",
                        f"- `expected_rows_artifact`: `{action.get('expected_rows_artifact')}`",
                        f"- `row_template_artifact`: `{action.get('row_template_artifact')}`",
                        f"- `row_template_preflight_artifact`: `{action.get('row_template_preflight_artifact')}`",
                        f"- `build_row_template_preflight_command`: `{action.get('build_row_template_preflight_command')}`",
                        f"- `role_receipt_blocked_count`: `{role_receipt_summary.get('role_receipt_blocked_count')}`",
                        f"- `first_blocked_role_receipt`: `{first_blocked_role.get('role_id', '')}` / `{first_blocked_role.get('slot_id', '')}`",
                        f"- `supported_candidate_paths`: {supported_paths}",
                        f"- `detected_row_artifact_count`: `{action.get('detected_row_artifact_count')}`",
                        f"- `selected_path`: `{action.get('selected_path')}`",
                        f"- `adapter_preflight_status`: `{action.get('adapter_preflight_status')}`",
                        f"- `adapter_preflight_blockers`: {preflight_blockers or '`none`'}",
                        f"- `direct_adapter_materialization_command`: `{action.get('direct_adapter_materialization_command')}`",
                        f"- `operator_rows_must_be_real_engine_outputs`: `{safety_policy.get('operator_rows_must_be_real_engine_outputs')}`",
                        f"- `preflight_does_not_run_engines`: `{safety_policy.get('preflight_does_not_run_engines')}`",
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
    case_input_slot_matrix = [
        row
        for row in payload["vina_gnina_runtime_readiness"].get(
            "case_input_slot_matrix", []
        )
        if isinstance(row, dict)
    ]
    if case_input_slot_matrix:
        lines.extend(
            [
                "### Vina/GNINA Case Input Slots",
                "",
                "| Slot | Case | Complex | Status | Action | Blockers |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in case_input_slot_matrix:
            blockers = ", ".join(
                f"`{blocker}`" for blocker in row.get("blockers", []) if str(blocker)
            )
            lines.append(
                f"| `{row.get('slot_id', '')}` | `{row.get('case_id', '')}` | "
                f"`{row.get('complex_id', '')}` | `{row.get('status', '')}` | "
                f"`{row.get('operator_action', '')}` | {blockers or '`none`'} |"
            )
        lines.append("")
    engine_run_slot_matrix = [
        row
        for row in payload["vina_gnina_runtime_readiness"].get(
            "engine_run_slot_matrix", []
        )
        if isinstance(row, dict)
    ]
    if engine_run_slot_matrix:
        lines.extend(
            [
                "### Vina/GNINA Engine Run Slots",
                "",
                "| Slot | Case | Engine | Status | Actions | Blockers |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in engine_run_slot_matrix:
            actions = ", ".join(
                f"`{action}`"
                for action in row.get("operator_actions", [])
                if str(action)
            )
            blockers = ", ".join(
                f"`{blocker}`" for blocker in row.get("blockers", []) if str(blocker)
            )
            lines.append(
                f"| `{row.get('slot_id', '')}` | `{row.get('case_id', '')}` | "
                f"`{row.get('engine_id', '')}` | `{row.get('status', '')}` | "
                f"{actions} | {blockers or '`none`'} |"
            )
        lines.append("")
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
    lines.extend(["", "## Source Access Preflight", ""])
    lines.extend(
        [
            "- `receipt_artifact`: "
            f"`{payload['official_source_receipt_plan']['source_access_preflight_receipt_artifact']}`",
            "- `receipt_command`: "
            f"`{payload['official_source_receipt_plan']['source_access_preflight_receipt_command']}`",
            "- `network_probe_command`: "
            f"`{payload['official_source_receipt_plan']['source_access_network_probe_command']}`",
            "",
        ]
    )
    lines.extend(
        [
            "| Source | Access Mode | Primary Probe | Fallback Probe |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["official_source_receipt_plan"][
        "source_access_preflight_rows"
    ]:
        lines.append(
            f"| `{row['source_id']}` | `{row['access_mode']}` | "
            f"`{row['primary_head_command']}` | "
            f"`{row['fallback_head_command']}` |"
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
