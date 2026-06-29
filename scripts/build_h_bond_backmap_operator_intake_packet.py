#!/usr/bin/env python3
"""Build the operator intake packet for H-bond BackMap evidence closure."""

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
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_EVIDENCE_SURFACE = SURFACE_DIR / "h_bond_backmap_evidence_surface.json"
DEFAULT_PRODUCT_CAPABILITIES = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_PM_RELEASE_GATE = PRODUCTIZATION / "pm_release_gate_report.json"
DEFAULT_GOAL_BOTTLENECK = PRODUCTIZATION / "goal_bottleneck_roadmap_surface.json"
DEFAULT_OUT = PRODUCTIZATION / "h_bond_backmap_operator_intake_packet.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

SCHEMA_VERSION = "h-bond-backmap-operator-intake-packet.v1"
REQUIRED_CASE_FIELDS = (
    "case_id",
    "receptor_id",
    "ligand_id",
    "source_system_ref",
    "donor_acceptor_map_ref",
    "contact_persistence_rate",
    "backmap_accuracy_rate",
    "h_bond_distance_error_angstrom_median",
    "h_bond_angle_error_degree_median",
    "reviewer_reproduction_command",
    "provenance_ref",
    "source_checksum",
)


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


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_h_bond_backmap_operator_intake_packet.py"),
        DEFAULT_EVIDENCE_SURFACE,
    ]


def _case_template() -> dict[str, Any]:
    return {
        "case_id": "h_bond_backmap_case_001",
        "receptor_id": "",
        "ligand_id": "",
        "source_system_ref": "",
        "donor_acceptor_map_ref": "",
        "contact_persistence_rate": None,
        "backmap_accuracy_rate": None,
        "h_bond_distance_error_angstrom_median": None,
        "h_bond_angle_error_degree_median": None,
        "reviewer_reproduction_command": "",
        "provenance_ref": "",
        "source_checksum": "",
    }


def _input_slots() -> list[dict[str, Any]]:
    return [
        {
            "slot_id": "operator_attached_h_bond_backmap_cases",
            "status": "operator_input_required",
            "required": True,
            "required_fields": list(REQUIRED_CASE_FIELDS),
            "template": _case_template(),
            "owner_actions": [
                "attach authoritative H-bond BackMap case rows",
                "keep persistence and accuracy values as fractions, not percents",
                "include a provenance reference and checksum for each source artifact",
            ],
        },
        {
            "slot_id": "contact_persistence_or_backmap_accuracy_rows",
            "status": "operator_input_required",
            "required": True,
            "required_fields": [
                "case_id",
                "contact_persistence_rate",
                "backmap_accuracy_rate",
                "h_bond_distance_error_angstrom_median",
                "h_bond_angle_error_degree_median",
                "source_checksum",
            ],
            "owner_actions": [
                "attach measured contact persistence or BackMap accuracy rows",
                "link every measured row back to an authoritative case receipt",
            ],
        },
        {
            "slot_id": "reviewer_reproduction_command",
            "status": "operator_input_required",
            "required": True,
            "required_fields": [
                "command",
                "expected_outputs",
                "environment_ref",
                "source_checksum",
            ],
            "owner_actions": [
                "attach a reviewer reproduction command for the receipt bundle",
                "ensure the command regenerates the same rows and checksums",
            ],
        },
    ]


