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
from types import MappingProxyType
from typing import Any, Iterable, Mapping, TypeAlias, TypeGuard, cast

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

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
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
)
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
    ConcreteDamageResponse,
    ConcreteDamageState,
    FractureEnergyConcreteDamageMaterial,
)
from structural_analysis.materials.confined_concrete import (
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
    "stateful-corotational-frame3d-sparse-result.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_STORAGE_PROFILE = (
    "member_12x12_triplet_coalesce_sorted_csr_fp64.v1"
)
STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CLAIM_BOUNDARY = (
    "Experimental bounded-graph 3D corotational Timoshenko path with native "
    "COO/CSR assembly, fail-closed exact-condition SuperLU diagnostics, and "
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
    maximum_iterations: int = 30
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
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        if type(self.maximum_iterations) is not int or self.maximum_iterations < 1:
            raise ValueError("maximum_iterations must be a positive integer")
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
            "maximum_iterations": self.maximum_iterations,
            "assembly": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_STORAGE_PROFILE,
            "linear_solver": _factorization_backend_label(self.factorization_policy),
            "factorization_policy": self.factorization_policy.to_manifest(),
            "load_control": "ordered_finite_targets_with_reversal_allowed",
            "line_search": False,
            "regularization_allowed": False,
            "fallback_allowed": False,
        }


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
            "reactions": [list(row) for row in self.reactions],
            "factorization_diagnostics": [
                row.to_manifest() for row in self.factorization_diagnostics
            ],
            "member_results": [dict(row) for row in self.member_results],
        }


@dataclass(frozen=True)
class StatefulCorotationalFrame3DSparseResult:
    schema_version: str
    profile: str
    model_hash: str
    solver_contract_hash: str
    start_checkpoint_hash: str
    steps: tuple[StatefulCorotationalFrame3DSparseStep, ...]
    checkpoints: tuple[StatefulCorotationalFrame3DSparseCheckpoint, ...]
    maximum_free_residual_inf_norm_kn: float
    result_hash: str
    exact_checkpoint_resume_supported: bool
    material_commit_rollback_supported: bool
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
            "steps": [step.to_dict() for step in self.steps],
            "checkpoints": [row.to_dict() for row in self.checkpoints],
            "maximum_free_residual_inf_norm_kn": (
                self.maximum_free_residual_inf_norm_kn
            ),
            "result_hash": self.result_hash,
            "exact_checkpoint_resume_supported": (
                self.exact_checkpoint_resume_supported
            ),
            "material_commit_rollback_supported": (
                self.material_commit_rollback_supported
            ),
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
    tangent = 0.5 * (tangent + tangent.T)
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


