"""Unified bounded nonlinear frame API for fixed-chord and corotational profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
import hashlib
from importlib import resources
import json
import math
import re
from types import MappingProxyType
from typing import Any, Final, Literal, NoReturn, cast

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.assembly.corotational_frame2d_member_features import (
    CorotationalFrame2DMemberFeatures,
    element_end_coordinates_m,
)
from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DMember,
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_chain_io import (
    StatefulCorotationalFiberFrame2DCheckpointChain,
    StatefulCorotationalFiberFrame2DCheckpointChainArtifactError,
    dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_corotational_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_engineering_recovery import (
    CorotationalEngineeringSourceAdapter,
    CorotationalFiberFrameEngineeringResultIR,
    create_corotational_fiber_frame_engineering_result_ir,
    validate_corotational_fiber_frame_engineering_result_manifest,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_general import (
    COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE,
    CorotationalFiberFrameGeneralCompilation,
    CorotationalFiberFrameGeneralError,
    compile_corotational_fiber_frame_general_profile,
    create_corotational_fiber_frame_general_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_j1_j5 import (
    CorotationalFiberFrameJ1J5Error,
    CorotationalFiberFramePortalCompilation,
    compile_corotational_fiber_frame_portal_profile,
    create_corotational_fiber_frame_j1_j5_adapter,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadPathResult,
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    FiberFrameNonlinearExecutionTopologyPlan,
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    FiberFramePhysicalEquationScalingBinding,
    FiberFramePhysicalResidualTrace,
    create_stateful_fiber_frame2d_physical_equation_scaling,
    trace_stateful_fiber_frame2d_free_physical_residual,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d import (
    StatefulCorotationalFiberBeam2D,
)
from structural_analysis.elements.axial_curvature_section import AxialCurvatureSection
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulRCFiberSection,
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)
from structural_analysis.adapters.bounded_planar_model_ir import (
    BoundedPlanarModelIRAdapter,
    adapt_bounded_planar_model_ir_v2,
    validate_bounded_planar_model_ir_adapter_manifest,
)
from structural_analysis.adapters.bounded_planar_execution_plan import (
    BoundedPlanarExecutionPlanBinding,
    create_bounded_planar_execution_plan_binding,
    validate_bounded_planar_execution_plan_manifest,
)
from structural_analysis.model_ir.types import ModelIRDocument
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    VECTOR_MATRIX_BACKENDS,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


UNIFIED_NONLINEAR_FRAME_SCHEMA_VERSION = "unified-nonlinear-frame-result.v1"
UNIFIED_NONLINEAR_FRAME_REPORT_SCHEMA_VERSION = (
    "unified-nonlinear-frame-validation-report.v1"
)
UNIFIED_NONLINEAR_FRAME_UNSUPPORTED_REASON_CODES: Final[tuple[str, ...]] = (
    "equation_scaling_unavailable",
    "input_contract_unsupported",
    "mechanism_detected",
    "profile_feature_unsupported",
    "restart_artifact_invalid",
    "singular_system_detected",
    "solver_execution_failed",
    "source_model_unsupported",
)
FIXED_CHORD_SERIAL_PROFILE: Final[Literal["fixed_chord_serial_cantilever.v1"]] = (
    "fixed_chord_serial_cantilever.v1"
)
COROTATIONAL_PORTAL_PROFILE: Final[Literal["corotational_one_bay_portal.v1"]] = (
    "corotational_one_bay_portal.v1"
)
COROTATIONAL_GENERAL_PROFILE: Final[Literal["corotational_connected_frame2d.v1"]] = (
    "corotational_connected_frame2d.v1"
)
UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY = (
    "The unified API selects one explicit bounded profile. The fixed-chord serial "
    "cantilever retains its existing Developer Preview authority. The corotational "
    "portal and connected-frame profiles bind J1-J5, exact terminal engineering "
    "recovery, and epoch-zero checkpoint-chain replay. The connected-frame profile "
    "adds bounded connected graphs, multiple support components, proportional "
    "prescribed displacements, finite rigid offsets, optional RZ end releases, and uniform "
    "dead loads on members in explicitly declared chord-bound local axes. Explicit SI "
    "mass-per-length and global gravity inputs generate self-weight in the same "
    "consistent load operator. Density-derived self-weight and arbitrarily rotated "
    "local axes remain outside the unified entry point. The connected profile is "
    "still a non-public "
    "candidate until its promotion gates pass. No profile grants design-code, "
    "final-design, commercial, or release-readiness authority."
)

NonlinearFrameProfile = Literal[
    "fixed_chord_serial_cantilever.v1",
    "corotational_one_bay_portal.v1",
    "corotational_connected_frame2d.v1",
]

_HASH_ZERO = "sha256:" + "0" * 64
_STABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ACTIVE_COMPONENTS = ("UX", "UY", "RZ")
_LOAD_COMPONENTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
_STEEL_KEYS = {
    "id",
    "type",
    "elastic_modulus_mpa",
    "yield_stress_mpa",
    "isotropic_hardening_modulus_mpa",
    "kinematic_hardening_modulus_mpa",
    "yield_tolerance_mpa",
}
_CONCRETE_KEYS = {
    "id",
    "type",
    "elastic_modulus_mpa",
    "tensile_strength_mpa",
    "compressive_strength_mpa",
    "tensile_softening_rate",
    "compressive_softening_rate",
    "history_tolerance",
}
_SECTION_KEYS = {
    "id",
    "type",
    "width_m",
    "depth_m",
    "cover_m",
    "concrete_layer_count",
    "top_bar_count",
    "bottom_bar_count",
    "bar_area_m2",
    "steel_material",
    "concrete_material",
}


class NonlinearFrameError(ValueError):
    """Stable unified API error."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")

    def to_blocker(self) -> dict[str, str]:
        return {"kind": self.code, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class NonlinearFrameConfig:
    profile: NonlinearFrameProfile = FIXED_CHORD_SERIAL_PROFILE
    load_steps: int = 4
    residual_tolerance: float = 1.0e-10
    increment_tolerance_m: float = 1.0e-12
    maximum_iterations: int = 40
    matrix_backend: str = VECTOR_MATRIX_BACKEND

    def __post_init__(self) -> None:
        if self.profile not in (
            FIXED_CHORD_SERIAL_PROFILE,
            COROTATIONAL_PORTAL_PROFILE,
            COROTATIONAL_GENERAL_PROFILE,
        ):
            raise ValueError("profile is not a supported nonlinear frame profile")
        if self.matrix_backend not in VECTOR_MATRIX_BACKENDS:
            raise ValueError("matrix_backend is not a supported vector backend")
        if (
            self.profile == FIXED_CHORD_SERIAL_PROFILE
            and self.matrix_backend != VECTOR_MATRIX_BACKEND
        ):
            raise ValueError(
                "the fixed-chord profile currently supports only the dense backend"
            )
        if type(self.load_steps) is not int or not 2 <= self.load_steps <= 64:
            raise ValueError("load_steps must be an integer in [2, 64]")
        if (
            type(self.maximum_iterations) is not int
            or not 1 <= self.maximum_iterations <= 200
        ):
            raise ValueError("maximum_iterations must be an integer in [1, 200]")
        for name in ("residual_tolerance", "increment_tolerance_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite positive number")
            normalized = float(value)
            if not math.isfinite(normalized) or normalized <= 0.0:
                raise ValueError(f"{name} must be a finite positive number")
            object.__setattr__(self, name, normalized)

    @property
    def target_load_factors(self) -> tuple[float, ...]:
        return tuple(step / self.load_steps for step in range(1, self.load_steps + 1))


@dataclass(frozen=True)
class NonlinearFrameResult:
    status: Literal["ready", "blocked"]
    contract_pass: bool
    result_hash: str
    profile: NonlinearFrameProfile
    source_result_hash: str | None
    engineering_result_ir: Mapping[str, Any] | None
    canonical_model_checksum: str
    input_checksum: str
    solver_id: str
    compiler_profile: str
    configuration: Mapping[str, Any]
    contract_bindings: Mapping[str, Any]
    checkpoint: Mapping[str, Any]
    authority: Mapping[str, str]
    node_displacements: tuple[Mapping[str, Any], ...]
    support_reactions: tuple[Mapping[str, Any], ...]
    member_end_forces: tuple[Mapping[str, Any], ...]
    section_results: tuple[Mapping[str, Any], ...]
    fiber_results: tuple[Mapping[str, Any], ...]
    convergence_history: tuple[Mapping[str, Any], ...]
    metrics: Mapping[str, Any]
    unsupported_features: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    claim_boundary: str = UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY
    _checkpoint_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def checkpoint_artifact(self) -> bytes:
        if self._checkpoint_bytes is None:
            raise ValueError("no checkpoint-chain artifact is available")
        return self._checkpoint_bytes

    def to_dict(self) -> dict[str, Any]:
        return _result_payload(self, include_hash=True)


@dataclass(frozen=True)
class NonlinearFrameValidationReport:
    status: Literal["ready", "blocked"]
    contract_pass: bool
    result_hash: str
    profile: NonlinearFrameProfile
    exact_engineering_recovery: bool
    exact_checkpoint_chain_replay: bool
    checkpoint_available: bool
    terminal_epoch: int | None
    terminal_load_factor: float | None
    unsupported_feature_count: int
    fallback_count: int
    regularization_count: int
    external_level2_attached: bool
    claim_boundary: str = UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": UNIFIED_NONLINEAR_FRAME_REPORT_SCHEMA_VERSION,
            "status": self.status,
            "contract_pass": self.contract_pass,
            "result_hash": self.result_hash,
            "profile": self.profile,
            "exact_engineering_recovery": self.exact_engineering_recovery,
            "exact_checkpoint_chain_replay": self.exact_checkpoint_chain_replay,
            "checkpoint_available": self.checkpoint_available,
            "terminal_epoch": self.terminal_epoch,
            "terminal_load_factor": self.terminal_load_factor,
            "unsupported_feature_count": self.unsupported_feature_count,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "external_level2_attached": self.external_level2_attached,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class NonlinearFrameCheckpointAdvance:
    """Opaque partial execution artifact for a durable worker checkpoint."""

    profile: NonlinearFrameProfile
    completed_steps: int
    total_steps: int
    newly_solved_steps: int
    replayed_prefix_steps: int
    problem_contract_hash: str
    resume_contract_hash: str
    checkpoint_chain_hash: str
    checkpoint_artifact_hash: str
    checkpoint_bytes: bytes = field(repr=False, compare=False)
    exact_prefix_replay: bool = True
    fallback_count: int = 0
    regularization_count: int = 0
    claim_boundary: str = UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY

    @property
    def remaining_steps(self) -> int:
        return self.total_steps - self.completed_steps

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "nonlinear-frame-checkpoint-advance.v1",
            "profile": self.profile,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "remaining_steps": self.remaining_steps,
            "newly_solved_steps": self.newly_solved_steps,
            "replayed_prefix_steps": self.replayed_prefix_steps,
            "problem_contract_hash": self.problem_contract_hash,
            "resume_contract_hash": self.resume_contract_hash,
            "checkpoint_chain_hash": self.checkpoint_chain_hash,
            "checkpoint_artifact_hash": self.checkpoint_artifact_hash,
            "checkpoint_byte_length": len(self.checkpoint_bytes),
            "exact_prefix_replay": self.exact_prefix_replay,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "solver_truth_created": False,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class _CompiledPortal:
    problem: StatefulCorotationalFiberFrame2DProblem
    compilation: (
        CorotationalFiberFramePortalCompilation
        | CorotationalFiberFrameGeneralCompilation
    )
    node_ids: tuple[str, ...]
    section_by_member: tuple[StatefulRCFiberSection, ...]
    support_node_ids: tuple[str, ...]
    model_ir_adapter_hash: str
    topology_plan: FiberFrameNonlinearExecutionTopologyPlan
    equation_scaling: FiberFramePhysicalEquationScalingBinding | None
    bounded_execution_plan: BoundedPlanarExecutionPlanBinding | None


@dataclass(frozen=True)
class _CorotationalExecution:
    path: StatefulCorotationalFiberFrame2DLoadPathResult
    chain: StatefulCorotationalFiberFrame2DCheckpointChain
    checkpoint_bytes: bytes
    restart_supplied: bool
    replayed_prefix_step_count: int
    newly_solved_step_count: int


def _rigid_body_constraint_rank(problem: StatefulCorotationalFiberFrame2DProblem) -> int:
    coordinates = np.asarray(problem.node_coordinates_m, dtype=np.float64)
    spans = np.ptp(coordinates, axis=0)
    characteristic_length = max(float(np.linalg.norm(spans)), 1.0)
    rows: list[tuple[float, float, float]] = []
    for dof in problem.fixed_global_dofs:
        node_index, component = divmod(dof, 3)
        x, y = coordinates[node_index] / characteristic_length
        if component == 0:
            rows.append((1.0, 0.0, -float(y)))
        elif component == 1:
            rows.append((0.0, 1.0, float(x)))
        else:
            rows.append((0.0, 0.0, 1.0))
    matrix = np.asarray(rows, dtype=np.float64)
    return int(np.linalg.matrix_rank(matrix, tol=1.0e-12))


def _corotational_solver_blocked_error(
    compiled: _CompiledPortal,
    execution: _CorotationalExecution,
    *,
    general_profile: bool,
) -> NonlinearFrameError:
    steps = execution.path.steps
    terminal_reason = (
        str(steps[-1].metrics.get("terminal_reason") or "") if steps else ""
    )
    if terminal_reason == "singular_tangent_stiffness":
        released_members = tuple(
            member.member_id
            for member in compiled.problem.members
            if member.features.has_release
        )
        if released_members:
            return NonlinearFrameError(
                "corotational_released_mechanism_detected",
                "/solver/tangent",
                (
                    "The tangent is singular for a model containing explicit RZ end "
                    f"releases; released members={list(released_members)}. The trial "
                    "was rejected without fallback or regularization."
                ),
            )
        return NonlinearFrameError(
            "corotational_singular_system_detected",
            "/solver/tangent",
            (
                "The tangent is singular without an explicit released-member "
                "mechanism. The trial was rejected without fallback or regularization."
            ),
        )
    return NonlinearFrameError(
        (
            "corotational_general_solver_blocked"
            if general_profile
            else "corotational_portal_solver_blocked"
        ),
        "/solver",
        (
            "The configured load path did not commit exactly"
            + (f"; terminal_reason={terminal_reason}." if terminal_reason else ".")
        ),
    )


def analyze_nonlinear_frame(
    model: CanonicalModel,
    config: NonlinearFrameConfig | None = None,
    *,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None = None,
) -> NonlinearFrameResult:
    """Analyze one explicitly selected bounded nonlinear frame profile."""

    if type(model) is not CanonicalModel:
        raise ValueError("model must be a CanonicalModel")
    if config is not None and type(config) is not NonlinearFrameConfig:
        raise ValueError("config must be a NonlinearFrameConfig")
    if restart_checkpoint_chain is not None and not isinstance(
        restart_checkpoint_chain, (bytes, bytearray, memoryview)
    ):
        raise ValueError("restart_checkpoint_chain must be bytes-like")
    cfg = NonlinearFrameConfig() if config is None else config
    snapshot = model.detached_analysis_snapshot()
    if cfg.profile == FIXED_CHORD_SERIAL_PROFILE:
        return _analyze_fixed_chord(snapshot, cfg, restart_checkpoint_chain)
    return _analyze_corotational_portal(
        snapshot,
        cfg,
        restart_checkpoint_chain,
        source_model_ir_adapter=None,
    )


def analyze_nonlinear_frame_model_ir(
    document: ModelIRDocument,
    config: NonlinearFrameConfig | None = None,
    *,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None = None,
) -> NonlinearFrameResult:
    """Analyze the exact bounded planar ModelIR profile with source binding."""

    cfg = (
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE)
        if config is None
        else config
    )
    if type(cfg) is not NonlinearFrameConfig:
        raise ValueError("config must be a NonlinearFrameConfig")
    if cfg.profile != COROTATIONAL_GENERAL_PROFILE:
        _fail(
            "bounded_planar_model_ir_solver_profile_invalid",
            "/config/profile",
            "Bounded planar ModelIR requires corotational_connected_frame2d.v1.",
        )
    adapter = adapt_bounded_planar_model_ir_v2(document)
    result = _analyze_corotational_portal(
        adapter.canonical_model,
        cfg,
        restart_checkpoint_chain,
        source_model_ir_adapter=adapter,
    )
    return _bind_source_model_ir_adapter(result, adapter)