def build_h_bond_backmap_operator_intake_packet(*, repo_root: Path = ROOT) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_EVIDENCE_SURFACE)
    blockers = [str(row) for row in _as_list(surface.get("blockers"))]
    required_receipts = [str(row) for row in _as_list(surface.get("required_receipts"))]
    current_status = str(surface.get("status") or "")

    refresh_capabilities_command = (
        "python3 scripts/build_product_capabilities_surface.py "
        f"--out {DEFAULT_PRODUCT_CAPABILITIES}"
    )
    refresh_goal_command = (
        "python3 scripts/build_goal_bottleneck_roadmap_surface.py "
        f"--out {DEFAULT_GOAL_BOTTLENECK}"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=True,
            reuse_policy="h_bond_backmap_operator_intake_packet_from_locked_surface_contract",
            repo_root=repo_root,
        ),
        "packet_id": "h_bond_backmap_operator_intake_packet",
        "status": "ready_for_operator_input",
        "reason_code": "PASS_INTAKE_PACKET",
        "contract_pass": True,
        "claim_locked": True,
        "owner_input_required": True,
        "required_operator_fields": list(REQUIRED_CASE_FIELDS),
        "input_slots": _input_slots(),
        "required_slot_count": 3,
        "current_surface_status": {
            "artifact": str(DEFAULT_EVIDENCE_SURFACE),
            "schema_version": str(
                surface.get("schema_version") or "science-evidence-surface-seed.v1"
            ),
            "status": current_status,
            "locked": bool(surface.get("locked", True)),
            "claim_locked": bool(surface.get("claim_locked", True)),
            "contract_pass": bool(surface.get("contract_pass")),
            "reason_code": str(surface.get("reason_code") or ""),
            "first_blocked_target": str(surface.get("first_blocked_target") or ""),
            "root_cause_tags": [
                str(row) for row in _as_list(surface.get("root_cause_tags"))
            ],
            "blocker_count": len(blockers),
            "blockers": blockers,
            "required_receipts": required_receipts,
            "operator_evidence_gap_count": int(
                surface.get("operator_evidence_gap_count") or 0
            ),
            "first_operator_evidence_gap": _as_dict(
                surface.get("first_operator_evidence_gap")
            ),
        },
        "handoff_sequence": [
            {
                "step_id": "attach_h_bond_backmap_operator_receipts",
                "command": "attach authoritative H-bond BackMap receipt bundle",
                "produces": "operator-owned H-bond BackMap receipt bundle",
            },
            {
                "step_id": "materialize_h_bond_backmap_evidence_rows",
                "command": (
                    "materialize receipt-backed H-bond BackMap rows into "
                    f"{DEFAULT_EVIDENCE_SURFACE}"
                ),
                "produces": str(DEFAULT_EVIDENCE_SURFACE),
            },
            {
                "step_id": "refresh_product_capabilities_surface",
                "schema_version": "product-capabilities-surface.v1",
                "command": refresh_capabilities_command,
                "produces": str(DEFAULT_PRODUCT_CAPABILITIES),
            },
            {
                "step_id": "refresh_goal_bottleneck_roadmap_surface",
                "schema_version": "goal-bottleneck-roadmap-surface.v1",
                "command": refresh_goal_command,
                "produces": str(DEFAULT_GOAL_BOTTLENECK),
            },
            {
                "step_id": "refresh_pm_release_gate_report",
                "schema_version": "pm-release-gate-report.v1",
                "command": (
                    "python3 scripts/report_pm_release_gate.py "
                    f"--out {DEFAULT_PM_RELEASE_GATE}"
                ),
                "produces": str(DEFAULT_PM_RELEASE_GATE),
            },
        ],
        "acceptance_criteria": [
            "h_bond_backmap_evidence_surface.required_receipts are all attached",
            "h_bond_backmap_evidence_surface.blockers == []",
            "h_bond_backmap_evidence_surface.contract_pass == true",
            "h_bond_backmap_evidence_surface.locked == false",
            "h_bond_backmap_evidence_surface.claim_locked == false",
        ],
        "linked_artifacts": {
            "evidence_surface": str(DEFAULT_EVIDENCE_SURFACE),
            "product_capabilities_surface": str(DEFAULT_PRODUCT_CAPABILITIES),
            "goal_bottleneck_roadmap_surface": str(DEFAULT_GOAL_BOTTLENECK),
            "pm_release_gate_report": str(DEFAULT_PM_RELEASE_GATE),
        },
        "next_actions": [
            "fill_h_bond_backmap_operator_intake_packet",
            "attach_h_bond_backmap_operator_receipts",
            "materialize_h_bond_backmap_evidence_rows",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_roadmap_surface",
            "regenerate_pm_release_gate_report",
        ],
        "summary": {
            "required_slot_count": 3,
            "current_surface_status": current_status,
            "current_surface_locked": bool(surface.get("locked", True)),
            "current_blocker_count": len(blockers),
            "required_receipt_count": len(required_receipts),
        },
        "summary_line": (
            "H-bond BackMap operator intake packet: READY | "
            f"slots=3 | surface_status={current_status or 'missing'}"
        ),
        "claim_boundary": (
            "This packet is an owner-facing intake contract for H-bond BackMap receipts. "
            "It does not generate molecular evidence, infer missing receipt values, or "
            "unlock the H-bond BackMap evidence surface without authoritative rows and "
            "reviewer reproduction evidence."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# H-Bond BackMap Operator Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `status`: `{payload['status']}`",
        f"- `claim_locked`: `{payload['claim_locked']}`",
        f"- `current_surface_status`: `{payload['summary']['current_surface_status']}`",
        f"- `claim_boundary`: {payload['claim_boundary']}",
        "",
        "| Slot | Status | Required Fields |",
        "|---|---|---|",
    ]
    for slot in payload["input_slots"]:
        lines.append(
            f"| `{slot['slot_id']}` | `{slot['status']}` | "
            f"`{', '.join(slot['required_fields'])}` |"
        )
    lines.extend(["", "## Handoff Sequence", ""])
    for step in payload["handoff_sequence"]:
        lines.append(f"- `{step['step_id']}`: `{step['command']}`")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in payload["acceptance_criteria"]:
        lines.append(f"- `{criterion}`")
    lines.append("")
    return "\n".join(lines)


def write_h_bond_backmap_operator_intake_packet(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_h_bond_backmap_operator_intake_packet(repo_root=repo_root)
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(_markdown(payload), encoding="utf-8")
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
    payload = write_h_bond_backmap_operator_intake_packet(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
    )
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
