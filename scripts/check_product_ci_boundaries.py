#!/usr/bin/env python3
"""Validate structural-core, legacy-evidence, and molecular-quarantine CI ownership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUARANTINE_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/"
    "structural_scope_quarantine_manifest.json"
)
SCHEMA_VERSION = "product-ci-boundary-report.v1"
LANES = ("core", "legacy_evidence", "molecular_quarantine")

MOLECULAR_TOKENS = (
    "gpcr",
    "pocketmd",
    "ligand",
    "docking",
    "vina",
    "gnina",
    "molecular",
    "science_actual",
    "h_bond",
    "md3bead",
    "fep",
    "free_energy",
    "all_atom",
    "casf_pdbbind",
    "pdbbind",
    "dud_e",
    "lit_pcba",
    "posebusters",
    "symmetry_rmsd",
    "symmetry_aware_ligand",
    "public_benchmark_enrichment",
    "public_benchmark_pose",
    "public_benchmark_vina_gnina",
)

CORE_PREFIXES = (
    "src/structural_analysis/",
)
CORE_EXACT_PATHS = {
    "scripts/check_git_remote_safety.py",
    "scripts/check_product_ci_boundaries.py",
    "scripts/check_repo_hygiene.py",
    "scripts/check_structural_scope_contamination.py",
    "scripts/plan_source_boundary_cleanup.py",
    "scripts/report_source_boundary_footprint.py",
    "scripts/run_product_ci_lane.py",
    "scripts/verify_quality_gate.py",
    "scripts/verify_release_artifacts_manifest.py",
    "scripts/verify_open_data_external_artifacts_manifest.py",
    "scripts/verify_structure_viewer_contracts.py",
    "tests/test_authoritative_linear_frame.py",
    "tests/test_authoritative_linear_frame_reference_cases.py",
    "tests/test_check_product_ci_boundaries.py",
    "tests/test_elastic_material_contract.py",
    "tests/test_mgt_frame_kernel_extraction.py",
    "tests/test_midas_mgt_nodal_load_contract.py",
    "tests/test_product_ci_workflow_contract.py",
    "tests/test_project_ops_api_service.py",
    "tests/test_result_validation_tolerance.py",
    "tests/test_runtime_dependency_contract.py",
    "tests/test_source_boundary_ci_contract.py",
    "tests/test_source_boundary_footprint_report.py",
    "tests/test_structure_viewer_dom_safety_contract.py",
    "tests/test_structural_analysis_core_api.py",
    "tests/test_verify_quality_gate_contract.py",
}
CORE_TEST_PREFIXES = (
    "tests/test_authoritative_linear_",
    "tests/test_structure_viewer_",
)

REQUIRED_WORKFLOW_LANES = {
    ".github/workflows/ci.yml": "core",
    ".github/workflows/legacy-evidence-ci.yml": "legacy_evidence",
    ".github/workflows/molecular-quarantine-ci.yml": "molecular_quarantine",
}


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _git_tracked_python_paths(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(
        row
        for row in completed.stdout.decode("utf-8", "replace").split("\0")
        if row
    )


def _normalized(path: str) -> str:
    return path.replace("-", "_").lower()


def looks_molecular(path: str) -> bool:
    normalized = _normalized(path)
    return any(token in normalized for token in MOLECULAR_TOKENS)


def is_core_path(path: str) -> bool:
    return (
        path in CORE_EXACT_PATHS
        or any(path.startswith(prefix) for prefix in CORE_PREFIXES)
        or any(path.startswith(prefix) for prefix in CORE_TEST_PREFIXES)
    )


def classify_path(path: str, *, quarantined_paths: set[str]) -> str:
    """Return the exactly-one CI lane that owns one tracked Python path."""

    if path in quarantined_paths or looks_molecular(path):
        return "molecular_quarantine"
    if is_core_path(path):
        return "core"
    return "legacy_evidence"


def _quarantine_paths(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("paths", [])
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("path", "")).strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("path", "")).strip()
    }


def _workflow_checks(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for workflow_path, lane in REQUIRED_WORKFLOW_LANES.items():
        path = repo_root / workflow_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        present = path.exists()
        runner_call_present = (
            f"scripts/run_product_ci_lane.py --lane {lane}" in text
        )
        hosted = "runs-on: ubuntu-latest" in text
        row = {
            "path": workflow_path,
            "lane": lane,
            "present": present,
            "runner_call_present": runner_call_present,
            "github_hosted": hosted,
            "contract_pass": bool(present and runner_call_present and hosted),
        }
        rows.append(row)
        if not present:
            blockers.append(f"workflow_missing:{workflow_path}")
        elif not runner_call_present:
            blockers.append(f"workflow_lane_runner_missing:{workflow_path}:{lane}")
        elif not hosted:
            blockers.append(f"workflow_not_github_hosted:{workflow_path}")
    return rows, blockers


def build_report(
    *,
    repo_root: Path = ROOT,
    quarantine_manifest: Path = DEFAULT_QUARANTINE_MANIFEST,
    tracked_python_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    manifest_path = _resolve(repo_root, quarantine_manifest)
    manifest = _load_json(manifest_path)
    manifest_rows = manifest.get("paths", [])
    manifest_rows = manifest_rows if isinstance(manifest_rows, list) else []
    quarantined_paths = _quarantine_paths(manifest)
    python_paths = (
        sorted(set(tracked_python_paths))
        if tracked_python_paths is not None
        else _git_tracked_python_paths(repo_root)
    )

    lane_paths = {lane: [] for lane in LANES}
    for path in python_paths:
        lane_paths[classify_path(path, quarantined_paths=quarantined_paths)].append(path)

    blockers: list[str] = []
    declared_count = manifest.get("path_count")
    if declared_count != len(manifest_rows):
        blockers.append(
            "quarantine_manifest_path_count_mismatch:"
            f"declared={declared_count}:observed={len(manifest_rows)}"
        )

    unexcluded = sorted(
        str(row.get("path", ""))
        for row in manifest_rows
        if isinstance(row, dict)
        and row.get("excluded_from_structural_release_surface") is not True
    )
    blockers.extend(f"quarantine_path_not_excluded:{path}" for path in unexcluded)

    unmanifested_molecular = sorted(
        path
        for path in python_paths
        if looks_molecular(path) and path not in quarantined_paths
    )
    blockers.extend(
        f"molecular_python_path_missing_from_quarantine_manifest:{path}"
        for path in unmanifested_molecular
    )

    core_molecular_overlap = sorted(
        path
        for path in lane_paths["core"]
        if path in quarantined_paths or looks_molecular(path)
    )
    blockers.extend(
        f"core_lane_contains_molecular_path:{path}"
        for path in core_molecular_overlap
    )

    missing_quarantined_python = sorted(
        path
        for path in quarantined_paths
        if path.endswith(".py") and path not in python_paths
    )
    blockers.extend(
        f"quarantined_python_path_not_tracked:{path}"
        for path in missing_quarantined_python
    )

    workflow_rows, workflow_blockers = _workflow_checks(repo_root)
    blockers.extend(workflow_blockers)
    blockers = sorted(dict.fromkeys(blockers))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if not blockers else "blocked",
        "contract_pass": not blockers,
        "quarantine_manifest": quarantine_manifest.as_posix(),
        "quarantine_manifest_declared_path_count": declared_count,
        "quarantine_manifest_observed_path_count": len(manifest_rows),
        "tracked_python_path_count": len(python_paths),
        "lane_counts": {lane: len(paths) for lane, paths in lane_paths.items()},
        "lane_paths": lane_paths,
        "workflow_rows": workflow_rows,
        "required_check_names": [
            "CI / verify",
            "Legacy Evidence CI / legacy-evidence",
            "Molecular Quarantine CI / molecular-quarantine",
            "Workflow Contract CI / validate",
        ],
        "unmanifested_molecular_python_paths": unmanifested_molecular,
        "core_molecular_overlap": core_molecular_overlap,
        "missing_quarantined_python_paths": missing_quarantined_python,
        "blockers": blockers,
        "claim_boundary": (
            "This report assigns every tracked Python file to exactly one CI ownership "
            "lane. Molecular-quarantine checks preserve syntax and isolation only and do "
            "not promote quarantined science code into the structural product surface."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--quarantine-manifest",
        type=Path,
        default=DEFAULT_QUARANTINE_MANIFEST,
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--print-paths", choices=LANES)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        repo_root=args.repo_root,
        quarantine_manifest=args.quarantine_manifest,
    )
    if args.print_paths:
        print("\n".join(payload["lane_paths"][args.print_paths]))
    elif args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "Product CI boundaries: "
            f"{payload['status']} | paths={payload['tracked_python_path_count']} | "
            f"lanes={payload['lane_counts']}"
        )
    if args.out:
        resolved = _resolve(args.repo_root.resolve(), args.out)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
