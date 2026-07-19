#!/usr/bin/env python3
"""Run or validate the Engine v2 HIP canonical sparse-LU apply receipt."""

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

from release_evidence_metadata import (  # noqa: E402
    file_sha256,
    git_head,
    input_checksums,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2_backends.hip_sparse_lu_apply import (  # noqa: E402
    build_hip_sparse_lu_apply_reference,
    compare_hip_sparse_lu_apply_output,
    validate_hip_sparse_lu_fixture_parser_output,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "engine_v2_hip_sparse_lu_apply_receipt.json"
DEFAULT_COMPILE_OUT = (
    PRODUCTIZATION / "engine_v2_hip_sparse_lu_apply_compile_receipt.json"
)
SOURCE_PATH = Path(
    "implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp"
)
MODULE_PATH = Path(
    "src/structural_analysis/engine_v2_backends/hip_sparse_lu_apply.py"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/hip_sparse_lu_apply_parity_v1.schema.json"
)
COMPILE_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "hip_sparse_lu_apply_compile_receipt_v1.schema.json"
)
RECEIPT_SCHEMA_VERSION = (
    "engine-v2-hip-sparse-lu-apply-parity-receipt.v1"
)
COMPILE_RECEIPT_SCHEMA_VERSION = (
    "engine-v2-hip-sparse-lu-apply-target-compile-host-parse-receipt.v1"
)
_ARCH_PATTERN = re.compile(r"gfx[0-9a-f]+")
BLOCKERS_REMAINING = [
    "actual_mgt_70560_factor_not_executed_by_this_fixture",
    "production_scale_level_schedule_not_executed",
    "current_tangent_fgmres_not_connected_to_hip_factor_apply",
    "independent_gfx1100_receipt_not_attached",
    "same_clean_source_commit_cross_device_not_verified",
    "signed_hardware_receipt_not_attached",
    "model_size_performance_sweep_not_executed",
]
CLAIM_BOUNDARY = (
    "This receipt covers one actual AMD ROCm/HIP execution of a nontrivial "
    "eight-equation canonical sparse-LU factor with row/column permutations "
    "and dependency-level scheduled forward/back substitution. It compares "
    "the device result to both the canonical Python-fsum apply and a matching "
    "sequential-FP64 device-order CPU reference. It does not cover the actual "
    "70,560-equation MGT factor, production-size scheduling or performance, "
    "device-resident current-tangent FGMRES, independent cross-device evidence, "
    "a retained release factor artifact, or G1 closure."
)
COMPILE_BLOCKERS_REMAINING = [
    "actual_hardware_execution_not_performed",
    "numerical_parity_not_evaluated",
    "actual_mgt_70560_factor_not_executed",
    "production_scale_level_schedule_not_executed",
    "current_tangent_fgmres_not_connected_to_hip_factor_apply",
    "independent_cross_device_receipts_not_attached",
    "model_size_performance_sweep_not_executed",
]
COMPILE_CLAIM_BOUNDARY = (
    "This dual-target receipt proves only that the canonical sparse-LU "
    "level-scheduled HIP source compiles with warnings treated as errors for "
    "declared gfx1030 and gfx1100 targets and that each resulting binary runs "
    "the same host-only, zero-HIP-runtime-call fixture parser successfully. It "
    "does not launch a kernel, access hardware, verify numerical parity, execute "
    "the actual 70,560-equation MGT factor, establish production-size schedule "
    "execution or current-tangent FGMRES integration, measure performance, or "
    "close G1."
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
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
    raise RuntimeError("engine_v2_hip_sparse_lu_hipcc_missing")


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
    raise RuntimeError("engine_v2_hip_sparse_lu_device_libs_missing")


def _detect_architecture(repo_root: Path, rocminfo: str) -> str:
    executable = shutil.which(rocminfo) or rocminfo
    result = _run([executable], cwd=repo_root, timeout=30.0)
    if result.returncode != 0:
        raise RuntimeError("engine_v2_hip_sparse_lu_rocminfo_failed")
    matches = _ARCH_PATTERN.findall(result.stdout)
    if not matches:
        raise RuntimeError("engine_v2_hip_sparse_lu_arch_not_detected")
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
        COMPILE_SCHEMA_PATH,
        Path("scripts/run_engine_v2_hip_sparse_lu_apply.py"),
        Path("tests/test_engine_v2_hip_sparse_lu_apply.py"),
        Path("tests/test_engine_v2_hip_sparse_lu_apply_runner.py"),
        Path(
            "src/structural_analysis/solvers/nonlinear/"
            "canonical_sparse_lu.py"
        ),
    ]


def _receipt_hash(payload: dict[str, Any]) -> str:
    without_hash = dict(payload)
    without_hash.pop("receipt_hash", None)
    return canonical_hash(without_hash)


def build_receipt_from_runtime_output(
    runtime_output: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    compiler_path: str,
    compiler_version_output: str,
    binary_sha256: str,
) -> dict[str, Any]:
    reference = build_hip_sparse_lu_apply_reference()
    comparison = compare_hip_sparse_lu_apply_output(reference, runtime_output)
    if comparison["contract_pass"] is not True:
        raise RuntimeError("engine_v2_hip_sparse_lu_numerical_parity_failed")
    architecture = str(runtime_output["gcn_arch_name"])
    provisional = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "source": {
            "repository_base_commit_sha": git_head(repo_root),
            "worktree_clean": _worktree_clean(repo_root),
            "exact_source_commit_claim": False,
            "input_checksums": input_checksums(
                _source_paths(),
                repo_root=repo_root,
            ),
        },
        "fixture": reference.fixture.to_manifest(),
        "hardware_execution": {
            "actual_hardware": True,
            "backend": "amd_rocm_hip",
            "device_name": runtime_output["device_name"],
            "gcn_arch_name": architecture,
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
        "comparison": comparison,
        "claims": {
            "actual_hardware_sparse_lu_apply": True,
            "canonical_sparse_lu_apply_numerical_parity": True,
            "same_stream_level_schedule_executed": True,
            "gfx1030_local_sparse_lu_apply": architecture == "gfx1030",
            "gfx1100_independent_sparse_lu_apply": architecture == "gfx1100",
            "actual_mgt_factor_apply": False,
            "production_scale_factor_apply": False,
            "production_current_tangent_fgmres": False,
            "performance": False,
        },
        "blockers_remaining": BLOCKERS_REMAINING,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    provisional["receipt_hash"] = _receipt_hash(provisional)
    return validate_receipt(provisional, repo_root=repo_root)


def validate_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool = False,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=None).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("engine_v2_hip_sparse_lu_receipt_hash_mismatch")
    runtime = payload["hardware_execution"]["runtime_output"]
    reference = build_hip_sparse_lu_apply_reference()
    comparison = compare_hip_sparse_lu_apply_output(reference, runtime)
    if comparison != payload["comparison"]:
        raise ValueError("engine_v2_hip_sparse_lu_comparison_mismatch")
    if payload["fixture"] != reference.fixture.to_manifest():
        raise ValueError("engine_v2_hip_sparse_lu_fixture_mismatch")
    if require_current_sources:
        expected = input_checksums(_source_paths(), repo_root=repo_root)
        if payload["source"]["input_checksums"] != expected:
            raise ValueError("engine_v2_hip_sparse_lu_source_checksums_stale")
        if payload["source"]["repository_base_commit_sha"] != git_head(
            repo_root
        ):
            raise ValueError("engine_v2_hip_sparse_lu_base_commit_mismatch")
    return payload


def build_compile_receipt(
    *,
    repo_root: Path = ROOT,
    compiler_path: str,
    compiler_version_output: str,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_targets = sorted(targets, key=lambda row: str(row["architecture"]))
    if [row["architecture"] for row in ordered_targets] != [
        "gfx1030",
        "gfx1100",
    ]:
        raise ValueError("engine_v2_hip_sparse_lu_compile_targets_invalid")
    if not all(
        row.get("host_fixture_parser_execution") is True
        and row.get("host_fixture_validation", {}).get("contract_pass") is True
        and row["host_fixture_validation"]["actual_hardware_execution"]
        is False
        and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
        for row in ordered_targets
    ):
        raise ValueError(
            "engine_v2_hip_sparse_lu_host_fixture_validation_invalid"
        )
    provisional = {
        "schema_version": COMPILE_RECEIPT_SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "contract_scope": "target_compile_and_host_fixture_parser_only",
        "source": {
            "repository_base_commit_sha": git_head(repo_root),
            "worktree_clean": _worktree_clean(repo_root),
            "exact_source_commit_claim": False,
            "input_checksums": input_checksums(
                _source_paths(),
                repo_root=repo_root,
            ),
        },
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
        "targets": ordered_targets,
        "claims": {
            "declared_target_compile": True,
            "gfx1030_target_compile": True,
            "gfx1100_target_compile": True,
            "dual_target_host_fixture_parser_execution": True,
            "actual_hardware_execution": False,
            "numerical_parity": False,
            "actual_mgt_factor_apply": False,
            "production_scale_factor_apply": False,
            "production_current_tangent_fgmres": False,
            "performance": False,
        },
        "blockers_remaining": COMPILE_BLOCKERS_REMAINING,
        "claim_boundary": COMPILE_CLAIM_BOUNDARY,
    }
    provisional["receipt_hash"] = _receipt_hash(provisional)
    return validate_compile_receipt(provisional, repo_root=repo_root)


def validate_compile_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool = False,
) -> dict[str, Any]:
    schema = _read_json(repo_root / COMPILE_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=None).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError(
            "engine_v2_hip_sparse_lu_compile_receipt_hash_mismatch"
        )
    architectures = [row["architecture"] for row in payload["targets"]]
    if architectures != ["gfx1030", "gfx1100"]:
        raise ValueError("engine_v2_hip_sparse_lu_compile_target_order_invalid")
    if require_current_sources:
        expected = input_checksums(_source_paths(), repo_root=repo_root)
        if payload["source"]["input_checksums"] != expected:
            raise ValueError(
                "engine_v2_hip_sparse_lu_compile_source_checksums_stale"
            )
        if payload["source"]["repository_base_commit_sha"] != git_head(
            repo_root
        ):
            raise ValueError(
                "engine_v2_hip_sparse_lu_compile_base_commit_mismatch"
            )
    return payload


def run_compile_only(
    *,
    repo_root: Path = ROOT,
    hipcc: str = "/opt/rocm/bin/hipcc",
    rocm_path: str = "/opt/rocm",
    device_lib_path: str = "",
) -> dict[str, Any]:
    compiler = _resolve_hipcc(hipcc)
    device_libs = _resolve_device_lib_path(repo_root, device_lib_path)
    version = _run([str(compiler), "--version"], cwd=repo_root, timeout=30.0)
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError("engine_v2_hip_sparse_lu_hipcc_version_failed")
    target_rows: list[dict[str, Any]] = []
    reference = build_hip_sparse_lu_apply_reference()
    with tempfile.TemporaryDirectory(
        prefix="engine-v2-hip-sparse-lu-compile-"
    ) as temporary:
        temporary_path = Path(temporary)
        fixture_path = temporary_path / "fixture.bin"
        fixture_path.write_bytes(reference.fixture.to_bytes())
        for architecture in ("gfx1030", "gfx1100"):
            binary_path = temporary_path / f"engine_v2_sparse_lu_{architecture}"
            command = [
                str(compiler),
                f"--rocm-path={rocm_path}",
                f"--rocm-device-lib-path={device_libs}",
                f"--offload-arch={architecture}",
                str(repo_root / SOURCE_PATH),
                "-O2",
                "-Werror",
                "-ffp-contract=off",
                "-std=c++17",
                "-o",
                str(binary_path),
            ]
            compiled = _run(command, cwd=repo_root, timeout=120.0)
            if compiled.returncode != 0:
                raise RuntimeError(
                    "engine_v2_hip_sparse_lu_compile_failed:"
                    f"{architecture}:"
                    + compiled.stderr[-1000:].replace("\n", " ")
                )
            parsed = _run(
                [
                    str(binary_path),
                    "--validate-fixture-only",
                    str(fixture_path),
                ],
                cwd=repo_root,
                timeout=30.0,
            )
            if parsed.returncode != 0:
                raise RuntimeError(
                    "engine_v2_hip_sparse_lu_host_fixture_validation_failed:"
                    f"{architecture}:"
                    + parsed.stderr[-1000:].replace("\n", " ")
                )
            try:
                parser_output = json.loads(
                    parsed.stdout.strip().splitlines()[-1]
                )
            except Exception as exc:
                raise RuntimeError(
                    "engine_v2_hip_sparse_lu_host_fixture_output_invalid:"
                    f"{architecture}"
                ) from exc
            host_fixture_validation = (
                validate_hip_sparse_lu_fixture_parser_output(
                    reference.fixture,
                    parser_output,
                )
            )
            target_rows.append(
                {
                    "architecture": architecture,
                    "target_compile": True,
                    "binary_sha256": file_sha256(binary_path),
                    "binary_byte_length": binary_path.stat().st_size,
                    "host_fixture_parser_execution": True,
                    "host_fixture_validation": host_fixture_validation,
                }
            )
    return build_compile_receipt(
        repo_root=repo_root,
        compiler_path=str(compiler),
        compiler_version_output=version.stdout,
        targets=target_rows,
    )


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
        raise RuntimeError("engine_v2_hip_sparse_lu_hipcc_version_failed")
    reference = build_hip_sparse_lu_apply_reference()
    with tempfile.TemporaryDirectory(
        prefix="engine-v2-hip-sparse-lu-"
    ) as temporary:
        temporary_path = Path(temporary)
        fixture_path = temporary_path / "fixture.bin"
        binary_path = temporary_path / "engine_v2_sparse_lu_apply"
        fixture_path.write_bytes(reference.fixture.to_bytes())
        command = [
            str(compiler),
            f"--rocm-path={rocm_path}",
            f"--rocm-device-lib-path={device_libs}",
            f"--offload-arch={architecture}",
            str(repo_root / SOURCE_PATH),
            "-O2",
            "-ffp-contract=off",
            "-std=c++17",
            "-o",
            str(binary_path),
        ]
        compiled = _run(command, cwd=repo_root, timeout=120.0)
        if compiled.returncode != 0:
            raise RuntimeError(
                "engine_v2_hip_sparse_lu_compile_failed:"
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
                "engine_v2_hip_sparse_lu_execution_failed:"
                + executed.stderr[-1000:].replace("\n", " ")
            )
        try:
            runtime_output = json.loads(executed.stdout.strip().splitlines()[-1])
        except Exception as exc:
            raise RuntimeError(
                "engine_v2_hip_sparse_lu_output_invalid"
            ) from exc
    if runtime_output.get("gcn_arch_name") != architecture:
        raise RuntimeError("engine_v2_hip_sparse_lu_runtime_arch_mismatch")
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
        return False, f"engine_v2_hip_sparse_lu_receipt_missing:{out}"
    try:
        payload = _read_json(path)
        if payload.get("schema_version") == COMPILE_RECEIPT_SCHEMA_VERSION:
            validate_compile_receipt(
                payload,
                repo_root=repo_root,
                require_current_sources=True,
            )
        else:
            validate_receipt(
                payload,
                repo_root=repo_root,
                require_current_sources=True,
            )
    except Exception as exc:
        return False, (
            "engine_v2_hip_sparse_lu_receipt_invalid:"
            f"{exc.__class__.__name__}:{exc}"
        )
    return True, "engine_v2_hip_sparse_lu_receipt_consistent"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--hipcc", default="/opt/rocm/bin/hipcc")
    parser.add_argument("--rocminfo", default="rocminfo")
    parser.add_argument("--rocm-path", default="/opt/rocm")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    output_argument = args.out or (
        DEFAULT_COMPILE_OUT if args.compile_only else DEFAULT_OUT
    )
    if args.check:
        passed, reason = check_committed_receipt(out=output_argument)
        print(f"{'PASS' if passed else 'FAIL'} | {reason}")
        return 0 if passed else 1
    if args.compile_only:
        receipt = run_compile_only(
            hipcc=args.hipcc,
            rocm_path=args.rocm_path,
            device_lib_path=args.device_lib_path,
        )
    else:
        receipt = run_hardware_parity(
            hipcc=args.hipcc,
            rocminfo=args.rocminfo,
            rocm_path=args.rocm_path,
            device_lib_path=args.device_lib_path,
        )
    output = (
        output_argument
        if output_argument.is_absolute()
        else ROOT / output_argument
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json_text(receipt), encoding="utf-8")
    if args.compile_only:
        print(
            "partial | compile_only=True | actual_hardware=False | "
            "host_fixture_parser=True | targets=gfx1030,gfx1100 | "
            "production=false"
        )
    else:
        print(
            "partial | actual_hardware=True | "
            f"arch={receipt['hardware_execution']['gcn_arch_name']} | "
            "production=false"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
