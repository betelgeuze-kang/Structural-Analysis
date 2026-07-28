"""Bounded direct displacement control for stateful sparse Frame3D models.

The proportional load factor is solved together with one free translational
control coordinate.  Equilibrium and the control equation are assembled in the
same dimensionless 6DOF scaling used by the load-control solver.  Every trial
is evaluated from one immutable accepted checkpoint and only a fully
reassembled converged state is committed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, cast

import numpy as np
from scipy.sparse import bmat, csr_matrix

from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    FactorizationDiagnostic,
    StatefulCorotationalFrame3DSparseAssembly,
    StatefulCorotationalFrame3DSparseCheckpoint,
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    _checkpoint_parent_signature,
    _equation_scaling,
    _linf,
    _make_checkpoint,
    _require_parent_unchanged,
    _scaled_increment_tolerance,
    _scaled_residual_tolerance,
    _solve_sparse_tangent,
    _translation_component_norm,
    assemble_stateful_corotational_frame3d_sparse,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    immutable_array,
)
from structural_analysis.materials.admissibility import (
    MaterialPathNotAdmissibleError,
)
from structural_analysis.solvers.equation_scaling import (
    EquationScaling6DOF,
    EquationScaling6DOFTransform,
)
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    ScalableSparseFactorizationError,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SparseFactorizationError,
)


STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE = (
    "stateful-corotational-frame3d-direct-displacement-control.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-direct-displacement-control-result.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY = (
    "Experimental bounded sparse Frame3D direct displacement-control candidate "
    "for one free translational DOF and proportional nodal reference loading. "
    "Rotational control, multiple control equations, prescribed-displacement "
    "patterns, arc length, follower loads, production-scale authority, "
    "independent external V&V, and release promotion remain open."
)


class StatefulCorotationalFrame3DDisplacementControlError(
    StatefulCorotationalFrame3DSparseError
):
    """Fail-closed direct-control trial or commit error."""


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlConfig:
    solver_config: StatefulCorotationalFrame3DSparseConfig = field(
        default_factory=StatefulCorotationalFrame3DSparseConfig
    )
    control_relative_tolerance: float = 1.0e-8
    control_absolute_tolerance_m: float = 1.0e-10
    load_factor_increment_tolerance: float = 1.0e-10
    maximum_path_targets: int = 256

    def __post_init__(self) -> None:
        if type(self.solver_config) is not StatefulCorotationalFrame3DSparseConfig:
            raise ValueError(
                "solver_config must be an exact "
                "StatefulCorotationalFrame3DSparseConfig"
            )
        for name in (
            "control_relative_tolerance",
            "control_absolute_tolerance_m",
            "load_factor_increment_tolerance",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if (
            type(self.maximum_path_targets) is not int
            or not 1 <= self.maximum_path_targets <= 10_000
        ):
            raise ValueError("maximum_path_targets must be an integer in [1, 10000]")

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
            "solver_contract": self.solver_config.to_manifest(),
            "solver_contract_hash": self.solver_config.contract_hash,
            "control_equation": (
                "one_free_translation_coordinate_equals_explicit_target.v1"
            ),
            "augmented_scaling": (
                "[D_R^-1*R;control_error/u_control_ref],"
                "[D_R^-1*K*D_u,D_R^-1*(-P);"
                "e_control^T*D_u/u_control_ref,0]"
            ),
            "control_relative_tolerance": self.control_relative_tolerance,
            "control_absolute_tolerance_m": self.control_absolute_tolerance_m,
            "load_factor_increment_tolerance": (
                self.load_factor_increment_tolerance
            ),
            "maximum_path_targets": self.maximum_path_targets,
            "globalization": "backtracking_augmented_scaled_merit.v1",
            "regularization_allowed": False,
            "fallback_allowed": False,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlStep:
    step_index: int
    control_global_dof: int
    target_control_displacement_m: float
    solved_load_factor: float
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    equation_scaling: EquationScaling6DOF
    control_reference_m: float
    scaled_control_error: float
    scaled_control_tolerance: float
    augmented_scaled_condition_number: float
    accepted_line_search_alphas: tuple[float, ...]
    convergence_checks: Mapping[str, bool]
    convergence_trace: tuple[Mapping[str, Any], ...]
    reactions: tuple[tuple[int, float], ...]
    factorization_diagnostics: tuple[FactorizationDiagnostic, ...]
    member_results: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "control_global_dof": self.control_global_dof,
            "target_control_displacement_m": (
                self.target_control_displacement_m
            ),
            "solved_load_factor": self.solved_load_factor,
            "checkpoint": self.checkpoint.to_dict(),
            "equation_scaling": self.equation_scaling.to_dict(),
            "control_reference_m": self.control_reference_m,
            "scaled_control_error": self.scaled_control_error,
            "scaled_control_tolerance": self.scaled_control_tolerance,
            "augmented_scaled_condition_number": (
                self.augmented_scaled_condition_number
            ),
            "accepted_line_search_alphas": list(
                self.accepted_line_search_alphas
            ),
            "convergence_checks": dict(self.convergence_checks),
            "convergence_trace": [dict(row) for row in self.convergence_trace],
            "reactions": [list(row) for row in self.reactions],
            "factorization_diagnostics": [
                row.to_manifest() for row in self.factorization_diagnostics
            ],
            "member_results": [dict(row) for row in self.member_results],
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlResult:
    schema_version: str
    profile: str
    model_hash: str
    direct_control_contract_hash: str
    start_checkpoint_hash: str
    control_global_dof: int
    target_control_displacements_m: tuple[float, ...]
    steps: tuple[StatefulCorotationalFrame3DDisplacementControlStep, ...]
    checkpoints: tuple[StatefulCorotationalFrame3DSparseCheckpoint, ...]
    result_hash: str
    exact_checkpoint_resume_supported: bool
    parent_state_immutability_enforced: bool
    regularization_used: bool
    fallback_used: bool
    contract_pass: bool
    claim_boundary: str

    @property
    def final_checkpoint(self) -> StatefulCorotationalFrame3DSparseCheckpoint:
        return self.checkpoints[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "model_hash": self.model_hash,
            "direct_control_contract_hash": self.direct_control_contract_hash,
            "start_checkpoint_hash": self.start_checkpoint_hash,
            "control_global_dof": self.control_global_dof,
            "target_control_displacements_m": list(
                self.target_control_displacements_m
            ),
            "steps": [row.to_dict() for row in self.steps],
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "result_hash": self.result_hash,
            "exact_checkpoint_resume_supported": (
                self.exact_checkpoint_resume_supported
            ),
            "parent_state_immutability_enforced": (
                self.parent_state_immutability_enforced
            ),
            "regularization_used": self.regularization_used,
            "fallback_used": self.fallback_used,
            "contract_pass": self.contract_pass,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class _DirectTrial:
    assembly: StatefulCorotationalFrame3DSparseAssembly
    augmented_residual: np.ndarray
    augmented_tangent: csr_matrix
    control_error: float
    control_reference: float
    scaled_control_error: float
    merit: float


@dataclass(frozen=True)
class _DirectLineSearchSelection:
    alpha: float
    displacement: np.ndarray
    load_factor: float
    attempts: tuple[Mapping[str, Any], ...]


def solve_stateful_corotational_frame3d_displacement_control_path(
    model: StatefulCorotationalFrame3DSparseModel,
    target_control_displacements_m: Iterable[float],
    *,
    control_global_dof: int,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    resume_from: StatefulCorotationalFrame3DSparseCheckpoint | None = None,
) -> StatefulCorotationalFrame3DDisplacementControlResult:
    """Solve an ordered path of explicit translational control targets."""

    if type(model) is not StatefulCorotationalFrame3DSparseModel:
        raise ValueError(
            "model must be an exact StatefulCorotationalFrame3DSparseModel"
        )
    if type(config) is not StatefulCorotationalFrame3DDisplacementControlConfig:
        raise ValueError(
            "config must be an exact "
            "StatefulCorotationalFrame3DDisplacementControlConfig"
        )
    control_free_index = _control_free_index(model, control_global_dof)
    checkpoint = (
        initial_stateful_corotational_frame3d_sparse_checkpoint(
            model,
            config=config.solver_config,
        )
        if resume_from is None
        else validate_stateful_corotational_frame3d_sparse_checkpoint(
            resume_from,
            model=model,
            config=config.solver_config,
            require_equilibrium=True,
        )
    )
    targets = _control_targets(
        target_control_displacements_m,
        after=checkpoint.displacement[control_global_dof],
        maximum_count=config.maximum_path_targets,
    )
    checkpoints = [checkpoint]
    steps: list[StatefulCorotationalFrame3DDisplacementControlStep] = []
    for target in targets:
        parent = checkpoints[-1]
        parent_bytes = canonical_json_bytes(parent.to_dict())
        try:
            step = _solve_direct_control_step(
                model=model,
                config=config,
                control_global_dof=control_global_dof,
                control_free_index=control_free_index,
                target=target,
                parent=parent,
            )
        except StatefulCorotationalFrame3DSparseError as error:
            rollback_exact = bool(
                parent_bytes == canonical_json_bytes(parent.to_dict())
            )
            raise StatefulCorotationalFrame3DDisplacementControlError(
                str(error),
                code=error.code,
                attempts=(
                    {
                        "target_control_displacement_m": target,
                        "parent_checkpoint_hash": parent.checkpoint_hash,
                        "rollback_exact": rollback_exact,
                        "failure_code": error.code,
                        "solver_attempts": list(error.attempts),
                    },
                ),
            ) from error
        steps.append(step)
        checkpoints.append(step.checkpoint)

    payload = {
        "schema_version": (
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION
        ),
        "profile": STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
        "model_hash": model.model_hash,
        "direct_control_contract_hash": config.contract_hash,
        "start_checkpoint_hash": checkpoint.checkpoint_hash,
        "control_global_dof": control_global_dof,
        "target_control_displacements_m": list(targets),
        "steps": [row.to_dict() for row in steps],
        "exact_checkpoint_resume_supported": True,
        "parent_state_immutability_enforced": True,
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": True,
        "claim_boundary": (
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY
        ),
    }
    return StatefulCorotationalFrame3DDisplacementControlResult(
        schema_version=(
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION
        ),
        profile=STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
        model_hash=model.model_hash,
        direct_control_contract_hash=config.contract_hash,
        start_checkpoint_hash=checkpoint.checkpoint_hash,
        control_global_dof=control_global_dof,
        target_control_displacements_m=targets,
        steps=tuple(steps),
        checkpoints=tuple(checkpoints),
        result_hash=canonical_hash(payload),
        exact_checkpoint_resume_supported=True,
        parent_state_immutability_enforced=True,
        regularization_used=False,
        fallback_used=False,
        contract_pass=True,
        claim_boundary=(
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY
        ),
    )


def _solve_direct_control_step(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    control_global_dof: int,
    control_free_index: int,
    target: float,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
) -> StatefulCorotationalFrame3DDisplacementControlStep:
    solver = config.solver_config
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    load_factor = float(parent.load_factor)
    free = list(model.free_dofs)
    scaling = _equation_scaling(model, solver)
    residual_tolerance = _scaled_residual_tolerance(solver, scaling)
    increment_tolerance = _scaled_increment_tolerance(solver, scaling)
    control_reference = max(
        abs(target),
        abs(parent.displacement[control_global_dof]),
        abs(target - parent.displacement[control_global_dof]),
        config.control_absolute_tolerance_m,
    )
    control_tolerance = config.control_relative_tolerance + (
        config.control_absolute_tolerance_m
        / control_reference
    )
    diagnostics: list[FactorizationDiagnostic] = []
    accepted_alphas: list[float] = []
    convergence_trace: list[Mapping[str, Any]] = []
    parent_signature = _checkpoint_parent_signature(parent)

    for iteration in range(solver.maximum_iterations + 1):
        trial = _direct_trial(
            model=model,
            parent=parent,
            target=target,
            control_free_index=control_free_index,
            displacement=displacement,
            load_factor=load_factor,
            scaling=scaling,
            control_reference=control_reference,
        )
        _require_parent_unchanged(parent, parent_signature)
        try:
            correction, diagnostic = _solve_sparse_tangent(
                trial.augmented_tangent,
                -trial.augmented_residual,
                solver.factorization_policy,
            )
        except (SparseFactorizationError, ScalableSparseFactorizationError) as error:
            raise StatefulCorotationalFrame3DDisplacementControlError(
                f"direct-control augmented factorization failed: {error.code}",
                code="direct_control_augmented_factorization_failed",
            ) from error
        diagnostics.append(diagnostic)
        if (
            correction.shape != (len(free) + 1,)
            or not np.all(np.isfinite(correction))
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct-control augmented correction is invalid",
                code="direct_control_invalid_augmented_correction",
            )
        scaled_displacement_correction = correction[:-1]
        load_factor_correction = float(correction[-1])
        physical_correction = scaling.unscale_increment(
            scaled_displacement_correction
        )
        observation = scaling.observe(
            residual=trial.assembly.residual_free,
            increment=physical_correction,
            scaled_tangent_condition=diagnostic.condition_number_1,
        )
        residual_gate = bool(
            observation.scaled_residual_norm <= residual_tolerance
        )
        control_gate = bool(
            abs(trial.scaled_control_error) <= control_tolerance
        )
        increment_gate = bool(
            observation.scaled_increment_norm <= increment_tolerance
        )
        load_increment_gate = bool(
            abs(load_factor_correction)
            <= config.load_factor_increment_tolerance
        )
        trace_row: dict[str, Any] = {
            "iteration": iteration,
            "load_factor": load_factor,
            "control_global_dof": control_global_dof,
            "target_control_displacement_m": target,
            "control_error_m": trial.control_error,
            "control_reference_m": trial.control_reference,
            "scaled_control_error": trial.scaled_control_error,
            "scaled_control_tolerance": control_tolerance,
            "load_factor_increment": load_factor_correction,
            "load_factor_increment_tolerance": (
                config.load_factor_increment_tolerance
            ),
            "equation_scaling": observation.to_dict(),
            "scaled_residual_tolerance": residual_tolerance,
            "scaled_increment_tolerance": increment_tolerance,
            "residual_gate_pass": residual_gate,
            "control_gate_pass": control_gate,
            "increment_gate_pass": increment_gate,
            "load_factor_increment_gate_pass": load_increment_gate,
            "sparse_diagnostic_pass": diagnostic.contract_pass,
            "condition_scope": (
                "dimensionless_augmented_equilibrium_control_jacobian"
            ),
            "accepted_line_search_alpha": None,
            "line_search_attempts": [],
            "accepted": False,
        }
        if (
            residual_gate
            and control_gate
            and increment_gate
            and load_increment_gate
        ):
            final = _direct_trial(
                model=model,
                parent=parent,
                target=target,
                control_free_index=control_free_index,
                displacement=displacement,
                load_factor=load_factor,
                scaling=scaling,
                control_reference=control_reference,
            )
            _require_parent_unchanged(parent, parent_signature)
            final_state_consistent = (
                tuple(
                    state.state_hash
                    for state in final.assembly.trial_material_states
                )
                == tuple(
                    state.state_hash
                    for state in trial.assembly.trial_material_states
                )
            )
            convergence_checks = MappingProxyType(
                {
                    "scaled_residual_gate": bool(
                        _linf(
                            scaling.scale_residual(
                                final.assembly.residual_free
                            )
                        )
                        <= residual_tolerance
                    ),
                    "scaled_control_gate": bool(
                        abs(final.scaled_control_error) <= control_tolerance
                    ),
                    "scaled_increment_gate": increment_gate,
                    "load_factor_increment_gate": load_increment_gate,
                    "line_search_step_valid": all(
                        solver.line_search_minimum_alpha <= alpha <= 1.0
                        for alpha in accepted_alphas
                    ),
                    "material_admissibility": final_state_consistent,
                    "final_reassembled_equilibrium": bool(
                        final.assembly.assembly_hash
                        == trial.assembly.assembly_hash
                        and final_state_consistent
                    ),
                    "parent_state_immutable": bool(
                        _checkpoint_parent_signature(parent)
                        == parent_signature
                    ),
                    "augmented_sparse_diagnostic_pass": bool(
                        diagnostics
                        and all(row.contract_pass for row in diagnostics)
                    ),
                    "regularization_not_used": all(
                        not row.regularization_used for row in diagnostics
                    ),
                    "fallback_not_used": all(
                        not row.fallback_used for row in diagnostics
                    ),
                }
            )
            if not all(convergence_checks.values()):
                failed = ",".join(
                    name
                    for name, passed in convergence_checks.items()
                    if not passed
                )
                raise StatefulCorotationalFrame3DDisplacementControlError(
                    f"direct-control commit contract failed: {failed}",
                    code="direct_control_commit_contract_failed",
                )
            trace_row["accepted"] = True
            convergence_trace.append(MappingProxyType(trace_row))
            residual = _translation_component_norm(
                final.assembly.residual_free,
                scaling.dof_labels,
            )
            checkpoint = _make_checkpoint(
                model=model,
                config=solver,
                step_index=parent.step_index + 1,
                load_factor=load_factor,
                displacement=displacement,
                material_states=final.assembly.trial_material_states,
                converged_iterations=iteration,
                residual_inf_norm_kn=residual,
                parent_checkpoint_hash=parent.checkpoint_hash,
            )
            validate_stateful_corotational_frame3d_sparse_checkpoint(
                checkpoint,
                model=model,
                config=solver,
                require_equilibrium=True,
            )
            return StatefulCorotationalFrame3DDisplacementControlStep(
                step_index=checkpoint.step_index,
                control_global_dof=control_global_dof,
                target_control_displacement_m=target,
                solved_load_factor=load_factor,
                checkpoint=checkpoint,
                equation_scaling=observation,
                control_reference_m=control_reference,
                scaled_control_error=final.scaled_control_error,
                scaled_control_tolerance=control_tolerance,
                augmented_scaled_condition_number=(
                    diagnostic.condition_number_1
                ),
                accepted_line_search_alphas=tuple(accepted_alphas),
                convergence_checks=convergence_checks,
                convergence_trace=tuple(convergence_trace),
                reactions=tuple(
                    (dof, float(final.assembly.reactions[dof]))
                    for dof in model.elastic_model.restrained_dofs
                ),
                factorization_diagnostics=tuple(diagnostics),
                member_results=tuple(
                    MappingProxyType(response.recovery_manifest())
                    for response in final.assembly.member_responses
                ),
            )
        if iteration == solver.maximum_iterations:
            convergence_trace.append(MappingProxyType(trace_row))
            break
        selected = _direct_line_search(
            model=model,
            solver=solver,
            parent=parent,
            parent_signature=parent_signature,
            target=target,
            control_free_index=control_free_index,
            displacement=displacement,
            load_factor=load_factor,
            free=free,
            physical_correction=physical_correction,
            load_factor_correction=load_factor_correction,
            scaling=scaling,
            control_reference=control_reference,
            base_merit=trial.merit,
            residual_tolerance=residual_tolerance,
            control_tolerance=control_tolerance,
        )
        trace_row["accepted_line_search_alpha"] = selected.alpha
        trace_row["line_search_attempts"] = list(selected.attempts)
        trace_row["accepted"] = True
        convergence_trace.append(MappingProxyType(trace_row))
        accepted_alphas.append(selected.alpha)
        displacement = np.asarray(selected.displacement, dtype=np.float64).copy()
        load_factor = selected.load_factor

    raise StatefulCorotationalFrame3DDisplacementControlError(
        f"direct-control target {target} did not converge in "
        f"{solver.maximum_iterations} iterations",
        code="direct_control_maximum_iterations_exhausted",
    )


def _direct_trial(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    target: float,
    control_free_index: int,
    displacement: np.ndarray,
    load_factor: float,
    scaling: EquationScaling6DOFTransform,
    control_reference: float,
) -> _DirectTrial:
    try:
        assembly = assemble_stateful_corotational_frame3d_sparse(
            model,
            parent,
            target_load_factor=load_factor,
            trial_displacement=displacement,
        )
    except MaterialPathNotAdmissibleError as error:
        raise StatefulCorotationalFrame3DDisplacementControlError(
            f"unsupported_constitutive_path: {error}",
            code="unsupported_constitutive_path",
        ) from error
    except StatefulCorotationalFrame3DSparseError as error:
        raise StatefulCorotationalFrame3DDisplacementControlError(
            str(error),
            code=error.code,
            attempts=error.attempts,
        ) from error
    except (ValueError, FloatingPointError) as error:
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "invalid geometry or material direct-control trial",
            code="invalid_geometry_or_material_trial",
        ) from error
    scaled_residual = scaling.scale_residual(assembly.residual_free)
    control_global_dof = model.free_dofs[control_free_index]
    control_error = float(displacement[control_global_dof] - target)
    scaled_control_error = control_error / control_reference
    augmented_residual = np.concatenate(
        (
            scaled_residual,
            np.asarray([scaled_control_error], dtype=np.float64),
        )
    )
    scaled_tangent = cast(csr_matrix, scaling.scale_tangent(
        assembly.tangent_free_csr
    ))
    reference_load = np.asarray(
        model.elastic_model.reference_load_kn,
        dtype=np.float64,
    )[list(model.free_dofs)]
    load_column = scaling.scale_residual(-reference_load)
    control_row = np.zeros(len(model.free_dofs), dtype=np.float64)
    control_row[control_free_index] = (
        scaling.increment_scales[control_free_index]
        / control_reference
    )
    augmented_tangent = bmat(
        [
            [
                scaled_tangent,
                csr_matrix(load_column.reshape(-1, 1)),
            ],
            [
                csr_matrix(control_row.reshape(1, -1)),
                csr_matrix((1, 1), dtype=np.float64),
            ],
        ],
        format="csr",
        dtype=np.float64,
    )
    augmented_tangent.sum_duplicates()
    augmented_tangent.eliminate_zeros()
    augmented_tangent.sort_indices()
    merit = _linf(augmented_residual)
    return _DirectTrial(
        assembly=assembly,
        augmented_residual=immutable_array(augmented_residual, dtype="<f8"),
        augmented_tangent=augmented_tangent,
        control_error=control_error,
        control_reference=control_reference,
        scaled_control_error=scaled_control_error,
        merit=merit,
    )


def _direct_line_search(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    solver: StatefulCorotationalFrame3DSparseConfig,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    parent_signature: tuple[Any, ...],
    target: float,
    control_free_index: int,
    displacement: np.ndarray,
    load_factor: float,
    free: list[int],
    physical_correction: np.ndarray,
    load_factor_correction: float,
    scaling: EquationScaling6DOFTransform,
    control_reference: float,
    base_merit: float,
    residual_tolerance: float,
    control_tolerance: float,
) -> _DirectLineSearchSelection:
    attempts: list[Mapping[str, Any]] = []
    alpha = 1.0
    for line_search_iteration in range(
        solver.maximum_line_search_iterations
    ):
        if alpha + 1.0e-15 < solver.line_search_minimum_alpha:
            break
        trial_displacement = np.array(
            displacement,
            dtype=np.float64,
            copy=True,
        )
        trial_displacement[free] += alpha * physical_correction
        trial_load_factor = load_factor + alpha * load_factor_correction
        attempt: dict[str, Any] = {
            "line_search_iteration": line_search_iteration,
            "alpha": alpha,
            "trial_load_factor": trial_load_factor,
            "invalid_trial": False,
            "invalid_trial_code": None,
            "scaled_residual_norm": None,
            "scaled_control_error": None,
            "augmented_scaled_merit": None,
            "required_augmented_scaled_merit": (
                (1.0 - solver.line_search_sufficient_decrease * alpha)
                * base_merit
            ),
            "accepted": False,
        }
        if not math.isfinite(trial_load_factor):
            attempt["invalid_trial"] = True
            attempt["invalid_trial_code"] = "invalid_load_factor_trial"
            attempts.append(MappingProxyType(attempt))
            alpha *= solver.line_search_reduction_factor
            continue
        try:
            candidate = _direct_trial(
                model=model,
                parent=parent,
                target=target,
                control_free_index=control_free_index,
                displacement=trial_displacement,
                load_factor=trial_load_factor,
                scaling=scaling,
                control_reference=control_reference,
            )
            _require_parent_unchanged(parent, parent_signature)
            scaled_residual_norm = _linf(
                scaling.scale_residual(candidate.assembly.residual_free)
            )
            attempt["scaled_residual_norm"] = scaled_residual_norm
            attempt["scaled_control_error"] = (
                candidate.scaled_control_error
            )
            attempt["augmented_scaled_merit"] = candidate.merit
            accepted = bool(
                (
                    scaled_residual_norm <= residual_tolerance
                    and abs(candidate.scaled_control_error)
                    <= control_tolerance
                )
                or candidate.merit
                <= float(attempt["required_augmented_scaled_merit"])
            )
            attempt["accepted"] = accepted
            attempts.append(MappingProxyType(attempt))
            if accepted:
                return _DirectLineSearchSelection(
                    alpha=alpha,
                    displacement=immutable_array(
                        trial_displacement,
                        dtype="<f8",
                    ),
                    load_factor=trial_load_factor,
                    attempts=tuple(attempts),
                )
        except StatefulCorotationalFrame3DDisplacementControlError as error:
            _require_parent_unchanged(parent, parent_signature)
            attempt["invalid_trial"] = True
            attempt["invalid_trial_code"] = error.code
            attempts.append(MappingProxyType(attempt))
        alpha *= solver.line_search_reduction_factor

    invalid_codes = {
        str(row["invalid_trial_code"])
        for row in attempts
        if bool(row["invalid_trial"])
    }
    if invalid_codes == {"unsupported_constitutive_path"}:
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "unsupported_constitutive_path: no admissible direct-control "
            "line-search step",
            code="unsupported_constitutive_path",
            attempts=attempts,
        )
    raise StatefulCorotationalFrame3DDisplacementControlError(
        "direct-control line search failed to reduce augmented scaled merit",
        code="direct_control_line_search_failed",
        attempts=attempts,
    )


def _control_free_index(
    model: StatefulCorotationalFrame3DSparseModel,
    control_global_dof: int,
) -> int:
    if type(control_global_dof) is not int:
        raise ValueError("control_global_dof must be an integer")
    if control_global_dof not in model.free_dofs:
        raise ValueError("control_global_dof must be a free global DOF")
    free_index = model.free_dofs.index(control_global_dof)
    if control_global_dof % 6 not in (0, 1, 2):
        raise ValueError(
            "control_global_dof must be translational UX, UY, or UZ"
        )
    return free_index


def _control_targets(
    values: Iterable[float],
    *,
    after: float,
    maximum_count: int,
) -> tuple[float, ...]:
    targets = tuple(
        _finite(value, f"target_control_displacements_m[{index}]")
        for index, value in enumerate(values)
    )
    if not targets:
        raise ValueError("target_control_displacements_m must not be empty")
    if len(targets) > maximum_count:
        raise ValueError("target_control_displacements_m exceeds maximum_path_targets")
    previous = float(after)
    for target in targets:
        if target == previous:
            raise ValueError(
                "adjacent control displacement targets must be distinct"
            )
        previous = target
    return targets


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite number")
    return normalized


def _positive(value: Any, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


__all__ = [
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION",
    "StatefulCorotationalFrame3DDisplacementControlConfig",
    "StatefulCorotationalFrame3DDisplacementControlError",
    "StatefulCorotationalFrame3DDisplacementControlResult",
    "StatefulCorotationalFrame3DDisplacementControlStep",
    "solve_stateful_corotational_frame3d_displacement_control_path",
]
