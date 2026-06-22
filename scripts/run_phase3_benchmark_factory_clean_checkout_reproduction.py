#!/usr/bin/env python3
"""Run Phase 3 benchmark factory seed commands in an isolated minimal checkout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_phase3_benchmark_factory_artifacts import _stable_payload_checksum  # noqa: E402
from release_evidence_metadata import git_head, input_checksums  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_BUNDLE = PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
DEFAULT_OUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
SCHEMA_VERSION = "phase3-benchmark-factory-clean-checkout-reproduction.v1"

COPY_FILES = [
    Path("package.json"),
    Path("pyproject.toml"),
    Path("pytest.ini"),
    Path("setup.cfg"),
    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl"),
    Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl"),
    Path("implementation/phase1/opensees_topology_report.json"),
    Path("implementation/phase1/release/benchmark_expansion/opensees_canonical_breadth_report.json"),
    Path("implementation/phase1/report_commercial_solver_cross_validation.py"),
    Path("implementation/phase1/release_evidence/productization/commercial_solver_cross_validation.json"),
    Path("scripts/build_phase3_benchmark_acquisition_artifacts.py"),
    Path("scripts/build_phase3_benchmark_factory_artifacts.py"),
    Path("scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
    Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
    Path("scripts/build_phase3_ifc_source_license_receipt.py"),
    Path("scripts/build_phase3_ifc_import_health_execution_receipt.py"),
    Path("scripts/build_phase3_opensees_source_license_receipt.py"),
    Path("scripts/build_phase4_commercial_comparison_import_template.py"),
    Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
    Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
    Path("scripts/phase3_benchmark_reproduction_contract.py"),
    Path("scripts/release_evidence_metadata.py"),
    Path("scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py"),
    Path("scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py"),
    Path("tests/test_build_phase3_benchmark_factory_artifacts.py"),
    Path("tests/test_build_phase3_benchmark_acquisition_artifacts.py"),
    Path("tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
    Path("tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
    Path("tests/test_build_phase3_ifc_source_license_receipt.py"),
    Path("tests/test_build_phase3_ifc_import_health_execution_receipt.py"),
    Path("tests/test_build_phase3_opensees_source_license_receipt.py"),
    Path("tests/test_build_phase4_commercial_comparison_import_template.py"),
    Path("tests/test_build_phase4_commercial_operator_reference_contract.py"),
    Path("tests/test_build_phase4_commercial_operator_reference_ingest_validator.py"),
    Path("tests/test_structural_analysis_benchmark_cli.py"),
    Path("tests/test_run_phase3_benchmark_factory_clean_checkout_reproduction.py"),
    Path("tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py"),
    Path("implementation/phase1/release_evidence/productization/phase3_buildingsmart_ifc_acquisition_receipt.json"),
    Path("implementation/phase1/release_evidence/productization/phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"),
    Path("implementation/phase1/release_evidence/productization/phase3_ifc_source_license_receipt.json"),
    Path("implementation/phase1/release_evidence/productization/phase3_ifc_import_health_execution_receipt.json"),
    Path("implementation/phase1/release_evidence/productization/phase4_commercial_comparison_import_template.json"),
    Path("implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_contract.json"),
    Path("implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_ingest_validator.json"),
]
COPY_DIRS = [Path("src/structural_analysis")]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _copy_minimal_checkout(repo_root: Path, checkout_root: Path) -> list[str]:
    copied: list[str] = []
    for raw_path in COPY_FILES:
        src = repo_root / raw_path
        dst = checkout_root / raw_path
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(raw_path.as_posix())
    for raw_path in COPY_DIRS:
        src = repo_root / raw_path
        dst = checkout_root / raw_path
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        copied.append(raw_path.as_posix())
    return sorted(copied)


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{cwd / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = round(time.monotonic() - started, 3)
    return {
        "command": " ".join(command),
        "return_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "stdout_excerpt": completed.stdout[-4000:],
        "stderr_excerpt": completed.stderr[-4000:],
    }


def build_phase3_clean_checkout_reproduction(
    *,
    repo_root: Path = ROOT,
    bundle_path: Path = DEFAULT_BUNDLE,
    source_commit_sha: str | None = None,
    keep_checkout: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source_commit = source_commit_sha if source_commit_sha is not None else git_head(repo_root)
    resolved_bundle = bundle_path if bundle_path.is_absolute() else repo_root / bundle_path
    expected_bundle = _load_json(resolved_bundle)
    checkout_root = Path(tempfile.mkdtemp(prefix="phase3-benchmark-clean-checkout-", dir="/tmp"))
    copied_inputs: list[str] = []
    command_results: list[dict[str, Any]] = []
    generated_artifact_checksums: dict[str, str] = {}
    blockers: list[str] = []
    retained_checkout_path = ""
    try:
        copied_inputs = _copy_minimal_checkout(repo_root, checkout_root)
        commands = [
            [
                "python3",
                "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_ifc_source_license_receipt.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_ifc_source_license_receipt.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_ifc_import_health_execution_receipt.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_ifc_import_health_execution_receipt.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_opensees_source_license_receipt.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_opensees_source_license_receipt.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase4_commercial_comparison_import_template.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase4_commercial_comparison_import_template.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase4_commercial_operator_reference_contract.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase4_commercial_operator_reference_contract.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_benchmark_factory_artifacts.py",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "scripts/build_phase3_benchmark_factory_artifacts.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
            [
                "python3",
                "-m",
                "structural_analysis.benchmark.cli",
                "--manifest-out",
                "/tmp/phase3_seed_manifest.json",
                "--scorecard-out",
                "/tmp/phase3_seed_scorecard.json",
                "--summary-out",
                "/tmp/phase3_seed_runner_summary.json",
                "--fail-blocked",
            ],
            [
                "python3",
                "-m",
                "pytest",
                "-q",
                "tests/test_build_phase3_benchmark_factory_artifacts.py",
                "tests/test_structural_analysis_benchmark_cli.py",
            ],
            [
                "python3",
                "-m",
                "ruff",
                "check",
                "src/structural_analysis/benchmark/acquisition.py",
                "src/structural_analysis/benchmark/cli.py",
                "src/structural_analysis/benchmark/factory.py",
                "scripts/build_phase3_benchmark_acquisition_artifacts.py",
                "scripts/build_phase3_benchmark_factory_artifacts.py",
                "scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                "scripts/build_phase3_ifc_source_license_receipt.py",
                "scripts/build_phase3_ifc_import_health_execution_receipt.py",
                "scripts/build_phase3_opensees_source_license_receipt.py",
                "scripts/build_phase4_commercial_comparison_import_template.py",
                "scripts/build_phase4_commercial_operator_reference_contract.py",
                "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
                "scripts/phase3_benchmark_reproduction_contract.py",
                "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
                "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
                "tests/test_build_phase3_benchmark_acquisition_artifacts.py",
                "tests/test_build_phase3_benchmark_factory_artifacts.py",
                "tests/test_build_phase3_buildingsmart_ifc_acquisition_receipt.py",
                "tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
                "tests/test_build_phase3_ifc_source_license_receipt.py",
                "tests/test_build_phase3_ifc_import_health_execution_receipt.py",
                "tests/test_build_phase3_opensees_source_license_receipt.py",
                "tests/test_build_phase4_commercial_comparison_import_template.py",
                "tests/test_build_phase4_commercial_operator_reference_contract.py",
                "tests/test_build_phase4_commercial_operator_reference_ingest_validator.py",
                "tests/test_structural_analysis_benchmark_cli.py",
                "tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
            ],
            [
                "python3",
                "scripts/build_phase3_benchmark_factory_artifacts.py",
                "--check",
                "--source-commit-sha",
                source_commit,
            ],
        ]
        for command in commands:
            result = _run_command(command, cwd=checkout_root)
            command_results.append(result)
            if result["return_code"] != 0:
                blockers.append(f"command_failed:{result['command']}")
                break

        artifact_paths = {
            "manifest": checkout_root / PRODUCTIZATION / "phase3_benchmark_factory_seed_manifest.json",
            "acquisition_plan": checkout_root / PRODUCTIZATION / "phase3_benchmark_acquisition_plan.json",
            "buildingsmart_ifc_acquisition_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_buildingsmart_ifc_acquisition_receipt.json"
            ),
            "buildingsmart_dirty_ifc_acquisition_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
            ),
            "ifc_source_license_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_ifc_source_license_receipt.json"
            ),
            "ifc_import_health_execution_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_ifc_import_health_execution_receipt.json"
            ),
            "opensees_source_license_receipt": (
                checkout_root / PRODUCTIZATION / "phase3_opensees_medium_source_license_receipt.json"
            ),
            "commercial_comparison_import_template": (
                checkout_root / PRODUCTIZATION / "phase4_commercial_comparison_import_template.json"
            ),
            "commercial_operator_reference_contract": (
                checkout_root / PRODUCTIZATION / "phase4_commercial_operator_reference_contract.json"
            ),
            "commercial_operator_reference_ingest_validator": (
                checkout_root / PRODUCTIZATION / "phase4_commercial_operator_reference_ingest_validator.json"
            ),
            "scorecard": checkout_root / PRODUCTIZATION / "phase3_benchmark_factory_seed_scorecard.json",
            "summary": checkout_root / PRODUCTIZATION / "phase3_benchmark_factory_seed_summary.json",
        }
        for key, path in artifact_paths.items():
            if not path.exists():
                blockers.append(f"generated_artifact_missing:{key}")
                continue
            generated_artifact_checksums[key] = _stable_payload_checksum(_load_json(path))

        expected_checksums = expected_bundle.get("stable_artifact_checksums")
        expected_checksums = expected_checksums if isinstance(expected_checksums, dict) else {}
        checksum_match = bool(generated_artifact_checksums) and generated_artifact_checksums == expected_checksums
        if not checksum_match:
            blockers.append("stable_artifact_checksum_mismatch")
    finally:
        if keep_checkout:
            retained_checkout_path = str(checkout_root)
        else:
            shutil.rmtree(checkout_root, ignore_errors=True)

    command_pass = all(row["return_code"] == 0 for row in command_results) and len(command_results) == 22
    contract_pass = bool(command_pass and not blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit,
        "status": "pass" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "clean_checkout_executed": True,
        "clean_checkout_execution_mode": "isolated_minimal_worktree_copy",
        "isolated_checkout_retained": keep_checkout,
        "isolated_checkout_path": retained_checkout_path,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "copied_inputs": copied_inputs,
        "input_checksums": input_checksums(COPY_FILES + COPY_DIRS + [bundle_path], repo_root=repo_root),
        "bundle_path": str(bundle_path),
        "expected_stable_artifact_checksums": expected_bundle.get("stable_artifact_checksums", {}),
        "generated_stable_artifact_checksums": generated_artifact_checksums,
        "stable_artifact_checksums_match": generated_artifact_checksums
        == expected_bundle.get("stable_artifact_checksums", {}),
        "command_results": command_results,
        "blockers": blockers,
        "claim_boundary": (
            "This receipt proves one local isolated minimal worktree-copy replay of the generated "
            "analytic-small and element-patch Phase 3 seed benchmark commands. It is not a full git "
            "clean clone, not Linux/Windows parity, not Developer Preview Release Candidate closure, "
            "and not full Phase 3 corpus closure."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--keep-checkout", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_phase3_clean_checkout_reproduction(
        repo_root=ROOT,
        bundle_path=args.bundle,
        source_commit_sha=args.source_commit_sha,
        keep_checkout=args.keep_checkout,
    )
    if not args.check:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json_text(payload), encoding="utf-8")
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "Phase 3 clean checkout reproduction: "
            f"{payload['status']} | executed={payload['clean_checkout_executed']} | "
            f"checksum_match={payload['stable_artifact_checksums_match']}"
        )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
