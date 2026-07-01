#!/usr/bin/env python3
"""Build a blocked Phase 3 OpenSees medium scorecard readiness receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase3_medium_model_scorecard_readiness_receipt.json"
SOURCE_LICENSE_RECEIPT = PRODUCTIZATION / "phase3_opensees_medium_source_license_receipt.json"
MEDIUM_RECEIPT_DIR = PRODUCTIZATION / "medium_model_scorecard_receipts"
MEDIUM_RECEIPT_SCHEMA_VERSION = "phase3-medium-model-scorecard-receipt.v1"
NORMALIZATION_RECEIPT_SCHEMA_VERSION = "phase3-medium-normalization-receipt.v1"
NORMALIZATION_MIN_MAPPING_COVERAGE = 0.99
ACCEPTED_SCORECARD_OR_REVIEW_DECISIONS = {"PASS", "APPROVED_REVIEW"}
MEDIUM_MODEL_INPUTS = [
    Path("implementation/phase1/opensees_topology_report.json"),
    Path("implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"),
    SOURCE_LICENSE_RECEIPT,
    MEDIUM_RECEIPT_DIR,
    Path("scripts/build_phase3_opensees_source_license_receipt.py"),
    Path("scripts/build_phase3_medium_model_scorecard_readiness_receipt.py"),
    Path("scripts/run_phase3_medium_model_scorecard_receipt.py"),
    Path("src/structural_analysis/benchmark/acquisition.py"),
]
RUNNER_SCRIPT = Path("scripts/run_phase3_medium_model_scorecard_receipt.py")
RUNNER_COMMAND_TEMPLATE = (
    "python3 scripts/run_phase3_medium_model_scorecard_receipt.py "
    "--model OPERATOR_ATTACHED_MODEL.json "
    "--source-id OPERATOR_ATTACHED_SOURCE_ID "
    "--case-id OPERATOR_ATTACHED_CASE_ID "
    "--source-sha256 OPERATOR_ATTACHED_SHA256 "
    "--scorecard-or-review OPERATOR_ATTACHED_SCORECARD_OR_REVIEW.json "
    "--out implementation/phase1/release_evidence/productization/"
    "medium_model_scorecard_receipts/OPERATOR_ATTACHED_CASE_ID.scorecard_receipt.json "
    "--result-out implementation/phase1/release_evidence/productization/"
    "medium_model_scorecard_receipts/OPERATOR_ATTACHED_CASE_ID.result.json "
    "--report-out implementation/phase1/release_evidence/productization/"
    "medium_model_scorecard_receipts/OPERATOR_ATTACHED_CASE_ID.validation_report.json "
    "--analysis-type model_health --fail-blocked"
)
RESOURCE_ENVELOPE = {
    "default_timeout_seconds": 3600,
    "default_memory_limit_gb": 32.0,
    "artifact_retention_policy": "operator_attached_scorecard_receipt_result_and_validation_report",
    "execution_scope": "operator_workstation_or_scheduled_self_hosted_runner",
}
REQUIRED_EVIDENCE = (
    {
        "id": "authoritative_source",
        "required": "Verified upstream source URL or DOI for each selected medium model.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "source_url_verification_pending",
    },
    {
        "id": "license_approval",
        "required": "License review for local execution, redistribution boundary, and commercial-use boundary.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "license_review_pending",
    },
    {
        "id": "local_candidate_parser_boundary",
        "required": "Local checksum/topology evidence recorded as parser-only, not benchmark pass evidence.",
        "status": "parser_only_ready",
        "contract_pass": True,
        "blocker": "",
    },
    {
        "id": "reference_outputs",
        "required": "Reference displacement/reaction/member/modal outputs or approved REVIEW baseline.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "reference_outputs_missing",
    },
    {
        "id": "canonical_normalization",
        "required": "Canonical model normalization with units, coordinates, and mapping coverage.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "normalization_receipts_missing",
    },
    {
        "id": "scorecard_execution",
        "required": "OpenSees medium scorecard execution retaining residual, increment, and convergence history.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "opensees_medium_scorecard_execution_missing",
    },
    {
        "id": "pass_or_approved_review",
        "required": "Per-case PASS or explicit pre-approved REVIEW decision for selected medium models.",
        "status": "missing",
        "contract_pass": False,
        "blocker": "medium_model_pass_or_review_missing",
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "source_commit_sha"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _try_load_json(path: Path) -> dict[str, Any]:
    try:
        return _load_json(path)
    except Exception:
        return {}


def _receipt_files(repo_root: Path, receipt_dir: Path) -> list[Path]:
    resolved = receipt_dir if receipt_dir.is_absolute() else repo_root / receipt_dir
    if not resolved.exists():
        return []
    return sorted(path for path in resolved.glob("*.scorecard_receipt.json") if path.is_file())


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_receipt_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_decision(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _scorecard_or_review_status(repo_root: Path, receipt_ref: str) -> dict[str, Any]:
    if not receipt_ref:
        return {
            "path": "",
            "present": False,
            "contract_pass": False,
            "decision": "",
            "evidence_ref": "",
            "reviewer": "",
            "blockers": ["scorecard_or_review_missing"],
        }
    path = _resolve_receipt_path(repo_root, receipt_ref)
    if not path.exists():
        return {
            "path": receipt_ref,
            "present": False,
            "contract_pass": False,
            "decision": "",
            "evidence_ref": "",
            "reviewer": "",
            "blockers": ["scorecard_or_review_path_missing"],
        }
    payload = _try_load_json(path)
    decision = _normalized_decision(payload.get("decision") or payload.get("status"))
    evidence_ref = str(
        payload.get("evidence_ref")
        or payload.get("review_evidence_ref")
        or payload.get("scorecard_ref")
        or ""
    ).strip()
    reviewer = str(payload.get("reviewer") or payload.get("approved_by") or "").strip()
    blockers: list[str] = []
    if not payload:
        blockers.append("scorecard_or_review_json_invalid_or_empty")
    if decision not in ACCEPTED_SCORECARD_OR_REVIEW_DECISIONS:
        blockers.append("scorecard_or_review_decision_not_accepted")
    if not evidence_ref:
        blockers.append("scorecard_or_review_evidence_ref_missing")
    if not reviewer:
        blockers.append("scorecard_or_review_reviewer_missing")
    return {
        "path": _relative_path(repo_root, path),
        "present": True,
        "contract_pass": not blockers,
        "decision": decision,
        "evidence_ref": evidence_ref,
        "reviewer": reviewer,
        "blockers": blockers,
    }


def _normalization_receipt_status(
    repo_root: Path,
    *,
    case_id: str,
    receipt_ref: str,
) -> dict[str, Any]:
    if not receipt_ref:
        return {
            "path": "",
            "present": False,
            "contract_pass": False,
            "blockers": ["normalization_receipt_missing"],
        }
    path = _resolve_receipt_path(repo_root, receipt_ref)
    if not path.exists():
        return {
            "path": receipt_ref,
            "present": False,
            "contract_pass": False,
            "blockers": ["normalization_receipt_missing"],
        }
    payload = _try_load_json(path)
    mapping_coverage = _safe_dict(payload.get("mapping_coverage"))
    node_coverage = max(
        _as_float(mapping_coverage.get("node")),
        _as_float(payload.get("node_mapping_coverage")),
    )
    member_coverage = max(
        _as_float(mapping_coverage.get("member")),
        _as_float(payload.get("member_mapping_coverage")),
    )
    blockers: list[str] = []
    if payload.get("schema_version") != NORMALIZATION_RECEIPT_SCHEMA_VERSION:
        blockers.append("normalization_receipt_schema_mismatch")
    if payload.get("contract_pass") is not True:
        blockers.append("normalization_receipt_contract_not_passed")
    receipt_case_id = str(payload.get("case_id") or "")
    if receipt_case_id and receipt_case_id != case_id:
        blockers.append("normalization_receipt_case_id_mismatch")
    if not _safe_dict(payload.get("units")):
        blockers.append("normalization_units_missing")
    if not (payload.get("coordinate_transform") or payload.get("coordinate_mapping")):
        blockers.append("normalization_coordinate_mapping_missing")
    if node_coverage < NORMALIZATION_MIN_MAPPING_COVERAGE:
        blockers.append("normalization_node_mapping_coverage_below_minimum")
    if member_coverage < NORMALIZATION_MIN_MAPPING_COVERAGE:
        blockers.append("normalization_member_mapping_coverage_below_minimum")
    return {
        "path": _relative_path(repo_root, path),
        "present": True,
        "contract_pass": not blockers,
        "schema_version": payload.get("schema_version"),
        "case_id": receipt_case_id,
        "node_mapping_coverage": node_coverage,
        "member_mapping_coverage": member_coverage,
        "blockers": blockers,
    }


def _medium_scorecard_receipt_inventory(repo_root: Path) -> dict[str, Any]:
    receipt_rows: list[dict[str, Any]] = []
    valid_scorecard_case_ids: set[str] = set()
    pass_or_review_case_ids: set[str] = set()
    valid_normalization_case_ids: set[str] = set()
    for path in _receipt_files(repo_root, MEDIUM_RECEIPT_DIR):
        payload = _try_load_json(path)
        relative_path = _relative_path(repo_root, path)
        schema_pass = payload.get("schema_version") == MEDIUM_RECEIPT_SCHEMA_VERSION
        case_id = str(payload.get("case_id") or path.stem)
        blockers = [str(blocker) for blocker in _safe_list(payload.get("blockers")) if str(blocker)]
        contract_pass = bool(payload.get("contract_pass") is True)
        validation_pass = bool(payload.get("validation_contract_pass") is True)
        crashed = bool(payload.get("crashed") is True)
        oom = bool(payload.get("oom") is True)
        scorecard_or_review_path = str(payload.get("scorecard_or_review_path") or "")
        scorecard_or_review_status = _scorecard_or_review_status(
            repo_root,
            scorecard_or_review_path,
        )
        reference_output_sha256 = str(payload.get("reference_output_sha256") or "")
        normalization_receipt = str(payload.get("normalization_receipt") or "")
        normalization_status = _normalization_receipt_status(
            repo_root,
            case_id=case_id,
            receipt_ref=normalization_receipt,
        )
        scorecard_execution_pass = bool(
            schema_pass
            and contract_pass
            and validation_pass
            and not crashed
            and not oom
        )
        pass_or_review_pass = bool(
            scorecard_execution_pass and scorecard_or_review_status["contract_pass"]
        )
        if scorecard_execution_pass:
            valid_scorecard_case_ids.add(case_id)
        if pass_or_review_pass:
            pass_or_review_case_ids.add(case_id)
        if normalization_status["contract_pass"]:
            valid_normalization_case_ids.add(case_id)
        receipt_rows.append(
            {
                "path": relative_path,
                "schema_pass": schema_pass,
                "case_id": case_id,
                "contract_pass": contract_pass,
                "validation_contract_pass": validation_pass,
                "crashed": crashed,
                "oom": oom,
                "scorecard_or_review_path": scorecard_or_review_path,
                "scorecard_or_review_contract_pass": scorecard_or_review_status["contract_pass"],
                "scorecard_or_review_status": scorecard_or_review_status,
                "reference_output_sha256": reference_output_sha256,
                "normalization_receipt": normalization_receipt,
                "normalization_receipt_contract_pass": normalization_status["contract_pass"],
                "normalization_receipt_status": normalization_status,
                "scorecard_execution_pass": scorecard_execution_pass,
                "pass_or_approved_review": pass_or_review_pass,
                "blockers": blockers,
            }
        )
    return {
        "schema_version": "phase3-medium-model-scorecard-receipt-inventory.v1",
        "receipt_directory": MEDIUM_RECEIPT_DIR.as_posix(),
        "receipt_file_count": len(receipt_rows),
        "valid_scorecard_case_count": len(valid_scorecard_case_ids),
        "pass_or_approved_review_count": len(pass_or_review_case_ids),
        "valid_normalization_case_count": len(valid_normalization_case_ids),
        "receipts": receipt_rows,
        "claim_boundary": (
            "Only operator-attached medium scorecard receipts with the expected schema, "
            "contract_pass=true, validation_contract_pass=true, and no crash/OOM are "
            "counted. This inventory does not create source, license, reference-output, "
            "or normalization evidence."
        ),
    }


def _scorecard_evidence_row(row: dict[str, Any], *, current: int, required: int) -> dict[str, Any]:
    enriched = dict(row)
    ready = current >= required
    enriched.update(
        {
            "status": "ready" if ready else ("partial" if current else "missing"),
            "contract_pass": ready,
            "blocker": "" if ready else row["blocker"],
            "current_scorecard_receipt_count": current,
            "required_scorecard_receipt_count": required,
        }
    )
    return enriched


def _pass_review_evidence_row(row: dict[str, Any], *, current: int, required: int) -> dict[str, Any]:
    enriched = dict(row)
    ready = current >= required
    enriched.update(
        {
            "status": "ready" if ready else ("partial" if current else "missing"),
            "contract_pass": ready,
            "blocker": "" if ready else row["blocker"],
            "current_pass_or_approved_review_count": current,
            "required_pass_or_approved_review_count": required,
        }
    )
    return enriched


def _normalization_evidence_row(row: dict[str, Any], *, current: int, required: int) -> dict[str, Any]:
    enriched = dict(row)
    ready = current >= required
    enriched.update(
        {
            "status": "ready" if ready else ("partial" if current else "missing"),
            "contract_pass": ready,
            "blocker": "" if ready else row["blocker"],
            "current_normalization_receipt_count": current,
            "required_normalization_receipt_count": required,
            "schema_version_required": NORMALIZATION_RECEIPT_SCHEMA_VERSION,
            "minimum_node_mapping_coverage": NORMALIZATION_MIN_MAPPING_COVERAGE,
            "minimum_member_mapping_coverage": NORMALIZATION_MIN_MAPPING_COVERAGE,
            "claim_boundary": (
                "The normalization contract is implemented as a receipt validator. "
                "This row still requires one valid operator-attached normalization "
                "receipt per selected medium case before it can pass."
            ),
        }
    )
    return enriched


def _missing_evidence_breakdown(
    evidence_rows: list[dict[str, Any]],
    *,
    required_medium_model_count: int,
    current_scorecard_count: int,
    pass_or_approved_review_count: int,
    normalization_receipt_count: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in evidence_rows:
        if row.get("contract_pass") is True:
            continue
        row_id = str(row.get("id") or "")
        item: dict[str, Any] = {
            "id": row_id,
            "status": str(row.get("status") or "missing"),
            "blocker": str(row.get("blocker") or ""),
            "required": str(row.get("required") or ""),
            "evidence_type": "operator_attached",
        }
        if row_id == "license_approval":
            item.update(
                {
                    "evidence_type": "product_legal_review",
                    "source_license_receipt_path": SOURCE_LICENSE_RECEIPT.as_posix(),
                    "license_review_status": str(row.get("license_review_status") or ""),
                    "spdx": str(row.get("spdx") or ""),
                }
            )
        elif row_id == "reference_outputs":
            item.update(
                {
                    "required_case_count": required_medium_model_count,
                    "current_case_count": 0,
                    "remaining_case_count": required_medium_model_count,
                    "required_artifacts": [
                        "reference displacement/reaction/member/modal outputs",
                        "reference output checksum per selected case",
                        "approved REVIEW baseline when exact reference output is unavailable",
                    ],
                }
            )
        elif row_id == "canonical_normalization":
            item.update(
                {
                    "required_case_count": required_medium_model_count,
                    "current_case_count": normalization_receipt_count,
                    "remaining_case_count": max(
                        required_medium_model_count - normalization_receipt_count,
                        0,
                    ),
                    "schema_version_required": NORMALIZATION_RECEIPT_SCHEMA_VERSION,
                    "minimum_mapping_coverage": NORMALIZATION_MIN_MAPPING_COVERAGE,
                    "required_artifacts": [
                        "canonical units and coordinate mapping",
                        "node/member mapping coverage",
                        "normalization receipt per selected case",
                    ],
                }
            )
        elif row_id == "scorecard_execution":
            item.update(
                {
                    "required_case_count": required_medium_model_count,
                    "current_case_count": current_scorecard_count,
                    "remaining_case_count": max(required_medium_model_count - current_scorecard_count, 0),
                    "runner_command_template": RUNNER_COMMAND_TEMPLATE,
                    "receipt_directory": MEDIUM_RECEIPT_DIR.as_posix(),
                }
            )
        elif row_id == "pass_or_approved_review":
            item.update(
                {
                    "required_case_count": required_medium_model_count,
                    "current_case_count": pass_or_approved_review_count,
                    "remaining_case_count": max(
                        required_medium_model_count - pass_or_approved_review_count,
                        0,
                    ),
                    "accepted_decisions": ["PASS", "APPROVED_REVIEW"],
                }
            )
        rows.append(item)
    return rows


def _operator_next_actions(
    blockers: list[str],
    *,
    required_medium_model_count: int,
    local_candidate_count: int,
    current_scorecard_count: int,
    pass_or_approved_review_count: int,
) -> list[dict[str, Any]]:
    blocker_set = set(blockers)
    actions: list[dict[str, Any]] = []
    if local_candidate_count < required_medium_model_count:
        actions.append(
            {
                "id": "select_additional_medium_model_cases",
                "owner": "benchmark_operator",
                "action": (
                    "Select and attach additional authoritative medium structural "
                    "model cases until the RC medium-model set reaches five cases."
                ),
                "clears_blockers": [
                    (
                        "medium_structural_models_current_below_required:"
                        f"{local_candidate_count}/{required_medium_model_count}"
                    )
                ],
                "current_candidate_case_count": local_candidate_count,
                "required_candidate_case_count": required_medium_model_count,
                "remaining_case_count": max(
                    required_medium_model_count - local_candidate_count,
                    0,
                ),
                "evidence_artifacts": [
                    "implementation/phase1/release/benchmark_expansion/"
                    "opensees_canonical_breadth_report.json",
                    "operator-attached source/license/reference/normalization rows "
                    "for each added case",
                ],
                "validation_commands": [
                    "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
                    "python3 scripts/build_phase6_benchmark_scale_status.py --check",
                    "python3 scripts/build_developer_preview_rc_status.py --check",
                ],
            }
        )
    if "license_review_pending" in blocker_set:
        actions.append(
            {
                "id": "complete_product_legal_license_review",
                "owner": "product_legal",
                "action": (
                    "Update the OpenSees medium source license receipt with approved "
                    "redistribution and commercial-use boundaries."
                ),
                "clears_blockers": ["license_review_pending"],
                "evidence_artifacts": [SOURCE_LICENSE_RECEIPT.as_posix()],
                "validation_commands": [
                    "python3 scripts/build_phase3_opensees_source_license_receipt.py --check",
                    "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
                ],
            }
        )
    if "reference_outputs_missing" in blocker_set:
        actions.append(
            {
                "id": "attach_medium_reference_outputs",
                "owner": "benchmark_operator",
                "action": (
                    "Attach reference outputs or approved REVIEW baselines for the five "
                    "selected medium structural models."
                ),
                "clears_blockers": ["reference_outputs_missing"],
                "remaining_case_count": required_medium_model_count,
                "evidence_artifacts": [
                    "OPERATOR_ATTACHED_REFERENCE_OUTPUTS",
                    "OPERATOR_ATTACHED_REFERENCE_OUTPUT_SHA256_PER_CASE",
                ],
                "validation_commands": [
                    "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
                ],
            }
        )
    if "normalization_receipts_missing" in blocker_set:
        actions.append(
            {
                "id": "record_medium_canonical_normalization",
                "owner": "benchmark_operator",
                "action": (
                    "Attach one validated medium normalization receipt per selected case, "
                    "including canonical units, coordinate transforms, and node/member "
                    "mapping coverage."
                ),
                "clears_blockers": ["normalization_receipts_missing"],
                "remaining_case_count": required_medium_model_count,
                "schema_version_required": NORMALIZATION_RECEIPT_SCHEMA_VERSION,
                "minimum_mapping_coverage": NORMALIZATION_MIN_MAPPING_COVERAGE,
                "evidence_artifacts": ["OPERATOR_ATTACHED_NORMALIZATION_RECEIPT_PER_CASE"],
                "validation_commands": [
                    "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
                ],
            }
        )
    if "opensees_medium_scorecard_execution_missing" in blocker_set:
        actions.append(
            {
                "id": "run_medium_scorecard_receipts",
                "owner": "benchmark_operator",
                "action": (
                    "Run the medium scorecard receipt command for each selected case and "
                    "retain receipt, result, and validation report artifacts."
                ),
                "clears_blockers": ["opensees_medium_scorecard_execution_missing"],
                "remaining_case_count": max(required_medium_model_count - current_scorecard_count, 0),
                "receipt_directory": MEDIUM_RECEIPT_DIR.as_posix(),
                "runner_command_template": RUNNER_COMMAND_TEMPLATE,
                "validation_commands": [
                    "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
                    "python3 scripts/build_phase6_benchmark_scale_status.py --check",
                    "python3 scripts/build_developer_preview_rc_status.py --check",
                ],
            }
        )
    if "medium_model_pass_or_review_missing" in blocker_set:
        actions.append(
            {
                "id": "attach_medium_pass_or_approved_review_decisions",
                "owner": "benchmark_reviewer",
                "action": (
                    "Attach per-case PASS decisions or explicit pre-approved REVIEW records "
                    "referenced by each scorecard receipt."
                ),
                "clears_blockers": ["medium_model_pass_or_review_missing"],
                "remaining_case_count": max(
                    required_medium_model_count - pass_or_approved_review_count,
                    0,
                ),
                "accepted_decisions": ["PASS", "APPROVED_REVIEW"],
                "validation_commands": [
                    "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
                    "python3 scripts/build_developer_preview_rc_status.py --check",
                ],
            }
        )
    return actions


def _validation_commands() -> list[str]:
    return [
        "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
        "python3 scripts/build_phase6_benchmark_scale_status.py --check",
        "python3 scripts/build_developer_preview_rc_status.py --check",
        "python3 scripts/build_product_readiness_snapshot.py --check",
    ]


def _medium_gate_minimum_evidence(action_id: str) -> list[str]:
    evidence_by_action = {
        "select_additional_medium_model_cases": [
            "five authoritative medium structural model cases selected",
            "each selected case has stable source id and checksum",
            "case selection remains parser-only until reference, normalization, scorecard, and review evidence pass",
        ],
        "complete_product_legal_license_review": [
            "source license receipt records approved redistribution boundary",
            "source license receipt records approved commercial-use boundary",
            "license_review_pending is absent from the readiness receipt blockers",
        ],
        "attach_medium_reference_outputs": [
            "reference displacement, reaction, member, or modal outputs attached per selected case",
            "reference output SHA256 or approved REVIEW baseline recorded per selected case",
            "reference_outputs_missing is absent from the readiness receipt blockers",
        ],
        "record_medium_canonical_normalization": [
            f"one {NORMALIZATION_RECEIPT_SCHEMA_VERSION} receipt attached per selected case",
            f"node and member mapping coverage are both >= {NORMALIZATION_MIN_MAPPING_COVERAGE}",
            "normalization_receipts_missing is absent from the readiness receipt blockers",
        ],
        "run_medium_scorecard_receipts": [
            "one scorecard receipt, result artifact, and validation report retained per selected case",
            "receipt records no crash, no OOM, residual formula, and convergence history",
            "opensees_medium_scorecard_execution_missing is absent from the readiness receipt blockers",
        ],
        "attach_medium_pass_or_approved_review_decisions": [
            "each selected case has PASS or APPROVED_REVIEW decision",
            "decision is referenced by the corresponding scorecard receipt",
            "medium_model_pass_or_review_missing is absent from the readiness receipt blockers",
        ],
    }
    return evidence_by_action.get(action_id, [])


def _gate_unblock_plan(
    *,
    operator_next_actions: list[dict[str, Any]],
    validation_commands: list[str],
    contract_pass: bool,
) -> list[dict[str, Any]]:
    if contract_pass:
        return []
    plan: list[dict[str, Any]] = []
    for row in operator_next_actions:
        action_id = str(row.get("id") or "")
        plan.append(
            {
                "slot_id": action_id,
                "owner": str(row.get("owner") or ""),
                "action": str(row.get("action") or ""),
                "clears_blockers": _safe_list(row.get("clears_blockers")),
                "evidence_artifacts": _safe_list(row.get("evidence_artifacts")),
                "remaining_case_count": row.get("remaining_case_count"),
                "minimum_evidence": _medium_gate_minimum_evidence(action_id),
                "validation_commands": _safe_list(row.get("validation_commands")) or validation_commands,
            }
        )
    plan.append(
        {
            "slot_id": "rerun_medium_model_and_dp_rc_checks",
            "owner": "release_engineering",
            "action": "Regenerate medium-model, benchmark-scale, Developer Preview RC, and product readiness receipts.",
            "minimum_evidence": [
                "phase3_medium_model_scorecard_readiness_receipt.json contract_pass=true",
                "phase6_benchmark_scale_status.json no longer reports medium-model blockers",
                "developer_preview_rc_status no longer blocks selected_medium_models_pass_or_approved_review",
                "product_readiness_snapshot remains semantically consistent",
            ],
            "validation_commands": validation_commands,
        }
    )
    return plan


def _case_input_requirements(
    *,
    required_medium_model_count: int,
    current_scorecard_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": "phase3-medium-model-scorecard-case-inputs.v1",
        "required_case_count": required_medium_model_count,
        "current_valid_scorecard_case_count": current_scorecard_count,
        "remaining_case_count": max(required_medium_model_count - current_scorecard_count, 0),
        "case_fields": [
            {
                "field": "model",
                "runner_argument": "--model",
                "required_artifact": "operator-attached normalized structural model JSON",
            },
            {
                "field": "source_id",
                "runner_argument": "--source-id",
                "required_artifact": "stable source identifier tied to the source/license receipt",
            },
            {
                "field": "case_id",
                "runner_argument": "--case-id",
                "required_artifact": "unique selected medium case id",
            },
            {
                "field": "source_sha256",
                "runner_argument": "--source-sha256",
                "required_artifact": "checksum of the attached source/model input",
            },
            {
                "field": "scorecard_or_review_path",
                "runner_argument": "--scorecard-or-review",
                "required_artifact": "PASS scorecard or pre-approved REVIEW record",
            },
            {
                "field": "reference_output_sha256",
                "runner_argument": "receipt_field",
                "required_artifact": "reference output checksum or approved REVIEW baseline",
            },
            {
                "field": "normalization_receipt",
                "runner_argument": "receipt_field",
                "required_artifact": (
                    "units/coordinates/mapping normalization receipt passing "
                    f"{NORMALIZATION_RECEIPT_SCHEMA_VERSION}"
                ),
            },
        ],
        "per_case_outputs": [
            "medium_model_scorecard_receipts/CASE_ID.scorecard_receipt.json",
            "medium_model_scorecard_receipts/CASE_ID.result.json",
            "medium_model_scorecard_receipts/CASE_ID.validation_report.json",
        ],
        "validation_commands": [
            "python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check",
            "python3 scripts/build_phase6_benchmark_scale_status.py --check",
            "python3 scripts/build_developer_preview_rc_status.py --check",
        ],
        "claim_boundary": (
            "These inputs describe the operator handoff contract only. They do not "
            "create model evidence, approve licenses, or close medium benchmark gates."
        ),
    }


def _case_readiness_ledger(
    *,
    canonical_rows: list[dict[str, Any]],
    receipt_inventory: dict[str, Any],
    source_license_receipt: dict[str, Any],
    required_medium_model_count: int,
) -> dict[str, Any]:
    receipts = [
        receipt
        for receipt in _safe_list(receipt_inventory.get("receipts"))
        if isinstance(receipt, dict)
    ]
    receipts_by_case = {str(row.get("case_id") or ""): row for row in receipts}
    source_verified = bool(source_license_receipt.get("source_url_verified") is True)
    license_approved = bool(
        source_license_receipt.get("redistribution_allowed") is True
        and source_license_receipt.get("commercial_use_allowed") is True
        and str(source_license_receipt.get("license_review_status") or "").startswith(
            "approved"
        )
    )
    case_rows: list[dict[str, Any]] = []
    for row in sorted(canonical_rows, key=lambda item: str(item.get("case_id") or "")):
        case_id = str(row.get("case_id") or "")
        receipt = receipts_by_case.get(case_id, {})
        scorecard_execution_pass = bool(
            receipt.get("scorecard_execution_pass") is True
        )
        pass_or_approved_review = bool(
            receipt.get("pass_or_approved_review") is True
        )
        reference_outputs_pass = bool(receipt.get("reference_output_sha256"))
        normalization_pass = bool(receipt.get("normalization_receipt_contract_pass") is True)
        blockers = []
        if source_verified is not True:
            blockers.append("source_url_verification_pending")
        if license_approved is not True:
            blockers.append("license_review_pending")
        if reference_outputs_pass is not True:
            blockers.append("reference_outputs_missing")
        if normalization_pass is not True:
            blockers.append("normalization_receipts_missing")
        if scorecard_execution_pass is not True:
            blockers.append("opensees_medium_scorecard_execution_missing")
        if pass_or_approved_review is not True:
            blockers.append("medium_model_pass_or_review_missing")
        case_rows.append(
            {
                "case_id": case_id,
                "family_id": row.get("family_id"),
                "source_path": row.get("path"),
                "source_sha256": row.get("sha256"),
                "parser_contract_pass": row.get("parser_contract_ready") is True,
                "authoritative_source_pass": source_verified,
                "license_approval_pass": license_approved,
                "reference_outputs_pass": reference_outputs_pass,
                "normalization_pass": normalization_pass,
                "normalization_receipt_status": receipt.get("normalization_receipt_status"),
                "scorecard_execution_pass": scorecard_execution_pass,
                "pass_or_approved_review": pass_or_approved_review,
                "scorecard_receipt_path": receipt.get("path"),
                "blockers": blockers,
                "ready_for_medium_scorecard_credit": not blockers,
            }
        )
    missing_case_count = max(required_medium_model_count - len(case_rows), 0)
    return {
        "schema_version": "phase3-medium-model-case-readiness-ledger.v1",
        "required_case_count": required_medium_model_count,
        "local_candidate_case_count": len(case_rows),
        "missing_candidate_case_count": missing_case_count,
        "case_ready_count": sum(
            1 for row in case_rows if row["ready_for_medium_scorecard_credit"]
        ),
        "case_rows": case_rows,
        "selection_gate": {
            "contract_pass": missing_case_count == 0,
            "current_candidate_case_count": len(case_rows),
            "required_candidate_case_count": required_medium_model_count,
            "blockers": (
                []
                if missing_case_count == 0
                else [
                    (
                        "medium_structural_models_current_below_required:"
                        f"{len(case_rows)}/{required_medium_model_count}"
                    )
                ]
            ),
        },
        "claim_boundary": (
            "This ledger is case-level readiness accounting. It does not create "
            "new source files, license approvals, reference outputs, normalization "
            "receipts, scorecard executions, or PASS/REVIEW decisions."
        ),
    }


def _authoritative_source_evidence_row(
    row: dict[str, Any],
    *,
    source_license_receipt: dict[str, Any],
) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in _safe_list(source_license_receipt.get("source_url_candidates"))
        if isinstance(candidate, dict)
    ]
    source_verified = bool(source_license_receipt.get("source_url_verified") is True)
    upstream_hash_match = any(
        candidate.get("case_id") == "SCBF16B"
        and candidate.get("local_matches_upstream_raw_sha256") is True
        for candidate in candidates
    )
    ready = source_verified and upstream_hash_match
    enriched = dict(row)
    enriched.update(
        {
            "status": "ready" if ready else "missing",
            "contract_pass": ready,
            "blocker": "" if ready else row["blocker"],
            "source_license_receipt_path": SOURCE_LICENSE_RECEIPT.as_posix(),
            "source_url_verified": source_verified,
            "source_url_candidate_count": len(candidates),
            "local_matches_upstream_raw_sha256": upstream_hash_match,
            "claim_boundary": (
                "Authoritative source evidence requires a verified upstream source URL "
                "and matching local/upstream raw checksum. It is separate from license "
                "approval, reference outputs, normalization, and scorecard execution."
            ),
        }
    )
    return enriched


def _license_approval_evidence_row(
    row: dict[str, Any],
    *,
    source_license_receipt: dict[str, Any],
) -> dict[str, Any]:
    license_evidence = _safe_dict(source_license_receipt.get("license_evidence"))
    redistribution_allowed = bool(source_license_receipt.get("redistribution_allowed") is True)
    commercial_use_allowed = bool(source_license_receipt.get("commercial_use_allowed") is True)
    review_status = str(source_license_receipt.get("license_review_status") or "")
    approved = redistribution_allowed and commercial_use_allowed and review_status.startswith("approved")
    identified = bool(license_evidence.get("spdx") or review_status)
    enriched = dict(row)
    enriched.update(
        {
            "status": "ready" if approved else ("identified_review_required" if identified else "missing"),
            "contract_pass": approved,
            "blocker": "" if approved else row["blocker"],
            "source_license_receipt_path": SOURCE_LICENSE_RECEIPT.as_posix(),
            "license_review_status": review_status,
            "spdx": license_evidence.get("spdx", ""),
            "redistribution_allowed": redistribution_allowed,
            "commercial_use_allowed": commercial_use_allowed,
            "claim_boundary": (
                "License identity alone is not product approval. This row passes only when "
                "the receipt records approved redistribution and commercial-use boundaries."
            ),
        }
    )
    return enriched


def build_phase3_medium_model_scorecard_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    topology_report = _load_json(repo_root / "implementation/phase1/opensees_topology_report.json")
    canonical_report = _load_json(
        repo_root / "implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"
    )
    topology_metrics = _safe_dict(topology_report.get("metrics"))
    topology_source = _safe_dict(topology_report.get("source_provenance"))
    canonical_rows = [
        row
        for row in _safe_list(canonical_report.get("rows"))
        if isinstance(row, dict) and row.get("case_id") in {"SCBF16B", "SCBF16B_shell_beam_mix"}
    ]
    source_license_receipt = _try_load_json(repo_root / SOURCE_LICENSE_RECEIPT)
    receipt_inventory = _medium_scorecard_receipt_inventory(repo_root)
    required_medium_model_count = 5
    case_readiness_ledger = _case_readiness_ledger(
        canonical_rows=canonical_rows,
        receipt_inventory=receipt_inventory,
        source_license_receipt=source_license_receipt,
        required_medium_model_count=required_medium_model_count,
    )
    current_scorecard_count = int(receipt_inventory["valid_scorecard_case_count"])
    pass_or_approved_review_count = int(receipt_inventory["pass_or_approved_review_count"])
    normalization_receipt_count = int(receipt_inventory["valid_normalization_case_count"])
    runner_script = repo_root / RUNNER_SCRIPT
    runner_command_ready = runner_script.exists()
    evidence_rows: list[dict[str, Any]] = []
    for row in REQUIRED_EVIDENCE:
        if row["id"] == "authoritative_source":
            evidence_rows.append(
                _authoritative_source_evidence_row(
                    row,
                    source_license_receipt=source_license_receipt,
                )
            )
        elif row["id"] == "license_approval":
            evidence_rows.append(
                _license_approval_evidence_row(
                    row,
                    source_license_receipt=source_license_receipt,
                )
            )
        elif row["id"] == "scorecard_execution":
            evidence_rows.append(
                _scorecard_evidence_row(
                    row,
                    current=current_scorecard_count,
                    required=required_medium_model_count,
                )
            )
        elif row["id"] == "pass_or_approved_review":
            evidence_rows.append(
                _pass_review_evidence_row(
                    row,
                    current=pass_or_approved_review_count,
                    required=required_medium_model_count,
                )
            )
        elif row["id"] == "canonical_normalization":
            evidence_rows.append(
                _normalization_evidence_row(
                    row,
                    current=normalization_receipt_count,
                    required=required_medium_model_count,
                )
            )
        else:
            evidence_rows.append(dict(row))
    evidence_rows.extend(
        [
            {
                "id": "runner_command",
                "required": (
                    "Repeatable medium-model scorecard runner command with selected "
                    "model inputs and output paths."
                ),
                "status": "ready" if runner_command_ready else "missing",
                "contract_pass": runner_command_ready,
                "blocker": "" if runner_command_ready else "opensees_medium_runner_command_missing",
                "runner_command_template": RUNNER_COMMAND_TEMPLATE,
                "runner_script": RUNNER_SCRIPT.as_posix(),
            },
            {
                "id": "resource_envelope",
                "required": (
                    "Declared workstation/nightly CPU, memory, timeout, and artifact "
                    "retention limits for medium scorecard runs."
                ),
                "status": "ready",
                "contract_pass": True,
                "blocker": "",
                "resource_envelope": RESOURCE_ENVELOPE,
            },
        ]
    )
    blockers = sorted({str(row["blocker"]) for row in evidence_rows if str(row.get("blocker", ""))})
    evidence_pass_count = sum(1 for row in evidence_rows if row["contract_pass"] is True)
    missing_evidence = _missing_evidence_breakdown(
        evidence_rows,
        required_medium_model_count=required_medium_model_count,
        current_scorecard_count=current_scorecard_count,
        pass_or_approved_review_count=pass_or_approved_review_count,
        normalization_receipt_count=normalization_receipt_count,
    )
    operator_next_actions = _operator_next_actions(
        blockers,
        required_medium_model_count=required_medium_model_count,
        local_candidate_count=len(canonical_rows),
        current_scorecard_count=current_scorecard_count,
        pass_or_approved_review_count=pass_or_approved_review_count,
    )
    validation_commands = _validation_commands()
    gate_unblock_plan = _gate_unblock_plan(
        operator_next_actions=operator_next_actions,
        validation_commands=validation_commands,
        contract_pass=False,
    )
    summary = {
        "required_medium_model_count": required_medium_model_count,
        "local_candidate_case_count": len(canonical_rows),
        "missing_candidate_case_count": max(required_medium_model_count - len(canonical_rows), 0),
        "current_medium_model_scorecard_count": current_scorecard_count,
        "pass_or_approved_review_count": pass_or_approved_review_count,
        "normalization_receipt_count": normalization_receipt_count,
        "remaining_scorecard_case_count": max(
            required_medium_model_count - current_scorecard_count,
            0,
        ),
        "remaining_pass_or_review_case_count": max(
            required_medium_model_count - pass_or_approved_review_count,
            0,
        ),
        "required_evidence_pass_count": evidence_pass_count,
        "required_evidence_count": len(evidence_rows),
        "runner_command_ready": runner_command_ready,
        "source_url_verified": bool(source_license_receipt.get("source_url_verified") is True),
        "license_review_status": str(source_license_receipt.get("license_review_status") or ""),
    }
    return {
        "schema_version": "phase3-medium-model-scorecard-readiness-receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(MEDIUM_MODEL_INPUTS, repo_root=repo_root),
        "source_id": "opensees_scbf16b_medium_candidate",
        "lanes": ["opensees-medium"],
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "medium_model_benchmark_pass_claim": False,
        "required_medium_model_count": required_medium_model_count,
        "current_medium_model_scorecard_count": current_scorecard_count,
        "pass_or_approved_review_count": pass_or_approved_review_count,
        "scorecard_receipt_inventory": receipt_inventory,
        "local_candidate_artifact_count": len(canonical_rows),
        "case_selection_summary": {
            "required_candidate_case_count": required_medium_model_count,
            "local_candidate_case_count": len(canonical_rows),
            "missing_candidate_case_count": max(required_medium_model_count - len(canonical_rows), 0),
            "current_scorecard_credit_count": current_scorecard_count,
            "claim_boundary": (
                "Candidate selection counts parser/topology-ready local source rows only. "
                "Scorecard credit remains zero until reference outputs, normalization "
                "receipts, scorecard execution, and PASS/REVIEW decisions pass."
            ),
        },
        "local_topology_contract_pass": bool(topology_report.get("contract_pass")),
        "source_license_receipt_path": SOURCE_LICENSE_RECEIPT.as_posix(),
        "source_url_verified": bool(source_license_receipt.get("source_url_verified") is True),
        "license_review_status": str(source_license_receipt.get("license_review_status") or ""),
        "required_evidence_count": len(evidence_rows),
        "required_evidence_pass_count": evidence_pass_count,
        "summary": summary,
        "required_evidence": evidence_rows,
        "case_readiness_ledger": case_readiness_ledger,
        "runner_command_ready": runner_command_ready,
        "runner_command_template": RUNNER_COMMAND_TEMPLATE,
        "resource_envelope": RESOURCE_ENVELOPE,
        "local_parser_boundary": {
            "topology_receipt_path": "implementation/phase1/opensees_topology_report.json",
            "topology_contract_pass": bool(topology_report.get("contract_pass")),
            "source_path": topology_source.get("source_path"),
            "source_sha256": topology_source.get("source_sha256"),
            "node_count": topology_metrics.get("node_count"),
            "beam_element_count": topology_metrics.get("beam_element_count"),
            "shell_element_count": topology_metrics.get("shell_element_count"),
            "canonical_candidate_case_ids": sorted(str(row.get("case_id")) for row in canonical_rows),
            "claim_boundary": (
                "Local checksum and topology/parser evidence is retained only as parser input "
                "evidence. It is not reference-output ingest, normalization, medium scorecard "
                "execution, or PASS/REVIEW benchmark evidence."
            ),
        },
        "scorecard_receipt_template": {
            "schema_version": "phase3-medium-model-scorecard-receipt.v1",
            "source_id": "opensees_scbf16b_medium_candidate",
            "case_id": "OPERATOR_ATTACHED_CASE_ID",
            "source_sha256": "OPERATOR_ATTACHED_SHA256",
            "reference_output_sha256": "OPERATOR_ATTACHED_REFERENCE_OUTPUT_SHA256",
            "normalization_receipt": "OPERATOR_ATTACHED_NORMALIZATION_RECEIPT",
            "runner_command": RUNNER_COMMAND_TEMPLATE,
            "runtime_seconds": "OPERATOR_RECORDED_RUNTIME",
            "peak_memory_gb": "OPERATOR_RECORDED_PEAK_MEMORY",
            "crashed": False,
            "oom": False,
            "metrics": {
                "residual_formula": "F_internal_minus_F_external",
                "convergence_history_retained": True,
                "node_member_mapping_coverage": "OPERATOR_RECORDED_COVERAGE",
            },
            "decision": "PASS|APPROVED_REVIEW",
            "contract_pass": False,
        },
        "normalization_receipt_template": {
            "schema_version": NORMALIZATION_RECEIPT_SCHEMA_VERSION,
            "case_id": "OPERATOR_ATTACHED_CASE_ID",
            "contract_pass": False,
            "units": {
                "length": "m",
                "force": "kN",
            },
            "coordinate_transform": "OPERATOR_RECORDED_TRANSFORM_OR_IDENTITY",
            "mapping_coverage": {
                "node": "OPERATOR_RECORDED_NODE_MAPPING_COVERAGE",
                "member": "OPERATOR_RECORDED_MEMBER_MAPPING_COVERAGE",
            },
            "claim_boundary": (
                "This normalization receipt records units, coordinates, and mapping "
                "coverage only. It is not a reference-output receipt, solver pass, "
                "or benchmark scorecard decision."
            ),
        },
        "missing_evidence_breakdown": missing_evidence,
        "operator_next_actions": operator_next_actions,
        "recommended_next_actions": operator_next_actions,
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "next_actions": [str(row.get("id")) for row in operator_next_actions],
        "validation_commands": validation_commands,
        "case_input_requirements": _case_input_requirements(
            required_medium_model_count=required_medium_model_count,
            current_scorecard_count=current_scorecard_count,
        ),
        "blocked_by": blockers,
        "blockers": blockers,
        "owner_action": (
            "Attach product legal license approval, ingest reference outputs, normalize five "
            "selected medium models, run the medium scorecard, and record PASS or pre-approved "
            "REVIEW rows before promoting this RC gate."
        ),
        "summary_line": (
            "Phase 3 OpenSees medium scorecard readiness: BLOCKED | "
            f"scorecards={current_scorecard_count}/{required_medium_model_count} | "
            f"evidence={evidence_pass_count}/{len(evidence_rows)}"
        ),
        "claim_boundary": (
            "This receipt records the evidence contract for OpenSees medium scorecards. "
            "It preserves local topology/parser evidence as parser-only, reads the source "
            "license receipt for upstream source identity, and implements the operator "
            "scorecard runner command plus normalization receipt validation, but it does "
            "not prove product license approval, reference outputs, attached normalization "
            "receipts, scorecard execution, PASS/REVIEW decisions, Phase 3 closure, or DP "
            "RC readiness."
        ),
    }


def write_phase3_medium_model_scorecard_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase3_medium_model_scorecard_readiness_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_medium_model_scorecard_readiness_receipt(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase3_medium_model_scorecard_readiness_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, f"phase3_medium_model_scorecard_readiness_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase3_medium_model_scorecard_readiness_mismatch"
    return True, "phase3_medium_model_scorecard_readiness_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_medium_model_scorecard_readiness_receipt(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 medium-model scorecard readiness check: {message}")
        return 0 if ok else 1
    payload = write_phase3_medium_model_scorecard_readiness_receipt(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
