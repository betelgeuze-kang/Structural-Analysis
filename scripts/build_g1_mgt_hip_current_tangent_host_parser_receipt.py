#!/usr/bin/env python3
"""Build the actual-MGT HIP current-tangent host-parser receipt."""

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

from g1_mgt_load_coupled_arc_length_adapter import (  # noqa: E402
    build_real_mgt_load_coupled_arc_length_problem,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)
from run_engine_v2_hip_current_tangent_operator import (  # noqa: E402
    DEFAULT_COMPILE_OUT as SYNTHETIC_COMPILE_RECEIPT,
    compile_and_validate_host_fixture_for_targets,
    validate_compile_receipt,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
    HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
    HIP_CURRENT_TANGENT_FIXTURE_VERSION,
    HIP_CURRENT_TANGENT_PARITY_PROFILE,
    HIP_CURRENT_TANGENT_SCHEDULE_PROFILE,
    HIPCurrentTangentOperatorFixture,
    create_hip_current_tangent_operator_fixture,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path(
    "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt"
)
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_relaxed_checkpoints/"
    "accepted_load_0p656.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_hip_current_tangent_host_parser_receipt.json"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_hip_current_tangent_host_parser_receipt_v1.schema.json"
)
SCHEMA_VERSION = "g1-mgt-hip-current-tangent-host-parser-receipt.v1"
CASE_ID = "g1_actual_mgt_hip_current_tangent_host_parser"
LOAD_FACTOR = 1.0


