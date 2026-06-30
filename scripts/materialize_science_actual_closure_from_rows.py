#!/usr/bin/env python3
"""Materialize GPCR and PocketMD Lite science closure from operator row files."""

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

import materialize_gpcr_hard_decoy_operator_template_from_rows as gpcr_rows  # noqa: E402
import materialize_gpcr_hard_decoy_suite_report as gpcr_suite  # noqa: E402
import materialize_pocketmd_lite_operator_intake_from_rows as pocketmd_rows  # noqa: E402
import materialize_pocketmd_lite_topk_survival_report as pocketmd_survival  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OUT = PRODUCTIZATION / "science_actual_closure_row_audit.json"
DEFAULT_GPCR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_GPCR_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"
DEFAULT_GPCR_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_POCKETMD_INTAKE = PRODUCTIZATION / "pocketmd_lite_operator_intake.json"
DEFAULT_POCKETMD_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_POCKETMD_SURFACE = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_POCKETMD_CONTRACT = PRODUCTIZATION / "pocketmd_lite_contract.json"

SCHEMA_VERSION = "science-actual-closure-row-audit.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _load_optional_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _gpcr_row_intake_contract(
    *,
    template_out: Path,
    report_out: Path,
    surface_out: Path,
) -> dict[str, Any]:
    return {
        "component_id": "gpcr_hard_decoy_actual_closure",
        "row_input_id": "gpcr_rows",
        "accepted_formats": list(gpcr_rows.SUPPORTED_ROW_FORMATS),
        "required_targets": list(gpcr_suite.REQUIRED_TARGETS),
        "required_flat_row_fields": [
            "target_id",
            *gpcr_suite.RAW_RANKING_ROW_FIELDS,
        ],
        "optional_flat_row_fields": ["score_direction"],
        "accepted_score_direction_values": [
            "higher_is_better",
            "lower_is_better",
        ],
        "default_score_direction": gpcr_rows.DEFAULT_SCORE_DIRECTION,
        "source_receipt_required_fields": [
            "source_id",
            "source_url",
            "source_license",
            "source_artifact_sha256",
        ],
        "raw_row_quality_minimums": dict(gpcr_suite.RAW_ROW_QUALITY_CRITERIA),
        "phase3_exit_criteria": dict(gpcr_suite.EXIT_CRITERIA),
        "actual_closure_criterion_id": gpcr_suite.ACTUAL_CLOSURE_CRITERION_ID,
        "expected_outputs": {
            "operator_template": str(template_out),
            "suite_report": str(report_out),
            "evidence_surface": str(surface_out),
        },
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--gpcr-rows <gpcr-hard-decoy-rows.csv|tsv|json|jsonl|ndjson> "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license> --fail-blocked"
        ),
        "claim_boundary": (
            "GPCR Phase 3 actual closure requires operator-attached raw hard-decoy "
            "ranking rows for every required target plus a verifiable source receipt. "
            "Summary metrics or fixture rows do not satisfy actual closure."
        ),
    }


def _pocketmd_row_intake_contract(
    *,
    intake_out: Path,
    report_out: Path,
    surface_out: Path,
    contract_path: Path,
    max_top_k: int,
) -> dict[str, Any]:
    return {
        "component_id": "pocketmd_lite_topk_actual_closure",
        "row_input_id": "pocketmd_rows",
        "accepted_formats": list(pocketmd_rows.SUPPORTED_ROW_FORMATS),
        "max_top_k": max_top_k,
        "required_case_fields": list(pocketmd_survival.REQUIRED_CASE_FIELDS),
        "uncertainty_field_modes": [
            "uncertainty_interval:{low,high,unit}",
            "uncertainty_low+uncertainty_high+uncertainty_unit",
        ],
        "required_summary_metrics": list(pocketmd_survival.REQUIRED_SUMMARY_METRICS),
        "required_component_metrics": list(pocketmd_survival.REQUIRED_METRICS),
        "top_k_row_quality_minimums": dict(
            pocketmd_survival.TOPK_ROW_QUALITY_CRITERIA
        ),
        "source_receipt_required_fields": [
            "source_id",
            "source_url",
            "source_license",
            "source_artifact_sha256",
            "per_row_source_checksum",
        ],
        "blocked_claims_that_remain_locked": list(pocketmd_survival.BLOCKED_CLAIMS),
        "expected_outputs": {
            "operator_intake": str(intake_out),
            "topk_survival_report": str(report_out),
            "science_surface": str(surface_out),
        },
        "contract_path": str(contract_path),
        "materialization_command": (
            "python3 scripts/materialize_science_actual_closure_from_rows.py "
            "--pocketmd-rows <pocketmd-lite-topk-rows.csv|tsv|json|jsonl|ndjson> "
            "--source-id <source-id> --source-url <source-url> "
            "--source-license <license> --fail-blocked"
        ),
        "claim_boundary": (
            "PocketMD Lite closure is limited to top-k local refinement rows with "
            "local-min survival, contact persistence, H-bond persistence, clash "
            "relief, and uncertainty summaries. It does not unlock broad all-atom "
            "MD, FEP, long-timescale dynamics, or de novo binding claims."
        ),
    }


