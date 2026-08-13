#!/usr/bin/env python3
"""Classify changed paths for the staged native CI lanes.

The classifier intentionally uses only the Python standard library so the gate
bootstrap can run before the Rust/C++ workspace exists.  Python is a CI control
plane dependency here; it is not part of the native product runtime.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

PROTECTED_EVIDENCE_PREFIXES = (
    ".betelgeuze/",
    "implementation/phase1/release_evidence/productization/",
)
PROTECTED_EVIDENCE_PATHS = frozenset(
    {
        "docs/commercial-structural-solver-product-gap-ledger.md",
        "docs/structural-analysis-ai-engine-gap-ledger.md",
    }
)

NATIVE_CI_CONTROL_PATHS = frozenset(
    {
        ".dockerignore",
        ".github/workflows/deploy-pages.yml",
        ".github/workflows/authoritative-core-evidence-resync.yml",
        ".github/workflows/release-publish.yml",
        ".github/workflows/native-pr-fast.yml",
        ".github/workflows/native-nightly-quality.yml",
        "native/decommission/legacy-frontend-build-contract-v1.json",
        "scripts/build_native_distribution.sh",
        "scripts/build_native_benchmark_catalog.sh",
        "scripts/build_native_workbench_evidence_bundle.sh",
        "scripts/build_onprem_deployment_packaging_manifest.py",
        "scripts/check_native_ci_contract.py",
        "scripts/check_native_automation_cutover.py",
        "scripts/check_native_capabilities.py",
        "scripts/check_native_checkpoint_restart.py",
        "scripts/check_native_deployment_cutover.py",
        "scripts/check_native_distribution_receipt.py",
        "scripts/check_native_dependency_boundary.py",
        "scripts/check_native_dependency_licenses.py",
        "scripts/check_native_external_comparison.py",
        "scripts/check_native_generalized_eigen.py",
        "scripts/check_native_generalized_eigen_hip.py",
        "scripts/check_native_generalized_eigen_product.py",
        "scripts/check_native_job_service_api.py",
        "scripts/check_native_mgt_import.py",
        "scripts/check_native_model_ir_linear_product.py",
        "scripts/check_native_model_ir_linear_jobs.py",
        "scripts/check_native_nonlinear_static_hip.py",
        "scripts/check_native_nonlinear_ndtha_hip.py",
        "scripts/check_native_pdf_report.py",
        "scripts/check_native_product_e2e.py",
        "scripts/check_native_reference_elements.py",
        "scripts/check_native_reference_elements_hip.py",
        "scripts/check_native_replay_product_link.py",
        "scripts/check_native_sparse_linear.py",
        "scripts/check_native_sparse_linear_hip.py",
        "scripts/check_native_workbench.py",
        "scripts/check_native_workbench_ui_transition.py",
        "scripts/check_structural_runtime_ffi_r1.py",
        "scripts/check_structural_runtime_ffi_r2.py",
        "scripts/check_structural_runtime_ffi_r3.py",
        "scripts/check_structural_runtime_ffi_r4.py",
        "scripts/classify_native_ci_scope.py",
        "scripts/run_native_distribution_e2e.sh",
        "scripts/run_native_rocm_distribution_e2e.sh",
        "scripts/run_native_rootfs_isolation_e2e.sh",
        "scripts/dispatch_release_publish_workflow.py",
        "scripts/publish_github_release_assets.py",
        "tests/test_native_ci_scope.py",
        "tests/test_native_capability_manifest.py",
        "tests/test_native_checkpoint_restart_contract.py",
        "tests/test_native_ci_workflow_contract.py",
        "tests/test_native_automation_cutover.py",
        "tests/test_native_dependency_license.py",
        "tests/test_native_deployment_cutover.py",
        "tests/test_native_distribution_contract.py",
        "tests/test_native_external_comparison_contract.py",
        "tests/test_native_generalized_eigen_contract.py",
        "tests/test_native_generalized_eigen_hip_contract.py",
        "tests/test_native_generalized_eigen_product_contract.py",
        "tests/test_native_generalized_eigen_python_parity.py",
        "tests/test_native_job_service_api_contract.py",
        "tests/test_native_mgt_import_contract.py",
        "tests/test_native_mgt_import_health_python_parity.py",
        "tests/test_native_model_ir_linear_product_contract.py",
        "tests/test_native_model_ir_linear_jobs_contract.py",
        "tests/test_native_pdf_report_contract.py",
        "tests/test_native_nonlinear_ndtha_python_parity.py",
        "tests/test_native_nonlinear_static_hip_contract.py",
        "tests/test_native_nonlinear_ndtha_hip_contract.py",
        "tests/test_native_product_e2e_contract.py",
        "tests/test_native_reference_elements_contract.py",
        "tests/test_native_reference_elements_hip_contract.py",
        "tests/test_native_reference_elements_python_parity.py",
        "tests/test_native_replay_product_link_contract.py",
        "tests/test_native_sparse_linear_contract.py",
        "tests/test_native_sparse_linear_hip_contract.py",
        "tests/test_native_sparse_linear_python_parity.py",
        "tests/test_native_nonlinear_static_python_parity.py",
        "tests/test_native_track_point_load_python_parity.py",
        "tests/test_native_workbench_contract.py",
        "tests/test_native_workbench_ui_transition.py",
        "tests/test_structural_runtime_ffi_r1.py",
        "tests/test_structural_runtime_ffi_r2.py",
        "tests/test_structural_runtime_ffi_r3.py",
        "tests/test_structural_runtime_ffi_r4.py",
        "tests/test_structural_runtime_bridge_paths.py",
    }
)

NATIVE_DEPLOYMENT_PREFIXES = (
    "deployment/onprem/",
    "deployment/legacy-python-onprem/",
    "deployment/legacy-react-pages/",
    "deployment/legacy-python-release-publication/",
)

NATIVE_CATALOG_SOURCE_PREFIXES = (
    "implementation/phase1/open_data/irregular/collected/reports/",
    "implementation/phase1/open_data/pbd_hinge/peer_spd_specimens/",
)

LEGACY_WORKBENCH_UI_PREFIXES = (
    "src/workbench/",
    "src/workbench-v2/",
    "src/structure-viewer/",
    "tests/frontend/",
)
LEGACY_WORKBENCH_UI_PATHS = frozenset(
    {
        "index.html",
        "package.json",
        "package-lock.json",
        "vite.config.ts",
        "src/App.tsx",
        "src/index.css",
        "src/main.tsx",
        ".github/workflows/ai-contract-verify.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/frontend-web-ci.yml",
        ".github/workflows/nightly-full-quality.yml",
        ".github/workflows/nightly-heavy-solver.yml",
        ".github/workflows/runtime-input-viewer-ci.yml",
        ".github/workflows/viewer-browser-ci.yml",
    }
)

MODELIR_ORACLE_PREFIXES = (
    "src/structural_analysis/model_ir/",
    "src/structural_analysis/io/midas/",
    "tests/fixtures/foundation_realish/",
    "tests/fixtures/model_ir_v2/",
    "tests/native_oracles/",
)
MODELIR_ORACLE_PATHS = frozenset(
    {
        "src/structural_analysis/schemas/model_ir_v2.schema.json",
        "tests/test_model_ir_v2_contract.py",
        "tests/test_native_model_ir_rust_parity.py",
        "tests/test_native_mgt_import_health_python_parity.py",
        "tests/test_native_nonlinear_ndtha_python_parity.py",
        "tests/test_native_nonlinear_static_python_parity.py",
        "tests/test_native_track_point_load_python_parity.py",
    }
)

NATIVE_NUMERICAL_ORACLE_PREFIXES = (
    "native/cpp/src/materials/",
    "native/cpp/src/elements/",
    "native/cpp/src/assembly/",
    "native/cpp/tests/materials/",
    "native/cpp/tests/elements/",
    "native/cpp/tests/assembly/",
    "native/cpp/tests/abi/reference_elements_",
    "native/cpp/src/hip/",
    "native/cpp/tests/hip/",
    "native/cpp/src/solver_cpu/sparse_linear",
    "native/cpp/tests/solver_cpu/sparse_linear",
    "native/cpp/tests/fuzz/sparse_linear",
    "native/cpp/tests/abi/sparse_linear",
    "native/cpp/src/solver_cpu/generalized_eigen",
    "native/cpp/tests/solver_cpu/generalized_eigen",
    "native/cpp/tests/fuzz/generalized_eigen",
    "native/crates/structural-ffi-sys/src/reference_elements",
    "native/crates/structural-ffi/tests/reference_elements",
    "native/crates/structural-ffi-sys/src/sparse_linear",
    "native/crates/structural-ffi/tests/sparse_linear",
    ".github/workflows/native-hip-dedicated.yml",
)
NATIVE_NUMERICAL_ORACLE_PATHS = frozenset(
    {
        "tests/test_native_reference_elements_python_parity.py",
        "tests/test_native_sparse_linear_python_parity.py",
        "tests/test_native_generalized_eigen_python_parity.py",
    }
)

LEGACY_RUNTIME_COMPAT_PREFIX = "implementation/phase1/structural_runtime_ffi/"
LEGACY_REPLAY_CPP_PATHS = frozenset(
    {
        "implementation/phase1/hip_frame_force_batch_replay.cpp",
        "implementation/phase1/hip_full_residual_batch_replay.cpp",
        "implementation/phase1/hip_full_residual_resident_worker.cpp",
        "implementation/phase1/hip_shell_csr_batch_replay.cpp",
        "implementation/phase1/product_full_residual_replay.hpp",
    }
)
LEGACY_REPLAY_RUNTIME_PATHS = frozenset(
    {
        "implementation/phase1/mgt_hip_full_residual_backend.py",
        "implementation/phase1/run_mgt_hip_frame_force_batch_probe.py",
        "implementation/phase1/run_mgt_hip_full_residual_batch_probe.py",
        "implementation/phase1/run_mgt_hip_full_residual_resident_worker_probe.py",
        "implementation/phase1/run_mgt_hip_shell_csr_batch_probe.py",
    }
)
LEGACY_REPLAY_COMPAT_PATHS = LEGACY_REPLAY_CPP_PATHS | LEGACY_REPLAY_RUNTIME_PATHS


def _normalize_path(raw: str) -> str:
    value = raw.replace("\\", "/").strip()
    if not value:
        raise ValueError("changed path must not be empty")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"changed path escapes repository root: {raw!r}")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError("changed path must name a repository entry")
    return normalized


def _starts_with_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def classify_paths(raw_paths: Iterable[str]) -> dict[str, object]:
    """Return deterministic applicability flags for one changed-path set."""

    paths = sorted({_normalize_path(path) for path in raw_paths})
    native_paths = [
        path
        for path in paths
        if path.startswith("native/")
        or path.startswith(LEGACY_RUNTIME_COMPAT_PREFIX)
        or path in LEGACY_REPLAY_COMPAT_PATHS
        or _starts_with_any(path, NATIVE_DEPLOYMENT_PREFIXES)
        or _starts_with_any(path, NATIVE_CATALOG_SOURCE_PREFIXES)
        or _starts_with_any(path, LEGACY_WORKBENCH_UI_PREFIXES)
        or path in LEGACY_WORKBENCH_UI_PATHS
        or (path.startswith("scripts/") and path.endswith((".js", ".mjs")))
        or path in {".dockerignore", ".github/workflows/deploy-pages.yml"}
    ]
    ci_control_paths = [
        path
        for path in paths
        if path in NATIVE_CI_CONTROL_PATHS
        or _starts_with_any(path, NATIVE_DEPLOYMENT_PREFIXES)
        or _starts_with_any(path, LEGACY_WORKBENCH_UI_PREFIXES)
        or path in LEGACY_WORKBENCH_UI_PATHS
        or (path.startswith("scripts/") and path.endswith((".js", ".mjs")))
    ]
    protected_paths = [
        path
        for path in paths
        if path in PROTECTED_EVIDENCE_PATHS
        or _starts_with_any(path, PROTECTED_EVIDENCE_PREFIXES)
    ]
    modelir_oracle_paths = [
        path
        for path in paths
        if path in MODELIR_ORACLE_PATHS
        or _starts_with_any(path, MODELIR_ORACLE_PREFIXES)
        or (path.startswith("examples/") and ".model-ir.v2." in path)
    ]
    numerical_oracle_paths = [
        path
        for path in paths
        if path in NATIVE_NUMERICAL_ORACLE_PATHS
        or _starts_with_any(path, NATIVE_NUMERICAL_ORACLE_PREFIXES)
    ]

    rust_paths = [
        path
        for path in native_paths
        if path in {"native/Cargo.toml", "native/Cargo.lock"}
        or path.startswith("native/crates/")
        or path.startswith(LEGACY_RUNTIME_COMPAT_PREFIX)
    ]
    cpp_paths = [
        path
        for path in native_paths
        if path.startswith("native/cpp/")
        or path.startswith("native/cmake/")
        or path in LEGACY_REPLAY_CPP_PATHS
    ]
    abi_paths = [
        path
        for path in native_paths
        if path == "native/cpp/include/structural/abi_v1.h"
        or path.startswith("native/cpp/src/abi/")
        or path.startswith("native/tests/abi/")
        or path.startswith("native/crates/structural-ffi")
        or path.startswith(LEGACY_RUNTIME_COMPAT_PREFIX)
        or path in LEGACY_REPLAY_CPP_PATHS
    ]
    modelir_paths = [
        path
        for path in native_paths
        if path == "native/capabilities.json"
        or "model_ir" in path
        or "model_linear" in path.lower()
        or "modelir" in path.lower()
        or "mgt_import" in path.lower()
        or path.startswith("native/crates/structural-contracts/")
        or path.startswith("native/tests/fixtures/")
    ]
    runtime_paths = [
        path
        for path in native_paths
        if path.startswith("native/crates/structural-runtime/")
        or path.startswith("native/crates/structural-report/")
        or path.startswith("native/crates/structural-cli/")
        or path.startswith("native/tests/integration/")
        or path.startswith(LEGACY_RUNTIME_COMPAT_PREFIX)
        or path in LEGACY_REPLAY_RUNTIME_PATHS
    ]
    hip_paths = [
        path
        for path in native_paths
        if path.startswith("native/cpp/hip/")
        or path.endswith((".hip", ".hip.cpp", ".hip.hpp"))
        or path in LEGACY_REPLAY_COMPAT_PATHS
    ]

    docs_only = bool(paths) and all(path.startswith("docs/") for path in paths)
    applicable = bool(native_paths or modelir_oracle_paths or ci_control_paths)
    return {
        "schema_version": "native-ci-scope.v1",
        "changed_paths": paths,
        "changed_path_count": len(paths),
        "native": bool(native_paths),
        "rust": bool(rust_paths),
        "cpp": bool(cpp_paths),
        "abi": bool(abi_paths),
        "modelir": bool(modelir_paths or modelir_oracle_paths),
        "runtime": bool(runtime_paths),
        "hip": bool(hip_paths),
        "oracle": bool(modelir_oracle_paths or numerical_oracle_paths),
        "ci_control": bool(ci_control_paths),
        "applicable": applicable,
        "docs_only": docs_only,
        "protected_evidence": bool(protected_paths),
        "protected_evidence_paths": protected_paths,
    }


def _git_changed_paths(*, base: str, head: str, repo_root: Path) -> list[str]:
    if not head:
        raise ValueError("head commit is required when --path is not used")
    zero_base = bool(base) and set(base) == {"0"}
    if not base:
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", f"{head}^"],
            cwd=repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        base = parent.stdout.strip() if parent.returncode == 0 else ""
    if zero_base or not base:
        command = [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-z",
            "-r",
            "--diff-filter=ACMRD",
            head,
        ]
    else:
        command = [
            "git",
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRD",
            f"{base}...{head}",
        ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        path
        for path in completed.stdout.decode("utf-8", "surrogateescape").split("\0")
        if path
    ]


def _write_github_outputs(path: Path, payload: dict[str, object]) -> None:
    boolean_keys = (
        "native",
        "rust",
        "cpp",
        "abi",
        "modelir",
        "runtime",
        "hip",
        "oracle",
        "ci_control",
        "applicable",
        "docs_only",
        "protected_evidence",
    )
    with path.open("a", encoding="utf-8") as stream:
        for key in boolean_keys:
            stream.write(f"{key}={str(bool(payload[key])).lower()}\n")
        stream.write(f"changed_path_count={payload['changed_path_count']}\n")
        stream.write(
            "changed_paths_json="
            + json.dumps(payload["changed_paths"], ensure_ascii=True, separators=(",", ":"))
            + "\n"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("NATIVE_CI_BASE_SHA", ""))
    parser.add_argument("--head", default=os.environ.get("NATIVE_CI_HEAD_SHA", ""))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--path", action="append", dest="paths")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--fail-protected-evidence", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        changed_paths = (
            args.paths
            if args.paths is not None
            else _git_changed_paths(
                base=args.base,
                head=args.head,
                repo_root=args.repo_root.resolve(),
            )
        )
        payload = classify_paths(changed_paths)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"native CI scope classification failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.github_output is not None:
        _write_github_outputs(args.github_output, payload)
    if args.fail_protected_evidence and payload["protected_evidence"]:
        print(
            "native CI scope includes protected evidence: "
            + ", ".join(payload["protected_evidence_paths"]),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
