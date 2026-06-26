#!/usr/bin/env python3
"""Build the Phase 4 commercial operator reference output contract receipt."""

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
DEFAULT_OUT = PRODUCTIZATION / "phase4_commercial_operator_reference_contract.json"

REQUIRED_PACKAGE_FIELDS = [
    "case_id",
    "modeling_convention_id",
    "modeling_assumption_diagnostic_order",
    "operator_name",
    "operator_contact_or_internal_ticket",
    "permission_scope",
    "reference_solvers",
    "raw_input_files",
    "raw_result_files",
    "normalized_result_file",
    "file_checksums",
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
    "unsupported_features",
    "warnings",
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

VALIDATION_RULES = [
    {
        "rule_id": "two_independent_reference_solvers_required",
        "severity": "blocking",
        "description": "Phase 4 closure needs at least two independent commercial/reference solver outputs for the same model.",
    },
    {
        "rule_id": "operator_permission_must_be_attached",
        "severity": "blocking",
        "description": "Operator or customer permission must explicitly allow local comparison use before any output is ingested.",
    },
    {
        "rule_id": "all_raw_files_need_sha256",
        "severity": "blocking",
        "description": "Every raw input, raw result, and normalized result file must carry a SHA256 checksum.",
    },
    {
        "rule_id": "modeling_convention_must_be_declared",
        "severity": "blocking",
        "description": "Units, local axes, offsets, releases, mass, damping, P-Delta, eigensolver, load combinations, and convergence tolerance must be declared.",
    },
    {
        "rule_id": "modeling_assumption_first_diagnosis_required",
        "severity": "blocking",
        "description": "Comparison deltas must be triaged against the declared modeling-assumption order before any solver-correctness hypothesis is recorded.",
    },
    {
        "rule_id": "unsupported_features_are_explicit",
        "severity": "blocking",
        "description": "Unsupported features and warnings must be listed explicitly; silent drops block comparison credit.",
    },
    {
        "rule_id": "commercial_outputs_are_not_absolute_truth",
        "severity": "claim_boundary",
        "description": "Commercial outputs are comparison references used to diagnose modeling assumptions, not proof that either solver is correct.",
    },
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


def build_phase4_commercial_operator_reference_contract(
    *,
    repo_root: Path = ROOT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    return {
        "schema_version": "phase4-commercial-operator-reference-contract.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
                Path("scripts/build_phase4_commercial_comparison_import_template.py"),
                Path("src/structure-viewer/viewer-commercial-tool-crosswalk-model.js"),
                Path("src/structure-viewer/viewer-report-export.js"),
                Path("tests/test_structure_viewer_commercial_tool_crosswalk_model_contract.py"),
                Path("tests/test_structure_viewer_explainability_report_contract.py"),
                Path("implementation/phase1/release_evidence/productization/commercial_solver_cross_validation.json"),
                Path("implementation/phase1/report_commercial_solver_cross_validation.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "blocked",
        "contract_pass": False,
        "phase3_closure_claim": False,
        "phase4_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "selected_benchmark_lanes": ["commercial-cross-solver"],
        "truth_class": "comparison_reference",
        "import_template": (
            "implementation/phase1/release_evidence/productization/"
            "phase4_commercial_comparison_import_template.json"
        ),
        "comparison_diagnostic_policy": {
            "policy_id": "modeling_assumption_first",
            "commercial_outputs_are_absolute_truth": False,
            "solver_correctness_claim_allowed": False,
            "diagnostic_order": MODELING_ASSUMPTION_DIAGNOSTIC_ORDER,
            "required_trace": (
                "Every material comparison delta must cite checked modeling assumptions "
                "before it can be escalated as a solver-behavior hypothesis."
            ),
        },
        "gui_traceability_contract": {
            "status": "ready",
            "contract_pass": True,
            "schema_version": "structure-viewer-commercial-tool-crosswalk.v1",
            "viewer_model": "src/structure-viewer/viewer-commercial-tool-crosswalk-model.js",
            "report_export": "src/structure-viewer/viewer-report-export.js",
            "focused_tests": [
                "tests/test_structure_viewer_commercial_tool_crosswalk_model_contract.py",
                "tests/test_structure_viewer_explainability_report_contract.py",
            ],
            "required_trace_dimensions": ["member", "story", "mode"],
            "missing_trace_dimensions_are_blocking": True,
            "operator_trace_rows_available": False,
        },
        "required_reference_solver_count": 2,
        "current_reference_solver_count": 0,
        "required_package_fields": REQUIRED_PACKAGE_FIELDS,
        "operator_reference_package_template": {
            "case_id": "OPERATOR_CASE_ID",
            "modeling_convention_id": "CONVENTION_ID",
            "permission_scope": {
                "comparison_use_allowed": False,
                "redistribution_allowed": False,
                "approval_receipt": "OPERATOR_PERMISSION_RECEIPT_PATH",
            },
            "reference_solvers": [
                {
                    "engine_name": "REFERENCE_SOLVER_A",
                    "engine_version": "ENGINE_VERSION",
                    "normalized_result_file": "operator_refs/CASE/solver_a.normalized.json",
                },
                {
                    "engine_name": "REFERENCE_SOLVER_B",
                    "engine_version": "ENGINE_VERSION",
                    "normalized_result_file": "operator_refs/CASE/solver_b.normalized.json",
                },
            ],
            "raw_input_files": [],
            "raw_result_files": [],
            "file_checksums": {},
            "modeling_assumption_diagnostic_order": MODELING_ASSUMPTION_DIAGNOSTIC_ORDER,
            "modeling_convention": {
                "unit_system": "DECLARED_BY_OPERATOR",
                "local_axis_convention": "DECLARED_BY_OPERATOR",
                "rigid_offset_policy": "DECLARED_BY_OPERATOR",
                "end_release_policy": "DECLARED_BY_OPERATOR",
                "diaphragm_policy": "DECLARED_BY_OPERATOR",
                "mass_source_policy": "DECLARED_BY_OPERATOR",
                "self_weight_policy": "DECLARED_BY_OPERATOR",
                "material_modulus_convention": "DECLARED_BY_OPERATOR",
                "shell_formulation": "DECLARED_BY_OPERATOR",
                "mesh_density": "DECLARED_BY_OPERATOR",
                "damping_policy": "DECLARED_BY_OPERATOR",
                "p_delta_policy": "DECLARED_BY_OPERATOR",
                "eigen_solver": "DECLARED_BY_OPERATOR",
                "load_combinations": [],
                "convergence_tolerance": "DECLARED_BY_OPERATOR",
            },
            "unsupported_features": [],
            "warnings": [],
        },
        "validation_rules": VALIDATION_RULES,
        "remaining_blockers": [
            "operator_reference_package_missing",
            "operator_files_missing",
            "license_or_customer_permission_missing",
            "operator_file_checksums_missing",
            "two_reference_solver_comparison_not_available",
            "commercial_cross_solver_execution_missing",
            "operator_comparison_trace_rows_missing",
        ],
        "claim_boundary": (
            "This artifact defines the operator-attached commercial reference output "
            "package contract only. It does not include operator files, grant permission, "
            "record SHA256 checksums for real operator data, ingest commercial results, "
            "execute modeling-assumption diagnostics, compare two independent reference "
            "solvers, execute GUI story/member/mode trace rows for operator data, or close Phase 3, "
            "Phase 4, Phase 6, Developer Preview, or commercial readiness."
        ),
    }


def write_phase4_commercial_operator_reference_contract(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    payload = build_phase4_commercial_operator_reference_contract(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase4_commercial_operator_reference_contract(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase4_commercial_operator_reference_contract(
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase4_commercial_operator_reference_contract_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            "phase4_commercial_operator_reference_contract_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase4_commercial_operator_reference_contract_mismatch"
    return True, "phase4_commercial_operator_reference_contract_consistent"


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
        ok, message = check_phase4_commercial_operator_reference_contract(
            out_path=args.out,
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 4 commercial operator reference contract check: {message}")
        return 0 if ok else 1
    payload = write_phase4_commercial_operator_reference_contract(
        out_path=args.out,
        source_commit_sha=args.source_commit_sha,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 4 commercial operator reference contract: "
            f"{payload['status']} | blockers={len(payload['remaining_blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