def _missing_component(component_id: str, blocker: str, expected_mode: str) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "status": "operator_evidence_required",
        "contract_pass": False,
        "materialized": False,
        "blockers": [blocker],
        "expected_rows_mode": expected_mode,
        "outputs": {},
    }


def _component_error(component_id: str, exc: Exception, expected_mode: str) -> dict[str, Any]:
    return {
        "component_id": component_id,
        "status": "blocked",
        "contract_pass": False,
        "materialized": False,
        "blockers": [f"{component_id}_materialization_failed:{exc}"],
        "expected_rows_mode": expected_mode,
        "outputs": {},
    }


def _materialize_gpcr(
    *,
    rows_path: Path | None,
    repo_root: Path,
    template_out: Path,
    report_out: Path,
    surface_out: Path,
    source_id: str,
    source_url: str,
    source_license: str,
    source_version: str,
) -> dict[str, Any]:
    if rows_path is None:
        return _missing_component(
            "gpcr_hard_decoy_actual_closure",
            "gpcr_hard_decoy_rows_not_provided",
            "raw_hard_decoy_rows",
        )
    try:
        template = gpcr_rows.build_gpcr_hard_decoy_operator_template_from_rows(
            rows_path=rows_path,
            repo_root=repo_root,
            source_id=source_id,
            source_url=source_url,
            source_license=source_license,
            source_version=source_version,
        )
        _write_json(repo_root, template_out, template)
        report = gpcr_suite.materialize_gpcr_hard_decoy_suite_report(
            template,
            repo_root=repo_root,
            intake_path=template_out,
        )
        _write_json(repo_root, report_out, report)
        surface = gpcr_suite.build_gpcr_evidence_surface(
            report,
            report_path=report_out,
            repo_root=repo_root,
        )
        _write_json(repo_root, surface_out, surface)
    except Exception as exc:
        return _component_error(
            "gpcr_hard_decoy_actual_closure",
            exc,
            "raw_hard_decoy_rows",
        )

    phase3_exit_gate = report.get("phase3_exit_gate")
    if not isinstance(phase3_exit_gate, dict):
        phase3_exit_gate = {}
    blockers = [str(item) for item in report.get("blockers", []) if str(item)]
    return {
        "component_id": "gpcr_hard_decoy_actual_closure",
        "status": str(report.get("status") or ""),
        "contract_pass": bool(report.get("contract_pass")),
        "materialized": True,
        "expected_rows_mode": "raw_hard_decoy_rows",
        "rows_path": str(rows_path),
        "target_pass_count": int(report.get("target_pass_count") or 0),
        "target_count": int(report.get("target_count") or 0),
        "phase3_exit_gate_status": str(phase3_exit_gate.get("status") or ""),
        "phase3_failed_criteria": [
            str(item) for item in phase3_exit_gate.get("failed_criteria", [])
        ],
        "blockers": blockers,
        "outputs": {
            "operator_template": str(template_out),
            "suite_report": str(report_out),
            "evidence_surface": str(surface_out),
        },
    }


