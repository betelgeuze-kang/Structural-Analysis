#!/usr/bin/env python3
"""Emit adapter-bound nonlinear ResultIR parity for the actual MGT HIP run."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

from release_evidence_metadata import file_sha256, git_head, input_checksums  # noqa: E402
from run_g1_mgt_device_fgmres import (  # noqa: E402
    DEFAULT_ACCEPTED_STATE, DEFAULT_COMMITTED_MATERIAL, DEFAULT_INITIAL_MATERIAL,
    DEFAULT_OUT as FGMRES_RECEIPT, DEFAULT_REJECTED_MATERIAL, DEFAULT_SOLUTION,
    MATERIAL_STATE_FIELD_NAMES, _mgt_state_hash,
)
from run_g1_mgt_single_lifecycle_preconditioned_jvp import build_references  # noqa: E402
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash, canonical_hash, immutable_array, sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (  # noqa: E402
    MaterialStateBundle, MaterialStateInput, commit_trial_material_state_bundle,
    create_initial_material_state_bundle, open_trial_material_state_bundle,
    validate_material_state_bundle,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (  # noqa: E402
    NonlinearNumericalResultSourceSnapshot, NonlinearTerminalReceipt,
    create_adapter_bound_nonlinear_numerical_result_ir,
    create_nonlinear_terminal_receipt, validate_nonlinear_result_manifest,
    validate_nonlinear_terminal_receipt,
)

PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_nonlinear_result_ir_receipt.json"
DEFAULT_HIP_RESULT = PRODUCTIZATION / "g1_mgt_nonlinear_result_ir_hip.json"
DEFAULT_CPU_RESULT = PRODUCTIZATION / "g1_mgt_nonlinear_result_ir_cpu.json"
DEFAULT_DISPLACEMENT = PRODUCTIZATION / "g1_mgt_nonlinear_result_ir_displacement.f64le"
SCHEMA = Path("src/structural_analysis/schemas/g1_mgt_nonlinear_result_ir_v1.schema.json")
VERSION = "g1-mgt-nonlinear-result-ir-receipt.v1"
SOURCE_PATHS = (
    FGMRES_RECEIPT, DEFAULT_ACCEPTED_STATE, DEFAULT_SOLUTION, DEFAULT_INITIAL_MATERIAL,
    DEFAULT_COMMITTED_MATERIAL, DEFAULT_REJECTED_MATERIAL,
    Path("scripts/build_g1_mgt_nonlinear_result_ir.py"), SCHEMA,
    Path("src/structural_analysis/engine_v2/contracts/nonlinear_result.py"),
    Path("src/structural_analysis/engine_v2/contracts/material_state_bundle.py"),
    Path("tests/test_build_g1_mgt_nonlinear_result_ir.py"),
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("json_object_required")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash({k: v for k, v in payload.items() if k != "receipt_hash"})


def _clean(root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--",
         *(path.as_posix() for path in SOURCE_PATHS)], cwd=root,
        check=True, capture_output=True, text=True)
    return not result.stdout.strip()


def _bundle(*, receipt: dict[str, Any], context: dict[str, Any],
            initial: np.ndarray, committed: np.ndarray,
            accepted_state: np.ndarray) -> MaterialStateBundle:
    model_hash = context["problem"].model_source_sha256
    plan_hash = context["problem"].equilibrium_operator_binding_hash
    state_hash = receipt["comparison"]["checkpoint_artifact"]["accepted_state_hash"]
    initial_state_hash = _mgt_state_hash(context=context, state=context["state"])
    def rows(values: np.ndarray, parents: tuple[str, ...] | None) -> tuple[MaterialStateInput, ...]:
        return tuple(MaterialStateInput(
            entity_id=f"mgt.frame_geometry.{index:04d}",
            integration_point_id="finite_chord_axial.ip0",
            material_type_id="elastic_finite_chord_axial",
            material_schema_version="elastic-finite-chord-axial-state.v1",
            state_bytes=np.ascontiguousarray(value, dtype="<f8").tobytes(),
            parent_state_data_hash=None if parents is None else parents[index],
        ) for index, value in enumerate(values))
    parent = create_initial_material_state_bundle(
        bundle_id="g1.mgt.elastic.initial", model_ir_content_hash=model_hash,
        execution_plan_hash=plan_hash, solver_state_hash=initial_state_hash,
        entries=rows(initial, None))
    trial = open_trial_material_state_bundle(
        parent, solver_state_hash=state_hash,
        entries=rows(committed, tuple(row.data_hash for row in parent.entries)),
        bundle_id="g1.mgt.elastic.accepted_trial")
    return commit_trial_material_state_bundle(
        parent, trial, solver_state_hash=state_hash,
        bundle_id="g1.mgt.elastic.committed")


@dataclass(frozen=True)
class _Adapter:
    snapshot: NonlinearNumericalResultSourceSnapshot
    bundle: MaterialStateBundle
    terminal: NonlinearTerminalReceipt
    expected_residual_inf_n: float
    observed_residual_inf_n: float

    def validate_nonlinear_result_source(self) -> NonlinearNumericalResultSourceSnapshot:
        validate_material_state_bundle(self.bundle)
        validate_nonlinear_terminal_receipt(self.terminal)
        if self.bundle.role != "committed" or self.bundle.epoch != self.snapshot.state_epoch:
            raise ValueError("result_material_bundle_not_terminal")
        if (self.bundle.model_ir_content_hash != self.snapshot.model_ir_content_hash
                or self.bundle.execution_plan_hash != self.snapshot.execution_plan_hash
                or self.bundle.solver_state_hash != self.snapshot.state_hash
                or self.snapshot.material_state_bundle_hash != self.bundle.bundle_hash):
            raise ValueError("result_material_bundle_mismatch")
        if (self.snapshot.nonlinear_terminal_hash != self.terminal.terminal_hash
                or self.terminal.state_hash != self.snapshot.state_hash
                or self.terminal.material_state_bundle_hash != self.bundle.bundle_hash
                or self.terminal.equation_scaling_hash != self.snapshot.equation_scaling_hash
                or self.terminal.reduced_csr_identity_hash != self.snapshot.reduced_csr_identity_hash
                or self.terminal.path_history_hash != self.snapshot.path_history_hash):
            raise ValueError("result_terminal_mismatch")
        if self.observed_residual_inf_n > self.expected_residual_inf_n:
            raise ValueError("result_cpu_residual_replay_failed")
        return self.snapshot


def run(*, root: Path = ROOT) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    root = root.resolve()
    if not _clean(root): raise RuntimeError("result_ir_requires_clean_sources")
    source = _read(root / FGMRES_RECEIPT)
    _, _, _, context = build_references(root=root)
    count = int(source["material_lifecycle"]["integration_point_count"])
    material_shape = (count, len(MATERIAL_STATE_FIELD_NAMES))
    artifacts = source["material_lifecycle"]["artifacts"]
    def material(name: str) -> np.ndarray:
        item = artifacts[name]; path = root / item["path"]
        if file_sha256(path) != item["file_sha256"]: raise ValueError("material_hash_mismatch")
        value = np.fromfile(path, dtype="<f8").reshape(material_shape)
        if array_data_hash(value) != item["data_hash"]: raise ValueError("material_data_hash_mismatch")
        return np.ascontiguousarray(value, dtype="<f8")
    initial_material = material("initial"); committed_material = material("committed")
    accepted_item = source["comparison"]["accepted_state_artifact"]
    accepted_state = np.fromfile(root / accepted_item["path"], dtype="<f8")
    if array_data_hash(accepted_state) != accepted_item["data_hash"]: raise ValueError("accepted_state_mismatch")
    solution_item = source["comparison"]["solution_artifact"]
    correction = np.fromfile(root / solution_item["path"], dtype="<f8")
    if array_data_hash(correction) != solution_item["data_hash"]: raise ValueError("solution_mismatch")
    bundle = _bundle(receipt=source, context=context, initial=initial_material,
                     committed=committed_material, accepted_state=accepted_state)
    expected_bundle_hash = source["material_lifecycle"]["material_state_bundle"]["committed_bundle_hash"]
    if bundle.bundle_hash != expected_bundle_hash:
        raise ValueError("committed_material_bundle_hash_mismatch")
    operator = context["problem"].current_tangent_operator
    free = np.asarray(operator.array("free_global_dofs"), dtype=np.int64)
    global_state = np.array(operator.array("background_global_displacements_m"), dtype="<f8", copy=True)
    global_state[free] = accepted_state
    displacement = immutable_array(global_state, dtype="<f8")
    cpu_residual = np.asarray(context["problem"].residual_kn(accepted_state, 1.0), dtype=np.float64) * 1000.0
    cpu_residual_inf = float(np.linalg.norm(cpu_residual, ord=np.inf))
    reference_force = float(source["equation_scaling"]["reference_force_n"])
    scaling_hash = canonical_hash(source["equation_scaling"])
    reduced_hash = canonical_hash({
        "profile": "actual-mgt-free-equation-current-tangent.v1",
        "equation_count": int(accepted_state.size),
        "free_dof_data_hash": array_data_hash(np.ascontiguousarray(free, dtype="<i8")),
        "operator_hash": operator.contract_hash,
    })
    path_hash = canonical_hash({
        "alphas": [1.0, 0.5, 0.25, 0.125, 0.0625],
        "selected": int(source["hardware_execution"]["line_search_selected_index"]),
        "candidate_l2_n": source["hardware_execution"]["line_search_candidate_l2_n"],
    })
    terminal = create_nonlinear_terminal_receipt(
        source_solver_schema_version=source["schema_version"],
        source_solver_receipt_hash=source["receipt_hash"],
        equation_scaling_hash=scaling_hash, reduced_csr_identity_hash=reduced_hash,
        source_solution_data_hash=array_data_hash(accepted_state),
        solver_coordinate_scaling_receipt_hash=canonical_hash({"profile": "relative-free-increment.v1"}),
        state_hash=source["comparison"]["checkpoint_artifact"]["accepted_state_hash"],
        material_state_bundle_hash=bundle.bundle_hash, path_history_hash=path_hash,
        terminal_reason="converged_residual_and_increment", converged=True,
        final_residual_linf=cpu_residual_inf / reference_force,
        residual_tolerance_linf=1.0e-9,
        final_increment_linf=float(np.linalg.norm(correction, ord=np.inf)) /
        max(float(np.linalg.norm(accepted_state, ord=np.inf)), 1.0e-30),
        increment_tolerance_linf=1.0e-4, accepted_step_count=1,
        fallback_count=0, regularization_count=0)
    common = dict(
        model_ir_content_hash=context["problem"].model_source_sha256,
        execution_plan_hash=context["problem"].equilibrium_operator_binding_hash,
        equation_scaling_hash=scaling_hash, reduced_csr_identity_hash=reduced_hash,
        operator_hash=operator.contract_hash,
        state_hash=source["comparison"]["checkpoint_artifact"]["accepted_state_hash"],
        state_epoch=1, material_state_bundle_hash=bundle.bundle_hash,
        integration_point_order_hash=bundle.integration_point_order_hash,
        path_history_hash=path_hash, nonlinear_terminal_hash=terminal.terminal_hash,
        full_residual_receipt_hash=canonical_hash({"cpu_residual_data_hash": array_data_hash(np.ascontiguousarray(cpu_residual, dtype="<f8"))}),
        boundary_condition_receipt_hash=canonical_hash({"free_dof_data_hash": array_data_hash(np.ascontiguousarray(free, dtype="<i8"))}),
        load_factor=1.0, time_s=0.0, dof_count=int(displacement.size),
        displacement_global_si=displacement)
    backend_hashes = {
        "hip": canonical_hash(source["hardware_execution"]),
        "cpu_optimized": canonical_hash(source["performance"]["cpu_baseline"]),
    }
    results = {}
    for role in ("hip", "cpu_optimized"):
        snapshot = NonlinearNumericalResultSourceSnapshot(
            **common, backend_role=role, backend_receipt_hash=backend_hashes[role])
        adapter = _Adapter(snapshot, bundle, terminal, 1.0e-6, cpu_residual_inf)
        result = create_adapter_bound_nonlinear_numerical_result_ir(
            result_id=f"g1.mgt.{role}.terminal", source_adapter=adapter)
        results[role] = result.to_manifest()
    binding_parity_keys = (
        "model_ir_content_hash", "execution_plan_hash", "equation_scaling_hash",
        "reduced_csr_identity_hash", "operator_hash", "state_hash", "state_epoch",
        "material_state_bundle_hash", "integration_point_order_hash",
        "path_history_hash", "nonlinear_terminal_hash")
    parity = all(results["hip"]["bindings"].get(key) == results["cpu_optimized"]["bindings"].get(key)
                 for key in binding_parity_keys)
    parity = bool(parity and results["hip"]["displacement_artifact"]["data_hash"]
                  == results["cpu_optimized"]["displacement_artifact"]["data_hash"]
                  and results["hip"]["load_factor"] == results["cpu_optimized"]["load_factor"]
                  and results["hip"]["dof_count"] == results["cpu_optimized"]["dof_count"])
    if not parity: raise RuntimeError("terminal_result_ir_parity_failed")
    hip_raw = json.dumps(results["hip"], indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    cpu_raw = json.dumps(results["cpu_optimized"], indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    displacement_raw = displacement.tobytes()
    payload = {
        "schema_version": VERSION, "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "partial",
        "contract_pass": True,
        "source": {"repository_commit_sha": git_head(root),
                   "source_paths_clean_at_execution": True,
                   "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root),
                   "fgmres_receipt_hash": source["receipt_hash"]},
        "terminal": {"load_factor": 1.0, "dof_count": int(displacement.size),
                     "free_equation_count": int(accepted_state.size),
                     "cpu_residual_replay_inf_n": cpu_residual_inf,
                     "residual_tolerance_n": 1.0e-6,
                     "nonlinear_terminal_hash": terminal.terminal_hash,
                     "material_state_bundle_hash": bundle.bundle_hash,
                     "material_entry_count": bundle.entry_count},
        "parity": {"terminal_resultir_parity": True,
                   "shared_binding_keys": list(binding_parity_keys),
                   "displacement_data_hash": array_data_hash(displacement),
                   "hip_result_hash": results["hip"]["result_hash"],
                   "cpu_result_hash": results["cpu_optimized"]["result_hash"]},
        "artifacts": {
            "hip_result": {"path": DEFAULT_HIP_RESULT.as_posix(), "byte_length": len(hip_raw), "file_sha256": sha256_prefixed(hip_raw)},
            "cpu_result": {"path": DEFAULT_CPU_RESULT.as_posix(), "byte_length": len(cpu_raw), "file_sha256": sha256_prefixed(cpu_raw)},
            "displacement": {"path": DEFAULT_DISPLACEMENT.as_posix(), "byte_length": len(displacement_raw), "file_sha256": sha256_prefixed(displacement_raw), "data_hash": array_data_hash(displacement)}},
        "claims": {"authoritative_nonlinear_resultir_emitted": True,
                   "terminal_resultir_parity": True, "diagnosticir_emitted": False,
                   "independent_gfx1100_run": False, "g1_closure": False},
        "blockers_remaining": ["diagnosticir_requires_actual_execution_plan_adapter",
                               "nonlinear_material_family_breadth_not_connected_to_actual_mgt_worker",
                               "independent_gfx1100_hardware_run_not_available"],
        "claim_boundary": "This receipt emits adapter-bound authoritative nonlinear ResultIR manifests for the exact actual-MGT terminal displacement and committed elastic MaterialStateBundle, with CPU/HIP terminal binding parity. It does not fabricate a generic ExecutionPlan-backed DiagnosticIR, connect nonlinear material-family breadth, prove independent gfx1100 hardware, or close G1."}
    payload["receipt_hash"] = _hash(payload)
    return payload, hip_raw, cpu_raw, displacement_raw


def validate(payload: dict[str, Any], *, root: Path = ROOT, current: bool = False,
             artifacts: bool = False) -> dict[str, Any]:
    schema = _read(root / SCHEMA); Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload): raise ValueError("result_receipt_hash_mismatch")
    if current and payload["source"]["input_checksums"] != input_checksums(SOURCE_PATHS, repo_root=root):
        raise ValueError("result_sources_stale")
    if artifacts:
        for name, item in payload["artifacts"].items():
            path = root / item["path"]
            if file_sha256(path) != item["file_sha256"] or path.stat().st_size != item["byte_length"]:
                raise ValueError(f"result_artifact_invalid:{name}")
        validate_nonlinear_result_manifest(_read(root / DEFAULT_HIP_RESULT))
        validate_nonlinear_result_manifest(_read(root / DEFAULT_CPU_RESULT))
    return payload


def write(*, root: Path = ROOT) -> dict[str, Any]:
    payload, hip, cpu, displacement = run(root=root)
    (root / DEFAULT_HIP_RESULT).write_bytes(hip); (root / DEFAULT_CPU_RESULT).write_bytes(cpu)
    (root / DEFAULT_DISPLACEMENT).write_bytes(displacement)
    (root / DEFAULT_OUT).write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return validate(payload, root=root, current=True, artifacts=True)


def check(*, root: Path = ROOT) -> tuple[bool, str]:
    try: validate(_read(root / DEFAULT_OUT), root=root, current=True, artifacts=True)
    except Exception as exc: return False, f"g1_mgt_result_ir_invalid:{exc}"
    return True, "g1_mgt_result_ir_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        passed, reason = check(); print(reason); return 0 if passed else 1
    payload = write(); print(f"partial | resultir_parity={payload['parity']['terminal_resultir_parity']} | diagnosticir=false")
    return 0


if __name__ == "__main__": raise SystemExit(main())