def advance_nonlinear_frame_checkpoint(
    model: CanonicalModel,
    config: NonlinearFrameConfig,
    *,
    maximum_new_steps: int,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None = None,
) -> NonlinearFrameCheckpointAdvance:
    """Advance a corotational path without publishing an engineering result.

    This entry point exists for durable workers. It emits only an exact,
    replay-validated checkpoint chain. Final result and engineering authority
    remain exclusively with :func:`analyze_nonlinear_frame` and its validator.
    """

    if type(model) is not CanonicalModel:
        raise ValueError("model must be a CanonicalModel")
    if type(config) is not NonlinearFrameConfig:
        raise ValueError("config must be a NonlinearFrameConfig")
    if config.profile == FIXED_CHORD_SERIAL_PROFILE:
        raise ValueError("durable checkpoint advance requires a corotational profile")
    if type(maximum_new_steps) is not int or not 1 <= maximum_new_steps <= 64:
        raise ValueError("maximum_new_steps must be an integer in [1, 64]")
    if restart_checkpoint_chain is not None and not isinstance(
        restart_checkpoint_chain, (bytes, bytearray, memoryview)
    ):
        raise ValueError("restart_checkpoint_chain must be bytes-like")
    snapshot = model.detached_analysis_snapshot()
    return _advance_corotational_checkpoint(
        snapshot,
        config,
        maximum_new_steps=maximum_new_steps,
        restart_checkpoint_chain=restart_checkpoint_chain,
        source_model_ir_adapter=None,
    )


def advance_nonlinear_frame_model_ir_checkpoint(
    document: ModelIRDocument,
    config: NonlinearFrameConfig,
    *,
    maximum_new_steps: int,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None = None,
) -> NonlinearFrameCheckpointAdvance:
    """Advance an exact source-bound bounded planar ModelIR path."""

    if type(config) is not NonlinearFrameConfig:
        raise ValueError("config must be a NonlinearFrameConfig")
    if config.profile != COROTATIONAL_GENERAL_PROFILE:
        _fail(
            "bounded_planar_model_ir_solver_profile_invalid",
            "/config/profile",
            "Bounded planar ModelIR requires corotational_connected_frame2d.v1.",
        )
    if type(maximum_new_steps) is not int or not 1 <= maximum_new_steps <= 64:
        raise ValueError("maximum_new_steps must be an integer in [1, 64]")
    if restart_checkpoint_chain is not None and not isinstance(
        restart_checkpoint_chain, (bytes, bytearray, memoryview)
    ):
        raise ValueError("restart_checkpoint_chain must be bytes-like")
    adapter = adapt_bounded_planar_model_ir_v2(document)
    return _advance_corotational_checkpoint(
        adapter.canonical_model,
        config,
        maximum_new_steps=maximum_new_steps,
        restart_checkpoint_chain=restart_checkpoint_chain,
        source_model_ir_adapter=adapter,
    )


def _advance_corotational_checkpoint(
    model: CanonicalModel,
    config: NonlinearFrameConfig,
    *,
    maximum_new_steps: int,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None,
    source_model_ir_adapter: BoundedPlanarModelIRAdapter | None,
) -> NonlinearFrameCheckpointAdvance:
    compiled = _compile_portal(
        model,
        general_profile=config.profile == COROTATIONAL_GENERAL_PROFILE,
        source_model_ir_adapter=source_model_ir_adapter,
    )
    execution = _run_corotational_path(
        compiled,
        config,
        restart_checkpoint_chain,
        maximum_new_steps=maximum_new_steps,
    )
    if execution.path.status != "ready" or not execution.path.contract_pass:
        raise NonlinearFrameError(
            "corotational_checkpoint_advance_blocked",
            "/solver",
            "The bounded partial path did not commit exactly.",
        )
    completed = len(execution.path.steps)
    if completed <= execution.replayed_prefix_step_count:
        raise NonlinearFrameError(
            "corotational_checkpoint_no_progress",
            "/maximum_new_steps",
            "Checkpoint advance must commit at least one new path step.",
        )
    fallback_count = sum(
        int(bool(step.metrics.get("fallback_used"))) for step in execution.path.steps
    )
    regularization_count = sum(
        int(bool(step.metrics.get("regularization_used")))
        for step in execution.path.steps
    )
    if fallback_count or regularization_count:
        raise NonlinearFrameError(
            "corotational_checkpoint_fallback_rejected",
            "/solver",
            "A durable checkpoint may not contain fallback or regularization.",
        )
    return NonlinearFrameCheckpointAdvance(
        profile=config.profile,
        completed_steps=completed,
        total_steps=config.load_steps,
        newly_solved_steps=execution.newly_solved_step_count,
        replayed_prefix_steps=execution.replayed_prefix_step_count,
        problem_contract_hash=compiled.problem.contract_hash,
        resume_contract_hash=_resume_contract_hash(compiled, config),
        checkpoint_chain_hash=execution.chain.chain_hash,
        checkpoint_artifact_hash=_artifact_hash(execution.checkpoint_bytes),
        checkpoint_bytes=execution.checkpoint_bytes,
        fallback_count=fallback_count,
        regularization_count=regularization_count,
    )


def nonlinear_frame_resume_contract_hash(
    model: CanonicalModel, config: NonlinearFrameConfig
) -> str:
    """Hash the exact model/compiler/load path required for checkpoint reuse."""

    if type(model) is not CanonicalModel or type(config) is not NonlinearFrameConfig:
        raise ValueError("model and config must use exact public contract types")
    if config.profile == FIXED_CHORD_SERIAL_PROFILE:
        raise ValueError("durable resume binding requires a corotational profile")
    snapshot = model.detached_analysis_snapshot()
    compiled = _compile_portal(
        snapshot,
        general_profile=config.profile == COROTATIONAL_GENERAL_PROFILE,
    )
    return _resume_contract_hash(compiled, config)


def nonlinear_frame_model_ir_resume_contract_hash(
    document: ModelIRDocument, config: NonlinearFrameConfig
) -> str:
    """Hash the exact ModelIR/adapter/compiler/load path for checkpoint reuse."""

    if type(config) is not NonlinearFrameConfig:
        raise ValueError("config must be a NonlinearFrameConfig")
    if config.profile != COROTATIONAL_GENERAL_PROFILE:
        _fail(
            "bounded_planar_model_ir_solver_profile_invalid",
            "/config/profile",
            "Bounded planar ModelIR requires corotational_connected_frame2d.v1.",
        )
    adapter = adapt_bounded_planar_model_ir_v2(document)
    compiled = _compile_portal(
        adapter.canonical_model,
        general_profile=True,
        source_model_ir_adapter=adapter,
    )
    return _resume_contract_hash(compiled, config)


def validate_nonlinear_frame_result(
    result: NonlinearFrameResult,
) -> NonlinearFrameValidationReport:
    if type(result) is not NonlinearFrameResult:
        raise ValueError("result must be a NonlinearFrameResult")
    expected_hash = canonical_hash(_result_payload(result, include_hash=False))
    if result.result_hash != expected_hash:
        raise ValueError("result_hash does not match the unified result payload")
    _validate_result_schema(result.to_dict())
    _validate_engineering_result_ir_binding(
        profile=result.profile,
        status=result.status,
        source_result_hash=result.source_result_hash,
        engineering_result_ir=result.engineering_result_ir,
        contract_bindings=result.contract_bindings,
        authority=result.authority,
    )
    _validate_source_model_ir_adapter_binding(
        profile=result.profile,
        input_checksum=result.input_checksum,
        canonical_model_checksum=result.canonical_model_checksum,
        contract_bindings=result.contract_bindings,
    )
    exact_recovery = bool(result.metrics.get("exact_engineering_recovery"))
    exact_replay = bool(result.metrics.get("exact_checkpoint_chain_replay"))
    fallback_count = int(result.metrics.get("fallback_count", 0))
    regularization_count = int(result.metrics.get("regularization_count", 0))
    sparse_selected = (
        result.configuration.get("matrix_backend") == VECTOR_SPARSE_MATRIX_BACKEND
    )
    solver_executed = result.metrics.get("solver_executed") is True
    no_solve_contract = result.metrics.get("no_solve_contract_pass") is True
    sparse_execution_contract = bool(
        not sparse_selected
        or (not solver_executed and no_solve_contract)
        or (
            solver_executed
            and result.metrics.get("sparse_backend_used") is True
            and result.metrics.get("native_sparse_assembly_used") is True
            and result.metrics.get("sparse_factorization_diagnostics_passed") is True
            and int(result.metrics.get("sparse_factorization_count", 0)) > 0
            and len(result.metrics.get("sparse_factorization_diagnostic_hashes", ()))
            == int(result.metrics.get("sparse_factorization_count", 0))
            and isinstance(result.metrics.get("sparse_factorization_policy_hash"), str)
            and result.metrics["sparse_factorization_policy_hash"].startswith("sha256:")
        )
    )
    ready = bool(
        result.status == "ready"
        and result.contract_pass
        and not result.unsupported_features
        and exact_recovery
        and exact_replay
        and fallback_count == 0
        and regularization_count == 0
        and sparse_execution_contract
        and result.checkpoint.get("available") is True
        and result.authority.get("reaction")
        in {"authoritative", "exact_bounded_candidate"}
        and result.authority.get("member_force")
        in {"authoritative", "exact_bounded_candidate"}
        and result.authority.get("section_resultant")
        in {"authoritative", "exact_bounded_candidate"}
        and result.authority.get("fiber_result")
        in {"authoritative", "exact_bounded_candidate"}
    )
    if result.contract_pass != ready:
        raise ValueError("contract_pass differs from unified local authority gates")
    epoch = result.checkpoint.get("terminal_epoch")
    load = result.checkpoint.get("terminal_load_factor")
    return NonlinearFrameValidationReport(
        status="ready" if ready else "blocked",
        contract_pass=ready,
        result_hash=result.result_hash,
        profile=result.profile,
        exact_engineering_recovery=exact_recovery,
        exact_checkpoint_chain_replay=exact_replay,
        checkpoint_available=bool(result.checkpoint.get("available")),
        terminal_epoch=int(epoch) if type(epoch) is int else None,
        terminal_load_factor=(
            float(load)
            if isinstance(load, (int, float)) and not isinstance(load, bool)
            else None
        ),
        unsupported_feature_count=len(result.unsupported_features),
        fallback_count=fallback_count,
        regularization_count=regularization_count,
        external_level2_attached=(result.authority.get("external_vv") == "level2"),
    )