def _materialize_pocketmd(
    *,
    rows_path: Path | None,
    repo_root: Path,
    intake_out: Path,
    report_out: Path,
    surface_out: Path,
    contract_path: Path,
    source_id: str,
    source_url: str,
    source_license: str,
    source_version: str,
    max_top_k: int,
) -> dict[str, Any]:
    if rows_path is None:
        return _missing_component(
            "pocketmd_lite_topk_actual_closure",
            "pocketmd_lite_topk_rows_not_provided",
            "raw_top_k_refinement_rows",
        )
    try:
        intake = pocketmd_rows.build_pocketmd_lite_operator_intake_from_rows(
            rows_path=rows_path,
            repo_root=repo_root,
            source_id=source_id,
            source_url=source_url,
            source_license=source_license,
            source_version=source_version,
            max_top_k=max_top_k,
        )
        _write_json(repo_root, intake_out, intake)
        contract = _load_optional_json(repo_root, contract_path)
        resolved_contract = _resolve(repo_root, contract_path)
        report = pocketmd_survival.materialize_pocketmd_lite_topk_survival_report(
            intake,
            contract=contract,
            repo_root=repo_root,
            intake_path=intake_out,
            contract_path=contract_path if resolved_contract.exists() else None,
        )
        _write_json(repo_root, report_out, report)
        surface = pocketmd_survival.build_pocketmd_lite_science_product_surface(
            report,
            contract=contract,
            report_path=report_out,
            contract_path=contract_path if resolved_contract.exists() else None,
            repo_root=repo_root,
        )
        _write_json(repo_root, surface_out, surface)
    except Exception as exc:
        return _component_error(
            "pocketmd_lite_topk_actual_closure",
            exc,
            "raw_top_k_refinement_rows",
        )

    phase4_exit_gate = report.get("phase4_exit_gate")
    if not isinstance(phase4_exit_gate, dict):
        phase4_exit_gate = {}
    blockers = [str(item) for item in report.get("blockers", []) if str(item)]
    return {
        "component_id": "pocketmd_lite_topk_actual_closure",
        "status": str(report.get("status") or ""),
        "contract_pass": bool(report.get("contract_pass")),
        "materialized": True,
        "expected_rows_mode": "raw_top_k_refinement_rows",
        "rows_path": str(rows_path),
        "real_refinement_case_count": int(report.get("real_refinement_case_count") or 0),
        "top_k_candidate_count": int(report.get("top_k_candidate_count") or 0),
        "phase4_exit_gate_status": str(phase4_exit_gate.get("status") or ""),
        "phase4_failed_criteria": [
            str(item) for item in phase4_exit_gate.get("failed_criteria", [])
        ],
        "blockers": blockers,
        "outputs": {
            "operator_intake": str(intake_out),
            "topk_survival_report": str(report_out),
            "science_surface": str(surface_out),
        },
    }


