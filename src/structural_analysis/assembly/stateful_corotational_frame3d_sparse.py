"""Stateful axial-material and native sparse corotational 3D frame path.

The existing energy-derived 3D element remains the elastic geometric reference.
This module replaces only its axial constitutive response with an immutable
same-parent uniaxial integration, applies the exact axial force/tangent
correction, and scatters member tangents directly to canonical COO/CSR storage.
The bounded larger-graph option uses blocked exact conditioning. It remains an
experimental P2 path and carries no release or external-V&V authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from numbers import Integral, Real
from types import MappingProxyType
from typing import Any, Iterable, Mapping, TypeAlias, TypeGuard, cast

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix, diags

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.assembly.corotational_frame3d_graph import (
    CorotationalFrame3DGraphModel,
)
from structural_analysis.elements.corotational_frame3d import (
    CorotationalFrame3DResponse,
    corotational_frame3d_response,
)
from structural_analysis.elements.stateful_corotational_fiber_frame3d import (
    StatefulCorotationalFiberFrame3D,
    StatefulCorotationalFiberFrame3DResponse,
    StatefulCorotationalFiberFrame3DState,
)
from structural_analysis.elements.stateful_corotational_partial_composite_frame3d import (
    StatefulCorotationalPartialCompositeFrame3D,
    StatefulCorotationalPartialCompositeFrame3DResponse,
    StatefulCorotationalPartialCompositeFrame3DState,
)
from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    immutable_array,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
)
from structural_analysis.materials.bond_slip import BondSlipState
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
    FractureEnergyConcreteDamageMaterial,
)
from structural_analysis.materials.confined_concrete import (
    CONFINED_CONCRETE_PATH_CAPABILITIES,
    ConfinedConcreteAdmissibilityError,
    ConfinedConcreteMaterial,
    ConfinedConcreteState,
    StatefulConfinedConcreteResponse,
)
from structural_analysis.materials.composite_section import (
    ParallelCompositeSectionResponse,
    ParallelCompositeSectionState,
    ParallelSteelConcreteSectionMaterial,
)
from structural_analysis.materials.partial_composite import (
    CondensedPartialCompositeAxialMaterial,
    CondensedPartialCompositeAxialResponse,
    CondensedPartialCompositeAxialState,
)
from structural_analysis.solvers.equation_scaling_6dof import (
    create_equation_scaling_6dof,
    equilibration_vectors_6dof,
    scaled_increment_metrics_6dof,
    scaled_residual_metrics_6dof,
)
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    ScalableSparseFactorizationDiagnostic,
    ScalableSparseFactorizationError,
    ScalableSparseFactorizationPolicy,
    factorize_and_solve_scalable_sparse,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SparseFactorizationDiagnostic,
    SparseFactorizationError,
    SparseFactorizationPolicy,
    factorize_and_solve_sparse,
)


STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE = (
    "stateful_axial_material_corotational_timoshenko_frame3d_native_coo_csr.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_ASSEMBLY_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-sparse-assembly.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-sparse-checkpoint.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-sparse-result.v2"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_STORAGE_PROFILE = (
    "member_12x12_triplet_coalesce_sorted_csr_fp64.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_SCHEMA_VERSION = (
    "stateful-corotational-frame3d-equation-scaling-6dof.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_POLICY = (
    "centroid_diameter_force_moment_6dof.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CLAIM_BOUNDARY = (
    "Experimental bounded-graph 3D corotational Timoshenko path with native "
    "COO/CSR assembly, fail-closed exact-condition SuperLU diagnostics, and "
    "model-bound 6DOF force/moment equation scaling with residual-and-increment "
    "commit gates, residual-decreasing backtracking line search, and bounded "
    "explicitly convergence-classified adaptive load cutback with rejected-trial "
    "rollback and exact material-response accepted-parent hash binding, plus "
    "stateful axial steel, concrete damage, confined-concrete envelope, "
    "perfect-bond parallel composite, or single-slip-mode partial-interaction "
    "integration, plus bounded 2/3-point axial-biaxial distributed-fiber and "
    "two-layer distributed bond-slip corrections. Shear and torsion remain elastic; "
    "general shear-lag/uplift/contact, warping coupling, releases, offsets, member "
    "loads, production-scale material behavior, independent external review, and "
    "release authority remain open."
)
_ZERO_HASH = "sha256:" + "0" * 64
_MPA_M2_TO_KN = 1000.0

AxialMaterial: TypeAlias = (
    BilinearCombinedHardeningSteel
    | AsymmetricConcreteDamageMaterial
    | FractureEnergyConcreteDamageMaterial
    | ParallelSteelConcreteSectionMaterial
    | ConfinedConcreteMaterial
    | CondensedPartialCompositeAxialMaterial
    | StatefulCorotationalFiberFrame3D
    | StatefulCorotationalPartialCompositeFrame3D
)
AxialMaterialState: TypeAlias = (
    UniaxialPlasticityState
    | ConcreteDamageState
    | ParallelCompositeSectionState
    | ConfinedConcreteState
    | CondensedPartialCompositeAxialState
    | StatefulCorotationalFiberFrame3DState
    | StatefulCorotationalPartialCompositeFrame3DState
)
AxialPointMaterialResponse: TypeAlias = (
    UniaxialPlasticityResponse
    | ConcreteDamageResponse
    | ParallelCompositeSectionResponse
    | StatefulConfinedConcreteResponse
    | CondensedPartialCompositeAxialResponse
)
AxialMaterialResponse: TypeAlias = (
    AxialPointMaterialResponse
    | StatefulCorotationalFiberFrame3DResponse
    | StatefulCorotationalPartialCompositeFrame3DResponse
)
ElasticFrame3DModel: TypeAlias = (
    CorotationalFrame3DModel | CorotationalFrame3DGraphModel
)
FactorizationPolicy: TypeAlias = (
    SparseFactorizationPolicy | ScalableSparseFactorizationPolicy
)
FactorizationDiagnostic: TypeAlias = (
    SparseFactorizationDiagnostic | ScalableSparseFactorizationDiagnostic
)


class StatefulCorotationalFrame3DSparseError(RuntimeError):
    """Fail-closed model, state, factorization, or convergence error."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "frame3d_sparse_error",
        retryable_convergence_failure: bool = False,
    ):
        super().__init__(message)
        self.reason_code = reason_code
        self.retryable_convergence_failure = retryable_convergence_failure


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseModel:
    elastic_model: ElasticFrame3DModel
    axial_materials: tuple[AxialMaterial, ...]

    def __post_init__(self) -> None:
        if type(self.elastic_model) not in (
            CorotationalFrame3DModel,
            CorotationalFrame3DGraphModel,
        ):
            raise ValueError(
                "elastic_model must be an exact CorotationalFrame3DModel or "
                "CorotationalFrame3DGraphModel"
            )
        materials = tuple(self.axial_materials)
        if len(materials) != len(self.elastic_model.members):
            raise ValueError("one axial material is required for every member")
        if any(not _supported_material(row) for row in materials):
            raise ValueError(
                "axial_materials must contain supported exact uniaxial material rows"
            )
        for member, material in zip(
            self.elastic_model.members,
            materials,
            strict=True,
        ):
            if type(material) in (
                StatefulCorotationalFiberFrame3D,
                StatefulCorotationalPartialCompositeFrame3D,
            ):
                _validate_member_material_binding(
                    self.elastic_model,
                    member,
                    material,
                )
                continue
            section_modulus = member.section.frame.e_n_per_m2
            material_modulus = _material_elastic_modulus_mpa(material) * _MPA_M2_TO_KN
            relative_error = abs(section_modulus - material_modulus) / max(
                abs(section_modulus),
                abs(material_modulus),
                1.0,
            )
            if relative_error > 1.0e-12:
                raise ValueError(
                    f"member {member.member_id} section/material elastic modulus mismatch"
                )
            _validate_member_material_binding(
                self.elastic_model,
                member,
                material,
            )
        object.__setattr__(self, "axial_materials", materials)

    @property
    def model_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    @property
    def total_dofs(self) -> int:
        return self.elastic_model.total_dofs

    @property
    def free_dofs(self) -> tuple[int, ...]:
        return self.elastic_model.free_dofs

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
            "elastic_model": self.elastic_model.to_manifest(),
            "axial_materials": [
                _material_manifest(material) for material in self.axial_materials
            ],
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseConfig:
    residual_relative_tolerance: float = 1.0e-8
    residual_absolute_tolerance_kn: float = 1.0e-7
    increment_relative_tolerance: float = 1.0e-10
    increment_absolute_tolerance_m: float = 1.0e-12
    maximum_iterations: int = 30
    minimum_characteristic_length_m: float = 1.0e-12
    minimum_reference_force_kn: float = 1.0
    line_search_alphas: tuple[float, ...] = (
        1.0,
        0.5,
        0.25,
        0.125,
        0.0625,
        0.03125,
    )
    adaptive_load_cutback_enabled: bool = True
    load_cutback_ratio: float = 0.5
    maximum_load_cutback_depth: int = 8
    maximum_load_cutback_substeps: int = 256
    minimum_load_increment_factor: float = 1.0e-6
    factorization_policy: FactorizationPolicy = field(
        default_factory=lambda: SparseFactorizationPolicy(
            maximum_condition_number_1=1.0e14,
            minimum_normalized_absolute_pivot=1.0e-16,
            maximum_backward_error=1.0e-12,
            maximum_exact_condition_equations=256,
        )
    )

    def __post_init__(self) -> None:
        for name in (
            "residual_relative_tolerance",
            "residual_absolute_tolerance_kn",
            "increment_relative_tolerance",
            "increment_absolute_tolerance_m",
            "minimum_characteristic_length_m",
            "minimum_reference_force_kn",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be a positive integer")
        if not isinstance(self.line_search_alphas, tuple) or not self.line_search_alphas:
            raise ValueError("line_search_alphas must be a non-empty tuple")
        normalized_alphas: list[float] = []
        previous = math.inf
        for index, value in enumerate(self.line_search_alphas):
            alpha = _positive(value, f"line_search_alphas[{index}]")
            if alpha > 1.0 or alpha >= previous:
                raise ValueError(
                    "line_search_alphas must be strictly decreasing in (0, 1]"
                )
            normalized_alphas.append(alpha)
            previous = alpha
        if normalized_alphas[0] != 1.0:
            raise ValueError("line_search_alphas must start with 1")
        object.__setattr__(self, "line_search_alphas", tuple(normalized_alphas))
        if type(self.adaptive_load_cutback_enabled) is not bool:
            raise ValueError("adaptive_load_cutback_enabled must be a boolean")
        ratio = _positive(self.load_cutback_ratio, "load_cutback_ratio")
        if ratio >= 1.0:
            raise ValueError("load_cutback_ratio must be in (0, 1)")
        object.__setattr__(self, "load_cutback_ratio", ratio)
        if (
            type(self.maximum_load_cutback_depth) is not int
            or self.maximum_load_cutback_depth < 0
        ):
            raise ValueError(
                "maximum_load_cutback_depth must be a nonnegative integer"
            )
        if (
            type(self.maximum_load_cutback_substeps) is not int
            or self.maximum_load_cutback_substeps < 1
        ):
            raise ValueError(
                "maximum_load_cutback_substeps must be a positive integer"
            )
        object.__setattr__(
            self,
            "minimum_load_increment_factor",
            _positive(
                self.minimum_load_increment_factor,
                "minimum_load_increment_factor",
            ),
        )
        if type(self.factorization_policy) not in (
            SparseFactorizationPolicy,
            ScalableSparseFactorizationPolicy,
        ):
            raise ValueError(
                "factorization_policy must be an exact bounded sparse policy"
            )

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
            "residual_relative_tolerance": self.residual_relative_tolerance,
            "residual_absolute_tolerance_kn": self.residual_absolute_tolerance_kn,
            "increment_relative_tolerance": self.increment_relative_tolerance,
            "increment_absolute_tolerance_m": self.increment_absolute_tolerance_m,
            "maximum_iterations": self.maximum_iterations,
            "minimum_characteristic_length_m": (
                self.minimum_characteristic_length_m
            ),
            "minimum_reference_force_kn": self.minimum_reference_force_kn,
            "assembly": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_STORAGE_PROFILE,
            "equation_scaling": (
                STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_POLICY
            ),
            "linear_solver": _factorization_backend_label(self.factorization_policy),
            "factorization_policy": self.factorization_policy.to_manifest(),
            "load_control": {
                "policy": "ordered_finite_targets_with_reversal_allowed",
                "adaptive_cutback": {
                    "enabled": self.adaptive_load_cutback_enabled,
                    "ratio": self.load_cutback_ratio,
                    "maximum_depth": self.maximum_load_cutback_depth,
                    "maximum_accepted_substeps": (
                        self.maximum_load_cutback_substeps
                    ),
                    "minimum_increment_factor": (
                        self.minimum_load_increment_factor
                    ),
                    "retry_reason_codes": [
                        "maximum_iterations_exceeded",
                        "line_search_failed",
                    ],
                    "retry_requires_explicit_convergence_classification": True,
                },
            },
            "line_search": {
                "policy": "strict_scaled_residual_decrease.v1",
                "alphas": list(self.line_search_alphas),
            },
            "regularization_allowed": False,
            "fallback_allowed": False,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DEquationScaling6DOF:
    """Model-bound force/moment and displacement/rotation scaling."""

    schema_version: str
    scaling_hash: str
    policy: str
    model_hash: str
    characteristic_length_m: float
    reference_force_kn: float
    residual_translation_scale_kn: float
    residual_rotation_scale_kn_m: float
    increment_translation_scale_m: float
    increment_rotation_scale_rad: float
    source_node_coordinates_hash: str
    source_reference_load_hash: str
    source_free_dofs_hash: str
    row_equilibration_hash: str
    column_equilibration_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = _equation_scaling_payload(self, include_hash=True)
        if (
            self.schema_version
            != STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_SCHEMA_VERSION
            or self.policy
            != STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_POLICY
            or not _optional_hash(self.model_hash)
            or self.model_hash is None
            or any(
                not _optional_hash(value) or value is None
                for value in (
                    self.scaling_hash,
                    self.source_node_coordinates_hash,
                    self.source_reference_load_hash,
                    self.source_free_dofs_hash,
                    self.row_equilibration_hash,
                    self.column_equilibration_hash,
                )
            )
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "equation scaling identity or hash binding is invalid"
            )
        if any(
            not math.isfinite(value) or value <= 0.0
            for value in (
                self.characteristic_length_m,
                self.reference_force_kn,
                self.residual_translation_scale_kn,
                self.residual_rotation_scale_kn_m,
                self.increment_translation_scale_m,
                self.increment_rotation_scale_rad,
            )
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "equation scaling contains an invalid physical scale"
            )
        if (
            self.residual_translation_scale_kn != self.reference_force_kn
            or self.residual_rotation_scale_kn_m
            != self.reference_force_kn * self.characteristic_length_m
            or self.increment_translation_scale_m
            != self.characteristic_length_m
            or self.increment_rotation_scale_rad != 1.0
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "equation scaling derived scales are inconsistent"
            )
        if self.scaling_hash != canonical_hash(
            _equation_scaling_payload(self, include_hash=False)
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "equation scaling hash mismatch"
            )
        return payload


@dataclass(frozen=True)
class StatefulCorotationalFrame3DMemberResponse:
    member_id: str
    elastic_reference: CorotationalFrame3DResponse
    axial_material_response: AxialMaterialResponse
    axial_strain: float
    axial_force_kn: float
    axial_tangent_kn_per_m: float
    internal_force_global: np.ndarray
    consistent_tangent_global: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "internal_force_global",
            immutable_array(self.internal_force_global, dtype="<f8"),
        )
        object.__setattr__(
            self,
            "consistent_tangent_global",
            immutable_array(self.consistent_tangent_global, dtype="<f8"),
        )
        if self.internal_force_global.shape != (12,):
            raise ValueError("member internal force must contain 12 values")
        if self.consistent_tangent_global.shape != (12, 12):
            raise ValueError("member tangent must be 12 by 12")

    @property
    def trial_state(self) -> AxialMaterialState:
        return self.axial_material_response.state

    def recovery_manifest(self) -> dict[str, Any]:
        elastic = self.elastic_reference
        return {
            "member_id": self.member_id,
            "initial_length_m": elastic.initial_length_m,
            "current_length_m": elastic.current_length_m,
            "basic_deformations": elastic.basic_deformations.tolist(),
            "basic_forces_elastic_reference": elastic.basic_forces.tolist(),
            "axial_strain": self.axial_strain,
            "axial_force_kn": self.axial_force_kn,
            "axial_tangent_kn_per_m": self.axial_tangent_kn_per_m,
            "axial_material_response": self.axial_material_response.to_dict(),
            "global_end_forces": self.internal_force_global.tolist(),
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    solver_contract_hash: str
    step_index: int
    load_factor: float
    displacement: tuple[float, ...]
    material_states: tuple[AxialMaterialState, ...]
    converged_iterations: int
    residual_inf_norm_kn: float
    parent_checkpoint_hash: str | None
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "model_hash": self.model_hash,
            "solver_contract_hash": self.solver_contract_hash,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "displacement": list(self.displacement),
            "material_states": [state.to_dict() for state in self.material_states],
            "converged_iterations": self.converged_iterations,
            "residual_inf_norm_kn": self.residual_inf_norm_kn,
            "parent_checkpoint_hash": self.parent_checkpoint_hash,
            "checkpoint_hash": self.checkpoint_hash,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseAssembly:
    schema_version: str
    profile: str
    storage_profile: str
    model_hash: str
    parent_checkpoint_hash: str
    target_load_factor: float
    assembly_hash: str
    free_equation_count: int
    raw_coo_entry_count: int
    csr_nnz: int
    csr_pattern_hash: str
    csr_numeric_hash: str
    displacement: np.ndarray
    internal_force: np.ndarray
    external_force: np.ndarray
    residual_free: np.ndarray
    reactions: np.ndarray
    coo_row_indices: np.ndarray
    coo_column_indices: np.ndarray
    coo_values_kn_per_m: np.ndarray
    csr_row_ptr: np.ndarray
    csr_column_indices: np.ndarray
    csr_values_kn_per_m: np.ndarray
    member_responses: tuple[StatefulCorotationalFrame3DMemberResponse, ...]
    trial_material_states: tuple[AxialMaterialState, ...]
    _tangent_free_csr: csr_matrix

    @property
    def tangent_free_csr(self) -> csr_matrix:
        return self._tangent_free_csr.copy()

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "storage_profile": self.storage_profile,
            "model_hash": self.model_hash,
            "parent_checkpoint_hash": self.parent_checkpoint_hash,
            "target_load_factor": self.target_load_factor,
            "assembly_hash": self.assembly_hash,
            "free_equation_count": self.free_equation_count,
            "raw_coo_entry_count": self.raw_coo_entry_count,
            "csr_nnz": self.csr_nnz,
            "csr_pattern_hash": self.csr_pattern_hash,
            "csr_numeric_hash": self.csr_numeric_hash,
            "array_hashes": {
                "displacement": array_data_hash(self.displacement),
                "internal_force": array_data_hash(self.internal_force),
                "external_force": array_data_hash(self.external_force),
                "residual_free": array_data_hash(self.residual_free),
                "reactions": array_data_hash(self.reactions),
                "coo_row_indices": array_data_hash(self.coo_row_indices),
                "coo_column_indices": array_data_hash(self.coo_column_indices),
                "coo_values_kn_per_m": array_data_hash(self.coo_values_kn_per_m),
                "csr_row_ptr": array_data_hash(self.csr_row_ptr),
                "csr_column_indices": array_data_hash(self.csr_column_indices),
                "csr_values_kn_per_m": array_data_hash(self.csr_values_kn_per_m),
            },
            "trial_material_state_hashes": [
                state.state_hash for state in self.trial_material_states
            ],
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDenseReference:
    displacement: np.ndarray
    internal_force: np.ndarray
    external_force: np.ndarray
    residual_free: np.ndarray
    reactions: np.ndarray
    tangent_free: np.ndarray
    trial_material_states: tuple[AxialMaterialState, ...]

    def __post_init__(self) -> None:
        for name in (
            "displacement",
            "internal_force",
            "external_force",
            "residual_free",
            "reactions",
            "tangent_free",
        ):
            object.__setattr__(
                self,
                name,
                immutable_array(getattr(self, name), dtype="<f8"),
            )


@dataclass(frozen=True)
class StatefulCorotationalFrame3DDenseSparseParityReceipt:
    schema_version: str
    receipt_hash: str
    model_hash: str
    parent_checkpoint_hash: str
    target_load_factor: float
    sparse_assembly_hash: str
    metrics: Mapping[str, float]
    checks: Mapping[str, bool]

    def to_dict(self) -> dict[str, Any]:
        payload = _parity_payload(self, include_hash=True)
        if self.receipt_hash != canonical_hash(
            _parity_payload(self, include_hash=False)
        ):
            raise ValueError("dense/sparse parity receipt hash mismatch")
        if not all(self.checks.values()):
            raise ValueError("dense/sparse parity receipt contains a failed check")
        return payload


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseStep:
    step_index: int
    load_factor: float
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint
    free_residual_inf_norm_kn: float
    relative_residual: float
    raw_translational_residual_inf_norm_kn: float
    raw_rotational_residual_inf_norm_kn_m: float
    scaled_residual_inf_norm: float
    scaled_residual_tolerance: float
    raw_translation_increment_inf_norm_m: float
    raw_rotation_increment_inf_norm_rad: float
    scaled_increment_inf_norm: float
    scaled_increment_tolerance: float
    residual_gate_passed: bool
    increment_gate_passed: bool
    line_search_required: bool
    selected_line_search_alpha: float | None
    line_search_valid: bool
    material_admissibility_passed: bool
    final_reassembled_equilibrium_passed: bool
    parent_state_immutable: bool
    sparse_diagnostic_passed: bool
    scaled_condition_number_1: float
    equation_scaling_hash: str
    convergence_history: tuple[Mapping[str, Any], ...]
    line_search_history: tuple[Mapping[str, Any], ...]
    reactions: tuple[tuple[int, float], ...]
    factorization_diagnostics: tuple[FactorizationDiagnostic, ...]
    member_results: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "checkpoint": self.checkpoint.to_dict(),
            "free_residual_inf_norm_kn": self.free_residual_inf_norm_kn,
            "relative_residual": self.relative_residual,
            "raw_translational_residual_inf_norm_kn": (
                self.raw_translational_residual_inf_norm_kn
            ),
            "raw_rotational_residual_inf_norm_kn_m": (
                self.raw_rotational_residual_inf_norm_kn_m
            ),
            "scaled_residual_inf_norm": self.scaled_residual_inf_norm,
            "scaled_residual_tolerance": self.scaled_residual_tolerance,
            "raw_translation_increment_inf_norm_m": (
                self.raw_translation_increment_inf_norm_m
            ),
            "raw_rotation_increment_inf_norm_rad": (
                self.raw_rotation_increment_inf_norm_rad
            ),
            "scaled_increment_inf_norm": self.scaled_increment_inf_norm,
            "scaled_increment_tolerance": self.scaled_increment_tolerance,
            "residual_gate_passed": self.residual_gate_passed,
            "increment_gate_passed": self.increment_gate_passed,
            "line_search_required": self.line_search_required,
            "selected_line_search_alpha": self.selected_line_search_alpha,
            "line_search_valid": self.line_search_valid,
            "material_admissibility_passed": self.material_admissibility_passed,
            "final_reassembled_equilibrium_passed": (
                self.final_reassembled_equilibrium_passed
            ),
            "parent_state_immutable": self.parent_state_immutable,
            "sparse_diagnostic_passed": self.sparse_diagnostic_passed,
            "scaled_condition_number_1": self.scaled_condition_number_1,
            "equation_scaling_hash": self.equation_scaling_hash,
            "convergence_history": [
                _thaw_trace_value(row) for row in self.convergence_history
            ],
            "line_search_history": [
                _thaw_trace_value(row) for row in self.line_search_history
            ],
            "reactions": [list(row) for row in self.reactions],
            "factorization_diagnostics": [
                row.to_manifest() for row in self.factorization_diagnostics
            ],
            "member_results": [dict(row) for row in self.member_results],
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DLoadCutbackAttempt:
    attempt_index: int
    recursion_depth: int
    requested_target_load_factor: float
    rejected_target_load_factor: float
    accepted_parent_load_factor: float
    accepted_parent_checkpoint_hash: str
    cutback_target_load_factor: float
    reason_code: str
    parent_state_immutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_index": self.attempt_index,
            "recursion_depth": self.recursion_depth,
            "requested_target_load_factor": self.requested_target_load_factor,
            "rejected_target_load_factor": self.rejected_target_load_factor,
            "accepted_parent_load_factor": self.accepted_parent_load_factor,
            "accepted_parent_checkpoint_hash": (
                self.accepted_parent_checkpoint_hash
            ),
            "cutback_target_load_factor": self.cutback_target_load_factor,
            "reason_code": self.reason_code,
            "parent_state_immutable": self.parent_state_immutable,
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseResult:
    schema_version: str
    profile: str
    model_hash: str
    solver_contract_hash: str
    start_checkpoint_hash: str
    requested_load_factors: tuple[float, ...]
    steps: tuple[StatefulCorotationalFrame3DSparseStep, ...]
    checkpoints: tuple[StatefulCorotationalFrame3DSparseCheckpoint, ...]
    load_cutback_history: tuple[StatefulCorotationalFrame3DLoadCutbackAttempt, ...]
    maximum_free_residual_inf_norm_kn: float
    maximum_scaled_residual_inf_norm: float
    maximum_scaled_increment_inf_norm: float
    equation_scaling: StatefulCorotationalFrame3DEquationScaling6DOF
    result_hash: str
    exact_checkpoint_resume_supported: bool
    material_commit_rollback_supported: bool
    adaptive_load_cutback_supported: bool
    adaptive_load_cutback_used: bool
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
            "start_checkpoint_hash": self.start_checkpoint_hash,
            "requested_load_factors": list(self.requested_load_factors),
            "steps": [step.to_dict() for step in self.steps],
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "load_cutback_history": [
                row.to_dict() for row in self.load_cutback_history
            ],
            "maximum_free_residual_inf_norm_kn": (
                self.maximum_free_residual_inf_norm_kn
            ),
            "maximum_scaled_residual_inf_norm": (
                self.maximum_scaled_residual_inf_norm
            ),
            "maximum_scaled_increment_inf_norm": (
                self.maximum_scaled_increment_inf_norm
            ),
            "equation_scaling": self.equation_scaling.to_dict(),
            "result_hash": self.result_hash,
            "exact_checkpoint_resume_supported": (
                self.exact_checkpoint_resume_supported
            ),
            "material_commit_rollback_supported": (
                self.material_commit_rollback_supported
            ),
            "adaptive_load_cutback_supported": (
                self.adaptive_load_cutback_supported
            ),
            "adaptive_load_cutback_used": self.adaptive_load_cutback_used,
            "regularization_used": self.regularization_used,
            "fallback_used": self.fallback_used,
            "contract_pass": self.contract_pass,
            "claim_boundary": self.claim_boundary,
        }


