#!/usr/bin/env python3
"""Build the product capabilities evidence surface."""

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


SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OUT = SURFACE_DIR / "product_capabilities_surface.json"

STRUCTURAL_SURFACE_PATHS = (
    SURFACE_DIR / "element_material_breadth_gate_report.json",
    SURFACE_DIR / "general_fe_contact_benchmark_gate_report.json",
    SURFACE_DIR / "material_constitutive_gate_report.json",
    SURFACE_DIR / "solver_breadth_report.json",
    SURFACE_DIR / "solver_truthfulness_gate_report.json",
    SURFACE_DIR / "steel_composite_constitutive_gate_report.json",
    SURFACE_DIR / "structural_contact_gate_report.json",
    SURFACE_DIR / "surface_interaction_benchmark_gate_report.json",
)

SCHEMA_VERSION = "product-capabilities-surface.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _truthy_contract(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass")
        or payload.get("pass")
        or str(payload.get("status", "")).strip().lower() == "ready"
    )


def _payload_blocked(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("locked") is True
        or payload.get("claim_locked") is True
        or _as_list(payload.get("blockers"))
        or not _truthy_contract(payload)
    )


def _state(payload: dict[str, Any], *, ready_flag: bool | None = None) -> str:
    if ready_flag is not None:
        return "ready" if ready_flag else "blocked"
    return "blocked" if _payload_blocked(payload) else "ready"


def _next_actions(payload: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(payload.get("next_actions"))]


def _blockers(payload: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(payload.get("blockers"))]


def _first_str(values: list[Any]) -> str:
    for value in values:
        text = str(value or "")
        if text:
            return text
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _surface_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return summary if summary else _as_dict(payload.get("readiness_summary"))


def _first_dict(values: list[Any]) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _capability_handoff_slot(summary: dict[str, Any]) -> dict[str, Any]:
    slot = (
        _as_dict(summary.get("first_operator_evidence_gap"))
        or _as_dict(summary.get("first_operator_handoff"))
        or _first_dict(_as_list(summary.get("operator_handoff_queue")))
        or _first_dict(_as_list(summary.get("operator_evidence_gap_register")))
        or _first_dict(_as_list(summary.get("gate_unblock_plan")))
        or _first_dict(_as_list(summary.get("operator_intake_slots")))
        or _first_dict(_as_list(summary.get("operator_target_slots")))
    )
    if not slot:
        return {}
    slot_id = str(slot.get("slot_id") or "")
    queue_match = {}
    for row in _as_list(summary.get("operator_handoff_queue")):
        if not isinstance(row, dict):
            continue
        if slot_id and str(row.get("slot_id") or "") == slot_id:
            queue_match = row
            break
    blocked_criteria = (
        _as_list(slot.get("blocked_tier_beta_criteria"))
        or _as_list(queue_match.get("blocked_tier_beta_criteria"))
        or _as_list(slot.get("blocked_phase3_criteria"))
        or _as_list(queue_match.get("blocked_phase3_criteria"))
        or _as_list(slot.get("blocked_phase4_criteria"))
        or _as_list(queue_match.get("blocked_phase4_criteria"))
        or _as_list(slot.get("blocked_criteria"))
        or _as_list(queue_match.get("blocked_criteria"))
        or _as_list(slot.get("unblocks_tier_beta_criteria"))
        or _as_list(queue_match.get("unblocks_tier_beta_criteria"))
        or _as_list(slot.get("unblocks_phase3_criteria"))
        or _as_list(queue_match.get("unblocks_phase3_criteria"))
        or _as_list(slot.get("unblocks_phase4_criteria"))
        or _as_list(queue_match.get("unblocks_phase4_criteria"))
    )
    return {
        "slot_id": slot_id,
        "target_id": str(slot.get("target_id") or queue_match.get("target_id") or ""),
        "handoff_id": str(slot.get("handoff_id") or queue_match.get("handoff_id") or ""),
        "status": str(slot.get("status") or queue_match.get("status") or ""),
        "blocked_criteria": [str(row) for row in blocked_criteria],
        "first_next_action": str(
            slot.get("first_next_action") or queue_match.get("first_next_action") or ""
        ),
        "template_artifact": str(
            slot.get("template_artifact") or queue_match.get("template_artifact") or ""
        ),
        "minimum_evidence": _as_dict(
            slot.get("minimum_evidence") or queue_match.get("minimum_evidence")
        ),
        "materialization_steps": [
            str(row)
            for row in (
                _as_list(slot.get("materialization_steps"))
                or _as_list(queue_match.get("materialization_steps"))
            )
        ],
        "materialization_command": str(
            slot.get("materialization_command")
            or queue_match.get("materialization_command")
            or ""
        ),
        "validation_command": str(
            slot.get("validation_command") or queue_match.get("validation_command") or ""
        ),
    }


