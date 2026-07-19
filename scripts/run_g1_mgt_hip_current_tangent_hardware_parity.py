#!/usr/bin/env python3
"""Run or validate actual-MGT HIP current-tangent hardware parity."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PHASE1_ROOT = ROOT / "implementation" / "phase1"
for candidate in (SCRIPT_DIR, SRC_ROOT, PHASE1_ROOT):
    candidate_text = str(candidate)
    while candidate_text in sys.path:
        sys.path.remove(candidate_text)
    sys.path.insert(0, candidate_text)

from build_g1_mgt_hip_current_tangent_host_parser_receipt import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    DEFAULT_MGT,
    DEFAULT_OUT as HOST_PARSER_RECEIPT,
    build_actual_fixture,
    summarize_actual_fixture,
    validate_receipt as validate_host_parser_receipt,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)
from run_engine_v2_hip_current_tangent_operator import (  # noqa: E402
    DEFAULT_COMPILE_OUT as SYNTHETIC_COMPILE_RECEIPT,
    compile_and_run_hardware_fixture,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    HIP_CURRENT_TANGENT_OUTPUT_VERSION,
    HIPCurrentTangentOperatorReference,
    compare_hip_current_tangent_operator_output,
    create_hip_current_tangent_operator_reference,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = (
    PRODUCTIZATION
    / "g1_mgt_hip_current_tangent_hardware_parity_receipt.json"
)
DEFAULT_ACTION_OUT = (
    PRODUCTIZATION / "g1_mgt_hip_current_tangent_action.f64le"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_hip_current_tangent_hardware_parity_receipt_v1.schema.json"
)
SCHEMA_VERSION = (
    "g1-mgt-hip-current-tangent-hardware-parity-receipt.v1"
)
CASE_ID = "g1_actual_mgt_hip_current_tangent_hardware_parity"
CONTRACT_SCOPE = (
    "actual_mgt_single_state_direction_local_gfx1030_hardware_parity"
)
ACTION_FORMAT = "canonical_little_endian_float64_vector.v1"
ACTION_DTYPE = "<f8"
ACTION_COUNT = 70_560
ACTION_BYTE_LENGTH = ACTION_COUNT * 8


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(repo_root: Path, path: Path) -> str:
    absolute = _resolve(repo_root, path).resolve()
    try:
        return absolute.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("g1_mgt_hip_action_path_outside_repository") from exc


def _receipt_hash(payload: dict[str, Any]) -> str:
    without_hash = dict(payload)
    without_hash.pop("receipt_hash", None)
    return canonical_hash(without_hash)


def _input_paths(*, mgt_path: Path, checkpoint_npz: Path) -> list[Path]:
    return [
        mgt_path,
        checkpoint_npz,
        HOST_PARSER_RECEIPT,
        SYNTHETIC_COMPILE_RECEIPT,
        Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
        Path(
            "implementation/phase1/hip_kernels/"
            "engine_v2_current_tangent_operator.hip.cpp"
        ),
        Path(
            "src/structural_analysis/engine_v2/contracts/"
            "current_tangent_operator.py"
        ),
        Path(
            "src/structural_analysis/engine_v2_backends/"
            "hip_current_tangent_operator.py"
        ),
        Path("src/structural_analysis/engine_v2_backends/__init__.py"),
        Path("scripts/run_engine_v2_hip_current_tangent_operator.py"),
        Path("scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py"),
        Path("scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py"),
        SCHEMA_PATH,
        Path("tests/test_engine_v2_hip_current_tangent_operator.py"),
        Path("tests/test_engine_v2_hip_current_tangent_operator_runner.py"),
        Path(
            "tests/test_run_g1_mgt_hip_current_tangent_hardware_parity.py"
        ),
    ]


def _load_host_parser_receipt(
    *,
    repo_root: Path,
    require_current_sources: bool,
) -> dict[str, Any]:
    return validate_host_parser_receipt(
        _read_json(repo_root / HOST_PARSER_RECEIPT),
        repo_root=repo_root,
        require_current_sources=require_current_sources,
    )


def _target_row(payload: dict[str, Any], architecture: str) -> dict[str, Any]:
    matches = [
        row for row in payload["targets"] if row["architecture"] == architecture
    ]
    if len(matches) != 1:
        raise ValueError("g1_mgt_hip_host_parser_target_missing")
    return matches[0]


def _runtime_metadata(runtime_output: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(runtime_output)
    metadata.pop("action_n_per_m")
    return metadata


def _runtime_with_action(
    metadata: dict[str, Any],
    action: np.ndarray,
) -> dict[str, Any]:
    runtime = dict(metadata)
    runtime["action_n_per_m"] = action.tolist()
    return runtime


def _comparison_bundle(
    reference: HIPCurrentTangentOperatorReference,
    runtime_output: dict[str, Any],
) -> dict[str, Any]:
    generic = compare_hip_current_tangent_operator_output(
        reference,
        runtime_output,
    )
    canonical_scale = max(
        float(
            np.max(
                np.abs(reference.canonical_action_n_per_m),
                initial=0.0,
            )
        ),
        1.0,
    )
    return {
        "generic_comparison": generic,
        "actual_mgt_context": {
            "actual_mgt_fixture_identity_pass": True,
            "fixture_hash": reference.fixture.fixture_hash,
            "equation_count": reference.fixture.equation_count,
            "canonical_scale_n_per_m": canonical_scale,
            "canonical_relative_max_error": (
                generic["canonical_cpu_max_abs_error_n_per_m"]
                / canonical_scale
            ),
            "device_order_bitwise_match": bool(
                generic["device_order_cpu_max_abs_error_n_per_m"] == 0.0
                and generic["action_data_hash"]
                == generic["device_order_action_data_hash"]
            ),
        },
    }


def _action_manifest(
    *,
    repo_root: Path,
    action_out: Path,
    action: np.ndarray,
) -> tuple[dict[str, Any], bytes]:
    canonical = immutable_array(action, dtype=ACTION_DTYPE)
    if canonical.shape != (ACTION_COUNT,):
        raise ValueError("g1_mgt_hip_action_shape_invalid")
    raw = canonical.tobytes(order="C")
    if len(raw) != ACTION_BYTE_LENGTH:
        raise ValueError("g1_mgt_hip_action_byte_length_invalid")
    data_hash = array_data_hash(canonical)
    binary_hash = sha256_prefixed(raw)
    if data_hash != binary_hash:
        raise ValueError("g1_mgt_hip_action_hash_contract_invalid")
    return (
        {
            "path": _repo_relative(repo_root, action_out),
            "format": ACTION_FORMAT,
            "dtype": ACTION_DTYPE,
            "shape": [ACTION_COUNT],
            "byte_length": ACTION_BYTE_LENGTH,
            "file_sha256": binary_hash,
            "data_hash": data_hash,
            "persisted": True,
        },
        raw,
    )


def _read_action_artifact(
    payload: dict[str, Any],
    *,
    repo_root: Path,
) -> np.ndarray:
    artifact = payload["hardware_execution"]["action_artifact"]
    path = _resolve(repo_root, Path(artifact["path"])).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("g1_mgt_hip_action_path_outside_repository") from exc
    if not path.is_file():
        raise ValueError("g1_mgt_hip_action_artifact_missing")
    raw = path.read_bytes()
    if len(raw) != artifact["byte_length"] or len(raw) != ACTION_BYTE_LENGTH:
        raise ValueError("g1_mgt_hip_action_artifact_size_mismatch")
    if file_sha256(path) != artifact["file_sha256"]:
        raise ValueError("g1_mgt_hip_action_artifact_file_hash_mismatch")
    action = immutable_array(
        np.frombuffer(raw, dtype=np.dtype(ACTION_DTYPE)),
        dtype=ACTION_DTYPE,
    )
    if action.shape != tuple(artifact["shape"]):
        raise ValueError("g1_mgt_hip_action_artifact_shape_mismatch")
    if array_data_hash(action) != artifact["data_hash"]:
        raise ValueError("g1_mgt_hip_action_artifact_data_hash_mismatch")
    return action


def build_receipt_from_execution(
    *,
    repo_root: Path,
    mgt_path: Path,
    checkpoint_npz: Path,
    out_path: Path,
    action_out: Path,
    reference: HIPCurrentTangentOperatorReference,
    state: np.ndarray,
    direction: np.ndarray,
    metadata: dict[str, Any],
    host_parser_receipt: dict[str, Any],
    execution: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    runtime_output = execution["runtime_output"]
    comparison = _comparison_bundle(reference, runtime_output)
    generic = comparison["generic_comparison"]
    context = comparison["actual_mgt_context"]
    if generic["contract_pass"] is not True:
        raise RuntimeError("g1_mgt_hip_current_tangent_numerical_parity_failed")
    if context["device_order_bitwise_match"] is not True:
        raise RuntimeError("g1_mgt_hip_current_tangent_device_order_mismatch")
    architecture = str(execution["architecture"])
    if architecture != "gfx1030":
        raise RuntimeError("g1_mgt_hip_current_tangent_architecture_invalid")
    target = _target_row(host_parser_receipt, architecture)
    target_binary_identity = bool(
        execution["binary_sha256"] == target["binary_sha256"]
        and execution["binary_byte_length"] == target["binary_byte_length"]
    )
    if not target_binary_identity:
        raise RuntimeError("g1_mgt_hip_current_tangent_binary_identity_failed")
    fixture_summary = summarize_actual_fixture(reference.fixture)
    if fixture_summary != host_parser_receipt["fixture"]:
        raise RuntimeError("g1_mgt_hip_current_tangent_fixture_identity_failed")
    if metadata["free_equation_count"] != ACTION_COUNT:
        raise RuntimeError("g1_mgt_hip_current_tangent_equation_count_invalid")
    action = immutable_array(runtime_output["action_n_per_m"], dtype=ACTION_DTYPE)
    action_manifest, action_bytes = _action_manifest(
        repo_root=repo_root,
        action_out=action_out,
        action=action,
    )
    runtime_metadata = _runtime_metadata(runtime_output)
    if runtime_metadata["schema_version"] != HIP_CURRENT_TANGENT_OUTPUT_VERSION:
        raise RuntimeError("g1_mgt_hip_current_tangent_output_version_invalid")
    normalized_runtime_output = _runtime_with_action(runtime_metadata, action)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "contract_scope": CONTRACT_SCOPE,
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "source_commit_exact_replay_claim": False,
        "source_tree_state": "working_tree_with_uncommitted_goal_changes",
        "input_checksums": input_checksums(
            _input_paths(
                mgt_path=mgt_path,
                checkpoint_npz=checkpoint_npz,
            ),
            repo_root=repo_root,
        ),
        "case_id": CASE_ID,
        "inputs": {
            "mgt_path": _repo_relative(repo_root, mgt_path),
            "mgt_sha256": file_sha256(_resolve(repo_root, mgt_path)),
            "checkpoint_npz": _repo_relative(repo_root, checkpoint_npz),
            "checkpoint_sha256": file_sha256(
                _resolve(repo_root, checkpoint_npz)
            ),
            "state_policy": "full_unit_zero_state_linear_predictor",
            "direction_policy": "normalized_current_right_hand_side",
            "load_factor": 1.0,
            "state_data_hash": array_data_hash(state),
            "direction_data_hash": array_data_hash(direction),
        },
        "fixture": fixture_summary,
        "host_parser_prerequisite": {
            "receipt": str(HOST_PARSER_RECEIPT),
            "receipt_hash": host_parser_receipt["receipt_hash"],
            "contract_pass": host_parser_receipt["contract_pass"],
            "fixture_hash": host_parser_receipt["fixture"]["fixture_hash"],
            "architecture": architecture,
            "binary_sha256": target["binary_sha256"],
            "binary_byte_length": target["binary_byte_length"],
            "target_binary_identity_pass": target_binary_identity,
        },
        "hardware_execution": {
            "actual_hardware": True,
            "backend": "amd_rocm_hip",
            "device_name": runtime_output["device_name"],
            "gcn_arch_name": runtime_output["gcn_arch_name"],
            "compiler": execution["compiler"],
            "binary_sha256": execution["binary_sha256"],
            "binary_byte_length": execution["binary_byte_length"],
            "runtime_metadata": runtime_metadata,
            "runtime_output_hash": canonical_hash(normalized_runtime_output),
            "action_artifact": action_manifest,
        },
        "comparison": comparison,
        "claims": {
            "actual_mgt_fixture_constructed": True,
            "actual_mgt_current_tangent_action_executed": True,
            "actual_hardware_execution": True,
            "local_gfx1030_hardware_execution": True,
            "deterministic_free_row_schedule_executed": True,
            "single_kernel_invocation": True,
            "mid_action_d2h_transfer_count_zero": True,
            "cpu_hip_numerical_parity": True,
            "device_order_bitwise_parity": True,
            "independent_gfx1100_hardware_execution": False,
            "device_resident_current_tangent_fgmres": False,
            "production_preconditioner_integration": False,
            "performance": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "device_resident_current_tangent_fgmres_not_integrated",
            "production_preconditioner_not_integrated_on_device",
            "independent_gfx1100_hardware_receipt_not_attached",
            "same_clean_source_commit_cross_device_not_verified",
            "signed_hardware_receipt_not_attached",
            "model_size_performance_sweep_not_executed",
            "g1_full_building_closure_not_established",
        ],
        "artifacts": {
            "receipt": _repo_relative(repo_root, out_path),
            "action_vector": _repo_relative(repo_root, action_out),
            "schema": str(SCHEMA_PATH),
            "runner": (
                "scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py"
            ),
            "host_parser_receipt": str(HOST_PARSER_RECEIPT),
            "hip_source": (
                "implementation/phase1/hip_kernels/"
                "engine_v2_current_tangent_operator.hip.cpp"
            ),
        },
        "claim_boundary": (
            "This receipt proves one actual 70,560-equation MGT "
            "current-tangent action for one declared state, load factor, and "
            "normalized direction on a local AMD Radeon RX 6900 XT gfx1030. "
            "The action used one kernel, no mid-action device-to-host "
            "transfer, and matches both the canonical CPU tolerance and the "
            "device-order CPU action bitwise. It does not establish an "
            "independent gfx1100 run, a clean exact-source cross-device "
            "receipt, device-resident FGMRES or preconditioning, a "
            "performance sweep, production readiness, or G1 closure."
        ),
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return payload, action_bytes


def validate_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool = False,
    require_action_artifact: bool = False,
    recompute_reference: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("g1_mgt_hip_hardware_receipt_hash_mismatch")
    host_receipt = _load_host_parser_receipt(
        repo_root=repo_root,
        require_current_sources=require_current_sources,
    )
    prerequisite = payload["host_parser_prerequisite"]
    target = _target_row(host_receipt, prerequisite["architecture"])
    if prerequisite["receipt_hash"] != host_receipt["receipt_hash"]:
        raise ValueError("g1_mgt_hip_host_parser_receipt_hash_mismatch")
    if prerequisite["fixture_hash"] != host_receipt["fixture"]["fixture_hash"]:
        raise ValueError("g1_mgt_hip_host_parser_fixture_hash_mismatch")
    if (
        prerequisite["binary_sha256"] != target["binary_sha256"]
        or prerequisite["binary_byte_length"] != target["binary_byte_length"]
    ):
        raise ValueError("g1_mgt_hip_host_parser_binary_mismatch")
    hardware = payload["hardware_execution"]
    if (
        hardware["binary_sha256"] != prerequisite["binary_sha256"]
        or hardware["binary_byte_length"]
        != prerequisite["binary_byte_length"]
    ):
        raise ValueError("g1_mgt_hip_hardware_binary_mismatch")
    if require_current_sources:
        expected_checksums = input_checksums(
            _input_paths(
                mgt_path=Path(payload["inputs"]["mgt_path"]),
                checkpoint_npz=Path(payload["inputs"]["checkpoint_npz"]),
            ),
            repo_root=repo_root,
        )
        if payload["input_checksums"] != expected_checksums:
            raise ValueError("g1_mgt_hip_hardware_source_checksums_stale")
        if payload["source_commit_sha"] != git_head(repo_root):
            raise ValueError("g1_mgt_hip_hardware_base_commit_mismatch")
    action: np.ndarray | None = None
    if require_action_artifact or recompute_reference:
        action = _read_action_artifact(payload, repo_root=repo_root)
    if recompute_reference:
        if action is None:
            raise AssertionError("action artifact must be loaded")
        fixture, state, direction, metadata = build_actual_fixture(
            mgt_path=_resolve(repo_root, Path(payload["inputs"]["mgt_path"])),
            checkpoint_npz=_resolve(
                repo_root,
                Path(payload["inputs"]["checkpoint_npz"]),
            ),
        )
        reference = create_hip_current_tangent_operator_reference(fixture)
        if summarize_actual_fixture(fixture) != payload["fixture"]:
            raise ValueError("g1_mgt_hip_hardware_fixture_mismatch")
        if array_data_hash(state) != payload["inputs"]["state_data_hash"]:
            raise ValueError("g1_mgt_hip_hardware_state_hash_mismatch")
        if array_data_hash(direction) != payload["inputs"]["direction_data_hash"]:
            raise ValueError("g1_mgt_hip_hardware_direction_hash_mismatch")
        if metadata["free_equation_count"] != ACTION_COUNT:
            raise ValueError("g1_mgt_hip_hardware_metadata_mismatch")
        runtime_output = _runtime_with_action(
            hardware["runtime_metadata"],
            action,
        )
        if canonical_hash(runtime_output) != hardware["runtime_output_hash"]:
            raise ValueError("g1_mgt_hip_hardware_runtime_hash_mismatch")
        expected_comparison = _comparison_bundle(reference, runtime_output)
        if expected_comparison != payload["comparison"]:
            raise ValueError("g1_mgt_hip_hardware_comparison_mismatch")
    return payload


def run_hardware_parity(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    out_path: Path = DEFAULT_OUT,
    action_out: Path = DEFAULT_ACTION_OUT,
    hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
    rocm_path: str = "/opt/rocm-6.0.2",
    device_lib_path: str = "",
    architecture: str = "gfx1030",
    runtime_timeout: float = 120.0,
) -> tuple[dict[str, Any], bytes]:
    repo_root = repo_root.resolve()
    resolved_mgt = _resolve(repo_root, mgt_path)
    resolved_checkpoint = _resolve(repo_root, checkpoint_npz)
    host_receipt = _load_host_parser_receipt(
        repo_root=repo_root,
        require_current_sources=True,
    )
    fixture, state, direction, metadata = build_actual_fixture(
        mgt_path=resolved_mgt,
        checkpoint_npz=resolved_checkpoint,
    )
    reference = create_hip_current_tangent_operator_reference(fixture)
    execution = compile_and_run_hardware_fixture(
        fixture,
        repo_root=repo_root,
        hipcc=hipcc,
        rocm_path=rocm_path,
        device_lib_path=device_lib_path,
        architecture=architecture,
        runtime_timeout=runtime_timeout,
    )
    return build_receipt_from_execution(
        repo_root=repo_root,
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint_npz,
        out_path=out_path,
        action_out=action_out,
        reference=reference,
        state=state,
        direction=direction,
        metadata=metadata,
        host_parser_receipt=host_receipt,
        execution=execution,
    )


def write_receipt(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    out_path = Path(kwargs.get("out_path", DEFAULT_OUT))
    action_out = Path(kwargs.get("action_out", DEFAULT_ACTION_OUT))
    payload, action_bytes = run_hardware_parity(**kwargs)
    action_target = _resolve(repo_root, action_out)
    receipt_target = _resolve(repo_root, out_path)
    action_target.parent.mkdir(parents=True, exist_ok=True)
    receipt_target.parent.mkdir(parents=True, exist_ok=True)
    action_target.write_bytes(action_bytes)
    receipt_target.write_text(_json_text(payload), encoding="utf-8")
    return validate_receipt(
        _read_json(receipt_target),
        repo_root=repo_root,
        require_current_sources=True,
        require_action_artifact=True,
    )


def check_receipt(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    repo_root = repo_root.resolve()
    target = _resolve(repo_root, out_path)
    if not target.is_file():
        return False, "g1_mgt_hip_hardware_parity_receipt_missing"
    try:
        validate_receipt(
            _read_json(target),
            repo_root=repo_root,
            require_current_sources=True,
            require_action_artifact=True,
            recompute_reference=True,
        )
    except Exception as exc:
        return False, str(exc)
    return True, "g1_mgt_hip_hardware_parity_receipt_consistent"


def check_source_only(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    """Check schema, source identity, and action bytes without CPU replay."""

    repo_root = repo_root.resolve()
    target = _resolve(repo_root, out_path)
    if not target.is_file():
        return False, "g1_mgt_hip_hardware_parity_receipt_missing"
    try:
        validate_receipt(
            _read_json(target),
            repo_root=repo_root,
            require_current_sources=True,
            require_action_artifact=True,
        )
    except Exception as exc:
        return False, str(exc)
    return True, "g1_mgt_hip_hardware_parity_sources_consistent"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--action-out", type=Path, default=DEFAULT_ACTION_OUT)
    parser.add_argument("--hipcc", default="/opt/rocm-6.0.2/bin/hipcc")
    parser.add_argument("--rocm-path", default="/opt/rocm-6.0.2")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--architecture", default="gfx1030")
    parser.add_argument("--runtime-timeout", type=float, default=120.0)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-source-only", action="store_true")
    args = parser.parse_args(argv)
    if args.check and args.check_source_only:
        parser.error("--check and --check-source-only are mutually exclusive")
    if args.check_source_only:
        passed, reason = check_source_only(
            repo_root=args.repo_root,
            out_path=args.out,
        )
        print(reason)
        return 0 if passed else 1
    if args.check:
        passed, reason = check_receipt(
            repo_root=args.repo_root,
            out_path=args.out,
        )
        print(reason)
        return 0 if passed else 1
    payload = write_receipt(
        repo_root=args.repo_root,
        mgt_path=args.mgt,
        checkpoint_npz=args.checkpoint,
        out_path=args.out,
        action_out=args.action_out,
        hipcc=args.hipcc,
        rocm_path=args.rocm_path,
        device_lib_path=args.device_lib_path,
        architecture=args.architecture,
        runtime_timeout=args.runtime_timeout,
    )
    comparison = payload["comparison"]["generic_comparison"]
    print(
        f"{payload['status']} | actual_mgt_equations="
        f"{payload['fixture']['dimensions']['equation_count']} | "
        f"device={payload['hardware_execution']['device_name']} | "
        f"architecture={payload['hardware_execution']['gcn_arch_name']} | "
        f"canonical_max_abs_error_n_per_m="
        f"{comparison['canonical_cpu_max_abs_error_n_per_m']} | "
        "device_order_bitwise_match=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