def stateful_corotational_frame3d_member_response(
    *,
    member: CorotationalFrame3DMember,
    node_coordinates_m: Any,
    element_displacements: Any,
    axial_material: AxialMaterial,
    committed_state: AxialMaterialState,
) -> StatefulCorotationalFrame3DMemberResponse:
    """Evaluate one member from one immutable accepted material parent."""

    if type(member) is not CorotationalFrame3DMember:
        raise ValueError("member must be an exact CorotationalFrame3DMember")
    if not _supported_material(axial_material):
        raise ValueError("axial_material must be a supported exact material")
    if not _material_state_matches(axial_material, committed_state):
        raise ValueError("committed_state does not match axial_material")
    _validate_material_state_admissibility(axial_material, committed_state)
    coordinates = np.asarray(node_coordinates_m, dtype=np.float64)
    displacement = np.asarray(element_displacements, dtype=np.float64)
    if coordinates.shape != (2, 3) or not np.all(np.isfinite(coordinates)):
        raise ValueError("node_coordinates_m must be a finite 2 by 3 array")
    if displacement.shape != (12,) or not np.all(np.isfinite(displacement)):
        raise ValueError("element_displacements must be a finite 12-vector")
    if type(axial_material) is StatefulCorotationalFiberFrame3D:
        assert type(committed_state) is StatefulCorotationalFiberFrame3DState
        distributed = axial_material.integrate(
            displacement,
            committed_state,
            reference_section=member.section,
        )
        _validate_material_response_lineage(
            axial_material,
            committed_state,
            distributed,
        )
        return StatefulCorotationalFrame3DMemberResponse(
            member_id=member.member_id,
            elastic_reference=distributed.elastic_reference,
            axial_material_response=distributed,
            axial_strain=distributed.axial_strain,
            axial_force_kn=distributed.axial_force_kn,
            axial_tangent_kn_per_m=distributed.axial_tangent_kn_per_m,
            internal_force_global=distributed.internal_force_global,
            consistent_tangent_global=distributed.consistent_tangent_global,
        )
    if type(axial_material) is StatefulCorotationalPartialCompositeFrame3D:
        assert type(committed_state) is StatefulCorotationalPartialCompositeFrame3DState
        partial = axial_material.integrate(
            displacement,
            committed_state,
            reference_section=member.section,
        )
        _validate_material_response_lineage(
            axial_material,
            committed_state,
            partial,
        )
        return StatefulCorotationalFrame3DMemberResponse(
            member_id=member.member_id,
            elastic_reference=partial.elastic_reference,
            axial_material_response=partial,
            axial_strain=partial.axial_strain,
            axial_force_kn=partial.axial_force_kn,
            axial_tangent_kn_per_m=partial.axial_tangent_kn_per_m,
            internal_force_global=partial.internal_force_global,
            consistent_tangent_global=partial.consistent_tangent_global,
        )
    elastic = corotational_frame3d_response(
        node_coordinates_m=coordinates,
        element_displacements=displacement,
        section=member.section,
        local_axis_roll_deg=member.local_axis_roll_deg,
    )
    extension = float(elastic.basic_deformations[0])
    axial_strain = extension / elastic.initial_length_m
    material_response = _integrate_axial_material(
        axial_material,
        axial_strain,
        committed_state,
    )
    _validate_material_response_lineage(
        axial_material,
        committed_state,
        material_response,
    )
    area = member.section.frame.area_m2
    axial_force = material_response.stress_mpa * area * _MPA_M2_TO_KN
    axial_tangent = (
        material_response.consistent_tangent_mpa
        * area
        * _MPA_M2_TO_KN
        / elastic.initial_length_m
    )
    elastic_axial_tangent = (
        member.section.frame.e_n_per_m2 * area / elastic.initial_length_m
    )
    elastic_axial_force = elastic_axial_tangent * extension
    current_start = coordinates[0] + displacement[0:3]
    current_end = coordinates[1] + displacement[6:9]
    current_chord = current_end - current_start
    current_length = float(np.linalg.norm(current_chord))
    if not math.isfinite(current_length) or current_length <= 1.0e-12:
        raise ValueError("current member chord is degenerate")
    direction = current_chord / current_length
    axial_gradient = np.zeros(12, dtype=np.float64)
    axial_gradient[0:3] = -direction
    axial_gradient[6:9] = direction
    projector = (np.eye(3, dtype=np.float64) - np.outer(direction, direction)) / (
        current_length
    )
    axial_hessian = np.zeros((12, 12), dtype=np.float64)
    axial_hessian[0:3, 0:3] = projector
    axial_hessian[6:9, 6:9] = projector
    axial_hessian[0:3, 6:9] = -projector
    axial_hessian[6:9, 0:3] = -projector
    force_correction = axial_force - elastic_axial_force
    tangent_correction = axial_tangent - elastic_axial_tangent
    internal = (
        np.asarray(elastic.internal_force_global, dtype=np.float64)
        + axial_gradient * force_correction
    )
    tangent = (
        np.asarray(elastic.consistent_tangent_global, dtype=np.float64)
        + np.outer(axial_gradient, axial_gradient) * tangent_correction
        + axial_hessian * force_correction
    )
    tangent[:] = 0.5 * (tangent + tangent.T)
    if not np.all(np.isfinite(internal)) or not np.all(np.isfinite(tangent)):
        raise StatefulCorotationalFrame3DSparseError(
            "stateful member response produced non-finite data"
        )
    return StatefulCorotationalFrame3DMemberResponse(
        member_id=member.member_id,
        elastic_reference=elastic,
        axial_material_response=material_response,
        axial_strain=axial_strain,
        axial_force_kn=axial_force,
        axial_tangent_kn_per_m=axial_tangent,
        internal_force_global=internal,
        consistent_tangent_global=tangent,
    )


