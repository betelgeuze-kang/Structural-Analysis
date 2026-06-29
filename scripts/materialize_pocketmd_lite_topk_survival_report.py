#!/usr/bin/env python3
"""Materialize a PocketMD Lite top-k survival report from operator intake rows."""

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

DEFAULT_CONTRACT = PRODUCTIZATION / "pocketmd_lite_contract.json"
DEFAULT_REPORT_OUT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_SURFACE_OUT = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_READONLY_API = PRODUCTIZATION / "pocketmd_lite_readonly_api.json"
DEFAULT_HANDOFF = PRODUCTIZATION / "pocketmd_lite_delivery_handoff.json"

SCHEMA_VERSION = "pocketmd-lite-topk-survival-report.v1"
MATERIALIZATION_SCHEMA_VERSION = "pocketmd-lite-topk-survival-materialization.v1"
SURFACE_SCHEMA_VERSION = "pocketmd-lite-science-product-surface.v1"

REQUIRED_CASE_FIELDS = (
    "case_id",
    "source_family",
    "top_k_rank",
    "candidate_id",
    "pre_refinement_energy_proxy",
    "post_refinement_energy_proxy",
    "local_min_survived",
    "contact_persistence_rate",
    "h_bond_persistence_rate",
    "clash_count_before",
    "clash_count_after",
    "uncertainty_interval",
    "provenance_ref",
    "source_checksum",
)
REQUIRED_METRICS = (
    "local_min_survival_rate",
    "contact_persistence_rate",
    "h_bond_persistence_rate",
    "clash_relief_rate",
    "uncertainty_width_median",
)
REQUIRED_SUMMARY_METRICS = (
    "local_min_survival_rate",
    "contact_persistence_rate_median",
    "h_bond_persistence_rate_median",
    "clash_relief_rate",
    "uncertainty_width_median",
)
BLOCKED_CLAIMS = (
    "broad_all_atom_md_claim",
    "free_energy_perturbation_claim",
    "long_timescale_md_claim",
    "de_novo_binding_mode_claim",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value or "").strip()


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


def _rate(value: Any) -> float | None:
    parsed = _number(value)
    if parsed is None or parsed < 0.0 or parsed > 1.0:
        return None
    return parsed


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _uncertainty_width(value: Any) -> tuple[float | None, str]:
    if not isinstance(value, dict):
        return None, ""
    low = _number(value.get("low"))
    high = _number(value.get("high"))
    unit = _string(value.get("unit") or "energy_proxy_delta")
    if low is None or high is None or high < low:
        return None, unit
    return high - low, unit


def _case_rows(intake: Any) -> list[dict[str, Any]]:
    if isinstance(intake, list):
        raw_rows = intake
    elif isinstance(intake, dict):
        raw_rows = _as_list(intake.get("cases"))
    else:
        raw_rows = []
    return [row for row in raw_rows if isinstance(row, dict)]


def _row_key(row: dict[str, Any], index: int) -> str:
    return _string(row.get("case_id")) or f"case_{index + 1}"


