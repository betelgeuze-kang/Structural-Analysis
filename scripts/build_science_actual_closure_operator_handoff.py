#!/usr/bin/env python3
"""Build a one-page operator handoff for science actual-closure row inputs."""

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


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_AUDIT = PRODUCTIZATION / "science_actual_closure_row_audit.json"
DEFAULT_OUT = PRODUCTIZATION / "science_actual_closure_operator_handoff.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_POCKETMD_REFINEMENT_PLAN = (
    PRODUCTIZATION / "pocketmd_lite_refinement_execution_plan.json"
)
SCHEMA_VERSION = "science-actual-closure-operator-handoff.v1"
EXPECTED_ROW_INPUTS = (
    "subset_rows",
    "pose_rows",
    "enrichment_rows",
    "vina_gnina_rows",
    "gpcr_rows",
    "pocketmd_rows",
)
DEFAULT_ROW_TEMPLATE_ARTIFACTS = {
    "subset_rows": PRODUCTIZATION / "public_benchmark_subset_rows_template.csv",
    "pose_rows": PRODUCTIZATION / "public_benchmark_pose_rows_template.csv",
    "enrichment_rows": PRODUCTIZATION / "public_benchmark_enrichment_rows_template.csv",
    "vina_gnina_rows": PRODUCTIZATION / "public_benchmark_vina_gnina_rows_template.csv",
    "gpcr_rows": PRODUCTIZATION / "gpcr_hard_decoy_rows_template.csv",
    "pocketmd_rows": PRODUCTIZATION / "pocketmd_lite_topk_rows_template.csv",
}
FIELD_GROUP_KEYS = (
    "required_case_fields",
    "required_context_fields",
    "required_pose_fields",
    "required_flat_row_fields",
    "required_target_fields",
    "required_molecule_fields",
    "required_engine_run_fields",
    "required_component_metrics",
    "required_summary_metrics",
    "uncertainty_field_modes",
    "source_receipt_required_fields",
)
POLICY_KEYS = (
    "row_integrity_policy",
    "source_actuality_policy",
    "source_checksum_policy",
    "numeric_value_policy",
    "boolean_label_policy",
    "boolean_value_policy",
    "score_direction_policy",
    "per_row_source_actuality_policy",
    "top_k_row_quality_minimums",
    "raw_row_quality_minimums",
)
ROW_INPUT_UPSTREAM_SOURCE_IDS = {
    "subset_rows": "public_benchmark_phase2",
    "pose_rows": "public_benchmark_phase2",
    "enrichment_rows": "public_benchmark_phase2",
    "vina_gnina_rows": "public_benchmark_phase2",
    "pocketmd_rows": "pocketmd_lite",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _contract_field_groups(contract: dict[str, Any]) -> dict[str, Any]:
    return {key: contract[key] for key in FIELD_GROUP_KEYS if key in contract}


def _contract_policies(contract: dict[str, Any]) -> dict[str, Any]:
    return {key: contract[key] for key in POLICY_KEYS if key in contract}


def _first_default_path(row: dict[str, Any]) -> str:
    candidates = [str(item) for item in _as_list(row.get("default_row_path_candidates"))]
    return candidates[0] if candidates else ""


def _operator_action(row: dict[str, Any]) -> str:
    row_input_id = str(row.get("row_input_id") or "")
    if bool(row.get("missing")):
        default_path = _first_default_path(row)
        if default_path:
            return f"attach_{row_input_id}_at_{default_path}"
        return f"attach_{row_input_id}"
    return f"review_{row_input_id}_materialization"


def _row_template_artifact(row_input_id: str) -> str:
    raw_path = DEFAULT_ROW_TEMPLATE_ARTIFACTS.get(row_input_id)
    return str(raw_path) if raw_path else ""


def _slot_source_context(
    row_input_id: str,
    upstream_source_acquisition: dict[str, Any],
) -> dict[str, Any]:
    source_id = ROW_INPUT_UPSTREAM_SOURCE_IDS.get(row_input_id, "")
    if not source_id:
        return {
            "source_id": "",
            "present": False,
            "status": "",
            "artifact": "",
            "contract_pass": None,
            "blocker_count": 0,
            "blockers": [],
            "summary": {},
            "operator_action": "",
        }
    source = _as_dict(upstream_source_acquisition.get(source_id))
    blockers = [str(item) for item in _as_list(source.get("blockers"))]
    return {
        "source_id": source_id,
        "present": bool(source.get("present")),
        "status": str(source.get("status") or ""),
        "artifact": str(source.get("artifact") or ""),
        "contract_pass": source.get("contract_pass"),
        "blocker_count": int(source.get("blocker_count") or len(blockers)),
        "blockers": blockers,
        "summary": _as_dict(source.get("summary")),
        "operator_action": (
            f"resolve_{source_id}_source_acquisition_blockers"
            if blockers
            else ""
        ),
    }


def _compact_candidate_slot_status(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot_id": str(row.get("slot_id") or ""),
        "case_id": str(row.get("case_id") or ""),
        "top_k_rank": _as_int(row.get("top_k_rank")),
        "status": str(row.get("status") or ""),
        "missing": bool(row.get("missing")),
        "provided": bool(row.get("provided")),
        "operator_action": str(row.get("operator_action") or ""),
        "expected_rows_artifact": str(row.get("expected_rows_artifact") or ""),
        "required_metric_fields": [
            str(item) for item in _as_list(row.get("required_metric_fields"))
        ],
        "required_receipt_fields": [
            str(item) for item in _as_list(row.get("required_receipt_fields"))
        ],
    }


def _pocketmd_top_k_slot_detail(
    refinement_plan: dict[str, Any],
    *,
    artifact: Path,
) -> dict[str, Any]:
    if not refinement_plan:
        return {}
    candidate_slot_statuses = [
        _compact_candidate_slot_status(row)
        for row in _as_list(refinement_plan.get("candidate_slot_statuses"))
        if isinstance(row, dict)
    ]
    summary = _as_dict(refinement_plan.get("top_k_slot_status_summary"))
    return {
        "artifact": str(artifact),
        "status": str(refinement_plan.get("status") or ""),
        "operator_rows_ready": bool(refinement_plan.get("operator_rows_ready")),
        "expected_rows_artifact": str(
            refinement_plan.get("expected_rows_artifact") or ""
        ),
        "required_candidate_slot_count": _as_int(
            refinement_plan.get("required_candidate_slot_count")
        ),
        "missing_candidate_slot_count": _as_int(
            summary.get("missing_candidate_slot_count")
        ),
        "provided_candidate_slot_count": _as_int(
            summary.get("provided_candidate_slot_count")
        ),
        "top_k_slot_status_summary": summary,
        "candidate_slot_statuses": candidate_slot_statuses,
        "first_missing_candidate_slot": _as_dict(
            summary.get("first_missing_candidate_slot")
        ),
        "claim_boundary": str(refinement_plan.get("claim_boundary") or ""),
    }


def _slot(
    row: dict[str, Any],
    contract: dict[str, Any],
    *,
    repo_root: Path,
    upstream_source_acquisition: dict[str, Any],
    row_input_slot_details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    row_input_id = str(row.get("row_input_id") or "")
    missing = bool(row.get("missing"))
    source_context = _slot_source_context(row_input_id, upstream_source_acquisition)
    row_input_slot_detail = _as_dict(row_input_slot_details.get(row_input_id))
    row_template_artifact = _row_template_artifact(row_input_id)
    row_template_path = (
        repo_root / row_template_artifact if row_template_artifact else Path()
    )
    materialization_chain = [
        str(item) for item in _as_list(row.get("materialization_chain"))
    ]
    materialization_command = str(contract.get("materialization_command") or "")
    if not materialization_command:
        materialization_command = (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--fail-blocked"
        )
    return {
        "handoff_id": f"science_actual_closure::{row_input_id}",
        "row_input_id": row_input_id,
        "description": str(row.get("description") or ""),
        "status": "operator_input_required" if missing else "provided",
        "missing": missing,
        "operator_action": _operator_action(row),
        "row_template_artifact": row_template_artifact,
        "row_template_present": bool(
            row_template_artifact and row_template_path.exists()
        ),
        "preferred_default_row_path": _first_default_path(row),
        "default_row_path_candidates": [
            str(item) for item in _as_list(row.get("default_row_path_candidates"))
        ],
        "accepted_formats": [str(item) for item in _as_list(row.get("accepted_formats"))],
        "provided_path": str(row.get("provided_path") or ""),
        "resolved_path": str(row.get("resolved_path") or ""),
        "actual_closure_component_id": str(
            row.get("actual_closure_component_id") or ""
        ),
        "expected_rows_mode": str(row.get("expected_rows_mode") or ""),
        "closes_actual_closure_criteria": [
            str(item) for item in _as_list(row.get("closes_actual_closure_criteria"))
        ],
        "closes_phase2_criteria": [
            str(item) for item in _as_list(row.get("closes_phase2_criteria"))
        ],
        "operator_blockers_if_missing": [
            str(item) for item in _as_list(row.get("operator_blockers_if_missing"))
        ],
        "phase2_operator_blockers_if_missing": [
            str(item)
            for item in _as_list(row.get("phase2_operator_blockers_if_missing"))
        ],
        "upstream_source_id": source_context["source_id"],
        "upstream_source_acquisition": source_context,
        "upstream_source_blockers": source_context["blockers"],
        "source_acquisition_operator_action": source_context["operator_action"],
        "row_input_slot_detail": row_input_slot_detail,
        "row_contract_ref": str(row.get("row_contract_ref") or ""),
        "contract_field_groups": _contract_field_groups(contract),
        "contract_policies": _contract_policies(contract),
        "materialization_chain": materialization_chain,
        "materialization_command": materialization_command,
        "claim_boundary": (
            "This slot records what operator-attached row evidence is needed. "
            "It does not close the science gate until the materializer accepts "
            "the real rows and the source receipt."
        ),
    }


def _slot_order(slot: dict[str, Any]) -> int:
    row_input_id = str(slot.get("row_input_id") or "")
    try:
        return EXPECTED_ROW_INPUTS.index(row_input_id)
    except ValueError:
        return len(EXPECTED_ROW_INPUTS)


def _component_slot_summary(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    component_ids = sorted(
        {
            str(slot.get("actual_closure_component_id") or "")
            for slot in slots
            if str(slot.get("actual_closure_component_id") or "")
        }
    )
    summaries: list[dict[str, Any]] = []
    for component_id in component_ids:
        component_slots = [
            slot
            for slot in slots
            if str(slot.get("actual_closure_component_id") or "") == component_id
        ]
        missing_slots = [slot for slot in component_slots if bool(slot.get("missing"))]
        criteria = []
        for slot in component_slots:
            criteria.extend(
                str(item)
                for item in _as_list(slot.get("closes_actual_closure_criteria"))
            )
        summaries.append(
            {
                "component_id": component_id,
                "slot_count": len(component_slots),
                "missing_slot_count": len(missing_slots),
                "row_input_ids": [
                    str(slot.get("row_input_id") or "") for slot in component_slots
                ],
                "missing_row_input_ids": [
                    str(slot.get("row_input_id") or "") for slot in missing_slots
                ],
                "closes_actual_closure_criteria": sorted(set(criteria)),
            }
        )
    return summaries


def _row_input_materialization_contracts(
    missing_slots: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for slot in missing_slots:
        row_input_id = str(slot.get("row_input_id") or "")
        if not row_input_id:
            continue
        contracts[row_input_id] = {
            "row_input_id": row_input_id,
            "status": str(slot.get("status") or ""),
            "operator_action": str(slot.get("operator_action") or ""),
            "preferred_default_row_path": str(
                slot.get("preferred_default_row_path") or ""
            ),
            "default_row_path_candidates": [
                str(item) for item in _as_list(slot.get("default_row_path_candidates"))
            ],
            "row_template_artifact": str(slot.get("row_template_artifact") or ""),
            "row_template_present": bool(slot.get("row_template_present")),
            "accepted_formats": [
                str(item) for item in _as_list(slot.get("accepted_formats"))
            ],
            "actual_closure_component_id": str(
                slot.get("actual_closure_component_id") or ""
            ),
            "expected_rows_mode": str(slot.get("expected_rows_mode") or ""),
            "materialization_chain": [
                str(item) for item in _as_list(slot.get("materialization_chain"))
            ],
            "materialization_command": str(
                slot.get("materialization_command") or ""
            ),
            "contract_field_groups": _as_dict(slot.get("contract_field_groups")),
            "contract_policies": _as_dict(slot.get("contract_policies")),
            "upstream_source_id": str(slot.get("upstream_source_id") or ""),
            "upstream_source_blockers": [
                str(item) for item in _as_list(slot.get("upstream_source_blockers"))
            ],
            "source_acquisition_operator_action": str(
                slot.get("source_acquisition_operator_action") or ""
            ),
            "row_input_slot_detail": _as_dict(
                slot.get("row_input_slot_detail")
            ),
            "operator_blockers_if_missing": [
                str(item)
                for item in _as_list(slot.get("operator_blockers_if_missing"))
            ],
            "claim_boundary": str(slot.get("claim_boundary") or ""),
        }
    return contracts


def _operator_rows_packet(missing_slots: list[dict[str, Any]]) -> dict[str, Any]:
    contracts = _row_input_materialization_contracts(missing_slots)
    missing_row_inputs = [str(slot.get("row_input_id") or "") for slot in missing_slots]
    return {
        "status": "operator_rows_required" if missing_slots else "ready",
        "missing_row_input_count": len(missing_slots),
        "missing_row_inputs": missing_row_inputs,
        "first_missing_row_input": missing_row_inputs[0] if missing_row_inputs else "",
        "row_input_materialization_contracts": contracts,
        "row_input_contract_count": len(contracts),
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--fail-blocked"
        ),
        "claim_boundary": (
            "This packet summarizes missing operator row inputs only. It does not "
            "promote any science closure until the referenced materializers accept "
            "real rows and source receipts."
        ),
    }


def _blocked_component_operator_actions(
    slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for summary in _component_slot_summary(slots):
        missing_ids = [
            str(item) for item in _as_list(summary.get("missing_row_input_ids"))
        ]
        if not missing_ids:
            continue
        component_slots = [
            slot
            for slot in slots
            if str(slot.get("actual_closure_component_id") or "")
            == str(summary.get("component_id") or "")
            and bool(slot.get("missing"))
        ]
        rows.append(
            {
                "component_id": str(summary.get("component_id") or ""),
                "missing_row_input_ids": missing_ids,
                "operator_actions": [
                    str(slot.get("operator_action") or "") for slot in component_slots
                ],
                "source_acquisition_operator_actions": sorted(
                    {
                        str(slot.get("source_acquisition_operator_action") or "")
                        for slot in component_slots
                        if str(slot.get("source_acquisition_operator_action") or "")
                    }
                ),
                "closes_actual_closure_criteria": [
                    str(item)
                    for item in _as_list(
                        summary.get("closes_actual_closure_criteria")
                    )
                ],
            }
        )
    return rows


def build_science_actual_closure_operator_handoff(
    *,
    repo_root: Path = ROOT,
    audit_path: Path = DEFAULT_AUDIT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    audit = _load_json(repo_root, audit_path)
    row_matrix = [
        row
        for row in _as_list(audit.get("row_closure_matrix"))
        if isinstance(row, dict)
    ]
    contracts = _as_dict(audit.get("row_intake_contracts"))
    upstream_source_acquisition = _as_dict(audit.get("upstream_source_acquisition"))
    upstream_source_blockers = [
        str(item) for item in _as_list(audit.get("upstream_source_blockers"))
    ]
    pocketmd_refinement_plan = _load_json(
        repo_root,
        DEFAULT_POCKETMD_REFINEMENT_PLAN,
    )
    row_input_slot_details = {
        "pocketmd_rows": _pocketmd_top_k_slot_detail(
            pocketmd_refinement_plan,
            artifact=DEFAULT_POCKETMD_REFINEMENT_PLAN,
        )
    }
    slots = sorted(
        [
            _slot(
                row,
                _as_dict(contracts.get(str(row.get("row_input_id") or ""))),
                repo_root=repo_root,
                upstream_source_acquisition=upstream_source_acquisition,
                row_input_slot_details=row_input_slot_details,
            )
            for row in row_matrix
        ],
        key=_slot_order,
    )
    missing_slots = [slot for slot in slots if bool(slot.get("missing"))]
    science_contract_pass = bool(audit.get("contract_pass"))
    if science_contract_pass:
        status = "ready_for_review"
    elif missing_slots:
        status = "operator_rows_required"
    else:
        status = "row_blockers_require_resolution"

    criteria = []
    for slot in slots:
        criteria.extend(
            str(item)
            for item in _as_list(slot.get("closes_actual_closure_criteria"))
        )
    handoff_contract_pass = bool(slots) and not set(EXPECTED_ROW_INPUTS).difference(
        str(slot.get("row_input_id") or "") for slot in slots
    )
    row_template_artifacts = {
        str(slot.get("row_input_id") or ""): str(slot.get("row_template_artifact") or "")
        for slot in slots
        if str(slot.get("row_template_artifact") or "")
    }
    missing_row_template_artifacts = [
        str(slot.get("row_input_id") or "")
        for slot in slots
        if not bool(slot.get("row_template_present"))
    ]
    row_input_materialization_contracts = _row_input_materialization_contracts(
        missing_slots
    )
    operator_rows_packet = _operator_rows_packet(missing_slots)
    blocked_component_operator_actions = _blocked_component_operator_actions(slots)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_science_actual_closure_operator_handoff.py"),
                audit_path,
                DEFAULT_POCKETMD_REFINEMENT_PLAN,
            ],
            reused_evidence=True,
            reuse_policy=(
                "science_actual_closure_operator_handoff_from_row_audit"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": handoff_contract_pass,
        "science_actual_closure_contract_pass": science_contract_pass,
        "science_actual_closure_status": str(audit.get("status") or ""),
        "audit_artifact": str(audit_path),
        "summary": {
            "slot_count": len(slots),
            "expected_slot_count": len(EXPECTED_ROW_INPUTS),
            "missing_slot_count": len(missing_slots),
            "provided_slot_count": len(slots) - len(missing_slots),
            "component_count": len(_component_slot_summary(slots)),
            "closes_actual_closure_criteria_count": len(set(criteria)),
            "science_actual_closure_blocker_count": len(
                _as_list(audit.get("blockers"))
            ),
            "row_template_artifact_count": len(row_template_artifacts),
            "missing_row_template_artifact_count": len(
                missing_row_template_artifacts
            ),
            "upstream_source_context_count": sum(
                1
                for source in upstream_source_acquisition.values()
                if _as_dict(source).get("present")
            ),
            "upstream_source_blocker_count": len(upstream_source_blockers),
            "operator_rows_packet_missing_input_count": operator_rows_packet[
                "missing_row_input_count"
            ],
            "blocked_component_operator_action_count": len(
                blocked_component_operator_actions
            ),
        },
        "upstream_source_acquisition": upstream_source_acquisition,
        "upstream_source_blockers": upstream_source_blockers,
        "row_template_artifacts": row_template_artifacts,
        "missing_row_template_artifacts": missing_row_template_artifacts,
        "missing_row_inputs": [
            str(slot.get("row_input_id") or "") for slot in missing_slots
        ],
        "row_input_materialization_contracts": row_input_materialization_contracts,
        "operator_rows_packet": operator_rows_packet,
        "blocked_component_operator_actions": blocked_component_operator_actions,
        "first_missing_slot": missing_slots[0] if missing_slots else {},
        "operator_next_actions": [
            str(item) for item in _as_list(audit.get("operator_next_actions"))
        ],
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--fail-blocked"
        ),
        "required_actual_closures": [
            str(item) for item in _as_list(audit.get("required_actual_closures"))
        ],
        "component_slot_summary": _component_slot_summary(slots),
        "row_slot_handoffs": slots,
        "row_slot_handoff_count": len(slots),
        "claim_boundary": (
            "This handoff is an operator checklist derived from the science row "
            "audit. It is not actual science evidence and does not close Phase 2, "
            "GPCR hard-decoy, or PocketMD Lite gates without accepted real rows."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = _as_dict(payload.get("summary"))
    lines = [
        "# Science Actual Closure Operator Handoff",
        "",
        f"- `status`: `{payload.get('status')}`",
        f"- `contract_pass`: `{payload.get('contract_pass')}`",
        "- `science_actual_closure_contract_pass`: "
        f"`{payload.get('science_actual_closure_contract_pass')}`",
        f"- `missing_slot_count`: `{summary.get('missing_slot_count')}`",
        f"- `slot_count`: `{summary.get('slot_count')}`",
        "",
        "| Row Input | Status | Preferred Path | CSV Starter | Closes Criteria | Action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for slot in _as_list(payload.get("row_slot_handoffs")):
        if not isinstance(slot, dict):
            continue
        criteria = ", ".join(
            str(item) for item in _as_list(slot.get("closes_actual_closure_criteria"))
        )
        lines.append(
            "| "
            f"`{slot.get('row_input_id')}` | "
            f"`{slot.get('status')}` | "
            f"`{slot.get('preferred_default_row_path')}` | "
            f"`{slot.get('row_template_artifact')}` | "
            f"`{criteria}` | "
            f"`{slot.get('operator_action')}` |"
        )
    operator_rows_packet = _as_dict(payload.get("operator_rows_packet"))
    packet_contracts = _as_dict(
        operator_rows_packet.get("row_input_materialization_contracts")
    )
    if packet_contracts:
        lines.extend(["", "## Missing Row Packet", ""])
        lines.extend(
            [
                "| Row Input | Action | Template | Materialization |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row_input_id, contract in packet_contracts.items():
            if not isinstance(contract, dict):
                continue
            lines.append(
                "| "
                f"`{row_input_id}` | "
                f"`{contract.get('operator_action')}` | "
                f"`{contract.get('row_template_artifact')}` | "
                f"`{contract.get('materialization_command')}` |"
            )
            row_input_detail = _as_dict(contract.get("row_input_slot_detail"))
            top_k_summary = _as_dict(
                row_input_detail.get("top_k_slot_status_summary")
            )
            missing_candidate_slots = [
                item
                for item in _as_list(top_k_summary.get("missing_candidate_slots"))
                if isinstance(item, dict)
            ]
            if missing_candidate_slots:
                lines.extend(["", "### PocketMD Top-k Candidate Slots", ""])
                lines.extend(
                    [
                        "| Slot | Case | Rank | Status | Action |",
                        "| --- | --- | --- | --- | --- |",
                    ]
                )
                for candidate_slot in missing_candidate_slots:
                    lines.append(
                        "| "
                        f"`{candidate_slot.get('slot_id')}` | "
                        f"`{candidate_slot.get('case_id')}` | "
                        f"`{candidate_slot.get('top_k_rank')}` | "
                        "`missing` | "
                        f"`{candidate_slot.get('operator_action')}` |"
                    )
    upstream_source_blockers = [
        str(item) for item in _as_list(payload.get("upstream_source_blockers"))
    ]
    if upstream_source_blockers:
        lines.extend(["", "## Upstream Source Blockers", ""])
        for blocker in upstream_source_blockers:
            lines.append(f"- `{blocker}`")
    lines.extend(
        [
            "",
            "## Materialization",
            "",
            f"```bash\n{payload.get('materialization_command')}\n```",
            "",
            "## Claim Boundary",
            "",
            str(payload.get("claim_boundary") or ""),
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-md", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_science_actual_closure_operator_handoff(
        repo_root=args.repo_root,
        audit_path=args.audit,
    )
    out = args.out if args.out.is_absolute() else args.repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json_text(payload), encoding="utf-8")
    if not args.no_md:
        out_md = (
            args.out_md
            if args.out_md.is_absolute()
            else args.repo_root / args.out_md
        )
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(payload), encoding="utf-8")
    print(
        _json_text(payload).rstrip()
        if args.json
        else (
            "science-actual-closure-operator-handoff: "
            f"{payload['status']} | "
            f"missing={payload['summary']['missing_slot_count']}/"
            f"{payload['summary']['slot_count']}"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