def stateful_corotational_frame3d_equation_scaling_6dof(
    model: StatefulCorotationalFrame3DSparseModel,
    *,
    config: StatefulCorotationalFrame3DSparseConfig,
) -> StatefulCorotationalFrame3DEquationScaling6DOF:
    """Derive deterministic 6DOF force/moment scaling from model evidence."""

    if type(model) is not StatefulCorotationalFrame3DSparseModel:
        raise ValueError(
            "model must be an exact StatefulCorotationalFrame3DSparseModel"
        )
    if type(config) is not StatefulCorotationalFrame3DSparseConfig:
        raise ValueError(
            "config must be an exact StatefulCorotationalFrame3DSparseConfig"
        )
    coordinates = np.asarray(
        model.elastic_model.node_coordinates_m,
        dtype=np.float64,
    )
    if (
        coordinates.ndim != 2
        or coordinates.shape[1] != 3
        or not np.all(np.isfinite(coordinates))
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "equation scaling node coordinates are invalid"
        )
    reference_load = np.asarray(
        model.elastic_model.reference_load_kn,
        dtype=np.float64,
    )
    free = np.asarray(model.free_dofs, dtype=np.int64)
    common = create_equation_scaling_6dof(
        source_identity_hash=model.model_hash,
        node_coordinates_m=coordinates,
        reference_equation_load=reference_load,
        free_dofs=model.free_dofs,
        minimum_characteristic_length_m=config.minimum_characteristic_length_m,
        minimum_reference_force=config.minimum_reference_force_kn,
    )
    characteristic_length = common.characteristic_length_m
    reference_force = common.reference_force
    row_scale, column_scale = equilibration_vectors_6dof(
        model.free_dofs, characteristic_length
    )
    provisional = StatefulCorotationalFrame3DEquationScaling6DOF(
        schema_version=(
            STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_SCHEMA_VERSION
        ),
        scaling_hash=_ZERO_HASH,
        policy=STATEFUL_COROTATIONAL_FRAME3D_EQUATION_SCALING_POLICY,
        model_hash=model.model_hash,
        characteristic_length_m=characteristic_length,
        reference_force_kn=reference_force,
        residual_translation_scale_kn=reference_force,
        residual_rotation_scale_kn_m=reference_force * characteristic_length,
        increment_translation_scale_m=characteristic_length,
        increment_rotation_scale_rad=1.0,
        source_node_coordinates_hash=array_data_hash(
            np.asarray(coordinates, dtype="<f8")
        ),
        source_reference_load_hash=array_data_hash(
            np.asarray(reference_load, dtype="<f8")
        ),
        source_free_dofs_hash=array_data_hash(np.asarray(free, dtype="<i8")),
        row_equilibration_hash=array_data_hash(
            np.asarray(row_scale, dtype="<f8")
        ),
        column_equilibration_hash=array_data_hash(
            np.asarray(column_scale, dtype="<f8")
        ),
    )
    scaling = replace(
        provisional,
        scaling_hash=canonical_hash(
            _equation_scaling_payload(provisional, include_hash=False)
        ),
    )
    if (
        not math.isfinite(scaling.characteristic_length_m)
        or not math.isfinite(scaling.reference_force_kn)
        or scaling.characteristic_length_m <= 0.0
        or scaling.reference_force_kn <= 0.0
        or not math.isfinite(scaling.residual_rotation_scale_kn_m)
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "equation scaling contains a non-finite or non-positive scale"
        )
    return scaling


def initial_stateful_corotational_frame3d_sparse_checkpoint(
    model: StatefulCorotationalFrame3DSparseModel,
    *,
    config: StatefulCorotationalFrame3DSparseConfig,
) -> StatefulCorotationalFrame3DSparseCheckpoint:
    scaling = stateful_corotational_frame3d_equation_scaling_6dof(
        model,
        config=config,
    )
    states = tuple(
        _initial_material_state(material) for material in model.axial_materials
    )
    displacement = np.zeros(model.total_dofs, dtype=np.float64)
    assembly = _assemble_sparse_core(
        model,
        states,
        parent_checkpoint_hash=_ZERO_HASH,
        target_load_factor=0.0,
        displacement=displacement,
    )
    residual = _linf(assembly.residual_free)
    residual_metrics = _scaled_residual_metrics(
        assembly.residual_free,
        model.free_dofs,
        scaling,
    )
    if residual_metrics["scaled"] > _scaled_residual_tolerance(config, scaling):
        raise StatefulCorotationalFrame3DSparseError(
            "zero state does not satisfy unloaded equilibrium"
        )
    return _make_checkpoint(
        model=model,
        config=config,
        step_index=0,
        load_factor=0.0,
        displacement=displacement,
        material_states=assembly.trial_material_states,
        converged_iterations=0,
        residual_inf_norm_kn=residual,
        parent_checkpoint_hash=None,
    )