def _blocked_capability_register(
    capability_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked_rows = [
        row
        for row in capability_rows
        if str(row.get("state") or "") != "ready"
    ]
    register: list[dict[str, Any]] = []
    for index, row in enumerate(blocked_rows, start=1):
        summary = _as_dict(row.get("summary"))
        next_actions = [str(action) for action in _as_list(row.get("next_actions"))]
        handoff_slot = _capability_handoff_slot(summary)
        first_next_action = _first_str(
            [handoff_slot.get("first_next_action"), *next_actions]
        )
        register.append(
            {
                "queue_priority": index,
                "capability_id": str(row.get("capability_id") or ""),
                "title": str(row.get("title") or ""),
                "capability_kind": str(row.get("capability_kind") or ""),
                "state": str(row.get("state") or ""),
                "contract_pass": bool(row.get("contract_pass")),
                "blocker_count": int(row.get("blocker_count") or 0),
                "first_blocked_target": str(summary.get("first_blocked_target") or ""),
                "root_cause_tags": [
                    str(tag) for tag in _as_list(summary.get("root_cause_tags"))
                ],
                "first_next_action": first_next_action,
                "operator_intake_route": str(
                    summary.get("operator_intake_route") or ""
                ),
                "operator_intake_artifact": str(
                    summary.get("operator_intake_artifact") or ""
                ),
                "operator_intake_markdown_artifact": str(
                    summary.get("operator_intake_markdown_artifact") or ""
                ),
                "operator_intake_packet_status": str(
                    summary.get("operator_intake_packet_status") or ""
                ),
                "operator_intake_required_slot_count": int(
                    summary.get("operator_intake_required_slot_count") or 0
                ),
                "gate_unblock_plan_count": int(
                    summary.get("gate_unblock_plan_count") or 0
                ),
                "handoff_slot": handoff_slot,
                "evidence_artifact_count": len(_as_list(row.get("evidence_artifacts"))),
            }
        )
    return register


def _capability_row(
    *,
    capability_id: str,
    title: str,
    capability_kind: str,
    state: str,
    evidence_artifacts: list[Path],
    contract_pass: bool,
    blocker_count: int,
    next_actions: list[str],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "title": title,
        "capability_kind": capability_kind,
        "state": state,
        "contract_pass": contract_pass,
        "blocker_count": blocker_count,
        "evidence_artifacts": [str(path) for path in evidence_artifacts],
        "next_actions": next_actions,
        "summary": summary or {},
    }


def _structural_solver_capability(repo_root: Path) -> dict[str, Any]:
    payloads = [_load_json(repo_root, path) for path in STRUCTURAL_SURFACE_PATHS]
    present_payloads = [payload for payload in payloads if payload]
    ready_count = sum(1 for payload in present_payloads if not _payload_blocked(payload))
    return _capability_row(
        capability_id="structural_solver_restricted_alpha_surface",
        title="Restricted alpha structural solver evidence",
        capability_kind="engineering_core",
        state="ready" if present_payloads and ready_count == len(STRUCTURAL_SURFACE_PATHS) else "blocked",
        evidence_artifacts=list(STRUCTURAL_SURFACE_PATHS),
        contract_pass=bool(present_payloads and ready_count == len(STRUCTURAL_SURFACE_PATHS)),
        blocker_count=len(STRUCTURAL_SURFACE_PATHS) - ready_count,
        next_actions=[] if ready_count == len(STRUCTURAL_SURFACE_PATHS) else ["refresh_structural_solver_surface_receipts"],
        summary={
            "surface_count": len(STRUCTURAL_SURFACE_PATHS),
            "present_surface_count": len(present_payloads),
            "ready_surface_count": ready_count,
        },
    )


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_product_capabilities_surface.py"),
        *STRUCTURAL_SURFACE_PATHS,
    ]


def build_product_capabilities_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    capability_rows = [
        _structural_solver_capability(repo_root),
    ]
    ready_count = sum(1 for row in capability_rows if row["state"] == "ready")
    blocked_rows = [row for row in capability_rows if row["state"] != "ready"]
    blocked_capability_register = _blocked_capability_register(capability_rows)
    first_blocked_capability = (
        blocked_capability_register[0] if blocked_capability_register else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=False,
            reuse_policy="product_capabilities_surface_aggregates_structural_solver_evidence",
            repo_root=repo_root,
        ),
        "surface_id": "product_capabilities_surface",
        "surface_kind": "product_capabilities_surface",
        "surface_scope": "product_capability_discovery",
        "status": "ready",
        "reason_code": "PASS",
        "contract_pass": True,
        "locked": False,
        "claim_locked": False,
        "product_capabilities_ready": False,
        "capability_count": len(capability_rows),
        "ready_capability_count": ready_count,
        "blocked_capability_count": len(blocked_rows),
        "capability_rows": capability_rows,
        "blocked_capability_register_count": len(blocked_capability_register),
        "first_blocked_capability_id": str(
            first_blocked_capability.get("capability_id") or ""
        ),
        "first_blocked_capability_next_action": str(
            first_blocked_capability.get("first_next_action") or ""
        ),
        "first_blocked_capability": first_blocked_capability,
        "blocked_capability_register": blocked_capability_register,
        "blockers": [],
        "first_blocked_target": "",
        "root_cause_tags": [],
        "read_model": {
            "route": "/product/capabilities",
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "next_actions": [
            "work_capability_rows_with_state_blocked",
            "regenerate_pm_release_gate_report",
            "regenerate_goal_bottleneck_action_board",
        ],
        "summary_line": (
            "Product capabilities surface: READY | "
            f"capabilities={len(capability_rows)} | ready={ready_count} | "
            f"blocked={len(blocked_rows)}"
        ),
        "claim_boundary": (
            "This surface is a read-only capability discovery map for the structural "
            "analysis solver product. Non-structural product domains are outside this "
            "repository's product scope."
        ),
    }


def write_product_capabilities_surface(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_product_capabilities_surface(repo_root=repo_root)
    resolved = out if out.is_absolute() else repo_root / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_product_capabilities_surface(repo_root=args.repo_root, out=args.out)
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