def validate_nonlinear_frame_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a detached unified result manifest and its canonical hash."""

    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    _validate_result_schema(normalized)
    claimed = str(normalized["result_hash"])
    body = dict(normalized)
    body.pop("result_hash")
    if claimed != canonical_hash(body):
        raise ValueError("result_hash does not match the unified result payload")
    _validate_engineering_result_ir_binding(
        profile=cast(NonlinearFrameProfile, normalized["profile"]),
        status=cast(Literal["ready", "blocked"], normalized["status"]),
        source_result_hash=cast(str | None, normalized["source_result_hash"]),
        engineering_result_ir=cast(
            Mapping[str, Any] | None,
            normalized["engineering_result_ir"],
        ),
        contract_bindings=cast(
            Mapping[str, Any],
            normalized["contract_bindings"],
        ),
        authority=cast(Mapping[str, str], normalized["authority"]),
    )
    _validate_source_model_ir_adapter_binding(
        profile=cast(NonlinearFrameProfile, normalized["profile"]),
        input_checksum=str(normalized["input_checksum"]),
        canonical_model_checksum=str(normalized["canonical_model_checksum"]),
        contract_bindings=cast(
            Mapping[str, Any],
            normalized["contract_bindings"],
        ),
    )
    return normalized


def _analyze_fixed_chord(
    model: CanonicalModel,
    config: NonlinearFrameConfig,
    restart: bytes | bytearray | memoryview | None,
) -> NonlinearFrameResult:
    source = analyze_public_rc_fiber_frame(
        model,
        PublicRCFiberFrameConfig(
            load_steps=config.load_steps,
            residual_tolerance=config.residual_tolerance,
            increment_tolerance_m=config.increment_tolerance_m,
            maximum_iterations=config.maximum_iterations,
        ),
        restart_checkpoint_chain=restart,
    )
    report = validate_public_rc_fiber_frame_result(source)
    checkpoint_bytes = (
        source.checkpoint_artifact() if source.checkpoint.get("available") else None
    )
    authority = MappingProxyType(
        {
            "convergence": str(
                source.authority.get("convergence", "not_authoritative")
            ),
            "displacement": str(
                source.authority.get("displacement", "not_authoritative")
            ),
            "reaction": str(source.authority.get("reaction", "not_authoritative")),
            "member_force": str(
                source.authority.get("member_force", "not_authoritative")
            ),
            "member_features": "not_supported",
            "section_resultant": str(
                source.authority.get("section_resultant", "not_authoritative")
            ),
            "fiber_result": str(
                source.authority.get("fiber_strain_stress", "not_authoritative")
            ),
            "fallback": "not_used"
            if report.fallback_count == 0
            else "used_not_authoritative",
            "public_api": "bounded_public",
            "external_vv": "not_attached",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        }
    )
    fibers = tuple(_normalize_fixed_fiber_row(row) for row in source.fiber_results)
    metrics = dict(source.metrics)
    metrics.update(
        {
            "exact_engineering_recovery": report.exact_engineering_recovery,
            "exact_checkpoint_chain_replay": bool(
                report.contract_pass and report.checkpoint_available
            ),
            "external_level2_attached": False,
        }
    )
    return _make_result(
        status="ready" if report.contract_pass else "blocked",
        profile=FIXED_CHORD_SERIAL_PROFILE,
        source_result_hash=source.result_hash,
        engineering_result_ir=None,
        model=model,
        solver_id=source.solver_id,
        compiler_profile=source.compiler_profile,
        configuration=dict(source.configuration),
        contract_bindings={
            "source_public_result_hash": source.result_hash,
            **dict(source.contract_bindings),
        },
        checkpoint=dict(source.checkpoint),
        authority=authority,
        node_displacements=source.node_displacements,
        support_reactions=source.support_reactions,
        member_end_forces=source.member_end_forces,
        section_results=source.section_results,
        fiber_results=fibers,
        convergence_history=source.convergence_history,
        metrics=metrics,
        unsupported_features=source.unsupported_features,
        warnings=source.warnings,
        checkpoint_bytes=checkpoint_bytes,
    )


def _analyze_corotational_portal(
    model: CanonicalModel,
    config: NonlinearFrameConfig,
    restart: bytes | bytearray | memoryview | None,
    *,
    source_model_ir_adapter: BoundedPlanarModelIRAdapter | None,
) -> NonlinearFrameResult:
    general_profile = config.profile == COROTATIONAL_GENERAL_PROFILE
    selected_compiler_profile = (
        COROTATIONAL_FIBER_FRAME_GENERAL_COMPILER_PROFILE
        if general_profile
        else "planar_one_bay_one_story_portal_explicit_fiber_section.v1"
    )
    configuration: dict[str, Any] = {
        "profile": config.profile,
        "load_steps": config.load_steps,
        "target_load_factors": list(config.target_load_factors),
        "scaled_residual_tolerance": config.residual_tolerance,
        "solver_coordinate_increment_tolerance_m": config.increment_tolerance_m,
        "maximum_iterations": config.maximum_iterations,
        "matrix_backend": config.matrix_backend,
        "stiffness_storage": (
            "scipy_sparse_csr"
            if config.matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND
            else "numpy_dense_ndarray"
        ),
        "restart_supplied": restart is not None,
        "restart_checkpoint_artifact_hash": (
            _artifact_hash(restart) if restart is not None else None
        ),
    }
    unsupported: list[Mapping[str, Any]] = [
        _normalize_unsupported_feature(row, index=index, source_model=True)
        for index, row in enumerate(model.unsupported_features)
    ]
    warnings = list(model.warnings)
    compiled: _CompiledPortal | None = None
    execution: _CorotationalExecution | None = None
    adapter: CorotationalEngineeringSourceAdapter | None = None
    engineering: CorotationalFiberFrameEngineeringResultIR | None = None
    terminal_trace: FiberFramePhysicalResidualTrace | None = None
    if not unsupported:
        try:
            compiled = _compile_portal(
                model,
                general_profile=general_profile,
                source_model_ir_adapter=source_model_ir_adapter,
            )
            rigid_body_rank = _rigid_body_constraint_rank(compiled.problem)
            if rigid_body_rank < 3:
                raise NonlinearFrameError(
                    "corotational_rigid_body_constraint_rank_deficient",
                    "/supports",
                    (
                        "Active support constraints eliminate only "
                        f"{rigid_body_rank}/3 planar rigid-body modes. The system is "
                        "rejected before solving without fallback or regularization."
                    ),
                )
            if (
                compiled.equation_scaling is None
                and compiled.topology_plan.array("free_physical_dofs").size
            ):
                configuration["equation_scaling"] = {
                    "status": "unavailable",
                    "reason": "no_free_reference_load",
                }
                raise NonlinearFrameError(
                    "corotational_equation_scaling_unavailable",
                    "/solver/equation_scaling",
                    (
                        "An iterative path with free equations requires a "
                        "source-bound reference force; prescribed motion alone "
                        "does not create one."
                    ),
                )
            execution = _run_corotational_path(compiled, config, restart)
            if execution.path.status != "ready" or not execution.path.contract_pass:
                raise _corotational_solver_blocked_error(
                    compiled,
                    execution,
                    general_profile=general_profile,
                )
            no_solve_path = all(
                step.metrics.get("no_solve_contract_pass") is True
                for step in execution.path.steps
            )
            if compiled.equation_scaling is not None:
                terminal_trace = trace_stateful_fiber_frame2d_free_physical_residual(
                    topology_plan=compiled.topology_plan,
                    scaling_binding=compiled.equation_scaling,
                    raw_free_residual_source_3dof=(
                        execution.path.steps[-1].trial_assembly.residual_kn
                    ),
                )
            elif not no_solve_path:
                raise NonlinearFrameError(
                    "corotational_equation_scaling_unavailable",
                    "/solver/equation_scaling",
                    "Iterative execution requires a source-bound free-equation scale.",
                )
            if isinstance(
                compiled.compilation, CorotationalFiberFrameGeneralCompilation
            ):
                adapter = create_corotational_fiber_frame_general_j1_j5_adapter(
                    compiled.compilation,
                    execution.path,
                )
            else:
                adapter = create_corotational_fiber_frame_j1_j5_adapter(
                    compiled.compilation,
                    execution.path,
                )
            digest = model.canonical_model_checksum.removeprefix("sha256:")[:20]
            engineering = create_corotational_fiber_frame_engineering_result_ir(
                engineering_result_id=(
                    f"engineering.corotational_general.{digest}"
                    if general_profile
                    else f"engineering.corotational_portal.{digest}"
                ),
                source_adapter=adapter,
            )
        except (
            NonlinearFrameError,
            StatefulCorotationalFiberFrame2DCheckpointChainArtifactError,
            ValueError,
        ) as exc:
            code = str(
                getattr(
                    exc,
                    "code",
                    (
                        "corotational_general_execution_failed"
                        if general_profile
                        else "corotational_portal_execution_failed"
                    ),
                )
            )
            path = str(
                getattr(
                    exc,
                    "path",
                    "/restart_checkpoint_chain"
                    if restart is not None and execution is None
                    else "/solver",
                )
            )
            unsupported.append({"kind": code, "path": path, "detail": str(exc)})

    ready = bool(
        compiled is not None
        and execution is not None
        and adapter is not None
        and engineering is not None
        and (
            terminal_trace is not None
            or all(
                step.metrics.get("no_solve_contract_pass") is True
                for step in execution.path.steps
            )
        )
        and not unsupported
    )
    if not ready:
        return _make_result(
            status="blocked",
            profile=config.profile,
            source_result_hash=None,
            engineering_result_ir=None,
            model=model,
            solver_id="public_cpu_corotational_rc_fiber_frame_newton_v1",
            compiler_profile=selected_compiler_profile,
            configuration=configuration,
            contract_bindings=(
                _corotational_plan_bindings(compiled, terminal_trace)
                if compiled is not None
                else {}
            ),
            checkpoint={"available": False},
            authority=_blocked_authority(),
            node_displacements=(),
            support_reactions=(),
            member_end_forces=(),
            section_results=(),
            fiber_results=(),
            convergence_history=(),
            metrics={
                "solver_executed": execution is not None,
                "exact_engineering_recovery": False,
                "exact_checkpoint_chain_replay": False,
                **_corotational_linear_solver_metrics(
                    execution,
                    matrix_backend=config.matrix_backend,
                ),
                "external_level2_attached": False,
            },
            unsupported_features=tuple(unsupported),
            warnings=tuple(warnings),
            checkpoint_bytes=None,
        )

    assert compiled is not None
    assert execution is not None
    assert adapter is not None
    assert engineering is not None
    checkpoint = {
        "available": True,
        "storage_profile": "canonical-signed-zero-preserving-utf8-json.v1",
        "chain_hash": execution.chain.chain_hash,
        "artifact_hash": _artifact_hash(execution.checkpoint_bytes),
        "artifact_byte_length": len(execution.checkpoint_bytes),
        "root_state_hash": execution.chain.root_checkpoint.state_hash,
        "terminal_state_hash": execution.chain.terminal_checkpoint.state_hash,
        "terminal_epoch": execution.chain.terminal_checkpoint.epoch,
        "terminal_load_factor": execution.chain.terminal_checkpoint.load_factor,
        "complete_ancestry_included": True,
        "prefix_replay_required": True,
    }
    history = tuple(
        {
            "load_step": index,
            "target_load_factor": step.metrics["target_load_factor"],
            "committed": step.committed,
            **dict(row),
        }
        for index, step in enumerate(execution.path.steps, start=1)
        for row in step.trial_solution.convergence_history
    )
    scaling_metrics: dict[str, Any]
    if terminal_trace is None:
        scaling_metrics = {
            "terminal_physical_residual_trace_status": "unavailable",
            "terminal_physical_residual_trace_reason": (
                "no_free_equations_no_convergence_claim"
            ),
        }
    else:
        scaling_metrics = {
            "terminal_physical_residual_trace_status": "available",
            "terminal_physical_residual_trace_hash": terminal_trace.trace_hash,
            "characteristic_length_m": terminal_trace.characteristic_length_m,
            "reference_force_n": terminal_trace.reference_force_n,
            "raw_translational_residual_linf_n": (
                terminal_trace.raw_translation_linf_n
            ),
            "raw_rotational_residual_linf_nm": (terminal_trace.raw_rotation_linf_nm),
            "dimensionless_scaled_residual_linf": terminal_trace.scaled_linf,
            "dimensionless_scaled_residual_l2": terminal_trace.scaled_l2,
            "scaled_residual_governing_equation": (terminal_trace.governing_equation),
            "scaled_residual_governing_node_id": (terminal_trace.governing_node_id),
            "scaled_residual_governing_dof": terminal_trace.governing_dof,
        }
    metrics = {
        "solver_executed": bool(
            execution.replayed_prefix_step_count or execution.newly_solved_step_count
        ),
        "exact_engineering_recovery": True,
        "exact_checkpoint_chain_replay": True,
        "restart_supplied": execution.restart_supplied,
        "replayed_prefix_step_count": execution.replayed_prefix_step_count,
        "newly_solved_step_count": execution.newly_solved_step_count,
        "committed_step_count": len(execution.path.steps),
        "terminal_solved_load_factor": execution.path.final_checkpoint.load_factor,
        **_corotational_linear_solver_metrics(
            execution,
            matrix_backend=config.matrix_backend,
        ),
        "external_level2_attached": False,
        **scaling_metrics,
        **dict(engineering.metrics),
    }
    if compiled.equation_scaling is None:
        equation_scaling_configuration: dict[str, Any] = {
            "status": "unavailable",
            "reason": "no_free_reference_load",
        }
    else:
        equation_scaling_configuration = {
            "status": "available",
            "schema_version": compiled.equation_scaling.engine_scaling.schema_version,
            "characteristic_length_m": (
                compiled.equation_scaling.characteristic_length_m
            ),
            "reference_force_n": compiled.equation_scaling.reference_force_n,
            "equation_scope": (
                compiled.equation_scaling.engine_scaling.reference_equation_scope
            ),
        }
    configuration = {
        **configuration,
        "equation_scaling": equation_scaling_configuration,
    }
    return _make_result(
        status="ready",
        profile=config.profile,
        source_result_hash=engineering.engineering_result_hash,
        engineering_result_ir=engineering.to_manifest(),
        model=model,
        solver_id="public_cpu_corotational_rc_fiber_frame_newton_v1",
        compiler_profile=adapter.compiler_profile,
        configuration=configuration,
        contract_bindings={
            **_corotational_plan_bindings(compiled, terminal_trace),
            "compiler_hash": adapter.compiler_hash,
            "j1_j5_adapter_hash": adapter.adapter_hash,
            "engineering_result_hash": engineering.engineering_result_hash,
            "engineering_array_bundle_hash": engineering.array_bundle_hash,
            "quantity_catalog_hash": engineering.quantity_catalog_hash,
            "checkpoint_chain_hash": execution.chain.chain_hash,
        },
        checkpoint=checkpoint,
        authority=MappingProxyType(
            {
                "convergence": "inherited_bounded_candidate",
                "displacement": "exact_bounded_candidate",
                "reaction": "exact_bounded_candidate",
                "member_force": "exact_bounded_candidate",
                "member_features": (
                    "exact_bounded_candidate" if general_profile else "not_supported"
                ),
                "section_resultant": "exact_bounded_candidate",
                "fiber_result": "exact_bounded_candidate",
                "fallback": "not_used",
                "public_api": "developer_preview_candidate",
                "external_vv": "not_attached",
                "engineering_design": "not_authoritative",
                "release_readiness": "not_authoritative",
            }
        ),
        node_displacements=_corotational_node_rows(compiled, engineering),
        support_reactions=_corotational_reaction_rows(compiled, engineering),
        member_end_forces=_corotational_member_rows(compiled, engineering),
        section_results=_corotational_section_rows(compiled, engineering),
        fiber_results=_corotational_fiber_rows(compiled, engineering),
        convergence_history=history,
        metrics=metrics,
        unsupported_features=(),
        warnings=tuple(warnings),
        checkpoint_bytes=execution.checkpoint_bytes,
    )


def _compile_portal(
    model: CanonicalModel,
    *,
    general_profile: bool = False,
    source_model_ir_adapter: BoundedPlanarModelIRAdapter | None = None,
) -> _CompiledPortal:
    if source_model_ir_adapter is not None:
        if type(source_model_ir_adapter) is not BoundedPlanarModelIRAdapter:
            _fail(
                "bounded_planar_model_ir_adapter_type_invalid",
                "/source_model_ir_adapter",
                "Expected an exact bounded planar ModelIR adapter.",
            )
        if (
            source_model_ir_adapter.canonical_model_checksum
            != model.canonical_model_checksum
        ):
            _fail(
                "bounded_planar_model_ir_adapter_target_mismatch",
                "/source_model_ir_adapter/canonical_model_checksum",
                "ModelIR adapter target differs from the analysis snapshot.",
            )
    if model.schema_version != CANONICAL_MODEL_SCHEMA_VERSION:
        _fail(
            "corotational_portal_schema_invalid",
            "/schema_version",
            "Canonical model v1 is required.",
        )
    if model.units.length != "m" or model.units.force != "kN":
        _fail(
            "corotational_portal_units_unsupported",
            "/units",
            "Units must be length=m and force=kN.",
        )
    if (
        tuple(str(value).upper() for value in model.coordinate_system.axis_order)
        != ("X", "Y", "Z")
        or str(model.coordinate_system.up_axis).upper() != "Z"
    ):
        _fail(
            "corotational_portal_coordinate_system_unsupported",
            "/coordinate_system",
            "Global XYZ order with Z up is required.",
        )
    if set(model.metadata) - {"case_id"}:
        _fail(
            "corotational_portal_metadata_unsupported",
            "/metadata",
            "Only optional metadata.case_id is supported.",
        )
    if "case_id" in model.metadata:
        _stable(model.metadata["case_id"], "/metadata/case_id")
    if (not general_profile and len(model.nodes) != 4) or (
        general_profile and not 2 <= len(model.nodes) <= 128
    ):
        _fail(
            "corotational_portal_node_count_invalid",
            "/nodes",
            (
                "The connected-frame profile requires 2-128 nodes."
                if general_profile
                else "Exactly four portal nodes are required."
            ),
        )
    node_ids: list[str] = []
    coordinates: list[tuple[float, float]] = []
    for index, row in enumerate(model.nodes):
        path = f"/nodes/{index}"
        _keys(row, {"id", "coordinates"}, path)
        node_id = _stable(row["id"], f"{path}/id")
        raw = row["coordinates"]
        if node_id in node_ids or type(raw) is not list or len(raw) != 3:
            _fail(
                "corotational_portal_node_invalid",
                path,
                "Node IDs must be unique and coordinates must contain XYZ.",
            )
        x, y, z = (
            _number(raw[offset], f"{path}/coordinates/{offset}") for offset in range(3)
        )
        if z != 0.0 or (x, y) in coordinates:
            _fail(
                "corotational_portal_node_geometry_invalid",
                f"{path}/coordinates",
                "Nodes must be unique in the XY plane with Z=0.",
            )
        node_ids.append(node_id)
        coordinates.append((x, y))

    materials: dict[str, tuple[str, Any]] = {}
    for index, row in enumerate(model.materials):
        path = f"/materials/{index}"
        material_id = _stable(row.get("id"), f"{path}/id")
        if material_id in materials:
            _fail(
                "corotational_portal_material_id_duplicate",
                f"{path}/id",
                "Material IDs must be unique.",
            )
        try:
            material: BilinearCombinedHardeningSteel | AsymmetricConcreteDamageMaterial
            if row.get("type") == "bilinear_combined_hardening_steel":
                _keys(row, _STEEL_KEYS, path)
                material = BilinearCombinedHardeningSteel(
                    elastic_modulus_mpa=_positive(
                        row["elastic_modulus_mpa"], f"{path}/elastic_modulus_mpa"
                    ),
                    yield_stress_mpa=_positive(
                        row["yield_stress_mpa"], f"{path}/yield_stress_mpa"
                    ),
                    isotropic_hardening_modulus_mpa=_nonnegative(
                        row["isotropic_hardening_modulus_mpa"],
                        f"{path}/isotropic_hardening_modulus_mpa",
                    ),
                    kinematic_hardening_modulus_mpa=_nonnegative(
                        row["kinematic_hardening_modulus_mpa"],
                        f"{path}/kinematic_hardening_modulus_mpa",
                    ),
                    yield_tolerance_mpa=_nonnegative(
                        row["yield_tolerance_mpa"], f"{path}/yield_tolerance_mpa"
                    ),
                    material_id=material_id,
                )
                kind = "steel"
            elif row.get("type") == "asymmetric_concrete_damage":
                _keys(row, _CONCRETE_KEYS, path)
                material = AsymmetricConcreteDamageMaterial(
                    elastic_modulus_mpa=_positive(
                        row["elastic_modulus_mpa"], f"{path}/elastic_modulus_mpa"
                    ),
                    tensile_strength_mpa=_positive(
                        row["tensile_strength_mpa"], f"{path}/tensile_strength_mpa"
                    ),
                    compressive_strength_mpa=_positive(
                        row["compressive_strength_mpa"],
                        f"{path}/compressive_strength_mpa",
                    ),
                    tensile_softening_rate=_positive(
                        row["tensile_softening_rate"], f"{path}/tensile_softening_rate"
                    ),
                    compressive_softening_rate=_positive(
                        row["compressive_softening_rate"],
                        f"{path}/compressive_softening_rate",
                    ),
                    history_tolerance=_nonnegative(
                        row["history_tolerance"], f"{path}/history_tolerance"
                    ),
                    material_id=material_id,
                )
                kind = "concrete"
            else:
                _fail(
                    "corotational_portal_material_type_unsupported",
                    f"{path}/type",
                    "Supported steel or concrete material is required.",
                )
        except NonlinearFrameError:
            raise
        except ValueError as exc:
            _fail("corotational_portal_material_invalid", path, str(exc))
        materials[material_id] = (kind, material)
    if not materials:
        _fail(
            "corotational_portal_materials_missing",
            "/materials",
            "Explicit steel and concrete materials are required.",
        )

    sections: dict[str, StatefulRCFiberSection] = {}
    section_materials: dict[str, tuple[str, str]] = {}
    for index, row in enumerate(model.sections):
        path = f"/sections/{index}"
        _keys(row, _SECTION_KEYS, path)
        section_id = _stable(row["id"], f"{path}/id")
        if section_id in sections or row["type"] != "rectangular_rc_fiber_section":
            _fail(
                "corotational_portal_section_invalid",
                path,
                "Unique rectangular RC fiber sections are required.",
            )
        steel_id = _stable(row["steel_material"], f"{path}/steel_material")
        concrete_id = _stable(row["concrete_material"], f"{path}/concrete_material")
        steel = materials.get(steel_id)
        concrete = materials.get(concrete_id)
        if (
            steel is None
            or steel[0] != "steel"
            or concrete is None
            or concrete[0] != "concrete"
        ):
            _fail(
                "corotational_portal_section_material_invalid",
                path,
                "Section material references have the wrong type.",
            )
        assert steel is not None
        assert concrete is not None
        try:
            sections[section_id] = make_rectangular_stateful_rc_fiber_section(
                width_m=_positive(row["width_m"], f"{path}/width_m"),
                depth_m=_positive(row["depth_m"], f"{path}/depth_m"),
                cover_m=_positive(row["cover_m"], f"{path}/cover_m"),
                concrete_layer_count=_integer(
                    row["concrete_layer_count"], f"{path}/concrete_layer_count", 2, 32
                ),
                top_bar_count=_integer(
                    row["top_bar_count"], f"{path}/top_bar_count", 1, 64
                ),
                bottom_bar_count=_integer(
                    row["bottom_bar_count"], f"{path}/bottom_bar_count", 1, 64
                ),
                bar_area_m2=_positive(row["bar_area_m2"], f"{path}/bar_area_m2"),
                section_id=section_id,
                steel=steel[1],
                concrete=concrete[1],
            )
        except NonlinearFrameError:
            raise
        except ValueError as exc:
            _fail("corotational_portal_section_invalid", path, str(exc))
        section_materials[section_id] = (steel_id, concrete_id)
    if not sections:
        _fail(
            "corotational_portal_sections_missing",
            "/sections",
            "At least one explicit section is required.",
        )

    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    members: list[StatefulCorotationalFiberFrame2DMember] = []
    member_sections: list[StatefulRCFiberSection] = []
    member_ids: set[str] = set()
    used_sections: set[str] = set()
    if (not general_profile and len(model.elements) != 3) or (
        general_profile and not 1 <= len(model.elements) <= 256
    ):
        _fail(
            "corotational_portal_member_count_invalid",
            "/elements",
            (
                "The connected-frame profile requires 1-256 members."
                if general_profile
                else "Exactly three portal members are required."
            ),
        )
    for index, row in enumerate(model.elements):
        path = f"/elements/{index}"
        required_element_keys = {
            "id",
            "type",
            "nodes",
            "section",
            "integration_order",
        }
        optional_element_keys = {
            "end_releases",
            "local_axis",
            "rigid_offsets_global_m",
            "self_weight",
            "uniform_distributed_load_local",
        }
        allowed_optional_element_keys = (
            optional_element_keys if general_profile else set()
        )
        if (
            type(row) is not dict
            or not required_element_keys.issubset(row)
            or set(row) - required_element_keys - allowed_optional_element_keys
        ):
            _fail(
                "corotational_portal_row_keys_invalid",
                path,
                "Expected required element keys plus only the documented member-feature keys.",
            )
        member_id = _stable(row["id"], f"{path}/id")
        connectivity = row["nodes"]
        if (
            member_id in member_ids
            or row["type"] != "stateful_corotational_rc_fiber_frame2d"
            or type(connectivity) is not list
            or len(connectivity) != 2
        ):
            _fail(
                "corotational_portal_member_invalid",
                path,
                "Unique corotational two-node members are required.",
            )
        node_i_id, node_j_id = connectivity
        if (
            node_i_id not in node_index
            or node_j_id not in node_index
            or node_i_id == node_j_id
        ):
            _fail(
                "corotational_portal_connectivity_invalid",
                f"{path}/nodes",
                "Connectivity must reference two distinct nodes.",
            )
        section_id = _stable(row["section"], f"{path}/section")
        section = sections.get(section_id)
        if section is None:
            _fail(
                "corotational_portal_section_reference_invalid",
                f"{path}/section",
                "Member section is not declared.",
            )
        assert section is not None
        integration_order = _integer(
            row["integration_order"], f"{path}/integration_order", 2, 3
        )
        node_i = node_index[str(node_i_id)]
        node_j = node_index[str(node_j_id)]
        features = _corotational_member_features(
            row,
            path,
            node_i_coordinates_m=coordinates[node_i],
            node_j_coordinates_m=coordinates[node_j],
        )
        element_coordinates = element_end_coordinates_m(
            coordinates[node_i], coordinates[node_j], features
        )
        members.append(
            StatefulCorotationalFiberFrame2DMember(
                member_id=member_id,
                node_i=node_i,
                node_j=node_j,
                element=StatefulCorotationalFiberBeam2D(
                    node_coordinates_m=element_coordinates,
                    section=cast(AxialCurvatureSection, section),
                    integration_order=integration_order,
                    element_id=member_id,
                ),
                features=features,
            )
        )
        member_sections.append(section)
        member_ids.add(member_id)
        used_sections.add(section_id)

    if (not general_profile and len(model.supports) != 2) or (
        general_profile and not 1 <= len(model.supports) <= len(model.nodes)
    ):
        _fail(
            "corotational_portal_support_count_invalid",
            "/supports",
            (
                "The connected-frame profile requires one or more support nodes."
                if general_profile
                else "Both portal bases must be supported."
            ),
        )
    support_ids: list[str] = []
    fixed: list[int] = []
    prescribed: list[tuple[int, float]] = []
    for index, row in enumerate(model.supports):
        path = f"/supports/{index}"
        _keys(
            row,
            (
                {"node", "dofs", "prescribed_values"}
                if general_profile and "prescribed_values" in row
                else {"node", "dofs"}
            ),
            path,
        )
        node_id = _stable(row["node"], f"{path}/node")
        raw_dofs = row["dofs"]
        valid_general_dofs = bool(
            type(raw_dofs) is list
            and raw_dofs
            and all(type(value) is str for value in raw_dofs)
            and len(raw_dofs) == len(set(raw_dofs))
            and set(raw_dofs).issubset(set(_ACTIVE_COMPONENTS))
        )
        valid_portal_dofs = bool(
            type(raw_dofs) is list
            and all(type(value) is str for value in raw_dofs)
            and set(raw_dofs) == set(_ACTIVE_COMPONENTS)
        )
        if (
            node_id not in node_index
            or node_id in support_ids
            or (not valid_general_dofs if general_profile else not valid_portal_dofs)
        ):
            _fail(
                "corotational_portal_support_invalid",
                path,
                (
                    "Support DOFs must be a non-empty unique subset of UX, UY and RZ."
                    if general_profile
                    else "Two unique nodes must restrain exactly UX, UY and RZ."
                ),
            )
        support_ids.append(node_id)
        dof_offsets = {label: offset for offset, label in enumerate(_ACTIVE_COMPONENTS)}
        support_dofs = tuple(str(value) for value in raw_dofs)
        fixed.extend(
            3 * node_index[node_id] + dof_offsets[label] for label in support_dofs
        )
        raw_prescribed = row.get("prescribed_values", {})
        if type(raw_prescribed) is not dict or not set(raw_prescribed).issubset(
            set(support_dofs)
        ):
            _fail(
                "corotational_general_prescribed_displacement_invalid",
                f"{path}/prescribed_values",
                "Prescribed keys must be constrained UX, UY, or RZ components.",
            )
        prescribed.extend(
            (
                3 * node_index[node_id] + dof_offsets[label],
                _number(value, f"{path}/prescribed_values/{label}"),
            )
            for label, value in raw_prescribed.items()
        )

    reference_loads: list[tuple[int, float]] = []
    loaded_nodes: set[str] = set()
    for index, row in enumerate(model.loads):
        path = f"/loads/{index}"
        _keys(row, {"node", "components"}, path)
        node_id = _stable(row["node"], f"{path}/node")
        components = row["components"]
        if (
            node_id not in node_index
            or node_id in loaded_nodes
            or type(components) is not dict
            or set(components) != set(_LOAD_COMPONENTS)
        ):
            _fail(
                "corotational_portal_load_invalid",
                path,
                "Use one complete load row per declared node.",
            )
        values = {
            name: _number(components[name], f"{path}/components/{name}")
            for name in _LOAD_COMPONENTS
        }
        if (
            values["FZ"] != 0.0
            or values["MX"] != 0.0
            or values["MY"] != 0.0
            or not any(values[name] != 0.0 for name in ("FX", "FY", "MZ"))
        ):
            _fail(
                "corotational_portal_load_components_invalid",
                f"{path}/components",
                "Only a nonzero in-plane FX/FY/MZ load row is supported.",
            )
        base = 3 * node_index[node_id]
        reference_loads.extend(
            (base + offset, values[name])
            for offset, name in enumerate(("FX", "FY", "MZ"))
            if values[name] != 0.0
        )
        loaded_nodes.add(node_id)
    if (
        not reference_loads
        and not (general_profile and any(value != 0.0 for _dof, value in prescribed))
        and not any(member.features.has_distributed_load for member in members)
    ):
        _fail(
            "corotational_portal_loads_missing",
            "/loads",
            "At least one nonzero nodal load, prescribed displacement, or member distributed load is required.",
        )

    if used_sections != set(sections):
        _fail(
            "corotational_portal_unused_section",
            "/sections",
            "Every section must be used.",
        )
    used_materials = {
        material
        for section_id in used_sections
        for material in section_materials[section_id]
    }
    if used_materials != set(materials):
        _fail(
            "corotational_portal_unused_material",
            "/materials",
            "Every material must be used.",
        )
    lengths = [member.element.initial_length_m for member in members]
    digest = model.canonical_model_checksum.removeprefix("sha256:")[:20]
    try:
        problem = StatefulCorotationalFiberFrame2DProblem(
            case_id=(
                f"public_corotational_general_{digest}"
                if general_profile
                else f"public_corotational_portal_{digest}"
            ),
            node_coordinates_m=tuple(coordinates),
            members=tuple(members),
            fixed_global_dofs=tuple(sorted(fixed)),
            reference_external_loads=tuple(sorted(reference_loads)),
            rotation_coordinate_scale_m=_binary_coordinate_scale(max(lengths)),
            prescribed_displacements=tuple(sorted(prescribed)),
        )
        compilation = (
            compile_corotational_fiber_frame_general_profile(
                problem,
                model_content_hash=model.canonical_model_checksum,
            )
            if general_profile
            else compile_corotational_fiber_frame_portal_profile(
                problem,
                model_content_hash=model.canonical_model_checksum,
            )
        )
        model_ir_adapter_hash = _corotational_model_ir_adapter_hash(
            model=model,
            problem=problem,
            compilation=compilation,
            node_ids=tuple(node_ids),
        )
        topology_plan = compile_stateful_fiber_frame2d_execution_topology(
            problem,
            model_ir_content_hash=(
                source_model_ir_adapter.model_ir_content_hash
                if source_model_ir_adapter is not None
                else model_ir_adapter_hash
            ),
            node_ids=tuple(node_ids),
        )
        free_physical_dofs = topology_plan.array("free_physical_dofs")
        reference_load = topology_plan.array("reference_external_load_physical_6dof")
        has_free_reference_load = bool(
            free_physical_dofs.size
            and any(
                float(reference_load[int(dof)]) != 0.0 for dof in free_physical_dofs
            )
        )
        equation_scaling = (
            create_stateful_fiber_frame2d_physical_equation_scaling(
                problem,
                topology_plan,
            )
            if has_free_reference_load
            else None
        )
        bounded_execution_plan = (
            create_bounded_planar_execution_plan_binding(
                model_ir_adapter=source_model_ir_adapter,
                problem=problem,
                topology_plan=topology_plan,
                equation_scaling=equation_scaling,
            )
            if source_model_ir_adapter is not None
            else None
        )
    except (CorotationalFiberFrameGeneralError, CorotationalFiberFrameJ1J5Error):
        raise
    except ValueError as exc:
        _fail("corotational_portal_problem_invalid", "/", str(exc))
    return _CompiledPortal(
        problem=problem,
        compilation=compilation,
        node_ids=tuple(node_ids),
        section_by_member=tuple(member_sections),
        support_node_ids=tuple(support_ids),
        model_ir_adapter_hash=model_ir_adapter_hash,
        topology_plan=topology_plan,
        equation_scaling=equation_scaling,
        bounded_execution_plan=bounded_execution_plan,
    )


def _corotational_model_ir_adapter_hash(
    *,
    model: CanonicalModel,
    problem: StatefulCorotationalFiberFrame2DProblem,
    compilation: (
        CorotationalFiberFramePortalCompilation
        | CorotationalFiberFrameGeneralCompilation
    ),
    node_ids: tuple[str, ...],
) -> str:
    """Bind the canonical input to the bounded nonlinear topology source.

    This remains the fallback source identity for direct CanonicalModel calls.
    The bounded ModelIR entry point binds its actual content hash separately.
    """

    return canonical_hash(
        {
            "schema_version": "nonlinear-frame-model-ir-adapter.v1",
            "adapter_profile": "canonical_model_to_connected_frame2d_problem.v1",
            "source_schema_version": model.schema_version,
            "source_canonical_model_checksum": model.canonical_model_checksum,
            "source_input_checksum": model.input_checksum,
            "problem_contract_hash": problem.contract_hash,
            "compiler_hash": compilation.compiler_hash,
            "node_ids": list(node_ids),
            "member_ids": [member.member_id for member in problem.members],
            "member_feature_contract_hashes": [
                member.features.contract_hash for member in problem.members
            ],
            "solver_dof_components": list(_ACTIVE_COMPONENTS),
            "canonical_dof_components": ["UX", "UY", "UZ", "RX", "RY", "RZ"],
            "model_ir_v2_representation_claim": False,
            "claim_boundary": (
                "Profile-specific fail-closed adapter identity only; no general "
                "ModelIR v2 nonlinear-material representation authority."
            ),
        }
    )


def _corotational_plan_bindings(
    compiled: _CompiledPortal,
    terminal_trace: FiberFramePhysicalResidualTrace | None = None,
) -> dict[str, Any]:
    plan = compiled.topology_plan
    scaling = compiled.equation_scaling
    bindings: dict[str, Any] = {
        "problem_contract_hash": compiled.problem.contract_hash,
        "model_ir_adapter_hash": compiled.model_ir_adapter_hash,
        "nonlinear_execution_topology_plan_hash": plan.plan_hash,
        "dof_ordering_hash": plan.entity_mapping_hash,
        "topology_hash": plan.topology_hash,
        "solver_coordinate_scaling_hash": plan.solver_coordinate_scaling_hash,
    }
    if plan.model_ir_content_hash != compiled.model_ir_adapter_hash:
        bindings["topology_model_ir_content_hash"] = plan.model_ir_content_hash
    if compiled.bounded_execution_plan is not None:
        bindings["bounded_planar_execution_plan"] = (
            compiled.bounded_execution_plan.to_dict()
        )
    if scaling is not None:
        bindings.update(
            {
                "physical_equation_scaling_binding_hash": scaling.binding_hash,
                "engine_equation_scaling_hash": (scaling.engine_equation_scaling_hash),
                "equation_order_hash": scaling.equation_order_hash,
            }
        )
    if terminal_trace is not None:
        bindings["terminal_physical_residual_trace_hash"] = terminal_trace.trace_hash
    return bindings


def _run_corotational_path(
    compiled: _CompiledPortal,
    config: NonlinearFrameConfig,
    restart: bytes | bytearray | memoryview | None,
    *,
    maximum_new_steps: int | None = None,
) -> _CorotationalExecution:
    problem = compiled.problem
    targets = config.target_load_factors
    solver_config = NewtonRaphsonConfig(
        residual_tolerance=config.residual_tolerance,
        increment_tolerance=config.increment_tolerance_m,
        max_iterations=config.maximum_iterations,
        matrix_backend=config.matrix_backend,
    )

    def run_segment(
        segment_targets: tuple[float, ...],
        *,
        initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    ) -> StatefulCorotationalFiberFrame2DLoadPathResult:
        return run_stateful_corotational_fiber_frame2d_load_path(
            problem,
            segment_targets,
            initial_checkpoint=initial_checkpoint,
            config=solver_config,
        )

    replayed_prefix = 0
    if restart is None:
        segment_targets = (
            targets if maximum_new_steps is None else targets[:maximum_new_steps]
        )
        path = run_segment(segment_targets)
        newly_solved = len(path.steps)
    else:
        loaded = load_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
            restart, problem
        )
        prefix_count = len(loaded.checkpoints) - 1
        if prefix_count > len(targets):
            raise NonlinearFrameError(
                "corotational_restart_path_too_long",
                "/restart_checkpoint_chain",
                "Restart chain exceeds the configured load path.",
            )
        expected_prefix = targets[:prefix_count]
        actual_prefix = tuple(
            checkpoint.load_factor for checkpoint in loaded.checkpoints[1:]
        )
        if actual_prefix != expected_prefix:
            raise NonlinearFrameError(
                "corotational_restart_load_prefix_mismatch",
                "/restart_checkpoint_chain",
                "Restart loads are not the exact configured prefix.",
            )
        if prefix_count:
            prefix_path = run_segment(expected_prefix)
            replayed = (
                prefix_path.initial_checkpoint,
                *(step.accepted_checkpoint for step in prefix_path.steps),
            )
            if (
                prefix_path.status != "ready"
                or not prefix_path.contract_pass
                or any(
                    left.canonical_bytes() != right.canonical_bytes()
                    for left, right in zip(replayed, loaded.checkpoints, strict=True)
                )
            ):
                raise NonlinearFrameError(
                    "corotational_restart_exact_replay_mismatch",
                    "/restart_checkpoint_chain",
                    "Restart checkpoint bytes differ from deterministic replay.",
                )
        else:
            root = initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
            if root.canonical_bytes() != loaded.root_checkpoint.canonical_bytes():
                raise NonlinearFrameError(
                    "corotational_restart_root_mismatch",
                    "/restart_checkpoint_chain",
                    "Restart root differs from exact genesis.",
                )
            prefix_path = StatefulCorotationalFiberFrame2DLoadPathResult(
                status="ready",
                initial_checkpoint=root,
                final_checkpoint=root,
                steps=(),
            )
        replayed_prefix = prefix_count
        remaining = targets[prefix_count:]
        if maximum_new_steps is not None:
            remaining = remaining[:maximum_new_steps]
        if remaining:
            suffix = run_segment(
                remaining,
                initial_checkpoint=prefix_path.final_checkpoint,
            )
            path = StatefulCorotationalFiberFrame2DLoadPathResult(
                status=suffix.status,
                initial_checkpoint=prefix_path.initial_checkpoint,
                final_checkpoint=suffix.final_checkpoint,
                steps=prefix_path.steps + suffix.steps,
            )
            newly_solved = len(suffix.steps)
        else:
            path = prefix_path
            newly_solved = 0
    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps if step.committed),
    )
    chain = make_stateful_corotational_fiber_frame2d_checkpoint_chain(
        problem, checkpoints
    )
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_chain_bytes(
        problem, chain
    )
    return _CorotationalExecution(
        path=path,
        chain=chain,
        checkpoint_bytes=raw,
        restart_supplied=restart is not None,
        replayed_prefix_step_count=replayed_prefix,
        newly_solved_step_count=newly_solved,
    )


def _resume_contract_hash(
    compiled: _CompiledPortal, config: NonlinearFrameConfig
) -> str:
    return canonical_hash(
        {
            "schema_version": "nonlinear-frame-resume-contract.v1",
            "profile": config.profile,
            "model_content_hash": compiled.compilation.model_content_hash,
            "compiler_hash": compiled.compilation.compiler_hash,
            "problem_contract_hash": compiled.problem.contract_hash,
            "model_ir_adapter_hash": compiled.model_ir_adapter_hash,
            "nonlinear_execution_topology_plan_hash": (
                compiled.topology_plan.plan_hash
            ),
            "bounded_planar_execution_plan_hash": (
                compiled.bounded_execution_plan.binding_hash
                if compiled.bounded_execution_plan is not None
                else None
            ),
            **(
                {
                    "physical_equation_scaling_binding_hash": (
                        compiled.equation_scaling.binding_hash
                    ),
                    "engine_equation_scaling_hash": (
                        compiled.equation_scaling.engine_equation_scaling_hash
                    ),
                }
                if compiled.equation_scaling is not None
                else {
                    "equation_scaling_status": "unavailable",
                    "equation_scaling_reason": "no_free_reference_load",
                }
            ),
            "load_steps": config.load_steps,
            "target_load_factors": list(config.target_load_factors),
            "residual_tolerance": config.residual_tolerance,
            "increment_tolerance_m": config.increment_tolerance_m,
            "maximum_iterations": config.maximum_iterations,
            "matrix_backend": config.matrix_backend,
        }
    )


def _corotational_node_rows(
    compiled: _CompiledPortal,
    result: CorotationalFiberFrameEngineeringResultIR,
) -> tuple[Mapping[str, Any], ...]:
    translations = result.artifact("node_translation_m")
    rotations = result.artifact("node_rotation_rad")
    return tuple(
        {
            "node_id": node_id,
            "UX_m": float(translations[index, 0]),
            "UY_m": float(translations[index, 1]),
            "UZ_m": 0.0,
            "RX_rad": 0.0,
            "RY_rad": 0.0,
            "RZ_rad": float(rotations[index]),
        }
        for index, node_id in enumerate(compiled.node_ids)
    )


def _corotational_reaction_rows(
    compiled: _CompiledPortal,
    result: CorotationalFiberFrameEngineeringResultIR,
) -> tuple[Mapping[str, Any], ...]:
    forces = result.artifact("reaction_force_n")
    moments = result.artifact("reaction_moment_nm")
    rows: list[Mapping[str, Any]] = []
    fixed = set(compiled.problem.fixed_global_dofs)
    for node_id in compiled.support_node_ids:
        node = compiled.node_ids.index(node_id)
        candidates = (
            ("UX", float(forces[node, 0]), "N"),
            ("UY", float(forces[node, 1]), "N"),
            ("RZ", float(moments[node]), "N*m"),
        )
        rows.extend(
            {
                "node_id": node_id,
                "dof": dof,
                "value_si": value,
                "unit": unit,
            }
            for offset, (dof, value, unit) in enumerate(candidates)
            if 3 * node + offset in fixed
        )
    return tuple(rows)


def _corotational_member_rows(
    compiled: _CompiledPortal,
    result: CorotationalFiberFrameEngineeringResultIR,
) -> tuple[Mapping[str, Any], ...]:
    forces = result.artifact("member_end_force_n")
    moments = result.artifact("member_end_moment_nm")
    return tuple(
        {
            "member_id": member.member_id,
            "node_i": compiled.node_ids[member.node_i],
            "node_j": compiled.node_ids[member.node_j],
            "local_end_i": {
                "FX_N": float(forces[index, 0]),
                "FY_N": float(forces[index, 1]),
                "MZ_Nm": float(moments[index, 0]),
            },
            "local_end_j": {
                "FX_N": float(forces[index, 2]),
                "FY_N": float(forces[index, 3]),
                "MZ_Nm": float(moments[index, 1]),
            },
            "local_axis": "current_chord",
            "end_force_definition": (
                "element_internal_minus_scaled_consistent_member_dead_load"
            ),
            "member_feature_contract_hash": member.features.contract_hash,
            "member_features": member.features.to_dict(),
        }
        for index, member in enumerate(compiled.problem.members)
    )


def _corotational_section_rows(
    compiled: _CompiledPortal,
    result: CorotationalFiberFrameEngineeringResultIR,
) -> tuple[Mapping[str, Any], ...]:
    offsets = result.artifact("section_offsets")
    xi = result.artifact("section_xi")
    axial = result.artifact("section_axial_force_n")
    moment = result.artifact("section_moment_nm")
    strain = result.artifact("section_strain")
    curvature = result.artifact("section_curvature_per_m")
    rows: list[Mapping[str, Any]] = []
    for member_index, member in enumerate(compiled.problem.members):
        points, weights = member.element.basic_beam.quadrature
        start, stop = int(offsets[member_index]), int(offsets[member_index + 1])
        for local_index, flat in enumerate(range(start, stop)):
            rows.append(
                {
                    "member_id": member.member_id,
                    "integration_point_index": local_index,
                    "xi": float(xi[flat]),
                    "weight": float(weights[local_index]),
                    "axial_strain": float(strain[flat]),
                    "curvature_z_per_m": float(curvature[flat]),
                    "axial_force_N": float(axial[flat]),
                    "moment_z_Nm": float(moment[flat]),
                }
            )
        if len(points) != stop - start:
            raise ValueError("section output count differs from member quadrature")
    return tuple(rows)


def _corotational_fiber_rows(
    compiled: _CompiledPortal,
    result: CorotationalFiberFrameEngineeringResultIR,
) -> tuple[Mapping[str, Any], ...]:
    section_offsets = result.artifact("section_offsets")
    fiber_offsets = result.artifact("fiber_offsets")
    y = result.artifact("fiber_y_m")
    area = result.artifact("fiber_area_m2")
    strain = result.artifact("fiber_strain")
    stress = result.artifact("fiber_stress_pa")
    rows: list[Mapping[str, Any]] = []
    for member_index, member in enumerate(compiled.problem.members):
        section = compiled.section_by_member[member_index]
        for flat_section in range(
            int(section_offsets[member_index]), int(section_offsets[member_index + 1])
        ):
            local_ip = flat_section - int(section_offsets[member_index])
            start, stop = (
                int(fiber_offsets[flat_section]),
                int(fiber_offsets[flat_section + 1]),
            )
            for fiber_index, (flat_fiber, fiber) in enumerate(
                zip(range(start, stop), section.fibers, strict=True)
            ):
                rows.append(
                    {
                        "member_id": member.member_id,
                        "integration_point_index": local_ip,
                        "fiber_index": fiber_index,
                        "fiber_id": fiber.fiber_id,
                        "material_kind": fiber.material_kind,
                        "y_m": float(y[flat_fiber]),
                        "area_m2": float(area[flat_fiber]),
                        "strain": float(strain[flat_fiber]),
                        "stress_Pa": float(stress[flat_fiber]),
                    }
                )
    return tuple(rows)


def _normalize_fixed_fiber_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = dict(row)
    stress_mpa = normalized.pop("stress_MPa")
    normalized["stress_Pa"] = float(stress_mpa) * 1.0e6
    return normalized


def _make_result(
    *,
    status: Literal["ready", "blocked"],
    profile: NonlinearFrameProfile,
    source_result_hash: str | None,
    engineering_result_ir: Mapping[str, Any] | None,
    model: CanonicalModel,
    solver_id: str,
    compiler_profile: str,
    configuration: Mapping[str, Any],
    contract_bindings: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    authority: Mapping[str, str],
    node_displacements: tuple[Mapping[str, Any], ...],
    support_reactions: tuple[Mapping[str, Any], ...],
    member_end_forces: tuple[Mapping[str, Any], ...],
    section_results: tuple[Mapping[str, Any], ...],
    fiber_results: tuple[Mapping[str, Any], ...],
    convergence_history: tuple[Mapping[str, Any], ...],
    metrics: Mapping[str, Any],
    unsupported_features: tuple[Mapping[str, Any], ...],
    warnings: tuple[str, ...],
    checkpoint_bytes: bytes | None,
) -> NonlinearFrameResult:
    ready = status == "ready" and not unsupported_features
    provisional = NonlinearFrameResult(
        status="ready" if ready else "blocked",
        contract_pass=ready,
        result_hash=_HASH_ZERO,
        profile=profile,
        source_result_hash=source_result_hash,
        engineering_result_ir=(
            None
            if engineering_result_ir is None
            else cast(Mapping[str, Any], _freeze_json(engineering_result_ir))
        ),
        canonical_model_checksum=model.canonical_model_checksum,
        input_checksum=model.input_checksum,
        solver_id=solver_id,
        compiler_profile=compiler_profile,
        configuration=MappingProxyType(dict(configuration)),
        contract_bindings=MappingProxyType(dict(contract_bindings)),
        checkpoint=MappingProxyType(dict(checkpoint)),
        authority=MappingProxyType(dict(authority)),
        node_displacements=tuple(dict(row) for row in node_displacements),
        support_reactions=tuple(dict(row) for row in support_reactions),
        member_end_forces=tuple(dict(row) for row in member_end_forces),
        section_results=tuple(dict(row) for row in section_results),
        fiber_results=tuple(dict(row) for row in fiber_results),
        convergence_history=tuple(dict(row) for row in convergence_history),
        metrics=MappingProxyType(dict(metrics)),
        unsupported_features=tuple(
            _normalize_unsupported_feature(row, index=index)
            for index, row in enumerate(unsupported_features)
        ),
        warnings=tuple(str(row) for row in warnings),
        _checkpoint_bytes=checkpoint_bytes,
    )
    return replace(
        provisional,
        result_hash=canonical_hash(_result_payload(provisional, include_hash=False)),
    )


def _bind_source_model_ir_adapter(
    result: NonlinearFrameResult,
    adapter: BoundedPlanarModelIRAdapter,
) -> NonlinearFrameResult:
    if "source_model_ir_adapter" in result.contract_bindings:
        raise ValueError("unified result already has a source ModelIR adapter binding")
    receipt = adapter.to_dict()
    validate_bounded_planar_model_ir_adapter_manifest(receipt)
    provisional = replace(
        result,
        result_hash=_HASH_ZERO,
        contract_bindings=MappingProxyType(
            {
                **dict(result.contract_bindings),
                "source_model_ir_adapter": receipt,
            }
        ),
    )
    bound = replace(
        provisional,
        result_hash=canonical_hash(_result_payload(provisional, include_hash=False)),
    )
    validate_nonlinear_frame_result(bound)
    return bound


def _validate_source_model_ir_adapter_binding(
    *,
    profile: NonlinearFrameProfile,
    input_checksum: str,
    canonical_model_checksum: str,
    contract_bindings: Mapping[str, Any],
) -> None:
    raw = contract_bindings.get("source_model_ir_adapter")
    if raw is None:
        return
    if not isinstance(raw, Mapping):
        raise ValueError("source ModelIR adapter binding must be an object")
    receipt = validate_bounded_planar_model_ir_adapter_manifest(raw)
    if profile != COROTATIONAL_GENERAL_PROFILE:
        raise ValueError(
            "source ModelIR adapter requires the connected Frame2D profile"
        )
    if input_checksum != receipt["model_ir_content_hash"]:
        raise ValueError("unified input checksum differs from source ModelIR content")
    if canonical_model_checksum != receipt["canonical_model_checksum"]:
        raise ValueError("unified canonical model differs from ModelIR adapter target")
    if (
        contract_bindings.get("topology_model_ir_content_hash")
        != receipt["model_ir_content_hash"]
    ):
        raise ValueError("nonlinear topology plan differs from source ModelIR content")
    raw_plan = contract_bindings.get("bounded_planar_execution_plan")
    if not isinstance(raw_plan, Mapping):
        raise ValueError("source ModelIR result requires a bounded execution plan")
    plan = validate_bounded_planar_execution_plan_manifest(raw_plan)
    for plan_key, receipt_key in (
        ("model_ir_content_hash", "model_ir_content_hash"),
        ("model_ir_semantic_hash", "model_ir_semantic_hash"),
        ("model_ir_provenance_hash", "model_ir_provenance_hash"),
        ("model_ir_adapter_hash", "adapter_hash"),
        ("canonical_model_checksum", "canonical_model_checksum"),
        ("load_pattern_id", "load_pattern_id"),
    ):
        if plan[plan_key] != receipt[receipt_key]:
            raise ValueError(
                f"bounded execution plan {plan_key} differs from ModelIR adapter"
            )
    for binding_key, plan_key in (
        ("problem_contract_hash", "problem_contract_hash"),
        ("nonlinear_execution_topology_plan_hash", "topology_plan_hash"),
        ("dof_ordering_hash", "entity_mapping_hash"),
        ("topology_hash", "topology_hash"),
        ("solver_coordinate_scaling_hash", "solver_coordinate_scaling_hash"),
    ):
        if contract_bindings.get(binding_key) != plan[plan_key]:
            raise ValueError(
                f"unified {binding_key} differs from bounded execution plan"
            )
    if plan["equation_scaling_status"] == "available":
        for binding_key, plan_key in (
            (
                "physical_equation_scaling_binding_hash",
                "physical_equation_scaling_binding_hash",
            ),
            ("engine_equation_scaling_hash", "engine_equation_scaling_hash"),
            ("equation_order_hash", "equation_order_hash"),
        ):
            if contract_bindings.get(binding_key) != plan[plan_key]:
                raise ValueError(
                    f"unified {binding_key} differs from bounded execution plan"
                )


def _normalize_unsupported_feature(
    row: Mapping[str, Any],
    *,
    index: int,
    source_model: bool = False,
) -> dict[str, Any]:
    """Project blockers onto the stable public unsupported contract.

    ``kind`` remains the detailed diagnostic identifier. ``reason_code`` is the
    deliberately small routing vocabulary consumed by public callers. Source
    diagnostics may carry arbitrary metadata, so fields outside the public
    contract are retained under ``source_context`` rather than silently lost.
    """

    source = dict(row)
    raw_kind = source.get("kind")
    if isinstance(raw_kind, str) and re.fullmatch(r"[a-z][a-z0-9_]{2,127}", raw_kind):
        kind = raw_kind
    else:
        kind = (
            "canonical_model_unsupported_feature_invalid"
            if source_model
            else "corotational_unsupported_feature_invalid"
        )

    raw_path = source.get("path")
    path = (
        raw_path
        if isinstance(raw_path, str) and raw_path.startswith("/")
        else f"/unsupported_features/{index}"
        if source_model
        else "/solver"
    )
    raw_detail = source.get("detail")
    detail = (
        raw_detail.strip()
        if isinstance(raw_detail, str) and raw_detail.strip()
        else f"{kind}@{path}: Unsupported feature reported without detail."
    )

    supplied_reason = source.get("reason_code")
    reason_code = (
        supplied_reason
        if isinstance(supplied_reason, str)
        and supplied_reason in UNIFIED_NONLINEAR_FRAME_UNSUPPORTED_REASON_CODES
        else _unsupported_reason_code(kind, path, source_model=source_model)
    )
    normalized: dict[str, Any] = {
        "reason_code": reason_code,
        "kind": kind,
        "path": path,
        "detail": detail,
    }
    existing_context = source.get("source_context")
    source_context = (
        {str(key): _thaw_json(value) for key, value in existing_context.items()}
        if isinstance(existing_context, Mapping)
        else {}
    )
    source_context.update(
        {
            str(key): _thaw_json(value)
            for key, value in source.items()
            if key not in {"reason_code", "kind", "path", "detail", "source_context"}
        }
    )
    if source_context:
        normalized["source_context"] = source_context
    return normalized


def _unsupported_reason_code(
    kind: str,
    path: str,
    *,
    source_model: bool,
) -> str:
    if source_model:
        return "source_model_unsupported"
    if kind == "corotational_equation_scaling_unavailable":
        return "equation_scaling_unavailable"
    if kind == "corotational_released_mechanism_detected":
        return "mechanism_detected"
    if kind == "corotational_singular_system_detected":
        return "singular_system_detected"
    if kind == "corotational_rigid_body_constraint_rank_deficient":
        return "singular_system_detected"
    if kind.startswith("corotational_restart_") or path.startswith(
        "/restart_checkpoint_chain"
    ):
        return "restart_artifact_invalid"
    if kind.endswith(("_execution_failed", "_solver_blocked")):
        return "solver_execution_failed"
    if "_unsupported" in kind or kind.startswith("corotational_member_"):
        return "profile_feature_unsupported"
    return "input_contract_unsupported"


def _blocked_authority() -> Mapping[str, str]:
    return MappingProxyType(
        {
            "convergence": "not_authoritative",
            "displacement": "not_authoritative",
            "reaction": "not_authoritative",
            "member_force": "not_authoritative",
            "member_features": "not_authoritative",
            "section_resultant": "not_authoritative",
            "fiber_result": "not_authoritative",
            "fallback": "not_authoritative",
            "public_api": "not_promoted",
            "external_vv": "not_attached",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        }
    )


def _result_payload(
    result: NonlinearFrameResult, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": UNIFIED_NONLINEAR_FRAME_SCHEMA_VERSION,
        "status": result.status,
        "contract_pass": result.contract_pass,
        "profile": result.profile,
        "source_result_hash": result.source_result_hash,
        "engineering_result_ir": (
            _thaw_json(result.engineering_result_ir)
            if result.engineering_result_ir is not None
            else None
        ),
        "canonical_model_checksum": result.canonical_model_checksum,
        "input_checksum": result.input_checksum,
        "solver_id": result.solver_id,
        "compiler_profile": result.compiler_profile,
        "configuration": dict(result.configuration),
        "contract_bindings": dict(result.contract_bindings),
        "checkpoint": dict(result.checkpoint),
        "authority": dict(result.authority),
        "node_displacements": [dict(row) for row in result.node_displacements],
        "support_reactions": [dict(row) for row in result.support_reactions],
        "member_end_forces": [dict(row) for row in result.member_end_forces],
        "section_results": [dict(row) for row in result.section_results],
        "fiber_results": [dict(row) for row in result.fiber_results],
        "convergence_history": [dict(row) for row in result.convergence_history],
        "metrics": dict(result.metrics),
        "unsupported_features": [dict(row) for row in result.unsupported_features],
        "warnings": list(result.warnings),
        "claim_boundary": result.claim_boundary,
    }
    if include_hash:
        payload["result_hash"] = result.result_hash
    return payload


def _validate_engineering_result_ir_binding(
    *,
    profile: NonlinearFrameProfile,
    status: Literal["ready", "blocked"],
    source_result_hash: str | None,
    engineering_result_ir: Mapping[str, Any] | None,
    contract_bindings: Mapping[str, Any],
    authority: Mapping[str, str],
) -> None:
    if profile == FIXED_CHORD_SERIAL_PROFILE:
        if engineering_result_ir is not None:
            raise ValueError(
                "fixed-chord result must not invent a corotational engineering ResultIR"
            )
        return
    if status == "blocked":
        if engineering_result_ir is not None:
            raise ValueError("blocked result must not expose an engineering ResultIR")
        return
    if engineering_result_ir is None:
        raise ValueError("ready corotational result requires an engineering ResultIR")
    manifest = validate_corotational_fiber_frame_engineering_result_manifest(
        cast(Mapping[str, Any], _thaw_json(engineering_result_ir))
    )
    engineering_hash = manifest["engineering_result_hash"]
    if (
        source_result_hash != engineering_hash
        or contract_bindings.get("engineering_result_hash") != engineering_hash
        or contract_bindings.get("engineering_array_bundle_hash")
        != manifest["array_bundle_hash"]
        or contract_bindings.get("quantity_catalog_hash")
        != manifest["quantity_catalog_hash"]
    ):
        raise ValueError(
            "engineering ResultIR differs from unified result contract bindings"
        )
    expected_kind = (
        "corotational_connected_frame2d_reaction_member_section_fiber"
        if profile == COROTATIONAL_GENERAL_PROFILE
        else "corotational_portal_reaction_member_section_fiber"
    )
    if manifest["result_kind"] != expected_kind:
        raise ValueError("engineering ResultIR profile differs from unified profile")
    for axis in (
        "convergence",
        "displacement",
        "reaction",
        "member_force",
        "member_features",
        "section_resultant",
        "fiber_result",
        "fallback",
        "external_vv",
        "engineering_design",
        "release_readiness",
    ):
        if authority.get(axis) != manifest["authority_axes"].get(axis):
            raise ValueError(f"engineering ResultIR authority axis differs: {axis}")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise ValueError("engineering ResultIR must contain only finite JSON values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _artifact_hash(data: bytes | bytearray | memoryview) -> str:
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


def _corotational_linear_solver_metrics(
    execution: _CorotationalExecution | None,
    *,
    matrix_backend: str,
) -> dict[str, Any]:
    steps = execution.path.steps if execution is not None else ()
    sparse_selected = matrix_backend == VECTOR_SPARSE_MATRIX_BACKEND
    factorization_count = sum(
        int(step.metrics.get("sparse_factorization_count", 0)) for step in steps
    )
    diagnostic_hashes = [
        diagnostic_hash
        for step in steps
        for diagnostic_hash in step.metrics.get(
            "sparse_factorization_diagnostic_hashes", ()
        )
    ]
    policy_hashes = {
        str(step.metrics["sparse_factorization_policy_hash"])
        for step in steps
        if step.metrics.get("sparse_factorization_policy_hash") is not None
    }
    solver_executed = bool(
        steps
        and any(
            step.trial_solution.metrics.get("solver_executed") is True for step in steps
        )
    )
    no_solve_contract = bool(
        steps
        and all(step.metrics.get("no_solve_contract_pass") is True for step in steps)
    )
    return {
        "solver_executed": solver_executed,
        "no_solve_contract_pass": no_solve_contract,
        "fallback_count": sum(
            int(bool(step.metrics.get("fallback_used"))) for step in steps
        ),
        "regularization_count": sum(
            int(bool(step.metrics.get("regularization_used"))) for step in steps
        ),
        "sparse_backend_used": bool(
            sparse_selected
            and steps
            and all(bool(step.metrics.get("sparse_backend_used")) for step in steps)
        ),
        "native_sparse_assembly_used": bool(
            sparse_selected
            and steps
            and all(
                bool(step.metrics.get("native_sparse_assembly_used")) for step in steps
            )
        ),
        "sparse_factorization_count": factorization_count,
        "sparse_factorization_diagnostics_passed": (
            bool(
                factorization_count > 0
                and len(diagnostic_hashes) == factorization_count
                and all(
                    step.metrics.get("sparse_factorization_diagnostics_passed") is True
                    for step in steps
                )
            )
            if sparse_selected and steps
            else None
        ),
        "sparse_factorization_max_condition_number_1": _optional_max(
            step.metrics.get("sparse_factorization_max_condition_number_1")
            for step in steps
        ),
        "sparse_factorization_min_normalized_absolute_pivot": _optional_min(
            step.metrics.get("sparse_factorization_min_normalized_absolute_pivot")
            for step in steps
        ),
        "sparse_factorization_max_backward_error": _optional_max(
            step.metrics.get("sparse_factorization_max_backward_error")
            for step in steps
        ),
        "sparse_factorization_diagnostic_hashes": diagnostic_hashes,
        "sparse_factorization_policy_hash": (
            next(iter(policy_hashes)) if len(policy_hashes) == 1 else None
        ),
    }


def _optional_max(values: Any) -> float | None:
    normalized = [float(value) for value in values if value is not None]
    return max(normalized) if normalized else None


def _optional_min(values: Any) -> float | None:
    normalized = [float(value) for value in values if value is not None]
    return min(normalized) if normalized else None


def _binary_coordinate_scale(maximum_member_length_m: float) -> float:
    """Choose a power-of-two scale so checkpoint replay is bit-reversible."""

    length = float(maximum_member_length_m)
    mantissa, exponent = math.frexp(length)
    return math.ldexp(1.0, exponent - 1 if mantissa == 0.5 else exponent)


@lru_cache(maxsize=1)
def _result_schema_validator() -> Draft202012Validator:
    path = (
        resources.files("structural_analysis")
        .joinpath("schemas")
        .joinpath("unified_nonlinear_frame_result_v1.schema.json")
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise TypeError("Packaged unified nonlinear frame schema must be an object.")
    return Draft202012Validator(schema)


def _validate_result_schema(payload: Mapping[str, Any]) -> None:
    errors = sorted(
        _result_schema_validator().iter_errors(dict(payload)),
        key=lambda row: list(row.path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        raise ValueError(
            f"unified nonlinear result schema invalid at {path}: {first.message}"
        )


def _keys(row: Any, expected: set[str], path: str) -> None:
    if type(row) is not dict or set(row) != expected:
        _fail(
            "corotational_portal_row_keys_invalid",
            path,
            f"Expected exact keys {sorted(expected)}.",
        )


def _corotational_member_features(
    row: Mapping[str, Any],
    path: str,
    *,
    node_i_coordinates_m: tuple[float, float],
    node_j_coordinates_m: tuple[float, float],
) -> CorotationalFrame2DMemberFeatures:
    raw_offsets = row.get(
        "rigid_offsets_global_m",
        {"i": [0.0, 0.0], "j": [0.0, 0.0]},
    )
    if type(raw_offsets) is not dict or set(raw_offsets) != {"i", "j"}:
        _fail(
            "corotational_member_rigid_offset_invalid",
            f"{path}/rigid_offsets_global_m",
            "Rigid offsets require exact i and j global XY vectors.",
        )
    offsets: dict[str, tuple[float, float]] = {}
    for end in ("i", "j"):
        raw_vector = raw_offsets[end]
        if type(raw_vector) is not list or len(raw_vector) != 2:
            _fail(
                "corotational_member_rigid_offset_invalid",
                f"{path}/rigid_offsets_global_m/{end}",
                "Each rigid offset must be a two-value global XY vector in metres.",
            )
        offsets[end] = (
            _number(raw_vector[0], f"{path}/rigid_offsets_global_m/{end}/0"),
            _number(raw_vector[1], f"{path}/rigid_offsets_global_m/{end}/1"),
        )

    element_i = np.asarray(node_i_coordinates_m, dtype=np.float64) + np.asarray(
        offsets["i"], dtype=np.float64
    )
    element_j = np.asarray(node_j_coordinates_m, dtype=np.float64) + np.asarray(
        offsets["j"], dtype=np.float64
    )
    chord = element_j - element_i
    length = float(np.linalg.norm(chord))
    if not math.isfinite(length) or length <= 0.0:
        _fail(
            "corotational_member_rigid_offset_invalid",
            f"{path}/rigid_offsets_global_m",
            "Rigid offsets must preserve a positive finite element length.",
        )
    chord_x = (float(chord[0] / length), float(chord[1] / length))
    chord_y = (-chord_x[1], chord_x[0])

    raw_axis = row.get("local_axis")
    local_axis_explicit = raw_axis is not None
    if raw_axis is None:
        local_x_axis = chord_x
        local_y_axis = chord_y
    else:
        if type(raw_axis) is not dict or set(raw_axis) != {
            "x_axis_global",
            "y_axis_global",
        }:
            _fail(
                "corotational_member_local_axis_invalid",
                f"{path}/local_axis",
                "Local axis requires exact x_axis_global and y_axis_global XY vectors.",
            )
        parsed_axes: dict[str, tuple[float, float]] = {}
        for name in ("x_axis_global", "y_axis_global"):
            raw_vector = raw_axis[name]
            if type(raw_vector) is not list or len(raw_vector) != 2:
                _fail(
                    "corotational_member_local_axis_invalid",
                    f"{path}/local_axis/{name}",
                    "Each local axis must be a two-value global XY vector.",
                )
            parsed_axes[name] = (
                _number(raw_vector[0], f"{path}/local_axis/{name}/0"),
                _number(raw_vector[1], f"{path}/local_axis/{name}/1"),
            )
        local_x_axis = parsed_axes["x_axis_global"]
        local_y_axis = parsed_axes["y_axis_global"]
        if not np.allclose(
            local_x_axis, chord_x, rtol=0.0, atol=1.0e-12
        ) or not np.allclose(
            local_y_axis,
            chord_y,
            rtol=0.0,
            atol=1.0e-12,
        ):
            _fail(
                "corotational_member_local_axis_invalid",
                f"{path}/local_axis",
                "The bounded v1 local axes must match the offset-adjusted chord and right-handed normal.",
            )

    raw_releases = row.get("end_releases", {"i": [], "j": []})
    if type(raw_releases) is not dict or set(raw_releases) != {"i", "j"}:
        _fail(
            "corotational_member_end_release_invalid",
            f"{path}/end_releases",
            "End releases require exact i and j component lists.",
        )
    releases: dict[str, bool] = {}
    for end in ("i", "j"):
        raw_components = raw_releases[end]
        if (
            type(raw_components) is not list
            or len(raw_components) != len(set(raw_components))
            or any(type(value) is not str for value in raw_components)
            or not set(raw_components).issubset({"RZ"})
        ):
            _fail(
                "corotational_member_end_release_invalid",
                f"{path}/end_releases/{end}",
                "The v1 planar member supports only an optional RZ end release.",
            )
        releases[end] = "RZ" in raw_components

    raw_load = row.get(
        "uniform_distributed_load_local",
        {
            "basis": "initial_member_local",
            "behavior": "dead",
            "qx_kN_per_m": 0.0,
            "qy_kN_per_m": 0.0,
        },
    )
    if (
        type(raw_load) is not dict
        or set(raw_load) != {"basis", "behavior", "qx_kN_per_m", "qy_kN_per_m"}
        or raw_load["basis"] != "initial_member_local"
        or raw_load["behavior"] != "dead"
    ):
        _fail(
            "corotational_member_distributed_load_invalid",
            f"{path}/uniform_distributed_load_local",
            "The v1 load must be uniform, dead, and expressed in initial member local axes.",
        )
    raw_self_weight = row.get("self_weight")
    if raw_self_weight is None:
        self_weight_local = (0.0, 0.0)
        self_weight_mass = None
        self_weight_gravity = None
    else:
        if type(raw_self_weight) is not dict or set(raw_self_weight) != {
            "mass_per_length_kg_per_m",
            "gravity_global_m_per_s2",
        }:
            _fail(
                "corotational_member_self_weight_invalid",
                f"{path}/self_weight",
                "Self-weight requires exact SI mass-per-length and global gravity fields.",
            )
        raw_gravity = raw_self_weight["gravity_global_m_per_s2"]
        if type(raw_gravity) is not list or len(raw_gravity) != 2:
            _fail(
                "corotational_member_self_weight_invalid",
                f"{path}/self_weight/gravity_global_m_per_s2",
                "Self-weight gravity must be a two-value global XY vector.",
            )
        self_weight_mass = _positive(
            raw_self_weight["mass_per_length_kg_per_m"],
            f"{path}/self_weight/mass_per_length_kg_per_m",
        )
        self_weight_gravity = (
            _number(
                raw_gravity[0],
                f"{path}/self_weight/gravity_global_m_per_s2/0",
            ),
            _number(
                raw_gravity[1],
                f"{path}/self_weight/gravity_global_m_per_s2/1",
            ),
        )
        gravity = np.asarray(self_weight_gravity, dtype=np.float64)
        if not np.any(gravity != 0.0):
            _fail(
                "corotational_member_self_weight_invalid",
                f"{path}/self_weight/gravity_global_m_per_s2",
                "Self-weight gravity must be nonzero.",
            )
        global_weight_kn_per_m = self_weight_mass * gravity / 1000.0
        self_weight_local = (
            float(global_weight_kn_per_m @ np.asarray(local_x_axis)),
            float(global_weight_kn_per_m @ np.asarray(local_y_axis)),
        )
    try:
        return CorotationalFrame2DMemberFeatures(
            offset_i_global_m=offsets["i"],
            offset_j_global_m=offsets["j"],
            release_i_rz=releases["i"],
            release_j_rz=releases["j"],
            uniform_load_local_kn_per_m=(
                _number(
                    raw_load["qx_kN_per_m"],
                    f"{path}/uniform_distributed_load_local/qx_kN_per_m",
                ),
                _number(
                    raw_load["qy_kN_per_m"],
                    f"{path}/uniform_distributed_load_local/qy_kN_per_m",
                ),
            ),
            local_x_axis_global=local_x_axis,
            local_y_axis_global=local_y_axis,
            local_axis_explicit=local_axis_explicit,
            self_weight_local_kn_per_m=self_weight_local,
            self_weight_mass_per_length_kg_per_m=self_weight_mass,
            self_weight_gravity_global_m_per_s2=self_weight_gravity,
        )
    except NonlinearFrameError:
        raise
    except ValueError as exc:
        _fail("corotational_member_features_invalid", path, str(exc))


def _stable(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID.fullmatch(value) is None:
        _fail(
            "corotational_portal_stable_id_invalid",
            path,
            "Expected a stable ASCII identifier.",
        )
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(
            "corotational_portal_number_invalid", path, "Expected a finite JSON number."
        )
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail(
            "corotational_portal_number_invalid", path, "Expected a finite JSON number."
        )
    return normalized


def _positive(value: Any, path: str) -> float:
    normalized = _number(value, path)
    if normalized <= 0.0:
        _fail(
            "corotational_portal_number_not_positive",
            path,
            "Expected a positive number.",
        )
    return normalized


def _nonnegative(value: Any, path: str) -> float:
    normalized = _number(value, path)
    if normalized < 0.0:
        _fail(
            "corotational_portal_number_negative",
            path,
            "Expected a non-negative number.",
        )
    return normalized


def _integer(value: Any, path: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(
            "corotational_portal_integer_out_of_range",
            path,
            f"Expected an integer in [{minimum}, {maximum}].",
        )
    return value


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise NonlinearFrameError(code, path, detail)


__all__ = [
    "COROTATIONAL_GENERAL_PROFILE",
    "COROTATIONAL_PORTAL_PROFILE",
    "FIXED_CHORD_SERIAL_PROFILE",
    "UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY",
    "UNIFIED_NONLINEAR_FRAME_REPORT_SCHEMA_VERSION",
    "UNIFIED_NONLINEAR_FRAME_SCHEMA_VERSION",
    "UNIFIED_NONLINEAR_FRAME_UNSUPPORTED_REASON_CODES",
    "NonlinearFrameConfig",
    "NonlinearFrameCheckpointAdvance",
    "NonlinearFrameError",
    "NonlinearFrameProfile",
    "NonlinearFrameResult",
    "NonlinearFrameValidationReport",
    "analyze_nonlinear_frame",
    "analyze_nonlinear_frame_model_ir",
    "advance_nonlinear_frame_checkpoint",
    "advance_nonlinear_frame_model_ir_checkpoint",
    "nonlinear_frame_model_ir_resume_contract_hash",
    "nonlinear_frame_resume_contract_hash",
    "validate_nonlinear_frame_manifest",
    "validate_nonlinear_frame_result",
]