def assemble_stateful_corotational_frame3d_sparse(
    model: StatefulCorotationalFrame3DSparseModel,
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    *,
    target_load_factor: float,
    trial_displacement: Any,
) -> StatefulCorotationalFrame3DSparseAssembly:
    validate_stateful_corotational_frame3d_sparse_checkpoint(
        accepted_checkpoint,
        model=model,
        config=None,
        require_equilibrium=False,
    )
    return _assemble_sparse_core(
        model,
        accepted_checkpoint.material_states,
        parent_checkpoint_hash=accepted_checkpoint.checkpoint_hash,
        target_load_factor=_finite(target_load_factor, "target_load_factor"),
        displacement=_displacement(model, trial_displacement),
    )


def assemble_stateful_corotational_frame3d_dense_reference(
    model: StatefulCorotationalFrame3DSparseModel,
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    *,
    target_load_factor: float,
    trial_displacement: Any,
) -> StatefulCorotationalFrame3DDenseReference:
    """Independently scatter the same member responses to a dense reference."""

    validate_stateful_corotational_frame3d_sparse_checkpoint(
        accepted_checkpoint,
        model=model,
        config=None,
        require_equilibrium=False,
    )
    values = _displacement(model, trial_displacement)
    factor = _finite(target_load_factor, "target_load_factor")
    internal = np.zeros(model.total_dofs, dtype=np.float64)
    tangent = np.zeros((model.total_dofs, model.total_dofs), dtype=np.float64)
    states: list[AxialMaterialState] = []
    coordinates = np.asarray(model.elastic_model.node_coordinates_m, dtype=np.float64)
    for member, material, parent in zip(
        model.elastic_model.members,
        model.axial_materials,
        accepted_checkpoint.material_states,
        strict=True,
    ):
        dofs = _member_dofs(member)
        try:
            response = stateful_corotational_frame3d_member_response(
                member=member,
                node_coordinates_m=coordinates[[member.node_i, member.node_j]],
                element_displacements=values[list(dofs)],
                axial_material=material,
                committed_state=parent,
            )
        except ConfinedConcreteAdmissibilityError as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"{error.code}: member {member.member_id}: {error.detail}",
                reason_code=error.code,
            ) from error
        except StatefulCorotationalFrame3DSparseError:
            raise
        except RuntimeError as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"material integration failed for member {member.member_id}: {error}",
                reason_code="material_integration_failed",
            ) from error
        except (ValueError, ArithmeticError) as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"member trial is inadmissible for {member.member_id}: {error}",
                reason_code="member_trial_inadmissible",
            ) from error
        internal[list(dofs)] += response.internal_force_global
        tangent[np.ix_(dofs, dofs)] += response.consistent_tangent_global
        states.append(response.trial_state)
    tangent[:] = 0.5 * (tangent + tangent.T)
    external = factor * np.asarray(
        model.elastic_model.reference_load_kn,
        dtype=np.float64,
    )
    residual = internal - external
    free = list(model.free_dofs)
    reactions = np.zeros(model.total_dofs, dtype=np.float64)
    reactions[list(model.elastic_model.restrained_dofs)] = residual[
        list(model.elastic_model.restrained_dofs)
    ]
    return StatefulCorotationalFrame3DDenseReference(
        displacement=values,
        internal_force=internal,
        external_force=external,
        residual_free=residual[free],
        reactions=reactions,
        tangent_free=tangent[np.ix_(free, free)],
        trial_material_states=tuple(states),
    )


def stateful_corotational_frame3d_dense_sparse_parity_receipt(
    model: StatefulCorotationalFrame3DSparseModel,
    accepted_checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    *,
    target_load_factor: float,
    trial_displacement: Any,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 1.0e-12,
) -> StatefulCorotationalFrame3DDenseSparseParityReceipt:
    sparse = assemble_stateful_corotational_frame3d_sparse(
        model,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_displacement=trial_displacement,
    )
    dense = assemble_stateful_corotational_frame3d_dense_reference(
        model,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_displacement=trial_displacement,
    )
    sparse_tangent = sparse.tangent_free_csr.toarray()
    metrics = MappingProxyType(
        {
            "maximum_internal_force_absolute_delta": _max_abs(
                sparse.internal_force - dense.internal_force
            ),
            "maximum_residual_absolute_delta": _max_abs(
                sparse.residual_free - dense.residual_free
            ),
            "maximum_reaction_absolute_delta": _max_abs(
                sparse.reactions - dense.reactions
            ),
            "maximum_tangent_absolute_delta": _max_abs(
                sparse_tangent - dense.tangent_free
            ),
        }
    )
    checks = MappingProxyType(
        {
            "internal_force_parity": bool(
                np.allclose(
                    sparse.internal_force,
                    dense.internal_force,
                    atol=absolute_tolerance,
                    rtol=relative_tolerance,
                )
            ),
            "residual_parity": bool(
                np.allclose(
                    sparse.residual_free,
                    dense.residual_free,
                    atol=absolute_tolerance,
                    rtol=relative_tolerance,
                )
            ),
            "reaction_parity": bool(
                np.allclose(
                    sparse.reactions,
                    dense.reactions,
                    atol=absolute_tolerance,
                    rtol=relative_tolerance,
                )
            ),
            "tangent_parity": bool(
                np.allclose(
                    sparse_tangent,
                    dense.tangent_free,
                    atol=absolute_tolerance,
                    rtol=relative_tolerance,
                )
            ),
            "trial_state_hash_parity": bool(
                tuple(state.state_hash for state in sparse.trial_material_states)
                == tuple(state.state_hash for state in dense.trial_material_states)
            ),
            "canonical_csr": bool(
                sparse.tangent_free_csr.has_sorted_indices
                and sparse.tangent_free_csr.has_canonical_format
            ),
        }
    )
    provisional = StatefulCorotationalFrame3DDenseSparseParityReceipt(
        schema_version="stateful-corotational-frame3d-dense-sparse-parity.v1",
        receipt_hash=_ZERO_HASH,
        model_hash=model.model_hash,
        parent_checkpoint_hash=accepted_checkpoint.checkpoint_hash,
        target_load_factor=float(target_load_factor),
        sparse_assembly_hash=sparse.assembly_hash,
        metrics=metrics,
        checks=checks,
    )
    receipt = replace(
        provisional,
        receipt_hash=canonical_hash(_parity_payload(provisional, include_hash=False)),
    )
    receipt.to_dict()
    return receipt


_LOAD_CUTBACK_RETRY_REASON_CODES = frozenset(
    {
        "maximum_iterations_exceeded",
        "line_search_failed",
    }
)


def _load_cutback_failure_is_retryable(
    error: StatefulCorotationalFrame3DSparseError,
) -> bool:
    return bool(
        error.retryable_convergence_failure
        and error.reason_code in _LOAD_CUTBACK_RETRY_REASON_CODES
    )


def _solve_target_with_adaptive_load_cutback(
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DSparseConfig,
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
    *,
    requested_target: float,
    target: float,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
    history: list[StatefulCorotationalFrame3DLoadCutbackAttempt],
) -> tuple[StatefulCorotationalFrame3DSparseStep, ...]:
    accepted: list[StatefulCorotationalFrame3DSparseStep] = []
    accepted_parent = parent
    attempt_target = target
    cutback_depth = 0
    while True:
        parent_checkpoint_hash = accepted_parent.checkpoint_hash
        parent_state_hashes = tuple(
            state.state_hash for state in accepted_parent.material_states
        )
        try:
            step = _solve_step(
                model,
                config,
                scaling,
                attempt_target,
                accepted_parent,
            )
        except StatefulCorotationalFrame3DSparseError as error:
            parent_immutable = bool(
                accepted_parent.checkpoint_hash == parent_checkpoint_hash
                and tuple(
                    state.state_hash for state in accepted_parent.material_states
                )
                == parent_state_hashes
            )
            if not parent_immutable:
                raise StatefulCorotationalFrame3DSparseError(
                    "failed Frame3D trial mutated its accepted parent",
                    reason_code="failed_trial_parent_mutated",
                ) from error
            if (
                not config.adaptive_load_cutback_enabled
                or not _load_cutback_failure_is_retryable(error)
            ):
                raise
            increment = attempt_target - accepted_parent.load_factor
            cutback_target = (
                accepted_parent.load_factor
                + config.load_cutback_ratio * increment
            )
            left_increment = abs(
                cutback_target - accepted_parent.load_factor
            )
            right_increment = abs(attempt_target - cutback_target)
            cutback_available = bool(
                cutback_depth < config.maximum_load_cutback_depth
                and math.isfinite(cutback_target)
                and cutback_target
                not in (accepted_parent.load_factor, attempt_target)
                and min(left_increment, right_increment)
                >= config.minimum_load_increment_factor
            )
            if not cutback_available:
                raise StatefulCorotationalFrame3DSparseError(
                    "adaptive load cutback exhausted before requested target "
                    f"{requested_target}; rejected target {attempt_target}; "
                    f"reason {error.reason_code}",
                    reason_code="adaptive_load_cutback_exhausted",
                ) from error
            history.append(
                StatefulCorotationalFrame3DLoadCutbackAttempt(
                    attempt_index=len(history),
                    recursion_depth=cutback_depth,
                    requested_target_load_factor=requested_target,
                    rejected_target_load_factor=attempt_target,
                    accepted_parent_load_factor=accepted_parent.load_factor,
                    accepted_parent_checkpoint_hash=(
                        accepted_parent.checkpoint_hash
                    ),
                    cutback_target_load_factor=cutback_target,
                    reason_code=error.reason_code,
                    parent_state_immutable=True,
                )
            )
            attempt_target = cutback_target
            cutback_depth += 1
            continue
        accepted.append(step)
        accepted_parent = step.checkpoint
        if attempt_target == requested_target:
            return tuple(accepted)
        if len(accepted) >= config.maximum_load_cutback_substeps:
            raise StatefulCorotationalFrame3DSparseError(
                "adaptive load cutback exceeded the accepted-substep bound "
                f"before requested target {requested_target}",
                reason_code="adaptive_load_cutback_substep_limit_exceeded",
            )
        attempt_target = requested_target
        cutback_depth = 0


