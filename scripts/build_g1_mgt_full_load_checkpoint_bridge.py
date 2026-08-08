#!/usr/bin/env python3
"""Build an exact-source full-load MGT checkpoint for the G1 HIP lane."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
from typing import Any
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"
PHASE1_ROOT = ROOT / "implementation/phase1"
for candidate in (SCRIPT_DIR, SRC_ROOT, PHASE1_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    DEFAULT_MGT,
    _continuation_config,
    _linear_solver_config,
)
from g1_mgt_load_coupled_arc_length_adapter import (  # noqa: E402
    build_real_mgt_load_coupled_arc_length_problem,
)
from release_evidence_metadata import (  # noqa: E402
    commit_bound_input_metadata,
    engine_version,
    file_sha256,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (  # noqa: E402
    load_controlled_matrix_free_newton_continuation,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CHECKPOINT_OUT = (
    PRODUCTIZATION / "g1_mgt_state_updated_frame_axial_full_load_checkpoint.npz"
)
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION / "g1_mgt_state_updated_frame_axial_full_load_checkpoint_receipt.json"
)
SCHEMA_VERSION = "g1-mgt-full-load-checkpoint-bridge-receipt.v1"
CHECKPOINT_SCHEMA = "g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _label(repo_root: Path, path: Path) -> str:
    resolved = _resolve(repo_root, path).resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _input_paths(*, mgt_path: Path, seed_checkpoint: Path) -> tuple[Path, ...]:
    return (
        mgt_path,
        seed_checkpoint,
        Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
        Path("implementation/phase1/mgt_physical_residual_assembly.py"),
        Path("implementation/phase1/mgt_state_updated_frame_axial_geometry.py"),
        Path("src/structural_analysis/solvers/nonlinear/load_controlled_matrix_free_newton.py"),
        Path("src/structural_analysis/solvers/nonlinear/matrix_free_fgmres.py"),
        Path("scripts/build_g1_mgt_full_load_checkpoint_bridge.py"),
        Path("scripts/build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.py"),
        Path("scripts/release_evidence_metadata.py"),
        Path("tests/test_build_g1_mgt_full_load_checkpoint_bridge.py"),
    )


def deterministic_npz_bytes(arrays: dict[str, np.ndarray]) -> bytes:
    """Encode an NPZ with canonical member order, metadata, and timestamps."""

    output = BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in sorted(arrays):
            member = BytesIO()
            np.lib.format.write_array(
                member,
                np.asarray(arrays[name]),
                allow_pickle=False,
            )
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, member.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def _checkpoint_arrays(
    *,
    node_id: np.ndarray,
    free_global_dofs: np.ndarray,
    free_displacements_m: np.ndarray,
    residual_inf_n: float,
    final_increment_inf_m: float,
    final_relative_increment: float,
    state_hash: str,
    source_binding: dict[str, Any],
) -> dict[str, np.ndarray]:
    nodes = np.ascontiguousarray(node_id, dtype="<i8")
    free = np.ascontiguousarray(free_global_dofs, dtype="<i8")
    values = np.ascontiguousarray(free_displacements_m, dtype="<f8")
    global_dof_count = int(nodes.size) * 6
    if free.ndim != 1 or values.shape != free.shape:
        raise ValueError("free displacement/order shape mismatch")
    if free.size and (int(free[0]) < 0 or int(free[-1]) >= global_dof_count):
        raise ValueError("free equation order is outside the global DOF range")
    if free.size > 1 and np.any(np.diff(free) <= 0):
        raise ValueError("free equation order must be strictly increasing")
    displacement = np.zeros(global_dof_count, dtype="<f8")
    displacement[free] = values
    translation = displacement.reshape((-1, 6))[:, :3]
    max_translation = float(
        np.max(np.linalg.norm(translation, axis=1), initial=0.0)
    )
    return {
        "checkpoint_schema": np.asarray(CHECKPOINT_SCHEMA),
        "schema_version": np.asarray(CHECKPOINT_SCHEMA),
        "load_scale": np.asarray(1.0, dtype="<f8"),
        "dof_per_node": np.asarray(6, dtype="<i4"),
        "node_id": nodes,
        "displacement_u": displacement,
        "free_global_dofs": free,
        "free_displacements_m": values,
        "residual_inf_n": np.asarray(residual_inf_n, dtype="<f8"),
        "fixed_point_relative_increment": np.asarray(
            final_relative_increment,
            dtype="<f8",
        ),
        "final_increment_inf_m": np.asarray(final_increment_inf_m, dtype="<f8"),
        "max_translation_m": np.asarray(max_translation, dtype="<f8"),
        "accepted_state_hash": np.asarray(state_hash),
        "source_commit_sha": np.asarray(source_binding["source_commit_sha"]),
        "model_source_sha256": np.asarray(source_binding["model_source_sha256"]),
        "equilibrium_operator_binding_hash": np.asarray(
            source_binding["equilibrium_operator_binding_hash"]
        ),
        "free_equation_order_data_hash": np.asarray(array_data_hash(free)),
        "free_displacement_data_hash": np.asarray(array_data_hash(values)),
    }


def build_artifacts(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    seed_checkpoint: Path = DEFAULT_CHECKPOINT,
    checkpoint_out: Path = DEFAULT_CHECKPOINT_OUT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
    source_commit_sha: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    repo_root = repo_root.resolve()
    source = commit_bound_input_metadata(
        _input_paths(mgt_path=mgt_path, seed_checkpoint=seed_checkpoint),
        repo_root=repo_root,
        source_commit_sha=source_commit_sha,
    )
    source_sha = str(source["source_commit_sha"])
    historical, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=_resolve(repo_root, mgt_path),
        roundtrip_npz=None,
        checkpoint_npz=_resolve(repo_root, seed_checkpoint),
        apply_state_updated_frame_axial_geometry=True,
        source_commit_sha=source_sha,
    )
    problem = historical.zero_state_problem()
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_linear_solver_config(),
    )
    result = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=_continuation_config(),
    )
    with np.load(_resolve(repo_root, seed_checkpoint), allow_pickle=False) as archive:
        node_id = np.asarray(archive["node_id"], dtype="<i8")
    binding = problem.exact_restart_binding()
    metrics = result.metrics
    final_attempt = result.attempts[-1]
    final_history = final_attempt["history"][-1]
    arrays = _checkpoint_arrays(
        node_id=node_id,
        free_global_dofs=np.asarray(problem.free_equation_global_dofs),
        free_displacements_m=result.final_free_displacements_m,
        residual_inf_n=float(metrics["final_residual_inf_kn"] * 1000.0),
        final_increment_inf_m=float(final_history["last_increment_inf_m"]),
        final_relative_increment=float(final_history["last_relative_increment"]),
        state_hash=result.final_checkpoint.state_hash,
        source_binding=binding,
    )
    checkpoint_bytes = deterministic_npz_bytes(arrays)
    source_exact = bool(source["source_input_provenance"]["contract_pass"])
    solver_gate = bool(
        result.status == "ready"
        and metrics["contract_pass"]
        and result.final_checkpoint.load_factor == 1.0
        and metrics["residual_and_increment_acceptance_gate"]
        and metrics["fallback_count"] == 0
        and metrics["regularization_count"] == 0
        and binding["complete"]
        and metadata["free_equation_count"] == 70_560
        and arrays["displacement_u"].shape == (78_282,)
    )
    contract_pass = bool(source_exact and solver_gate)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "source_commit_sha": source_sha,
        "engine_version": engine_version(repo_root),
        "source_commit_exact_replay_claim": source_exact,
        "source_input_provenance": source["source_input_provenance"],
        "input_checksums": source["input_checksums"],
        "case_id": problem.case_id,
        "checkpoint": {
            "path": _label(repo_root, checkpoint_out),
            "schema_version": CHECKPOINT_SCHEMA,
            "byte_length": len(checkpoint_bytes),
            "sha256": "sha256:" + __import__("hashlib").sha256(checkpoint_bytes).hexdigest(),
            "load_scale": 1.0,
            "node_count": int(node_id.size),
            "global_dof_count": int(arrays["displacement_u"].size),
            "free_equation_count": int(arrays["free_global_dofs"].size),
            "accepted_state_hash": result.final_checkpoint.state_hash,
            "free_equation_order_data_hash": str(
                arrays["free_equation_order_data_hash"].item()
            ),
            "free_displacement_data_hash": str(
                arrays["free_displacement_data_hash"].item()
            ),
            "exact_restart_binding": binding,
        },
        "solver": {
            "status": result.status,
            "terminal_reason": result.terminal_reason,
            "accepted_step_count": metrics["accepted_step_count"],
            "tangent_solve_count": metrics["tangent_solve_count"],
            "final_residual_inf_n": float(metrics["final_residual_inf_kn"] * 1000.0),
            "residual_and_increment_acceptance_gate": metrics[
                "residual_and_increment_acceptance_gate"
            ],
            "fallback_count": metrics["fallback_count"],
            "regularization_count": metrics["regularization_count"],
            "contract_pass": solver_gate,
        },
        "claims": {
            "actual_mgt_full_load_checkpoint": contract_pass,
            "load_scale_at_least_one": contract_pass,
            "physical_residual_and_increment_gate": contract_pass,
            "exact_source_model_operator_binding": contract_pass,
            "legacy_g1_lane_npz_compatible": contract_pass,
            "production_hip_worker_execution": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "production_hip_worker_not_executed_from_checkpoint",
            "device_resident_fgmres_preconditioner_not_integrated",
            "independent_gfx1100_receipt_not_attached",
            "signed_hardware_receipts_not_attached",
        ],
        "artifacts": {
            "checkpoint": _label(repo_root, checkpoint_out),
            "receipt": _label(repo_root, receipt_out),
        },
        "claim_boundary": (
            "This bridge materializes the exact accepted λ=1.0 CPU free vector "
            "into the legacy 78,282-DOF NPZ consumed by the G1 HIP lane while "
            "retaining source, model, operator, state, free-order, and free-vector "
            "identities. It does not claim that the downstream HIP Newton worker "
            "has executed or that full frame/shell material coupling is closed."
        ),
    }
    return receipt, checkpoint_bytes


def write_artifacts(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    checkpoint_out = Path(kwargs.get("checkpoint_out", DEFAULT_CHECKPOINT_OUT))
    receipt_out = Path(kwargs.get("receipt_out", DEFAULT_RECEIPT_OUT))
    receipt, checkpoint_bytes = build_artifacts(**kwargs)
    checkpoint_path = _resolve(repo_root, checkpoint_out)
    receipt_path = _resolve(repo_root, receipt_out)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(checkpoint_bytes)
    receipt_path.write_text(_json_text(receipt), encoding="utf-8")
    return receipt


def check_artifacts(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    seed_checkpoint: Path = DEFAULT_CHECKPOINT,
    checkpoint_out: Path = DEFAULT_CHECKPOINT_OUT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
) -> tuple[bool, str]:
    repo_root = repo_root.resolve()
    checkpoint_path = _resolve(repo_root, checkpoint_out)
    receipt_path = _resolve(repo_root, receipt_out)
    if not checkpoint_path.is_file() or not receipt_path.is_file():
        return False, "g1_full_load_checkpoint_bridge_artifact_missing"
    existing = _read_json(receipt_path)
    if file_sha256(checkpoint_path) != existing["checkpoint"]["sha256"]:
        return False, "g1_full_load_checkpoint_bridge_npz_hash_mismatch"
    expected, checkpoint_bytes = build_artifacts(
        repo_root=repo_root,
        mgt_path=mgt_path,
        seed_checkpoint=seed_checkpoint,
        checkpoint_out=checkpoint_out,
        receipt_out=receipt_out,
        source_commit_sha=str(existing["source_commit_sha"]),
    )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_full_load_checkpoint_bridge_receipt_mismatch"
    if checkpoint_path.read_bytes() != checkpoint_bytes:
        return False, "g1_full_load_checkpoint_bridge_npz_mismatch"
    return True, "g1_full_load_checkpoint_bridge_consistent"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--seed-checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--checkpoint-out", type=Path, default=DEFAULT_CHECKPOINT_OUT)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT_OUT)
    parser.add_argument("--source-commit-sha", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    kwargs = {
        "repo_root": ROOT,
        "mgt_path": args.mgt,
        "seed_checkpoint": args.seed_checkpoint,
        "checkpoint_out": args.checkpoint_out,
        "receipt_out": args.receipt_out,
    }
    if args.check:
        ok, message = check_artifacts(**kwargs)
        print(message)
        return 0 if ok else 1
    payload = write_artifacts(
        **kwargs,
        source_commit_sha=args.source_commit_sha,
    )
    print(
        f"{payload['status']} | load={payload['checkpoint']['load_scale']} | "
        f"equations={payload['checkpoint']['free_equation_count']} | "
        f"residual_n={payload['solver']['final_residual_inf_n']:.12g}"
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
