#!/usr/bin/env python3
"""Run or validate the Engine v2 HIP current-tangent operator receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
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
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    HIPCurrentTangentOperatorFixture,
    build_hip_current_tangent_operator_reference,
    compare_hip_current_tangent_operator_output,
    validate_hip_current_tangent_fixture_parser_output,
    validate_hip_current_tangent_operator_fixture,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = (
    PRODUCTIZATION / "engine_v2_hip_current_tangent_operator_receipt.json"
)
DEFAULT_COMPILE_OUT = (
    PRODUCTIZATION
    / "engine_v2_hip_current_tangent_operator_compile_receipt.json"
)
SOURCE_PATH = Path(
    "implementation/phase1/hip_kernels/"
    "engine_v2_current_tangent_operator.hip.cpp"
)
MODULE_PATH = Path(
    "src/structural_analysis/engine_v2_backends/"
    "hip_current_tangent_operator.py"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "hip_current_tangent_operator_parity_v1.schema.json"
)
COMPILE_SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "hip_current_tangent_operator_compile_receipt_v1.schema.json"
)
RECEIPT_SCHEMA_VERSION = (
    "engine-v2-hip-current-tangent-operator-parity-receipt.v1"
)
COMPILE_RECEIPT_SCHEMA_VERSION = (
    "engine-v2-hip-current-tangent-target-compile-host-parse-receipt.v1"
)
_ARCH_PATTERN = re.compile(r"gfx[0-9a-f]+")
BLOCKERS_REMAINING = [
    "actual_mgt_70560_operator_not_executed_by_this_fixture",
    "actual_mgt_current_tangent_cpu_hip_parity_not_verified",
    "current_tangent_fgmres_and_preconditioner_not_integrated_on_device",
    "independent_cross_device_receipts_not_attached",
    "same_clean_source_commit_cross_device_not_verified",
    "signed_hardware_receipt_not_attached",
    "model_size_performance_sweep_not_executed",
]
CLAIM_BOUNDARY = (
    "This receipt covers one actual AMD ROCm/HIP execution of a nontrivial "
    "five-equation current-tangent fixture containing reference CSR, frame "
    "load delta, prescribed background, and finite-chord axial terms. It "
    "compares the device action to canonical NumPy and matching device-order "
    "CPU references. It does not cover the actual 70,560-equation MGT "
    "operator, device-resident FGMRES/preconditioner integration, independent "
    "cross-device evidence, performance, a production nonlinear solver, or "
    "G1 closure."
)
COMPILE_BLOCKERS_REMAINING = [
    "actual_hardware_execution_not_performed",
    "numerical_parity_not_evaluated",
    "actual_mgt_70560_operator_not_executed",
    "current_tangent_fgmres_and_preconditioner_not_integrated_on_device",
    "independent_cross_device_receipts_not_attached",
    "model_size_performance_sweep_not_executed",
]
COMPILE_CLAIM_BOUNDARY = (
    "This dual-target receipt proves only that the current-tangent HIP source "
    "compiles with warnings treated as errors for declared gfx1030 and "
    "gfx1100 targets and that each binary runs the same host-only, zero-HIP-"
    "runtime-call fixture parser. It does not launch a kernel, access "
    "hardware, verify numerical parity, execute the actual 70,560-equation "
    "MGT operator, integrate device-resident FGMRES/preconditioning, measure "
    "performance, or close G1."
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
    raise RuntimeError("engine_v2_hip_current_tangent_hipcc_missing")


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
    raise RuntimeError("engine_v2_hip_current_tangent_device_libs_missing")


def _detect_architecture(repo_root: Path, rocminfo: str) -> str:
    executable = shutil.which(rocminfo) or rocminfo
    result = _run([executable], cwd=repo_root, timeout=30.0)
    if result.returncode != 0:
        raise RuntimeError("engine_v2_hip_current_tangent_rocminfo_failed")
    matches = _ARCH_PATTERN.findall(result.stdout)
    if not matches:
        raise RuntimeError("engine_v2_hip_current_tangent_arch_not_detected")
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
        Path("scripts/run_engine_v2_hip_current_tangent_operator.py"),
        Path("tests/test_engine_v2_hip_current_tangent_operator.py"),
        Path("tests/test_engine_v2_hip_current_tangent_operator_runner.py"),
        Path(
            "src/structural_analysis/engine_v2/contracts/"
            "current_tangent_operator.py"
        ),
        Path(
            "src/structural_analysis/schemas/"
            "current_tangent_operator_v1.schema.json"
        ),
        Path("tests/test_engine_v2_current_tangent_operator_v1.py"),
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
    reference = build_hip_current_tangent_operator_reference()
    comparison = compare_hip_current_tangent_operator_output(
        reference,
        runtime_output,
    )
    if comparison["contract_pass"] is not True:
        raise RuntimeError(
            "engine_v2_hip_current_tangent_numerical_parity_failed"
        )
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
            "compiler": _compiler_manifest(
                compiler_path,
                compiler_version_output,
            ),
            "binary_sha256": binary_sha256,
            "runtime_output": runtime_output,
        },
        "comparison": comparison,
        "claims": {
            "actual_hardware_current_tangent_action": True,
            "current_tangent_numerical_parity": True,
            "deterministic_free_row_schedule_executed": True,
            "gfx1030_local_current_tangent_action": architecture == "gfx1030",
            "gfx1100_independent_current_tangent_action": (
                architecture == "gfx1100"
            ),
            "actual_mgt_current_tangent_action": False,
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
        raise ValueError(
            "engine_v2_hip_current_tangent_receipt_hash_mismatch"
        )
    reference = build_hip_current_tangent_operator_reference()
    runtime = payload["hardware_execution"]["runtime_output"]
    comparison = compare_hip_current_tangent_operator_output(
        reference,
        runtime,
    )
    if comparison != payload["comparison"]:
        raise ValueError(
            "engine_v2_hip_current_tangent_comparison_mismatch"
        )
    if payload["fixture"] != reference.fixture.to_manifest():
        raise ValueError("engine_v2_hip_current_tangent_fixture_mismatch")
    if require_current_sources:
        _validate_source_identity(payload["source"], repo_root=repo_root)
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
        raise ValueError(
            "engine_v2_hip_current_tangent_compile_targets_invalid"
        )
    if not all(
        row.get("host_fixture_parser_execution") is True
        and row.get("host_fixture_validation", {}).get("contract_pass") is True
        and row["host_fixture_validation"]["actual_hardware_execution"]
        is False
        and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
        for row in ordered_targets
    ):
        raise ValueError(
            "engine_v2_hip_current_tangent_host_fixture_validation_invalid"
        )
    reference = build_hip_current_tangent_operator_reference()
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
        "fixture": reference.fixture.to_manifest(),
        "compiler": _compiler_manifest(
            compiler_path,
            compiler_version_output,
        ),
        "targets": ordered_targets,
        "claims": {
            "declared_target_compile": True,
            "gfx1030_target_compile": True,
            "gfx1100_target_compile": True,
            "dual_target_host_fixture_parser_execution": True,
            "actual_hardware_execution": False,
            "numerical_parity": False,
            "actual_mgt_current_tangent_action": False,
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
            "engine_v2_hip_current_tangent_compile_receipt_hash_mismatch"
        )
    if [row["architecture"] for row in payload["targets"]] != [
        "gfx1030",
        "gfx1100",
    ]:
        raise ValueError(
            "engine_v2_hip_current_tangent_compile_target_order_invalid"
        )
    reference = build_hip_current_tangent_operator_reference()
    if payload["fixture"] != reference.fixture.to_manifest():
        raise ValueError(
            "engine_v2_hip_current_tangent_compile_fixture_mismatch"
        )
    for row in payload["targets"]:
        validation = row["host_fixture_validation"]
        if validation["fixture_hash"] != reference.fixture.fixture_hash:
            raise ValueError(
                "engine_v2_hip_current_tangent_parser_fixture_mismatch"
            )
    if require_current_sources:
        _validate_source_identity(payload["source"], repo_root=repo_root)
    return payload


def compile_and_validate_host_fixture_for_targets(
    fixture: HIPCurrentTangentOperatorFixture,
    *,
    repo_root: Path = ROOT,
    hipcc: str = "/opt/rocm/bin/hipcc",
    rocm_path: str = "/opt/rocm",
    device_lib_path: str = "",
    architectures: tuple[str, ...] = ("gfx1030", "gfx1100"),
) -> dict[str, Any]:
    """Compile declared targets and run only their host fixture parser."""

    validated = validate_hip_current_tangent_operator_fixture(fixture)
    if (
        not architectures
        or len(set(architectures)) != len(architectures)
        or any(_ARCH_PATTERN.fullmatch(value) is None for value in architectures)
    ):
        raise ValueError(
            "engine_v2_hip_current_tangent_host_parser_targets_invalid"
        )
    compiler = _resolve_hipcc(hipcc)
    device_libs = _resolve_device_lib_path(repo_root, device_lib_path)
    version = _run([str(compiler), "--version"], cwd=repo_root, timeout=30.0)
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError(
            "engine_v2_hip_current_tangent_hipcc_version_failed"
        )
    target_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="engine-v2-hip-current-tangent-compile-"
    ) as temporary:
        temporary_path = Path(temporary)
        fixture_path = temporary_path / "fixture.bin"
        fixture_path.write_bytes(validated.to_bytes())
        for architecture in architectures:
            binary_path = temporary_path / f"current_tangent_{architecture}"
            compiled = _compile(
                compiler=compiler,
                repo_root=repo_root,
                rocm_path=rocm_path,
                device_libs=device_libs,
                architecture=architecture,
                binary_path=binary_path,
            )
            if compiled.returncode != 0:
                raise RuntimeError(
                    "engine_v2_hip_current_tangent_compile_failed:"
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
                    "engine_v2_hip_current_tangent_host_fixture_failed:"
                    f"{architecture}:"
                    + parsed.stderr[-1000:].replace("\n", " ")
                )
            parser_output = _last_json(parsed.stdout, architecture)
            validation = validate_hip_current_tangent_fixture_parser_output(
                validated,
                parser_output,
            )
            target_rows.append(
                {
                    "architecture": architecture,
                    "target_compile": True,
                    "binary_sha256": file_sha256(binary_path),
                    "binary_byte_length": binary_path.stat().st_size,
                    "host_fixture_parser_execution": True,
                    "host_fixture_validation": validation,
                }
            )
    return {
        "compiler": _compiler_manifest(str(compiler), version.stdout),
        "compiler_path": str(compiler),
        "compiler_version_output": version.stdout,
        "targets": target_rows,
    }


def run_compile_only(
    *,
    repo_root: Path = ROOT,
    hipcc: str = "/opt/rocm/bin/hipcc",
    rocm_path: str = "/opt/rocm",
    device_lib_path: str = "",
) -> dict[str, Any]:
    reference = build_hip_current_tangent_operator_reference()
    compiled = compile_and_validate_host_fixture_for_targets(
        reference.fixture,
        repo_root=repo_root,
        hipcc=hipcc,
        rocm_path=rocm_path,
        device_lib_path=device_lib_path,
    )
    return build_compile_receipt(
        repo_root=repo_root,
        compiler_path=compiled["compiler_path"],
        compiler_version_output=compiled["compiler_version_output"],
        targets=compiled["targets"],
    )


def run_hardware_parity(
    *,
    repo_root: Path = ROOT,
    hipcc: str = "/opt/rocm/bin/hipcc",
    rocm_path: str = "/opt/rocm",
    device_lib_path: str = "",
    rocminfo: str = "rocminfo",
    architecture: str = "",
) -> dict[str, Any]:
    reference = build_hip_current_tangent_operator_reference()
    executed = compile_and_run_hardware_fixture(
        reference.fixture,
        repo_root=repo_root,
        hipcc=hipcc,
        rocm_path=rocm_path,
        device_lib_path=device_lib_path,
        rocminfo=rocminfo,
        architecture=architecture,
    )
    return build_receipt_from_runtime_output(
        executed["runtime_output"],
        repo_root=repo_root,
        compiler_path=executed["compiler_path"],
        compiler_version_output=executed["compiler_version_output"],
        binary_sha256=executed["binary_sha256"],
    )


def compile_and_run_hardware_fixture(
    fixture: HIPCurrentTangentOperatorFixture,
    *,
    repo_root: Path = ROOT,
    hipcc: str = "/opt/rocm/bin/hipcc",
    rocm_path: str = "/opt/rocm",
    device_lib_path: str = "",
    rocminfo: str = "rocminfo",
    architecture: str = "",
    runtime_timeout: float = 120.0,
) -> dict[str, Any]:
    """Compile and execute one valid fixture on a matching HIP device."""

    validated = validate_hip_current_tangent_operator_fixture(fixture)
    if architecture and not _ARCH_PATTERN.fullmatch(architecture):
        raise ValueError("engine_v2_hip_current_tangent_arch_invalid")
    if not math.isfinite(runtime_timeout) or runtime_timeout <= 0.0:
        raise ValueError("engine_v2_hip_current_tangent_timeout_invalid")
    compiler = _resolve_hipcc(hipcc)
    device_libs = _resolve_device_lib_path(repo_root, device_lib_path)
    selected_arch = architecture or _detect_architecture(repo_root, rocminfo)
    if not _ARCH_PATTERN.fullmatch(selected_arch):
        raise ValueError("engine_v2_hip_current_tangent_arch_invalid")
    version = _run([str(compiler), "--version"], cwd=repo_root, timeout=30.0)
    if version.returncode != 0 or not version.stdout.strip():
        raise RuntimeError(
            "engine_v2_hip_current_tangent_hipcc_version_failed"
        )
    with tempfile.TemporaryDirectory(
        prefix="engine-v2-hip-current-tangent-runtime-"
    ) as temporary:
        temporary_path = Path(temporary)
        fixture_path = temporary_path / "fixture.bin"
        binary_path = temporary_path / "current_tangent"
        fixture_path.write_bytes(validated.to_bytes())
        compiled = _compile(
            compiler=compiler,
            repo_root=repo_root,
            rocm_path=rocm_path,
            device_libs=device_libs,
            architecture=selected_arch,
            binary_path=binary_path,
        )
        if compiled.returncode != 0:
            raise RuntimeError(
                "engine_v2_hip_current_tangent_compile_failed:"
                + compiled.stderr[-1000:].replace("\n", " ")
            )
        executed = _run(
            [str(binary_path), str(fixture_path)],
            cwd=repo_root,
            timeout=runtime_timeout,
        )
        if executed.returncode != 0:
            raise RuntimeError(
                "engine_v2_hip_current_tangent_runtime_failed:"
                + executed.stderr[-1000:].replace("\n", " ")
            )
        runtime_output = _last_json(executed.stdout, selected_arch)
        if runtime_output.get("gcn_arch_name") != selected_arch:
            raise RuntimeError(
                "engine_v2_hip_current_tangent_runtime_arch_mismatch"
            )
        return {
            "compiler": _compiler_manifest(str(compiler), version.stdout),
            "compiler_path": str(compiler),
            "compiler_version_output": version.stdout,
            "architecture": selected_arch,
            "binary_sha256": file_sha256(binary_path),
            "binary_byte_length": binary_path.stat().st_size,
            "runtime_output": runtime_output,
        }


def check_committed_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path | None = None,
    compile_only: bool = False,
) -> tuple[bool, str]:
    relative = out_path or (DEFAULT_COMPILE_OUT if compile_only else DEFAULT_OUT)
    path = relative if relative.is_absolute() else repo_root / relative
    if not path.is_file():
        return False, "receipt_missing"
    try:
        payload = _read_json(path)
        if compile_only:
            validate_compile_receipt(
                payload,
                repo_root=repo_root,
                require_current_sources=True,
            )
            return True, "hip_current_tangent_compile_receipt_consistent"
        validate_receipt(
            payload,
            repo_root=repo_root,
            require_current_sources=True,
        )
        return True, "hip_current_tangent_runtime_receipt_consistent"
    except Exception as exc:
        return False, str(exc)


def _compiler_manifest(path: str, version_output: str) -> dict[str, Any]:
    return {
        "path": path,
        "version_first_line": version_output.splitlines()[0],
        "version_output_sha256": (
            "sha256:"
            + hashlib.sha256(version_output.encode("utf-8")).hexdigest()
        ),
    }


def _validate_source_identity(source: dict[str, Any], *, repo_root: Path) -> None:
    if source["input_checksums"] != input_checksums(
        _source_paths(),
        repo_root=repo_root,
    ):
        raise ValueError(
            "engine_v2_hip_current_tangent_source_checksums_stale"
        )
    if source["repository_base_commit_sha"] != git_head(repo_root):
        raise ValueError("engine_v2_hip_current_tangent_base_commit_mismatch")


def _compile(
    *,
    compiler: Path,
    repo_root: Path,
    rocm_path: str,
    device_libs: Path,
    architecture: str,
    binary_path: Path,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
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
        ],
        cwd=repo_root,
        timeout=120.0,
    )


def _last_json(output: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(output.strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(
            f"engine_v2_hip_current_tangent_output_invalid:{label}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"engine_v2_hip_current_tangent_output_invalid:{label}"
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--compile-out", type=Path, default=DEFAULT_COMPILE_OUT)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--hipcc", default="/opt/rocm/bin/hipcc")
    parser.add_argument("--rocm-path", default="/opt/rocm")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--rocminfo", default="rocminfo")
    parser.add_argument("--architecture", default="")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    selected_out = args.compile_out if args.compile_only else args.out
    if args.check:
        passed, reason = check_committed_receipt(
            repo_root=repo_root,
            out_path=selected_out,
            compile_only=args.compile_only,
        )
        print(reason)
        return 0 if passed else 1
    if args.compile_only:
        payload = run_compile_only(
            repo_root=repo_root,
            hipcc=args.hipcc,
            rocm_path=args.rocm_path,
            device_lib_path=args.device_lib_path,
        )
    else:
        payload = run_hardware_parity(
            repo_root=repo_root,
            hipcc=args.hipcc,
            rocm_path=args.rocm_path,
            device_lib_path=args.device_lib_path,
            rocminfo=args.rocminfo,
            architecture=args.architecture,
        )
    output_path = selected_out
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json_text(payload), encoding="utf-8")
    print(
        f"{payload['status']} | scope="
        f"{payload.get('contract_scope', 'hardware_parity')} | "
        f"contract_pass={str(payload['contract_pass']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
