"""Bounded RC control API with whole accepted-history transition recovery.

This profile uses the existing RC compiler/assembler and authored control path.
It does not wrap augmented or cyclic results in the monotonic-load J1--J5 chain.
The artifact validator explicitly reruns the original request, including restart
prefix solves; local serialization alone never establishes source reachability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable

import numpy as np

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.nonlinear_fiber_frame import (
    PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
    _compile,
    _node_displacement_rows,
    _reaction_rows,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    CONTROL_RESTART_MAX_BYTES,
    StatefulFiberFrame2DControlExecutionError,
    StatefulFiberFrame2DControlPathResult,
    StatefulFiberFrame2DControlRestartError,
    _decode_restart,
    _integer,
    _targets,
    run_stateful_fiber_frame2d_control_path,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    _same_vector,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FIBER_FRAME_FORCE_TO_SI,
    FIBER_FRAME_MOMENT_TO_SI,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.model.schema import CanonicalModel


BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION = (
    "bounded-rc-fiber-direct-control-result.v1"
)
BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES = 512 * 1024 * 1024
_CLAIMS = {
    "experimental_small_displacement_rc_control": True,
    "public_j1_j5_authority": False,
    "independent_physical_validation": False,
    "general_cyclic_validation": False,
    "global_capacity_verified": False,
    "design_authority": False,
    "performance_improvement": False,
    "production_promotion_eligible": False,
    "release_approved": False,
    "hashes_authenticate_source": False,
}


def _json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _bytes(value: Any, limit: int, name: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{name} must be bytes-like")
    raw = bytes(value)
    if not raw or len(raw) > limit:
        raise ValueError(f"{name} is empty or exceeds its byte bound")
    return raw


def _zero_work() -> dict[str, int]:
    return {
        "attempted_step_count": 0,
        "known_linear_solve_count": 0,
        "known_newton_iteration_count": 0,
        "unknown_solver_work_attempt_count": 0,
    }


class BoundedRCFiberDirectControlArtifactError(ValueError):
    """An export failed after execution; retain its actual work and source scope."""

    def __init__(self, message, payload):
        super().__init__(message)
        self._report = _json(
            {
                "status": "artifact_export_failed",
                "failure": message,
                "model": payload["model"],
                "request": payload["request"],
                "computed_path_status": payload["status"],
                "execution_metrics": payload["metrics"],
                "contract_pass": False,
                "state_or_restart_export_available": False,
                "claims": dict(_CLAIMS),
            }
        )

    def to_dict(self):
        return json.loads(self._report)


def _canonical6(source, *, forces=False):
    values = np.asarray(source, dtype=np.float64).reshape((-1, 3))
    result = np.zeros((len(values), 6), dtype=np.float64)
    result[:, (0, 1, 5)] = values
    if forces:
        result[:, :3] *= FIBER_FRAME_FORCE_TO_SI
        result[:, 3:] *= FIBER_FRAME_MOMENT_TO_SI
    return result


def _response_rows(compiled, assembly, checkpoint, step_hash):
    """Project a freshly replayed original transition, using original SI conventions."""
    members, sections, fibers = [], [], []
    for member, section, row in zip(
        compiled.problem.members,
        compiled.section_by_member,
        assembly.member_assemblies,
        strict=True,
    ):
        response = row.response
        force = response.internal_force_local * 1000.0
        members.append(
            {
                "member_id": member.member_id,
                "node_i": compiled.node_ids[member.node_i],
                "node_j": compiled.node_ids[member.node_j],
                "local_end_i": dict(
                    zip(("FX_N", "FY_N", "MZ_Nm"), map(float, force[:3]), strict=True)
                ),
                "local_end_j": dict(
                    zip(("FX_N", "FY_N", "MZ_Nm"), map(float, force[3:]), strict=True)
                ),
                "dissipated_energy_MJ": response.dissipated_energy_mj,
            }
        )
        for ip, state_response in enumerate(response.section_responses):
            section.validate_state(state_response.state)
            sections.append(
                {
                    "member_id": member.member_id,
                    "integration_point_index": ip,
                    "xi": float(response.integration_point_xi[ip]),
                    "weight": float(response.integration_point_weights[ip]),
                    "axial_strain": state_response.axial_strain,
                    "curvature_z_per_m": state_response.curvature_z_per_m,
                    "axial_force_N": state_response.axial_force_kn
                    * FIBER_FRAME_FORCE_TO_SI,
                    "moment_z_Nm": state_response.moment_z_kn_m
                    * FIBER_FRAME_MOMENT_TO_SI,
                    "dissipated_energy_MJ_per_m": state_response.dissipated_energy_mj_per_m,
                    "section_state_hash": state_response.state.state_hash,
                }
            )
            for index, (fiber, state) in enumerate(
                zip(section.fibers, state_response.state.fiber_states, strict=True)
            ):
                fibers.append(
                    {
                        "member_id": member.member_id,
                        "integration_point_index": ip,
                        "fiber_index": index,
                        "fiber_id": fiber.fiber_id,
                        "material_kind": fiber.material_kind,
                        "y_m": fiber.y_m,
                        "area_m2": fiber.area_m2,
                        "strain": float(state_response.fiber_strains[index]),
                        "stress_MPa": float(state_response.fiber_stresses_mpa[index]),
                        "dissipated_energy_density_MJ_per_m3": state.dissipated_energy_density_mj_per_m3,
                        "material_state": state.to_dict(),
                    }
                )
    return {
        "epoch": checkpoint.epoch,
        "step_index": checkpoint.step_index,
        "load_factor": checkpoint.load_factor,
        "parent_checkpoint_hash": checkpoint.parent_state_hash,
        "checkpoint_hash": checkpoint.state_hash,
        "source_step_hash": step_hash,
        "replayed_assembly_hash": _hash(_json(assembly.to_dict())),
        "node_displacements": list(
            _node_displacement_rows(
                compiled, _canonical6(assembly.global_displacements)
            )
        ),
        "support_reactions": list(
            _reaction_rows(
                compiled, _canonical6(assembly.reactions_global, forces=True)
            )
        ),
        "member_end_forces": members,
        "section_results": sections,
        "fiber_results": fibers,
        "material_point_count": len(fibers),
        "recovery_scope": "exact_previous_parent_original_newton_coordinates_constitutive_transition",
    }


def _recover_step(compiled, parent, step, cfg, control_global_dof, target, source_hash):
    """Recover one original transition without retaining earlier response rows."""
    problem = compiled.problem
    if (
        not step.committed
        or step.parent_checkpoint.canonical_bytes() != parent.canonical_bytes()
    ):
        raise ValueError("response history parent chain mismatch")
    epoch = parent.epoch + 1
    # Never invert rounded physical checkpoint rotations to recover q.
    coordinates = step.trial_solution.free_displacements_m
    load_factor = float(coordinates[-1]) / cfg.load_factor_coordinate_scale_m
    fresh = assemble_stateful_fiber_frame2d(
        problem,
        parent,
        target_load_factor=load_factor,
        trial_free_coordinates_m=coordinates[:-1],
    )
    child = StatefulFiberFrame2DCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=source_hash,
        epoch=epoch,
        step_index=parent.step_index + 1,
        load_factor=load_factor,
        parent_state_hash=parent.state_hash,
        global_displacements=tuple(float(v) for v in fresh.global_displacements),
        element_states=fresh.trial_element_states,
    )
    validate_stateful_fiber_frame2d_checkpoint(problem, child)
    if (
        problem.contract_hash != source_hash
        or child.canonical_bytes() != step.accepted_checkpoint.canonical_bytes()
        or _json(fresh.to_dict()) != _json(step.trial_assembly.to_dict())
        or not _same_vector(
            fresh.generalized_coordinates_m[list(problem.free_global_dofs)],
            coordinates[:-1],
        )
    ):
        raise ValueError(
            "response transition differs from original solver/checkpoint source"
        )
    relative = (
        float(np.linalg.norm(fresh.residual_kn, ord=np.inf))
        / problem.reference_force_scale()
    )
    error = float(fresh.global_displacements[control_global_dof]) - target
    if relative > cfg.newton.residual_tolerance or abs(error) > cfg.control_tolerance_m:
        raise ValueError("replayed response equilibrium/control gate failed")
    return child, _response_rows(compiled, fresh, child, step.step_hash)


def _recover_history(compiled, path, cfg, payload, progress):
    problem = compiled.problem
    source_hash = problem.contract_hash
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    history = []
    all_steps = (*path.replayed_steps, *path.steps)
    for step in all_steps:
        if not step.committed:
            break
        if step.parent_checkpoint.canonical_bytes() != parent.canonical_bytes():
            raise ValueError("response history parent chain mismatch")
        epoch = parent.epoch + 1
        progress["response_reassembly_attempts"] += 1
        progress["current_epoch"] = epoch
        child, response = _recover_step(
            compiled,
            parent,
            step,
            cfg,
            payload["scope"]["control_global_dof"],
            payload["accepted_target_prefix_m"][epoch - 1],
            source_hash,
        )
        history.append(response)
        progress["response_reassembly_verified_count"] += 1
        parent = child
    if (
        len(history) != len(payload["accepted_target_prefix_m"])
        or parent.canonical_bytes() != path.final_checkpoint.canonical_bytes()
        or _json(path.to_dict()) != _json(payload)
    ):
        raise ValueError("response history coverage or source changed during recovery")
    progress["current_epoch"] = None
    return history


def _attach_recovered_path(payload, compiled, path, cfg):
    try:
        if type(path) is not StatefulFiberFrame2DControlPathResult:
            raise ValueError("control path result type mismatch")
        path_payload = path.to_dict()
    except Exception as exc:
        # Retain a returned execution's original receipt snapshot even when it
        # no longer passes its source checks. Its claimed work is not promoted
        # to verified counts, and physical/restart export remains unavailable.
        raw_snapshot = None
        if type(path) is StatefulFiberFrame2DControlPathResult:
            try:
                raw_snapshot = strict_json_object_bytes(
                    path._payload,
                    maximum_bytes=BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES,
                )
            except Exception:
                pass
        payload["status"] = "invalid_execution"
        payload["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stage": "returned_path_source_validation",
            "unvalidated_path_snapshot": raw_snapshot,
        }
        payload["metrics"]["control_work"] = None
        payload["metrics"]["unavailable_execution_work"] = True
        return None
    payload["path"] = path_payload
    payload["metrics"]["control_work"] = path_payload["metrics"]["total_work"]
    try:
        history = _recover_history(
            compiled, path, cfg, path_payload, payload["metrics"]
        )
        checkpoint = path.restart_artifact()
        restored, prefix, terminal = _decode_restart(
            checkpoint, compiled.problem, path_payload["scope"]
        )
        if (
            restored["artifact_hash"] != path_payload["restart_artifact_hash"]
            or _json(list(prefix)) != _json(path_payload["accepted_target_prefix_m"])
            or terminal.canonical_bytes() != path.final_checkpoint.canonical_bytes()
        ):
            raise ValueError("restart artifact differs from recovered path source")
    except Exception as exc:
        payload["status"] = "invalid_recovery"
        payload["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stage": "whole_accepted_history_recovery",
        }
        return None
    payload["response_history"] = history
    payload["terminal_response"] = history[-1] if history else None
    payload["metrics"]["whole_accepted_history_recovered"] = True
    payload["status"] = path_payload["status"]
    # Genesis-only verification cannot prove a positive accepted response.
    payload["contract_pass"] = path_payload["status"] == "ready" and bool(history)
    payload["checkpoint"] = {
        "sha256": _hash(checkpoint),
        "byte_length": len(checkpoint),
    }
    return checkpoint


@dataclass(frozen=True)
class BoundedRCFiberDirectControlResult:
    _payload: bytes = field(repr=False)
    _checkpoint_bytes: bytes | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        if type(self._payload) is not bytes:
            raise ValueError("result snapshot must be immutable bytes")
        payload = strict_json_object_bytes(
            self._payload,
            maximum_bytes=BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES,
        )
        body = {k: v for k, v in payload.items() if k != "result_hash"}
        if payload.get(
            "schema_version"
        ) != BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION or payload.get(
            "result_hash"
        ) != _hash(_json(body)):
            raise ValueError("result snapshot hash/schema mismatch")
        binding = payload["checkpoint"]
        if self._checkpoint_bytes is None:
            if binding is not None:
                raise ValueError("result checkpoint snapshot missing")
        elif type(self._checkpoint_bytes) is not bytes or binding != {
            "sha256": _hash(self._checkpoint_bytes),
            "byte_length": len(self._checkpoint_bytes),
        }:
            raise ValueError("result checkpoint snapshot binding mismatch")
        return payload

    @property
    def status(self):
        return self.to_dict()["status"]

    @property
    def contract_pass(self):
        return self.to_dict()["contract_pass"]

    @property
    def result_hash(self):
        return self.to_dict()["result_hash"]

    def result_artifact_bytes(self) -> bytes:
        self.to_dict()
        return self._payload

    def checkpoint_artifact_bytes(self) -> bytes:
        self.to_dict()
        if self._checkpoint_bytes is None:
            raise ValueError("no verified accepted restart artifact is available")
        return self._checkpoint_bytes


@dataclass(frozen=True)
class BoundedRCFiberDirectControlValidationReport:
    _payload: bytes = field(repr=False)

    def to_dict(self):
        return json.loads(self._payload)

    @property
    def artifact_contract_pass(self):
        return self.to_dict()["artifact_contract_pass"]

    @property
    def contract_pass(self):
        return self.to_dict()["contract_pass"]

    @property
    def status(self):
        return self.to_dict()["status"]


def _prepare(
    model,
    targets_m,
    control_global_dof,
    config,
    allow_reversals,
    maximum_reversals,
    maximum_targets,
    restart,
):
    if type(model) is not CanonicalModel:
        raise ValueError("model must be an exact CanonicalModel")
    snapshot = model.detached_analysis_snapshot()
    # Validate finite, serializable model provenance before compilation/solving.
    _json(snapshot.to_dict())
    cfg = (
        config
        if config is not None
        else StatefulFiberFrame2DDisplacementControlConfig()
    )
    if type(cfg) is not StatefulFiberFrame2DDisplacementControlConfig:
        raise ValueError(
            "config must be an exact StatefulFiberFrame2DDisplacementControlConfig"
        )
    _integer(control_global_dof, "control_global_dof", 47)
    _integer(maximum_targets, "maximum_targets", 255, 1)
    _integer(maximum_reversals, "maximum_reversals", 254)
    if type(allow_reversals) is not bool or (not allow_reversals and maximum_reversals):
        raise ValueError("reversals require explicit opt-in and budget")
    targets = _targets(targets_m, maximum_targets)
    resume = (
        None
        if restart is None
        else _bytes(restart, CONTROL_RESTART_MAX_BYTES, "restart")
    )
    if not targets and resume is None:
        raise ValueError("empty targets require an explicit restart")
    request = {
        "targets_m": list(targets),
        "control_global_dof": control_global_dof,
        "configuration": cfg.to_manifest(),
        "configuration_hash": cfg.contract_hash,
        "allow_reversals": allow_reversals,
        "maximum_reversals": maximum_reversals,
        "maximum_targets": maximum_targets,
        "restart_input_sha256": None if resume is None else _hash(resume),
    }
    model_binding = {
        "canonical_model_checksum": snapshot.canonical_model_checksum,
        "input_checksum": snapshot.input_checksum,
        "source_format": snapshot.source_format,
        "compiler_profile": PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
    }
    return snapshot, targets, cfg, resume, request, model_binding


def analyze_bounded_rc_fiber_direct_control(
    model: CanonicalModel,
    targets_m: Iterable[float],
    *,
    control_global_dof: int,
    config: StatefulFiberFrame2DDisplacementControlConfig | None = None,
    allow_reversals: bool = False,
    maximum_reversals: int = 0,
    maximum_targets: int = 255,
    restart: bytes | bytearray | memoryview | None = None,
) -> BoundedRCFiberDirectControlResult:
    snapshot, targets, cfg, resume, request, binding = _prepare(
        model,
        targets_m,
        control_global_dof,
        config,
        allow_reversals,
        maximum_reversals,
        maximum_targets,
        restart,
    )
    compiled, unsupported, warnings = _compile(snapshot)
    payload = {
        "schema_version": BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION,
        "status": "unsupported",
        "contract_pass": False,
        "model": binding,
        "request": request,
        "control": None,
        "path": None,
        "response_history": [],
        "terminal_response": None,
        "checkpoint": None,
        "unsupported_features": unsupported,
        "warnings": warnings,
        "failure": None,
        "claims": dict(_CLAIMS),
        "metrics": {
            "control_work": _zero_work(),
            "response_reassembly_attempts": 0,
            "response_reassembly_verified_count": 0,
            "current_epoch": None,
            "response_history_scope": "cumulative_accepted_prefix",
            "whole_accepted_history_recovered": False,
            "explicit_validation_solver_replay_performed": False,
        },
    }
    checkpoint = None
    if compiled is not None:
        problem = compiled.problem
        payload["model"]["problem_contract_hash"] = problem.contract_hash
        if control_global_dof >= problem.global_dof_count:
            raise ValueError("control_global_dof is outside compiled model")
        payload["control"] = {
            "global_dof": control_global_dof,
            "node_id": compiled.node_ids[control_global_dof // 3],
            "component": ("UX", "UY", "RZ")[control_global_dof % 3],
            "unit": "m",
        }
        try:
            path = run_stateful_fiber_frame2d_control_path(
                problem,
                targets,
                control_global_dof=control_global_dof,
                config=cfg,
                allow_reversals=allow_reversals,
                maximum_reversals=maximum_reversals,
                maximum_targets=maximum_targets,
                restart=resume,
            )
        except (
            StatefulFiberFrame2DControlExecutionError,
            StatefulFiberFrame2DControlRestartError,
        ) as exc:
            failure = exc.to_dict()
            payload["status"] = "invalid_execution"
            payload["failure"] = failure
            payload["metrics"]["control_work"] = failure.get(
                "total_work", failure.get("replay_work")
            )
            if payload["metrics"]["control_work"] is None:
                payload["metrics"]["unavailable_execution_work"] = True
        else:
            checkpoint = _attach_recovered_path(payload, compiled, path, cfg)
    try:
        payload["result_hash"] = _hash(_json(payload))
        encoded = _json(payload)
        if len(encoded) > BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES:
            raise ValueError("result exceeds bounded artifact size")
    except (ValueError, TypeError, OverflowError) as exc:
        raise BoundedRCFiberDirectControlArtifactError(str(exc), payload) from exc
    return BoundedRCFiberDirectControlResult(encoded, checkpoint)


def validate_bounded_rc_fiber_direct_control_artifacts(
    model: CanonicalModel,
    targets_m: Iterable[float],
    *,
    result: bytes | bytearray | memoryview | dict,
    checkpoint: bytes | bytearray | memoryview | None = None,
    control_global_dof: int,
    config: StatefulFiberFrame2DDisplacementControlConfig | None = None,
    allow_reversals: bool = False,
    maximum_reversals: int = 0,
    maximum_targets: int = 255,
    restart: bytes | bytearray | memoryview | None = None,
) -> BoundedRCFiberDirectControlValidationReport:
    """Verify against a fresh complete source execution, never a supplied success flag."""
    report: dict[str, Any] = {
        "schema_version": "bounded-rc-fiber-direct-control-validation.v1",
        "status": "invalid_artifact",
        "artifact_contract_pass": False,
        "contract_pass": False,
        "physical_path_complete": False,
        "fresh_source_execution_invoked": False,
        "solver_replay_performed": False,
        "unavailable_execution_work": False,
        "replay_control_work": _zero_work(),
        "response_reassembly_attempts": 0,
        "response_reassembly_verified_count": 0,
        "verified_result_hash": None,
        "errors": [],
        "claims": dict(_CLAIMS),
        "verification_scope": "fresh_complete_request_solver_and_original_transition_replay",
    }
    expected = None
    try:
        # Snapshot every mutable caller input before starting source verification.
        encoded = (
            _json(result)
            if type(result) is dict
            else _bytes(
                result, BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES, "result"
            )
        )
        supplied = strict_json_object_bytes(
            encoded, maximum_bytes=BOUNDED_RC_FIBER_DIRECT_CONTROL_RESULT_MAX_BYTES
        )
        supplied_checkpoint = (
            None
            if checkpoint is None
            else _bytes(checkpoint, CONTROL_RESTART_MAX_BYTES, "checkpoint")
        )
        snapshot, targets, cfg, resume, request, model_binding = _prepare(
            model,
            targets_m,
            control_global_dof,
            config,
            allow_reversals,
            maximum_reversals,
            maximum_targets,
            restart,
        )
        if (
            supplied.get("schema_version")
            != BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION
        ):
            raise ValueError("result schema mismatch")
        if _json(supplied.get("request")) != _json(request):
            raise ValueError("result request/restart source mismatch")
        actual_model = supplied.get("model")
        if type(actual_model) is not dict or any(
            _json(actual_model.get(key)) != _json(value)
            for key, value in model_binding.items()
        ):
            raise ValueError("result model source mismatch")
        if supplied.get("result_hash") != _hash(
            _json({k: v for k, v in supplied.items() if k != "result_hash"})
        ):
            raise ValueError("result content hash mismatch")
        report["fresh_source_execution_invoked"] = True
        report["solver_replay_performed"] = None
        report["replay_control_work"] = None
        report["response_reassembly_attempts"] = None
        report["response_reassembly_verified_count"] = None
        report["unavailable_execution_work"] = True
        expected = analyze_bounded_rc_fiber_direct_control(
            snapshot,
            targets,
            control_global_dof=control_global_dof,
            config=cfg,
            allow_reversals=allow_reversals,
            maximum_reversals=maximum_reversals,
            maximum_targets=maximum_targets,
            restart=resume,
        )
        regenerated = expected.to_dict()
        report["replay_control_work"] = regenerated["metrics"]["control_work"]
        if report["replay_control_work"] is not None:
            report["solver_replay_performed"] = (
                report["replay_control_work"]["attempted_step_count"] > 0
            )
            report["unavailable_execution_work"] = False
        for name in (
            "response_reassembly_attempts",
            "response_reassembly_verified_count",
        ):
            report[name] = regenerated["metrics"][name]
        if _json(supplied) != expected.result_artifact_bytes():
            raise ValueError("result differs from fresh source execution/recovery")
        if supplied_checkpoint != expected._checkpoint_bytes:
            raise ValueError("checkpoint differs from fresh source execution")
        report.update(
            status="valid_artifact",
            artifact_contract_pass=True,
            contract_pass=regenerated["contract_pass"],
            physical_path_complete=regenerated["contract_pass"],
            verified_result_hash=regenerated["result_hash"],
        )
    except Exception as exc:
        report["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        if type(exc) is BoundedRCFiberDirectControlArtifactError:
            failure = exc.to_dict()
            report["execution_failure"] = failure
            metrics = failure["execution_metrics"]
            report["replay_control_work"] = metrics["control_work"]
            for name in (
                "response_reassembly_attempts",
                "response_reassembly_verified_count",
            ):
                report[name] = metrics[name]
            if metrics["control_work"] is not None:
                report["solver_replay_performed"] = (
                    metrics["control_work"]["attempted_step_count"] > 0
                )
                report["unavailable_execution_work"] = False
    return BoundedRCFiberDirectControlValidationReport(_json(report))
