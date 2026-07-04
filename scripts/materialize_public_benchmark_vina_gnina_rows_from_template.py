#!/usr/bin/env python3
"""Materialize Vina/GNINA rows from a completed operator template CSV."""

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

from build_public_benchmark_vina_gnina_rows_template_preflight import (  # noqa: E402
    DEFAULT_RUNTIME_READINESS,
    DEFAULT_TEMPLATE,
    build_public_benchmark_vina_gnina_rows_template_preflight,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    load_vina_gnina_intake_payload,
    materialize_vina_gnina_comparison_adapter,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT_ROWS = PRODUCTIZATION / "public_benchmark_vina_gnina_rows.json"
DEFAULT_OUT_REPORT = (
    PRODUCTIZATION / "public_benchmark_vina_gnina_rows_from_template_report.json"
)
SCHEMA_VERSION = "public-benchmark-vina-gnina-rows-from-template-materialization.v1"
ROWS_SCHEMA_VERSION = "public-benchmark-vina-gnina-rows.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _engine_run_count(cases: list[dict[str, Any]]) -> int:
    return sum(
        len(case.get("engine_runs", []))
        for case in cases
        if isinstance(case.get("engine_runs"), list)
    )


def materialize_public_benchmark_vina_gnina_rows_from_template(
    *,
    repo_root: Path = ROOT,
    runtime_readiness: Path = DEFAULT_RUNTIME_READINESS,
    template: Path = DEFAULT_TEMPLATE,
    out_rows: Path = DEFAULT_OUT_ROWS,
    out_report: Path = DEFAULT_OUT_REPORT,
) -> dict[str, Any]:
    preflight = build_public_benchmark_vina_gnina_rows_template_preflight(
        repo_root=repo_root,
        runtime_readiness=runtime_readiness,
        template=template,
        expected_rows=out_rows,
    )
    cases: list[dict[str, Any]] = []
    rows_written = False
    adapter_status = "not_run"
    adapter_summary: dict[str, Any] = {}
    materialization_error = ""

    if preflight.get("adapter_template_ready"):
        try:
            intake_payload = load_vina_gnina_intake_payload(_resolve(repo_root, template))
            cases = [
                row
                for row in intake_payload.get("cases", [])
                if isinstance(row, dict)
            ]
            adapter = materialize_vina_gnina_comparison_adapter(
                {"cases": cases},
                repo_root=repo_root,
                intake_path=template,
            )
            adapter_status = str(adapter.get("status") or "")
            adapter_summary = dict(adapter.get("summary") or {})
            if not adapter.get("public_benchmark_engine_comparison_ready"):
                materialization_error = "vina_gnina_adapter_validation_failed"
            else:
                rows_payload = {
                    "schema_version": ROWS_SCHEMA_VERSION,
                    **release_evidence_metadata(
                        input_paths=[
                            Path(
                                "scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py"
                            ),
                            Path(
                                "scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"
                            ),
                            Path(
                                "scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"
                            ),
                            runtime_readiness,
                            template,
                        ],
                        reused_evidence=False,
                        reuse_policy=(
                            "public_benchmark_vina_gnina_rows_materialized_from_"
                            "operator_completed_template"
                        ),
                        repo_root=repo_root,
                    ),
                    "cases": cases,
                    "template_artifact": str(template),
                    "runtime_readiness_artifact": str(runtime_readiness),
                    "case_count": len(cases),
                    "engine_run_count": _engine_run_count(cases),
                    "claim_boundary": (
                        "These rows are copied from an operator-completed Vina/GNINA "
                        "template after template preflight and adapter validation. "
                        "They do not run Vina or GNINA, compute symmetry-aware RMSD, "
                        "or close Public Benchmark Phase 2 without downstream row "
                        "audit materialization."
                    ),
                }
                _write_json(repo_root, out_rows, rows_payload)
                rows_written = True
        except Exception as exc:
            materialization_error = str(exc)

    status = "rows_materialized" if rows_written else "template_not_ready"
    if materialization_error:
        status = "materialization_blocked"
    blockers = []
    if not preflight.get("adapter_template_ready"):
        blockers.append("public_benchmark_vina_gnina_rows_template_not_ready")
    if materialization_error:
        blockers.append(
            "public_benchmark_vina_gnina_rows_template_materialization_failed:"
            f"{materialization_error}"
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py"),
                Path("scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py"),
                Path(
                    "scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py"
                ),
                runtime_readiness,
                template,
            ],
            reused_evidence=False,
            reuse_policy=(
                "public_benchmark_vina_gnina_rows_from_template_materialization_report"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": rows_written,
        "rows_materialized": rows_written,
        "template_ready": bool(preflight.get("adapter_template_ready")),
        "template_preflight_status": str(preflight.get("status") or ""),
        "adapter_validation_status": adapter_status,
        "adapter_validation_summary": adapter_summary,
        "template_artifact": str(template),
        "runtime_readiness_artifact": str(runtime_readiness),
        "out_rows_artifact": str(out_rows),
        "out_report_artifact": str(out_report),
        "case_count": len(cases),
        "engine_run_count": _engine_run_count(cases),
        "blockers": blockers,
        "template_preflight_summary": dict(preflight.get("summary") or {}),
        "commands": {
            "rerun_template_preflight": (
                "python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py "
                f"--out {PRODUCTIZATION / 'public_benchmark_vina_gnina_rows_template_preflight.json'} "
                f"--out-md {PRODUCTIZATION / 'public_benchmark_vina_gnina_rows_template_preflight.md'}"
            ),
            "rerun_rows_materialization": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py "
                f"--template {template} --out-rows {out_rows} --out-report {out_report}"
            ),
            "materialize_adapter": (
                "python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py "
                f"--intake {out_rows} "
                f"--out-adapter {PRODUCTIZATION / 'public_benchmark_vina_gnina_comparison_adapter.json'} "
                f"--out-report {PRODUCTIZATION / 'public_benchmark_vina_gnina_materialization_report.json'} "
                "--fail-blocked"
            ),
            "rerun_phase2_row_audit": (
                "python3 scripts/materialize_public_benchmark_phase2_from_rows.py "
                f"--vina-gnina-rows {out_rows} --fail-blocked"
            ),
        },
        "claim_boundary": (
            "This helper only materializes rows from a completed operator template. "
            "It does not run Vina/GNINA, invent engine output checksums, synthesize "
            "symmetry-aware RMSD or pose-success labels, or close Public Benchmark "
            "Phase 2 without the downstream adapter and row audit."
        ),
    }
    _write_json(repo_root, out_report, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--runtime-readiness", type=Path, default=DEFAULT_RUNTIME_READINESS)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--out-rows", type=Path, default=DEFAULT_OUT_ROWS)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_OUT_REPORT)
    parser.add_argument("--fail-blocked", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = materialize_public_benchmark_vina_gnina_rows_from_template(
        repo_root=args.repo_root,
        runtime_readiness=args.runtime_readiness,
        template=args.template,
        out_rows=args.out_rows,
        out_report=args.out_report,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-vina-gnina-rows-from-template: "
            f"{payload['status']} | cases={payload['case_count']} | "
            f"written={payload['rows_materialized']}"
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