def solve_stateful_corotational_frame3d_sparse_load_path(
    model: StatefulCorotationalFrame3DSparseModel,
    load_factors: Iterable[float],
    *,
    config: StatefulCorotationalFrame3DSparseConfig,
    resume_from: StatefulCorotationalFrame3DSparseCheckpoint | None = None,
) -> StatefulCorotationalFrame3DSparseResult:
    if type(model) is not StatefulCorotationalFrame3DSparseModel:
        raise ValueError(
            "model must be an exact StatefulCorotationalFrame3DSparseModel"
        )
    if type(config) is not StatefulCorotationalFrame3DSparseConfig:
        raise ValueError(
            "config must be an exact StatefulCorotationalFrame3DSparseConfig"
        )
    scaling = stateful_corotational_frame3d_equation_scaling_6dof(
        model,
        config=config,
    )
    checkpoint = (
        initial_stateful_corotational_frame3d_sparse_checkpoint(model, config=config)
        if resume_from is None
        else validate_stateful_corotational_frame3d_sparse_checkpoint(
            resume_from,
            model=model,
            config=config,
            require_equilibrium=True,
        )
    )
    factors = _load_factors(load_factors, after=checkpoint.load_factor)
    checkpoints = [checkpoint]
    steps: list[StatefulCorotationalFrame3DSparseStep] = []
    load_cutback_history: list[StatefulCorotationalFrame3DLoadCutbackAttempt] = []
    for factor in factors:
        accepted_steps = _solve_target_with_adaptive_load_cutback(
            model,
            config,
            scaling,
            requested_target=factor,
            target=factor,
            parent=checkpoints[-1],
            history=load_cutback_history,
        )
        steps.extend(accepted_steps)
        checkpoints.extend(step.checkpoint for step in accepted_steps)
    maximum_residual = max(
        (row.free_residual_inf_norm_kn for row in steps),
        default=checkpoint.residual_inf_norm_kn,
    )
    maximum_scaled_residual = max(
        (row.scaled_residual_inf_norm for row in steps),
        default=0.0,
    )
    maximum_scaled_increment = max(
        (row.scaled_increment_inf_norm for row in steps),
        default=0.0,
    )
    contract_pass = bool(
        steps
        and all(
            row.residual_gate_passed
            and row.increment_gate_passed
            and row.line_search_valid
            and row.material_admissibility_passed
            and row.final_reassembled_equilibrium_passed
            and row.parent_state_immutable
            and row.sparse_diagnostic_passed
            for row in steps
        )
    )
    payload = {
        "schema_version": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION,
        "profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        "model_hash": model.model_hash,
        "solver_contract_hash": config.contract_hash,
        "start_checkpoint_hash": checkpoint.checkpoint_hash,
        "requested_load_factors": list(factors),
        "steps": [step.to_dict() for step in steps],
        "load_cutback_history": [
            row.to_dict() for row in load_cutback_history
        ],
        "maximum_free_residual_inf_norm_kn": maximum_residual,
        "maximum_scaled_residual_inf_norm": maximum_scaled_residual,
        "maximum_scaled_increment_inf_norm": maximum_scaled_increment,
        "equation_scaling": scaling.to_dict(),
        "exact_checkpoint_resume_supported": True,
        "material_commit_rollback_supported": True,
        "adaptive_load_cutback_supported": True,
        "adaptive_load_cutback_used": bool(load_cutback_history),
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": contract_pass,
        "claim_boundary": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CLAIM_BOUNDARY,
    }
    return StatefulCorotationalFrame3DSparseResult(
        schema_version=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION,
        profile=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        model_hash=model.model_hash,
        solver_contract_hash=config.contract_hash,
        start_checkpoint_hash=checkpoint.checkpoint_hash,
        requested_load_factors=factors,
        steps=tuple(steps),
        checkpoints=tuple(checkpoints),
        load_cutback_history=tuple(load_cutback_history),
        maximum_free_residual_inf_norm_kn=maximum_residual,
        maximum_scaled_residual_inf_norm=maximum_scaled_residual,
        maximum_scaled_increment_inf_norm=maximum_scaled_increment,
        equation_scaling=scaling,
        result_hash=canonical_hash(payload),
        exact_checkpoint_resume_supported=True,
        material_commit_rollback_supported=True,
        adaptive_load_cutback_supported=True,
        adaptive_load_cutback_used=bool(load_cutback_history),
        regularization_used=False,
        fallback_used=False,
        contract_pass=contract_pass,
        claim_boundary=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CLAIM_BOUNDARY,
    )


def validate_stateful_corotational_frame3d_sparse_checkpoint(
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DSparseConfig | None,
    require_equilibrium: bool = True,
) -> StatefulCorotationalFrame3DSparseCheckpoint:
    if type(checkpoint) is not StatefulCorotationalFrame3DSparseCheckpoint:
        raise StatefulCorotationalFrame3DSparseError("checkpoint type is invalid")
    if (
        checkpoint.schema_version
        != STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CHECKPOINT_SCHEMA_VERSION
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint schema version is invalid"
        )
    if (
        checkpoint.profile != STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE
        or checkpoint.model_hash != model.model_hash
        or not _optional_hash(checkpoint.solver_contract_hash)
        or checkpoint.solver_contract_hash is None
        or (
            config is not None
            and checkpoint.solver_contract_hash != config.contract_hash
        )
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint contract binding is invalid"
        )
    if type(checkpoint.step_index) is not int or checkpoint.step_index < 0:
        raise StatefulCorotationalFrame3DSparseError("checkpoint step index is invalid")
    try:
        values = _displacement(model, checkpoint.displacement)
    except ValueError as error:
        raise StatefulCorotationalFrame3DSparseError(
            f"checkpoint displacement is invalid: {error}",
            reason_code="checkpoint_displacement_invalid",
        ) from error
    if canonical_json_bytes(list(checkpoint.displacement)) != canonical_json_bytes(
        values.tolist()
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint displacement changes during binary64 normalization",
            reason_code="checkpoint_displacement_numeric_domain_mismatch",
        )
    if len(checkpoint.material_states) != len(model.elastic_model.members) or any(
        not _material_state_matches(material, state)
        for material, state in zip(
            model.axial_materials,
            checkpoint.material_states,
            strict=True,
        )
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint material state rows are invalid"
        )
    for material, state in zip(
        model.axial_materials,
        checkpoint.material_states,
        strict=True,
    ):
        _validate_material_state_admissibility(material, state)
    if (
        type(checkpoint.load_factor) is not float
        or not math.isfinite(checkpoint.load_factor)
        or type(checkpoint.converged_iterations) is not int
        or checkpoint.converged_iterations < 0
        or type(checkpoint.residual_inf_norm_kn) is not float
        or not math.isfinite(checkpoint.residual_inf_norm_kn)
        or checkpoint.residual_inf_norm_kn < 0.0
        or not _optional_hash(checkpoint.parent_checkpoint_hash)
        or (checkpoint.step_index == 0)
        != (checkpoint.parent_checkpoint_hash is None)
        or (checkpoint.step_index == 0 and checkpoint.converged_iterations != 0)
        or (
            checkpoint.step_index > 0
            and checkpoint.parent_checkpoint_hash == _ZERO_HASH
        )
        or (
            config is not None
            and checkpoint.converged_iterations > config.maximum_iterations
        )
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint scalar metadata is invalid"
        )
    if checkpoint.step_index == 0:
        initial_states = tuple(
            _initial_material_state(material) for material in model.axial_materials
        )
        zero_displacement = np.zeros(model.total_dofs, dtype=np.float64)
        genesis_assembly = _assemble_sparse_core(
            model,
            initial_states,
            parent_checkpoint_hash=_ZERO_HASH,
            target_load_factor=0.0,
            displacement=zero_displacement,
        )
        genesis_state_hashes = tuple(
            state.state_hash for state in genesis_assembly.trial_material_states
        )
        genesis_residual = _linf(genesis_assembly.residual_free)
        if (
            checkpoint.load_factor != 0.0
            or np.any(values != 0.0)
            or checkpoint.residual_inf_norm_kn != genesis_residual
            or tuple(state.state_hash for state in checkpoint.material_states)
            != genesis_state_hashes
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "checkpoint genesis state is not the deterministic unloaded initial state",
                reason_code="checkpoint_genesis_state_invalid",
            )
    expected_hash = canonical_hash(_checkpoint_payload(checkpoint, include_hash=False))
    if checkpoint.checkpoint_hash != expected_hash:
        raise StatefulCorotationalFrame3DSparseError("checkpoint hash mismatch")
    replay_assembly = _assemble_sparse_core(
        model,
        checkpoint.material_states,
        parent_checkpoint_hash=checkpoint.checkpoint_hash,
        target_load_factor=checkpoint.load_factor,
        displacement=values,
    )
    if tuple(
        state.state_hash for state in replay_assembly.trial_material_states
    ) != tuple(state.state_hash for state in checkpoint.material_states):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint material state is not idempotent at its stored displacement",
            reason_code="checkpoint_material_state_replay_invalid",
        )
    if require_equilibrium:
        if config is None:
            raise ValueError("config is required for equilibrium validation")
        scaling = stateful_corotational_frame3d_equation_scaling_6dof(
            model,
            config=config,
        )
        residual = _linf(replay_assembly.residual_free)
        residual_metrics = _scaled_residual_metrics(
            replay_assembly.residual_free,
            model.free_dofs,
            scaling,
        )
        scaled_tolerance = _scaled_residual_tolerance(config, scaling)
        if residual_metrics["scaled"] > scaled_tolerance:
            raise StatefulCorotationalFrame3DSparseError(
                "checkpoint free-equation equilibrium is invalid"
            )
        if abs(residual - checkpoint.residual_inf_norm_kn) > max(
            config.residual_absolute_tolerance_kn,
            1.0e-12,
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "checkpoint residual observation is inconsistent"
            )
    return checkpoint


def _assemble_sparse_core(
    model: StatefulCorotationalFrame3DSparseModel,
    parent_states: tuple[AxialMaterialState, ...],
    *,
    parent_checkpoint_hash: str,
    target_load_factor: float,
    displacement: np.ndarray,
) -> StatefulCorotationalFrame3DSparseAssembly:
    free_dofs = model.free_dofs
    free_position = {dof: index for index, dof in enumerate(free_dofs)}
    internal = np.zeros(model.total_dofs, dtype=np.float64)
    responses: list[StatefulCorotationalFrame3DMemberResponse] = []
    states: list[AxialMaterialState] = []
    coo_rows: list[int] = []
    coo_columns: list[int] = []
    coo_values: list[float] = []
    coordinates = np.asarray(model.elastic_model.node_coordinates_m, dtype=np.float64)
    for member, material, parent in zip(
        model.elastic_model.members,
        model.axial_materials,
        parent_states,
        strict=True,
    ):
        dofs = _member_dofs(member)
        try:
            response = stateful_corotational_frame3d_member_response(
                member=member,
                node_coordinates_m=coordinates[[member.node_i, member.node_j]],
                element_displacements=displacement[list(dofs)],
                axial_material=material,
                committed_state=parent,
            )
        except ConfinedConcreteAdmissibilityError as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"{error.code}: member {member.member_id}: {error.detail}",
                reason_code=error.code,
            ) from error
        except StatefulCorotationalFrame3DSparseError:
            raise
        except RuntimeError as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"material integration failed for member {member.member_id}: {error}",
                reason_code="material_integration_failed",
            ) from error
        except (ValueError, ArithmeticError) as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"member trial is inadmissible for {member.member_id}: {error}",
                reason_code="member_trial_inadmissible",
            ) from error
        internal[list(dofs)] += response.internal_force_global
        tangent = response.consistent_tangent_global
        for local_row, global_row in enumerate(dofs):
            sparse_row = free_position.get(global_row)
            if sparse_row is None:
                continue
            for local_column, global_column in enumerate(dofs):
                sparse_column = free_position.get(global_column)
                if sparse_column is None:
                    continue
                coo_rows.append(sparse_row)
                coo_columns.append(sparse_column)
                coo_values.append(float(tangent[local_row, local_column]))
        responses.append(response)
        states.append(response.trial_state)
    size = len(free_dofs)
    coo = coo_matrix(
        (
            np.asarray(coo_values, dtype=np.float64),
            (
                np.asarray(coo_rows, dtype=np.int64),
                np.asarray(coo_columns, dtype=np.int64),
            ),
        ),
        shape=(size, size),
        dtype=np.float64,
    )
    csr = coo.tocsr(copy=True)
    csr.sum_duplicates()
    csr.eliminate_zeros()
    csr.sort_indices()
    if (
        csr.shape != (size, size)
        or not csr.has_canonical_format
        or not np.all(np.isfinite(csr.data))
    ):
        raise StatefulCorotationalFrame3DSparseError("native sparse tangent is invalid")
    external = target_load_factor * np.asarray(
        model.elastic_model.reference_load_kn,
        dtype=np.float64,
    )
    residual = internal - external
    reactions = np.zeros(model.total_dofs, dtype=np.float64)
    restrained = list(model.elastic_model.restrained_dofs)
    reactions[restrained] = residual[restrained]
    frozen = {
        "displacement": immutable_array(displacement, dtype="<f8"),
        "internal": immutable_array(internal, dtype="<f8"),
        "external": immutable_array(external, dtype="<f8"),
        "residual": immutable_array(residual[list(free_dofs)], dtype="<f8"),
        "reactions": immutable_array(reactions, dtype="<f8"),
        "coo_rows": immutable_array(coo_rows, dtype="<i8"),
        "coo_columns": immutable_array(coo_columns, dtype="<i8"),
        "coo_values": immutable_array(coo_values, dtype="<f8"),
        "csr_row_ptr": immutable_array(csr.indptr, dtype="<i8"),
        "csr_columns": immutable_array(csr.indices, dtype="<i8"),
        "csr_values": immutable_array(csr.data, dtype="<f8"),
    }
    pattern_hash = canonical_hash(
        {
            "shape": [size, size],
            "row_ptr": frozen["csr_row_ptr"].tolist(),
            "column_indices": frozen["csr_columns"].tolist(),
        }
    )
    numeric_hash = array_data_hash(frozen["csr_values"])
    hash_payload = {
        "schema_version": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_ASSEMBLY_SCHEMA_VERSION,
        "profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        "storage_profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_STORAGE_PROFILE,
        "model_hash": model.model_hash,
        "parent_checkpoint_hash": parent_checkpoint_hash,
        "target_load_factor": target_load_factor,
        "free_equation_count": size,
        "raw_coo_entry_count": len(coo_values),
        "csr_nnz": int(csr.nnz),
        "csr_pattern_hash": pattern_hash,
        "csr_numeric_hash": numeric_hash,
        "displacement_hash": array_data_hash(frozen["displacement"]),
        "internal_force_hash": array_data_hash(frozen["internal"]),
        "external_force_hash": array_data_hash(frozen["external"]),
        "residual_hash": array_data_hash(frozen["residual"]),
        "reaction_hash": array_data_hash(frozen["reactions"]),
        "trial_material_state_hashes": [state.state_hash for state in states],
    }
    return StatefulCorotationalFrame3DSparseAssembly(
        schema_version=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_ASSEMBLY_SCHEMA_VERSION,
        profile=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        storage_profile=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_STORAGE_PROFILE,
        model_hash=model.model_hash,
        parent_checkpoint_hash=parent_checkpoint_hash,
        target_load_factor=target_load_factor,
        assembly_hash=canonical_hash(hash_payload),
        free_equation_count=size,
        raw_coo_entry_count=len(coo_values),
        csr_nnz=int(csr.nnz),
        csr_pattern_hash=pattern_hash,
        csr_numeric_hash=numeric_hash,
        displacement=frozen["displacement"],
        internal_force=frozen["internal"],
        external_force=frozen["external"],
        residual_free=frozen["residual"],
        reactions=frozen["reactions"],
        coo_row_indices=frozen["coo_rows"],
        coo_column_indices=frozen["coo_columns"],
        coo_values_kn_per_m=frozen["coo_values"],
        csr_row_ptr=frozen["csr_row_ptr"],
        csr_column_indices=frozen["csr_columns"],
        csr_values_kn_per_m=frozen["csr_values"],
        member_responses=tuple(responses),
        trial_material_states=tuple(states),
        _tangent_free_csr=csr,
    )