def _normalize_candidate_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    row_key = _row_key(row, index)
    blockers: list[str] = []
    root_cause_tags: list[str] = []

    for field in REQUIRED_CASE_FIELDS:
        if field not in row:
            blockers.append(f"{row_key}:{field}_missing")
            root_cause_tags.append("operator_values_required")

    case_id = _string(row.get("case_id"))
    source_family = _string(row.get("source_family"))
    candidate_id = _string(row.get("candidate_id"))
    provenance_ref = _string(row.get("provenance_ref"))
    source_checksum = _string(row.get("source_checksum"))
    top_k_rank = _integer(row.get("top_k_rank"))
    pre_energy = _number(row.get("pre_refinement_energy_proxy"))
    post_energy = _number(row.get("post_refinement_energy_proxy"))
    local_min_survived = _boolean(row.get("local_min_survived"))
    contact_rate = _rate(row.get("contact_persistence_rate"))
    h_bond_rate = _rate(row.get("h_bond_persistence_rate"))
    clash_before = _integer(row.get("clash_count_before"))
    clash_after = _integer(row.get("clash_count_after"))
    uncertainty_width, uncertainty_unit = _uncertainty_width(row.get("uncertainty_interval"))

    string_fields = {
        "case_id": case_id,
        "source_family": source_family,
        "candidate_id": candidate_id,
        "provenance_ref": provenance_ref,
        "source_checksum": source_checksum,
    }
    for field, value in string_fields.items():
        if field in row and not value:
            blockers.append(f"{row_key}:{field}_blank")
            root_cause_tags.append("operator_values_required")

    if "top_k_rank" in row and (top_k_rank is None or top_k_rank < 1):
        blockers.append(f"{row_key}:top_k_rank_invalid")
        root_cause_tags.append("top_k_rank_invalid")
    if "pre_refinement_energy_proxy" in row and pre_energy is None:
        blockers.append(f"{row_key}:pre_refinement_energy_proxy_invalid")
        root_cause_tags.append("operator_values_required")
    if "post_refinement_energy_proxy" in row and post_energy is None:
        blockers.append(f"{row_key}:post_refinement_energy_proxy_invalid")
        root_cause_tags.append("operator_values_required")
    if "local_min_survived" in row and local_min_survived is None:
        blockers.append(f"{row_key}:local_min_survived_invalid")
        root_cause_tags.append("operator_values_required")
    if "contact_persistence_rate" in row and contact_rate is None:
        blockers.append(f"{row_key}:contact_persistence_rate_invalid")
        root_cause_tags.append("operator_values_required")
    if "h_bond_persistence_rate" in row and h_bond_rate is None:
        blockers.append(f"{row_key}:h_bond_persistence_rate_invalid")
        root_cause_tags.append("operator_values_required")
    if "clash_count_before" in row and (clash_before is None or clash_before < 0):
        blockers.append(f"{row_key}:clash_count_before_invalid")
        root_cause_tags.append("operator_values_required")
    if "clash_count_after" in row and (clash_after is None or clash_after < 0):
        blockers.append(f"{row_key}:clash_count_after_invalid")
        root_cause_tags.append("operator_values_required")
    if "uncertainty_interval" in row and uncertainty_width is None:
        blockers.append(f"{row_key}:uncertainty_interval_invalid")
        root_cause_tags.append("operator_values_required")

    clash_relief = (
        clash_after < clash_before
        if clash_before is not None
        and clash_after is not None
        and clash_before >= 0
        and clash_after >= 0
        else None
    )

    return {
        "case_id": case_id,
        "source_family": source_family,
        "top_k_rank": top_k_rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": pre_energy,
        "post_refinement_energy_proxy": post_energy,
        "energy_proxy_delta": (
            post_energy - pre_energy if pre_energy is not None and post_energy is not None else None
        ),
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "clash_relief": clash_relief,
        "uncertainty_width": uncertainty_width,
        "uncertainty_unit": uncertainty_unit,
        "provenance_ref": provenance_ref,
        "source_checksum": source_checksum,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "root_cause_tags": list(dict.fromkeys(root_cause_tags)),
        "blockers": blockers,
    }


