#!/usr/bin/env python3
"""Build Phase 3 benchmark factory seed artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from build_phase3_benchmark_acquisition_artifacts import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_ACQUISITION_PLAN_OUT,
    build_phase3_benchmark_acquisition_artifact,
)
from build_phase3_buildingsmart_ifc_acquisition_receipt import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_BUILDINGSMART_IFC_ACQUISITION_OUT,
    build_phase3_buildingsmart_ifc_acquisition_receipt,
)
from build_phase3_buildingsmart_dirty_ifc_acquisition_receipt import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_BUILDINGSMART_DIRTY_IFC_ACQUISITION_OUT,
    build_phase3_buildingsmart_dirty_ifc_acquisition_receipt,
)
from build_phase3_opensees_source_license_receipt import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_OPENSEES_SOURCE_LICENSE_OUT,
    build_phase3_opensees_source_license_receipt,
)
from build_phase4_commercial_comparison_import_template import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_COMMERCIAL_COMPARISON_TEMPLATE_OUT,
    build_phase4_commercial_comparison_import_template,
)
from build_phase4_analytic_physical_fallback_scorecard import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_PHASE4_ANALYTIC_PHYSICAL_FALLBACK_OUT,
    build_phase4_analytic_physical_fallback_scorecard,
)
from build_phase4_commercial_operator_reference_contract import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_CONTRACT_OUT,
    build_phase4_commercial_operator_reference_contract,
)
from build_phase4_commercial_operator_reference_ingest_validator import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_INGEST_VALIDATOR_OUT,
    build_phase4_commercial_operator_reference_ingest_validator,
)
from build_phase3_ifc_source_license_receipt import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_IFC_SOURCE_LICENSE_OUT,
    build_phase3_ifc_source_license_receipt,
)
from build_phase3_ifc_import_health_execution_receipt import (  # noqa: E402
    DEFAULT_OUT as DEFAULT_IFC_IMPORT_HEALTH_EXECUTION_OUT,
    build_phase3_ifc_import_health_execution_receipt,
)
from phase3_benchmark_reproduction_contract import (  # noqa: E402
    GIT_CLEAN_CLONE_REQUIRED_INPUTS,
    path_strings,
)
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.benchmark.factory import (  # noqa: E402
    build_manifest,
    cases_to_jsonable,
    generated_benchmark_factory_cases,
    run_benchmark_cases,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MANIFEST_OUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_manifest.json"
DEFAULT_SCORECARD_OUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_scorecard.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_summary.json"
DEFAULT_REPRODUCIBILITY_BUNDLE_OUT = PRODUCTIZATION / "phase3_benchmark_factory_seed_reproducibility_bundle.json"
DEFAULT_CLEAN_CHECKOUT_REPRODUCTION_OUT = (
    PRODUCTIZATION / "phase3_benchmark_factory_seed_clean_checkout_reproduction.json"
)
DEFAULT_GIT_CLEAN_CLONE_REPRODUCTION_OUT = (
    PRODUCTIZATION / "phase3_benchmark_factory_seed_git_clean_clone_reproduction.json"
)
SCHEMA_VERSION = "phase3-benchmark-factory-seed-artifacts.v1"
SEED_ANALYTIC_COMPONENT_LANES = (
    "analytic-small",
    "element-patch",
    "nonlinear-material-mesh",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


STABLE_CHECKSUM_EXCLUDED_KEYS = {
    "blockers",
    "elapsed_seconds",
    "execution",
    "execution_attempted_count",
    "generated_at",
    "import_health_contract_pass",
    "import_health_contract_pass_count",
    "import_health_executed",
    "input_checksums",
    "quantity_credit_ready",
    "quantity_credit_ready_count",
    "silent_import_loss_gate",
    "silent_import_loss_pass_count",
    "source_checksum_attached_count",
    "source_checksum_status",
    "source_commit_sha",
    "source_file_acquired",
    "source_file_acquired_count",
    "source_file_is_git_lfs_pointer",
    "source_sha256",
    "stderr_excerpt",
    "stdout_excerpt",
}


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in STABLE_CHECKSUM_EXCLUDED_KEYS
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _stable_payload_checksum(payload: dict[str, Any]) -> str:
    text = json.dumps(_strip_volatile(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _run_package_benchmark_cli(repo_root: Path) -> dict[str, dict[str, Any]]:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        manifest_path = tmp_path / "manifest.json"
        scorecard_path = tmp_path / "scorecard.json"
        summary_path = tmp_path / "summary.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(SRC_ROOT)
            if not env.get("PYTHONPATH")
            else f"{SRC_ROOT}{os.pathsep}{env['PYTHONPATH']}"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "structural_analysis.benchmark.cli",
                "--manifest-out",
                str(manifest_path),
                "--scorecard-out",
                str(scorecard_path),
                "--summary-out",
                str(summary_path),
                "--fail-blocked",
            ],
            cwd=repo_root,
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            return {
                "summary": {
                    "status": "blocked",
                    "contract_pass": False,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.strip(),
                },
                "manifest": {},
                "scorecard": {},
            }
        return {
            "manifest": _read_json(manifest_path),
            "scorecard": _read_json(scorecard_path),
            "summary": _read_json(summary_path),
        }


def build_phase3_benchmark_factory_artifacts(
    *,
    repo_root: Path = ROOT,
    manifest_out: Path = DEFAULT_MANIFEST_OUT,
    scorecard_out: Path = DEFAULT_SCORECARD_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    reproducibility_bundle_out: Path = DEFAULT_REPRODUCIBILITY_BUNDLE_OUT,
    clean_checkout_reproduction_out: Path = DEFAULT_CLEAN_CHECKOUT_REPRODUCTION_OUT,
    git_clean_clone_reproduction_out: Path = DEFAULT_GIT_CLEAN_CLONE_REPRODUCTION_OUT,
    acquisition_plan_out: Path = DEFAULT_ACQUISITION_PLAN_OUT,
    buildingsmart_ifc_acquisition_out: Path = DEFAULT_BUILDINGSMART_IFC_ACQUISITION_OUT,
    buildingsmart_dirty_ifc_acquisition_out: Path = DEFAULT_BUILDINGSMART_DIRTY_IFC_ACQUISITION_OUT,
    ifc_source_license_out: Path = DEFAULT_IFC_SOURCE_LICENSE_OUT,
    ifc_import_health_execution_out: Path = DEFAULT_IFC_IMPORT_HEALTH_EXECUTION_OUT,
    opensees_source_license_out: Path = DEFAULT_OPENSEES_SOURCE_LICENSE_OUT,
    commercial_comparison_template_out: Path = DEFAULT_COMMERCIAL_COMPARISON_TEMPLATE_OUT,
    phase4_analytic_physical_fallback_out: Path = DEFAULT_PHASE4_ANALYTIC_PHYSICAL_FALLBACK_OUT,
    commercial_operator_reference_contract_out: Path = DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_CONTRACT_OUT,
    commercial_operator_reference_ingest_validator_out: Path = (
        DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_INGEST_VALIDATOR_OUT
    ),
    source_commit_sha: str | None = None,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    resolved_source_commit_sha = source_commit_sha if source_commit_sha is not None else git_head(repo_root)
    cases = generated_benchmark_factory_cases()
    manifest = build_manifest(cases)
    scorecard = run_benchmark_cases(cases)
    package_cli = _run_package_benchmark_cli(repo_root)
    opensees_source_license_receipt = build_phase3_opensees_source_license_receipt(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    commercial_comparison_template = build_phase4_commercial_comparison_import_template(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    phase4_analytic_physical_fallback = build_phase4_analytic_physical_fallback_scorecard(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    commercial_operator_reference_contract = build_phase4_commercial_operator_reference_contract(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    commercial_operator_reference_ingest_validator = (
        build_phase4_commercial_operator_reference_ingest_validator(
            repo_root=repo_root,
            source_commit_sha=resolved_source_commit_sha,
        )
    )
    ifc_source_license_receipt = build_phase3_ifc_source_license_receipt(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    buildingsmart_ifc_acquisition_receipt = build_phase3_buildingsmart_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    buildingsmart_dirty_ifc_acquisition_receipt = build_phase3_buildingsmart_dirty_ifc_acquisition_receipt(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    ifc_import_health_execution_receipt = build_phase3_ifc_import_health_execution_receipt(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    acquisition_plan = build_phase3_benchmark_acquisition_artifact(
        repo_root=repo_root,
        source_commit_sha=resolved_source_commit_sha,
    )
    lane_case_counts = {
        lane: sum(1 for row in manifest["rows"] if row["lane"] == lane)
        for lane in manifest["lanes"]
    }
    all_cases_have_license = all(
        row["license"]["redistribution_allowed"] is True
        and row["license"]["commercial_use_allowed"] is True
        and row["checksum"].startswith("sha256:")
        and row["truth_class"] == "analytic_truth"
        and row["expected_outputs"]
        for row in manifest["rows"]
    )
    contract_pass = (
        scorecard["contract_pass"]
        and scorecard["expected_output_contract_pass"]
        and package_cli["manifest"] == manifest
        and package_cli["scorecard"] == scorecard
        and package_cli["summary"].get("contract_pass") is True
        and phase4_analytic_physical_fallback["contract_pass"] is True
        and all_cases_have_license
        and manifest["case_count"] == scorecard["case_count"]
        and "analytic-small" in manifest["lanes"]
        and "element-patch" in manifest["lanes"]
    )
    analytic_component_case_count = sum(
        lane_case_counts.get(lane, 0) for lane in SEED_ANALYTIC_COMPONENT_LANES
    )
    analytic_component_quantity_gate_met = analytic_component_case_count >= 20
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": resolved_source_commit_sha,
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/benchmark/__init__.py"),
                Path("src/structural_analysis/benchmark/cli.py"),
                Path("src/structural_analysis/benchmark/factory.py"),
                Path("src/structural_analysis/api/core.py"),
                Path("src/structural_analysis/solvers/linear/static.py"),
                Path("pyproject.toml"),
                Path("setup.cfg"),
                Path("tests/test_structural_analysis_benchmark_cli.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "phase3_closure_claim": False,
        "lane_count": manifest["lane_count"],
        "case_count": manifest["case_count"],
        "pass_count": scorecard["pass_count"],
        "lanes": manifest["lanes"],
        "lane_case_counts": lane_case_counts,
        "scorecard_expected_output_comparison_count": scorecard[
            "expected_output_comparison_count"
        ],
        "scorecard_expected_output_comparison_pass_count": scorecard[
            "expected_output_comparison_pass_count"
        ],
        "scorecard_expected_output_contract_pass": scorecard[
            "expected_output_contract_pass"
        ],
        "all_cases_have_license_checksum_truth_and_expected_outputs": all_cases_have_license,
        "scorecard_reproducible_from_manifest": manifest["case_count"] == scorecard["case_count"],
        "analytic_component_quantity_gate_met": analytic_component_quantity_gate_met,
        "package_benchmark_runner": {
            "status": "ready" if package_cli["summary"].get("contract_pass") else "blocked",
            "contract_pass": bool(package_cli["summary"].get("contract_pass")),
            "entry_point": "structural-analysis-benchmark = structural_analysis.benchmark.cli:main",
            "module_command": "python -m structural_analysis.benchmark.cli",
            "invocation_surfaces": ["python_api_factory", "package_cli"],
            "scope": (
                "generated analytic-small, element-patch, and nonlinear material-mesh "
                "seed only"
            ),
            "same_manifest_as_python_factory": package_cli["manifest"] == manifest,
            "same_scorecard_as_python_factory": package_cli["scorecard"] == scorecard,
            "expected_output_contract_pass": bool(
                package_cli["scorecard"].get("expected_output_contract_pass") is True
            ),
            "expected_output_comparison_count": package_cli["scorecard"].get(
                "expected_output_comparison_count",
                0,
            ),
            "expected_output_comparison_pass_count": package_cli["scorecard"].get(
                "expected_output_comparison_pass_count",
                0,
            ),
            "factory_manifest_checksum": _stable_payload_checksum(manifest),
            "package_cli_manifest_checksum": _stable_payload_checksum(package_cli["manifest"]),
            "factory_scorecard_checksum": _stable_payload_checksum(scorecard),
            "package_cli_scorecard_checksum": _stable_payload_checksum(package_cli["scorecard"]),
            "phase3_closure_claim": False,
            "developer_preview_release_candidate_claim": False,
        },
        "full_phase3_quantity_gates_met": False,
        "remaining_quantity_targets": {
            "analytic_component_cases_required": 20,
            "analytic_component_cases_current": analytic_component_case_count,
            "medium_structural_models_required": 5,
            "medium_structural_models_current": 0,
            "large_structural_models_required": 2,
            "large_structural_models_current": 0,
            "ifc_clean_dirty_import_cases_required": 10,
            "ifc_clean_dirty_import_cases_current": 0,
        },
        "remaining_corpus_lanes": [
            {
                "lane": "element-patch",
                "status": "seed_ready",
                "case_count": lane_case_counts.get("element-patch", 0),
            },
            {"lane": "opensees-medium", "status": "not_started"},
            {"lane": "opensees-megatall", "status": "not_started"},
            {"lane": "buildingsmart-clean-ifc", "status": "not_started"},
            {"lane": "buildingsmart-dirty-ifc", "status": "not_started"},
            {"lane": "ifc-query-and-gui", "status": "not_started"},
            {"lane": "commercial-cross-solver", "status": "not_started"},
            {"lane": "large-model-performance", "status": "not_started"},
        ],
        "artifacts": {
            "manifest": str(manifest_out),
            "scorecard": str(scorecard_out),
            "summary": str(summary_out),
            "reproducibility_bundle": str(reproducibility_bundle_out),
            "clean_checkout_reproduction": str(clean_checkout_reproduction_out),
            "git_clean_clone_reproduction": str(git_clean_clone_reproduction_out),
            "acquisition_plan": str(acquisition_plan_out),
            "buildingsmart_ifc_acquisition_receipt": str(buildingsmart_ifc_acquisition_out),
            "buildingsmart_dirty_ifc_acquisition_receipt": str(buildingsmart_dirty_ifc_acquisition_out),
            "ifc_source_license_receipt": str(ifc_source_license_out),
            "ifc_import_health_execution_receipt": str(ifc_import_health_execution_out),
            "opensees_source_license_receipt": str(opensees_source_license_out),
            "commercial_comparison_import_template": str(commercial_comparison_template_out),
            "commercial_operator_reference_contract": str(commercial_operator_reference_contract_out),
            "phase4_analytic_physical_fallback_scorecard": str(
                phase4_analytic_physical_fallback_out
            ),
            "commercial_operator_reference_ingest_validator": str(
                commercial_operator_reference_ingest_validator_out
            ),
        },
        "claim_boundary": (
            "This is a generated analytic-small benchmark factory seed. "
            "It proves manifest + checksum/license/truth/expected-output metadata "
            "and a deterministic scorecard run for generated axial, axis-aligned "
            "element patch, and narrow nonlinear material-mesh axial-chain cases only. "
            "The analytic/component quantity gate is satisfied only inside these "
            "repo-generated seed families; it does not close OpenSees, buildingSMART "
            "IFC, commercial-cross-solver, large-model, full nonlinear full-mesh, or "
            "G1 solver-core gates."
        ),
    }
    reproducibility_bundle = {
        "schema_version": "phase3-benchmark-factory-seed-reproducibility-bundle.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": resolved_source_commit_sha,
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "clean_checkout_reproducibility_claim": "command_replay_contract_only",
        "clean_checkout_executed": False,
        "git_clean_clone_reproducibility_claim": "local_file_protocol_clone_when_preflight_passes",
        "git_clean_clone_executed": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "regeneration_commands": [
            "python3 scripts/build_phase3_benchmark_factory_artifacts.py",
            "python3 scripts/build_phase3_benchmark_acquisition_artifacts.py",
            "python3 scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
            "python3 scripts/build_phase3_ifc_import_health_execution_receipt.py",
            "python3 scripts/build_phase3_opensees_source_license_receipt.py",
            "python3 scripts/build_phase4_commercial_comparison_import_template.py",
            "python3 scripts/build_phase4_analytic_physical_fallback_scorecard.py",
            "python3 scripts/build_phase4_commercial_operator_reference_contract.py",
            "python3 scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
            "python3 scripts/build_phase3_benchmark_factory_artifacts.py --check",
            "python3 scripts/build_phase3_benchmark_acquisition_artifacts.py --check",
            "python3 scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py --check",
            "python3 scripts/build_phase3_ifc_import_health_execution_receipt.py --check",
            "python3 scripts/build_phase3_opensees_source_license_receipt.py --check",
            "python3 scripts/build_phase4_commercial_comparison_import_template.py --check",
            "python3 scripts/build_phase4_analytic_physical_fallback_scorecard.py --check",
            "python3 scripts/build_phase4_commercial_operator_reference_contract.py --check",
            "python3 scripts/build_phase4_commercial_operator_reference_ingest_validator.py --check",
            (
                "python3 -m structural_analysis.benchmark.cli "
                "--manifest-out /tmp/phase3_seed_manifest.json "
                "--scorecard-out /tmp/phase3_seed_scorecard.json "
                "--summary-out /tmp/phase3_seed_runner_summary.json "
                "--fail-blocked"
            ),
            "python3 scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
            "python3 scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
            (
                "python3 -m pytest -q "
                "tests/test_build_phase3_benchmark_factory_artifacts.py "
                "tests/test_structural_analysis_benchmark_cli.py"
            ),
            (
                "python3 -m ruff check "
                "src/structural_analysis/benchmark/cli.py "
                "src/structural_analysis/benchmark/factory.py "
                "src/structural_analysis/benchmark/acquisition.py "
                "scripts/build_phase3_benchmark_acquisition_artifacts.py "
                "scripts/build_phase3_opensees_source_license_receipt.py "
                "scripts/build_phase4_commercial_comparison_import_template.py "
                "scripts/build_phase3_ifc_query_gui_readiness_receipt.py "
                "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py "
                "scripts/build_phase3_large_model_runner_readiness_receipt.py "
                "scripts/build_phase4_commercial_cross_solver_readiness_receipt.py "
                "scripts/build_phase4_analytic_physical_fallback_scorecard.py "
                "scripts/build_phase4_commercial_operator_reference_contract.py "
                "scripts/build_phase4_commercial_operator_reference_ingest_validator.py "
                "scripts/build_phase3_benchmark_factory_artifacts.py "
                "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py "
                "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py "
                "tests/test_build_phase3_benchmark_factory_artifacts.py "
                "tests/test_structural_analysis_benchmark_cli.py "
                "tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py"
            ),
        ],
        "required_git_clean_clone_inputs": path_strings(GIT_CLEAN_CLONE_REQUIRED_INPUTS),
        "required_clean_checkout_inputs": [
            "src/structural_analysis/benchmark/factory.py",
            "src/structural_analysis/benchmark/cli.py",
            "src/structural_analysis/benchmark/__init__.py",
            "src/structural_analysis/api/core.py",
            "src/structural_analysis/solvers/linear/static.py",
            "scripts/build_phase3_benchmark_factory_artifacts.py",
            "scripts/build_phase3_benchmark_acquisition_artifacts.py",
            "scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
            "scripts/build_phase3_ifc_query_gui_readiness_receipt.py",
            "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py",
            "scripts/build_phase3_large_model_runner_readiness_receipt.py",
            "scripts/build_phase3_opensees_source_license_receipt.py",
            "scripts/build_phase4_commercial_comparison_import_template.py",
            "scripts/build_phase4_commercial_cross_solver_readiness_receipt.py",
            "scripts/build_phase4_analytic_physical_fallback_scorecard.py",
            "scripts/build_phase4_commercial_operator_reference_contract.py",
            "scripts/build_phase4_commercial_operator_reference_ingest_validator.py",
            "scripts/run_phase3_benchmark_factory_clean_checkout_reproduction.py",
            "scripts/run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
            "tests/test_build_phase3_benchmark_factory_artifacts.py",
            "tests/test_structural_analysis_benchmark_cli.py",
            "tests/test_build_phase3_benchmark_acquisition_artifacts.py",
            "tests/test_build_phase4_commercial_comparison_import_template.py",
            "tests/test_build_phase4_analytic_physical_fallback_scorecard.py",
            "tests/test_build_phase4_commercial_operator_reference_contract.py",
            "tests/test_build_phase4_commercial_operator_reference_ingest_validator.py",
            "tests/test_build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py",
            "tests/test_run_phase3_benchmark_factory_git_clean_clone_reproduction.py",
            "pyproject.toml",
            "setup.cfg",
        ],
        "input_checksums": input_checksums(
            [
                path
                for path in GIT_CLEAN_CLONE_REQUIRED_INPUTS
                if not path.as_posix().startswith(f"{PRODUCTIZATION.as_posix()}/")
            ],
            repo_root=repo_root,
        ),
        "clean_checkout_reproduction_receipt_path": str(clean_checkout_reproduction_out),
        "git_clean_clone_reproduction_receipt_path": str(git_clean_clone_reproduction_out),
        "artifact_paths": {
            "acquisition_plan": str(acquisition_plan_out),
            "buildingsmart_ifc_acquisition_receipt": str(buildingsmart_ifc_acquisition_out),
            "buildingsmart_dirty_ifc_acquisition_receipt": str(buildingsmart_dirty_ifc_acquisition_out),
            "ifc_source_license_receipt": str(ifc_source_license_out),
            "ifc_import_health_execution_receipt": str(ifc_import_health_execution_out),
            "opensees_source_license_receipt": str(opensees_source_license_out),
            "commercial_comparison_import_template": str(commercial_comparison_template_out),
            "commercial_operator_reference_contract": str(commercial_operator_reference_contract_out),
            "phase4_analytic_physical_fallback_scorecard": str(
                phase4_analytic_physical_fallback_out
            ),
            "commercial_operator_reference_ingest_validator": str(
                commercial_operator_reference_ingest_validator_out
            ),
            "manifest": str(manifest_out),
            "scorecard": str(scorecard_out),
            "summary": str(summary_out),
        },
        "stable_artifact_checksums": {
            "acquisition_plan": _stable_payload_checksum(acquisition_plan),
            "buildingsmart_ifc_acquisition_receipt": _stable_payload_checksum(
                buildingsmart_ifc_acquisition_receipt
            ),
            "buildingsmart_dirty_ifc_acquisition_receipt": _stable_payload_checksum(
                buildingsmart_dirty_ifc_acquisition_receipt
            ),
            "ifc_source_license_receipt": _stable_payload_checksum(ifc_source_license_receipt),
            "ifc_import_health_execution_receipt": _stable_payload_checksum(
                ifc_import_health_execution_receipt
            ),
            "opensees_source_license_receipt": _stable_payload_checksum(opensees_source_license_receipt),
            "commercial_comparison_import_template": _stable_payload_checksum(
                commercial_comparison_template
            ),
            "commercial_operator_reference_contract": _stable_payload_checksum(
                commercial_operator_reference_contract
            ),
            "phase4_analytic_physical_fallback_scorecard": _stable_payload_checksum(
                phase4_analytic_physical_fallback
            ),
            "commercial_operator_reference_ingest_validator": _stable_payload_checksum(
                commercial_operator_reference_ingest_validator
            ),
            "manifest": _stable_payload_checksum(manifest),
            "scorecard": _stable_payload_checksum(scorecard),
            "summary": _stable_payload_checksum(summary),
        },
        "stable_checksum_normalization": {
            "excluded_keys": sorted(STABLE_CHECKSUM_EXCLUDED_KEYS),
            "rationale": (
                "Stable replay checksums exclude volatile provenance plus local-only "
                "operator/private-corpus source acquisition and import execution fields. "
                "Those fields remain visible in their receipts, but they must not make "
                "minimal or git-clean checkout replay depend on ignored local corpora."
            ),
        },
        "expected_scorecard": {
            "status": scorecard["status"],
            "case_count": scorecard["case_count"],
            "pass_count": scorecard["pass_count"],
            "lanes": scorecard["lanes"],
            "lane_case_counts": lane_case_counts,
            "expected_output_comparison_count": scorecard[
                "expected_output_comparison_count"
            ],
            "expected_output_comparison_pass_count": scorecard[
                "expected_output_comparison_pass_count"
            ],
            "expected_output_contract_pass": scorecard["expected_output_contract_pass"],
            "residual_formula": "F_internal_minus_F_external",
            "regularization_used": False,
            "fallback_used": False,
        },
        "remaining_non_seed_phase3_targets": summary["remaining_quantity_targets"],
        "environment_notes": [
            "Requires the Python package sources and test dependencies available in the checkout.",
            "Does not download OpenSees, buildingSMART IFC, commercial solver, or large-model corpora.",
            "Does not prove Linux/Windows clean-checkout parity until those runs attach their own receipts.",
        ],
        "claim_boundary": (
            "This bundle records the command replay contract and stable checksums for the generated "
            "analytic-small, element-patch, and nonlinear material-mesh seed benchmark artifacts only. "
            "It does not prove an executed clean checkout run, Developer Preview Release Candidate "
            "closure, OpenSees, buildingSMART IFC, commercial-cross-solver, large-model, or full "
            "Phase 3 closure."
        ),
    }
    return {
        "cases": {"schema_version": "phase3-benchmark-factory-cases.v1", "rows": cases_to_jsonable(cases)},
        "buildingsmart_ifc_acquisition_receipt": buildingsmart_ifc_acquisition_receipt,
        "buildingsmart_dirty_ifc_acquisition_receipt": buildingsmart_dirty_ifc_acquisition_receipt,
        "ifc_source_license_receipt": ifc_source_license_receipt,
        "ifc_import_health_execution_receipt": ifc_import_health_execution_receipt,
        "opensees_source_license_receipt": opensees_source_license_receipt,
        "commercial_comparison_import_template": commercial_comparison_template,
        "phase4_analytic_physical_fallback_scorecard": phase4_analytic_physical_fallback,
        "commercial_operator_reference_contract": commercial_operator_reference_contract,
        "commercial_operator_reference_ingest_validator": commercial_operator_reference_ingest_validator,
        "acquisition_plan": acquisition_plan,
        "manifest": manifest,
        "scorecard": scorecard,
        "summary": summary,
        "reproducibility_bundle": reproducibility_bundle,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def check_phase3_benchmark_factory_artifacts(
    *,
    repo_root: Path = ROOT,
    manifest_out: Path = DEFAULT_MANIFEST_OUT,
    scorecard_out: Path = DEFAULT_SCORECARD_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    reproducibility_bundle_out: Path = DEFAULT_REPRODUCIBILITY_BUNDLE_OUT,
    clean_checkout_reproduction_out: Path = DEFAULT_CLEAN_CHECKOUT_REPRODUCTION_OUT,
    git_clean_clone_reproduction_out: Path = DEFAULT_GIT_CLEAN_CLONE_REPRODUCTION_OUT,
    acquisition_plan_out: Path = DEFAULT_ACQUISITION_PLAN_OUT,
    buildingsmart_ifc_acquisition_out: Path = DEFAULT_BUILDINGSMART_IFC_ACQUISITION_OUT,
    buildingsmart_dirty_ifc_acquisition_out: Path = DEFAULT_BUILDINGSMART_DIRTY_IFC_ACQUISITION_OUT,
    ifc_source_license_out: Path = DEFAULT_IFC_SOURCE_LICENSE_OUT,
    ifc_import_health_execution_out: Path = DEFAULT_IFC_IMPORT_HEALTH_EXECUTION_OUT,
    opensees_source_license_out: Path = DEFAULT_OPENSEES_SOURCE_LICENSE_OUT,
    commercial_comparison_template_out: Path = DEFAULT_COMMERCIAL_COMPARISON_TEMPLATE_OUT,
    phase4_analytic_physical_fallback_out: Path = DEFAULT_PHASE4_ANALYTIC_PHYSICAL_FALLBACK_OUT,
    commercial_operator_reference_contract_out: Path = DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_CONTRACT_OUT,
    commercial_operator_reference_ingest_validator_out: Path = (
        DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_INGEST_VALIDATOR_OUT
    ),
    source_commit_sha: str | None = None,
) -> tuple[bool, str]:
    expected = build_phase3_benchmark_factory_artifacts(
        repo_root=repo_root,
        manifest_out=manifest_out,
        scorecard_out=scorecard_out,
        summary_out=summary_out,
        reproducibility_bundle_out=reproducibility_bundle_out,
        clean_checkout_reproduction_out=clean_checkout_reproduction_out,
        git_clean_clone_reproduction_out=git_clean_clone_reproduction_out,
        acquisition_plan_out=acquisition_plan_out,
        buildingsmart_ifc_acquisition_out=buildingsmart_ifc_acquisition_out,
        buildingsmart_dirty_ifc_acquisition_out=buildingsmart_dirty_ifc_acquisition_out,
        ifc_source_license_out=ifc_source_license_out,
        ifc_import_health_execution_out=ifc_import_health_execution_out,
        opensees_source_license_out=opensees_source_license_out,
        commercial_comparison_template_out=commercial_comparison_template_out,
        phase4_analytic_physical_fallback_out=phase4_analytic_physical_fallback_out,
        commercial_operator_reference_contract_out=commercial_operator_reference_contract_out,
        commercial_operator_reference_ingest_validator_out=commercial_operator_reference_ingest_validator_out,
        source_commit_sha=source_commit_sha,
    )
    targets = {
        "manifest": manifest_out,
        "acquisition_plan": acquisition_plan_out,
        "buildingsmart_ifc_acquisition_receipt": buildingsmart_ifc_acquisition_out,
        "buildingsmart_dirty_ifc_acquisition_receipt": buildingsmart_dirty_ifc_acquisition_out,
        "ifc_source_license_receipt": ifc_source_license_out,
        "ifc_import_health_execution_receipt": ifc_import_health_execution_out,
        "opensees_source_license_receipt": opensees_source_license_out,
        "commercial_comparison_import_template": commercial_comparison_template_out,
        "phase4_analytic_physical_fallback_scorecard": phase4_analytic_physical_fallback_out,
        "commercial_operator_reference_contract": commercial_operator_reference_contract_out,
        "commercial_operator_reference_ingest_validator": commercial_operator_reference_ingest_validator_out,
        "scorecard": scorecard_out,
        "summary": summary_out,
        "reproducibility_bundle": reproducibility_bundle_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase3_benchmark_factory_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase3_benchmark_factory_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase3_benchmark_factory_mismatch:{key}"
    return True, "phase3_benchmark_factory_consistent"


def write_phase3_benchmark_factory_artifacts(
    *,
    repo_root: Path = ROOT,
    manifest_out: Path = DEFAULT_MANIFEST_OUT,
    scorecard_out: Path = DEFAULT_SCORECARD_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
    reproducibility_bundle_out: Path = DEFAULT_REPRODUCIBILITY_BUNDLE_OUT,
    clean_checkout_reproduction_out: Path = DEFAULT_CLEAN_CHECKOUT_REPRODUCTION_OUT,
    git_clean_clone_reproduction_out: Path = DEFAULT_GIT_CLEAN_CLONE_REPRODUCTION_OUT,
    acquisition_plan_out: Path = DEFAULT_ACQUISITION_PLAN_OUT,
    buildingsmart_ifc_acquisition_out: Path = DEFAULT_BUILDINGSMART_IFC_ACQUISITION_OUT,
    buildingsmart_dirty_ifc_acquisition_out: Path = DEFAULT_BUILDINGSMART_DIRTY_IFC_ACQUISITION_OUT,
    ifc_source_license_out: Path = DEFAULT_IFC_SOURCE_LICENSE_OUT,
    ifc_import_health_execution_out: Path = DEFAULT_IFC_IMPORT_HEALTH_EXECUTION_OUT,
    opensees_source_license_out: Path = DEFAULT_OPENSEES_SOURCE_LICENSE_OUT,
    commercial_comparison_template_out: Path = DEFAULT_COMMERCIAL_COMPARISON_TEMPLATE_OUT,
    phase4_analytic_physical_fallback_out: Path = DEFAULT_PHASE4_ANALYTIC_PHYSICAL_FALLBACK_OUT,
    commercial_operator_reference_contract_out: Path = DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_CONTRACT_OUT,
    commercial_operator_reference_ingest_validator_out: Path = (
        DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_INGEST_VALIDATOR_OUT
    ),
    source_commit_sha: str | None = None,
) -> dict[str, dict[str, Any]]:
    artifacts = build_phase3_benchmark_factory_artifacts(
        repo_root=repo_root,
        manifest_out=manifest_out,
        scorecard_out=scorecard_out,
        summary_out=summary_out,
        reproducibility_bundle_out=reproducibility_bundle_out,
        clean_checkout_reproduction_out=clean_checkout_reproduction_out,
        git_clean_clone_reproduction_out=git_clean_clone_reproduction_out,
        acquisition_plan_out=acquisition_plan_out,
        buildingsmart_ifc_acquisition_out=buildingsmart_ifc_acquisition_out,
        buildingsmart_dirty_ifc_acquisition_out=buildingsmart_dirty_ifc_acquisition_out,
        ifc_source_license_out=ifc_source_license_out,
        ifc_import_health_execution_out=ifc_import_health_execution_out,
        opensees_source_license_out=opensees_source_license_out,
        commercial_comparison_template_out=commercial_comparison_template_out,
        phase4_analytic_physical_fallback_out=phase4_analytic_physical_fallback_out,
        commercial_operator_reference_contract_out=commercial_operator_reference_contract_out,
        commercial_operator_reference_ingest_validator_out=commercial_operator_reference_ingest_validator_out,
        source_commit_sha=source_commit_sha,
    )
    for key, path in {
        "manifest": manifest_out,
        "acquisition_plan": acquisition_plan_out,
        "buildingsmart_ifc_acquisition_receipt": buildingsmart_ifc_acquisition_out,
        "buildingsmart_dirty_ifc_acquisition_receipt": buildingsmart_dirty_ifc_acquisition_out,
        "ifc_source_license_receipt": ifc_source_license_out,
        "ifc_import_health_execution_receipt": ifc_import_health_execution_out,
        "opensees_source_license_receipt": opensees_source_license_out,
        "commercial_comparison_import_template": commercial_comparison_template_out,
        "phase4_analytic_physical_fallback_scorecard": phase4_analytic_physical_fallback_out,
        "commercial_operator_reference_contract": commercial_operator_reference_contract_out,
        "commercial_operator_reference_ingest_validator": commercial_operator_reference_ingest_validator_out,
        "scorecard": scorecard_out,
        "summary": summary_out,
        "reproducibility_bundle": reproducibility_bundle_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--scorecard-out", type=Path, default=DEFAULT_SCORECARD_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--reproducibility-bundle-out", type=Path, default=DEFAULT_REPRODUCIBILITY_BUNDLE_OUT)
    parser.add_argument("--clean-checkout-reproduction-out", type=Path, default=DEFAULT_CLEAN_CHECKOUT_REPRODUCTION_OUT)
    parser.add_argument(
        "--git-clean-clone-reproduction-out",
        type=Path,
        default=DEFAULT_GIT_CLEAN_CLONE_REPRODUCTION_OUT,
    )
    parser.add_argument("--acquisition-plan-out", type=Path, default=DEFAULT_ACQUISITION_PLAN_OUT)
    parser.add_argument(
        "--buildingsmart-ifc-acquisition-out",
        type=Path,
        default=DEFAULT_BUILDINGSMART_IFC_ACQUISITION_OUT,
    )
    parser.add_argument(
        "--buildingsmart-dirty-ifc-acquisition-out",
        type=Path,
        default=DEFAULT_BUILDINGSMART_DIRTY_IFC_ACQUISITION_OUT,
    )
    parser.add_argument("--ifc-source-license-out", type=Path, default=DEFAULT_IFC_SOURCE_LICENSE_OUT)
    parser.add_argument(
        "--ifc-import-health-execution-out",
        type=Path,
        default=DEFAULT_IFC_IMPORT_HEALTH_EXECUTION_OUT,
    )
    parser.add_argument("--opensees-source-license-out", type=Path, default=DEFAULT_OPENSEES_SOURCE_LICENSE_OUT)
    parser.add_argument(
        "--commercial-comparison-template-out",
        type=Path,
        default=DEFAULT_COMMERCIAL_COMPARISON_TEMPLATE_OUT,
    )
    parser.add_argument(
        "--phase4-analytic-physical-fallback-out",
        type=Path,
        default=DEFAULT_PHASE4_ANALYTIC_PHYSICAL_FALLBACK_OUT,
    )
    parser.add_argument(
        "--commercial-operator-reference-contract-out",
        type=Path,
        default=DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_CONTRACT_OUT,
    )
    parser.add_argument(
        "--commercial-operator-reference-ingest-validator-out",
        type=Path,
        default=DEFAULT_COMMERCIAL_OPERATOR_REFERENCE_INGEST_VALIDATOR_OUT,
    )
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_phase3_benchmark_factory_artifacts(
            manifest_out=args.manifest_out,
            scorecard_out=args.scorecard_out,
            summary_out=args.summary_out,
            reproducibility_bundle_out=args.reproducibility_bundle_out,
            clean_checkout_reproduction_out=args.clean_checkout_reproduction_out,
            git_clean_clone_reproduction_out=args.git_clean_clone_reproduction_out,
            acquisition_plan_out=args.acquisition_plan_out,
            buildingsmart_ifc_acquisition_out=args.buildingsmart_ifc_acquisition_out,
            buildingsmart_dirty_ifc_acquisition_out=args.buildingsmart_dirty_ifc_acquisition_out,
            ifc_source_license_out=args.ifc_source_license_out,
            ifc_import_health_execution_out=args.ifc_import_health_execution_out,
            opensees_source_license_out=args.opensees_source_license_out,
            commercial_comparison_template_out=args.commercial_comparison_template_out,
            phase4_analytic_physical_fallback_out=args.phase4_analytic_physical_fallback_out,
            commercial_operator_reference_contract_out=args.commercial_operator_reference_contract_out,
            commercial_operator_reference_ingest_validator_out=(
                args.commercial_operator_reference_ingest_validator_out
            ),
            source_commit_sha=args.source_commit_sha,
        )
        print(f"Phase 3 benchmark factory check: {message}")
        return 0 if ok else 1
    artifacts = write_phase3_benchmark_factory_artifacts(
        manifest_out=args.manifest_out,
        scorecard_out=args.scorecard_out,
        summary_out=args.summary_out,
        reproducibility_bundle_out=args.reproducibility_bundle_out,
        clean_checkout_reproduction_out=args.clean_checkout_reproduction_out,
        git_clean_clone_reproduction_out=args.git_clean_clone_reproduction_out,
        acquisition_plan_out=args.acquisition_plan_out,
        buildingsmart_ifc_acquisition_out=args.buildingsmart_ifc_acquisition_out,
        buildingsmart_dirty_ifc_acquisition_out=args.buildingsmart_dirty_ifc_acquisition_out,
        ifc_source_license_out=args.ifc_source_license_out,
        ifc_import_health_execution_out=args.ifc_import_health_execution_out,
        opensees_source_license_out=args.opensees_source_license_out,
        commercial_comparison_template_out=args.commercial_comparison_template_out,
        phase4_analytic_physical_fallback_out=args.phase4_analytic_physical_fallback_out,
        commercial_operator_reference_contract_out=args.commercial_operator_reference_contract_out,
        commercial_operator_reference_ingest_validator_out=(
            args.commercial_operator_reference_ingest_validator_out
        ),
        source_commit_sha=args.source_commit_sha,
    )
    summary = artifacts["summary"]
    print(
        "Phase 3 benchmark factory seed: "
        f"{summary['status']} | cases={summary['case_count']} | "
        f"pass={summary['pass_count']} | phase3_closure={summary['phase3_closure_claim']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