def _solve_step(
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DSparseConfig,
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
    factor: float,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
) -> StatefulCorotationalFrame3DSparseStep:
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    free = list(model.free_dofs)
    residual_tolerance = _scaled_residual_tolerance(config, scaling)
    increment_tolerance = _scaled_increment_tolerance(config, scaling)
    diagnostics: list[FactorizationDiagnostic] = []
    convergence_history: list[Mapping[str, Any]] = []
    line_search_history: list[Mapping[str, Any]] = []
    selected_line_search_alpha: float | None = None
    line_search_required = False
    parent_checkpoint_hash = parent.checkpoint_hash
    parent_state_hashes = tuple(state.state_hash for state in parent.material_states)
    first_admissibility_error: StatefulCorotationalFrame3DSparseError | None = None
    inadmissible_trial_count = 0
    for iteration in range(config.maximum_iterations + 1):
        assembly = assemble_stateful_corotational_frame3d_sparse(
            model,
            parent,
            target_load_factor=factor,
            trial_displacement=displacement,
        )
        residual = _linf(assembly.residual_free)
        residual_metrics = _scaled_residual_metrics(
            assembly.residual_free,
            model.free_dofs,
            scaling,
        )
        scaled_tangent, scaled_rhs, column_scale = _scaled_newton_system(
            assembly.tangent_free_csr,
            assembly.residual_free,
            model.free_dofs,
            scaling,
        )
        try:
            equivalent_correction, diagnostic = _solve_sparse_tangent(
                scaled_tangent,
                scaled_rhs,
                config.factorization_policy,
            )
        except (SparseFactorizationError, ScalableSparseFactorizationError) as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"sparse factorization failed without fallback: {error.code}",
                reason_code="sparse_factorization_failed",
            ) from error
        diagnostics.append(diagnostic)
        correction = np.asarray(column_scale * equivalent_correction)
        if correction.shape != (len(free),) or not np.all(np.isfinite(correction)):
            raise StatefulCorotationalFrame3DSparseError(
                "scaled sparse Newton correction is invalid"
            )
        increment_metrics = _scaled_increment_metrics(
            correction,
            model.free_dofs,
            scaling,
        )
        residual_gate = residual_metrics["scaled"] <= residual_tolerance
        increment_gate = increment_metrics["scaled"] <= increment_tolerance
        convergence_row: dict[str, Any] = {
            "iteration": iteration,
            "assembly_hash": assembly.assembly_hash,
            "raw_translational_residual_inf_norm_kn": residual_metrics[
                "translation"
            ],
            "raw_rotational_residual_inf_norm_kn_m": residual_metrics["rotation"],
            "scaled_residual_inf_norm": residual_metrics["scaled"],
            "scaled_residual_tolerance": residual_tolerance,
            "raw_translation_increment_inf_norm_m": increment_metrics[
                "translation"
            ],
            "raw_rotation_increment_inf_norm_rad": increment_metrics["rotation"],
            "scaled_increment_inf_norm": increment_metrics["scaled"],
            "scaled_increment_tolerance": increment_tolerance,
            "residual_gate_passed": residual_gate,
            "increment_gate_passed": increment_gate,
            "scaled_condition_number_1": diagnostic.condition_number_1,
            "sparse_diagnostic_hash": diagnostic.diagnostic_hash,
        }
        if residual_gate and increment_gate:
            convergence_row["accepted"] = True
            convergence_row["selected_line_search_alpha"] = None
            convergence_history.append(MappingProxyType(convergence_row))
            final_assembly = assemble_stateful_corotational_frame3d_sparse(
                model,
                parent,
                target_load_factor=factor,
                trial_displacement=displacement,
            )
            final_metrics = _scaled_residual_metrics(
                final_assembly.residual_free,
                model.free_dofs,
                scaling,
            )
            final_reassembled_equilibrium = bool(
                final_assembly.assembly_hash == assembly.assembly_hash
                and final_metrics["scaled"] <= residual_tolerance
                and tuple(
                    state.state_hash
                    for state in final_assembly.trial_material_states
                )
                == tuple(
                    state.state_hash for state in assembly.trial_material_states
                )
            )
            parent_immutable = bool(
                parent.checkpoint_hash == parent_checkpoint_hash
                and tuple(
                    state.state_hash for state in parent.material_states
                )
                == parent_state_hashes
            )
            sparse_diagnostic_passed = bool(
                diagnostics and all(row.contract_pass for row in diagnostics)
            )
            line_search_valid = bool(
                not line_search_required or selected_line_search_alpha is not None
            )
            if not (
                final_reassembled_equilibrium
                and parent_immutable
                and sparse_diagnostic_passed
                and line_search_valid
            ):
                raise StatefulCorotationalFrame3DSparseError(
                    "final Frame3D convergence contract failed before commit",
                    reason_code="final_convergence_contract_failed",
                )
            checkpoint = _make_checkpoint(
                model=model,
                config=config,
                step_index=parent.step_index + 1,
                load_factor=factor,
                displacement=displacement,
                material_states=final_assembly.trial_material_states,
                converged_iterations=iteration,
                residual_inf_norm_kn=residual,
                parent_checkpoint_hash=parent.checkpoint_hash,
            )
            return StatefulCorotationalFrame3DSparseStep(
                step_index=checkpoint.step_index,
                load_factor=factor,
                checkpoint=checkpoint,
                free_residual_inf_norm_kn=residual,
                relative_residual=residual_metrics["scaled"],
                raw_translational_residual_inf_norm_kn=residual_metrics[
                    "translation"
                ],
                raw_rotational_residual_inf_norm_kn_m=residual_metrics["rotation"],
                scaled_residual_inf_norm=residual_metrics["scaled"],
                scaled_residual_tolerance=residual_tolerance,
                raw_translation_increment_inf_norm_m=increment_metrics[
                    "translation"
                ],
                raw_rotation_increment_inf_norm_rad=increment_metrics["rotation"],
                scaled_increment_inf_norm=increment_metrics["scaled"],
                scaled_increment_tolerance=increment_tolerance,
                residual_gate_passed=True,
                increment_gate_passed=True,
                line_search_required=line_search_required,
                selected_line_search_alpha=selected_line_search_alpha,
                line_search_valid=line_search_valid,
                material_admissibility_passed=True,
                final_reassembled_equilibrium_passed=(
                    final_reassembled_equilibrium
                ),
                parent_state_immutable=parent_immutable,
                sparse_diagnostic_passed=sparse_diagnostic_passed,
                scaled_condition_number_1=diagnostic.condition_number_1,
                equation_scaling_hash=scaling.scaling_hash,
                convergence_history=tuple(convergence_history),
                line_search_history=tuple(line_search_history),
                reactions=tuple(
                    (dof, float(final_assembly.reactions[dof]))
                    for dof in model.elastic_model.restrained_dofs
                ),
                factorization_diagnostics=tuple(diagnostics),
                member_results=tuple(
                    MappingProxyType(response.recovery_manifest())
                    for response in final_assembly.member_responses
                ),
            )
        if iteration == config.maximum_iterations:
            convergence_row["accepted"] = False
            convergence_row["selected_line_search_alpha"] = None
            convergence_history.append(MappingProxyType(convergence_row))
            if first_admissibility_error is not None:
                raise first_admissibility_error
            break
        line_search_required = True
        attempts: list[dict[str, Any]] = []
        selected_displacement: np.ndarray | None = None
        selected_line_search_alpha = None
        for alpha in config.line_search_alphas:
            candidate = displacement.copy()
            candidate[free] += alpha * correction
            try:
                trial = assemble_stateful_corotational_frame3d_sparse(
                    model,
                    parent,
                    target_load_factor=factor,
                    trial_displacement=candidate,
                )
            except (
                StatefulCorotationalFrame3DSparseError,
                ValueError,
                FloatingPointError,
            ) as error:
                inadmissible_trial_count += 1
                admissibility_error = (
                    error
                    if isinstance(error, StatefulCorotationalFrame3DSparseError)
                    else StatefulCorotationalFrame3DSparseError(
                        f"Frame3D line-search trial is inadmissible: {error}",
                        reason_code="member_trial_inadmissible",
                    )
                )
                if first_admissibility_error is None:
                    first_admissibility_error = admissibility_error
                attempts.append(
                    {
                        "alpha": alpha,
                        "accepted": False,
                        "admissible": False,
                        "reason": type(error).__name__,
                        "reason_code": getattr(
                            error,
                            "reason_code",
                            "member_trial_inadmissible",
                        ),
                    }
                )
                continue
            trial_metrics = _scaled_residual_metrics(
                trial.residual_free,
                model.free_dofs,
                scaling,
            )
            accepted = bool(
                math.isfinite(trial_metrics["scaled"])
                and trial_metrics["scaled"] < residual_metrics["scaled"]
            )
            attempts.append(
                {
                    "alpha": alpha,
                    "accepted": accepted,
                    "admissible": True,
                    "trial_assembly_hash": trial.assembly_hash,
                    "trial_scaled_residual_inf_norm": trial_metrics["scaled"],
                }
            )
            if accepted:
                selected_line_search_alpha = alpha
                selected_displacement = candidate
                break
        line_search_row = MappingProxyType(
            {
                "iteration": iteration,
                "selected_alpha": selected_line_search_alpha,
                "attempts": tuple(
                    MappingProxyType(dict(attempt)) for attempt in attempts
                ),
            }
        )
        line_search_history.append(line_search_row)
        convergence_row["selected_line_search_alpha"] = (
            selected_line_search_alpha
        )
        convergence_row["accepted"] = selected_displacement is not None
        convergence_row["inadmissible_trial_count"] = inadmissible_trial_count
        convergence_history.append(MappingProxyType(convergence_row))
        if selected_displacement is None:
            if first_admissibility_error is not None:
                raise first_admissibility_error
            raise StatefulCorotationalFrame3DSparseError(
                "line search failed to produce an admissible "
                "scaled-residual-decreasing trial",
                reason_code="line_search_failed",
                retryable_convergence_failure=True,
            )
        displacement = selected_displacement
    raise StatefulCorotationalFrame3DSparseError(
        f"load factor {factor} did not converge in {config.maximum_iterations} iterations",
        reason_code="maximum_iterations_exceeded",
        retryable_convergence_failure=True,
    )


def _make_checkpoint(
    *,
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DSparseConfig,
    step_index: int,
    load_factor: float,
    displacement: np.ndarray,
    material_states: tuple[AxialMaterialState, ...],
    converged_iterations: int,
    residual_inf_norm_kn: float,
    parent_checkpoint_hash: str | None,
) -> StatefulCorotationalFrame3DSparseCheckpoint:
    provisional = StatefulCorotationalFrame3DSparseCheckpoint(
        schema_version=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CHECKPOINT_SCHEMA_VERSION,
        profile=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        model_hash=model.model_hash,
        solver_contract_hash=config.contract_hash,
        step_index=step_index,
        load_factor=float(load_factor),
        displacement=tuple(float(value) for value in displacement),
        material_states=tuple(material_states),
        converged_iterations=converged_iterations,
        residual_inf_norm_kn=float(residual_inf_norm_kn),
        parent_checkpoint_hash=parent_checkpoint_hash,
        checkpoint_hash=_ZERO_HASH,
    )
    checkpoint = replace(
        provisional,
        checkpoint_hash=canonical_hash(
            _checkpoint_payload(provisional, include_hash=False)
        ),
    )
    return validate_stateful_corotational_frame3d_sparse_checkpoint(
        checkpoint,
        model=model,
        config=config,
        require_equilibrium=False,
    )