def initial_stateful_corotational_frame3d_sparse_checkpoint(
    model: StatefulCorotationalFrame3DSparseModel,
    *,
    config: StatefulCorotationalFrame3DSparseConfig,
) -> StatefulCorotationalFrame3DSparseCheckpoint:
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
    if residual > _residual_tolerance(model, config, 0.0):
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
        response = stateful_corotational_frame3d_member_response(
            member=member,
            node_coordinates_m=coordinates[[member.node_i, member.node_j]],
            element_displacements=values[list(dofs)],
            axial_material=material,
            committed_state=parent,
        )
        internal[list(dofs)] += response.internal_force_global
        tangent[np.ix_(dofs, dofs)] += response.consistent_tangent_global
        states.append(response.trial_state)
    tangent = 0.5 * (tangent + tangent.T)
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
    for factor in factors:
        step = _solve_step(model, config, factor, checkpoints[-1])
        steps.append(step)
        checkpoints.append(step.checkpoint)
    maximum_residual = max(
        (row.free_residual_inf_norm_kn for row in steps),
        default=checkpoint.residual_inf_norm_kn,
    )
    payload = {
        "schema_version": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION,
        "profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        "model_hash": model.model_hash,
        "solver_contract_hash": config.contract_hash,
        "start_checkpoint_hash": checkpoint.checkpoint_hash,
        "steps": [step.to_dict() for step in steps],
        "maximum_free_residual_inf_norm_kn": maximum_residual,
        "exact_checkpoint_resume_supported": True,
        "material_commit_rollback_supported": True,
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": True,
        "claim_boundary": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_CLAIM_BOUNDARY,
    }
    return StatefulCorotationalFrame3DSparseResult(
        schema_version=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_RESULT_SCHEMA_VERSION,
        profile=STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        model_hash=model.model_hash,
        solver_contract_hash=config.contract_hash,
        start_checkpoint_hash=checkpoint.checkpoint_hash,
        steps=tuple(steps),
        checkpoints=tuple(checkpoints),
        maximum_free_residual_inf_norm_kn=maximum_residual,
        result_hash=canonical_hash(payload),
        exact_checkpoint_resume_supported=True,
        material_commit_rollback_supported=True,
        regularization_used=False,
        fallback_used=False,
        contract_pass=True,
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
    values = _displacement(model, checkpoint.displacement)
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
    if (
        not math.isfinite(checkpoint.load_factor)
        or type(checkpoint.converged_iterations) is not int
        or checkpoint.converged_iterations < 0
        or not math.isfinite(checkpoint.residual_inf_norm_kn)
        or checkpoint.residual_inf_norm_kn < 0.0
        or not _optional_hash(checkpoint.parent_checkpoint_hash)
    ):
        raise StatefulCorotationalFrame3DSparseError(
            "checkpoint scalar metadata is invalid"
        )
    expected_hash = canonical_hash(_checkpoint_payload(checkpoint, include_hash=False))
    if checkpoint.checkpoint_hash != expected_hash:
        raise StatefulCorotationalFrame3DSparseError("checkpoint hash mismatch")
    if require_equilibrium:
        if config is None:
            raise ValueError("config is required for equilibrium validation")
        assembly = _assemble_sparse_core(
            model,
            checkpoint.material_states,
            parent_checkpoint_hash=checkpoint.checkpoint_hash,
            target_load_factor=checkpoint.load_factor,
            displacement=values,
        )
        residual = _linf(assembly.residual_free)
        tolerance = _residual_tolerance(model, config, checkpoint.load_factor)
        if residual > tolerance:
            raise StatefulCorotationalFrame3DSparseError(
                "checkpoint free-equation equilibrium is invalid"
            )
        if abs(residual - checkpoint.residual_inf_norm_kn) > max(
            tolerance,
            1.0e-12,
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "checkpoint residual observation is inconsistent"
            )
        if tuple(state.state_hash for state in assembly.trial_material_states) != tuple(
            state.state_hash for state in checkpoint.material_states
        ):
            raise StatefulCorotationalFrame3DSparseError(
                "checkpoint material state is not self-consistent"
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
        response = stateful_corotational_frame3d_member_response(
            member=member,
            node_coordinates_m=coordinates[[member.node_i, member.node_j]],
            element_displacements=displacement[list(dofs)],
            axial_material=material,
            committed_state=parent,
        )
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
    factor: float,
    parent: StatefulCorotationalFrame3DSparseCheckpoint,
) -> StatefulCorotationalFrame3DSparseStep:
    displacement = np.asarray(parent.displacement, dtype=np.float64).copy()
    free = list(model.free_dofs)
    tolerance = _residual_tolerance(model, config, factor)
    diagnostics: list[FactorizationDiagnostic] = []
    for iteration in range(config.maximum_iterations + 1):
        assembly = assemble_stateful_corotational_frame3d_sparse(
            model,
            parent,
            target_load_factor=factor,
            trial_displacement=displacement,
        )
        residual = _linf(assembly.residual_free)
        if residual <= tolerance:
            checkpoint = _make_checkpoint(
                model=model,
                config=config,
                step_index=parent.step_index + 1,
                load_factor=factor,
                displacement=displacement,
                material_states=assembly.trial_material_states,
                converged_iterations=iteration,
                residual_inf_norm_kn=residual,
                parent_checkpoint_hash=parent.checkpoint_hash,
            )
            applied_free = assembly.external_force[free]
            relative = residual / max(_linf(applied_free), 1.0)
            return StatefulCorotationalFrame3DSparseStep(
                step_index=checkpoint.step_index,
                load_factor=factor,
                checkpoint=checkpoint,
                free_residual_inf_norm_kn=residual,
                relative_residual=relative,
                reactions=tuple(
                    (dof, float(assembly.reactions[dof]))
                    for dof in model.elastic_model.restrained_dofs
                ),
                factorization_diagnostics=tuple(diagnostics),
                member_results=tuple(
                    MappingProxyType(response.recovery_manifest())
                    for response in assembly.member_responses
                ),
            )
        if iteration == config.maximum_iterations:
            break
        try:
            correction, diagnostic = _solve_sparse_tangent(
                assembly.tangent_free_csr,
                -assembly.residual_free,
                config.factorization_policy,
            )
        except (SparseFactorizationError, ScalableSparseFactorizationError) as error:
            raise StatefulCorotationalFrame3DSparseError(
                f"sparse factorization failed without fallback: {error.code}"
            ) from error
        diagnostics.append(diagnostic)
        if correction.shape != (len(free),) or not np.all(np.isfinite(correction)):
            raise StatefulCorotationalFrame3DSparseError(
                "sparse Newton correction is invalid"
            )
        displacement[free] += correction
    raise StatefulCorotationalFrame3DSparseError(
        f"load factor {factor} did not converge in {config.maximum_iterations} iterations"
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
            "effective_lateral_pressure_mpa": (
                material.effective_lateral_pressure_mpa
            ),
            "confined_compressive_strength_mpa": (
                material.confined_compressive_strength_mpa
            ),
            "confined_peak_strain": material.confined_peak_strain,
            "ultimate_compressive_strain": material.ultimate_compressive_strain,
            "residual_strength_ratio": material.residual_strength_ratio,
        }
    if isinstance(material, CondensedPartialCompositeAxialMaterial):
        component = material.partial_composite
        connector = component.connector
        return {
            "material_type": "condensed_partial_composite_axial",
            "material_id": material.material_id,
            "member_length_m": material.member_length_m,
            "reference_area_m2": material.reference_area_m2,
            "initial_effective_modulus_mpa": (
                material.initial_effective_modulus_mpa
            ),
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
        binding_label = (
            "distributed-fiber"
            if type(material) is StatefulCorotationalFiberFrame3D
            else "distributed-partial-composite"
        )
        coordinates = np.asarray(model.node_coordinates_m, dtype=np.float64)
        member_coordinates = coordinates[[member.node_i, member.node_j]]
        material_coordinates = np.asarray(
            material.node_coordinates_m,
            dtype=np.float64,
        )
        if not np.array_equal(member_coordinates, material_coordinates):
            raise ValueError(
                f"member {member.member_id} {binding_label} coordinate "
                "binding mismatch"
            )
        if member.local_axis_roll_deg != material.local_axis_roll_deg:
            raise ValueError(
                f"member {member.member_id} {binding_label} roll binding mismatch"
            )
        material.validate_reference_section(member.section)
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
    vector = np.asarray(values, dtype=np.float64)
    if vector.shape != (model.total_dofs,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"displacement must be a finite {model.total_dofs}-vector")
    restrained = list(model.elastic_model.restrained_dofs)
    if np.any(vector[restrained] != 0.0):
        raise ValueError("restrained displacement entries must be exactly zero")
    return np.array(vector, dtype=np.float64, copy=True)


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


def _residual_tolerance(
    model: StatefulCorotationalFrame3DSparseModel,
    config: StatefulCorotationalFrame3DSparseConfig,
    factor: float,
) -> float:
    reference = np.asarray(model.elastic_model.reference_load_kn, dtype=np.float64)
    scale = max(_linf(factor * reference[list(model.free_dofs)]), 1.0)
    return config.residual_absolute_tolerance_kn + (
        config.residual_relative_tolerance * scale
    )


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
