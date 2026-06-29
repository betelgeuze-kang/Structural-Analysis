#!/usr/bin/env python3
"""Materialize a GPCR hard-decoy suite report from operator target metrics."""

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


SCHEMA_VERSION = "gpcr-hard-decoy-suite-report.v1"
SURFACE_SCHEMA_VERSION = "gpcr-hard-decoy-evidence-surface.v1"
REQUIRED_TARGETS = ("DRD2", "HTR2A", "OPRM1")
EXIT_CRITERIA = {
    "ranking_pr_auc_ci_low_min": 0.45,
    "top20_hit_rate_min": 0.20,
    "decoys_above_positive_count_max": 0,
    "positive_out_anchored_by_top_decoys_allowed": False,
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _target_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _row_by_target(intake: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _as_list(intake.get("targets")):
        if not isinstance(row, dict):
            continue
        target_id = _target_key(row.get("target_id") or row.get("target"))
        if target_id:
            rows[target_id] = row
    return rows


def _missing_target_row(target_id: str) -> dict[str, Any]:
    blockers = [
        f"{target_id}:operator_metrics_required",
        f"{target_id}:ranking_pr_auc_ci_low_required",
        f"{target_id}:top20_hit_rate_required",
        f"{target_id}:decoys_above_positive_count_required",
        f"{target_id}:positive_out_anchored_by_top_decoys_required",
    ]
    return {
        "target_id": target_id,
        "status": "blocked",
        "contract_pass": False,
        "ranking_pr_auc_ci_low": None,
        "top20_hit_rate": None,
        "decoys_above_positive_count": None,
        "positive_out_anchored_by_top_decoys": None,
        "criteria": EXIT_CRITERIA,
        "root_cause_tags": ["operator_values_required"],
        "blockers": blockers,
    }


def _target_result(target_id: str, row: dict[str, Any]) -> dict[str, Any]:
    ranking = _number(row.get("ranking_pr_auc_ci_low"))
    top20 = _number(row.get("top20_hit_rate"))
    decoys_above = _integer(row.get("decoys_above_positive_count"))
    out_anchored = _boolean(
        row.get("positive_out_anchored_by_top_decoys")
        if "positive_out_anchored_by_top_decoys" in row
        else row.get("positive_out_anchored_by_top_decoy")
    )
    blockers: list[str] = []
    root_cause_tags: list[str] = []

    if ranking is None:
        blockers.append(f"{target_id}:ranking_pr_auc_ci_low_required")
        root_cause_tags.append("operator_values_required")
    elif ranking < EXIT_CRITERIA["ranking_pr_auc_ci_low_min"]:
        blockers.append(f"{target_id}:ranking_pr_auc_ci_low_below_threshold")
        root_cause_tags.append("ranking_pr_auc_ci_low_below_threshold")

    if top20 is None:
        blockers.append(f"{target_id}:top20_hit_rate_required")
        root_cause_tags.append("operator_values_required")
    elif top20 < EXIT_CRITERIA["top20_hit_rate_min"]:
        blockers.append(f"{target_id}:top20_hit_rate_below_threshold")
        root_cause_tags.append("top20_hit_rate_below_threshold")

    if decoys_above is None:
        blockers.append(f"{target_id}:decoys_above_positive_count_required")
        root_cause_tags.append("operator_values_required")
    elif decoys_above > EXIT_CRITERIA["decoys_above_positive_count_max"]:
        blockers.append(f"{target_id}:decoys_above_positive_count_above_limit")
        root_cause_tags.append("decoy_rank_leakage")

    if out_anchored is None:
        blockers.append(f"{target_id}:positive_out_anchored_by_top_decoys_required")
        root_cause_tags.append("operator_values_required")
    elif out_anchored is not EXIT_CRITERIA["positive_out_anchored_by_top_decoys_allowed"]:
        blockers.append(f"{target_id}:positive_out_anchored_by_top_decoys")
        root_cause_tags.append("positive_out_anchored_by_top_decoys")

    deduped_root_causes = list(dict.fromkeys(root_cause_tags))
    return {
        "target_id": target_id,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "ranking_pr_auc_ci_low": ranking,
        "top20_hit_rate": top20,
        "decoys_above_positive_count": decoys_above,
        "positive_out_anchored_by_top_decoys": out_anchored,
        "criteria": EXIT_CRITERIA,
        "root_cause_tags": deduped_root_causes,
        "blockers": blockers,
    }


def _field_blockers(row: dict[str, Any], field_name: str) -> list[str]:
    return [
        str(blocker)
        for blocker in _as_list(row.get("blockers"))
        if str(blocker).split(":", 1)[-1].startswith(field_name)
    ]


def _numeric_min_gate(
    *,
    target_rows: list[dict[str, Any]],
    criterion_id: str,
    field_name: str,
    required: float,
) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, float | None] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        value = _number(row.get(field_name))
        current_by_target[target_id] = value
        if value is None or value < required:
            failed_targets.append(target_id)
            blockers.extend(_field_blockers(row, field_name))
    return {
        "criterion_id": criterion_id,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": f">={required:g}",
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _integer_max_gate(
    *,
    target_rows: list[dict[str, Any]],
    criterion_id: str,
    field_name: str,
    required: int,
) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, int | None] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        value = _integer(row.get(field_name))
        current_by_target[target_id] = value
        if value is None or value > required:
            failed_targets.append(target_id)
            blockers.extend(_field_blockers(row, field_name))
    return {
        "criterion_id": criterion_id,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": f"<={required}",
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _boolean_gate(
    *,
    target_rows: list[dict[str, Any]],
    criterion_id: str,
    field_name: str,
    required: bool,
) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, bool | None] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        value = _boolean(row.get(field_name))
        current_by_target[target_id] = value
        if value is not required:
            failed_targets.append(target_id)
            blockers.extend(_field_blockers(row, field_name))
    return {
        "criterion_id": criterion_id,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": required,
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _phase3_exit_gate(
    *,
    target_rows: list[dict[str, Any]],
    target_pass_count: int,
    broad_safe: bool,
    first_blocked_target: str,
) -> dict[str, Any]:
    criteria = [
        _numeric_min_gate(
            target_rows=target_rows,
            criterion_id="ranking_pr_auc_ci_low_min",
            field_name="ranking_pr_auc_ci_low",
            required=float(EXIT_CRITERIA["ranking_pr_auc_ci_low_min"]),
        ),
        _numeric_min_gate(
            target_rows=target_rows,
            criterion_id="top20_hit_rate_min",
            field_name="top20_hit_rate",
            required=float(EXIT_CRITERIA["top20_hit_rate_min"]),
        ),
        _integer_max_gate(
            target_rows=target_rows,
            criterion_id="decoys_above_positive_count_max",
            field_name="decoys_above_positive_count",
            required=int(EXIT_CRITERIA["decoys_above_positive_count_max"]),
        ),
        _boolean_gate(
            target_rows=target_rows,
            criterion_id="no_positive_out_anchored_by_top_decoys",
            field_name="positive_out_anchored_by_top_decoys",
            required=bool(EXIT_CRITERIA["positive_out_anchored_by_top_decoys_allowed"]),
        ),
    ]
    failed_criteria = [
        str(row["criterion_id"]) for row in criteria if not bool(row["pass"])
    ]
    return {
        "status": "ready" if broad_safe else "blocked",
        "claim": "broad_gpcr_hard_decoy_closure",
        "target_count": len(REQUIRED_TARGETS),
        "target_pass_count": target_pass_count,
        "first_blocked_target": first_blocked_target,
        "criteria": criteria,
        "failed_criterion_count": len(failed_criteria),
        "failed_criteria": failed_criteria,
    }


def materialize_gpcr_hard_decoy_suite_report(
    intake: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
) -> dict[str, Any]:
    rows_by_target = _row_by_target(intake)
    target_rows = [
        _target_result(target_id, rows_by_target[target_id])
        if target_id in rows_by_target
        else _missing_target_row(target_id)
        for target_id in REQUIRED_TARGETS
    ]
    blockers = [blocker for row in target_rows for blocker in row["blockers"]]
    root_cause_tags = list(
        dict.fromkeys(tag for row in target_rows for tag in row["root_cause_tags"])
    )
    first_blocked_target = next(
        (row["target_id"] for row in target_rows if row["status"] != "pass"),
        "",
    )
    target_pass_count = sum(1 for row in target_rows if row["contract_pass"])
    broad_safe = bool(target_pass_count == len(REQUIRED_TARGETS) and not blockers)
    phase3_exit_gate = _phase3_exit_gate(
        target_rows=target_rows,
        target_pass_count=target_pass_count,
        broad_safe=broad_safe,
        first_blocked_target=first_blocked_target,
    )
    input_paths = [Path("scripts/materialize_gpcr_hard_decoy_suite_report.py")]
    if intake_path is not None:
        input_paths.append(intake_path)

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_suite_report_materialized_from_operator_metrics",
            repo_root=repo_root,
        ),
        "status": "ready" if broad_safe else "locked",
        "contract_pass": broad_safe,
        "broad_gpcr_family_claim_safe": broad_safe,
        "target_count": len(REQUIRED_TARGETS),
        "target_pass_count": target_pass_count,
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": root_cause_tags,
        "exit_criteria": EXIT_CRITERIA,
        "phase3_exit_gate": phase3_exit_gate,
        "target_rows": target_rows,
        "blockers": blockers,
        "summary_line": (
            "GPCR hard-decoy suite: PASS"
            if broad_safe
            else (
                "GPCR hard-decoy suite: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'} | "
                f"root_cause={','.join(root_cause_tags) or 'none'}"
            )
        ),
        "claim_boundary": (
            "This report evaluates operator-attached DRD2/HTR2A/OPRM1 hard-decoy "
            "metrics against the Phase 3 exit criteria. It does not infer target "
            "activity, generate docking results, or unlock broad GPCR claims without "
            "all required numeric receipts."
        ),
    }


