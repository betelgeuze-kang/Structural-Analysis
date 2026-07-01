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
SCHEMA_VERSION = "science-actual-closure-operator-handoff.v1"
EXPECTED_ROW_INPUTS = (
    "subset_rows",
    "pose_rows",
    "enrichment_rows",
    "vina_gnina_rows",
    "gpcr_rows",
    "pocketmd_rows",
)
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


def _slot(row: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    row_input_id = str(row.get("row_input_id") or "")
    missing = bool(row.get("missing"))
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
    slots = sorted(
        [
            _slot(row, _as_dict(contracts.get(str(row.get("row_input_id") or ""))))
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
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_science_actual_closure_operator_handoff.py"),
                audit_path,
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
        },
        "missing_row_inputs": [
            str(slot.get("row_input_id") or "") for slot in missing_slots
        ],
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
        "| Row Input | Status | Preferred Path | Closes Criteria | Action |",
        "| --- | --- | --- | --- | --- |",
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
            f"`{criteria}` | "
            f"`{slot.get('operator_action')}` |"
        )
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