def _json_text(payload: dict[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _label(repo_root: Path, path: Path) -> str:
    absolute = _resolve(repo_root, path).resolve()
    try:
        return absolute.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at", "receipt_hash"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _receipt_hash(payload: dict[str, Any]) -> str:
    without_hash = dict(payload)
    without_hash.pop("receipt_hash", None)
    return canonical_hash(without_hash)


def _input_paths(*, mgt_path: Path, checkpoint_npz: Path) -> list[Path]:
    return [
        mgt_path,
        checkpoint_npz,
        SYNTHETIC_COMPILE_RECEIPT,
        Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
        Path(
            "implementation/phase1/hip_kernels/"
            "engine_v2_current_tangent_operator.hip.cpp"
        ),
        Path("src/structural_analysis/engine_v2/contracts/current_tangent_operator.py"),
        Path(
            "src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py"
        ),
        Path("scripts/run_engine_v2_hip_current_tangent_operator.py"),
        Path("scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py"),
        SCHEMA_PATH,
        Path("tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py"),
    ]


def build_actual_fixture(
    *,
    mgt_path: Path,
    checkpoint_npz: Path,
) -> tuple[
    HIPCurrentTangentOperatorFixture,
    np.ndarray,
    np.ndarray,
    dict[str, Any],
]:
    historical_problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=mgt_path,
        roundtrip_npz=None,
        checkpoint_npz=checkpoint_npz,
        apply_state_updated_frame_axial_geometry=True,
    )
    problem = historical_problem.zero_state_problem()
    state = np.ascontiguousarray(
        problem.full_unit_zero_state_predictor_free_m(),
        dtype=np.float64,
    )
    right_hand_side = np.ascontiguousarray(
        -problem.residual_kn(state, LOAD_FACTOR),
        dtype=np.float64,
    )
    right_hand_side_inf = float(np.linalg.norm(right_hand_side, ord=np.inf))
    if not np.isfinite(right_hand_side_inf) or right_hand_side_inf <= 0.0:
        raise ValueError("actual_mgt_current_tangent_right_hand_side_invalid")
    direction = np.ascontiguousarray(
        right_hand_side / right_hand_side_inf,
        dtype=np.float64,
    )
    operator = problem.current_tangent_operator
    if operator is None:
        raise ValueError("actual_mgt_current_tangent_operator_missing")
    fixture = create_hip_current_tangent_operator_fixture(
        operator,
        free_displacements_m=state,
        load_factor=LOAD_FACTOR,
        free_direction_m=direction,
    )
    return fixture, state, direction, metadata


def summarize_actual_fixture(
    fixture: HIPCurrentTangentOperatorFixture,
) -> dict[str, Any]:
    manifest = fixture.to_manifest()
    return {
        "schema_version": manifest["schema_version"],
        "fixture_hash": manifest["fixture_hash"],
        "parity_profile": manifest["parity_profile"],
        "schedule_profile": manifest["schedule_profile"],
        "execution_profile": manifest["execution_profile"],
        "accumulation_profile": manifest["accumulation_profile"],
        "operator_contract_hash": manifest["operator_contract_hash"],
        "schedule_contract_hash": manifest["schedule_contract_hash"],
        "execution_contract_hash": manifest["execution_contract_hash"],
        "load_factor": manifest["load_factor"],
        "dimensions": manifest["dimensions"],
        "expected_kernel_invocation_count": manifest[
            "expected_kernel_invocation_count"
        ],
        "binary_profile": manifest["binary_profile"],
        "array_count": len(manifest["arrays"]),
        "fixture_byte_length": manifest["fixture_byte_length"],
        "fixture_binary_ephemeral": True,
        "fixture_binary_persisted": False,
    }


def build_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    out_path: Path = DEFAULT_OUT,
    hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
    rocm_path: str = "/opt/rocm-6.0.2",
    device_lib_path: str = "",
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_mgt = _resolve(repo_root, mgt_path)
    resolved_checkpoint = _resolve(repo_root, checkpoint_npz)
    synthetic_receipt = validate_compile_receipt(
        _read_json(repo_root / SYNTHETIC_COMPILE_RECEIPT),
        repo_root=repo_root,
        require_current_sources=True,
    )
    fixture, state, direction, metadata = build_actual_fixture(
        mgt_path=resolved_mgt,
        checkpoint_npz=resolved_checkpoint,
    )
    fixture_summary = summarize_actual_fixture(fixture)
    compiled = compile_and_validate_host_fixture_for_targets(
        fixture,
        repo_root=repo_root,
        hipcc=hipcc,
        rocm_path=rocm_path,
        device_lib_path=device_lib_path,
    )
    targets = compiled["targets"]
    synthetic_targets = {
        row["architecture"]: row for row in synthetic_receipt["targets"]
    }
    target_binary_identity_pass = bool(
        [row["architecture"] for row in targets] == ["gfx1030", "gfx1100"]
        and all(
            row["binary_sha256"]
            == synthetic_targets[row["architecture"]]["binary_sha256"]
            and row["binary_byte_length"]
            == synthetic_targets[row["architecture"]]["binary_byte_length"]
            for row in targets
        )
    )
    actual_host_parser_pass = bool(
        len(targets) == 2
        and all(
            row["target_compile"] is True
            and row["host_fixture_parser_execution"] is True
            and row["host_fixture_validation"]["contract_pass"] is True
            and row["host_fixture_validation"]["fixture_hash"]
            == fixture_summary["fixture_hash"]
            and row["host_fixture_validation"]["equation_count"] == 70_560
            and row["host_fixture_validation"]["fixture_byte_length"] == 36_123_072
            and row["host_fixture_validation"]["actual_hardware_execution"] is False
            and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
            for row in targets
        )
    )
    fixture_contract_pass = bool(
        fixture_summary["schema_version"] == HIP_CURRENT_TANGENT_FIXTURE_VERSION
        and fixture_summary["parity_profile"] == HIP_CURRENT_TANGENT_PARITY_PROFILE
        and fixture_summary["schedule_profile"] == HIP_CURRENT_TANGENT_SCHEDULE_PROFILE
        and fixture_summary["execution_profile"]
        == HIP_CURRENT_TANGENT_EXECUTION_PROFILE
        and fixture_summary["accumulation_profile"]
        == HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE
        and fixture_summary["dimensions"]
        == {
            "equation_count": 70_560,
            "global_dof_count": 78_282,
            "reference_nnz": 1_262_462,
            "frame_element_count": 5_572,
            "geometry_element_count": 5_572,
            "frame_incidence_count": 61_494,
            "geometry_incidence_count": 61_494,
        }
        and fixture_summary["array_count"] == 21
        and fixture_summary["fixture_byte_length"] == 36_123_072
        and fixture_summary["expected_kernel_invocation_count"] == 1
    )
    contract_pass = bool(
        fixture_contract_pass
        and actual_host_parser_pass
        and target_binary_identity_pass
        and metadata["free_equation_count"] == 70_560
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "contract_scope": (
            "actual_mgt_dual_target_compile_and_host_fixture_parser_only"
        ),
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
            "mgt_path": _label(repo_root, mgt_path),
            "mgt_sha256": file_sha256(resolved_mgt),
            "checkpoint_npz": _label(repo_root, checkpoint_npz),
            "checkpoint_sha256": file_sha256(resolved_checkpoint),
            "state_policy": "full_unit_zero_state_linear_predictor",
            "direction_policy": "normalized_current_right_hand_side",
            "load_factor": LOAD_FACTOR,
            "state_data_hash": array_data_hash(state),
            "direction_data_hash": array_data_hash(direction),
        },
        "fixture": fixture_summary,
        "synthetic_compile_receipt": {
            "receipt": str(SYNTHETIC_COMPILE_RECEIPT),
            "receipt_hash": synthetic_receipt["receipt_hash"],
            "fixture_equation_count": synthetic_receipt["fixture"]["dimensions"][
                "equation_count"
            ],
            "target_binary_identity_pass": target_binary_identity_pass,
        },
        "compiler": compiled["compiler"],
        "targets": targets,
        "claims": {
            "actual_mgt_fixture_constructed": fixture_contract_pass,
            "actual_mgt_dual_target_host_fixture_parser_execution": (
                actual_host_parser_pass
            ),
            "actual_mgt_host_parser_hip_runtime_api_calls_zero": (
                actual_host_parser_pass
            ),
            "synthetic_and_actual_parser_binary_identity": (
                target_binary_identity_pass
            ),
            "actual_hardware_execution": False,
            "current_tangent_action_executed": False,
            "cpu_hip_numerical_parity": False,
            "device_resident_current_tangent_fgmres": False,
            "performance": False,
            "g1_full_building_closure": False,
        },
        "blockers_remaining": [
            "actual_hardware_current_tangent_action_not_executed",
            "actual_mgt_current_tangent_cpu_hip_parity_not_verified",
            "device_resident_current_tangent_fgmres_not_integrated",
            "independent_gfx1100_hardware_receipt_not_attached",
            "same_clean_source_commit_cross_device_not_verified",
            "signed_hardware_receipt_not_attached",
            "model_size_performance_sweep_not_executed",
            "g1_full_building_closure_not_established",
        ],
        "artifacts": {
            "receipt": _label(repo_root, out_path),
            "schema": str(SCHEMA_PATH),
            "builder": (
                "scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py"
            ),
            "hip_source": (
                "implementation/phase1/hip_kernels/"
                "engine_v2_current_tangent_operator.hip.cpp"
            ),
            "hip_fixture_module": (
                "src/structural_analysis/engine_v2_backends/"
                "hip_current_tangent_operator.py"
            ),
            "synthetic_compile_receipt": str(SYNTHETIC_COMPILE_RECEIPT),
        },
        "claim_boundary": (
            "This receipt proves that warning-free gfx1030 and gfx1100 "
            "binaries with the same hashes as the synthetic compile receipt "
            "parse the canonical 36,123,072-byte actual-MGT current-tangent "
            "fixture through their host-only path with zero HIP runtime API "
            "calls. It does not open a device, launch a kernel, execute a "
            "current-tangent action, establish CPU/HIP numerical parity, "
            "integrate device-resident FGMRES or preconditioning, measure "
            "performance, or close G1."
        ),
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return validate_receipt(payload, repo_root=repo_root)


def validate_receipt(
    payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    require_current_sources: bool = False,
) -> dict[str, Any]:
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("g1_mgt_hip_current_tangent_receipt_hash_mismatch")
    if [row["architecture"] for row in payload["targets"]] != [
        "gfx1030",
        "gfx1100",
    ]:
        raise ValueError("g1_mgt_hip_current_tangent_target_order_invalid")
    if require_current_sources:
        expected_checksums = input_checksums(
            _input_paths(
                mgt_path=Path(payload["inputs"]["mgt_path"]),
                checkpoint_npz=Path(payload["inputs"]["checkpoint_npz"]),
            ),
            repo_root=repo_root,
        )
        if payload["input_checksums"] != expected_checksums:
            raise ValueError("g1_mgt_hip_current_tangent_source_checksums_stale")
        if payload["source_commit_exact_replay_claim"] is True and payload[
            "source_commit_sha"
        ] != git_head(repo_root):
            raise ValueError("g1_mgt_hip_current_tangent_base_commit_mismatch")
    return payload


def check_receipt(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    out_path: Path = DEFAULT_OUT,
    hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
    rocm_path: str = "/opt/rocm-6.0.2",
    device_lib_path: str = "",
) -> tuple[bool, str]:
    target = _resolve(repo_root, out_path)
    if not target.is_file():
        return False, "g1_mgt_hip_current_tangent_host_parser_receipt_missing"
    try:
        existing = validate_receipt(
            _read_json(target),
            repo_root=repo_root,
            require_current_sources=True,
        )
        expected = build_receipt(
            repo_root=repo_root,
            mgt_path=mgt_path,
            checkpoint_npz=checkpoint_npz,
            out_path=out_path,
            hipcc=hipcc,
            rocm_path=rocm_path,
            device_lib_path=device_lib_path,
        )
    except Exception as exc:
        return False, str(exc)
    expected_for_comparison = dict(expected)
    if (
        existing["source_commit_exact_replay_claim"] is False
        and expected["source_commit_exact_replay_claim"] is False
    ):
        # For a non-exact replay receipt, current input checksums are the
        # authority. The historical commit label remains informational and
        # must not force downstream hardware receipts to be rewritten.
        expected_for_comparison["source_commit_sha"] = existing["source_commit_sha"]
    if _strip_volatile(existing) != _strip_volatile(expected_for_comparison):
        return False, "g1_mgt_hip_current_tangent_host_parser_mismatch"
    return True, "g1_mgt_hip_current_tangent_host_parser_consistent"


def check_receipt_source_only(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    target = _resolve(repo_root, out_path)
    if not target.is_file():
        return False, "g1_mgt_hip_current_tangent_host_parser_receipt_missing"
    try:
        validate_receipt(
            _read_json(target),
            repo_root=repo_root,
            require_current_sources=True,
        )
    except Exception as exc:
        return False, str(exc)
    return True, "g1_mgt_hip_current_tangent_host_parser_sources_consistent"


def write_receipt(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    out_path = Path(kwargs.get("out_path", DEFAULT_OUT))
    payload = build_receipt(**kwargs)
    target = _resolve(repo_root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hipcc", default="/opt/rocm-6.0.2/bin/hipcc")
    parser.add_argument("--rocm-path", default="/opt/rocm-6.0.2")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-source-only", action="store_true")
    args = parser.parse_args(argv)
    if args.check and args.check_source_only:
        parser.error("--check and --check-source-only are mutually exclusive")
    kwargs = {
        "repo_root": args.repo_root,
        "mgt_path": args.mgt,
        "checkpoint_npz": args.checkpoint,
        "out_path": args.out,
        "hipcc": args.hipcc,
        "rocm_path": args.rocm_path,
        "device_lib_path": args.device_lib_path,
    }
    if args.check:
        passed, reason = check_receipt(**kwargs)
        print(reason)
        return 0 if passed else 1
    if args.check_source_only:
        passed, reason = check_receipt_source_only(
            repo_root=args.repo_root,
            out_path=args.out,
        )
        print(reason)
        return 0 if passed else 1
    payload = write_receipt(**kwargs)
    print(
        f"{payload['status']} | actual_mgt_equations="
        f"{payload['fixture']['dimensions']['equation_count']} | "
        f"fixture_bytes={payload['fixture']['fixture_byte_length']} | "
        "host_parser_targets=2 | actual_hardware=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
