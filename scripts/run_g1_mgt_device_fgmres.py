#!/usr/bin/env python3
"""Gate actual-MGT scaled FGMRES in one persistent gfx1030 lifecycle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import time
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve_triangular

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

from release_evidence_metadata import engine_version, file_sha256, git_head, input_checksums  # noqa: E402
from build_g1_mgt_material_family_adequacy_audit import (  # noqa: E402
    DEFAULT_OUT as MATERIAL_FAMILY_AUDIT,
    FAMILY_CODES,
    _frame_fixture,
    validate as validate_material_family_audit,
)
from build_g1_mgt_full_load_checkpoint_bridge import deterministic_npz_bytes  # noqa: E402
from run_engine_v2_hip_sparse_lu_apply import _detect_architecture, _resolve_device_lib_path, _resolve_hipcc, _run  # noqa: E402
from run_g1_mgt_accepted_state_hip_sparse_lu_parity import DEFAULT_CHECKPOINT, DEFAULT_MGT, WHEEL  # noqa: E402
from run_g1_mgt_single_lifecycle_preconditioned_jvp import build_references  # noqa: E402
from structural_analysis.engine_v2.contracts._canonical import array_data_hash, canonical_hash, sha256_prefixed  # noqa: E402
from structural_analysis.engine_v2.contracts.material_state_bundle import (  # noqa: E402
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
    rollback_trial_material_state_bundle,
)
from structural_analysis.engine_v2_backends.hip_current_tangent_operator import create_hip_current_tangent_operator_fixture, create_hip_current_tangent_operator_reference  # noqa: E402

PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SOURCE = Path("implementation/phase1/hip_kernels/engine_v2_mgt_fgmres.hip.cpp")
SCHEMA = Path("src/structural_analysis/schemas/g1_mgt_device_fgmres_v1.schema.json")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_device_fgmres_receipt.json"
DEFAULT_SOLUTION = PRODUCTIZATION / "g1_mgt_device_fgmres_solution.f64le"
DEFAULT_RESIDUAL = PRODUCTIZATION / "g1_mgt_device_fgmres_residual.f64le"
DEFAULT_ACCEPTED_STATE = PRODUCTIZATION / "g1_mgt_device_fgmres_accepted_state.f64le"
DEFAULT_NONLINEAR_RESIDUAL = PRODUCTIZATION / "g1_mgt_device_fgmres_nonlinear_residual.f64le"
DEFAULT_CHECKPOINT_OUT = PRODUCTIZATION / "g1_mgt_device_fgmres_checkpoint.npz"
DEFAULT_INITIAL_MATERIAL = PRODUCTIZATION / "g1_mgt_device_fgmres_initial_material.f64le"
DEFAULT_COMMITTED_MATERIAL = PRODUCTIZATION / "g1_mgt_device_fgmres_committed_material.f64le"
DEFAULT_REJECTED_MATERIAL = PRODUCTIZATION / "g1_mgt_device_fgmres_rejected_material.f64le"
DEFAULT_ROLLBACK_MATERIAL = PRODUCTIZATION / "g1_mgt_device_fgmres_rollback_material.f64le"
VERSION = "g1-mgt-device-fgmres-receipt.v1"
N = 70_560
MATERIAL_STATE_FIELD_NAMES = (
    "reference_length_m", "current_length_m", "extension_m",
    "engineering_strain", "axial_force_n", "axial_stiffness_n_per_m",
    "material_family_code", "source_primary_elastic_modulus_mpa",
    "source_secondary_elastic_modulus_mpa", "source_elastic_stress_mpa",
)
MATERIAL_FAMILY_FIXTURE_MAGIC = 0x314D414654474D47
MATERIAL_FAMILY_FIXTURE_VERSION = 1
SOURCE_PATHS = (
    DEFAULT_MGT, DEFAULT_CHECKPOINT, WHEEL, SOURCE,
    Path("implementation/phase1/hip_kernels/engine_v2_mgt_preconditioned_jvp.hip.cpp"),
    Path("implementation/phase1/hip_kernels/engine_v2_sparse_lu_apply.hip.cpp"),
    Path("implementation/phase1/hip_kernels/engine_v2_current_tangent_operator.hip.cpp"),
    Path("scripts/run_g1_mgt_single_lifecycle_preconditioned_jvp.py"),
    Path("scripts/build_g1_mgt_full_load_checkpoint_bridge.py"),
    Path("scripts/build_g1_mgt_material_family_adequacy_audit.py"),
    MATERIAL_FAMILY_AUDIT,
    Path("scripts/run_g1_mgt_device_fgmres.py"), SCHEMA,
    Path("src/structural_analysis/engine_v2/contracts/material_state_bundle.py"),
    Path("tests/test_run_g1_mgt_device_fgmres.py"),
)


def _material_family_fixture(
    *, root: Path, context: dict[str, Any]
) -> tuple[dict[str, np.ndarray], bytes, dict[str, Any]]:
    audit = validate_material_family_audit(
        _read(root / MATERIAL_FAMILY_AUDIT), root=root, current=True
    )
    frames, geometry, material_props, _select_audit = _frame_fixture(root)
    operator = context["problem"].current_tangent_operator
    comparisons = (
        np.array_equal(operator.array("geometry_dofs"), geometry.dofs),
        np.array_equal(
            operator.array("geometry_relative_translation_operators"),
            geometry.relative_translation_operators,
        ),
        np.array_equal(
            operator.array("geometry_reference_chords_m"),
            geometry.reference_chords_m,
        ),
        np.array_equal(
            operator.array("geometry_reference_lengths_m"),
            geometry.reference_lengths_m,
        ),
        np.array_equal(
            operator.array("geometry_axial_stiffness_n_per_m"),
            geometry.axial_stiffness_n_per_m,
        ),
    )
    if not all(comparisons):
        raise RuntimeError("material_family_fixture_geometry_order_mismatch")
    element_ids = np.asarray([row.elem_id for row in frames], dtype="<i8")
    family_names = tuple(
        str(material_props[int(row.material_id)]["type"]).upper()
        for row in frames
    )
    family_codes = np.asarray(
        [FAMILY_CODES[name] for name in family_names], dtype="<i4"
    )
    primary_e_mpa = np.asarray(
        [
            float(material_props[int(row.material_id)]["E_kN_per_m2"]) * 1.0e-3
            for row in frames
        ],
        dtype="<f8",
    )
    secondary_e_mpa = np.asarray(
        [
            float(
                material_props[int(row.material_id)].get(
                    "E_secondary_kN_per_m2", 0.0
                )
                or 0.0
            )
            * 1.0e-3
            for row in frames
        ],
        dtype="<f8",
    )
    arrays = {
        "element_ids": np.ascontiguousarray(element_ids),
        "family_codes": np.ascontiguousarray(family_codes),
        "primary_e_mpa": np.ascontiguousarray(primary_e_mpa),
        "secondary_e_mpa": np.ascontiguousarray(secondary_e_mpa),
    }
    header = struct.pack(
        "<QQq",
        MATERIAL_FAMILY_FIXTURE_MAGIC,
        MATERIAL_FAMILY_FIXTURE_VERSION,
        int(element_ids.size),
    )
    raw = header + b"".join(value.tobytes() for value in arrays.values())
    expected_bytes = 24 + int(element_ids.size) * (8 + 4 + 8 + 8)
    if len(raw) != expected_bytes:
        raise RuntimeError("material_family_fixture_byte_length_invalid")
    return arrays, raw, {
        "profile": "actual_mgt_geometry_ordered_material_family_fixture.v1",
        "byte_length": len(raw),
        "file_sha256": sha256_prefixed(raw),
        "adequacy_audit_receipt_hash": audit["receipt_hash"],
        "element_id_order_data_hash": array_data_hash(element_ids),
        "family_code_data_hash": array_data_hash(family_codes),
        "primary_elastic_modulus_mpa_data_hash": array_data_hash(primary_e_mpa),
        "secondary_elastic_modulus_mpa_data_hash": array_data_hash(
            secondary_e_mpa
        ),
        "family_counts": audit["material_fixture"]["family_counts"],
        "geometry_order_exact": True,
    }


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative(root: Path, path: Path) -> str:
    return _resolve(root, path).resolve().relative_to(root.resolve()).as_posix()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("receipt_must_be_object")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash({k: v for k, v in payload.items() if k != "receipt_hash"})


def _clean(root: Path) -> bool:
    result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--",
                             *(_relative(root, p) for p in SOURCE_PATHS)], cwd=root,
                            check=True, capture_output=True, text=True)
    return not result.stdout.strip()


def _artifact(root: Path, path: Path, vector: np.ndarray) -> tuple[dict[str, Any], bytes]:
    value = np.ascontiguousarray(vector, dtype="<f8"); raw = value.tobytes()
    return ({"path": _relative(root, path), "dtype": "<f8", "shape": [N],
             "byte_length": len(raw), "file_sha256": sha256_prefixed(raw),
             "data_hash": array_data_hash(value)}, raw)


def _material_artifact(root: Path, path: Path, values: np.ndarray) -> tuple[dict[str, Any], bytes]:
    value = np.ascontiguousarray(values, dtype="<f8"); raw = value.tobytes()
    return ({"path": _relative(root, path), "dtype": "<f8",
             "shape": [int(value.shape[0]), int(value.shape[1])],
             "field_names": list(MATERIAL_STATE_FIELD_NAMES),
             "byte_length": len(raw), "file_sha256": sha256_prefixed(raw),
             "data_hash": array_data_hash(value)}, raw)


def _mgt_state_hash(*, context: dict[str, Any], state: np.ndarray) -> str:
    operator = context["problem"].current_tangent_operator
    free = np.asarray(operator.array("free_global_dofs"), dtype="<i8")
    binding = context["problem"].exact_restart_binding()
    return canonical_hash({
        "schema_version": "g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1",
        "load_factor": 1.0,
        "free_displacement_data_hash": array_data_hash(state),
        "free_equation_order_data_hash": array_data_hash(free),
        "equilibrium_operator_binding_hash": binding["equilibrium_operator_binding_hash"],
    })


def _checkpoint(root: Path, path: Path, *, context: dict[str, Any],
                accepted_state: np.ndarray, nonlinear_residual_n: np.ndarray,
                correction: np.ndarray) -> tuple[dict[str, Any], bytes]:
    operator = context["problem"].current_tangent_operator
    free = np.asarray(operator.array("free_global_dofs"), dtype="<i8")
    global_state = np.array(
        operator.array("background_global_displacements_m"), dtype="<f8", copy=True)
    global_state[free] = accepted_state
    binding = context["problem"].exact_restart_binding()
    state_hash = _mgt_state_hash(context=context, state=accepted_state)
    with np.load(root / DEFAULT_CHECKPOINT, allow_pickle=False) as seed:
        node_id = np.asarray(seed["node_id"], dtype="<i8")
    arrays = {
        "accepted_state_hash": np.asarray(state_hash),
        "checkpoint_schema": np.asarray("g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1"),
        "displacement_u": np.ascontiguousarray(global_state, dtype="<f8"),
        "dof_per_node": np.asarray(6, dtype="<i4"),
        "equilibrium_operator_binding_hash": np.asarray(binding["equilibrium_operator_binding_hash"]),
        "final_increment_inf_m": np.asarray(float(np.linalg.norm(correction, ord=np.inf)), dtype="<f8"),
        "fixed_point_relative_increment": np.asarray(
            float(np.linalg.norm(correction, ord=np.inf)) /
            max(float(np.linalg.norm(accepted_state, ord=np.inf)), 1.0e-30), dtype="<f8"),
        "free_displacement_data_hash": np.asarray(array_data_hash(accepted_state)),
        "free_displacements_m": np.ascontiguousarray(accepted_state, dtype="<f8"),
        "free_equation_order_data_hash": np.asarray(array_data_hash(free)),
        "free_global_dofs": free,
        "load_scale": np.asarray(1.0, dtype="<f8"),
        "max_translation_m": np.asarray(float(np.max(np.abs(global_state.reshape(-1, 6)[:, :3]))), dtype="<f8"),
        "model_source_sha256": np.asarray(binding["model_source_sha256"]),
        "node_id": node_id,
        "residual_inf_n": np.asarray(float(np.linalg.norm(nonlinear_residual_n, ord=np.inf)), dtype="<f8"),
        "schema_version": np.asarray("g1-mgt-state-updated-frame-axial-full-load-checkpoint.v1"),
        "source_commit_sha": np.asarray(binding["source_commit_sha"]),
    }
    started = time.perf_counter(); raw = deterministic_npz_bytes(arrays)
    overhead = time.perf_counter() - started
    if raw != deterministic_npz_bytes(arrays):
        raise RuntimeError("device_fgmres_checkpoint_not_deterministic")
    with np.load(BytesIO(raw), allow_pickle=False) as replay:
        if set(replay.files) != set(arrays) or not all(
            np.array_equal(replay[name], value) for name, value in arrays.items()):
            raise RuntimeError("device_fgmres_checkpoint_exact_reload_failed")
        if not np.array_equal(replay["free_displacements_m"], accepted_state):
            raise RuntimeError("device_fgmres_checkpoint_exact_restart_failed")
    return ({"path": _relative(root, path), "schema": str(arrays["schema_version"]),
             "byte_length": len(raw), "file_sha256": sha256_prefixed(raw),
             "accepted_state_hash": state_hash, "free_displacement_data_hash": array_data_hash(accepted_state),
             "exact_reload": True, "exact_restart_terminal_state": True,
             "serialization_overhead_seconds": overhead,
             "source_commit_sha": binding["source_commit_sha"],
             "model_source_sha256": binding["model_source_sha256"],
             "equilibrium_operator_binding_hash": binding["equilibrium_operator_binding_hash"]}, raw)


def _material_reference(
    *,
    context: dict[str, Any],
    free_state: np.ndarray,
    family_fixture: dict[str, np.ndarray],
) -> np.ndarray:
    operator = context["problem"].current_tangent_operator
    free = np.asarray(operator.array("free_global_dofs"), dtype=np.int64)
    global_state = np.array(
        operator.array("background_global_displacements_m"), dtype=np.float64, copy=True)
    global_state[free] = np.asarray(free_state, dtype=np.float64)
    dofs = np.asarray(operator.array("geometry_dofs"), dtype=np.int64)
    relative_operator = np.asarray(
        operator.array("geometry_relative_translation_operators"), dtype=np.float64)
    reference_chords = np.asarray(
        operator.array("geometry_reference_chords_m"), dtype=np.float64)
    reference_lengths = np.asarray(
        operator.array("geometry_reference_lengths_m"), dtype=np.float64)
    axial = np.asarray(
        operator.array("geometry_axial_stiffness_n_per_m"), dtype=np.float64)
    gathered = global_state[dofs]
    relative = np.einsum("eij,ej->ei", relative_operator, gathered, optimize=False)
    current_chords = reference_chords + relative
    current_lengths = np.sqrt(np.sum(current_chords * current_chords, axis=1))
    reference_direction = reference_chords / reference_lengths[:, None]
    linear_extension = np.sum(reference_direction * relative, axis=1)
    relative_squared = np.sum(relative * relative, axis=1)
    extension = (
        2.0 * reference_lengths * linear_extension + relative_squared
    ) / (current_lengths + reference_lengths)
    strain = extension / reference_lengths
    return np.ascontiguousarray(
        np.column_stack(
            (
                reference_lengths,
                current_lengths,
                extension,
                strain,
                axial * extension,
                axial,
                family_fixture["family_codes"],
                family_fixture["primary_e_mpa"],
                family_fixture["secondary_e_mpa"],
                family_fixture["primary_e_mpa"] * strain,
            )
        ),
        dtype="<f8",
    )


def _material_bundles(*, context: dict[str, Any], initial: np.ndarray,
                      committed: np.ndarray, rejected: np.ndarray,
                      accepted_state: np.ndarray,
                      correction: np.ndarray,
                      family_fixture: dict[str, np.ndarray]) -> dict[str, Any]:
    problem = context["problem"]
    model_hash = problem.model_source_sha256
    plan_hash = problem.equilibrium_operator_binding_hash
    initial_state_hash = _mgt_state_hash(context=context, state=context["state"])
    committed_state_hash = _mgt_state_hash(context=context, state=accepted_state)
    rejected_state_hash = canonical_hash({
        "profile": "g1-mgt-post-acceptance-material-trial-state.v1",
        "accepted_state_hash": committed_state_hash,
        "free_displacement_data_hash": array_data_hash(
            np.ascontiguousarray(accepted_state + 0.5 * correction, dtype="<f8")),
    })

    def inputs(values: np.ndarray, parents: tuple[str, ...] | None) -> tuple[MaterialStateInput, ...]:
        rows: list[MaterialStateInput] = []
        for index, value in enumerate(values):
            family_code = int(family_fixture["family_codes"][index])
            family_name = next(
                name for name, code in FAMILY_CODES.items() if code == family_code
            )
            rows.append(MaterialStateInput(
                entity_id=f"mgt.frame.{int(family_fixture['element_ids'][index])}",
                integration_point_id="finite_chord_axial.ip0",
                material_type_id=f"mgt_source_elastic_{family_name.lower()}",
                material_schema_version="mgt-source-elastic-family-state.v1",
                state_bytes=np.ascontiguousarray(value, dtype="<f8").tobytes(),
                parent_state_data_hash=None if parents is None else parents[index],
            ))
        return tuple(rows)

    parent = create_initial_material_state_bundle(
        bundle_id="g1.mgt.elastic.initial", model_ir_content_hash=model_hash,
        execution_plan_hash=plan_hash, solver_state_hash=initial_state_hash,
        entries=inputs(initial, None))
    trial = open_trial_material_state_bundle(
        parent, solver_state_hash=committed_state_hash,
        entries=inputs(committed, tuple(row.data_hash for row in parent.entries)),
        bundle_id="g1.mgt.elastic.accepted_trial")
    accepted = commit_trial_material_state_bundle(
        parent, trial, solver_state_hash=committed_state_hash,
        bundle_id="g1.mgt.elastic.committed")
    rejected_trial = open_trial_material_state_bundle(
        accepted, solver_state_hash=rejected_state_hash,
        entries=inputs(rejected, tuple(row.data_hash for row in accepted.entries)),
        bundle_id="g1.mgt.elastic.rejected_trial")
    rolled_back = rollback_trial_material_state_bundle(accepted, rejected_trial)
    return {
        "model_ir_content_hash": model_hash,
        "execution_plan_hash": plan_hash,
        "initial_bundle_hash": parent.bundle_hash,
        "accepted_trial_bundle_hash": trial.bundle_hash,
        "committed_bundle_hash": accepted.bundle_hash,
        "rejected_trial_bundle_hash": rejected_trial.bundle_hash,
        "integration_point_order_hash": accepted.integration_point_order_hash,
        "entry_count": accepted.entry_count,
        "committed_epoch": accepted.epoch,
        "rejected_trial_epoch": rejected_trial.epoch,
        "committed_solver_state_hash": accepted.solver_state_hash,
        "rollback_returns_exact_accepted_object": rolled_back is accepted,
    }


def _compile_run(root: Path, sparse: Any, tangent: Any, material_fixture_raw: bytes,
                 reference_force_n: float,
                 hipcc: str, rocm_path: str, device_lib_path: str, timeout: float,
                 expected_architecture: str) -> dict[str, Any]:
    compiler = _resolve_hipcc(hipcc); libs = _resolve_device_lib_path(root, device_lib_path)
    architecture = _detect_architecture(root, "rocminfo")
    if expected_architecture not in {"gfx1030", "gfx1100"}:
        raise ValueError("device_fgmres_expected_architecture_invalid")
    if architecture != expected_architecture:
        raise RuntimeError(
            "device_fgmres_architecture_mismatch:"
            f"expected={expected_architecture}:observed={architecture}"
        )
    with tempfile.TemporaryDirectory(prefix="g1-mgt-device-fgmres-") as raw:
        temp = Path(raw); sp = temp / "sparse.bin"; tp = temp / "tangent.bin"
        mp = temp / "material-family.bin"
        binaries = {
            "gfx1030": temp / "fgmres-gfx1030",
            "gfx1100": temp / "fgmres-gfx1100",
        }
        solution = temp / "solution.bin"; residual = temp / "residual.bin"
        accepted_state = temp / "accepted-state.bin"; nonlinear_residual = temp / "nonlinear-residual.bin"
        initial_material = temp / "initial-material.bin"
        committed_material = temp / "committed-material.bin"
        rejected_material = temp / "rejected-material.bin"
        rollback_material = temp / "rollback-material.bin"
        sp.write_bytes(sparse.to_bytes()); tp.write_bytes(tangent.to_bytes())
        mp.write_bytes(material_fixture_raw)
        base = [str(compiler), f"--rocm-path={rocm_path}", f"--rocm-device-lib-path={libs}"]
        tail = [str(root / SOURCE), "-O2", "-Werror", "-ffp-contract=off", "-std=c++17"]
        for arch, output in binaries.items():
            built = _run([*base, f"--offload-arch={arch}", *tail, "-o", str(output)], cwd=root, timeout=180)
            if built.returncode: raise RuntimeError(f"device_fgmres_{arch}_compile_failed:" + built.stderr[-1000:])
        binary = binaries[expected_architecture]
        executed = _run([str(binary), str(sp), str(tp), str(mp), repr(reference_force_n),
                         str(solution), str(residual), str(accepted_state), str(nonlinear_residual),
                         str(initial_material), str(committed_material),
                         str(rejected_material), str(rollback_material)],
                        cwd=root, timeout=timeout)
        if executed.returncode: raise RuntimeError("device_fgmres_execution_failed:" + executed.stderr[-1000:])
        runtime = json.loads(executed.stdout.strip().splitlines()[-1])
        return {"runtime": runtime, "solution": np.fromfile(solution, dtype="<f8"),
                "residual": np.fromfile(residual, dtype="<f8"),
                "accepted_state": np.fromfile(accepted_state, dtype="<f8"),
                "nonlinear_residual": np.fromfile(nonlinear_residual, dtype="<f8"),
                "initial_material": np.fromfile(initial_material, dtype="<f8"),
                "committed_material": np.fromfile(committed_material, dtype="<f8"),
                "rejected_material": np.fromfile(rejected_material, dtype="<f8"),
                "rollback_material": np.fromfile(rollback_material, dtype="<f8"),
                "binary_sha256": file_sha256(binary), "binary_byte_length": binary.stat().st_size,
                "dual_target_binary_sha256": {
                    arch: file_sha256(path) for arch, path in binaries.items()
                },
                "compiler_version": _run([str(compiler), "--version"], cwd=root, timeout=30).stdout.splitlines()[0]}


def _cpu_baseline(*, sparse: Any, context: dict[str, Any],
                  reference_force_n: float) -> dict[str, Any]:
    factor = sparse.factor; n = factor.dimension; restart = 6
    lower = csr_matrix((factor.lower_numeric_values, factor.lower_column_indices,
                        factor.lower_row_pointer), shape=(n, n))
    upper = csr_matrix((factor.upper_numeric_values, factor.upper_column_indices,
                        factor.upper_row_pointer), shape=(n, n))

    def precondition(vector: np.ndarray) -> np.ndarray:
        rhs_n = vector * reference_force_n
        permuted = rhs_n[factor.inverse_row_permutation]
        low = spsolve_triangular(lower, permuted, lower=True)
        high = spsolve_triangular(upper, low, lower=False)
        return np.asarray(high[factor.column_permutation], dtype=np.float64)

    operator = context["problem"].current_tangent_operator
    state = context["state"]
    rhs_n = context["rhs_kn"] * 1000.0
    started = time.perf_counter()
    scaled_rhs = rhs_n / reference_force_n
    beta = float(np.linalg.norm(scaled_rhs))
    basis = np.zeros((restart + 1, n), dtype=np.float64)
    directions = np.zeros((restart, n), dtype=np.float64)
    hessenberg = np.zeros((restart + 1, restart), dtype=np.float64)
    basis[0] = scaled_rhs / beta
    for column in range(restart):
        directions[column] = precondition(basis[column])
        work = np.asarray(operator.apply_n_per_m(
            state, 1.0, directions[column]), dtype=np.float64) / reference_force_n
        for _pass in range(2):
            for row in range(column + 1):
                coefficient = float(np.dot(basis[row], work))
                hessenberg[row, column] += coefficient
                work -= coefficient * basis[row]
        hessenberg[column + 1, column] = float(np.linalg.norm(work))
        basis[column + 1] = work / hessenberg[column + 1, column]
    target = np.zeros(restart + 1, dtype=np.float64); target[0] = beta
    coefficients = np.linalg.lstsq(hessenberg, target, rcond=None)[0]
    correction = coefficients @ directions
    linear_action_n = np.asarray(
        operator.apply_n_per_m(state, 1.0, correction), dtype=np.float64)
    linear_residual_inf_n = float(np.linalg.norm(rhs_n - linear_action_n, ord=np.inf))
    alphas = (1.0, 0.5, 0.25, 0.125, 0.0625)
    base_l2 = float(np.linalg.norm(-rhs_n))
    candidates = []
    selected = None
    for alpha in alphas:
        residual_n = np.asarray(
            context["problem"].residual_kn(state + alpha * correction, 1.0),
            dtype=np.float64) * 1000.0
        l2 = float(np.linalg.norm(residual_n)); inf = float(np.linalg.norm(residual_n, ord=np.inf))
        candidates.append({"alpha": alpha, "residual_l2_n": l2, "residual_inf_n": inf})
        if selected is None and l2 <= (1.0 - 1.0e-4 * alpha) * base_l2:
            selected = len(candidates) - 1
    wall = time.perf_counter() - started
    if selected is None: raise RuntimeError("cpu_baseline_line_search_failed")
    return {"wall_seconds": wall, "krylov_iterations": restart,
            "preconditioner_apply_count": restart, "matvec_count": restart + 1,
            "physical_residual_evaluation_count": len(alphas),
            "terminal_linear_residual_inf_n": linear_residual_inf_n,
            "selected_index": selected, "accepted_alpha": alphas[selected],
            "accepted_residual_inf_n": candidates[selected]["residual_inf_n"],
            "candidate_rows": candidates,
            "correction_data_hash": array_data_hash(np.ascontiguousarray(correction, dtype="<f8"))}


def run(*, root: Path = ROOT, out: Path = DEFAULT_OUT, solution_out: Path = DEFAULT_SOLUTION,
        residual_out: Path = DEFAULT_RESIDUAL, accepted_state_out: Path = DEFAULT_ACCEPTED_STATE,
        nonlinear_residual_out: Path = DEFAULT_NONLINEAR_RESIDUAL,
        checkpoint_out: Path = DEFAULT_CHECKPOINT_OUT,
        initial_material_out: Path = DEFAULT_INITIAL_MATERIAL,
        committed_material_out: Path = DEFAULT_COMMITTED_MATERIAL,
        rejected_material_out: Path = DEFAULT_REJECTED_MATERIAL,
        rollback_material_out: Path = DEFAULT_ROLLBACK_MATERIAL,
        hipcc: str = "/opt/rocm-6.0.2/bin/hipcc",
        rocm_path: str = "/opt/rocm-6.0.2", device_lib_path: str = "", timeout: float = 600,
        expected_architecture: str = "gfx1030",
        ) -> tuple[dict[str, Any], bytes, bytes, bytes, bytes, bytes, bytes, bytes, bytes, bytes]:
    root = root.resolve()
    if not _clean(root): raise RuntimeError("device_fgmres_requires_clean_source_paths")
    sparse, _, tangent, context = build_references(root=root)
    family_fixture, family_fixture_raw, family_fixture_manifest = (
        _material_family_fixture(root=root, context=context)
    )
    reference_load_kn = np.asarray(context["problem"].reference_load_kn(), dtype=np.float64)
    reference_force_n = max(1.0, float(np.max(np.abs(reference_load_kn))) * 1000.0)
    execution = _compile_run(root, sparse, tangent.fixture, family_fixture_raw,
                             reference_force_n,
                             hipcc, rocm_path, device_lib_path, timeout,
                             expected_architecture)
    cpu_baseline = _cpu_baseline(
        sparse=sparse, context=context, reference_force_n=reference_force_n)
    runtime = execution["runtime"]; solution = execution["solution"]; residual = execution["residual"]
    accepted_state = execution["accepted_state"]; nonlinear_residual = execution["nonlinear_residual"]
    if any(value.shape != (N,) for value in (solution, residual, accepted_state, nonlinear_residual)):
        raise RuntimeError("device_fgmres_output_shape_invalid")
    replay_fixture = create_hip_current_tangent_operator_fixture(
        context["problem"].current_tangent_operator,
        free_displacements_m=context["state"], load_factor=1.0, free_direction_m=solution)
    replay = create_hip_current_tangent_operator_reference(replay_fixture)
    expected_residual = context["rhs_kn"] * 1000.0 - replay.device_order_action_n_per_m
    replay_error = float(np.max(np.abs(residual - expected_residual)))
    expected_nonlinear_residual = np.asarray(
        context["problem"].residual_kn(accepted_state, 1.0), dtype=np.float64) * 1000.0
    nonlinear_replay_error = float(np.max(np.abs(
        nonlinear_residual - expected_nonlinear_residual)))
    nonlinear_parity_tolerance_n = 2.0e-6
    material_count = int(runtime["material_integration_point_count"])
    material_shape = (material_count, len(MATERIAL_STATE_FIELD_NAMES))
    initial_material = execution["initial_material"].reshape(material_shape)
    committed_material = execution["committed_material"].reshape(material_shape)
    rejected_material = execution["rejected_material"].reshape(material_shape)
    rollback_material = execution["rollback_material"].reshape(material_shape)
    expected_material = (
        _material_reference(
            context=context,
            free_state=context["state"],
            family_fixture=family_fixture,
        ),
        _material_reference(
            context=context,
            free_state=accepted_state,
            family_fixture=family_fixture,
        ),
        _material_reference(
            context=context,
            free_state=accepted_state + 0.5 * solution,
            family_fixture=family_fixture,
        ),
    )
    observed_material = (initial_material, committed_material, rejected_material)
    material_field_max_abs_errors = [
        float(max(np.max(np.abs(actual[:, field] - expected[:, field]))
                  for actual, expected in zip(observed_material, expected_material, strict=True)))
        for field in range(len(MATERIAL_STATE_FIELD_NAMES))
    ]
    material_max_scaled_error = float(max(
        np.max(np.abs(actual - expected) / np.maximum(np.abs(expected), 1.0))
        for actual, expected in zip(observed_material, expected_material, strict=True)))
    material_tolerance = 2.0e-12
    rollback_material_exact = bool(np.array_equal(rollback_material, committed_material))
    material_bundles = _material_bundles(
        context=context, initial=initial_material, committed=committed_material,
        rejected=rejected_material, accepted_state=accepted_state,
        correction=solution, family_fixture=family_fixture)
    material_contract = bool(
        material_count == context["problem"].current_tangent_operator.geometry_element_count
        and runtime["material_state_field_count"] == len(MATERIAL_STATE_FIELD_NAMES)
        and runtime["material_trial_count"] == 2
        and runtime["material_commit_count"] == 1
        and runtime["material_rollback_count"] == 1
        and runtime["material_family_fixture_bound"] is True
        and runtime["material_conc_count"] == 2_182
        and runtime["material_steel_count"] == 1_692
        and runtime["material_src_count"] == 1_692
        and runtime["material_user_count"] == 6
        and material_max_scaled_error <= material_tolerance
        and rollback_material_exact
        and material_bundles["rollback_returns_exact_accepted_object"] is True
        and material_bundles["committed_solver_state_hash"]
        == _mgt_state_hash(context=context, state=accepted_state)
    )
    contract = bool(runtime["status"] == "ok" and runtime["gcn_arch_name"] == expected_architecture
                    and runtime["krylov_iterations"] == 6 and runtime["preconditioner_apply_count"] == 6
                    and runtime["matvec_count"] == 7 and runtime["mid_iteration_d2h_transfer_count"] == 0
                    and runtime["physical_residual_inf_n"] <= 1.0e-9 and replay_error <= 1.0e-18
                    and runtime["accepted_alpha"] == 1.0
                    and runtime["accepted_nonlinear_residual_inf_n"] <= 5.0e-4
                    and nonlinear_replay_error <= nonlinear_parity_tolerance_n
                    and material_contract)
    if not contract: raise RuntimeError("device_fgmres_contract_failed")
    solution_item, solution_raw = _artifact(root, solution_out, solution)
    residual_item, residual_raw = _artifact(root, residual_out, residual)
    accepted_state_item, accepted_state_raw = _artifact(root, accepted_state_out, accepted_state)
    nonlinear_residual_item, nonlinear_residual_raw = _artifact(
        root, nonlinear_residual_out, nonlinear_residual)
    checkpoint_item, checkpoint_raw = _checkpoint(
        root, checkpoint_out, context=context, accepted_state=accepted_state,
        nonlinear_residual_n=nonlinear_residual, correction=solution)
    initial_material_item, initial_material_raw = _material_artifact(
        root, initial_material_out, initial_material)
    committed_material_item, committed_material_raw = _material_artifact(
        root, committed_material_out, committed_material)
    rejected_material_item, rejected_material_raw = _material_artifact(
        root, rejected_material_out, rejected_material)
    rollback_material_item, rollback_material_raw = _material_artifact(
        root, rollback_material_out, rollback_material)
    scaling = {"schema_version": "equation-scaling-mgt-translation-free.v1",
               "reference_force_policy": "max_translation_or_equivalent_moment_with_floor.v1",
               "minimum_reference_force_n": 1.0, "reference_force_n": reference_force_n,
               "free_equation_scope": True, "translation_equation_count": N,
               "scale_vector_data_hash": array_data_hash(np.full(N, reference_force_n, dtype="<f8"))}
    payload = {
        "schema_version": VERSION, "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "partial", "contract_pass": True,
        "contract_scope": (
            "actual_mgt_full_load_scaled_fgmres_single_device_lifecycle_"
            + expected_architecture
        ),
        "source": {"repository_commit_sha": git_head(root), "source_paths_clean_at_execution": True,
                   "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root), "engine_version": engine_version(root)},
        "runtime": {"backend": "amd_rocm_hip", "device_name": runtime["device_name"],
                    "gcn_arch_name": runtime["gcn_arch_name"], "device_nodes": ["/dev/kfd", "/dev/dri/renderD128"],
                    "compiler_version": execution["compiler_version"], "binary_sha256": execution["binary_sha256"],
                    "binary_byte_length": execution["binary_byte_length"],
                    "executed_architecture": expected_architecture,
                    "dual_target_binary_sha256": execution["dual_target_binary_sha256"],
                    "wheel_sha256": file_sha256(root / WHEEL)},
        "accepted_state": {"checkpoint": DEFAULT_CHECKPOINT.as_posix(), "checkpoint_sha256": file_sha256(root / DEFAULT_CHECKPOINT),
                           "load_factor": 1.0, "equation_count": N, "state_data_hash": array_data_hash(context["state"]),
                           "right_hand_side_data_hash": array_data_hash(context["rhs_kn"])},
        "material_lifecycle": {
            "profile": "actual_mgt_source_family_finite_chord_elastic_state.v1",
            "integration_point_count": material_count,
            "field_names": list(MATERIAL_STATE_FIELD_NAMES),
            "family_fixture": family_fixture_manifest,
            "trial_count": runtime["material_trial_count"],
            "commit_count": runtime["material_commit_count"],
            "rollback_count": runtime["material_rollback_count"],
            "kernel_invocation_count": runtime["material_kernel_invocation_count"],
            "mid_lifecycle_d2h_transfer_count": 0,
            "cpu_hip_max_scaled_error": material_max_scaled_error,
            "cpu_hip_scaled_error_tolerance": material_tolerance,
            "field_max_abs_errors": dict(zip(
                MATERIAL_STATE_FIELD_NAMES, material_field_max_abs_errors, strict=True)),
            "rollback_state_bitwise_exact": rollback_material_exact,
            "material_state_bundle": material_bundles,
            "artifacts": {
                "initial": initial_material_item,
                "committed": committed_material_item,
                "rejected_trial": rejected_material_item,
                "rollback": rollback_material_item,
            },
        },
        "equation_scaling": scaling, "hardware_execution": runtime,
        "performance": {"cpu_baseline": cpu_baseline,
                        "gpu_device_lifecycle_wall_seconds": runtime["device_lifecycle_wall_time_ms"] / 1000.0,
                        "speedup_vs_cpu": cpu_baseline["wall_seconds"] /
                        (runtime["device_lifecycle_wall_time_ms"] / 1000.0),
                        "terminal_resultir_parity": False,
                        "terminal_resultir_parity_reason": "authoritative_resultir_adapter_and_manifest_not_yet_emitted_despite_bound_elastic_material_bundle"},
        "comparison": {"terminal_physical_residual_cpu_replay_max_abs_error_n": replay_error,
                       "terminal_physical_residual_tolerance_n": 1.0e-9,
                       "accepted_nonlinear_residual_cpu_replay_max_abs_error_n": nonlinear_replay_error,
                       "accepted_nonlinear_residual_parity_tolerance_n": nonlinear_parity_tolerance_n,
                       "accepted_nonlinear_residual_cpu_inf_n": float(np.linalg.norm(expected_nonlinear_residual, ord=np.inf)),
                       "solution_artifact": solution_item, "residual_artifact": residual_item,
                       "accepted_state_artifact": accepted_state_item,
                       "nonlinear_residual_artifact": nonlinear_residual_item,
                       "checkpoint_artifact": checkpoint_item},
        "claims": {"actual_mgt_full_load_accepted_state": True, "production_size_fgmres": True,
                   "two_pass_mgs_arnoldi": True, "device_givens_and_backsolve": True,
                   "equation_scaling": True, "terminal_physical_residual_replay": True,
                   "single_device_lifecycle": True, "mid_iteration_d2h_zero": True,
                   "newton_update_on_device": True, "physical_line_search_on_device": True,
                   "nonlinear_convergence_gate_on_device": True,
                   "checkpoint_emitted": True, "exact_restart": True,
                   "dual_target_cross_compile": True,
                   "actual_gfx1030_hardware": expected_architecture == "gfx1030",
                   "actual_gfx1100_hardware": expected_architecture == "gfx1100",
                   "independent_gfx1100_run": False,
                   "material_commit_rollback": True,
                   "actual_mgt_elastic_material_state_bundle": True,
                   "actual_mgt_material_family_fixture_device_bound": True,
                   "nonlinear_material_family_breadth": False,
                   "resultir_diagnosticir": False,
                   "g1_closure": False},
        "blockers_remaining": ["independent_gfx1100_hardware_run_not_available",
                               "source_authoritative_nonlinear_material_parameters_unavailable",
                               "nonlinear_material_laws_not_connected_to_equilibrium_residual_jvp",
                               "resultir_diagnosticir_not_established"],
        "claim_boundary": (
            "Actual 70,560-equation accepted-state right-preconditioned FGMRES "
            "executes six two-pass-MGS Arnoldi iterations, device Givens rotations "
            "and backsolve, finite-chord physical-residual line-search candidates, "
            "accepted-state update, and a nonlinear convergence gate in one "
            f"{expected_architecture} lifecycle with zero iteration-time D2H. The "
            "same resident fixture uploads and consumes the exact 5,572-element MGT "
            "family order, source primary/secondary elastic moduli, and finite-chord "
            "material state during initial, accepted, and rejected trials, followed "
            "by exact rollback and MaterialStateBundle binding. This is "
            "source-authoritative family-buffer connectivity, not nonlinear "
            "constitutive breadth: source-authoritative hardening, damage/softening, "
            "and SRC fraction parameters are unavailable and nonlinear laws are not "
            "connected to residual/JVP. A single receipt does not establish runner "
            "independence or a signed cross-device pair. ResultIR, DiagnosticIR, "
            "independent gfx1100 hardware, and G1 closure remain unclaimed."
        )
    }
    payload["receipt_hash"] = _hash(payload); validate(payload, root=root, current=True)
    return (payload, solution_raw, residual_raw, accepted_state_raw,
            nonlinear_residual_raw, checkpoint_raw, initial_material_raw,
            committed_material_raw, rejected_material_raw, rollback_material_raw)


def validate(payload: dict[str, Any], *, root: Path = ROOT, current: bool = False, artifacts: bool = False) -> dict[str, Any]:
    schema = _read(root / SCHEMA); Draft202012Validator.check_schema(schema); Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload): raise ValueError("device_fgmres_receipt_hash_mismatch")
    if current and payload["source"]["input_checksums"] != input_checksums(SOURCE_PATHS, repo_root=root):
        raise ValueError("device_fgmres_sources_stale")
    if artifacts:
        for key in ("solution_artifact", "residual_artifact", "accepted_state_artifact", "nonlinear_residual_artifact", "checkpoint_artifact"):
            item = payload["comparison"][key]; path = _resolve(root, Path(item["path"]))
            if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]:
                raise ValueError("device_fgmres_artifact_invalid")
        for item in payload["material_lifecycle"]["artifacts"].values():
            path = _resolve(root, Path(item["path"]))
            if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]:
                raise ValueError("device_fgmres_material_artifact_invalid")
    return payload


def write(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs.get("root", ROOT)).resolve(); out = Path(kwargs.get("out", DEFAULT_OUT))
    solution = Path(kwargs.get("solution_out", DEFAULT_SOLUTION)); residual = Path(kwargs.get("residual_out", DEFAULT_RESIDUAL))
    accepted = Path(kwargs.get("accepted_state_out", DEFAULT_ACCEPTED_STATE))
    nonlinear = Path(kwargs.get("nonlinear_residual_out", DEFAULT_NONLINEAR_RESIDUAL))
    checkpoint = Path(kwargs.get("checkpoint_out", DEFAULT_CHECKPOINT_OUT))
    initial_material = Path(kwargs.get("initial_material_out", DEFAULT_INITIAL_MATERIAL))
    committed_material = Path(kwargs.get("committed_material_out", DEFAULT_COMMITTED_MATERIAL))
    rejected_material = Path(kwargs.get("rejected_material_out", DEFAULT_REJECTED_MATERIAL))
    rollback_material = Path(kwargs.get("rollback_material_out", DEFAULT_ROLLBACK_MATERIAL))
    payload, sr, rr, ar, nr, cr, imr, cmr, rmr, bmr = run(**kwargs)
    _resolve(root, solution).write_bytes(sr); _resolve(root, residual).write_bytes(rr)
    _resolve(root, accepted).write_bytes(ar); _resolve(root, nonlinear).write_bytes(nr)
    _resolve(root, checkpoint).write_bytes(cr)
    _resolve(root, initial_material).write_bytes(imr)
    _resolve(root, committed_material).write_bytes(cmr)
    _resolve(root, rejected_material).write_bytes(rmr)
    _resolve(root, rollback_material).write_bytes(bmr)
    _resolve(root, out).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return validate(payload, root=root, current=True, artifacts=True)


def check(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> tuple[bool, str]:
    try: validate(_read(_resolve(root, out)), root=root, current=True, artifacts=True)
    except Exception as exc: return False, f"g1_mgt_device_fgmres_receipt_invalid:{exc}"
    return True, "g1_mgt_device_fgmres_receipt_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--expected-architecture",
        choices=("gfx1030", "gfx1100"),
        default="gfx1030",
    )
    parser.add_argument("--hipcc", default="/opt/rocm-6.0.2/bin/hipcc")
    parser.add_argument("--rocm-path", default="/opt/rocm-6.0.2")
    parser.add_argument("--device-lib-path", default="")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(argv)
    if args.check:
        passed, reason = check(out=args.out)
        print(reason)
        return 0 if passed else 1
    payload = write(
        out=args.out,
        expected_architecture=args.expected_architecture,
        hipcc=args.hipcc,
        rocm_path=args.rocm_path,
        device_lib_path=args.device_lib_path,
        timeout=args.timeout,
    )
    runmeta = payload["hardware_execution"]
    print(f"partial | fgmres={runmeta['krylov_iterations']} | residual_inf_n={runmeta['physical_residual_inf_n']:.3e} | mid_d2h=0")
    return 0


if __name__ == "__main__": raise SystemExit(main())