def _checkpoint_payload(
    checkpoint: StatefulCorotationalFrame3DSparseCheckpoint,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = checkpoint.to_dict()
    if not include_hash:
        payload.pop("checkpoint_hash")
    return payload


def _parity_payload(
    receipt: StatefulCorotationalFrame3DDenseSparseParityReceipt,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "model_hash": receipt.model_hash,
        "parent_checkpoint_hash": receipt.parent_checkpoint_hash,
        "target_load_factor": receipt.target_load_factor,
        "sparse_assembly_hash": receipt.sparse_assembly_hash,
        "metrics": dict(receipt.metrics),
        "checks": dict(receipt.checks),
        "contract_pass": bool(all(receipt.checks.values())),
        "claim_boundary": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CLAIM_BOUNDARY,
    }
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _supported_material(value: object) -> TypeGuard[AxialMaterial]:
    return type(value) in (
        BilinearCombinedHardeningSteel,
        AsymmetricConcreteDamageMaterial,
        FractureEnergyConcreteDamageMaterial,
        ParallelSteelConcreteSectionMaterial,
        ConfinedConcreteMaterial,
        CondensedPartialCompositeAxialMaterial,
        StatefulCorotationalFiberFrame3D,
        StatefulCorotationalPartialCompositeFrame3D,
    )


def _material_state_matches(
    material: AxialMaterial,
    state: object,
) -> bool:
    if type(material) is BilinearCombinedHardeningSteel:
        return type(state) is UniaxialPlasticityState
    if type(material) in (
        AsymmetricConcreteDamageMaterial,
        FractureEnergyConcreteDamageMaterial,
    ):
        return type(state) is ConcreteDamageState
    if type(material) is ParallelSteelConcreteSectionMaterial:
        return type(state) is ParallelCompositeSectionState
    if type(material) is ConfinedConcreteMaterial:
        return type(state) is ConfinedConcreteState
    if type(material) is CondensedPartialCompositeAxialMaterial:
        return type(state) is CondensedPartialCompositeAxialState
    if type(material) is StatefulCorotationalFiberFrame3D:
        return type(state) is StatefulCorotationalFiberFrame3DState
    if type(material) is StatefulCorotationalPartialCompositeFrame3D:
        return type(state) is StatefulCorotationalPartialCompositeFrame3DState
    return False


def _validate_material_state_admissibility(
    material: AxialMaterial,
    state: AxialMaterialState,
) -> None:
    """Apply material-aware invariants before any checkpoint or trial reuse."""

    try:
        if type(material) is BilinearCombinedHardeningSteel:
            assert type(state) is UniaxialPlasticityState
            material.validate_state_admissibility(state)
        elif type(material) in (
            AsymmetricConcreteDamageMaterial,
            FractureEnergyConcreteDamageMaterial,
        ):
            assert type(state) is ConcreteDamageState
            material.validate_state_admissibility(state)
        elif type(material) is ParallelSteelConcreteSectionMaterial:
            assert type(state) is ParallelCompositeSectionState
            material.steel.validate_state_admissibility(state.steel_state)
            material.concrete.validate_state_admissibility(state.concrete_state)
        elif type(material) is ConfinedConcreteMaterial:
            assert type(state) is ConfinedConcreteState
            material.validate_state_admissibility(state)
        elif type(material) is CondensedPartialCompositeAxialMaterial:
            assert type(state) is CondensedPartialCompositeAxialState
            material.partial_composite.connector.validate_state_admissibility(
                state.component_state.connector_state
            )
        elif type(material) is StatefulCorotationalFiberFrame3D:
            assert type(state) is StatefulCorotationalFiberFrame3DState
            material.validate_state(state)
            for section_state in state.integration_point_states:
                _validate_biaxial_section_material_states(
                    material.section,
                    section_state,
                )
        elif type(material) is StatefulCorotationalPartialCompositeFrame3D:
            assert type(state) is StatefulCorotationalPartialCompositeFrame3DState
            material.validate_state(state)
            for section_state in state.steel_section_states:
                _validate_biaxial_section_material_states(
                    material.steel_section,
                    section_state,
                )
            for section_state in state.concrete_section_states:
                _validate_biaxial_section_material_states(
                    material.concrete_section,
                    section_state,
                )
            for connector_state in state.connector_states:
                assert type(connector_state) is BondSlipState
                material.connector.validate_state_admissibility(connector_state)
    except ValueError as error:
        raise StatefulCorotationalFrame3DSparseError(
            f"material state is inadmissible: {error}",
            reason_code="material_state_admissibility_failed",
        ) from error


def _validate_biaxial_section_material_states(
    section: Any,
    state: Any,
) -> None:
    section.validate_state(state)
    for fiber, fiber_state in zip(
        section.fibers,
        state.fiber_states,
        strict=True,
    ):
        if type(fiber.material) is BilinearCombinedHardeningSteel:
            assert type(fiber_state) is UniaxialPlasticityState
            fiber.material.validate_state_admissibility(fiber_state)
        elif type(fiber.material) in (
            AsymmetricConcreteDamageMaterial,
            FractureEnergyConcreteDamageMaterial,
        ):
            assert type(fiber_state) is ConcreteDamageState
            fiber.material.validate_state_admissibility(fiber_state)
        elif type(fiber.material) is ConfinedConcreteMaterial:
            assert type(fiber_state) is ConfinedConcreteState
            fiber.material.validate_state_admissibility(fiber_state)


def _material_response_matches(
    material: AxialMaterial,
    response: object,
) -> bool:
    if type(material) is BilinearCombinedHardeningSteel:
        return type(response) is UniaxialPlasticityResponse
    if type(material) in (
        AsymmetricConcreteDamageMaterial,
        FractureEnergyConcreteDamageMaterial,
    ):
        return type(response) is ConcreteDamageResponse
    if type(material) is ParallelSteelConcreteSectionMaterial:
        return type(response) is ParallelCompositeSectionResponse
    if type(material) is ConfinedConcreteMaterial:
        return type(response) is StatefulConfinedConcreteResponse
    if type(material) is CondensedPartialCompositeAxialMaterial:
        return type(response) is CondensedPartialCompositeAxialResponse
    if type(material) is StatefulCorotationalFiberFrame3D:
        return type(response) is StatefulCorotationalFiberFrame3DResponse
    if type(material) is StatefulCorotationalPartialCompositeFrame3D:
        return type(response) is StatefulCorotationalPartialCompositeFrame3DResponse
    return False


def _validate_material_response_lineage(
    material: AxialMaterial,
    committed_state: AxialMaterialState,
    response: AxialMaterialResponse,
) -> None:
    if not _material_response_matches(material, response):
        raise StatefulCorotationalFrame3DSparseError(
            "material response type does not match its exact material family",
            reason_code="material_response_type_mismatch",
        )
    if type(response) in (
        StatefulCorotationalFiberFrame3DResponse,
        StatefulCorotationalPartialCompositeFrame3DResponse,
    ):
        response_parent_hash = response.parent_state_hash
    else:
        response_parent_hash = response.committed_state_hash
    if response_parent_hash != committed_state.state_hash:
        raise StatefulCorotationalFrame3DSparseError(
            "material response was not evaluated from the accepted parent state",
            reason_code="material_response_parent_state_mismatch",
        )
    if not _material_state_matches(material, response.state):
        raise StatefulCorotationalFrame3DSparseError(
            "material response trial state does not match its exact material family",
            reason_code="material_response_trial_state_mismatch",
        )
    _validate_material_state_admissibility(material, response.state)


def _initial_material_state(material: AxialMaterial) -> AxialMaterialState:
    if isinstance(material, BilinearCombinedHardeningSteel):
        return material.initial_state()
    if isinstance(material, AsymmetricConcreteDamageMaterial):
        return material.initial_state()
    if isinstance(material, ParallelSteelConcreteSectionMaterial):
        return material.initial_state()
    if isinstance(material, ConfinedConcreteMaterial):
        return material.initial_state()
    if isinstance(material, CondensedPartialCompositeAxialMaterial):
        return material.initial_state()
    if isinstance(material, StatefulCorotationalFiberFrame3D):
        return material.initial_state()
    if isinstance(material, StatefulCorotationalPartialCompositeFrame3D):
        return material.initial_state()
    raise TypeError("unsupported axial material")


def _integrate_axial_material(
    material: AxialMaterial,
    strain: float,
    state: AxialMaterialState,
) -> AxialPointMaterialResponse:
    if isinstance(material, BilinearCombinedHardeningSteel) and isinstance(
        state,
        UniaxialPlasticityState,
    ):
        return material.integrate(strain, state)
    if isinstance(material, AsymmetricConcreteDamageMaterial) and isinstance(
        state,
        ConcreteDamageState,
    ):
        return material.integrate(strain, state)
    if isinstance(material, ParallelSteelConcreteSectionMaterial) and isinstance(
        state,
        ParallelCompositeSectionState,
    ):
        return material.integrate(strain, state)
    if isinstance(material, ConfinedConcreteMaterial) and isinstance(
        state,
        ConfinedConcreteState,
    ):
        return material.integrate(strain, state)
    if isinstance(material, CondensedPartialCompositeAxialMaterial) and isinstance(
        state,
        CondensedPartialCompositeAxialState,
    ):
        return material.integrate(strain, state)
    raise ValueError("material and committed state types do not match")


def _material_elastic_modulus_mpa(material: AxialMaterial) -> float:
    if isinstance(material, BilinearCombinedHardeningSteel):
        return material.elastic_modulus_mpa
    if isinstance(material, AsymmetricConcreteDamageMaterial):
        return material.elastic_modulus_mpa
    if isinstance(material, ParallelSteelConcreteSectionMaterial):
        return (
            material.steel_area_fraction * material.steel.elastic_modulus_mpa
            + material.concrete_area_fraction * material.concrete.elastic_modulus_mpa
        )
    if isinstance(material, ConfinedConcreteMaterial):
        return material.elastic_modulus_mpa
    if isinstance(material, CondensedPartialCompositeAxialMaterial):
        return material.initial_effective_modulus_mpa
    raise TypeError("unsupported axial material")


def _material_manifest(material: AxialMaterial) -> dict[str, Any]:
    if isinstance(material, BilinearCombinedHardeningSteel):
        return {
            "material_type": "bilinear_combined_hardening_steel",
            "material_id": material.material_id,
            "elastic_modulus_mpa": material.elastic_modulus_mpa,
            "yield_stress_mpa": material.yield_stress_mpa,
            "isotropic_hardening_modulus_mpa": (
                material.isotropic_hardening_modulus_mpa
            ),
            "kinematic_hardening_modulus_mpa": (
                material.kinematic_hardening_modulus_mpa
            ),
            "yield_tolerance_mpa": material.yield_tolerance_mpa,
        }
    if isinstance(material, FractureEnergyConcreteDamageMaterial):
        return {
            "material_type": "fracture_energy_concrete_damage",
            "material_id": material.material_id,
            "elastic_modulus_mpa": material.elastic_modulus_mpa,
            "tensile_strength_mpa": material.tensile_strength_mpa,
            "compressive_strength_mpa": material.compressive_strength_mpa,
            "characteristic_length_m": material.characteristic_length_m,
            "tensile_fracture_energy_n_per_m": (
                material.tensile_fracture_energy_n_per_m
            ),
            "compressive_fracture_energy_n_per_m": (
                material.compressive_fracture_energy_n_per_m
            ),
            "history_tolerance": material.history_tolerance,
            "damage_algorithm": material.damage_algorithm,
            "tangent_definition": material.tangent_definition,
        }
    if isinstance(material, AsymmetricConcreteDamageMaterial):
        return {
            "material_type": "asymmetric_concrete_damage",
            "material_id": material.material_id,
            "elastic_modulus_mpa": material.elastic_modulus_mpa,
            "tensile_strength_mpa": material.tensile_strength_mpa,
            "compressive_strength_mpa": material.compressive_strength_mpa,
            "tensile_softening_rate": material.tensile_softening_rate,
            "compressive_softening_rate": material.compressive_softening_rate,
            "history_tolerance": material.history_tolerance,
            "damage_algorithm": material.damage_algorithm,
            "tangent_definition": material.tangent_definition,
        }
    if isinstance(material, ParallelSteelConcreteSectionMaterial):
        return {
            "material_type": "parallel_steel_concrete_section",
            "material_id": material.material_id,
            "steel_area_fraction": material.steel_area_fraction,
            "concrete_area_fraction": material.concrete_area_fraction,
            "effective_elastic_modulus_mpa": _material_elastic_modulus_mpa(material),
            "steel": _material_manifest(material.steel),
            "concrete": _material_manifest(material.concrete),
        }
    if isinstance(material, ConfinedConcreteMaterial):
        return {
            "material_type": "confined_concrete_envelope",
            "material_id": material.material_id,
            "elastic_modulus_mpa": material.elastic_modulus_mpa,
            "unconfined_compressive_strength_mpa": (
                material.unconfined_compressive_strength_mpa
            ),
            "effective_lateral_pressure_mpa": (material.effective_lateral_pressure_mpa),
            "confined_compressive_strength_mpa": (
                material.confined_compressive_strength_mpa
            ),
            "confined_peak_strain": material.confined_peak_strain,
            "ultimate_compressive_strain": material.ultimate_compressive_strain,
            "residual_strength_ratio": material.residual_strength_ratio,
            "path_capabilities": dict(CONFINED_CONCRETE_PATH_CAPABILITIES),
        }
    if isinstance(material, CondensedPartialCompositeAxialMaterial):
        component = material.partial_composite
        connector = component.connector
        return {
            "material_type": "condensed_partial_composite_axial",
            "material_id": material.material_id,
            "member_length_m": material.member_length_m,
            "reference_area_m2": material.reference_area_m2,
            "initial_effective_modulus_mpa": (material.initial_effective_modulus_mpa),
            "steel_axial_rigidity_n": component.steel_axial_rigidity_n,
            "concrete_axial_rigidity_n": component.concrete_axial_rigidity_n,
            "connector": {
                "material_id": connector.material_id,
                "initial_stiffness_n_per_m": connector.initial_stiffness_n_per_m,
                "yield_slip_m": connector.yield_slip_m,
                "ultimate_slip_m": connector.ultimate_slip_m,
                "residual_strength_ratio": connector.residual_strength_ratio,
                "reversal_stiffness_degradation": (
                    connector.reversal_stiffness_degradation
                ),
                "reversal_strength_degradation": (
                    connector.reversal_strength_degradation
                ),
                "minimum_stiffness_ratio": connector.minimum_stiffness_ratio,
            },
            "local_equilibrium_absolute_tolerance_n": (
                material.local_equilibrium_absolute_tolerance_n
            ),
            "local_increment_tolerance_m": material.local_increment_tolerance_m,
            "maximum_local_iterations": material.maximum_local_iterations,
            "line_search_alphas": list(material.line_search_alphas),
        }
    if isinstance(material, StatefulCorotationalFiberFrame3D):
        return {
            "material_type": "distributed_axial_biaxial_fiber_frame3d",
            **material.to_manifest(),
        }
    if isinstance(material, StatefulCorotationalPartialCompositeFrame3D):
        return {
            "material_type": "distributed_partial_composite_fiber_frame3d",
            **material.to_manifest(),
        }
    raise TypeError("unsupported axial material")


def _validate_member_material_binding(
    model: ElasticFrame3DModel,
    member: CorotationalFrame3DMember,
    material: AxialMaterial,
) -> None:
    if type(material) in (
        StatefulCorotationalFiberFrame3D,
        StatefulCorotationalPartialCompositeFrame3D,
    ):
        distributed = cast(
            StatefulCorotationalFiberFrame3D
            | StatefulCorotationalPartialCompositeFrame3D,
            material,
        )
        binding_label = (
            "distributed-fiber"
            if type(material) is StatefulCorotationalFiberFrame3D
            else "distributed-partial-composite"
        )
        coordinates = np.asarray(model.node_coordinates_m, dtype=np.float64)
        member_coordinates = coordinates[[member.node_i, member.node_j]]
        material_coordinates = np.asarray(
            distributed.node_coordinates_m,
            dtype=np.float64,
        )
        if not np.array_equal(member_coordinates, material_coordinates):
            raise ValueError(
                f"member {member.member_id} {binding_label} coordinate binding mismatch"
            )
        if member.local_axis_roll_deg != distributed.local_axis_roll_deg:
            raise ValueError(
                f"member {member.member_id} {binding_label} roll binding mismatch"
            )
        distributed.validate_reference_section(member.section)
        return
    if type(material) is not CondensedPartialCompositeAxialMaterial:
        return
    condensed = cast(CondensedPartialCompositeAxialMaterial, material)
    coordinates = np.asarray(model.node_coordinates_m, dtype=np.float64)
    member_length = float(
        np.linalg.norm(coordinates[member.node_j] - coordinates[member.node_i])
    )
    length_error = abs(member_length - condensed.member_length_m) / max(
        member_length,
        condensed.member_length_m,
        1.0,
    )
    area = member.section.frame.area_m2
    area_error = abs(area - condensed.reference_area_m2) / max(
        area,
        condensed.reference_area_m2,
        1.0,
    )
    if length_error > 1.0e-12:
        raise ValueError(
            f"member {member.member_id} partial-interaction length binding mismatch"
        )
    if area_error > 1.0e-12:
        raise ValueError(
            f"member {member.member_id} partial-interaction area binding mismatch"
        )


def _factorization_backend_label(policy: FactorizationPolicy) -> str:
    if type(policy) is SparseFactorizationPolicy:
        return "scipy_superlu_splu_cpu_exact_condition_fail_closed"
    if type(policy) is ScalableSparseFactorizationPolicy:
        return "scipy_superlu_splu_cpu_blocked_exact_condition_fail_closed"
    raise TypeError("unsupported sparse factorization policy")


def _solve_sparse_tangent(
    tangent: csr_matrix,
    rhs: np.ndarray,
    policy: FactorizationPolicy,
) -> tuple[np.ndarray, FactorizationDiagnostic]:
    if type(policy) is SparseFactorizationPolicy:
        standard = factorize_and_solve_sparse(tangent, rhs, policy=policy)
        return np.asarray(standard.solution, dtype=np.float64), standard.diagnostic
    if type(policy) is ScalableSparseFactorizationPolicy:
        scalable = factorize_and_solve_scalable_sparse(tangent, rhs, policy=policy)
        return np.asarray(scalable.solution, dtype=np.float64), scalable.diagnostic
    raise TypeError("unsupported sparse factorization policy")


def _member_dofs(member: CorotationalFrame3DMember) -> tuple[int, ...]:
    start = 6 * member.node_i
    end = 6 * member.node_j
    return tuple(range(start, start + 6)) + tuple(range(end, end + 6))


def _displacement(
    model: StatefulCorotationalFrame3DSparseModel,
    values: Any,
) -> np.ndarray:
    try:
        _validate_real_binary64_source(values)
        vector = immutable_array(values, dtype="<f8")
    except (CanonicalContractError, TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            "displacement must contain finite, losslessly representable "
            "real binary64 values"
        ) from error
    if vector.shape != (model.total_dofs,):
        raise ValueError(f"displacement must be a finite {model.total_dofs}-vector")
    restrained = list(model.elastic_model.restrained_dofs)
    if np.any(vector[restrained] != 0.0):
        raise ValueError("restrained displacement entries must be exactly zero")
    return np.array(vector, dtype=np.float64, copy=True)


def _validate_real_binary64_source(value: Any) -> None:
    """Reject scalar kinds that NumPy would silently coerce before hashing."""

    if np.ma.isMaskedArray(value):
        raise CanonicalContractError("Masked numeric sources are not contract-safe.")
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject or value.dtype.kind not in "iuf":
            raise CanonicalContractError(
                "Only integer and real floating-point sources are contract-safe."
            )
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_real_binary64_source(item)
        return
    if isinstance(value, bool) or not isinstance(value, Real):
        raise CanonicalContractError(
            "Only integer and real floating-point sources are contract-safe."
        )
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise CanonicalContractError(
            "Numeric source cannot be represented as binary64."
        ) from error
    if not math.isfinite(converted) or value != converted:
        raise CanonicalContractError(
            "Numeric source cannot be represented exactly as binary64."
        )
    if isinstance(value, Integral) and int(converted) != int(value):
        raise CanonicalContractError(
            "Integer source cannot be represented exactly as binary64."
        )


def _load_factors(values: Iterable[float], *, after: float) -> tuple[float, ...]:
    factors = tuple(
        _finite(value, f"load_factors[{index}]") for index, value in enumerate(values)
    )
    if not factors:
        raise ValueError("load_factors must not be empty")
    previous = after
    for factor in factors:
        if factor == previous:
            raise ValueError("adjacent load factors must be distinct")
        previous = factor
    return factors


def _equation_scaling_payload(
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": scaling.schema_version,
        "policy": scaling.policy,
        "model_hash": scaling.model_hash,
        "characteristic_length_m": scaling.characteristic_length_m,
        "reference_force_kn": scaling.reference_force_kn,
        "residual_translation_scale_kn": scaling.residual_translation_scale_kn,
        "residual_rotation_scale_kn_m": scaling.residual_rotation_scale_kn_m,
        "increment_translation_scale_m": scaling.increment_translation_scale_m,
        "increment_rotation_scale_rad": scaling.increment_rotation_scale_rad,
        "source_node_coordinates_hash": scaling.source_node_coordinates_hash,
        "source_reference_load_hash": scaling.source_reference_load_hash,
        "source_free_dofs_hash": scaling.source_free_dofs_hash,
        "row_equilibration_hash": scaling.row_equilibration_hash,
        "column_equilibration_hash": scaling.column_equilibration_hash,
    }
    if include_hash:
        payload["scaling_hash"] = scaling.scaling_hash
    return payload


def _thaw_trace_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_trace_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_trace_value(item) for item in value]
    return value