def build_gpcr_evidence_surface(
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    contract_pass = bool(report.get("broad_gpcr_family_claim_safe"))
    status = "ready" if contract_pass else "locked"
    input_paths = [
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
    ]
    if report_path is not None:
        input_paths.append(report_path)
    return {
        "schema_version": SURFACE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_evidence_surface_from_suite_report",
            repo_root=repo_root,
        ),
        "surface_id": "gpcr_hard_decoy_evidence_surface",
        "science_surface_family": "gpcr",
        "surface_scope": "broad_gpcr_hard_decoy",
        "status": status,
        "reason_code": "PASS" if contract_pass else "ERR_BROAD_GPCR_CLAIM_LOCKED",
        "contract_pass": contract_pass,
        "locked": not contract_pass,
        "claim_locked": not contract_pass,
        "broad_gpcr_family_claim_safe": contract_pass,
        "target_families": list(REQUIRED_TARGETS),
        "exit_criteria": EXIT_CRITERIA,
        "phase3_exit_gate": _as_dict(report.get("phase3_exit_gate")),
        "first_blocked_target": str(report.get("first_blocked_target") or ""),
        "root_cause_tags": _as_list(report.get("root_cause_tags")),
        "suite_report": str(report_path) if report_path is not None else "",
        "blockers": _as_list(report.get("blockers")),
        "summary_line": str(report.get("summary_line") or ""),
        "claim_boundary": (
            "This GPCR evidence surface mirrors the hard-decoy suite report for PM "
            "routing. Broad GPCR claims stay locked until every required target row "
            "passes the numeric exit criteria."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--out-surface", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    report = materialize_gpcr_hard_decoy_suite_report(
        intake,
        repo_root=args.repo_root,
        intake_path=args.intake,
    )
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(_json_text(report), encoding="utf-8")
    if args.out_surface is not None:
        surface = build_gpcr_evidence_surface(
            report,
            report_path=args.out_report,
            repo_root=args.repo_root,
        )
        args.out_surface.parent.mkdir(parents=True, exist_ok=True)
        args.out_surface.write_text(_json_text(surface), encoding="utf-8")
    print(
        "gpcr-hard-decoy-suite: "
        f"{report['status']} | targets={report['target_pass_count']}/{report['target_count']} | "
        f"first_blocked={report['first_blocked_target'] or 'none'} | "
        f"blockers={len(report['blockers'])}"
    )
    return 1 if args.fail_blocked and not report["broad_gpcr_family_claim_safe"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
