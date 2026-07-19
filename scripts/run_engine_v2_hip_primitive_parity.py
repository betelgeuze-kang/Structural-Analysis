#!/usr/bin/env python3
"""Run or offline-check the Engine v2 CPU/HIP primitive parity receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import file_sha256, git_head, input_checksums  # noqa: E402
from structural_analysis.engine_v2_backends.hip_primitive_parity import (  # noqa: E402
    build_engine_v2_cpu_hip_parity_reference,
    compare_hip_primitive_output,
    parity_receipt_hash,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "engine_v2_cpu_hip_primitive_parity_receipt.json"
SOURCE_PATH = Path(
    "implementation/phase1/hip_kernels/engine_v2_primitive_parity.hip.cpp"
)
MODULE_PATH = Path(
    "src/structural_analysis/engine_v2_backends/hip_primitive_parity.py"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/cpu_hip_primitive_parity_v1.schema.json"
)
RECEIPT_SCHEMA_VERSION = "engine-v2-cpu-hip-primitive-parity-receipt.v1"
BLOCKERS_REMAINING = [
    "full_fgmres_recurrence_not_covered_by_this_primitive_receipt",
    "device_resident_restart_checkpoint_not_covered_by_this_primitive_receipt",
    "production_scale_preconditioner_effectiveness_not_verified",
    "independent_gfx1100_receipt_not_attached",
    "same_clean_source_commit_cross_device_not_verified",
    "signed_hardware_receipt_not_attached",
    "wheel_hash_cross_device_identity_not_verified",
    "model_size_performance_sweep_not_executed",
]
CLAIM_BOUNDARY = (
    "This local development receipt binds the deterministic CPU FGMRES run and "
    "one actual gfx1030 HIP execution to the same reduced-CSR fixture. It verifies "
    "FP64 SpMV, dot, L2/Linf norm, operator-derived left-scaled Jacobi "
    "preconditioner apply, AXPY, "
    "solution update, same-stream ordering, and runtime status propagation within "
    "the declared tolerance. This primitive receipt does not cover the full "
    "device-resident FGMRES recurrence or restart/checkpoint parity, "
    "production-scale preconditioner effectiveness, gfx1100 "
    "independent evidence, a clean same-commit/wheel pair, a signed receipt, or "
    "performance."
)
_ARCH_PATTERN = re.compile(r"\b(gfx[0-9a-f]+)\b")


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: float = 120.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _resolve_hipcc(explicit: str) -> Path:
    candidates = [
        Path(explicit),
        Path("/opt/rocm/bin/hipcc"),
        Path("/opt/rocm-6.0.2/bin/hipcc"),
    ]
    located = shutil.which(explicit)
    if located:
        candidates.insert(0, Path(located))
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return candidate.resolve()
    raise RuntimeError("engine_v2_hipcc_missing")


def _resolve_device_lib_path(repo_root: Path, explicit: str) -> Path:
    candidates = [
        Path(explicit) if explicit else Path("/nonexistent"),
        repo_root
        / "implementation/phase1/third_party/rocm_device_libs/opt/"
        "rocm-5.7.1/amdgcn/bitcode",
        Path("/opt/rocm/amdgcn/bitcode"),
        Path("/opt/rocm/lib/bitcode"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError("engine_v2_rocm_device_libs_missing")


def _detect_architecture(repo_root: Path, rocminfo: str) -> str:
    executable = shutil.which(rocminfo) or rocminfo
    result = _run([executable], cwd=repo_root, timeout=30.0)
    if result.returncode != 0:
        raise RuntimeError("engine_v2_rocminfo_failed")
    matches = _ARCH_PATTERN.findall(result.stdout)
    if not matches:
        raise RuntimeError("engine_v2_gfx_arch_not_detected")
    return matches[0]


def _worktree_clean(repo_root: Path) -> bool:
    result = _run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=repo_root,
        timeout=30.0,
    )
    return result.returncode == 0 and not result.stdout.strip()


def _source_paths() -> list[Path]:
    return [
        MODULE_PATH,
        SOURCE_PATH,
        SCHEMA_PATH,
        Path("src/structural_analysis/engine_v2/cpu_fgmres.py"),
        Path(
            "src/structural_analysis/schemas/"
            "cpu_fgmres_run_v1.schema.json"
        ),
        Path(
            "src/structural_analysis/engine_v2/contracts/"
            "execution_plan_reduced_csr.py"
        ),
        Path("scripts/run_engine_v2_hip_primitive_parity.py"),
        Path("tests/test_engine_v2_hip_primitive_parity.py"),
        Path("tests/test_engine_v2_hip_primitive_parity_runner.py"),
        Path("tests/test_engine_v2_cpu_fgmres_v1.py"),
    ]


def build_receipt_from_runtime_output(
    runtime_output: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    compiler_path: str,
    compiler_version_output: str,
    binary_sha256: str,
) -> dict[str, Any]:
    reference = build_engine_v2_cpu_hip_parity_reference()
    comparison = compare_hip_primitive_output(reference.fixture, runtime_output)
    if comparison["contract_pass"] is not True:
        raise RuntimeError("engine_v2_hip_primitive_numerical_parity_failed")
    checksums = input_checksums(_source_paths(), repo_root=repo_root)
    clean = _worktree_clean(repo_root)
    cpu_run = reference.cpu_run
    provisional = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "source": {
            "repository_base_commit_sha": git_head(repo_root),
            "worktree_clean": clean,
            "exact_source_commit_claim": False,
            "input_checksums": checksums,
        },
        "cpu_reference": {
            "run_hash": cpu_run.run_hash,
            "execution_plan_hash": cpu_run.execution_plan_hash,
            "scaling_hash": cpu_run.scaling_hash,
            "reduced_csr_identity_hash": cpu_run.reduced_csr_identity_hash,
            "operator_numeric_values_hash": cpu_run.operator_numeric_values_hash,
            "preconditioner_profile": cpu_run.preconditioner_profile,
            "preconditioner_contract_hash": (
                reference.fixture.preconditioner_contract_hash
            ),
            "terminal_reason": cpu_run.terminal_reason,
            "converged": cpu_run.converged,
            "iteration_count": cpu_run.iteration_count,
            "restart_count": len(cpu_run.restart_history),
            "result_ir_authority": False,
        },
        "fixture": reference.fixture.to_manifest(),
        "hardware_execution": {
            "actual_hardware": True,
            "backend": "amd_rocm_hip",
            "device_name": runtime_output["device_name"],
            "gcn_arch_name": runtime_output["gcn_arch_name"],
            "compiler": {
                "path": compiler_path,
                "version_first_line": compiler_version_output.splitlines()[0],
                "version_output_sha256": (
                    "sha256:"
                    + hashlib.sha256(
                        compiler_version_output.encode("utf-8")
                    ).hexdigest()
                ),
            },
            "binary_sha256": binary_sha256,
            "runtime_output": runtime_output,
        },
        "primitive_comparison": comparison,
        "claims": {
            "gfx1030_local_primitive_parity": runtime_output["gcn_arch_name"]
            == "gfx1030",
            "gfx1030_local_operator_derived_scaled_jacobi_apply_parity": (
                runtime_output["gcn_arch_name"] == "gfx1030"
            ),
            "full_fgmres_recurrence_parity": False,
            "device_resident_restart_checkpoint": False,
            "independent_gfx1100_parity": False,
            "same_source_commit_cross_device": False,
            "signed_receipt": False,
            "production_preconditioner_parity": False,
            "performance": False,
        },
        "blockers_remaining": BLOCKERS_REMAINING,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    provisional["receipt_hash"] = parity_receipt_hash(provisional)
    validate_receipt(provisional, repo_root=repo_root, require_current_sources=True)
    return provisional


def validate_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != parity_receipt_hash(payload):
        raise ValueError("engine_v2_cpu_hip_primitive_receipt_hash_mismatch")
    reference = build_engine_v2_cpu_hip_parity_reference()
    cpu = payload["cpu_reference"]
    expected_cpu = {
        "run_hash": reference.cpu_run.run_hash,
        "execution_plan_hash": reference.cpu_run.execution_plan_hash,
        "scaling_hash": reference.cpu_run.scaling_hash,
        "reduced_csr_identity_hash": reference.cpu_run.reduced_csr_identity_hash,
        "operator_numeric_values_hash": (
            reference.cpu_run.operator_numeric_values_hash
        ),
    }
    if any(cpu[key] != value for key, value in expected_cpu.items()):
        raise ValueError("engine_v2_cpu_hip_primitive_cpu_reference_mismatch")
    if payload["fixture"] != reference.fixture.to_manifest():
        raise ValueError("engine_v2_cpu_hip_primitive_fixture_mismatch")
    comparison = compare_hip_primitive_output(
        reference.fixture,
        payload["hardware_execution"]["runtime_output"],
    )
    if comparison != payload["primitive_comparison"]:
        raise ValueError("engine_v2_cpu_hip_primitive_comparison_mismatch")
    if require_current_sources:
        current = input_checksums(_source_paths(), repo_root=repo_root)
        if current != payload["source"]["input_checksums"]:
            raise ValueError("engine_v2_cpu_hip_primitive_source_checksum_mismatch")
        if (
            payload["source"]["exact_source_commit_claim"] is True
            and git_head(repo_root)
            != payload["source"]["repository_base_commit_sha"]
        ):
            raise ValueError("engine_v2_cpu_hip_primitive_base_commit_mismatch")
    return payload


def run_hardware_parity(
    *,
    repo_root: Path = ROOT,
    hipcc: str = "/opt/rocm/bin/hipcc",
    rocminfo: str = "rocminfo",
    rocm_path: str = "/opt/rocm",
    device_lib_path: str = "",
) -> dict[str, Any]:
    compiler = _resolve_hipcc(hipcc)
    device_libs = _resolve_device_lib_path(repo_root, device_lib_path)
    architecture = _detect_architecture(repo_root, rocminfo)
    version = _run([str(compiler), "--version"], cwd=repo_root, timeout=30.0)
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError("engine_v2_hipcc_version_failed")
    reference = build_engine_v2_cpu_hip_parity_reference()
    with tempfile.TemporaryDirectory(
        prefix="engine-v2-hip-primitive-"
    ) as temporary:
        temporary_path = Path(temporary)
        fixture_path = temporary_path / "fixture.bin"
        binary_path = temporary_path / "engine_v2_primitive_parity"
        fixture_path.write_bytes(reference.fixture.to_bytes())
        compile_command = [
            str(compiler),
            f"--rocm-path={rocm_path}",
            f"--rocm-device-lib-path={device_libs}",
            f"--offload-arch={architecture}",
            str(repo_root / SOURCE_PATH),
            "-O2",
            "-std=c++17",
            "-o",
            str(binary_path),
        ]
        compiled = _run(compile_command, cwd=repo_root, timeout=120.0)
        if compiled.returncode != 0:
            raise RuntimeError(
                "engine_v2_hip_primitive_compile_failed:"
                + compiled.stderr[-1000:].replace("\n", " ")
            )
        binary_hash = file_sha256(binary_path)
        executed = _run(
            [str(binary_path), str(fixture_path)],
            cwd=repo_root,
            timeout=60.0,
        )
        if executed.returncode != 0:
            raise RuntimeError(
                "engine_v2_hip_primitive_execution_failed:"
                + executed.stderr[-1000:].replace("\n", " ")
            )
        try:
            runtime_output = json.loads(executed.stdout.strip().splitlines()[-1])
        except Exception as exc:
            raise RuntimeError("engine_v2_hip_primitive_output_invalid") from exc
    if runtime_output.get("gcn_arch_name") != architecture:
        raise RuntimeError("engine_v2_hip_primitive_compiled_runtime_arch_mismatch")
    return build_receipt_from_runtime_output(
        runtime_output,
        repo_root=repo_root,
        compiler_path=str(compiler),
        compiler_version_output=version.stdout,
        binary_sha256=binary_hash,
    )


def check_committed_receipt(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    path = out if out.is_absolute() else repo_root / out
    if not path.is_file():
        return False, f"engine_v2_cpu_hip_primitive_receipt_missing:{out}"
    try:
        payload = _read_json(path)
        validate_receipt(payload, repo_root=repo_root, require_current_sources=True)
    except Exception as exc:
        return False, (
            "engine_v2_cpu_hip_primitive_receipt_invalid:"
            f"{exc.__class__.__name__}:{exc}"
        )
    return True, "engine_v2_cpu_hip_primitive_receipt_consistent"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hipcc", default="/opt/rocm/bin/hipcc")
    parser.add_argument("--rocminfo", default="rocminfo")
    parser.add_argument("--rocm-path", default="/opt/rocm")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        ok, message = check_committed_receipt(repo_root=ROOT, out=args.out)
        print(message)
        return 0 if ok else 1
    receipt = run_hardware_parity(
        repo_root=ROOT,
        hipcc=args.hipcc,
        rocminfo=args.rocminfo,
        rocm_path=args.rocm_path,
        device_lib_path=args.device_lib_path,
    )
    path = args.out if args.out.is_absolute() else ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(receipt), encoding="utf-8")
    print(
        "partial | primitive_parity=True | full_recurrence=False | "
        f"device={receipt['hardware_execution']['gcn_arch_name']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
