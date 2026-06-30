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
        "blocker": "normalization_not_implemented",
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
            if key not in {"generated_at"}
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
    return sorted(path for path in resolved.glob("*.json") if path.is_file())


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _medium_scorecard_receipt_inventory(repo_root: Path) -> dict[str, Any]:
    receipt_rows: list[dict[str, Any]] = []
    valid_scorecard_case_ids: set[str] = set()
    pass_or_review_case_ids: set[str] = set()
    for path in _receipt_files(repo_root, MEDIUM_RECEIPT_DIR):
        payload = _try_load_json(path)
        relative_path = path.relative_to(repo_root).as_posix() if path.is_relative_to(repo_root) else path.as_posix()
        schema_pass = payload.get("schema_version") == MEDIUM_RECEIPT_SCHEMA_VERSION
        case_id = str(payload.get("case_id") or path.stem)
        blockers = [str(blocker) for blocker in _safe_list(payload.get("blockers")) if str(blocker)]
        contract_pass = bool(payload.get("contract_pass") is True)
        validation_pass = bool(payload.get("validation_contract_pass") is True)
        crashed = bool(payload.get("crashed") is True)
        oom = bool(payload.get("oom") is True)
        scorecard_or_review_path = str(payload.get("scorecard_or_review_path") or "")
        scorecard_execution_pass = bool(
            schema_pass
            and contract_pass
            and validation_pass
            and not crashed
            and not oom
        )
        pass_or_review_pass = bool(scorecard_execution_pass and scorecard_or_review_path)
        if scorecard_execution_pass:
            valid_scorecard_case_ids.add(case_id)
        if pass_or_review_pass:
            pass_or_review_case_ids.add(case_id)
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


def _missing_evidence_breakdown(
    evidence_rows: list[dict[str, Any]],
    *,
    required_medium_model_count: int,
    current_scorecard_count: int,
    pass_or_approved_review_count: int,
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
                    "current_case_count": 0,
                    "remaining_case_count": required_medium_model_count,
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
    current_scorecard_count: int,
    pass_or_approved_review_count: int,
) -> list[dict[str, Any]]:
    blocker_set = set(blockers)
    actions: list[dict[str, Any]] = []
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
    if "normalization_not_implemented" in blocker_set:
        actions.append(
            {
                "id": "record_medium_canonical_normalization",
                "owner": "benchmark_operator",
                "action": (
                    "Record units, coordinate transforms, node/member mapping coverage, "
                    "and normalization receipt paths for all selected medium cases."
                ),
                "clears_blockers": ["normalization_not_implemented"],
                "remaining_case_count": required_medium_model_count,
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
                "required_artifact": "units/coordinates/mapping normalization receipt",
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
    current_scorecard_count = int(receipt_inventory["valid_scorecard_case_count"])
    pass_or_approved_review_count = int(receipt_inventory["pass_or_approved_review_count"])
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
    )
    operator_next_actions = _operator_next_actions(
        blockers,
        required_medium_model_count=required_medium_model_count,
        current_scorecard_count=current_scorecard_count,
        pass_or_approved_review_count=pass_or_approved_review_count,
    )
    summary = {
        "required_medium_model_count": required_medium_model_count,
        "current_medium_model_scorecard_count": current_scorecard_count,
        "pass_or_approved_review_count": pass_or_approved_review_count,
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
        "local_topology_contract_pass": bool(topology_report.get("contract_pass")),
        "source_license_receipt_path": SOURCE_LICENSE_RECEIPT.as_posix(),
        "source_url_verified": bool(source_license_receipt.get("source_url_verified") is True),
        "license_review_status": str(source_license_receipt.get("license_review_status") or ""),
        "required_evidence_count": len(evidence_rows),
        "required_evidence_pass_count": evidence_pass_count,
        "summary": summary,
        "required_evidence": evidence_rows,
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
        "missing_evidence_breakdown": missing_evidence,
        "operator_next_actions": operator_next_actions,
        "recommended_next_actions": operator_next_actions,
        "next_actions": [str(row.get("id")) for row in operator_next_actions],
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
            "scorecard runner command, but it does not prove product license approval, "
            "reference outputs, normalization, scorecard execution, PASS/REVIEW decisions, "
            "Phase 3 closure, or DP RC readiness."
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
