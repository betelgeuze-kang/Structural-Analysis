#!/usr/bin/env python3
"""Run accepted-state HIP JVP on the actual HIP preconditioner output."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PHASE1_ROOT = ROOT / "implementation" / "phase1"
for candidate in (SCRIPT_DIR, SRC_ROOT, PHASE1_ROOT):
    text = str(candidate)
    while text in sys.path:
        sys.path.remove(text)
    sys.path.insert(0, text)

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
    compile_and_run_hardware_fixture,
)
from run_g1_mgt_accepted_state_hip_sparse_lu_parity import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    DEFAULT_MGT,
    DEFAULT_OUT as PRECONDITIONER_RECEIPT,
    DEFAULT_SOLUTION_OUT as PRECONDITIONER_SOLUTION,
    validate_receipt as validate_preconditioner_receipt,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
    immutable_array,
    sha256_prefixed,
)
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    compare_hip_current_tangent_operator_output,
    create_hip_current_tangent_operator_fixture,
    create_hip_current_tangent_operator_reference,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_accepted_state_preconditioned_jvp_parity_receipt.json"
DEFAULT_ACTION_OUT = PRODUCTIZATION / "g1_mgt_accepted_state_preconditioned_jvp_action.f64le"
SCHEMA_PATH = Path("src/structural_analysis/schemas/g1_mgt_accepted_state_preconditioned_jvp_parity_v1.schema.json")
SCHEMA_VERSION = "g1-mgt-accepted-state-preconditioned-jvp-parity-receipt.v1"
EQUATION_COUNT = 70_560
ACTION_BYTES = EQUATION_COUNT * 8
SOURCE_PATHS = (
    DEFAULT_MGT,
    DEFAULT_CHECKPOINT,
    PRECONDITIONER_RECEIPT,
    PRECONDITIONER_SOLUTION,
    Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
    Path("implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp"),
    Path("src/structural_analysis/engine_v2/contracts/current_tangent_operator.py"),
    Path("src/structural_analysis/engine_v2_backends/hip_current_tangent_operator.py"),
    Path("scripts/run_engine_v2_hip_current_tangent_operator.py"),
    Path("scripts/run_g1_mgt_accepted_state_hip_sparse_lu_parity.py"),
    Path("scripts/run_g1_mgt_accepted_state_preconditioned_jvp_parity.py"),
    SCHEMA_PATH,
    Path("tests/test_run_g1_mgt_accepted_state_preconditioned_jvp_parity.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative(root: Path, path: Path) -> str:
    return _resolve(root, path).resolve().relative_to(root.resolve()).as_posix()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("receipt_must_be_object")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash({key: value for key, value in payload.items() if key != "receipt_hash"})


def _clean(root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *(_relative(root, path) for path in SOURCE_PATHS)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


def _solution_from_preconditioner(payload: dict[str, Any], *, root: Path) -> np.ndarray:
    artifact = payload["hardware_execution"]["solution_artifact"]
    path = _resolve(root, Path(artifact["path"]))
    raw = path.read_bytes()
    if len(raw) != ACTION_BYTES or file_sha256(path) != artifact["file_sha256"]:
        raise ValueError("preconditioner_solution_artifact_mismatch")
    direction = immutable_array(np.frombuffer(raw, dtype="<f8"), dtype="<f8")
    if direction.shape != (EQUATION_COUNT,) or array_data_hash(direction) != artifact["data_hash"]:
        raise ValueError("preconditioner_solution_vector_mismatch")
    return direction


def build_fixture(*, root: Path, mgt_path: Path, checkpoint: Path) -> tuple[Any, Any, np.ndarray, np.ndarray, dict[str, Any]]:
    prerequisite = validate_preconditioner_receipt(
        _read(root / PRECONDITIONER_RECEIPT),
        repo_root=root,
        require_current_sources=True,
        require_solution_artifact=True,
    )
    direction = _solution_from_preconditioner(prerequisite, root=root)
    problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=_resolve(root, mgt_path),
        roundtrip_npz=None,
        checkpoint_npz=_resolve(root, checkpoint),
        apply_state_updated_frame_axial_geometry=True,
        source_commit_sha=git_head(root),
    )
    state = np.ascontiguousarray(problem.initial_free_displacements_m(), dtype="<f8")
    if state.shape != (EQUATION_COUNT,) or problem.initial_load_factor() != 1.0:
        raise ValueError("accepted_state_contract_invalid")
    operator = problem.current_tangent_operator
    if operator is None:
        raise ValueError("accepted_state_current_tangent_operator_missing")
    fixture = create_hip_current_tangent_operator_fixture(
        operator,
        free_displacements_m=state,
        load_factor=1.0,
        free_direction_m=direction,
    )
    return fixture, create_hip_current_tangent_operator_reference(fixture), state, direction, {"adapter": metadata, "prerequisite": prerequisite}


def _artifact(root: Path, path: Path, action: np.ndarray) -> tuple[dict[str, Any], bytes]:
    vector = immutable_array(action, dtype="<f8")
    if vector.shape != (EQUATION_COUNT,):
        raise ValueError("accepted_state_jvp_action_shape_invalid")
    raw = vector.tobytes(order="C")
    digest = sha256_prefixed(raw)
    return ({
        "path": _relative(root, path), "format": "canonical_little_endian_float64_vector.v1",
        "dtype": "<f8", "shape": [EQUATION_COUNT], "byte_length": len(raw),
        "file_sha256": digest, "data_hash": array_data_hash(vector), "persisted": True,
    }, raw)


def run(
    *, root: Path = ROOT, mgt_path: Path = DEFAULT_MGT, checkpoint: Path = DEFAULT_CHECKPOINT,
    out_path: Path = DEFAULT_OUT, action_out: Path = DEFAULT_ACTION_OUT,
    hipcc: str = "/opt/rocm-6.0.2/bin/hipcc", rocm_path: str = "/opt/rocm-6.0.2",
    device_lib_path: str = "", runtime_timeout: float = 180.0,
) -> tuple[dict[str, Any], bytes]:
    root = root.resolve()
    if not _clean(root):
        raise RuntimeError("accepted_state_preconditioned_jvp_requires_clean_source_paths")
    fixture, reference, state, direction, context = build_fixture(root=root, mgt_path=mgt_path, checkpoint=checkpoint)
    execution = compile_and_run_hardware_fixture(
        fixture, repo_root=root, hipcc=hipcc, rocm_path=rocm_path,
        device_lib_path=device_lib_path, architecture="gfx1030", runtime_timeout=runtime_timeout,
    )
    runtime = execution["runtime_output"]
    comparison = compare_hip_current_tangent_operator_output(reference, runtime)
    if comparison["contract_pass"] is not True:
        raise RuntimeError("accepted_state_preconditioned_jvp_parity_failed")
    action_manifest, action_bytes = _artifact(root, action_out, np.asarray(runtime["action_n_per_m"], dtype="<f8"))
    runtime_metadata = dict(runtime)
    runtime_metadata.pop("action_n_per_m")
    prerequisite = context["prerequisite"]
    payload = {
        "schema_version": SCHEMA_VERSION, "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "contract_pass": True,
        "contract_scope": "actual_mgt_full_load_accepted_state_preconditioned_jvp_local_gfx1030",
        "source": {"repository_commit_sha": git_head(root), "source_paths_clean_at_execution": _clean(root), "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root), "engine_version": engine_version(root)},
        "accepted_state": {
            "checkpoint": _relative(root, checkpoint), "checkpoint_sha256": file_sha256(_resolve(root, checkpoint)),
            "load_factor": 1.0, "equation_count": EQUATION_COUNT, "state_data_hash": array_data_hash(state),
            "operator_contract_hash": fixture.operator.contract_hash, "fixture_hash": fixture.fixture_hash,
        },
        "preconditioned_direction": {
            "source_receipt": PRECONDITIONER_RECEIPT.as_posix(), "source_receipt_hash": prerequisite["receipt_hash"],
            "source_solution_artifact": PRECONDITIONER_SOLUTION.as_posix(), "direction_data_hash": array_data_hash(direction),
            "direction_inf_m": float(np.linalg.norm(direction, ord=np.inf)),
            "bridge_policy": "persisted_final_d2h_artifact_then_next_process_h2d",
        },
        "hardware_execution": {
            "actual_hardware": True, "backend": "amd_rocm_hip", "device_name": runtime["device_name"],
            "gcn_arch_name": runtime["gcn_arch_name"], "compiler": execution["compiler"],
            "binary_sha256": execution["binary_sha256"], "binary_byte_length": execution["binary_byte_length"],
            "runtime_metadata": runtime_metadata, "runtime_output_hash": canonical_hash(runtime), "action_artifact": action_manifest,
        },
        "comparison": comparison,
        "claims": {
            "actual_mgt_full_load_accepted_state": True, "actual_preconditioner_output_consumed": True,
            "actual_accepted_state_current_tangent_jvp": True, "mathematical_right_preconditioned_jvp_composition": True,
            "cpu_hip_numerical_parity": True, "single_device_lifecycle": False,
            "mid_composition_d2h_zero": False, "production_fgmres": False, "independent_gfx1100": False, "g1_closure": False,
        },
        "blockers_remaining": [
            "preconditioner_and_current_tangent_execute_in_separate_processes",
            "persisted_d2h_h2d_bridge_between_preconditioner_and_jvp",
            "arnoldi_recurrence_not_connected_to_actual_mgt_operator_and_factor",
            "independent_gfx1100_run_not_available",
            "full_device_newton_line_search_material_checkpoint_lifecycle_not_established",
        ],
        "artifacts": {"receipt": _relative(root, out_path), "action_vector": _relative(root, action_out), "schema": SCHEMA_PATH.as_posix(), "runner": "scripts/run_g1_mgt_accepted_state_preconditioned_jvp_parity.py"},
        "claim_boundary": (
            "This receipt composes two actual-MGT mathematical operations at the same accepted load-scale 1.0 state: the persisted local gfx1030 sparse-LU preconditioner output is consumed as the direction of an actual 70,560-equation current-tangent HIP JVP, and that JVP passes CPU/HIP parity. The composition deliberately uses a final D2H artifact from the preconditioner process followed by H2D in the JVP process. It therefore does not establish one persistent device lifecycle, zero transfer between preconditioner and JVP, a production Arnoldi/FGMRES recurrence, independent gfx1100 execution, or G1 closure."
        ),
    }
    payload["receipt_hash"] = _hash(payload)
    validate(payload, root=root, current=True)
    return payload, action_bytes


def validate(payload: dict[str, Any], *, root: Path = ROOT, current: bool = False, artifact: bool = False) -> dict[str, Any]:
    schema = _read(root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload):
        raise ValueError("accepted_state_preconditioned_jvp_receipt_hash_mismatch")
    if current and payload["source"]["input_checksums"] != input_checksums(SOURCE_PATHS, repo_root=root):
        raise ValueError("accepted_state_preconditioned_jvp_sources_stale")
    if artifact:
        item = payload["hardware_execution"]["action_artifact"]
        path = _resolve(root, Path(item["path"]))
        if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]:
            raise ValueError("accepted_state_preconditioned_jvp_action_artifact_mismatch")
    return payload


def write(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs.get("root", ROOT)).resolve(); out = Path(kwargs.get("out_path", DEFAULT_OUT)); action = Path(kwargs.get("action_out", DEFAULT_ACTION_OUT))
    payload, raw = run(**kwargs)
    _resolve(root, action).write_bytes(raw); _resolve(root, out).write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return validate(payload, root=root, current=True, artifact=True)


def check(*, root: Path = ROOT, out_path: Path = DEFAULT_OUT) -> tuple[bool, str]:
    path = _resolve(root, out_path)
    if not path.is_file(): return False, "g1_mgt_accepted_state_preconditioned_jvp_receipt_missing"
    try: validate(_read(path), root=root, current=True, artifact=True)
    except Exception as exc: return False, f"g1_mgt_accepted_state_preconditioned_jvp_receipt_invalid:{exc}"
    return True, "g1_mgt_accepted_state_preconditioned_jvp_receipt_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--out", type=Path, default=DEFAULT_OUT); parser.add_argument("--action-out", type=Path, default=DEFAULT_ACTION_OUT); parser.add_argument("--check", action="store_true"); args = parser.parse_args(argv)
    if args.check:
        passed, reason = check(out_path=args.out); print(reason); return 0 if passed else 1
    payload = write(out_path=args.out, action_out=args.action_out)
    print(f"partial | accepted_state_preconditioned_jvp=true | arch={payload['hardware_execution']['gcn_arch_name']} | canonical_error={payload['comparison']['canonical_cpu_max_abs_error_n_per_m']}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
