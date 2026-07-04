#!/usr/bin/env python3
"""Materialize PocketMD Lite top-k rows from a completed template CSV."""

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

from build_pocketmd_lite_topk_rows_template_preflight import (  # noqa: E402
    DEFAULT_REFINEMENT_PLAN,
    DEFAULT_TEMPLATE,
    build_pocketmd_lite_topk_rows_template_preflight,
)
from materialize_pocketmd_lite_operator_intake_from_rows import (  # noqa: E402
    DEFAULT_MAX_TOP_K,
    _normalize_row,
    _read_source_rows,
    _validate_topk_integrity,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT_ROWS = PRODUCTIZATION / "pocketmd_lite_topk_rows.json"
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION / "pocketmd_lite_topk_rows_from_template_report.json"
)
SCHEMA_VERSION = "pocketmd-lite-topk-rows-from-template-materialization.v1"
ROWS_SCHEMA_VERSION = "pocketmd-lite-topk-rows.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _normalized_rows(
    *,
    repo_root: Path,
    template: Path,
    max_top_k: int,
) -> list[dict[str, Any]]:
    resolved_template = _resolve(repo_root, template)
    raw_rows = _read_source_rows(resolved_template)
    rows = [
        _normalize_row(raw_row, row_index=index, max_top_k=max_top_k)
        for index, raw_row in enumerate(raw_rows, start=1)
    ]
    _validate_topk_integrity(rows)
    return rows


def materialize_pocketmd_lite_topk_rows_from_template(
    *,
    repo_root: Path = ROOT,
    refinement_plan: Path = DEFAULT_REFINEMENT_PLAN,
    template: Path = DEFAULT_TEMPLATE,
    out_rows: Path = DEFAULT_OUT_ROWS,
    out_report: Path = DEFAULT_OUT_REPORT,
    max_top_k: int = DEFAULT_MAX_TOP_K,
) -> dict[str, Any]:
    if max_top_k < 1:
        raise ValueError("max_top_k_must_be_positive")
    preflight = build_pocketmd_lite_topk_rows_template_preflight(
        repo_root=repo_root,
        refinement_plan=refinement_plan,
        template=template,
        expected_rows=out_rows,
    )
    rows: list[dict[str, Any]] = []
    rows_written = False
    materialization_error = ""
    if preflight.get("top_k_template_ready"):
        try:
            rows = _normalized_rows(
                repo_root=repo_root,
                template=template,
                max_top_k=max_top_k,
            )
        except Exception as exc:
            materialization_error = str(exc)
        else:
            rows_payload = {
                "schema_version": ROWS_SCHEMA_VERSION,
                **release_evidence_metadata(
                    input_paths=[
                        Path("scripts/materialize_pocketmd_lite_topk_rows_from_template.py"),
                        Path("scripts/build_pocketmd_lite_topk_rows_template_preflight.py"),
                        Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
                        refinement_plan,
                        template,
                    ],
                    reused_evidence=False,
                    reuse_policy="pocketmd_lite_topk_rows_materialized_from_operator_completed_template",
                    repo_root=repo_root,
                ),
                "top_k_refinement_rows": rows,
                "template_artifact": str(template),
                "refinement_plan_artifact": str(refinement_plan),
                "row_count": len(rows),
                "case_count": len({str(row["case_id"]) for row in rows}),
                "claim_boundary": (
                    "These rows are copied from an operator-completed PocketMD Lite "
                    "top-k template after template preflight validation. They still "
                    "require operator input source receipts and the PocketMD Lite "
                    "survival materializer before Phase 4 actual closure."
                ),
            }
            _write_json(repo_root, out_rows, rows_payload)
            rows_written = True

    status = "rows_materialized" if rows_written else "template_not_ready"
    if materialization_error:
        status = "materialization_blocked"
    blockers = []
    if not preflight.get("top_k_template_ready"):
        blockers.append("pocketmd_lite_topk_template_not_ready")
    if materialization_error:
        blockers.append(f"pocketmd_lite_topk_template_materialization_failed:{materialization_error}")

    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_pocketmd_lite_topk_rows_from_template.py"),
                Path("scripts/build_pocketmd_lite_topk_rows_template_preflight.py"),
                Path("scripts/materialize_pocketmd_lite_operator_intake_from_rows.py"),
                refinement_plan,
                template,
            ],
            reused_evidence=False,
            reuse_policy="pocketmd_lite_topk_rows_from_template_materialization_report",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": rows_written,
        "rows_materialized": rows_written,
        "template_ready": bool(preflight.get("top_k_template_ready")),
        "template_preflight_status": str(preflight.get("status") or ""),
        "template_artifact": str(template),
        "refinement_plan_artifact": str(refinement_plan),
        "out_rows_artifact": str(out_rows),
        "out_report_artifact": str(out_report),
        "row_count": len(rows),
        "case_count": len({str(row["case_id"]) for row in rows}),
        "max_top_k": max_top_k,
        "blockers": blockers,
        "template_preflight_summary": dict(preflight.get("summary") or {}),
        "commands": {
            "rerun_template_preflight": (
                "python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py "
                f"--out {PRODUCTIZATION / 'pocketmd_lite_topk_rows_template_preflight.json'} "
                f"--out-md {PRODUCTIZATION / 'pocketmd_lite_topk_rows_template_preflight.md'}"
            ),
            "rerun_rows_materialization": (
                "python3 scripts/materialize_pocketmd_lite_topk_rows_from_template.py "
                f"--template {template} --out-rows {out_rows} --out-report {out_report}"
            ),
            "materialize_operator_intake": (
                "python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py "
                f"--rows {out_rows} "
                f"--out {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
            "materialize_survival_report": (
                "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
                f"--intake {PRODUCTIZATION / 'pocketmd_lite_operator_intake.json'} "
                f"--contract {PRODUCTIZATION / 'pocketmd_lite_contract.json'} "
                f"--out-report {PRODUCTIZATION / 'pocketmd_lite_topk_survival_report.json'} "
                "--out-surface implementation/phase1/release_evidence/surface/"
                "pocketmd_lite_science_product_surface.json --fail-blocked"
            ),
        },
        "claim_boundary": (
            "This helper only materializes rows from a completed operator template. "
            "It does not run PocketMD Lite refinement, invent local-min/contact/"
            "H-bond/clash/uncertainty metrics, attach source receipts, or close "
            "Phase 4 without the downstream importer and survival materializer."
        ),
    }
    _write_json(repo_root, out_report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--refinement-plan", type=Path, default=DEFAULT_REFINEMENT_PLAN)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out-rows", type=Path, default=DEFAULT_OUT_ROWS)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--max-top-k", type=int, default=DEFAULT_MAX_TOP_K)
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_pocketmd_lite_topk_rows_from_template(
        repo_root=args.repo_root,
        refinement_plan=args.refinement_plan,
        template=args.template,
        out_rows=args.out_rows,
        out_report=args.out_report,
        max_top_k=args.max_top_k,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "pocketmd-lite-topk-rows-from-template: "
            f"{payload['status']} | rows={payload['row_count']} | "
            f"written={payload['rows_materialized']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
