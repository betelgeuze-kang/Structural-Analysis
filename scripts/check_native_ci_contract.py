#!/usr/bin/env python3
"""Validate the fail-closed shape of the staged native GitHub Actions gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
PR_FAST_PATH = WORKFLOW_DIR / "native-pr-fast.yml"
NIGHTLY_QUALITY_PATH = WORKFLOW_DIR / "native-nightly-quality.yml"
HIP_DEDICATED_PATH = WORKFLOW_DIR / "native-hip-dedicated.yml"

PR_FAST_CHILDREN = (
    "scope-contract",
    "rust-quality",
    "cpp-quality",
    "abi-contract",
    "modelir-golden",
    "dependency-boundary",
)
MERGE_PRODUCT_CHILDREN = (
    "build-package",
    "rust-cpp-integration",
    "python-oracle-parity",
    "checkpoint-restart",
    "bounded-product-e2e",
)
NIGHTLY_QUALITY_CHILDREN = ("sanitizer", "fuzz-smoke", "dependency-license")

FORBIDDEN_HOSTED_COMMANDS = (
    "hipcc",
    "rocminfo",
    "rocm-smi",
    "systemctl",
    "service --status-all",
    "service actions.runner",
)


def _job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    try:
        jobs_index = next(index for index, line in enumerate(lines) if line == "jobs:")
    except StopIteration:
        return {}
    starts: list[tuple[str, int]] = []
    for index in range(jobs_index + 1, len(lines)):
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", lines[index])
        if match:
            starts.append((match.group(1), index))
    blocks: dict[str, str] = {}
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        blocks[name] = "\n".join(lines[start:end])
    return blocks


def _needs(block: str) -> set[str]:
    inline = re.search(r"^    needs:\s*\[([^\]]*)\]", block, flags=re.MULTILINE)
    if inline:
        return {
            item.strip()
            for item in inline.group(1).split(",")
            if item.strip()
        }
    lines = block.splitlines()
    values: set[str] = set()
    for index, line in enumerate(lines):
        if line != "    needs:":
            continue
        for child in lines[index + 1 :]:
            match = re.match(r"^      - ([A-Za-z0-9_-]+)\s*$", child)
            if match:
                values.add(match.group(1))
                continue
            if child.strip() and not child.startswith("      "):
                break
        break
    return values


def _timeout(block: str) -> int | None:
    match = re.search(r"^    timeout-minutes:\s*(\d+)\s*$", block, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _checkout_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if "uses: actions/checkout@" in line]
    blocks: list[str] = []
    for start in starts:
        end = start + 1
        while end < len(lines):
            line = lines[end]
            if re.match(r"^      - (?:name|uses):", line):
                break
            end += 1
        blocks.append("\n".join(lines[start:end]))
    return blocks


def check_native_ci_contract(repo_root: Path = ROOT) -> dict[str, object]:
    repo_root = repo_root.resolve()
    pr_path = repo_root / PR_FAST_PATH.relative_to(ROOT)
    nightly_path = repo_root / NIGHTLY_QUALITY_PATH.relative_to(ROOT)
    blockers: list[str] = []

    if not pr_path.is_file():
        blockers.append("workflow_missing:.github/workflows/native-pr-fast.yml")
    if not nightly_path.is_file():
        blockers.append("workflow_missing:.github/workflows/native-nightly-quality.yml")
    if blockers:
        return _report(blockers, {}, {})

    pr_text = pr_path.read_text(encoding="utf-8")
    nightly_text = nightly_path.read_text(encoding="utf-8")
    pr_jobs = _job_blocks(pr_text)
    nightly_jobs = _job_blocks(nightly_text)

    expected_pr_jobs = set(PR_FAST_CHILDREN) | {
        "native-pr-fast",
        "native-merge-product",
    } | set(MERGE_PRODUCT_CHILDREN)
    expected_nightly_jobs = set(NIGHTLY_QUALITY_CHILDREN) | {
        "native-nightly-quality"
    }
    for job in sorted(expected_pr_jobs - set(pr_jobs)):
        blockers.append(f"native_pr_fast_job_missing:{job}")
    for job in sorted(expected_nightly_jobs - set(nightly_jobs)):
        blockers.append(f"native_nightly_quality_job_missing:{job}")

    aggregate = pr_jobs.get("native-pr-fast", "")
    if _needs(aggregate) != set(PR_FAST_CHILDREN):
        blockers.append("native_pr_fast_aggregate_needs_mismatch")
    if "if: always()" not in aggregate:
        blockers.append("native_pr_fast_aggregate_not_fail_closed")

    merge_aggregate = pr_jobs.get("native-merge-product", "")
    if _needs(merge_aggregate) != (
        set(MERGE_PRODUCT_CHILDREN) | {"scope-contract", "native-pr-fast"}
    ):
        blockers.append("native_merge_product_aggregate_needs_mismatch")
    if "if: always()" not in merge_aggregate:
        blockers.append("native_merge_product_aggregate_not_fail_closed")
    if "name: native-merge-product" not in merge_aggregate:
        blockers.append("native_merge_product_context_name_mismatch")
    if "uses: ./.github/workflows/" in merge_aggregate:
        blockers.append("native_merge_product_context_is_reusable_compound_name")
    for child in MERGE_PRODUCT_CHILDREN:
        if _needs(pr_jobs.get(child, "")) != {"scope-contract", "native-pr-fast"}:
            blockers.append(f"native_merge_product_child_not_sequenced:{child}")

    nightly_aggregate = nightly_jobs.get("native-nightly-quality", "")
    if _needs(nightly_aggregate) != set(NIGHTLY_QUALITY_CHILDREN):
        blockers.append("native_nightly_quality_aggregate_needs_mismatch")
    if "if: always()" not in nightly_aggregate:
        blockers.append("native_nightly_quality_aggregate_not_fail_closed")

    fast_jobs = set(PR_FAST_CHILDREN) | {"native-pr-fast"}
    merge_jobs = set(MERGE_PRODUCT_CHILDREN) | {"native-merge-product"}
    for name in sorted(fast_jobs):
        block = pr_jobs.get(name, "")
        timeout = _timeout(block)
        if timeout is None:
            blockers.append(f"native_pr_fast_timeout_missing:{name}")
        elif timeout > 10:
            blockers.append(f"native_pr_fast_timeout_exceeds_10:{name}:{timeout}")
        if "runs-on: ubuntu-24.04" not in block:
            blockers.append(f"native_pr_fast_hosted_runner_mismatch:{name}")

    for name in sorted(merge_jobs):
        block = pr_jobs.get(name, "")
        timeout = _timeout(block)
        if timeout is None:
            blockers.append(f"native_merge_product_timeout_missing:{name}")
        elif timeout > 30:
            blockers.append(f"native_merge_product_timeout_exceeds_30:{name}:{timeout}")
        if "runs-on: ubuntu-24.04" not in block:
            blockers.append(f"native_merge_product_hosted_runner_mismatch:{name}")

    for name, block in nightly_jobs.items():
        timeout = _timeout(block)
        if timeout is None:
            blockers.append(f"native_nightly_quality_timeout_missing:{name}")
        elif timeout > 45:
            blockers.append(f"native_nightly_quality_timeout_exceeds_45:{name}:{timeout}")
        if "runs-on: ubuntu-24.04" not in block:
            blockers.append(f"native_nightly_quality_hosted_runner_mismatch:{name}")

    for label, text in (
        ("native-pr-fast", pr_text),
        ("native-nightly-quality", nightly_text),
    ):
        for index, checkout in enumerate(_checkout_blocks(text), start=1):
            if "lfs: false" not in checkout:
                blockers.append(f"{label}_checkout_lfs_not_explicit:{index}")
            if "persist-credentials: false" not in checkout:
                blockers.append(f"{label}_checkout_credentials_persisted:{index}")
        lowered = text.lower()
        for command in FORBIDDEN_HOSTED_COMMANDS:
            if command in lowered:
                blockers.append(f"{label}_hosted_command_forbidden:{command}")

    for required in (
        "pull_request:",
        "merge_group:",
        "push:",
        'branches: ["main"]',
        "cancel-in-progress: true",
        "--fail-protected-evidence",
        "STRUCTURAL_ENABLE_HIP=OFF",
        "merge-ref base parent mismatch",
        "merge-ref head parent mismatch",
        "git rev-parse HEAD^{tree}",
        "check_native_capabilities.py --fail-invalid",
        "check_native_checkpoint_restart.py",
        "check_native_product_e2e.py",
        "check_native_mgt_import.py",
        "check_native_durable_jobs.py",
        "check_native_job_service_api.py",
        "check_native_external_comparison.py",
        "check_native_generalized_eigen.py",
        "check_native_generalized_eigen_product.py",
        "check_native_pdf_report.py",
        "check_native_workbench.py",
        "check_native_reference_elements.py",
        "check_native_sparse_linear.py",
        "check_native_sparse_linear_product.py",
        "check_native_model_ir_linear_product.py",
        "check_native_model_ir_linear_jobs.py",
        "check_native_model_ir_linear_workbench.py",
        "check_native_nonlinear_static_product.py",
        "check_native_nonlinear_static_hip.py",
        "check_native_nonlinear_ndtha_hip.py",
        "check_native_sparse_linear_hip.py",
        "check_native_full_residual_backend_hip.py",
        "check_native_backend_selector.py",
        "check_native_deployment_cutover.py --json --fail-blocked",
        "check_native_automation_cutover.py --json --fail-blocked",
        "check_native_workbench_ui_transition.py --json --fail-blocked",
        "check_native_replay_product_link.py",
        "check_structural_runtime_ffi_r4.py",
        "implementation/phase1/structural_runtime_ffi/Cargo.toml",
        "build/native-legacy-runtime-r4/release/libstructural_runtime_ffi.so",
        "tests/test_native_nonlinear_ndtha_python_parity.py",
        "tests/test_native_mgt_import_health_python_parity.py",
        "tests/test_native_reference_elements_python_parity.py",
        "tests/test_native_sparse_linear_python_parity.py",
        "tests/test_native_generalized_eigen_python_parity.py",
        "tests/test_native_nonlinear_static_python_parity.py",
        "tests/test_native_track_point_load_python_parity.py",
        "structural_nonlinear_static_abi_tests",
        "structural_backend_selector_abi_tests",
        "structural_legacy_full_residual_replay_consumer",
        "structural_legacy_full_residual_worker_consumer",
        "structural_legacy_frame_force_replay_consumer",
        "structural_legacy_shell_csr_replay_consumer",
        "structural_nonlinear_ndtha_abi_tests",
        "structural_reference_elements_abi_tests",
        "structural_model_ir_linear_assembly_abi_tests",
        "structural_sparse_linear_abi_tests",
        'payload["abi_version"] == "0x0001000f"',
    ):
        if required not in pr_text:
            blockers.append(f"native_pr_fast_contract_token_missing:{required}")

    try:
        hip_text = HIP_DEDICATED_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"native_hip_dedicated_unreadable:{exc}")
        hip_text = ""
    for required in (
        "workflow_dispatch:",
        "environment: native-hip-approved",
        "runs-on: [self-hosted, linux, x64, rocm, structural-approved]",
        "STRUCTURAL_ENABLE_HIP=ON",
        "structural_reference_elements_hip_parity_tests",
        "structural_sparse_linear_hip_parity_tests",
        "structural_nonlinear_static_hip_parity_tests",
        "structural_nonlinear_ndtha_hip_parity_tests",
        "structural_full_residual_backend_hip_parity_tests",
        "check_native_reference_elements_hip.py",
        "check_native_sparse_linear_hip.py",
        "check_native_nonlinear_static_hip.py",
        "check_native_nonlinear_ndtha_hip.py",
        "check_native_full_residual_backend_hip.py",
        "native-sparse-linear-hip-receipt.json",
        "native-nonlinear-static-hip-receipt.json",
        "native-nonlinear-ndtha-hip-receipt.json",
        "native-full-residual-backend-hip-receipt.json",
        "--require-approved-runner",
    ):
        if required not in hip_text:
            blockers.append(f"native_hip_dedicated_contract_token_missing:{required}")
    hip_trigger_text = hip_text.split("permissions:", 1)[0]
    if "pull_request:" in hip_trigger_text or "push:" in hip_trigger_text:
        blockers.append("native_hip_dedicated_has_automatic_trigger")

    trigger_text = pr_text.split("permissions:", 1)[0]
    if "paths:" in trigger_text:
        blockers.append("native_required_context_workflow_uses_path_filter")

    for required in (
        "schedule:",
        "STRUCTURAL_ENABLE_SANITIZERS=ON",
        "STRUCTURAL_BUILD_FUZZERS=ON",
        "structural_native_fuzzers",
        "check_native_dependency_licenses.py",
        "STRUCTURAL_ENABLE_HIP=OFF",
    ):
        if required not in nightly_text:
            blockers.append(f"native_nightly_quality_contract_token_missing:{required}")

    return _report(blockers, pr_jobs, nightly_jobs)


def _report(
    blockers: list[str],
    pr_jobs: dict[str, str],
    nightly_jobs: dict[str, str],
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "native-ci-workflow-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "native_pr_fast_jobs": sorted(pr_jobs),
        "native_merge_product_jobs": sorted(
            set(pr_jobs) & (set(MERGE_PRODUCT_CHILDREN) | {"native-merge-product"})
        ),
        "native_nightly_quality_jobs": sorted(nightly_jobs),
        "blockers": blockers,
        "claim_boundary": (
            "This validates hosted workflow topology, sequencing and fail-closed scope. "
            "It is not execution evidence for a workspace, product slice, or HIP device."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_native_ci_contract(args.repo_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native CI workflow contract: {payload['status']}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
