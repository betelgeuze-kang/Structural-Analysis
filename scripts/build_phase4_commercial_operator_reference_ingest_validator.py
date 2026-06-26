#!/usr/bin/env python3
"""Build and run the Phase 4 commercial operator reference ingest validator receipt."""

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

from build_phase4_commercial_operator_reference_contract import (  # noqa: E402
    DEFAULT_OUT as OPERATOR_REFERENCE_CONTRACT_OUT,
)
from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "phase4_commercial_operator_reference_ingest_validator.json"

MODELING_CONVENTION_FIELDS = [
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_declared(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and not value.startswith("DECLARED_BY_OPERATOR")
    if isinstance(value, list):
        return bool(value)
    return True


def validate_operator_reference_package(
    package: dict[str, Any],
    *,
    package_root: Path,
    verify_file_hashes: bool = True,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    for field in ("case_id", "modeling_convention_id"):
        if not _is_declared(package.get(field)):
            blockers.append(f"missing_field:{field}")

    permission = package.get("permission_scope")
    if not isinstance(permission, dict):
        blockers.append("permission_scope_missing")
    else:
        if permission.get("comparison_use_allowed") is not True:
            blockers.append("comparison_use_permission_missing")
        if not _is_declared(permission.get("approval_receipt")):
            blockers.append("permission_approval_receipt_missing")
        if permission.get("redistribution_allowed") is True:
            warnings.append("redistribution_allowed_true_requires_separate_release_review")

    solvers = package.get("reference_solvers")
    solvers = solvers if isinstance(solvers, list) else []
    solver_names = [
        str(row.get("engine_name", "")).strip()
        for row in solvers
        if isinstance(row, dict) and str(row.get("engine_name", "")).strip()
    ]
    distinct_solver_names = sorted(set(solver_names))
    if len(distinct_solver_names) < 2:
        blockers.append("two_reference_solver_comparison_not_available")

    modeling_convention = package.get("modeling_convention")
    modeling_convention = modeling_convention if isinstance(modeling_convention, dict) else {}
    for field in MODELING_CONVENTION_FIELDS:
        if not _is_declared(modeling_convention.get(field)):
            blockers.append(f"modeling_convention_missing:{field}")

    file_checksums = package.get("file_checksums")
    file_checksums = file_checksums if isinstance(file_checksums, dict) else {}
    paths: list[str] = []
    for key in ("raw_input_files", "raw_result_files"):
        values = package.get(key)
        if isinstance(values, list):
            paths.extend(str(value) for value in values if isinstance(value, str) and value)
        else:
            blockers.append(f"{key}_missing")
    for solver in solvers:
        if isinstance(solver, dict):
            result_file = solver.get("normalized_result_file")
            if isinstance(result_file, str) and result_file:
                paths.append(result_file)
            else:
                blockers.append("normalized_result_file_missing")

    for rel_path in sorted(set(paths)):
        checksum = file_checksums.get(rel_path)
        if not (isinstance(checksum, str) and checksum.startswith("sha256:")):
            blockers.append(f"checksum_missing:{rel_path}")
            continue
        if verify_file_hashes:
            resolved = package_root / rel_path
            if not resolved.exists() or not resolved.is_file():
                blockers.append(f"operator_file_missing:{rel_path}")
                continue
            actual = _sha256(resolved)
            if actual != checksum:
                blockers.append(f"checksum_mismatch:{rel_path}")

    unsupported_features = package.get("unsupported_features")
    if not isinstance(unsupported_features, list):
        blockers.append("unsupported_features_not_declared")
    package_warnings = package.get("warnings")
    if not isinstance(package_warnings, list):
        blockers.append("warnings_not_declared")

    return {
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": warnings,
        "case_id": package.get("case_id", ""),
        "modeling_convention_id": package.get("modeling_convention_id", ""),
        "reference_solver_count": len(solvers),
        "distinct_reference_solver_count": len(distinct_solver_names),
        "distinct_reference_solvers": distinct_solver_names,
        "checked_file_count": len(sorted(set(paths))),
        "checksum_declared_count": sum(
            1 for path in sorted(set(paths)) if isinstance(file_checksums.get(path), str)
        ),
        "verify_file_hashes": verify_file_hashes,
    }


def build_phase4_commercial_operator_reference_ingest_validator(
    *,
    repo_root: Path = ROOT,
    package_path: Path | None = None,
    source_commit_sha: str | None = None,
    verify_file_hashes: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    package_path_text = package_path.as_posix() if package_path is not None else ""
    validation_result = {
        "status": "blocked",
        "contract_pass": False,
        "blockers": ["operator_reference_package_missing"],
        "warnings": [],
        "case_id": "",
        "modeling_convention_id": "",
        "reference_solver_count": 0,
        "distinct_reference_solver_count": 0,
        "distinct_reference_solvers": [],
        "checked_file_count": 0,
        "checksum_declared_count": 0,
        "verify_file_hashes": verify_file_hashes,
    }
    if package_path is not None:
        resolved_package = package_path if package_path.is_absolute() else repo_root / package_path
        if resolved_package.exists():
            package = _load_json(resolved_package)
            validation_result = validate_operator_reference_package(
                package,
                package_root=resolved_package.parent,
                verify_file_hashes=verify_file_hashes,
            )
        else:
            validation_result["blockers"] = [f"operator_reference_package_missing:{package_path_text}"]

    return {
        "schema_version": "phase4-commercial-operator-reference-ingest-validator.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
                Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
                Path("scripts/build_phase4_commercial_comparison_import_template.py"),
                Path("src/structure-viewer/viewer-commercial-tool-crosswalk-model.js"),
                Path("src/structure-viewer/viewer-report-export.js"),
            ],
            repo_root=repo_root,
        ),
        "status": validation_result["status"],
        "contract_pass": validation_result["contract_pass"],
        "phase3_closure_claim": False,
        "phase4_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "selected_benchmark_lanes": ["commercial-cross-solver"],
        "truth_class": "comparison_reference",
        "operator_reference_contract": str(OPERATOR_REFERENCE_CONTRACT_OUT),
        "package_path": package_path_text,
        "validation_result": validation_result,
        "remaining_blockers": (
            validation_result["blockers"]
            if validation_result["blockers"]
            else [
                "commercial_cross_solver_execution_missing",
                "operator_comparison_trace_rows_missing",
                "phase4_two_solver_comparison_metrics_not_recorded",
            ]
        ),
        "claim_boundary": (
            "This artifact validates the shape, permission signal, two-reference-solver "
            "presence, modeling convention declarations, and SHA256 coverage for an "
            "operator-attached commercial reference package. A passing validation is an "
            "ingest preflight only; it does not bundle operator data, grant legal approval, "
            "run comparisons, execute GUI story/member/mode trace rows for operator data, "
            "or close Phase 3, Phase 4, Phase 6, Developer Preview, or commercial readiness."
        ),
    }


def write_phase4_commercial_operator_reference_ingest_validator(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    package_path: Path | None = None,
    source_commit_sha: str | None = None,
    verify_file_hashes: bool = True,
) -> dict[str, Any]:
    payload = build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=repo_root,
        package_path=package_path,
        source_commit_sha=source_commit_sha,
        verify_file_hashes=verify_file_hashes,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def check_phase4_commercial_operator_reference_ingest_validator(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    package_path: Path | None = None,
    source_commit_sha: str | None = None,
    verify_file_hashes: bool = True,
) -> tuple[bool, str]:
    expected = build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=repo_root,
        package_path=package_path,
        source_commit_sha=source_commit_sha,
        verify_file_hashes=verify_file_hashes,
    )
    resolved = out_path if out_path.is_absolute() else repo_root / out_path
    if not resolved.exists():
        return False, f"phase4_commercial_operator_reference_ingest_validator_missing:{out_path.as_posix()}"
    try:
        existing = _load_json(resolved)
    except Exception as exc:
        return False, (
            "phase4_commercial_operator_reference_ingest_validator_unreadable:"
            f"{out_path.as_posix()}:{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "phase4_commercial_operator_reference_ingest_validator_mismatch"
    return True, "phase4_commercial_operator_reference_ingest_validator_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--package", type=Path, default=None)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--no-verify-file-hashes", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verify_file_hashes = not args.no_verify_file_hashes
    if args.check:
        ok, message = check_phase4_commercial_operator_reference_ingest_validator(
            out_path=args.out,
            package_path=args.package,
            source_commit_sha=args.source_commit_sha,
            verify_file_hashes=verify_file_hashes,
        )
        print(f"Phase 4 commercial operator reference ingest validator check: {message}")
        return 0 if ok else 1
    payload = write_phase4_commercial_operator_reference_ingest_validator(
        out_path=args.out,
        package_path=args.package,
        source_commit_sha=args.source_commit_sha,
        verify_file_hashes=verify_file_hashes,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 4 commercial operator reference ingest validator: "
            f"{payload['status']} | blockers={len(payload['remaining_blockers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
