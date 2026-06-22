#!/usr/bin/env python3
"""Build the Phase 4/6 commercial comparison import template receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase4_commercial_comparison_import_template.json"

REQUIRED_RESULT_FIELDS = [
    "case_id",
    "modeling_convention_id",
    "modeling_assumption_diagnostics",
    "engine_name",
    "engine_version",
    "input_checksum",
    "node_member_mapping_coverage",
    "displacement_metrics",
    "reaction_metrics",
    "member_force_metrics",
    "modal_metrics",
    "nonlinear_curve_metrics",
    "equilibrium_residual",
    "runtime",
    "peak_memory",
    "warnings",
    "unsupported_features",
]

MODELING_ASSUMPTION_DIAGNOSTIC_ORDER = [
    "unit_system",
    "local_axis_convention",
    "rigid_offset_policy",
    "end_release_policy",
    "diaphragm_policy",
    "mass_source_policy",
    "self_weight_policy",
    "material_modulus_convention",
    "shell_formulation",
    "mesh_density",
    "damping_policy",
    "p_delta_policy",
    "eigen_solver",
    "load_combinations",
    "convergence_tolerance",
]

CSV_COLUMNS = [
    "case_id",
    "modeling_convention_id",
    "modeling_assumption_diagnostic_status",
    "primary_modeling_assumption_delta",
    "modeling_assumption_delta_codes",
    "engine_name",
    "engine_version",
    "input_checksum",
    "node_mapping_coverage_ratio",
    "member_mapping_coverage_ratio",
    "max_displacement_rel_error",
    "max_reaction_rel_error",
    "max_member_force_rel_error",
    "mode_frequency_rel_error",
    "mode_shape_mac",
    "nonlinear_peak_rel_error",
    "nonlinear_curve_area_rel_error",
    "equilibrium_residual_norm",
    "runtime_seconds",
    "peak_memory_mb",
    "warning_codes",
    "unsupported_feature_codes",
]


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


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def build_phase4_commercial_comparison_import_template(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    return {
        "schema_version": "phase4-commercial-comparison-import-template.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase4_commercial_comparison_import_template.py"),
                Path("implementation/phase1/release_evidence/productization/commercial_solver_cross_validation.json"),
                Path("implementation/phase1/report_commercial_solver_cross_validation.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready",
        "contract_pass": True,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "selected_benchmark_lanes": ["commercial-cross-solver"],
        "truth_class": "comparison_reference",
        "template_scope": {
            "operator_files_bundled": False,
            "commercial_results_are_absolute_truth": False,
            "requires_two_reference_solvers_for_phase4_closure": True,
            "supports_operator_attached_csv": True,
            "supports_operator_attached_json": True,
        },
        "comparison_diagnostic_policy": {
            "policy_id": "modeling_assumption_first",
            "commercial_outputs_are_absolute_truth": False,
            "solver_correctness_claim_allowed": False,
            "diagnostic_order": MODELING_ASSUMPTION_DIAGNOSTIC_ORDER,
            "required_result_field": "modeling_assumption_diagnostics",
            "difference_triage": (
                "When comparison metrics differ, diagnose declared modeling convention "
                "differences before attributing correctness to any solver."
            ),
        },
        "required_result_fields": REQUIRED_RESULT_FIELDS,
        "csv_columns": CSV_COLUMNS,
        "json_template": {
            "case_id": "OPERATOR_CASE_ID",
            "modeling_convention_id": "CONVENTION_ID",
            "modeling_assumption_diagnostics": {
                "status": "missing|matched|differences_found|blocked",
                "diagnostic_order": MODELING_ASSUMPTION_DIAGNOSTIC_ORDER,
                "primary_delta": None,
                "delta_codes": [],
                "notes": [],
            },
            "engine_name": "ETABS|SAP2000|MIDAS|RFEM|ABAQUS|OTHER",
            "engine_version": "ENGINE_VERSION",
            "input_checksum": "sha256:OPERATOR_INPUT_SHA256",
            "node_member_mapping_coverage": {
                "node_ratio": 0.0,
                "member_ratio": 0.0,
                "unmapped_node_count": 0,
                "unmapped_member_count": 0,
            },
            "displacement_metrics": [],
            "reaction_metrics": [],
            "member_force_metrics": [],
            "modal_metrics": [],
            "nonlinear_curve_metrics": [],
            "equilibrium_residual": {
                "norm": None,
                "normalization": "operator_declared",
            },
            "runtime": {"seconds": None},
            "peak_memory": {"megabytes": None},
            "warnings": [],
            "unsupported_features": [],
        },
        "operator_attachment_requirements": [
            "Attach raw commercial-tool export files outside bundled repo data.",
            "Record SHA256 for every operator-attached input and result file.",
            "Declare modeling convention for units, local axes, releases, offsets, mass source, damping, P-Delta, eigen solver, load combinations, and convergence tolerance.",
            "Triage result deltas through the modeling-assumption diagnostic order before recording any solver-correctness hypothesis.",
            "Keep commercial-tool outputs as comparison references, not absolute truth.",
            "Mark missing mappings, warnings, and unsupported features explicitly; silent drops are blocking.",
        ],
        "remaining_blockers": [
            "operator_files_missing",
            "license_or_customer_permission_missing",
            "operator_file_checksums_missing",
            "two_reference_solver_comparison_not_available",
            "commercial_cross_solver_execution_missing",
        ],
        "claim_boundary": (
            "This artifact authors the commercial comparison import template and mapping "
            "expectations only. It does not attach operator files, grant redistribution "
            "permission, ingest commercial outputs, compare two independent reference solvers, "
            "or close Phase 4/Phase 6."
        ),
    }


def write_phase4_commercial_comparison_import_template(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase4_commercial_comparison_import_template(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase4_commercial_comparison_import_template(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase4_commercial_comparison_import_template(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase4_commercial_comparison_import_template_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            "phase4_commercial_comparison_import_template_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase4_commercial_comparison_import_template_mismatch"
    return True, "phase4_commercial_comparison_import_template_consistent"


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
        ok, message = check_phase4_commercial_comparison_import_template(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 4 commercial comparison import template check: {message}")
        return 0 if ok else 1
    payload = write_phase4_commercial_comparison_import_template(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 4 commercial comparison import template: "
            f"{payload['status']} | fields={len(payload['required_result_fields'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