def build_science_actual_closure_audit(
    *,
    repo_root: Path = ROOT,
    gpcr_rows_path: Path | None = None,
    pocketmd_rows_path: Path | None = None,
    gpcr_template_out: Path = DEFAULT_GPCR_TEMPLATE,
    gpcr_report_out: Path = DEFAULT_GPCR_REPORT,
    gpcr_surface_out: Path = DEFAULT_GPCR_SURFACE,
    pocketmd_intake_out: Path = DEFAULT_POCKETMD_INTAKE,
    pocketmd_report_out: Path = DEFAULT_POCKETMD_REPORT,
    pocketmd_surface_out: Path = DEFAULT_POCKETMD_SURFACE,
    pocketmd_contract_path: Path = DEFAULT_POCKETMD_CONTRACT,
    source_id: str = "",
    source_url: str = "",
    source_license: str = "",
    source_version: str = "",
    pocketmd_max_top_k: int = pocketmd_rows.DEFAULT_MAX_TOP_K,
) -> dict[str, Any]:
    row_intake_contracts = {
        "gpcr_rows": _gpcr_row_intake_contract(
            template_out=gpcr_template_out,
            report_out=gpcr_report_out,
            surface_out=gpcr_surface_out,
        ),
        "pocketmd_rows": _pocketmd_row_intake_contract(
            intake_out=pocketmd_intake_out,
            report_out=pocketmd_report_out,
            surface_out=pocketmd_surface_out,
            contract_path=pocketmd_contract_path,
            max_top_k=pocketmd_max_top_k,
        ),
    }
    gpcr = _materialize_gpcr(
        rows_path=gpcr_rows_path,
        repo_root=repo_root,
        template_out=gpcr_template_out,
        report_out=gpcr_report_out,
        surface_out=gpcr_surface_out,
        source_id=source_id,
        source_url=source_url,
        source_license=source_license,
        source_version=source_version,
    )
    pocketmd = _materialize_pocketmd(
        rows_path=pocketmd_rows_path,
        repo_root=repo_root,
        intake_out=pocketmd_intake_out,
        report_out=pocketmd_report_out,
        surface_out=pocketmd_surface_out,
        contract_path=pocketmd_contract_path,
        source_id=source_id,
        source_url=source_url,
        source_license=source_license,
        source_version=source_version,
        max_top_k=pocketmd_max_top_k,
    )
    components = [gpcr, pocketmd]
    blockers = [
        f"{component['component_id']}::{blocker}"
        for component in components
        for blocker in component.get("blockers", [])
    ]
    contract_pass = all(bool(component.get("contract_pass")) for component in components)
    input_paths = [
        Path("scripts/materialize_science_actual_closure_from_rows.py"),
        Path("scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py"),
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
        Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
        Path("scripts/materialize_pocketmd_lite_topk_survival_report.py"),
    ]
    if gpcr_rows_path is not None:
        input_paths.append(gpcr_rows_path)
    if pocketmd_rows_path is not None:
        input_paths.append(pocketmd_rows_path)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="science_actual_closure_audit_from_operator_rows",
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "operator_evidence_required",
        "contract_pass": contract_pass,
        "blockers": blockers,
        "component_count": len(components),
        "component_ready_count": sum(1 for component in components if component.get("contract_pass")),
        "components": components,
        "missing_row_inputs": [
            row_input_id
            for row_input_id, rows_path in (
                ("gpcr_rows", gpcr_rows_path),
                ("pocketmd_rows", pocketmd_rows_path),
            )
            if rows_path is None
        ],
        "row_intake_contracts": row_intake_contracts,
        "required_actual_closures": [
            "gpcr_hard_decoy_actual_closure",
            "pocketmd_lite_topk_actual_closure",
        ],
        "claim_boundary": (
            "This runner only materializes operator-attached raw rows through the "
            "existing GPCR and PocketMD Lite materializers. It does not generate "
            "docking scores, run MD, infer missing metrics, or treat fixture/proxy "
            "rows as actual science closure evidence."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--gpcr-rows", type=Path)
    parser.add_argument("--pocketmd-rows", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--gpcr-template-out", type=Path, default=DEFAULT_GPCR_TEMPLATE)
    parser.add_argument("--gpcr-report-out", type=Path, default=DEFAULT_GPCR_REPORT)
    parser.add_argument("--gpcr-surface-out", type=Path, default=DEFAULT_GPCR_SURFACE)
    parser.add_argument("--pocketmd-intake-out", type=Path, default=DEFAULT_POCKETMD_INTAKE)
    parser.add_argument("--pocketmd-report-out", type=Path, default=DEFAULT_POCKETMD_REPORT)
    parser.add_argument("--pocketmd-surface-out", type=Path, default=DEFAULT_POCKETMD_SURFACE)
    parser.add_argument("--pocketmd-contract", type=Path, default=DEFAULT_POCKETMD_CONTRACT)
    parser.add_argument("--source-id", default="")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-license", default="")
    parser.add_argument("--source-version", default="")
    parser.add_argument("--pocketmd-max-top-k", type=int, default=pocketmd_rows.DEFAULT_MAX_TOP_K)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_science_actual_closure_audit(
        repo_root=args.repo_root,
        gpcr_rows_path=args.gpcr_rows,
        pocketmd_rows_path=args.pocketmd_rows,
        gpcr_template_out=args.gpcr_template_out,
        gpcr_report_out=args.gpcr_report_out,
        gpcr_surface_out=args.gpcr_surface_out,
        pocketmd_intake_out=args.pocketmd_intake_out,
        pocketmd_report_out=args.pocketmd_report_out,
        pocketmd_surface_out=args.pocketmd_surface_out,
        pocketmd_contract_path=args.pocketmd_contract,
        source_id=args.source_id,
        source_url=args.source_url,
        source_license=args.source_license,
        source_version=args.source_version,
        pocketmd_max_top_k=args.pocketmd_max_top_k,
    )
    _write_json(args.repo_root, args.out, payload)
    print(
        "science-actual-closure-row-audit: "
        f"{payload['status']} | ready={payload['component_ready_count']}/"
        f"{payload['component_count']} | blockers={len(payload['blockers'])}"
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
