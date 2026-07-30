"""Bounded direct displacement control for the stateful sparse Frame3D path."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.sparse import bmat, csr_matrix, diags

from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    FactorizationDiagnostic,
    StatefulCorotationalFrame3DEquationScaling6DOF,
    StatefulCorotationalFrame3DSparseAssembly,
    StatefulCorotationalFrame3DSparseCheckpoint,
    StatefulCorotationalFrame3DSparseConfig,
    StatefulCorotationalFrame3DSparseError,
    StatefulCorotationalFrame3DSparseModel,
    _make_checkpoint,
    _solve_sparse_tangent,
    assemble_stateful_corotational_frame3d_sparse,
    initial_stateful_corotational_frame3d_sparse_checkpoint,
    stateful_corotational_frame3d_equation_scaling_6dof,
    validate_stateful_corotational_frame3d_sparse_checkpoint,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    immutable_array,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.solvers.equation_scaling_6dof import (
    equilibration_vectors_6dof,
    scaled_increment_metrics_6dof,
    scaled_residual_metrics_6dof,
)


STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE = (
    "stateful_corotational_frame3d_sparse_direct_displacement_control.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-displacement-control-result.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-displacement-control-resume-binding.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-displacement-control-resume-binding.v2"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_TARGET_CHAIN_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-displacement-control-target-chain.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE = (
    "cyclic_reversal"
)
STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY = (
    "Experimental internal single-free-DOF direct displacement control over the "
    "bounded stateful sparse Frame3D candidate. The augmented solve uses the "
    "source-bound 6DOF force/moment scaling, exact-condition sparse diagnostics, "
    "strict merit-decreasing backtracking, immutable same-parent material trials, "
    "and final equilibrium/control reassembly without fallback or regularization. "
    "Exact continuation additionally requires the hash-bound direct-control resume "
    "receipt; a bare equilibrium checkpoint is labeled an unbound restart. "
    "Bounded adaptive target cutback retries only convergence and line-search "
    "failures, records every rejected target against an immutable accepted parent, "
    "and never masks factorization, material-admissibility, or contract failures. "
    "An opt-in cyclic mode is limited to exact bilinear combined-hardening steel, "
    "binds each authored leg and reversal to a rolling v2 target-chain receipt, and "
    "keeps the monotonic v1 direction receipt unchanged. Other material families "
    "and general cyclic behavior remain unsupported. "
    "Multiple simultaneous control DOFs, prescribed supports, arc-length "
    "continuation, independent external 3D V&V, design authority, and release "
    "authority remain unsupported."
)
_ZERO_HASH = "sha256:" + "0" * 64


class StatefulCorotationalFrame3DDisplacementControlError(RuntimeError):
    """Stable fail-closed direct-control error."""

    def __init__(self, reason_code: str, detail: str):
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}")


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlConfig:
    frame_config: StatefulCorotationalFrame3DSparseConfig = field(
        default_factory=StatefulCorotationalFrame3DSparseConfig
    )
    control_relative_tolerance: float = 1.0e-10
    control_absolute_tolerance_m: float = 1.0e-12
    control_absolute_tolerance_rad: float = 1.0e-12
    minimum_control_reference_m: float = 1.0e-9
    load_factor_increment_tolerance: float = 1.0e-10
    maximum_iterations: int = 30
    maximum_path_targets: int = 255
    allow_direction_reversal: bool = False
    maximum_direction_reversals: int = 0
    adaptive_target_cutback_enabled: bool = True
    target_cutback_ratio: float = 0.5
    maximum_target_cutback_depth: int = 8
    maximum_target_cutback_substeps: int = 256
    maximum_path_solve_attempts: int = 4096
    minimum_control_increment_m: float = 1.0e-9
    minimum_control_increment_rad: float = 1.0e-9
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    )

    def __post_init__(self) -> None:
        if type(self.frame_config) is not StatefulCorotationalFrame3DSparseConfig:
            raise ValueError("frame_config must be an exact sparse Frame3D config")
        for name in (
            "control_relative_tolerance",
            "control_absolute_tolerance_m",
            "control_absolute_tolerance_rad",
            "minimum_control_reference_m",
            "load_factor_increment_tolerance",
            "minimum_control_increment_m",
            "minimum_control_increment_rad",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        for name, upper in (
            ("maximum_iterations", 200),
            ("maximum_path_targets", 4096),
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1 or value > upper:
                raise ValueError(f"{name} must be an integer in [1, {upper}]")
        if self.maximum_iterations > self.frame_config.maximum_iterations:
            raise ValueError(
                "maximum_iterations cannot exceed "
                "frame_config.maximum_iterations because accepted direct-control "
                "steps use the sparse Frame3D checkpoint contract"
            )
        if type(self.allow_direction_reversal) is not bool:
            raise ValueError("allow_direction_reversal must be a boolean")
        if (
            type(self.maximum_direction_reversals) is not int
            or self.maximum_direction_reversals < 0
            or self.maximum_direction_reversals > 4095
        ):
            raise ValueError(
                "maximum_direction_reversals must be an integer in [0, 4095]"
            )
        if self.allow_direction_reversal:
            if self.maximum_direction_reversals < 1:
                raise ValueError(
                    "maximum_direction_reversals must be positive when "
                    "direction reversal is enabled"
                )
            if self.maximum_direction_reversals >= self.maximum_path_targets:
                raise ValueError(
                    "maximum_direction_reversals must be smaller than "
                    "maximum_path_targets"
                )
        elif self.maximum_direction_reversals != 0:
            raise ValueError(
                "maximum_direction_reversals must be zero when direction "
                "reversal is disabled"
            )
        if type(self.adaptive_target_cutback_enabled) is not bool:
            raise ValueError("adaptive_target_cutback_enabled must be a boolean")
        ratio = _positive(self.target_cutback_ratio, "target_cutback_ratio")
        if ratio >= 1.0:
            raise ValueError("target_cutback_ratio must be in (0, 1)")
        object.__setattr__(self, "target_cutback_ratio", ratio)
        if (
            type(self.maximum_target_cutback_depth) is not int
            or self.maximum_target_cutback_depth < 0
            or self.maximum_target_cutback_depth > 32
        ):
            raise ValueError(
                "maximum_target_cutback_depth must be an integer in [0, 32]"
            )
        if (
            type(self.maximum_target_cutback_substeps) is not int
            or self.maximum_target_cutback_substeps < 1
            or self.maximum_target_cutback_substeps > 4096
        ):
            raise ValueError(
                "maximum_target_cutback_substeps must be an integer in [1, 4096]"
            )
        if (
            type(self.maximum_path_solve_attempts) is not int
            or self.maximum_path_solve_attempts < 1
            or self.maximum_path_solve_attempts > 65536
        ):
            raise ValueError(
                "maximum_path_solve_attempts must be an integer in [1, 65536]"
            )
        if not isinstance(self.line_search_alphas, tuple) or not (
            self.line_search_alphas
        ):
            raise ValueError("line_search_alphas must be a non-empty tuple")
        normalized: list[float] = []
        previous = math.inf
        for index, raw in enumerate(self.line_search_alphas):
            alpha = _positive(raw, f"line_search_alphas[{index}]")
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized.append(alpha)
            previous = alpha
        if normalized[0] != 1.0:
            raise ValueError("line_search_alphas must start with 1")
        object.__setattr__(self, "line_search_alphas", tuple(normalized))

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
            "frame_config": self.frame_config.to_manifest(),
            "control_relative_tolerance": self.control_relative_tolerance,
            "control_absolute_tolerance_m": self.control_absolute_tolerance_m,
            "control_absolute_tolerance_rad": self.control_absolute_tolerance_rad,
            "minimum_control_reference_m": self.minimum_control_reference_m,
            "load_factor_increment_tolerance": (
                self.load_factor_increment_tolerance
            ),
            "maximum_iterations": self.maximum_iterations,
            "maximum_path_targets": self.maximum_path_targets,
            "path_direction": {
                "reversal_supported": True,
                "allow_direction_reversal": self.allow_direction_reversal,
                "maximum_direction_reversals": (
                    self.maximum_direction_reversals
                ),
                "equal_consecutive_targets_allowed": False,
            },
            "line_search": {
                "policy": "strict_augmented_gate_normalized_merit_decrease.v1",
                "alphas": list(self.line_search_alphas),
            },
            "control_dof_count": 1,
            "load_factor_coordinate_scale": "characteristic_length_m",
            "target_cutback": {
                "supported": True,
                "enabled": self.adaptive_target_cutback_enabled,
                "ratio": self.target_cutback_ratio,
                "maximum_depth": self.maximum_target_cutback_depth,
                "maximum_accepted_substeps_per_requested_target": (
                    self.maximum_target_cutback_substeps
                ),
                "maximum_path_solve_attempts": self.maximum_path_solve_attempts,
                "minimum_translation_increment_m": (
                    self.minimum_control_increment_m
                ),
                "minimum_rotation_increment_rad": (
                    self.minimum_control_increment_rad
                ),
                "retry_reason_codes": [
                    "direct_control_maximum_iterations_exceeded",
                    "direct_control_line_search_failed",
                ],
            },
            "target_cutback_supported": True,
            "regularization_allowed": False,
            "fallback_allowed": False,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlResumeBinding:
    """Hash-bound proof that a sparse checkpoint belongs to one control path."""

    schema_version: str
    profile: str
    model_hash: str
    frame_solver_contract_hash: str
    direct_control_contract_hash: str
    control_global_dof: int
    control_unit: str
    direction_sign: int
    accepted_control_target: float
    accepted_step_index: int
    accepted_checkpoint_hash: str
    binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = _resume_binding_payload(self, include_hash=True)
        if (
            self.schema_version
            != STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION
            or self.profile
            != STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE
            or not all(
                _canonical_hash(value)
                for value in (
                    self.model_hash,
                    self.frame_solver_contract_hash,
                    self.direct_control_contract_hash,
                    self.accepted_checkpoint_hash,
                    self.binding_hash,
                )
            )
            or type(self.control_global_dof) is not int
            or self.control_global_dof < 0
            or self.control_unit not in ("m", "rad")
            or self.control_unit
            != ("m" if self.control_global_dof % 6 < 3 else "rad")
            or type(self.direction_sign) is not int
            or self.direction_sign not in (-1, 1)
            or type(self.accepted_control_target) is not float
            or not math.isfinite(self.accepted_control_target)
            or type(self.accepted_step_index) is not int
            or self.accepted_step_index < 0
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_resume_binding_invalid",
                "resume binding fields are invalid",
            )
        if self.binding_hash != canonical_hash(
            _resume_binding_payload(self, include_hash=False)
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_resume_binding_hash_mismatch",
                "resume binding hash does not match its canonical payload",
            )
        return payload


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding:
    """V2 self-hashed lineage receipt for a bounded cyclic continuation."""

    schema_version: str
    profile: str
    model_hash: str
    frame_solver_contract_hash: str
    direct_control_contract_hash: str
    control_global_dof: int
    control_unit: str
    path_mode: str
    last_completed_leg_direction_sign: int | None
    cumulative_reversal_count: int
    cumulative_completed_target_count: int
    accepted_target_chain_hash: str
    accepted_control_target: float
    accepted_step_index: int
    accepted_checkpoint_hash: str
    binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = _cyclic_resume_binding_payload(self, include_hash=True)
        completed = self.cumulative_completed_target_count
        last_direction = self.last_completed_leg_direction_sign
        last_direction_valid = (
            last_direction is None
            if type(completed) is int and completed == 0
            else type(last_direction) is int and last_direction in (-1, 1)
        )
        if (
            self.schema_version
            != STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION
            or self.profile
            != STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE
            or self.path_mode
            != STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE
            or not all(
                _canonical_hash(value)
                for value in (
                    self.model_hash,
                    self.frame_solver_contract_hash,
                    self.direct_control_contract_hash,
                    self.accepted_target_chain_hash,
                    self.accepted_checkpoint_hash,
                    self.binding_hash,
                )
            )
            or type(self.control_global_dof) is not int
            or self.control_global_dof < 0
            or self.control_unit not in ("m", "rad")
            or self.control_unit
            != ("m" if self.control_global_dof % 6 < 3 else "rad")
            or not last_direction_valid
            or type(self.cumulative_reversal_count) is not int
            or self.cumulative_reversal_count < 0
            or type(completed) is not int
            or completed < 0
            or completed > 4096
            or type(self.accepted_step_index) is not int
            or self.accepted_step_index < 0
            or completed > self.accepted_step_index
            or self.cumulative_reversal_count > max(0, completed - 1)
            or type(self.accepted_control_target) is not float
            or not math.isfinite(self.accepted_control_target)
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_cyclic_resume_binding_invalid",
                "cyclic resume binding fields are invalid",
            )
        if self.binding_hash != canonical_hash(
            _cyclic_resume_binding_payload(self, include_hash=False)
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_cyclic_resume_binding_hash_mismatch",
                "cyclic resume binding hash does not match its canonical payload",
            )
        return payload


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlAssembly:
    frame_assembly: StatefulCorotationalFrame3DSparseAssembly
    augmented_coordinates_m: np.ndarray
    augmented_residual_kn: np.ndarray
    load_factor_residual_derivative_kn: np.ndarray
    control_error: float
    equivalent_control_error_m: float
    control_reference_m: float
    control_tolerance_m: float
    control_equation_scale_kn_per_m: float
    scaling_hash: str
    _augmented_jacobian_kn_per_m: csr_matrix

    def __post_init__(self) -> None:
        for name in (
            "augmented_coordinates_m",
            "augmented_residual_kn",
            "load_factor_residual_derivative_kn",
        ):
            object.__setattr__(
                self,
                name,
                immutable_array(getattr(self, name), dtype="<f8"),
            )
        matrix = self._augmented_jacobian_kn_per_m.tocsr(copy=True)
        matrix.sum_duplicates()
        matrix.eliminate_zeros()
        matrix.sort_indices()
        if not matrix.has_canonical_format or not np.all(np.isfinite(matrix.data)):
            raise ValueError("augmented direct-control Jacobian is invalid")
        object.__setattr__(self, "_augmented_jacobian_kn_per_m", matrix)

    @property
    def augmented_jacobian_kn_per_m(self) -> csr_matrix:
        return self._augmented_jacobian_kn_per_m.copy()


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlStepProblem:
    model: StatefulCorotationalFrame3DSparseModel
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    control_global_dof: int
    target_control_coordinate: float
    config: StatefulCorotationalFrame3DDisplacementControlConfig
    equation_scaling: StatefulCorotationalFrame3DEquationScaling6DOF = field(
        init=False
    )

    def __post_init__(self) -> None:
        if type(self.model) is not StatefulCorotationalFrame3DSparseModel:
            raise ValueError("model must be an exact sparse Frame3D model")
        if type(self.config) is not (
            StatefulCorotationalFrame3DDisplacementControlConfig
        ):
            raise ValueError("config type is invalid")
        validate_stateful_corotational_frame3d_sparse_checkpoint(
            self.accepted_checkpoint,
            model=self.model,
            config=self.config.frame_config,
            require_equilibrium=True,
        )
        _control_free_index(self.model, self.control_global_dof)
        target = _finite(
            self.target_control_coordinate,
            "target_control_coordinate",
        )
        object.__setattr__(self, "target_control_coordinate", target)
        scaling = stateful_corotational_frame3d_equation_scaling_6dof(
            self.model,
            config=self.config.frame_config,
        )
        object.__setattr__(self, "equation_scaling", scaling)
        parent_value = self.accepted_checkpoint.displacement[
            self.control_global_dof
        ]
        if target == parent_value:
            raise ValueError("target control coordinate must differ from the parent")
        if _target_is_within_control_tolerance(
            parent_value,
            target,
            control_global_dof=self.control_global_dof,
            characteristic_length_m=scaling.characteristic_length_m,
            config=self.config,
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_target_within_tolerance",
                "target increment must exceed the configured control tolerance",
            )
        free_load = np.asarray(
            self.model.elastic_model.reference_load_kn,
            dtype=np.float64,
        )[list(self.model.free_dofs)]
        if not np.any(free_load != 0.0):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_reference_load_missing",
                "at least one free equation must have a nonzero reference load",
            )

    @property
    def control_free_index(self) -> int:
        return _control_free_index(self.model, self.control_global_dof)

    @property
    def control_unit(self) -> str:
        return "m" if self.control_global_dof % 6 < 3 else "rad"

    @property
    def load_factor_coordinate_scale_m(self) -> float:
        return self.equation_scaling.characteristic_length_m

    def initial_augmented_coordinates_m(self) -> np.ndarray:
        _row, column = equilibration_vectors_6dof(
            self.model.free_dofs,
            self.equation_scaling.characteristic_length_m,
        )
        physical = np.asarray(
            self.accepted_checkpoint.displacement,
            dtype=np.float64,
        )[list(self.model.free_dofs)]
        equivalent = physical / column
        return np.concatenate(
            (
                equivalent,
                np.asarray(
                    [
                        self.accepted_checkpoint.load_factor
                        * self.load_factor_coordinate_scale_m
                    ],
                    dtype=np.float64,
                ),
            )
        )

    def physical_displacement(self, augmented_coordinates_m: Any) -> np.ndarray:
        coordinates = _augmented_coordinates(
            augmented_coordinates_m,
            len(self.model.free_dofs) + 1,
        )
        _row, column = equilibration_vectors_6dof(
            self.model.free_dofs,
            self.equation_scaling.characteristic_length_m,
        )
        displacement = np.asarray(
            self.accepted_checkpoint.displacement,
            dtype=np.float64,
        ).copy()
        displacement[list(self.model.free_dofs)] = column * coordinates[:-1]
        return displacement

    def load_factor(self, augmented_coordinates_m: Any) -> float:
        coordinates = _augmented_coordinates(
            augmented_coordinates_m,
            len(self.model.free_dofs) + 1,
        )
        return float(coordinates[-1]) / self.load_factor_coordinate_scale_m

    def equivalent_control_target_m(self) -> float:
        if self.control_global_dof % 6 < 3:
            return self.target_control_coordinate
        return (
            self.equation_scaling.characteristic_length_m
            * self.target_control_coordinate
        )

    def equivalent_control_absolute_tolerance_m(self) -> float:
        if self.control_global_dof % 6 < 3:
            return self.config.control_absolute_tolerance_m
        return (
            self.equation_scaling.characteristic_length_m
            * self.config.control_absolute_tolerance_rad
        )

    def assemble(
        self,
        augmented_coordinates_m: Any,
    ) -> StatefulCorotationalFrame3DDisplacementControlAssembly:
        coordinates = _augmented_coordinates(
            augmented_coordinates_m,
            len(self.model.free_dofs) + 1,
        )
        displacement = self.physical_displacement(coordinates)
        load_factor = self.load_factor(coordinates)
        frame = assemble_stateful_corotational_frame3d_sparse(
            self.model,
            self.accepted_checkpoint,
            target_load_factor=load_factor,
            trial_displacement=displacement,
        )
        row_scale, column_scale = equilibration_vectors_6dof(
            self.model.free_dofs,
            self.equation_scaling.characteristic_length_m,
        )
        scaled_tangent = (
            diags(row_scale, format="csr")
            @ frame.tangent_free_csr
            @ diags(column_scale, format="csr")
        ).tocsr()
        reference = np.asarray(
            self.model.elastic_model.reference_load_kn,
            dtype=np.float64,
        )[list(self.model.free_dofs)]
        load_derivative = -reference
        load_column = (
            row_scale * load_derivative / self.load_factor_coordinate_scale_m
        )
        target_equivalent = self.equivalent_control_target_m()
        parent = self.initial_augmented_coordinates_m()[self.control_free_index]
        control_reference = max(
            abs(target_equivalent),
            abs(target_equivalent - parent),
            self.config.minimum_control_reference_m,
        )
        control_tolerance = (
            self.config.control_relative_tolerance * control_reference
            + self.equivalent_control_absolute_tolerance_m()
        )
        equivalent_control_error = float(
            coordinates[self.control_free_index] - target_equivalent
        )
        control_scale = (
            self.equation_scaling.reference_force_kn / control_reference
        )
        augmented_residual = np.concatenate(
            (
                row_scale * np.asarray(frame.residual_free, dtype=np.float64),
                np.asarray(
                    [control_scale * equivalent_control_error],
                    dtype=np.float64,
                ),
            )
        )
        control_row = np.zeros((1, len(self.model.free_dofs)), dtype=np.float64)
        control_row[0, self.control_free_index] = control_scale
        augmented_jacobian = bmat(
            [
                [scaled_tangent, csr_matrix(load_column[:, None])],
                [csr_matrix(control_row), csr_matrix((1, 1), dtype=np.float64)],
            ],
            format="csr",
        )
        physical_control_error = float(
            displacement[self.control_global_dof]
            - self.target_control_coordinate
        )
        return StatefulCorotationalFrame3DDisplacementControlAssembly(
            frame_assembly=frame,
            augmented_coordinates_m=coordinates,
            augmented_residual_kn=augmented_residual,
            load_factor_residual_derivative_kn=load_derivative,
            control_error=physical_control_error,
            equivalent_control_error_m=equivalent_control_error,
            control_reference_m=control_reference,
            control_tolerance_m=control_tolerance,
            control_equation_scale_kn_per_m=control_scale,
            scaling_hash=self.equation_scaling.scaling_hash,
            _augmented_jacobian_kn_per_m=augmented_jacobian,
        )


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlSolution:
    status: str
    reason_code: str | None
    augmented_coordinates_m: np.ndarray
    displacement: tuple[float, ...]
    load_factor: float
    metrics: Mapping[str, Any]
    convergence_history: tuple[Mapping[str, Any], ...]
    line_search_history: tuple[Mapping[str, Any], ...]
    factorization_diagnostics: tuple[FactorizationDiagnostic, ...]
    final_assembly: StatefulCorotationalFrame3DDisplacementControlAssembly

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "augmented_coordinates_m",
            immutable_array(self.augmented_coordinates_m, dtype="<f8"),
        )


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlStepResult:
    status: str
    committed: bool
    control_global_dof: int
    target_control_coordinate: float
    parent_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint | None
    solution: StatefulCorotationalFrame3DDisplacementControlSolution
    parent_state_immutable: bool
    final_reassembly_binding: bool
    control_gate_passed: bool
    residual_gate_passed: bool
    sparse_diagnostic_passed: bool
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "committed": self.committed,
            "control_global_dof": self.control_global_dof,
            "target_control_coordinate": self.target_control_coordinate,
            "parent_checkpoint": self.parent_checkpoint.to_dict(),
            "accepted_checkpoint": (
                None
                if self.accepted_checkpoint is None
                else self.accepted_checkpoint.to_dict()
            ),
            "solution": _solution_payload(self.solution),
            "parent_state_immutable": self.parent_state_immutable,
            "final_reassembly_binding": self.final_reassembly_binding,
            "control_gate_passed": self.control_gate_passed,
            "residual_gate_passed": self.residual_gate_passed,
            "sparse_diagnostic_passed": self.sparse_diagnostic_passed,
            "result_hash": self.result_hash,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt:
    attempt_index: int
    recursion_depth: int
    cumulative_target_index: int
    leg_direction_sign: int
    reversal_from_previous_leg: bool
    control_global_dof: int
    control_unit: str
    requested_target_control_coordinate: float
    rejected_target_control_coordinate: float
    accepted_parent_control_coordinate: float
    accepted_parent_checkpoint_hash: str
    cutback_target_control_coordinate: float | None
    reason_code: str
    outcome: str
    outcome_reason_code: str | None
    rejected_result_hash: str
    parent_state_immutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "recursion_depth": self.recursion_depth,
            "cumulative_target_index": self.cumulative_target_index,
            "leg_direction_sign": self.leg_direction_sign,
            "reversal_from_previous_leg": self.reversal_from_previous_leg,
            "control_global_dof": self.control_global_dof,
            "control_unit": self.control_unit,
            "requested_target_control_coordinate": (
                self.requested_target_control_coordinate
            ),
            "rejected_target_control_coordinate": (
                self.rejected_target_control_coordinate
            ),
            "accepted_parent_control_coordinate": (
                self.accepted_parent_control_coordinate
            ),
            "accepted_parent_checkpoint_hash": (
                self.accepted_parent_checkpoint_hash
            ),
            "cutback_target_control_coordinate": (
                self.cutback_target_control_coordinate
            ),
            "reason_code": self.reason_code,
            "outcome": self.outcome,
            "outcome_reason_code": self.outcome_reason_code,
            "rejected_result_hash": self.rejected_result_hash,
            "parent_state_immutable": self.parent_state_immutable,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDisplacementControlPathResult:
    schema_version: str
    profile: str
    model_hash: str
    solver_contract_hash: str
    status: str
    control_global_dof: int
    control_unit: str
    path_mode: str
    requested_control_targets: tuple[float, ...]
    requested_target_direction_signs: tuple[int, ...]
    requested_direction_reversal_count: int
    completed_direction_reversal_count: int
    resumed_with_direction_reversal: bool
    cumulative_completed_target_count: int
    cumulative_direction_reversal_count: int
    accepted_target_chain_hash: str | None
    initial_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    checkpoints: tuple[StatefulCorotationalFrame3DSparseCheckpoint, ...]
    steps: tuple[StatefulCorotationalFrame3DDisplacementControlStepResult, ...]
    target_cutback_history: tuple[
        StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt, ...
    ]
    completed_requested_target_count: int
    completed_requested_target_checkpoint_hashes: tuple[str, ...]
    solve_attempt_count: int
    final_checkpoint_at_requested_target_boundary: bool
    terminal_reason_code: str | None
    resume_binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        | None
    )
    resume_mode: str
    resume_contract_verified: bool
    result_hash: str
    exact_checkpoint_resume_supported: bool
    adaptive_target_cutback_supported: bool
    adaptive_target_cutback_used: bool
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
            "solver_contract_hash": self.solver_contract_hash,
            "status": self.status,
            "control_global_dof": self.control_global_dof,
            "control_unit": self.control_unit,
            "path_mode": self.path_mode,
            "requested_control_targets": list(self.requested_control_targets),
            "requested_target_direction_signs": list(
                self.requested_target_direction_signs
            ),
            "requested_direction_reversal_count": (
                self.requested_direction_reversal_count
            ),
            "completed_direction_reversal_count": (
                self.completed_direction_reversal_count
            ),
            "resumed_with_direction_reversal": (
                self.resumed_with_direction_reversal
            ),
            "cumulative_completed_target_count": (
                self.cumulative_completed_target_count
            ),
            "cumulative_direction_reversal_count": (
                self.cumulative_direction_reversal_count
            ),
            "accepted_target_chain_hash": self.accepted_target_chain_hash,
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "steps": [row.to_dict() for row in self.steps],
            "target_cutback_history": [
                row.to_dict() for row in self.target_cutback_history
            ],
            "completed_requested_target_count": (
                self.completed_requested_target_count
            ),
            "completed_requested_target_checkpoint_hashes": list(
                self.completed_requested_target_checkpoint_hashes
            ),
            "solve_attempt_count": self.solve_attempt_count,
            "final_checkpoint_at_requested_target_boundary": (
                self.final_checkpoint_at_requested_target_boundary
            ),
            "terminal_reason_code": self.terminal_reason_code,
            "resume_binding": (
                None if self.resume_binding is None else self.resume_binding.to_dict()
            ),
            "resume_mode": self.resume_mode,
            "resume_contract_verified": self.resume_contract_verified,
            "result_hash": self.result_hash,
            "exact_checkpoint_resume_supported": (
                self.exact_checkpoint_resume_supported
            ),
            "adaptive_target_cutback_supported": (
                self.adaptive_target_cutback_supported
            ),
            "adaptive_target_cutback_used": self.adaptive_target_cutback_used,
            "regularization_used": self.regularization_used,
            "fallback_used": self.fallback_used,
            "contract_pass": self.contract_pass,
            "claim_boundary": self.claim_boundary,
        }


def solve_stateful_corotational_frame3d_displacement_control(
    step_problem: StatefulCorotationalFrame3DDisplacementControlStepProblem,
) -> StatefulCorotationalFrame3DDisplacementControlSolution:
    """Solve one free-DOF target and its proportional load factor together."""

    if type(step_problem) is not (
        StatefulCorotationalFrame3DDisplacementControlStepProblem
    ):
        raise ValueError("step_problem type is invalid")
    config = step_problem.config
    coordinates = step_problem.initial_augmented_coordinates_m()
    histories: list[Mapping[str, Any]] = []
    line_search_histories: list[Mapping[str, Any]] = []
    diagnostics: list[FactorizationDiagnostic] = []
    terminal_increment_metrics: dict[str, float] | None = None
    terminal_load_factor_increment: float | None = None
    terminal_condition_number_1: float | None = None
    reason_code: str | None = None
    inadmissible_trial_count = 0
    first_inadmissibility_reason_code: str | None = None
    ready = False
    for iteration in range(config.maximum_iterations + 1):
        assembly = step_problem.assemble(coordinates)
        residual_metrics = scaled_residual_metrics_6dof(
            assembly.frame_assembly.residual_free,
            step_problem.model.free_dofs,
            step_problem.equation_scaling,
        )
        residual_tolerance = _scaled_residual_tolerance(step_problem)
        control_gate = bool(
            abs(assembly.equivalent_control_error_m)
            <= assembly.control_tolerance_m
        )
        residual_gate = residual_metrics["scaled"] <= residual_tolerance
        try:
            correction, diagnostic = _solve_sparse_tangent(
                assembly.augmented_jacobian_kn_per_m,
                -np.asarray(assembly.augmented_residual_kn, dtype=np.float64),
                config.frame_config.factorization_policy,
            )
        except np.linalg.LinAlgError as error:
            reason_code = "direct_control_sparse_factorization_failed"
            terminal_increment_metrics = None
            terminal_load_factor_increment = None
            terminal_condition_number_1 = None
            histories.append(
                MappingProxyType(
                    {
                        "iteration": iteration,
                        "accepted": False,
                        "reason_code": reason_code,
                        "detail": str(error),
                    }
                )
            )
            break
        diagnostics.append(diagnostic)
        terminal_condition_number_1 = diagnostic.condition_number_1
        physical_free_increment = _physical_free_increment(
            step_problem,
            correction[:-1],
        )
        increment_metrics = scaled_increment_metrics_6dof(
            physical_free_increment,
            step_problem.model.free_dofs,
            step_problem.equation_scaling,
        )
        load_increment = (
            float(correction[-1]) / step_problem.load_factor_coordinate_scale_m
        )
        terminal_increment_metrics = increment_metrics
        terminal_load_factor_increment = load_increment
        increment_tolerance = _scaled_increment_tolerance(step_problem)
        increment_gate = bool(
            increment_metrics["scaled"] <= increment_tolerance
            and abs(load_increment)
            <= config.load_factor_increment_tolerance
        )
        row: dict[str, Any] = {
            "iteration": iteration,
            "load_factor": step_problem.load_factor(coordinates),
            "scaled_residual": residual_metrics["scaled"],
            "scaled_residual_tolerance": residual_tolerance,
            "equivalent_control_error_m": assembly.equivalent_control_error_m,
            "control_tolerance_m": assembly.control_tolerance_m,
            "scaled_increment": increment_metrics["scaled"],
            "raw_translation_increment_inf_norm_m": increment_metrics[
                "translation"
            ],
            "raw_rotation_increment_inf_norm_rad": increment_metrics["rotation"],
            "scaled_increment_tolerance": increment_tolerance,
            "load_factor_increment": load_increment,
            "load_factor_increment_tolerance": (
                config.load_factor_increment_tolerance
            ),
            "residual_gate_passed": residual_gate,
            "control_gate_passed": control_gate,
            "increment_gate_passed": increment_gate,
            "diagnostic_hash": diagnostic.diagnostic_hash,
        }
        if residual_gate and control_gate and increment_gate:
            row["accepted"] = True
            row["line_search_alpha"] = None
            histories.append(MappingProxyType(row))
            ready = True
            break
        if iteration == config.maximum_iterations:
            row["accepted"] = False
            row["line_search_alpha"] = None
            histories.append(MappingProxyType(row))
            reason_code = "direct_control_maximum_iterations_exceeded"
            break
        merit_before = _merit(step_problem, assembly)
        selected: np.ndarray | None = None
        selected_alpha: float | None = None
        attempts: list[Mapping[str, Any]] = []
        for alpha in config.line_search_alphas:
            candidate = coordinates + alpha * correction
            try:
                trial = step_problem.assemble(candidate)
            except (
                StatefulCorotationalFrame3DSparseError,
                StatefulCorotationalFrame3DDisplacementControlError,
                TypeError,
                ValueError,
                ArithmeticError,
            ) as error:
                trial_reason_code = getattr(
                    error,
                    "reason_code",
                    "direct_control_trial_assembly_inadmissible",
                )
                inadmissible_trial_count += 1
                if first_inadmissibility_reason_code is None:
                    first_inadmissibility_reason_code = trial_reason_code
                attempts.append(
                    MappingProxyType(
                        {
                            "alpha": alpha,
                            "accepted": False,
                            "admissible": False,
                            "reason_code": trial_reason_code,
                        }
                    )
                )
                continue
            trial_merit = _merit(step_problem, trial)
            accepted = bool(math.isfinite(trial_merit) and trial_merit < merit_before)
            attempts.append(
                MappingProxyType(
                    {
                        "alpha": alpha,
                        "accepted": accepted,
                        "admissible": True,
                        "trial_merit": trial_merit,
                        "trial_load_factor": step_problem.load_factor(candidate),
                    }
                )
            )
            if accepted:
                selected = candidate
                selected_alpha = alpha
                break
        line_search_histories.append(
            MappingProxyType(
                {
                    "iteration": iteration,
                    "selected_alpha": selected_alpha,
                    "attempts": tuple(attempts),
                }
            )
        )
        row["accepted"] = selected is not None
        row["line_search_alpha"] = selected_alpha
        histories.append(MappingProxyType(row))
        if selected is None:
            reason_code = (
                first_inadmissibility_reason_code
                if attempts
                and all(not bool(attempt["admissible"]) for attempt in attempts)
                and first_inadmissibility_reason_code is not None
                else "direct_control_line_search_failed"
            )
            break
        coordinates = selected
    final = step_problem.assemble(coordinates)
    displacement = step_problem.physical_displacement(coordinates)
    load_factor = step_problem.load_factor(coordinates)
    final_metrics = scaled_residual_metrics_6dof(
        final.frame_assembly.residual_free,
        step_problem.model.free_dofs,
        step_problem.equation_scaling,
    )
    contract_pass = bool(
        ready
        and final_metrics["scaled"] <= _scaled_residual_tolerance(step_problem)
        and abs(final.equivalent_control_error_m) <= final.control_tolerance_m
        and diagnostics
        and all(row.contract_pass for row in diagnostics)
        and line_search_histories
        and all(row["selected_alpha"] is not None for row in line_search_histories)
    )
    if not contract_pass and reason_code is None:
        reason_code = "direct_control_terminal_contract_failed"
    metrics = MappingProxyType(
        {
            "control_mode": "single_free_dof_direct_displacement_control",
            "control_global_dof": step_problem.control_global_dof,
            "control_unit": step_problem.control_unit,
            "target_control_coordinate": step_problem.target_control_coordinate,
            "final_control_coordinate": float(
                displacement[step_problem.control_global_dof]
            ),
            "load_factor": load_factor,
            "characteristic_length_m": (
                step_problem.equation_scaling.characteristic_length_m
            ),
            "raw_translational_residual_inf_norm_kn": final_metrics[
                "translation"
            ],
            "raw_rotational_residual_inf_norm_kn_m": final_metrics["rotation"],
            "scaled_residual": final_metrics["scaled"],
            "scaled_residual_tolerance": _scaled_residual_tolerance(step_problem),
            "equivalent_control_error_m": final.equivalent_control_error_m,
            "control_tolerance_m": final.control_tolerance_m,
            "raw_translation_increment_inf_norm_m": (
                None
                if terminal_increment_metrics is None
                else terminal_increment_metrics["translation"]
            ),
            "raw_rotation_increment_inf_norm_rad": (
                None
                if terminal_increment_metrics is None
                else terminal_increment_metrics["rotation"]
            ),
            "scaled_increment": (
                None
                if terminal_increment_metrics is None
                else terminal_increment_metrics["scaled"]
            ),
            "scaled_increment_tolerance": _scaled_increment_tolerance(
                step_problem
            ),
            "load_factor_increment": terminal_load_factor_increment,
            "load_factor_increment_tolerance": (
                config.load_factor_increment_tolerance
            ),
            "scaled_condition_number_1": (
                terminal_condition_number_1
            ),
            "iteration_count": len(histories),
            "converged_iterations": len(line_search_histories),
            "line_search_step_count": len(line_search_histories),
            "equation_scaling_hash": step_problem.equation_scaling.scaling_hash,
            "direct_control_contract_hash": config.contract_hash,
            "accepted_trial_material_admissibility_passed": contract_pass,
            "inadmissible_trial_count": inadmissible_trial_count,
            "first_inadmissibility_reason_code": (
                first_inadmissibility_reason_code
            ),
            "regularization_used": False,
            "fallback_used": False,
            "contract_pass": contract_pass,
        }
    )
    return StatefulCorotationalFrame3DDisplacementControlSolution(
        status="ready" if contract_pass else "blocked",
        reason_code=None if contract_pass else reason_code,
        augmented_coordinates_m=coordinates,
        displacement=tuple(float(value) for value in displacement),
        load_factor=load_factor,
        metrics=metrics,
        convergence_history=tuple(histories),
        line_search_history=tuple(line_search_histories),
        factorization_diagnostics=tuple(diagnostics),
        final_assembly=final,
    )


def solve_stateful_corotational_frame3d_displacement_control_step(
    model: StatefulCorotationalFrame3DSparseModel,
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    *,
    control_global_dof: int,
    target_control_coordinate: float,
    config: StatefulCorotationalFrame3DDisplacementControlConfig | None = None,
) -> StatefulCorotationalFrame3DDisplacementControlStepResult:
    solver_config = config or (
        StatefulCorotationalFrame3DDisplacementControlConfig()
    )
    problem = StatefulCorotationalFrame3DDisplacementControlStepProblem(
        model=model,
        accepted_checkpoint=accepted_checkpoint,
        control_global_dof=control_global_dof,
        target_control_coordinate=target_control_coordinate,
        config=solver_config,
    )
    parent_hash = accepted_checkpoint.checkpoint_hash
    parent_state_hashes = tuple(
        state.state_hash for state in accepted_checkpoint.material_states
    )
    solution = solve_stateful_corotational_frame3d_displacement_control(problem)
    reassembled = problem.assemble(solution.augmented_coordinates_m)
    parent_immutable = bool(
        accepted_checkpoint.checkpoint_hash == parent_hash
        and tuple(
            state.state_hash for state in accepted_checkpoint.material_states
        )
        == parent_state_hashes
    )
    assembly_binding = bool(
        reassembled.frame_assembly.assembly_hash
        == solution.final_assembly.frame_assembly.assembly_hash
        and reassembled.scaling_hash == solution.final_assembly.scaling_hash
        and np.array_equal(
            reassembled.augmented_residual_kn,
            solution.final_assembly.augmented_residual_kn,
        )
    )
    control_gate = bool(
        abs(reassembled.equivalent_control_error_m)
        <= reassembled.control_tolerance_m
    )
    residual_metrics = scaled_residual_metrics_6dof(
        reassembled.frame_assembly.residual_free,
        model.free_dofs,
        problem.equation_scaling,
    )
    residual_gate_passed = bool(
        residual_metrics["scaled"] <= _scaled_residual_tolerance(problem)
    )
    sparse_diagnostic_passed = bool(
        solution.factorization_diagnostics
        and all(
            row.contract_pass for row in solution.factorization_diagnostics
        )
    )
    commit = bool(
        solution.status == "ready"
        and solution.metrics["contract_pass"] is True
        and parent_immutable
        and assembly_binding
        and control_gate
        and residual_gate_passed
        and sparse_diagnostic_passed
    )
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint | None = None
    if commit:
        checkpoint = _make_checkpoint(
            model=model,
            config=solver_config.frame_config,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=solution.load_factor,
            displacement=np.asarray(solution.displacement, dtype=np.float64),
            material_states=reassembled.frame_assembly.trial_material_states,
            converged_iterations=int(solution.metrics["converged_iterations"]),
            residual_inf_norm_kn=_linf(reassembled.frame_assembly.residual_free),
            parent_checkpoint_hash=accepted_checkpoint.checkpoint_hash,
        )
    payload = {
        "status": "ready" if commit else "blocked",
        "committed": commit,
        "control_global_dof": control_global_dof,
        "target_control_coordinate": target_control_coordinate,
        "parent_checkpoint_hash": accepted_checkpoint.checkpoint_hash,
        "accepted_checkpoint_hash": (
            None if checkpoint is None else checkpoint.checkpoint_hash
        ),
        "solution": _solution_payload(solution),
        "parent_immutable": parent_immutable,
        "final_reassembly_binding": assembly_binding,
        "control_gate_passed": control_gate,
        "residual_gate_passed": residual_gate_passed,
        "sparse_diagnostic_passed": sparse_diagnostic_passed,
        "regularization_used": False,
        "fallback_used": False,
    }
    return StatefulCorotationalFrame3DDisplacementControlStepResult(
        status="ready" if commit else "blocked",
        committed=commit,
        control_global_dof=control_global_dof,
        target_control_coordinate=float(target_control_coordinate),
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=checkpoint,
        solution=solution,
        parent_state_immutable=parent_immutable,
        final_reassembly_binding=assembly_binding,
        control_gate_passed=control_gate,
        residual_gate_passed=residual_gate_passed,
        sparse_diagnostic_passed=sparse_diagnostic_passed,
        result_hash=canonical_hash(payload),
    )


_TARGET_CUTBACK_RETRY_REASON_CODES = frozenset(
    {
        "direct_control_maximum_iterations_exceeded",
        "direct_control_line_search_failed",
    }
)


def _target_is_within_control_tolerance(
    parent_coordinate: float,
    target_coordinate: float,
    *,
    control_global_dof: int,
    characteristic_length_m: float,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
) -> bool:
    coordinate_scale_m = (
        1.0 if control_global_dof % 6 < 3 else characteristic_length_m
    )
    parent_equivalent_m = coordinate_scale_m * parent_coordinate
    target_equivalent_m = coordinate_scale_m * target_coordinate
    increment_equivalent_m = target_equivalent_m - parent_equivalent_m
    absolute_tolerance_m = (
        config.control_absolute_tolerance_m
        if control_global_dof % 6 < 3
        else characteristic_length_m * config.control_absolute_tolerance_rad
    )
    reference_m = max(
        abs(target_equivalent_m),
        abs(increment_equivalent_m),
        config.minimum_control_reference_m,
    )
    tolerance_m = (
        config.control_relative_tolerance * reference_m
        + absolute_tolerance_m
    )
    return abs(increment_equivalent_m) <= tolerance_m


def _minimum_control_increment(
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    control_global_dof: int,
) -> float:
    return (
        config.minimum_control_increment_m
        if control_global_dof % 6 < 3
        else config.minimum_control_increment_rad
    )


def _target_failure_is_retryable(
    step: StatefulCorotationalFrame3DDisplacementControlStepResult,
) -> bool:
    return bool(
        step.solution.reason_code in _TARGET_CUTBACK_RETRY_REASON_CODES
        and step.solution.metrics["inadmissible_trial_count"] == 0
    )


def _solve_target_with_adaptive_target_cutback(
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    *,
    control_global_dof: int,
    cumulative_target_index: int,
    leg_direction_sign: int,
    reversal_from_previous_leg: bool,
    requested_target: float,
    target: float,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    history: list[
        StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt
    ],
    solve_attempt_counter: list[int],
) -> tuple[
    tuple[StatefulCorotationalFrame3DDisplacementControlStepResult, ...],
    StatefulCorotationalFrame3DDisplacementControlStepResult | None,
    str | None,
]:
    accepted: list[StatefulCorotationalFrame3DDisplacementControlStepResult] = []
    accepted_parent = parent
    attempt_target = target
    cutback_depth = 0
    while True:
        parent_control_before_attempt = float(
            accepted_parent.displacement[control_global_dof]
        )
        attempted_increment = attempt_target - parent_control_before_attempt
        if (
            attempted_increment == 0.0
            or (1 if attempted_increment > 0.0 else -1)
            != leg_direction_sign
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_cutback_leg_direction_mismatch",
                "every trial and retry must remain inside its authored target leg",
            )
        parent_checkpoint_hash = accepted_parent.checkpoint_hash
        parent_state_hashes = tuple(
            state.state_hash for state in accepted_parent.material_states
        )
        if solve_attempt_counter[0] >= config.maximum_path_solve_attempts:
            return (
                tuple(accepted),
                None,
                "direct_control_path_solve_attempt_limit_exceeded",
            )
        solve_attempt_counter[0] += 1
        try:
            step = solve_stateful_corotational_frame3d_displacement_control_step(
                model,
                accepted_parent,
                control_global_dof=control_global_dof,
                target_control_coordinate=attempt_target,
                config=config,
            )
        except Exception as error:
            parent_immutable_after_error = bool(
                accepted_parent.checkpoint_hash == parent_checkpoint_hash
                and tuple(
                    state.state_hash for state in accepted_parent.material_states
                )
                == parent_state_hashes
            )
            if not parent_immutable_after_error:
                raise StatefulCorotationalFrame3DDisplacementControlError(
                    "direct_control_failed_trial_parent_mutated",
                    "exceptional target trial mutated its accepted parent",
                ) from error
            raise
        parent_immutable = bool(
            accepted_parent.checkpoint_hash == parent_checkpoint_hash
            and tuple(
                state.state_hash for state in accepted_parent.material_states
            )
            == parent_state_hashes
        )
        if not parent_immutable:
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_failed_trial_parent_mutated",
                "failed or accepted target trial mutated its accepted parent",
            )
        if step.committed and step.accepted_checkpoint is not None:
            accepted.append(step)
            accepted_parent = step.accepted_checkpoint
            if attempt_target == requested_target:
                return tuple(accepted), None, None
            if len(accepted) >= config.maximum_target_cutback_substeps:
                return (
                    tuple(accepted),
                    None,
                    "direct_control_target_cutback_substep_limit_exceeded",
                )
            attempt_target = requested_target
            cutback_depth = 0
            continue
        reason_code = step.solution.reason_code or "direct_control_unknown_failure"
        if (
            not config.adaptive_target_cutback_enabled
            or not _target_failure_is_retryable(step)
        ):
            return tuple(accepted), step, reason_code
        parent_control = float(
            accepted_parent.displacement[control_global_dof]
        )
        increment = attempt_target - parent_control
        cutback_target = parent_control + config.target_cutback_ratio * increment
        minimum_increment = _minimum_control_increment(
            config,
            control_global_dof,
        )
        left_increment = abs(cutback_target - parent_control)
        right_increment = abs(attempt_target - cutback_target)
        cutback_available = bool(
            cutback_depth < config.maximum_target_cutback_depth
            and math.isfinite(cutback_target)
            and cutback_target not in (parent_control, attempt_target)
            and min(left_increment, right_increment) >= minimum_increment
            and (1 if cutback_target > parent_control else -1)
            == leg_direction_sign
            and (1 if attempt_target > cutback_target else -1)
            == leg_direction_sign
        )
        if not cutback_available:
            history.append(
                StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt(
                    attempt_index=len(history),
                    recursion_depth=cutback_depth,
                    cumulative_target_index=cumulative_target_index,
                    leg_direction_sign=leg_direction_sign,
                    reversal_from_previous_leg=reversal_from_previous_leg,
                    control_global_dof=control_global_dof,
                    control_unit=(
                        "m" if control_global_dof % 6 < 3 else "rad"
                    ),
                    requested_target_control_coordinate=requested_target,
                    rejected_target_control_coordinate=attempt_target,
                    accepted_parent_control_coordinate=parent_control,
                    accepted_parent_checkpoint_hash=(
                        accepted_parent.checkpoint_hash
                    ),
                    cutback_target_control_coordinate=None,
                    reason_code=reason_code,
                    outcome="bounds_exhausted",
                    outcome_reason_code=(
                        "direct_control_target_cutback_exhausted"
                    ),
                    rejected_result_hash=step.result_hash,
                    parent_state_immutable=True,
                )
            )
            return (
                tuple(accepted),
                step,
                "direct_control_target_cutback_exhausted",
            )
        history.append(
            StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt(
                attempt_index=len(history),
                recursion_depth=cutback_depth,
                cumulative_target_index=cumulative_target_index,
                leg_direction_sign=leg_direction_sign,
                reversal_from_previous_leg=reversal_from_previous_leg,
                control_global_dof=control_global_dof,
                control_unit="m" if control_global_dof % 6 < 3 else "rad",
                requested_target_control_coordinate=requested_target,
                rejected_target_control_coordinate=attempt_target,
                accepted_parent_control_coordinate=parent_control,
                accepted_parent_checkpoint_hash=accepted_parent.checkpoint_hash,
                cutback_target_control_coordinate=cutback_target,
                reason_code=reason_code,
                outcome="cutback_scheduled",
                outcome_reason_code=None,
                rejected_result_hash=step.result_hash,
                parent_state_immutable=True,
            )
        )
        attempt_target = cutback_target
        cutback_depth += 1


def _target_chain_genesis_hash(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    control_global_dof: int,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
) -> str:
    return canonical_hash(
        {
            "schema_version": (
                STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_TARGET_CHAIN_SCHEMA_VERSION
            ),
            "entry_kind": "genesis",
            "model_hash": model.model_hash,
            "frame_solver_contract_hash": config.frame_config.contract_hash,
            "direct_control_contract_hash": config.contract_hash,
            "control_global_dof": control_global_dof,
            "initial_checkpoint_hash": checkpoint.checkpoint_hash,
        }
    )


def _advance_target_chain_hash(
    *,
    previous_chain_hash: str,
    cumulative_target_index: int,
    authored_target: float,
    leg_direction_sign: int,
    reversal_from_previous_leg: bool,
    requested_boundary_checkpoint_hash: str,
    accepted_steps: tuple[
        StatefulCorotationalFrame3DDisplacementControlStepResult, ...
    ],
    cutback_attempts: tuple[
        StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt, ...
    ],
) -> str:
    return canonical_hash(
        {
            "schema_version": (
                STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_TARGET_CHAIN_SCHEMA_VERSION
            ),
            "entry_kind": "completed_authored_target",
            "previous_chain_hash": previous_chain_hash,
            "cumulative_target_index": cumulative_target_index,
            "authored_target": authored_target,
            "leg_direction_sign": leg_direction_sign,
            "reversal_from_previous_leg": reversal_from_previous_leg,
            "requested_boundary_checkpoint_hash": (
                requested_boundary_checkpoint_hash
            ),
            "accepted_step_hashes": [row.result_hash for row in accepted_steps],
            "cutback_history_hash": canonical_hash(
                [
                    _target_chain_cutback_payload(row)
                    for row in cutback_attempts
                ]
            ),
        }
    )


def _target_chain_cutback_payload(
    attempt: StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt,
) -> dict[str, Any]:
    """Return invocation-independent cutback lineage for rolling-chain hashing."""

    payload = attempt.to_dict()
    payload.pop("attempt_index")
    return payload


def _direction_reversal_count(
    direction_signs: tuple[int, ...],
    *,
    bound_direction: int | None,
) -> int:
    if not direction_signs:
        return 0
    previous = (
        direction_signs[0] if bound_direction is None else bound_direction
    )
    count = 0
    for direction_sign in direction_signs:
        if direction_sign != previous:
            count += 1
        previous = direction_sign
    return count


def _validate_requested_target_directions(
    targets: tuple[float, ...],
    *,
    accepted_value: float,
    bound_direction: int | None,
    prior_cumulative_reversal_count: int,
    control_global_dof: int,
    characteristic_length_m: float,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
) -> tuple[tuple[int, ...], int, bool]:
    direction_signs: list[int] = []
    previous = accepted_value
    for target in targets:
        delta = target - previous
        if delta == 0.0:
            raise ValueError(
                "control_targets must advance to a distinct coordinate"
            )
        if _target_is_within_control_tolerance(
            previous,
            target,
            control_global_dof=control_global_dof,
            characteristic_length_m=characteristic_length_m,
            config=config,
        ):
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_target_within_tolerance",
                "every requested target increment must exceed the configured "
                "control tolerance",
            )
        direction_signs.append(1 if delta > 0.0 else -1)
        previous = target
    signs = tuple(direction_signs)
    resumed_with_direction_reversal = bool(
        bound_direction is not None and signs[0] != bound_direction
    )
    reversal_count = _direction_reversal_count(
        signs,
        bound_direction=bound_direction,
    )
    if not config.allow_direction_reversal:
        if resumed_with_direction_reversal:
            raise StatefulCorotationalFrame3DDisplacementControlError(
                "direct_control_resume_direction_mismatch",
                "resumed targets must continue the hash-bound control direction",
            )
        if reversal_count:
            raise ValueError(
                "control_targets must advance strictly in one direction"
            )
    elif (
        prior_cumulative_reversal_count + reversal_count
        > config.maximum_direction_reversals
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_direction_reversal_limit_exceeded",
            "requested target path exceeds the configured cumulative reversal limit",
        )
    return signs, reversal_count, resumed_with_direction_reversal


def run_stateful_corotational_frame3d_displacement_control_path(
    model: StatefulCorotationalFrame3DSparseModel,
    control_targets: Iterable[float],
    *,
    control_global_dof: int,
    config: StatefulCorotationalFrame3DDisplacementControlConfig | None = None,
    resume_from: StatefulCorotationalFrame3DSparseCheckpoint | None = None,
    resume_binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        | None
    ) = None,
) -> StatefulCorotationalFrame3DDisplacementControlPathResult:
    solver_config = config or (
        StatefulCorotationalFrame3DDisplacementControlConfig()
    )
    path_mode = (
        STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE
        if solver_config.allow_direction_reversal
        else "monotonic_v1"
    )
    cumulative_completed_target_count = 0
    cumulative_direction_reversal_count = 0
    accepted_target_chain_hash: str | None = None
    last_completed_leg_direction_sign: int | None = None
    if solver_config.allow_direction_reversal and any(
        type(material) is not BilinearCombinedHardeningSteel
        for material in model.axial_materials
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_cyclic_material_family_unsupported",
            "cyclic reversal is bounded to exact bilinear combined-hardening steel",
        )
    if resume_from is None:
        if resume_binding is not None:
            raise ValueError("resume_binding requires resume_from")
        initial = initial_stateful_corotational_frame3d_sparse_checkpoint(
            model,
            config=solver_config.frame_config,
        )
        resume_mode = "fresh_start"
        resume_contract_verified = False
        bound_direction: int | None = None
        if solver_config.allow_direction_reversal:
            accepted_target_chain_hash = _target_chain_genesis_hash(
                model=model,
                config=solver_config,
                control_global_dof=control_global_dof,
                checkpoint=initial,
            )
    else:
        initial = validate_stateful_corotational_frame3d_sparse_checkpoint(
            resume_from,
            model=model,
            config=solver_config.frame_config,
            require_equilibrium=True,
        )
        if resume_binding is None:
            resume_mode = "unbound_equilibrium_checkpoint_restart"
            resume_contract_verified = False
            bound_direction = None
            if solver_config.allow_direction_reversal:
                accepted_target_chain_hash = _target_chain_genesis_hash(
                    model=model,
                    config=solver_config,
                    control_global_dof=control_global_dof,
                    checkpoint=initial,
                )
        else:
            validate_stateful_corotational_frame3d_displacement_control_resume_binding(
                resume_binding,
                checkpoint=initial,
                model=model,
                config=solver_config,
                control_global_dof=control_global_dof,
            )
            resume_contract_verified = True
            if solver_config.allow_direction_reversal:
                if type(resume_binding) is not (
                    StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
                ):
                    raise StatefulCorotationalFrame3DDisplacementControlError(
                        "direct_control_v1_binding_cyclic_policy_mismatch",
                        "cyclic continuation requires a v2 rolling-chain binding",
                    )
                resume_mode = "exact_bound_cyclic_resume"
                bound_direction = (
                    resume_binding.last_completed_leg_direction_sign
                )
                last_completed_leg_direction_sign = bound_direction
                cumulative_completed_target_count = (
                    resume_binding.cumulative_completed_target_count
                )
                cumulative_direction_reversal_count = (
                    resume_binding.cumulative_reversal_count
                )
                accepted_target_chain_hash = (
                    resume_binding.accepted_target_chain_hash
                )
            else:
                if type(resume_binding) is not (
                    StatefulCorotationalFrame3DDisplacementControlResumeBinding
                ):
                    raise StatefulCorotationalFrame3DDisplacementControlError(
                        "direct_control_v2_binding_monotonic_policy_mismatch",
                        "monotonic continuation requires a v1 direction binding",
                    )
                resume_mode = "exact_bound_resume"
                bound_direction = resume_binding.direction_sign
    targets = tuple(
        _finite(value, f"control_targets[{index}]")
        for index, value in enumerate(control_targets)
    )
    if not targets:
        raise ValueError("control_targets must not be empty")
    if len(targets) > solver_config.maximum_path_targets:
        raise ValueError("control_targets exceeds the bounded path length")
    if (
        solver_config.allow_direction_reversal
        and cumulative_completed_target_count + len(targets)
        > solver_config.maximum_path_targets
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_cumulative_target_limit_exceeded",
            "exact cyclic continuation exceeds the configured cumulative target limit",
        )
    _control_free_index(model, control_global_dof)
    path_scaling = stateful_corotational_frame3d_equation_scaling_6dof(
        model,
        config=solver_config.frame_config,
    )
    accepted_value = initial.displacement[control_global_dof]
    (
        target_direction_signs,
        requested_direction_reversal_count,
        resumed_with_direction_reversal,
    ) = _validate_requested_target_directions(
        targets,
        accepted_value=accepted_value,
        bound_direction=bound_direction,
        prior_cumulative_reversal_count=(
            cumulative_direction_reversal_count
        ),
        control_global_dof=control_global_dof,
        characteristic_length_m=path_scaling.characteristic_length_m,
        config=solver_config,
    )
    checkpoints = [initial]
    steps: list[StatefulCorotationalFrame3DDisplacementControlStepResult] = []
    target_cutback_history: list[
        StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt
    ] = []
    solve_attempt_counter = [0]
    completed_requested_target_count = 0
    completed_requested_target_checkpoint_hashes: list[str] = []
    terminal_reason_code: str | None = None
    for target, leg_direction_sign in zip(
        targets,
        target_direction_signs,
        strict=True,
    ):
        previous_leg_direction_sign = (
            last_completed_leg_direction_sign
            if solver_config.allow_direction_reversal
            else (
                bound_direction
                if completed_requested_target_count == 0
                else target_direction_signs[
                    completed_requested_target_count - 1
                ]
            )
        )
        reversal_from_previous_leg = bool(
            previous_leg_direction_sign is not None
            and leg_direction_sign != previous_leg_direction_sign
        )
        cumulative_target_index = cumulative_completed_target_count + 1
        cutback_history_start = len(target_cutback_history)
        accepted_steps, failure, target_terminal_reason = (
            _solve_target_with_adaptive_target_cutback(
            model,
            solver_config,
            control_global_dof=control_global_dof,
            cumulative_target_index=cumulative_target_index,
            leg_direction_sign=leg_direction_sign,
            reversal_from_previous_leg=reversal_from_previous_leg,
            requested_target=target,
            target=target,
            parent=checkpoints[-1],
            history=target_cutback_history,
            solve_attempt_counter=solve_attempt_counter,
            )
        )
        steps.extend(accepted_steps)
        checkpoints.extend(
            step.accepted_checkpoint
            for step in accepted_steps
            if step.accepted_checkpoint is not None
        )
        if target_terminal_reason is not None:
            if failure is not None:
                steps.append(failure)
            terminal_reason_code = target_terminal_reason
            break
        completed_requested_target_count += 1
        completed_requested_target_checkpoint_hashes.append(
            checkpoints[-1].checkpoint_hash
        )
        cumulative_completed_target_count += 1
        if reversal_from_previous_leg:
            cumulative_direction_reversal_count += 1
        last_completed_leg_direction_sign = leg_direction_sign
        if solver_config.allow_direction_reversal:
            if accepted_target_chain_hash is None:  # pragma: no cover
                raise StatefulCorotationalFrame3DDisplacementControlError(
                    "direct_control_cyclic_target_chain_missing",
                    "cyclic path target chain was not initialized",
                )
            accepted_target_chain_hash = _advance_target_chain_hash(
                previous_chain_hash=accepted_target_chain_hash,
                cumulative_target_index=cumulative_target_index,
                authored_target=target,
                leg_direction_sign=leg_direction_sign,
                reversal_from_previous_leg=reversal_from_previous_leg,
                requested_boundary_checkpoint_hash=(
                    checkpoints[-1].checkpoint_hash
                ),
                accepted_steps=accepted_steps,
                cutback_attempts=tuple(
                    target_cutback_history[cutback_history_start:]
                ),
            )
    last_requested_target_boundary_hash = (
        completed_requested_target_checkpoint_hashes[-1]
        if completed_requested_target_checkpoint_hashes
        else initial.checkpoint_hash
    )
    final_checkpoint_at_requested_target_boundary = bool(
        checkpoints[-1].checkpoint_hash == last_requested_target_boundary_hash
    )
    completed_direction_reversal_count = _direction_reversal_count(
        target_direction_signs[:completed_requested_target_count],
        bound_direction=bound_direction,
    )
    contract_pass = bool(
        terminal_reason_code is None
        and completed_requested_target_count == len(targets)
        and steps
        and all(step.committed for step in steps)
        and steps[-1].solution.metrics["contract_pass"] is True
    )
    final_resume_binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        | None
    ) = None
    if final_checkpoint_at_requested_target_boundary:
        if solver_config.allow_direction_reversal:
            if accepted_target_chain_hash is None:  # pragma: no cover
                raise StatefulCorotationalFrame3DDisplacementControlError(
                    "direct_control_cyclic_target_chain_missing",
                    "cyclic path target chain was not initialized",
                )
            final_resume_binding = _make_cyclic_resume_binding(
                model=model,
                config=solver_config,
                control_global_dof=control_global_dof,
                last_completed_leg_direction_sign=(
                    last_completed_leg_direction_sign
                ),
                cumulative_reversal_count=(
                    cumulative_direction_reversal_count
                ),
                cumulative_completed_target_count=(
                    cumulative_completed_target_count
                ),
                accepted_target_chain_hash=accepted_target_chain_hash,
                checkpoint=checkpoints[-1],
            )
        else:
            final_resume_binding = _make_resume_binding(
                model=model,
                config=solver_config,
                control_global_dof=control_global_dof,
                direction_sign=(
                    target_direction_signs[
                        completed_requested_target_count - 1
                    ]
                    if completed_requested_target_count
                    else (
                        target_direction_signs[0]
                        if bound_direction is None
                        else bound_direction
                    )
                ),
                checkpoint=checkpoints[-1],
            )
    payload = {
        "schema_version": (
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION
        ),
        "profile": STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
        "model_hash": model.model_hash,
        "solver_contract_hash": solver_config.contract_hash,
        "status": "ready" if contract_pass else "blocked",
        "control_global_dof": control_global_dof,
        "control_unit": "m" if control_global_dof % 6 < 3 else "rad",
        "path_mode": path_mode,
        "requested_control_targets": list(targets),
        "requested_target_direction_signs": list(target_direction_signs),
        "requested_direction_reversal_count": (
            requested_direction_reversal_count
        ),
        "completed_direction_reversal_count": (
            completed_direction_reversal_count
        ),
        "resumed_with_direction_reversal": resumed_with_direction_reversal,
        "cumulative_completed_target_count": (
            cumulative_completed_target_count
        ),
        "cumulative_direction_reversal_count": (
            cumulative_direction_reversal_count
        ),
        "accepted_target_chain_hash": accepted_target_chain_hash,
        "initial_checkpoint_hash": initial.checkpoint_hash,
        "checkpoint_hashes": [row.checkpoint_hash for row in checkpoints],
        "step_hashes": [row.result_hash for row in steps],
        "target_cutback_history": [
            row.to_dict() for row in target_cutback_history
        ],
        "completed_requested_target_count": completed_requested_target_count,
        "completed_requested_target_checkpoint_hashes": (
            completed_requested_target_checkpoint_hashes
        ),
        "solve_attempt_count": solve_attempt_counter[0],
        "final_checkpoint_at_requested_target_boundary": (
            final_checkpoint_at_requested_target_boundary
        ),
        "terminal_reason_code": terminal_reason_code,
        "resume_binding": (
            None
            if final_resume_binding is None
            else final_resume_binding.to_dict()
        ),
        "resume_mode": resume_mode,
        "resume_contract_verified": resume_contract_verified,
        "exact_checkpoint_resume_supported": (
            final_checkpoint_at_requested_target_boundary
        ),
        "adaptive_target_cutback_supported": True,
        "adaptive_target_cutback_used": bool(target_cutback_history),
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
        "claim_boundary": (
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY
        ),
    }
    return StatefulCorotationalFrame3DDisplacementControlPathResult(
        schema_version=(
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION
        ),
        profile=STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
        model_hash=model.model_hash,
        solver_contract_hash=solver_config.contract_hash,
        status="ready" if contract_pass else "blocked",
        control_global_dof=control_global_dof,
        control_unit="m" if control_global_dof % 6 < 3 else "rad",
        path_mode=path_mode,
        requested_control_targets=targets,
        requested_target_direction_signs=target_direction_signs,
        requested_direction_reversal_count=(
            requested_direction_reversal_count
        ),
        completed_direction_reversal_count=(
            completed_direction_reversal_count
        ),
        resumed_with_direction_reversal=resumed_with_direction_reversal,
        cumulative_completed_target_count=(
            cumulative_completed_target_count
        ),
        cumulative_direction_reversal_count=(
            cumulative_direction_reversal_count
        ),
        accepted_target_chain_hash=accepted_target_chain_hash,
        initial_checkpoint=initial,
        checkpoints=tuple(checkpoints),
        steps=tuple(steps),
        target_cutback_history=tuple(target_cutback_history),
        completed_requested_target_count=completed_requested_target_count,
        completed_requested_target_checkpoint_hashes=tuple(
            completed_requested_target_checkpoint_hashes
        ),
        solve_attempt_count=solve_attempt_counter[0],
        final_checkpoint_at_requested_target_boundary=(
            final_checkpoint_at_requested_target_boundary
        ),
        terminal_reason_code=terminal_reason_code,
        resume_binding=final_resume_binding,
        resume_mode=resume_mode,
        resume_contract_verified=resume_contract_verified,
        result_hash=canonical_hash(payload),
        exact_checkpoint_resume_supported=(
            final_checkpoint_at_requested_target_boundary
        ),
        adaptive_target_cutback_supported=True,
        adaptive_target_cutback_used=bool(target_cutback_history),
        regularization_used=False,
        fallback_used=False,
        contract_pass=contract_pass,
        claim_boundary=(
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY
        ),
    )


def validate_stateful_corotational_frame3d_displacement_control_resume_binding(
    binding: (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding
        | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
    ),
    *,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    control_global_dof: int,
) -> (
    StatefulCorotationalFrame3DDisplacementControlResumeBinding
    | StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
):
    """Validate an exact direct-control resume binding and its checkpoint."""

    if type(binding) not in (
        StatefulCorotationalFrame3DDisplacementControlResumeBinding,
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_resume_binding_type_invalid",
            "resume binding must be an exact direct-control binding",
        )
    if type(config) is not StatefulCorotationalFrame3DDisplacementControlConfig:
        raise ValueError("config type is invalid")
    _control_free_index(model, control_global_dof)
    binding.to_dict()
    validate_stateful_corotational_frame3d_sparse_checkpoint(
        checkpoint,
        model=model,
        config=config.frame_config,
        require_equilibrium=True,
    )
    expected_unit = "m" if control_global_dof % 6 < 3 else "rad"
    if (
        config.allow_direction_reversal
        and type(binding) is not (
            StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding
        )
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_v1_binding_cyclic_policy_mismatch",
            "cyclic continuation requires a v2 rolling-chain binding",
        )
    if (
        not config.allow_direction_reversal
        and type(binding) is not (
            StatefulCorotationalFrame3DDisplacementControlResumeBinding
        )
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_v2_binding_monotonic_policy_mismatch",
            "monotonic continuation requires a v1 direction binding",
        )
    if (
        binding.model_hash != model.model_hash
        or binding.frame_solver_contract_hash != config.frame_config.contract_hash
        or binding.direct_control_contract_hash != config.contract_hash
        or binding.control_global_dof != control_global_dof
        or binding.control_unit != expected_unit
        or binding.accepted_checkpoint_hash != checkpoint.checkpoint_hash
        or binding.accepted_step_index != checkpoint.step_index
        or binding.accepted_control_target
        != checkpoint.displacement[control_global_dof]
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_resume_binding_contract_mismatch",
            "resume binding does not match the model, solver, control DOF, or checkpoint",
        )
    return binding


def _make_resume_binding(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    control_global_dof: int,
    direction_sign: int,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
) -> StatefulCorotationalFrame3DDisplacementControlResumeBinding:
    provisional = StatefulCorotationalFrame3DDisplacementControlResumeBinding(
        schema_version=(
            STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION
        ),
        profile=STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
        model_hash=model.model_hash,
        frame_solver_contract_hash=config.frame_config.contract_hash,
        direct_control_contract_hash=config.contract_hash,
        control_global_dof=control_global_dof,
        control_unit="m" if control_global_dof % 6 < 3 else "rad",
        direction_sign=direction_sign,
        accepted_control_target=float(checkpoint.displacement[control_global_dof]),
        accepted_step_index=checkpoint.step_index,
        accepted_checkpoint_hash=checkpoint.checkpoint_hash,
        binding_hash=_ZERO_HASH,
    )
    binding = StatefulCorotationalFrame3DDisplacementControlResumeBinding(
        **{
            **_resume_binding_payload(provisional, include_hash=False),
            "binding_hash": canonical_hash(
                _resume_binding_payload(provisional, include_hash=False)
            ),
        }
    )
    binding.to_dict()
    return binding


def _make_cyclic_resume_binding(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DDisplacementControlConfig,
    control_global_dof: int,
    last_completed_leg_direction_sign: int | None,
    cumulative_reversal_count: int,
    cumulative_completed_target_count: int,
    accepted_target_chain_hash: str,
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
) -> StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding:
    provisional = (
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding(
            schema_version=(
                STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION
            ),
            profile=(
                STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE
            ),
            model_hash=model.model_hash,
            frame_solver_contract_hash=config.frame_config.contract_hash,
            direct_control_contract_hash=config.contract_hash,
            control_global_dof=control_global_dof,
            control_unit=("m" if control_global_dof % 6 < 3 else "rad"),
            path_mode=(
                STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE
            ),
            last_completed_leg_direction_sign=(
                last_completed_leg_direction_sign
            ),
            cumulative_reversal_count=cumulative_reversal_count,
            cumulative_completed_target_count=(
                cumulative_completed_target_count
            ),
            accepted_target_chain_hash=accepted_target_chain_hash,
            accepted_control_target=float(
                checkpoint.displacement[control_global_dof]
            ),
            accepted_step_index=checkpoint.step_index,
            accepted_checkpoint_hash=checkpoint.checkpoint_hash,
            binding_hash=_ZERO_HASH,
        )
    )
    payload = _cyclic_resume_binding_payload(provisional, include_hash=False)
    binding = (
        StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding(
            **{
                **payload,
                "binding_hash": canonical_hash(payload),
            }
        )
    )
    binding.to_dict()
    return binding


def _resume_binding_payload(
    binding: StatefulCorotationalFrame3DDisplacementControlResumeBinding,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": binding.schema_version,
        "profile": binding.profile,
        "model_hash": binding.model_hash,
        "frame_solver_contract_hash": binding.frame_solver_contract_hash,
        "direct_control_contract_hash": binding.direct_control_contract_hash,
        "control_global_dof": binding.control_global_dof,
        "control_unit": binding.control_unit,
        "direction_sign": binding.direction_sign,
        "accepted_control_target": binding.accepted_control_target,
        "accepted_step_index": binding.accepted_step_index,
        "accepted_checkpoint_hash": binding.accepted_checkpoint_hash,
    }
    if include_hash:
        payload["binding_hash"] = binding.binding_hash
    return payload


def _cyclic_resume_binding_payload(
    binding: StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": binding.schema_version,
        "profile": binding.profile,
        "model_hash": binding.model_hash,
        "frame_solver_contract_hash": binding.frame_solver_contract_hash,
        "direct_control_contract_hash": binding.direct_control_contract_hash,
        "control_global_dof": binding.control_global_dof,
        "control_unit": binding.control_unit,
        "path_mode": binding.path_mode,
        "last_completed_leg_direction_sign": (
            binding.last_completed_leg_direction_sign
        ),
        "cumulative_reversal_count": binding.cumulative_reversal_count,
        "cumulative_completed_target_count": (
            binding.cumulative_completed_target_count
        ),
        "accepted_target_chain_hash": binding.accepted_target_chain_hash,
        "accepted_control_target": binding.accepted_control_target,
        "accepted_step_index": binding.accepted_step_index,
        "accepted_checkpoint_hash": binding.accepted_checkpoint_hash,
    }
    if include_hash:
        payload["binding_hash"] = binding.binding_hash
    return payload


def finite_difference_stateful_corotational_frame3d_displacement_control_check(
    step_problem: StatefulCorotationalFrame3DDisplacementControlStepProblem,
    *,
    coordinate_step_m: float = 1.0e-7,
) -> dict[str, Any]:
    step = _positive(coordinate_step_m, "coordinate_step_m")
    parent_hash = step_problem.accepted_checkpoint.checkpoint_hash
    parent_state_hashes = tuple(
        state.state_hash
        for state in step_problem.accepted_checkpoint.material_states
    )
    center_coordinates = step_problem.initial_augmented_coordinates_m()
    center = step_problem.assemble(center_coordinates)
    direction = np.arange(1, center_coordinates.size + 1, dtype=np.float64)
    direction /= np.linalg.norm(direction)
    forward_coordinates = center_coordinates + step * direction
    backward_coordinates = center_coordinates - step * direction
    forward = step_problem.assemble(forward_coordinates)
    backward = step_problem.assemble(backward_coordinates)
    finite = (
        np.asarray(forward.augmented_residual_kn)
        - np.asarray(backward.augmented_residual_kn)
    ) / (2.0 * step)
    analytic = center.augmented_jacobian_kn_per_m @ direction
    error = float(np.linalg.norm(finite - analytic, ord=np.inf))
    parent_immutable = bool(
        step_problem.accepted_checkpoint.checkpoint_hash == parent_hash
        and tuple(
            state.state_hash
            for state in step_problem.accepted_checkpoint.material_states
        )
        == parent_state_hashes
    )
    return {
        "profile": STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE,
        "control_global_dof": step_problem.control_global_dof,
        "direction": direction.tolist(),
        "finite_difference": finite.tolist(),
        "analytic": np.asarray(analytic).tolist(),
        "maximum_absolute_error_kn_per_m": error,
        "parent_state_immutable": parent_immutable,
        "scaling_hash": step_problem.equation_scaling.scaling_hash,
    }


def _scaled_residual_tolerance(
    problem: StatefulCorotationalFrame3DDisplacementControlStepProblem,
) -> float:
    config = problem.config.frame_config
    return config.residual_relative_tolerance + (
        config.residual_absolute_tolerance_kn
        / problem.equation_scaling.reference_force_kn
    )


def _scaled_increment_tolerance(
    problem: StatefulCorotationalFrame3DDisplacementControlStepProblem,
) -> float:
    config = problem.config.frame_config
    return config.increment_relative_tolerance + (
        config.increment_absolute_tolerance_m
        / problem.equation_scaling.characteristic_length_m
    )


def _merit(
    problem: StatefulCorotationalFrame3DDisplacementControlStepProblem,
    assembly: StatefulCorotationalFrame3DDisplacementControlAssembly,
) -> float:
    residual = scaled_residual_metrics_6dof(
        assembly.frame_assembly.residual_free,
        problem.model.free_dofs,
        problem.equation_scaling,
    )["scaled"]
    return max(
        residual / _scaled_residual_tolerance(problem),
        abs(assembly.equivalent_control_error_m) / assembly.control_tolerance_m,
    )


def _physical_free_increment(
    problem: StatefulCorotationalFrame3DDisplacementControlStepProblem,
    equivalent_increment_m: Any,
) -> np.ndarray:
    increment = np.asarray(equivalent_increment_m, dtype=np.float64)
    if increment.shape != (len(problem.model.free_dofs),) or not np.all(
        np.isfinite(increment)
    ):
        raise StatefulCorotationalFrame3DDisplacementControlError(
            "direct_control_increment_invalid",
            "equivalent free-coordinate increment is invalid",
        )
    _row, column = equilibration_vectors_6dof(
        problem.model.free_dofs,
        problem.equation_scaling.characteristic_length_m,
    )
    return column * increment


def _control_free_index(
    model: StatefulCorotationalFrame3DSparseModel,
    control_global_dof: int,
) -> int:
    if type(control_global_dof) is not int:
        raise ValueError("control_global_dof must be an integer")
    if control_global_dof not in model.free_dofs:
        raise ValueError("control_global_dof must be one free Frame3D DOF")
    return model.free_dofs.index(control_global_dof)


def _augmented_coordinates(value: Any, size: int) -> np.ndarray:
    try:
        coordinates = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("augmented coordinates contain invalid values") from error
    if coordinates.shape != (size,) or not np.all(np.isfinite(coordinates)):
        raise ValueError("augmented coordinates have invalid shape or values")
    return np.array(coordinates, dtype=np.float64, copy=True)


def _solution_payload(
    solution: StatefulCorotationalFrame3DDisplacementControlSolution,
) -> dict[str, Any]:
    return {
        "status": solution.status,
        "reason_code": solution.reason_code,
        "augmented_coordinates_m": solution.augmented_coordinates_m.tolist(),
        "displacement": list(solution.displacement),
        "load_factor": solution.load_factor,
        "metrics": dict(solution.metrics),
        "convergence_history": [dict(row) for row in solution.convergence_history],
        "line_search_history": [
            {
                **dict(row),
                "attempts": [dict(attempt) for attempt in row["attempts"]],
            }
            for row in solution.line_search_history
        ],
        "factorization_diagnostics": [
            row.to_manifest() for row in solution.factorization_diagnostics
        ],
        "final_assembly_hash": solution.final_assembly.frame_assembly.assembly_hash,
    }


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{name} must be a finite, losslessly representable binary64 number"
        )
    normalized = float(value)
    if (
        not math.isfinite(normalized)
        or value != normalized
        or (type(value) is int and int(normalized) != value)
    ):
        raise ValueError(
            f"{name} must be a finite, losslessly representable binary64 number"
        )
    return 0.0 if normalized == 0.0 else normalized


def _positive(value: Any, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0.0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _linf(value: Any) -> float:
    vector = np.asarray(value, dtype=np.float64)
    return float(np.linalg.norm(vector, ord=np.inf)) if vector.size else 0.0


def _canonical_hash(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


__all__ = [
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_PATH_MODE",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_CYCLIC_RESUME_BINDING_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_PROFILE",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESUME_BINDING_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FRAME3D_DISPLACEMENT_CONTROL_RESULT_SCHEMA_VERSION",
    "StatefulCorotationalFrame3DDisplacementControlAssembly",
    "StatefulCorotationalFrame3DDisplacementControlConfig",
    "StatefulCorotationalFrame3DDisplacementControlCyclicResumeBinding",
    "StatefulCorotationalFrame3DDisplacementControlError",
    "StatefulCorotationalFrame3DDisplacementControlPathResult",
    "StatefulCorotationalFrame3DDisplacementControlResumeBinding",
    "StatefulCorotationalFrame3DDisplacementControlSolution",
    "StatefulCorotationalFrame3DDisplacementControlStepProblem",
    "StatefulCorotationalFrame3DDisplacementControlStepResult",
    "StatefulCorotationalFrame3DDisplacementControlTargetCutbackAttempt",
    "finite_difference_stateful_corotational_frame3d_displacement_control_check",
    "run_stateful_corotational_frame3d_displacement_control_path",
    "solve_stateful_corotational_frame3d_displacement_control",
    "solve_stateful_corotational_frame3d_displacement_control_step",
    "validate_stateful_corotational_frame3d_displacement_control_resume_binding",
]