def _summary(rows: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    local_min_rows = [
        bool(row["local_min_survived"])
        for row in rows
        if row.get("local_min_survived") is not None
    ]
    contact_rates = [
        float(row["contact_persistence_rate"])
        for row in rows
        if row.get("contact_persistence_rate") is not None
    ]
    h_bond_rates = [
        float(row["h_bond_persistence_rate"])
        for row in rows
        if row.get("h_bond_persistence_rate") is not None
    ]
    clash_relief_rows = [
        bool(row["clash_relief"]) for row in rows if row.get("clash_relief") is not None
    ]
    uncertainty_widths = [
        float(row["uncertainty_width"])
        for row in rows
        if row.get("uncertainty_width") is not None
    ]
    case_ids = {_string(row.get("case_id")) for row in rows if _string(row.get("case_id"))}

    return {
        "local_min_survival_rate": (
            sum(1 for value in local_min_rows if value) / len(local_min_rows)
            if local_min_rows
            else None
        ),
        "contact_persistence_rate_median": _median(contact_rates),
        "h_bond_persistence_rate_median": _median(h_bond_rates),
        "clash_relief_rate": (
            sum(1 for value in clash_relief_rows if value) / len(clash_relief_rows)
            if clash_relief_rows
            else None
        ),
        "uncertainty_width_median": _median(uncertainty_widths),
        "top_k_candidate_count": len(rows),
        "real_refinement_case_count": len(case_ids),
        "blocker_count": len(blockers),
    }


def _input_paths(
    *,
    intake_path: Path | None,
    contract_path: Path | None,
) -> list[Path]:
    paths = [Path("scripts/materialize_pocketmd_lite_topk_survival_report.py")]
    if intake_path is not None:
        paths.append(intake_path)
    if contract_path is not None:
        paths.append(contract_path)
    return paths


def _contract_schema_version(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return ""
    return _string(contract.get("schema_version"))


def materialize_pocketmd_lite_topk_survival_report(
    intake: Any,
    *,
    contract: dict[str, Any] | None = None,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    rows = [_normalize_candidate_row(row, index) for index, row in enumerate(_case_rows(intake))]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    root_cause_tags = list(dict.fromkeys(tag for row in rows for tag in row["root_cause_tags"]))
    if not rows:
        blockers.append("pocketmd_lite_topk_candidate_rows_missing")
        blockers.append("pocketmd_lite_local_min_survival_rows_missing")
        blockers.append("pocketmd_lite_contact_hbond_persistence_rows_missing")
        blockers.append("pocketmd_lite_uncertainty_rows_missing")
        root_cause_tags.append("operator_refinement_rows_required")

    summary = _summary(rows, blockers)
    metrics_complete = all(summary[metric] is not None for metric in REQUIRED_SUMMARY_METRICS)
    product_surface_ready = bool(rows and not blockers and metrics_complete)
    first_blocked_target = next(
        (
            row.get("case_id") or row.get("candidate_id") or "operator_intake"
            for row in rows
            if row["blockers"]
        ),
        "top_k_refinement_operator_intake" if blockers else "",
    )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(intake_path=intake_path, contract_path=contract_path),
            reused_evidence=False,
            reuse_policy="pocketmd_lite_topk_survival_report_materialized_from_operator_intake",
            repo_root=repo_root,
        ),
        "status": "ready" if product_surface_ready else "operator_evidence_required",
        "contract_pass": product_surface_ready,
        "product_surface_ready": product_surface_ready,
        "materialization_schema_version": MATERIALIZATION_SCHEMA_VERSION,
        "contract_schema_version": _contract_schema_version(contract),
        "real_refinement_case_count": summary["real_refinement_case_count"],
        "top_k_candidate_count": summary["top_k_candidate_count"],
        "rows": rows,
        "summary": summary,
        "required_metrics": list(REQUIRED_METRICS),
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": list(dict.fromkeys(root_cause_tags)),
        "blockers": blockers,
        "blocked_claims": list(BLOCKED_CLAIMS),
        "next_actions": (
            [
                "review_pocketmd_lite_topk_survival_report",
                "regenerate_pocketmd_lite_science_product_surface",
                "regenerate_pm_release_gate_report",
            ]
            if product_surface_ready
            else [
                "attach_top_k_candidate_refinement_rows",
                "rerun_pocketmd_lite_topk_survival_materializer",
                "resolve_report_blockers",
                "regenerate_pocketmd_lite_science_product_surface",
            ]
        ),
        "materialization_report": {
            "schema_version": MATERIALIZATION_SCHEMA_VERSION,
            "operator_intake_row_count": len(rows),
            "real_refinement_case_count": summary["real_refinement_case_count"],
            "top_k_candidate_count": summary["top_k_candidate_count"],
            "metric_complete": metrics_complete,
            "blocker_count": len(blockers),
            "product_surface_ready": product_surface_ready,
        },
        "summary_line": (
            "PocketMD Lite top-k survival report: PASS | "
            f"cases={summary['real_refinement_case_count']} | "
            f"candidates={summary['top_k_candidate_count']} | "
            f"local_min_survival={summary['local_min_survival_rate']}"
            if product_surface_ready
            else (
                "PocketMD Lite top-k survival report: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'} | "
                f"blockers={len(blockers)}"
            )
        ),
        "claim_boundary": (
            "This report materializes bounded PocketMD Lite evidence from operator-attached "
            "top-k refinement rows. It does not run MD, create candidate rows, infer FEP, "
            "or unlock broad all-atom dynamics claims."
        ),
    }


def build_pocketmd_lite_science_product_surface(
    report: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    report_path: Path | None = None,
    contract_path: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    product_surface_ready = bool(report.get("product_surface_ready") and report.get("contract_pass"))
    status = "ready" if product_surface_ready else "locked"
    blockers = _as_list(report.get("blockers"))
    root_cause_tags = _as_list(report.get("root_cause_tags"))
    first_blocked_target = _string(report.get("first_blocked_target"))
    if not product_surface_ready and not first_blocked_target:
        first_blocked_target = "top_k_refinement_operator_intake"

    return {
        "schema_version": SURFACE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(intake_path=report_path, contract_path=contract_path),
            reused_evidence=False,
            reuse_policy="pocketmd_lite_science_product_surface_from_topk_survival_report",
            repo_root=repo_root,
        ),
        "surface_id": "pocketmd_lite_science_product_surface",
        "science_surface_family": "pocketmd_lite",
        "surface_scope": "pocketmd_lite_top_k_refinement",
        "surface_kind": "science_product_surface",
        "product_capability_id": "pocketmd_lite_top_k_refinement",
        "status": status,
        "reason_code": "PASS" if product_surface_ready else "ERR_POCKETMD_LITE_PRODUCT_SURFACE_LOCKED",
        "contract_pass": product_surface_ready,
        "locked": not product_surface_ready,
        "claim_locked": not product_surface_ready,
        "product_surface_ready": product_surface_ready,
        "first_blocked_target": "" if product_surface_ready else first_blocked_target,
        "root_cause_tags": [] if product_surface_ready else root_cause_tags,
        "blockers": [] if product_surface_ready else blockers,
        "blocked_claims": list(BLOCKED_CLAIMS),
        "required_receipts": [
            "top_k_candidate_refinement_rows",
            "local_min_survival_report",
            "contact_persistence_report",
            "h_bond_persistence_report",
            "clash_relief_report",
            "uncertainty_summary",
        ],
        "linked_artifacts": {
            "contract": str(contract_path or DEFAULT_CONTRACT),
            "topk_survival_report": str(report_path or DEFAULT_REPORT_OUT),
            "readonly_api": str(DEFAULT_READONLY_API),
            "delivery_handoff": str(DEFAULT_HANDOFF),
        },
        "readiness_summary": {
            "contract_ready": bool(contract.get("contract_pass")) if isinstance(contract, dict) else False,
            "readonly_api_ready": True,
            "handoff_ready": True,
            "real_refinement_case_count": int(report.get("real_refinement_case_count") or 0),
            "top_k_candidate_count": int(report.get("top_k_candidate_count") or 0),
            "blocked_claim_count": len(BLOCKED_CLAIMS),
            "summary": report.get("summary", {}),
        },
        "materializer": {
            "schema_version": MATERIALIZATION_SCHEMA_VERSION,
            "script": "scripts/materialize_pocketmd_lite_topk_survival_report.py",
            "report_path": str(report_path or DEFAULT_REPORT_OUT),
        },
        "goal_roadmap_linkage": {
            "phase": "Phase 4",
            "roadmap_item": "PocketMD Lite science product surface",
            "bottleneck": (
                "pocketmd_lite_science_product_surface_ready"
                if product_surface_ready
                else "pocketmd_lite_science_product_surface_locked"
            ),
            "next_goal_actions": (
                [
                    "publish_pocketmd_lite_readonly_api",
                    "regenerate_product_capabilities_surface",
                    "regenerate_goal_bottleneck_action_board",
                ]
                if product_surface_ready
                else [
                    "run_pocketmd_lite_topk_survival_materializer",
                    "publish_pocketmd_lite_readonly_api",
                    "regenerate_product_capabilities_surface",
                    "regenerate_goal_bottleneck_action_board",
                ]
            ),
        },
        "next_actions": (
            [
                "review_pocketmd_lite_topk_survival_report",
                "publish_pocketmd_lite_readonly_api",
                "regenerate_pm_release_gate_report",
            ]
            if product_surface_ready
            else [
                "attach_top_k_candidate_refinement_rows",
                "run_pocketmd_lite_topk_survival_materializer",
                "regenerate_pocketmd_lite_science_product_surface",
                "regenerate_pm_release_gate_report",
            ]
        ),
        "summary_line": (
            "PocketMD Lite science product surface: PASS | "
            f"cases={int(report.get('real_refinement_case_count') or 0)} | "
            f"candidates={int(report.get('top_k_candidate_count') or 0)}"
            if product_surface_ready
            else (
                "PocketMD Lite science product surface: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'}"
            )
        ),
        "claim_boundary": (
            "PocketMD Lite is exposed as a bounded science product surface for top-k "
            "local refinement evidence only. Broad all-atom MD, FEP, long-timescale "
            "dynamics, and de novo binding claims remain locked."
        ),
    }


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--out-surface", type=Path, default=DEFAULT_SURFACE_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root
    intake_path = _resolve(repo_root, args.intake)
    contract_path = _resolve(repo_root, args.contract)
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    contract = _load_optional_json(contract_path)
    report = materialize_pocketmd_lite_topk_survival_report(
        intake,
        contract=contract,
        repo_root=repo_root,
        intake_path=args.intake,
        contract_path=args.contract if contract_path.exists() else None,
    )

    out_report = _resolve(repo_root, args.out_report)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(_json_text(report), encoding="utf-8")

    surface = build_pocketmd_lite_science_product_surface(
        report,
        contract=contract,
        report_path=args.out_report,
        contract_path=args.contract if contract_path.exists() else None,
        repo_root=repo_root,
    )
    out_surface = _resolve(repo_root, args.out_surface)
    out_surface.parent.mkdir(parents=True, exist_ok=True)
    out_surface.write_text(_json_text(surface), encoding="utf-8")

    print(
        "pocketmd-lite-topk-survival-materialization: "
        f"{report['status']} | cases={report['real_refinement_case_count']} | "
        f"candidates={report['top_k_candidate_count']} | blockers={len(report['blockers'])}"
    )
    return 1 if args.fail_blocked and not report["product_surface_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