def _free_equation_equilibration(
    free_dofs: tuple[int, ...],
    characteristic_length_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    return equilibration_vectors_6dof(free_dofs, characteristic_length_m)


def _scaled_residual_metrics(
    residual_free: Any,
    free_dofs: tuple[int, ...],
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
) -> dict[str, float]:
    return scaled_residual_metrics_6dof(residual_free, free_dofs, scaling)


def _scaled_increment_metrics(
    correction_free: Any,
    free_dofs: tuple[int, ...],
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
) -> dict[str, float]:
    return scaled_increment_metrics_6dof(correction_free, free_dofs, scaling)


def _scaled_newton_system(
    tangent_free: csr_matrix,
    residual_free: Any,
    free_dofs: tuple[int, ...],
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
    residual = np.asarray(residual_free, dtype=np.float64)
    row_scale, column_scale = _free_equation_equilibration(
        free_dofs,
        scaling.characteristic_length_m,
    )
    scaled_tangent = (
        diags(row_scale, offsets=0, format="csr")
        @ tangent_free
        @ diags(column_scale, offsets=0, format="csr")
    ).tocsr()
    scaled_tangent.sum_duplicates()
    scaled_tangent.eliminate_zeros()
    scaled_tangent.sort_indices()
    scaled_rhs = -row_scale * residual
    if (
        scaled_tangent.shape != tangent_free.shape
        or not scaled_tangent.has_canonical_format
        or not np.all(np.isfinite(scaled_tangent.data))
        or not np.all(np.isfinite(scaled_rhs))
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "scaled 6DOF Newton system is invalid"
        )
    return scaled_tangent, scaled_rhs, column_scale


def _scaled_residual_tolerance(
    config: StatefulCorotationalFrame3DSparseConfig,
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
) -> float:
    return config.residual_relative_tolerance + (
        config.residual_absolute_tolerance_kn / scaling.reference_force_kn
    )


def _scaled_increment_tolerance(
    config: StatefulCorotationalFrame3DSparseConfig,
    scaling: StatefulCorotationalFrame3DEquationScaling6DOF,
) -> float:
    return config.increment_relative_tolerance + (
        config.increment_absolute_tolerance_m / scaling.characteristic_length_m
    )


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


def _linf(values: Any) -> float:
    vector = np.asarray(values, dtype=np.float64)
    return float(np.linalg.norm(vector, ord=np.inf)) if vector.size else 0.0


def _max_abs(values: Any) -> float:
    vector = np.asarray(values, dtype=np.float64)
    return float(np.max(np.abs(vector))) if vector.size else 0.0


def _optional_hash(value: str | None) -> bool:
    return value is None or (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )
