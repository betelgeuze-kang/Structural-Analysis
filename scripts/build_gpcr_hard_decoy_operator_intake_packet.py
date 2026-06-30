#!/usr/bin/env python3
"""Build the operator intake packet for GPCR hard-decoy closure."""

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
from materialize_gpcr_hard_decoy_suite_report import (  # noqa: E402
    EXIT_CRITERIA,
    REQUIRED_TARGETS,
    SCHEMA_VERSION as SUITE_REPORT_SCHEMA_VERSION,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_SUITE_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"
DEFAULT_EVIDENCE_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_PRODUCT_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_product_report.json"
DEFAULT_PRODUCT_CAPABILITIES = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_GOAL_BOTTLENECK = PRODUCTIZATION / "goal_bottleneck_roadmap_surface.json"
DEFAULT_OUT = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")

SCHEMA_VERSION = "gpcr-hard-decoy-operator-intake-packet.v1"
GPCR_PRODUCT_REPORT_ROUTE = "/product/gpcr-hard-decoy-suite-report"
GPCR_OPERATOR_INTAKE_ROUTE = "/product/gpcr-hard-decoy-suite-report/operator-intake"
REQUIRED_OPERATOR_FIELDS = (
    "target_id",
    "ranking_pr_auc_ci_low",
    "top20_hit_rate",
    "decoys_above_positive_count",
    "positive_out_anchored_by_top_decoys",
)
PHASE3_EXIT_CRITERIA_BY_FIELD = {
    "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min",
    "top20_hit_rate": "top20_hit_rate_min",
    "decoys_above_positive_count": "decoys_above_positive_count_max",
    "positive_out_anchored_by_top_decoys": "no_positive_out_anchored_by_top_decoys",
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_gpcr_hard_decoy_operator_intake_packet.py"),
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
        DEFAULT_OPERATOR_TEMPLATE,
        DEFAULT_SUITE_REPORT,
        DEFAULT_EVIDENCE_SURFACE,
    ]


def _target_template(target_id: str) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "ranking_pr_auc_ci_low": None,
        "top20_hit_rate": None,
        "decoys_above_positive_count": None,
        "positive_out_anchored_by_top_decoys": None,
    }


def _target_slot(target_id: str) -> dict[str, Any]:
    return {
        "slot_id": f"{target_id.lower()}_hard_decoy_metrics",
        "target_id": target_id,
        "status": "operator_input_required",
        "required": True,
        "template_artifact": str(DEFAULT_OPERATOR_TEMPLATE),
        "required_fields": list(REQUIRED_OPERATOR_FIELDS),
        "exit_criteria": EXIT_CRITERIA,
        "template": _target_template(target_id),
        "owner_actions": [
            "attach authoritative hard-decoy evaluation metrics for this target",
            "keep ranking_pr_auc_ci_low as the lower confidence bound",
            "keep top20_hit_rate as a fraction, not a percent",
            "verify decoys_above_positive_count is zero",
            "verify positive_out_anchored_by_top_decoys is false",
        ],
    }


def _gate_unblock_plan(*, materialize_command: str) -> list[dict[str, Any]]:
    return [
        {
            "slot_id": f"{target_id.lower()}_hard_decoy_metrics",
            "target_id": target_id,
            "status": "operator_input_required",
            "template_artifact": str(DEFAULT_OPERATOR_TEMPLATE),
            "unblocks_phase3_criteria": list(PHASE3_EXIT_CRITERIA_BY_FIELD.values()),
            "minimum_evidence": {
                "target_id": target_id,
                "required_operator_fields": list(REQUIRED_OPERATOR_FIELDS),
                "criterion_by_field": dict(PHASE3_EXIT_CRITERIA_BY_FIELD),
                "thresholds": {
                    "ranking_pr_auc_ci_low": f">={EXIT_CRITERIA['ranking_pr_auc_ci_low_min']}",
                    "top20_hit_rate": f">={EXIT_CRITERIA['top20_hit_rate_min']}",
                    "decoys_above_positive_count": f"<={EXIT_CRITERIA['decoys_above_positive_count_max']}",
                    "positive_out_anchored_by_top_decoys": EXIT_CRITERIA[
                        "positive_out_anchored_by_top_decoys_allowed"
                    ],
                },
            },
            "materialization_steps": [
                "materialize_gpcr_hard_decoy_suite_report",
                "refresh_gpcr_hard_decoy_product_report",
                "refresh_product_capabilities_surface",
                "refresh_goal_bottleneck_roadmap_surface",
            ],
            "materialization_command": materialize_command,
            "validation_command": materialize_command,
        }
        for target_id in REQUIRED_TARGETS
    ]


def build_gpcr_hard_decoy_operator_intake_packet(*, repo_root: Path = ROOT) -> dict[str, Any]:
    template = _load_json(repo_root, DEFAULT_OPERATOR_TEMPLATE)
    suite = _load_json(repo_root, DEFAULT_SUITE_REPORT)
    surface = _load_json(repo_root, DEFAULT_EVIDENCE_SURFACE)
    blockers = [str(row) for row in _as_list(suite.get("blockers") or surface.get("blockers"))]
    first_blocked_target = str(
        suite.get("first_blocked_target") or surface.get("first_blocked_target") or "DRD2"
    )
    root_cause_tags = [
        str(row)
        for row in _as_list(suite.get("root_cause_tags") or surface.get("root_cause_tags"))
    ]

    materialize_command = (
        "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
        f"--intake {DEFAULT_OPERATOR_TEMPLATE} "
        f"--out-report {DEFAULT_SUITE_REPORT} "
        f"--out-surface {DEFAULT_EVIDENCE_SURFACE} --fail-blocked"
    )
    refresh_product_report_command = (
        "python3 scripts/build_gpcr_hard_decoy_product_report.py "
        f"--out {DEFAULT_PRODUCT_REPORT}"
    )
    refresh_capabilities_command = (
        "python3 scripts/build_product_capabilities_surface.py "
        f"--out {DEFAULT_PRODUCT_CAPABILITIES}"
    )
    refresh_goal_command = (
        "python3 scripts/build_goal_bottleneck_roadmap_surface.py "
        f"--out {DEFAULT_GOAL_BOTTLENECK}"
    )
    gate_unblock_plan = _gate_unblock_plan(materialize_command=materialize_command)

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=True,
            reuse_policy="gpcr_hard_decoy_operator_intake_packet_from_template_and_suite_contracts",
            repo_root=repo_root,
        ),
        "packet_id": "gpcr_hard_decoy_operator_intake_packet",
        "status": "ready_for_operator_input",
        "reason_code": "PASS_INTAKE_PACKET",
        "contract_pass": True,
        "read_model_ready": True,
        "route": GPCR_OPERATOR_INTAKE_ROUTE,
        "read_model": {
            "route": GPCR_OPERATOR_INTAKE_ROUTE,
            "alternate_routes": [GPCR_PRODUCT_REPORT_ROUTE, "/product/capabilities"],
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "broad_gpcr_family_claim_safe": False,
        "owner_input_required": True,
        "required_targets": list(REQUIRED_TARGETS),
        "required_operator_fields": list(REQUIRED_OPERATOR_FIELDS),
        "exit_criteria": EXIT_CRITERIA,
        "target_slots": [_target_slot(target_id) for target_id in REQUIRED_TARGETS],
        "required_slot_count": len(REQUIRED_TARGETS),
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "minimum_target_count": len(REQUIRED_TARGETS),
        "minimum_metric_field_count_per_target": len(REQUIRED_OPERATOR_FIELDS) - 1,
        "operator_template": {
            "artifact": str(DEFAULT_OPERATOR_TEMPLATE),
            "schema_version": str(template.get("schema_version") or "gpcr-hard-decoy-operator-intake.v1"),
            "required_targets": [str(row) for row in _as_list(template.get("required_targets"))]
            or list(REQUIRED_TARGETS),
            "targets_json_pointer": "/targets",
        },
        "current_suite_status": {
            "artifact": str(DEFAULT_SUITE_REPORT),
            "schema_version": str(suite.get("schema_version") or SUITE_REPORT_SCHEMA_VERSION),
            "status": str(suite.get("status") or ""),
            "target_count": int(suite.get("target_count") or len(REQUIRED_TARGETS)),
            "target_pass_count": int(suite.get("target_pass_count") or 0),
            "first_blocked_target": first_blocked_target,
            "root_cause_tags": root_cause_tags,
            "blocker_count": len(blockers),
        },
        "materialization_sequence": [
            {
                "step_id": "fill_gpcr_hard_decoy_operator_template",
                "command": f"edit {DEFAULT_OPERATOR_TEMPLATE}",
                "produces": str(DEFAULT_OPERATOR_TEMPLATE),
            },
            {
                "step_id": "materialize_gpcr_hard_decoy_suite_report",
                "schema_version": SUITE_REPORT_SCHEMA_VERSION,
                "command": materialize_command,
                "produces": str(DEFAULT_SUITE_REPORT),
            },
            {
                "step_id": "refresh_gpcr_hard_decoy_product_report",
                "schema_version": "gpcr-hard-decoy-product-report.v1",
                "command": refresh_product_report_command,
                "produces": str(DEFAULT_PRODUCT_REPORT),
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
        ],
        "acceptance_criteria": [
            "gpcr_hard_decoy_suite_report.target_pass_count == 3",
            "gpcr_hard_decoy_suite_report.broad_gpcr_family_claim_safe == true",
            "gpcr_hard_decoy_suite_report.blockers == []",
            "gpcr_hard_decoy_product_report.science_claim_status == ready",
            "gpcr_hard_decoy_evidence_surface.locked == false",
        ],
        "linked_artifacts": {
            "operator_template": str(DEFAULT_OPERATOR_TEMPLATE),
            "suite_report": str(DEFAULT_SUITE_REPORT),
            "evidence_surface": str(DEFAULT_EVIDENCE_SURFACE),
            "product_report": str(DEFAULT_PRODUCT_REPORT),
            "product_capabilities_surface": str(DEFAULT_PRODUCT_CAPABILITIES),
            "goal_bottleneck_roadmap_surface": str(DEFAULT_GOAL_BOTTLENECK),
        },
        "next_actions": [
            "fill_gpcr_hard_decoy_operator_intake_packet",
            "fill_drd2_htr2a_oprm1_operator_template_values",
            "run_gpcr_hard_decoy_materializer",
            "refresh_gpcr_hard_decoy_product_report",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_roadmap_surface",
        ],
        "summary": {
            "required_slot_count": len(REQUIRED_TARGETS),
            "gate_unblock_plan_count": len(gate_unblock_plan),
            "minimum_target_count": len(REQUIRED_TARGETS),
            "minimum_metric_field_count_per_target": len(REQUIRED_OPERATOR_FIELDS) - 1,
            "current_blocker_count": len(blockers),
            "first_blocked_target": first_blocked_target,
            "broad_gpcr_family_claim_safe": False,
        },
        "summary_line": (
            "GPCR hard-decoy operator intake packet: READY | "
            f"targets={len(REQUIRED_TARGETS)} | first_blocked_target={first_blocked_target}"
        ),
        "claim_boundary": (
            "This packet is an owner-facing intake contract for GPCR hard-decoy metrics. "
            "It does not generate docking results, infer missing values, or promote broad "
            "GPCR claims. DRD2, HTR2A, and OPRM1 must all pass the numeric exit criteria."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GPCR Hard-Decoy Operator Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `status`: `{payload['status']}`",
        f"- `broad_gpcr_family_claim_safe`: `{payload['broad_gpcr_family_claim_safe']}`",
        f"- `first_blocked_target`: `{payload['summary']['first_blocked_target']}`",
        f"- `claim_boundary`: {payload['claim_boundary']}",
        "",
        "| Target | Status | Required Fields |",
        "|---|---|---|",
    ]
    for slot in payload["target_slots"]:
        lines.append(
            f"| `{slot['target_id']}` | `{slot['status']}` | "
            f"`{', '.join(slot['required_fields'])}` |"
        )
    lines.extend(["", "## Gate Unblock Plan", "", "| Target | Criteria | Minimum Evidence |"])
    lines.append("|---|---|---|")
    for row in payload["gate_unblock_plan"]:
        criteria = ", ".join(
            f"`{criterion}`" for criterion in row["unblocks_phase3_criteria"]
        )
        minimum = json.dumps(row["minimum_evidence"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| `{row['target_id']}` | {criteria} | `{minimum}` |")
    lines.extend(["", "## Materialization Sequence", ""])
    for step in payload["materialization_sequence"]:
        lines.append(f"- `{step['step_id']}`: `{step['command']}`")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in payload["acceptance_criteria"]:
        lines.append(f"- `{criterion}`")
    lines.append("")
    return "\n".join(lines)


def write_gpcr_hard_decoy_operator_intake_packet(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_gpcr_hard_decoy_operator_intake_packet(repo_root=repo_root)
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
    payload = write_gpcr_hard_decoy_operator_intake_packet(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
    )
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
