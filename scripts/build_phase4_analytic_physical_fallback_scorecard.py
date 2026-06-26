#!/usr/bin/env python3
"""Build the Phase 4 analytic/physical fallback scorecard receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.benchmark.factory import (  # noqa: E402
    build_manifest,
    generated_benchmark_factory_cases,
    run_benchmark_cases,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase4_analytic_physical_fallback_scorecard.json"
SCHEMA_VERSION = "phase4-analytic-physical-fallback-scorecard.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _stable_payload_checksum(payload: dict[str, Any]) -> str:
    text = json.dumps(
        _strip_volatile(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _physical_contract_pass(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics", {})
    errors = row.get("errors", {})
    convergence_history = row.get("convergence_history", [])
    gate_values = [
        metrics.get("residual_gate_passed"),
        metrics.get("increment_gate_passed"),
    ]
    gate_pass = all(value is not False for value in gate_values)
    if row.get("analysis_type") == "nonlinear_static_material_mesh":
        gate_pass = gate_pass and all(value is True for value in gate_values)
    return bool(
        metrics.get("residual_formula") == "F_internal_minus_F_external"
        and metrics.get("regularization_used") is False
        and metrics.get("fallback_used") is False
        and float(metrics.get("relative_residual", 1.0)) <= 1.0e-8
        and float(errors.get("tip_displacement_abs", 1.0)) <= 1.0e-12
        and float(errors.get("base_reaction_abs", 1.0)) <= 1.0e-12
        and bool(convergence_history)
        and gate_pass
    )


def _fallback_rows(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in scorecard["rows"]:
        physical_pass = _physical_contract_pass(row)
        rows.append(
            {
                "case_id": row["case_id"],
                "lane": row["lane"],
                "analysis_type": row["analysis_type"],
                "commercial_reference_available": False,
                "fallback_basis": [
                    "analytic_expected_output_comparisons",
                    "physical_residual_equilibrium_metrics",
                    "convergence_history_presence",
                    "regularization_and_fallback_absence",
                ],
                "analytic_expected_output_contract_pass": bool(
                    row["expected_output_contract_pass"] is True
                ),
                "expected_output_comparison_count": len(row["expected_output_comparisons"]),
                "physical_equilibrium_contract_pass": physical_pass,
                "residual_formula": row["metrics"]["residual_formula"],
                "relative_residual": row["metrics"]["relative_residual"],
                "regularization_used": row["metrics"]["regularization_used"],
                "fallback_used": row["metrics"]["fallback_used"],
                "convergence_history_count": len(row["convergence_history"]),
                "contract_pass": bool(
                    row["expected_output_contract_pass"] is True and physical_pass
                ),
            }
        )
    return rows


def build_phase4_analytic_physical_fallback_scorecard(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    cases = generated_benchmark_factory_cases()
    manifest = build_manifest(cases)
    scorecard = run_benchmark_cases(cases)
    rows = _fallback_rows(scorecard)
    pass_count = sum(1 for row in rows if row["contract_pass"])
    analytic_pass_count = sum(
        1 for row in rows if row["analytic_expected_output_contract_pass"]
    )
    physical_pass_count = sum(
        1 for row in rows if row["physical_equilibrium_contract_pass"]
    )
    contract_pass = bool(
        rows
        and pass_count == len(rows)
        and scorecard["expected_output_contract_pass"] is True
        and scorecard["contract_pass"] is True
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase4_analytic_physical_fallback_scorecard.py"),
                Path("src/structural_analysis/benchmark/factory.py"),
                Path("src/structural_analysis/benchmark/cli.py"),
                Path("src/structural_analysis/api/core.py"),
                Path("src/structural_analysis/solvers/linear/static.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("src/structure-viewer/viewer-commercial-tool-crosswalk-model.js"),
                Path("src/structure-viewer/viewer-report-export.js"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "phase3_closure_claim": False,
        "phase4_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "selected_benchmark_lanes": manifest["lanes"],
        "truth_class": "analytic_physical_fallback",
        "commercial_reference_case_count": 0,
        "operator_reference_package_attached": False,
        "two_reference_solver_comparison_available": False,
        "case_count": len(rows),
        "pass_count": pass_count,
        "analytic_expected_output_pass_count": analytic_pass_count,
        "physical_equilibrium_pass_count": physical_pass_count,
        "expected_output_comparison_count": scorecard[
            "expected_output_comparison_count"
        ],
        "expected_output_comparison_pass_count": scorecard[
            "expected_output_comparison_pass_count"
        ],
        "phase3_seed_manifest_checksum": _stable_payload_checksum(manifest),
        "phase3_seed_scorecard_checksum": _stable_payload_checksum(scorecard),
        "fallback_scope": {
            "supports_cases_without_commercial_outputs": True,
            "supports_commercial_cross_solver_closure": False,
            "supports_two_reference_solver_comparison": False,
            "supports_gui_story_member_mode_traceability": False,
            "gui_traceability_contract_available": True,
            "gui_traceability_contract_scope": "commercial_crosswalk_schema_and_report_export_only",
            "source": "generated_phase3_seed_manifest_and_scorecard",
        },
        "remaining_blockers": [
            "operator_reference_package_missing",
            "operator_reference_outputs_missing",
            "two_reference_solver_comparison_not_available",
            "commercial_cross_solver_execution_missing",
            "operator_comparison_trace_rows_missing",
        ],
        "rows": rows,
        "claim_boundary": (
            "This receipt proves that generated Phase 3 seed cases without commercial "
            "operator outputs can still be evaluated by analytic expected-output checks "
            "and physical residual/equilibrium metrics. It is fallback evidence only; it "
            "does not attach commercial outputs, compare two independent reference solvers, "
            "execute GUI story/member/mode trace rows for operator data, close Phase 4, "
            "close Phase 6, or promote commercial readiness."
        ),
    }


def write_phase4_analytic_physical_fallback_scorecard(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase4_analytic_physical_fallback_scorecard(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase4_analytic_physical_fallback_scorecard(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase4_analytic_physical_fallback_scorecard(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase4_analytic_physical_fallback_scorecard_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            "phase4_analytic_physical_fallback_scorecard_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase4_analytic_physical_fallback_scorecard_mismatch"
    return True, "phase4_analytic_physical_fallback_scorecard_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase4_analytic_physical_fallback_scorecard(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 4 analytic physical fallback scorecard check: {message}")
        return 0 if ok else 1
    payload = write_phase4_analytic_physical_fallback_scorecard(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 4 analytic physical fallback scorecard: "
            f"{payload['status']} | cases={payload['case_count']} | "
            f"pass={payload['pass_count']} | phase4_closure={payload['phase4_closure_claim']}"
        )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
