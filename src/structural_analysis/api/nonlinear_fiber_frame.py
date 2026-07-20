"""Public bounded stateful RC fiber-frame API.

The compiler accepts one deliberately narrow planar serial-cantilever profile.
Every accepted final result is produced through the existing J1--J5 source
chain and the exact source-specific engineering recovery operator.  General
frame topology and unsupported model semantics fail closed before solve.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import re
from typing import Any, Mapping

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DMember,
    StatefulFiberFrame2DProblem,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    StatefulFiberFrame2DCheckpointChain,
    StatefulFiberFrame2DCheckpointChainArtifactError,
    dump_stateful_fiber_frame2d_checkpoint_chain_bytes,
    load_stateful_fiber_frame2d_checkpoint_chain_bytes,
    make_stateful_fiber_frame2d_checkpoint_chain,
    stateful_fiber_frame2d_checkpoint_chain_artifact_hash,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    create_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    create_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    create_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_recovery import (
    FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES,
    FiberFrameNonlinearEngineeringResultIR,
    create_fiber_frame_nonlinear_engineering_result_ir,
    create_fiber_frame_nonlinear_recovery_operator,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    FiberFrameNonlinearNumericalResultAdapter,
    create_fiber_frame_nonlinear_numerical_result_adapter,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    create_fiber_frame_nonlinear_terminal_receipt,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
    run_stateful_fiber_frame2d_load_path,
)
from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
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
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


PUBLIC_RC_FIBER_FRAME_SCHEMA_VERSION = "public-rc-fiber-frame-result.v1"
PUBLIC_RC_FIBER_FRAME_REPORT_SCHEMA_VERSION = (
    "public-rc-fiber-frame-validation-report.v1"
)
PUBLIC_RC_FIBER_FRAME_SOLVER_ID = "public_cpu_stateful_rc_fiber_frame_newton_v1"
PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE = (
    "planar_serial_cantilever_explicit_rectangular_rc.v1"
)
PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY = (
    "This public Developer Preview path accepts only one XY-plane serial "
    "cantilever chain with a single fully fixed endpoint, UX/UY/RZ activity, "
    "explicit rectangular RC fiber sections, supported one-dimensional steel "
    "and concrete profiles, zero prescribed displacement, proportional nodal "
    "loading, and dense CPU reference Newton load control. Ready results replay "
    "the complete J1-J5 source chain and exact terminal engineering recovery. "
    "It does not establish arbitrary or branched frame topology, geometric "
    "nonlinearity, releases, offsets, diaphragms, distributed loads, nonzero "
    "prescribed movement, arc length, shear deformation, sparse/HIP parity, "
    "design-code checks, final-design approval, commercial readiness, or G1 "
    "closure."
)

_MAX_NODES = 16
_MAX_MATERIALS = 32
_MAX_SECTIONS = 16
_MAX_LOAD_ROWS = 16
_MAX_CONCRETE_LAYERS = 32
_MAX_BARS_PER_LAYER = 64
_MAX_LOAD_STEPS = 64
_STABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ACTIVE_COMPONENTS = ("UX", "UY", "RZ")
_LOAD_COMPONENTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
_ACTIVE_TO_CANONICAL = {"UX": 0, "UY": 1, "RZ": 5}

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


class _PublicRCFiberFrameCompileError(ValueError):
    def __init__(self, kind: str, path: str, detail: str) -> None:
        self.kind = kind
        self.path = path
        self.detail = detail
        super().__init__(f"{kind}@{path}: {detail}")

    def to_blocker(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class PublicRCFiberFrameConfig:
    load_steps: int = 4
    residual_tolerance: float = 1.0e-10
    increment_tolerance_m: float = 1.0e-12
    maximum_iterations: int = 40

    def __post_init__(self) -> None:
        if (
            type(self.load_steps) is not int
            or self.load_steps < 2
            or self.load_steps > _MAX_LOAD_STEPS
        ):
            raise ValueError(f"load_steps must be an integer in [2, {_MAX_LOAD_STEPS}]")
        if (
            type(self.maximum_iterations) is not int
            or self.maximum_iterations < 1
            or self.maximum_iterations > 200
        ):
            raise ValueError("maximum_iterations must be an integer in [1, 200]")
        for name in ("residual_tolerance", "increment_tolerance_m"):
            object.__setattr__(
                self,
                name,
                _positive_config_number(getattr(self, name), name),
            )

    @property
    def target_load_factors(self) -> tuple[float, ...]:
        return tuple(step / self.load_steps for step in range(1, self.load_steps + 1))


@dataclass(frozen=True)
class PublicRCFiberFrameResult:
    status: str
    contract_pass: bool
    result_hash: str
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
    claim_boundary: str = PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY
    _problem: StatefulFiberFrame2DProblem | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _checkpoint_chain: StatefulFiberFrame2DCheckpointChain | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def checkpoint_artifact(self, epoch: int | None = None) -> bytes:
        """Return exact canonical checkpoint-chain bytes through ``epoch``."""

        if self._problem is None or self._checkpoint_chain is None:
            raise ValueError("no checkpoint artifact is available for this result")
        terminal_epoch = self._checkpoint_chain.terminal_checkpoint.epoch
        selected = terminal_epoch if epoch is None else epoch
        if type(selected) is not int or selected < 0 or selected > terminal_epoch:
            raise ValueError(f"epoch must be an integer in [0, {terminal_epoch}]")
        chain = make_stateful_fiber_frame2d_checkpoint_chain(
            self._problem,
            self._checkpoint_chain.checkpoints[: selected + 1],
        )
        return dump_stateful_fiber_frame2d_checkpoint_chain_bytes(
            self._problem,
            chain,
        )

    def to_dict(self) -> dict[str, Any]:
        return _public_result_payload(self, include_hash=True)


@dataclass(frozen=True)
class PublicRCFiberFrameValidationReport:
    status: str
    contract_pass: bool
    result_hash: str
    exact_engineering_recovery: bool
    checkpoint_available: bool
    terminal_epoch: int | None
    terminal_load_factor: float | None
    unsupported_feature_count: int
    warning_count: int
    fallback_count: int
    regularization_count: int
    claim_boundary: str = PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_RC_FIBER_FRAME_REPORT_SCHEMA_VERSION,
            "status": self.status,
            "contract_pass": self.contract_pass,
            "result_hash": self.result_hash,
            "exact_engineering_recovery": self.exact_engineering_recovery,
            "checkpoint_available": self.checkpoint_available,
            "terminal_epoch": self.terminal_epoch,
            "terminal_load_factor": self.terminal_load_factor,
            "unsupported_feature_count": self.unsupported_feature_count,
            "warning_count": self.warning_count,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class _CompiledPublicRCFiberFrame:
    problem: StatefulFiberFrame2DProblem
    node_ids: tuple[str, ...]
    section_by_member: tuple[StatefulRCFiberSection, ...]
    support_node_id: str


@dataclass(frozen=True)
class _ExecutionArtifacts:
    path: StatefulFiberFrame2DLoadPathResult
    checkpoint_chain: StatefulFiberFrame2DCheckpointChain
    checkpoint_bytes: bytes
    restart_supplied: bool
    replayed_prefix_step_count: int
    newly_solved_step_count: int


@dataclass(frozen=True)
class _AuthorityArtifacts:
    adapter: FiberFrameNonlinearNumericalResultAdapter
    engineering_result: FiberFrameNonlinearEngineeringResultIR


def analyze_public_rc_fiber_frame(
    model: CanonicalModel,
    config: PublicRCFiberFrameConfig | None = None,
    *,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None = None,
) -> PublicRCFiberFrameResult:
    """Compile, solve, replay, and recover the exact bounded public scope."""

    if type(model) is not CanonicalModel:
        raise ValueError("model must be a CanonicalModel")
    if config is not None and type(config) is not PublicRCFiberFrameConfig:
        raise ValueError("config must be a PublicRCFiberFrameConfig")
    if restart_checkpoint_chain is not None and not isinstance(
        restart_checkpoint_chain,
        (bytes, bytearray, memoryview),
    ):
        raise ValueError("restart_checkpoint_chain must be bytes-like")
    cfg = PublicRCFiberFrameConfig() if config is None else config
    snapshot = model.detached_analysis_snapshot()
    restart_hash = (
        stateful_fiber_frame2d_checkpoint_chain_artifact_hash(restart_checkpoint_chain)
        if restart_checkpoint_chain is not None
        else None
    )
    configuration = {
        "load_steps": cfg.load_steps,
        "target_load_factors": list(cfg.target_load_factors),
        "scaled_residual_tolerance": cfg.residual_tolerance,
        "solver_coordinate_increment_tolerance_m": cfg.increment_tolerance_m,
        "maximum_iterations": cfg.maximum_iterations,
        "matrix_backend": "numpy_dense_ndarray",
        "restart_supplied": restart_checkpoint_chain is not None,
        "restart_checkpoint_artifact_hash": restart_hash,
    }
    compiled, unsupported, warnings = _compile(snapshot)
    if compiled is None:
        return _build_public_result(
            snapshot,
            configuration=configuration,
            status="blocked",
            compiled=None,
            execution=None,
            authority=None,
            unsupported=unsupported,
            warnings=warnings,
        )

    try:
        execution = _run_load_path(
            compiled,
            cfg,
            restart_checkpoint_chain=restart_checkpoint_chain,
        )
    except (StatefulFiberFrame2DCheckpointChainArtifactError, ValueError) as exc:
        restart_failure = restart_checkpoint_chain is not None
        unsupported.append(
            {
                "kind": (
                    "rc_fiber_frame_checkpoint_restart_invalid"
                    if restart_failure
                    else "rc_fiber_frame_execution_failed"
                ),
                "path": "/restart_checkpoint_chain" if restart_failure else "/solver",
                "detail": str(exc),
            }
        )
        return _build_public_result(
            snapshot,
            configuration=configuration,
            status="blocked",
            compiled=compiled,
            execution=None,
            authority=None,
            unsupported=unsupported,
            warnings=warnings,
        )

    if execution.path.status != "ready" or not execution.path.contract_pass:
        return _build_public_result(
            snapshot,
            configuration=configuration,
            status="blocked",
            compiled=compiled,
            execution=execution,
            authority=None,
            unsupported=unsupported,
            warnings=warnings,
        )

    try:
        authority = _create_authority_artifacts(snapshot, compiled, execution, cfg)
    except ValueError as exc:
        code = getattr(exc, "code", "rc_fiber_frame_authority_pipeline_failed")
        unsupported.append(
            {
                "kind": str(code),
                "path": "/result_authority",
                "detail": str(exc),
            }
        )
        return _build_public_result(
            snapshot,
            configuration=configuration,
            status="blocked",
            compiled=compiled,
            execution=execution,
            authority=None,
            unsupported=unsupported,
            warnings=warnings,
        )

    return _build_public_result(
        snapshot,
        configuration=configuration,
        status="ready",
        compiled=compiled,
        execution=execution,
        authority=authority,
        unsupported=unsupported,
        warnings=warnings,
    )


def validate_public_rc_fiber_frame_result(
    result: PublicRCFiberFrameResult,
) -> PublicRCFiberFrameValidationReport:
    """Validate the stable public envelope and summarize its authority gates."""

    if type(result) is not PublicRCFiberFrameResult:
        raise ValueError("result must be a PublicRCFiberFrameResult")
    expected_hash = canonical_hash(_public_result_payload(result, include_hash=False))
    if result.result_hash != expected_hash:
        raise ValueError("result_hash does not match the public result payload")
    exact_recovery = bool(
        result.contract_pass
        and result.status == "ready"
        and not result.unsupported_features
        and result.authority.get("reaction") == "authoritative"
        and result.authority.get("member_force") == "authoritative"
        and result.authority.get("section_resultant") == "authoritative"
        and result.authority.get("fiber_strain_stress") == "authoritative"
        and result.metrics.get("exact_engineering_recovery") is True
    )
    if result.contract_pass != exact_recovery:
        raise ValueError("contract_pass does not match exact recovery authority")
    terminal_epoch = result.checkpoint.get("terminal_epoch")
    terminal_load_factor = result.checkpoint.get("terminal_load_factor")
    return PublicRCFiberFrameValidationReport(
        status="ready" if exact_recovery else "blocked",
        contract_pass=exact_recovery,
        result_hash=result.result_hash,
        exact_engineering_recovery=exact_recovery,
        checkpoint_available=bool(result.checkpoint.get("available", False)),
        terminal_epoch=(
            int(terminal_epoch) if isinstance(terminal_epoch, int) else None
        ),
        terminal_load_factor=(
            float(terminal_load_factor)
            if isinstance(terminal_load_factor, (int, float))
            and not isinstance(terminal_load_factor, bool)
            else None
        ),
        unsupported_feature_count=len(result.unsupported_features),
        warning_count=len(result.warnings),
        fallback_count=int(result.metrics.get("fallback_count", 0)),
        regularization_count=int(result.metrics.get("regularization_count", 0)),
    )


def _compile(
    model: CanonicalModel,
) -> tuple[
    _CompiledPublicRCFiberFrame | None,
    list[Mapping[str, Any]],
    list[str],
]:
    unsupported: list[Mapping[str, Any]] = [
        dict(row) for row in model.unsupported_features
    ]
    warnings = list(model.warnings)
    if unsupported:
        return None, unsupported, warnings
    try:
        compiled = _compile_exact(model)
    except _PublicRCFiberFrameCompileError as exc:
        unsupported.append(exc.to_blocker())
        return None, unsupported, warnings
    return compiled, unsupported, warnings


def _compile_exact(model: CanonicalModel) -> _CompiledPublicRCFiberFrame:
    if model.schema_version != CANONICAL_MODEL_SCHEMA_VERSION:
        _fail_compile(
            "rc_fiber_frame_schema_invalid",
            "/schema_version",
            f"Expected {CANONICAL_MODEL_SCHEMA_VERSION}.",
        )
    if model.units.length != "m" or model.units.force != "kN":
        _fail_compile(
            "rc_fiber_frame_units_unsupported",
            "/units",
            "The public profile requires length=m and force=kN.",
        )
    if (
        tuple(str(value).upper() for value in model.coordinate_system.axis_order)
        != ("X", "Y", "Z")
        or str(model.coordinate_system.up_axis).upper() != "Z"
    ):
        _fail_compile(
            "rc_fiber_frame_coordinate_system_unsupported",
            "/coordinate_system",
            "The public profile requires global XYZ order with Z up.",
        )
    if set(model.metadata) - {"case_id"}:
        _fail_compile(
            "rc_fiber_frame_metadata_unsupported",
            "/metadata",
            "Only optional metadata.case_id is supported.",
        )
    if "case_id" in model.metadata:
        _stable_id(model.metadata["case_id"], "/metadata/case_id")

    node_count = len(model.nodes)
    if node_count < 2 or node_count > _MAX_NODES:
        _fail_compile(
            "rc_fiber_frame_node_count_unsupported",
            "/nodes",
            f"Expected between 2 and {_MAX_NODES} nodes.",
        )
    node_ids: list[str] = []
    coordinates: list[tuple[float, float]] = []
    for index, row in enumerate(model.nodes):
        path = f"/nodes/{index}"
        _exact_keys(row, {"id", "coordinates"}, path)
        node_id = _stable_id(row["id"], f"{path}/id")
        if node_id in node_ids:
            _fail_compile(
                "rc_fiber_frame_node_id_duplicate",
                f"{path}/id",
                "Node IDs must be unique.",
            )
        raw = row["coordinates"]
        if type(raw) is not list or len(raw) != 3:
            _fail_compile(
                "rc_fiber_frame_node_coordinates_invalid",
                f"{path}/coordinates",
                "Coordinates must be an exact three-value JSON array.",
            )
        x = _finite_number(raw[0], f"{path}/coordinates/0")
        y = _finite_number(raw[1], f"{path}/coordinates/1")
        z = _finite_number(raw[2], f"{path}/coordinates/2")
        if z != 0.0:
            _fail_compile(
                "rc_fiber_frame_node_not_in_xy_plane",
                f"{path}/coordinates/2",
                "Every node must have exactly zero Z coordinate.",
            )
        if (x, y) in coordinates:
            _fail_compile(
                "rc_fiber_frame_node_coordinates_duplicate",
                f"{path}/coordinates",
                "Distinct nodes must not occupy identical XY coordinates.",
            )
        node_ids.append(node_id)
        coordinates.append((x, y))

    if len(model.materials) < 2 or len(model.materials) > _MAX_MATERIALS:
        _fail_compile(
            "rc_fiber_frame_material_count_unsupported",
            "/materials",
            f"Expected between 2 and {_MAX_MATERIALS} explicit materials.",
        )
    materials: dict[
        str,
        tuple[str, BilinearCombinedHardeningSteel | AsymmetricConcreteDamageMaterial],
    ] = {}
    for index, row in enumerate(model.materials):
        path = f"/materials/{index}"
        if type(row) is not dict:
            _fail_compile(
                "rc_fiber_frame_material_row_invalid",
                path,
                "Expected a material JSON object.",
            )
        material_id = _stable_id(row.get("id"), f"{path}/id")
        if material_id in materials:
            _fail_compile(
                "rc_fiber_frame_material_id_duplicate",
                f"{path}/id",
                "Material IDs must be unique.",
            )
        material_type = row.get("type")
        try:
            if material_type == "bilinear_combined_hardening_steel":
                _exact_keys(row, _STEEL_KEYS, path)
                material = BilinearCombinedHardeningSteel(
                    elastic_modulus_mpa=_positive_number(
                        row["elastic_modulus_mpa"],
                        f"{path}/elastic_modulus_mpa",
                    ),
                    yield_stress_mpa=_positive_number(
                        row["yield_stress_mpa"],
                        f"{path}/yield_stress_mpa",
                    ),
                    isotropic_hardening_modulus_mpa=_nonnegative_number(
                        row["isotropic_hardening_modulus_mpa"],
                        f"{path}/isotropic_hardening_modulus_mpa",
                    ),
                    kinematic_hardening_modulus_mpa=_nonnegative_number(
                        row["kinematic_hardening_modulus_mpa"],
                        f"{path}/kinematic_hardening_modulus_mpa",
                    ),
                    yield_tolerance_mpa=_nonnegative_number(
                        row["yield_tolerance_mpa"],
                        f"{path}/yield_tolerance_mpa",
                    ),
                    material_id=material_id,
                )
                kind = "steel"
            elif material_type == "asymmetric_concrete_damage":
                _exact_keys(row, _CONCRETE_KEYS, path)
                material = AsymmetricConcreteDamageMaterial(
                    elastic_modulus_mpa=_positive_number(
                        row["elastic_modulus_mpa"],
                        f"{path}/elastic_modulus_mpa",
                    ),
                    tensile_strength_mpa=_positive_number(
                        row["tensile_strength_mpa"],
                        f"{path}/tensile_strength_mpa",
                    ),
                    compressive_strength_mpa=_positive_number(
                        row["compressive_strength_mpa"],
                        f"{path}/compressive_strength_mpa",
                    ),
                    tensile_softening_rate=_positive_number(
                        row["tensile_softening_rate"],
                        f"{path}/tensile_softening_rate",
                    ),
                    compressive_softening_rate=_positive_number(
                        row["compressive_softening_rate"],
                        f"{path}/compressive_softening_rate",
                    ),
                    history_tolerance=_nonnegative_number(
                        row["history_tolerance"],
                        f"{path}/history_tolerance",
                    ),
                    material_id=material_id,
                )
                kind = "concrete"
            else:
                _fail_compile(
                    "rc_fiber_frame_material_type_unsupported",
                    f"{path}/type",
                    "Expected bilinear_combined_hardening_steel or "
                    "asymmetric_concrete_damage.",
                )
        except ValueError as exc:
            if isinstance(exc, _PublicRCFiberFrameCompileError):
                raise
            _fail_compile(
                "rc_fiber_frame_material_invalid",
                path,
                str(exc),
            )
        materials[material_id] = (kind, material)

    if len(model.sections) < 1 or len(model.sections) > _MAX_SECTIONS:
        _fail_compile(
            "rc_fiber_frame_section_count_unsupported",
            "/sections",
            f"Expected between 1 and {_MAX_SECTIONS} explicit sections.",
        )
    sections: dict[str, StatefulRCFiberSection] = {}
    section_material_ids: dict[str, tuple[str, str]] = {}
    for index, row in enumerate(model.sections):
        path = f"/sections/{index}"
        _exact_keys(row, _SECTION_KEYS, path)
        section_id = _stable_id(row["id"], f"{path}/id")
        if section_id in sections:
            _fail_compile(
                "rc_fiber_frame_section_id_duplicate",
                f"{path}/id",
                "Section IDs must be unique.",
            )
        if row["type"] != "rectangular_rc_fiber_section":
            _fail_compile(
                "rc_fiber_frame_section_type_unsupported",
                f"{path}/type",
                "Expected rectangular_rc_fiber_section.",
            )
        steel_id = _stable_id(row["steel_material"], f"{path}/steel_material")
        concrete_id = _stable_id(
            row["concrete_material"],
            f"{path}/concrete_material",
        )
        steel_entry = materials.get(steel_id)
        concrete_entry = materials.get(concrete_id)
        if steel_entry is None or steel_entry[0] != "steel":
            _fail_compile(
                "rc_fiber_frame_section_steel_reference_invalid",
                f"{path}/steel_material",
                "steel_material must reference a supported steel row.",
            )
        if concrete_entry is None or concrete_entry[0] != "concrete":
            _fail_compile(
                "rc_fiber_frame_section_concrete_reference_invalid",
                f"{path}/concrete_material",
                "concrete_material must reference a supported concrete row.",
            )
        layer_count = _integer_range(
            row["concrete_layer_count"],
            f"{path}/concrete_layer_count",
            2,
            _MAX_CONCRETE_LAYERS,
        )
        top_bars = _integer_range(
            row["top_bar_count"],
            f"{path}/top_bar_count",
            1,
            _MAX_BARS_PER_LAYER,
        )
        bottom_bars = _integer_range(
            row["bottom_bar_count"],
            f"{path}/bottom_bar_count",
            1,
            _MAX_BARS_PER_LAYER,
        )
        try:
            section = make_rectangular_stateful_rc_fiber_section(
                width_m=_positive_number(row["width_m"], f"{path}/width_m"),
                depth_m=_positive_number(row["depth_m"], f"{path}/depth_m"),
                cover_m=_positive_number(row["cover_m"], f"{path}/cover_m"),
                concrete_layer_count=layer_count,
                top_bar_count=top_bars,
                bottom_bar_count=bottom_bars,
                bar_area_m2=_positive_number(
                    row["bar_area_m2"],
                    f"{path}/bar_area_m2",
                ),
                section_id=section_id,
                steel=steel_entry[1],  # type: ignore[arg-type]
                concrete=concrete_entry[1],  # type: ignore[arg-type]
            )
        except ValueError as exc:
            if isinstance(exc, _PublicRCFiberFrameCompileError):
                raise
            _fail_compile(
                "rc_fiber_frame_section_invalid",
                path,
                str(exc),
            )
        sections[section_id] = section
        section_material_ids[section_id] = (steel_id, concrete_id)

    if len(model.elements) != node_count - 1:
        _fail_compile(
            "rc_fiber_frame_serial_member_count_invalid",
            "/elements",
            "A serial chain requires exactly node_count - 1 members.",
        )
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    member_ids: set[str] = set()
    members: list[StatefulFiberFrame2DMember] = []
    section_by_member: list[StatefulRCFiberSection] = []
    used_sections: set[str] = set()
    for index, row in enumerate(model.elements):
        path = f"/elements/{index}"
        _exact_keys(
            row,
            {"id", "type", "nodes", "section", "integration_order"},
            path,
        )
        member_id = _stable_id(row["id"], f"{path}/id")
        if member_id in member_ids:
            _fail_compile(
                "rc_fiber_frame_member_id_duplicate",
                f"{path}/id",
                "Member IDs must be unique.",
            )
        if row["type"] != "stateful_rc_fiber_frame2d":
            _fail_compile(
                "rc_fiber_frame_member_type_unsupported",
                f"{path}/type",
                "Expected stateful_rc_fiber_frame2d.",
            )
        connectivity = row["nodes"]
        if type(connectivity) is not list or len(connectivity) != 2:
            _fail_compile(
                "rc_fiber_frame_member_connectivity_invalid",
                f"{path}/nodes",
                "Member connectivity must contain exactly two node IDs.",
            )
        node_i_id = connectivity[0]
        node_j_id = connectivity[1]
        if (
            type(node_i_id) is not str
            or type(node_j_id) is not str
            or node_i_id not in node_index
            or node_j_id not in node_index
            or node_i_id == node_j_id
        ):
            _fail_compile(
                "rc_fiber_frame_member_connectivity_invalid",
                f"{path}/nodes",
                "Connectivity must reference two distinct declared nodes.",
            )
        if node_j_id in adjacency[node_i_id]:
            _fail_compile(
                "rc_fiber_frame_member_connectivity_duplicate",
                f"{path}/nodes",
                "Parallel or duplicate member connectivity is unsupported.",
            )
        section_id = _stable_id(row["section"], f"{path}/section")
        section = sections.get(section_id)
        if section is None:
            _fail_compile(
                "rc_fiber_frame_member_section_reference_invalid",
                f"{path}/section",
                "Member section must reference a declared RC fiber section.",
            )
        integration_order = _integer_range(
            row["integration_order"],
            f"{path}/integration_order",
            2,
            3,
        )
        point_i = np.asarray(coordinates[node_index[node_i_id]], dtype=np.float64)
        point_j = np.asarray(coordinates[node_index[node_j_id]], dtype=np.float64)
        length = float(np.linalg.norm(point_j - point_i))
        if not math.isfinite(length) or length <= np.finfo(np.float64).eps:
            _fail_compile(
                "rc_fiber_frame_member_length_invalid",
                f"{path}/nodes",
                "Member length must be finite and positive.",
            )
        member = StatefulFiberFrame2DMember(
            member_id=member_id,
            node_i=node_index[node_i_id],
            node_j=node_index[node_j_id],
            element=StatefulFiberBeam2D(
                section=section,
                length_m=length,
                integration_order=integration_order,
                element_id=member_id,
            ),
        )
        members.append(member)
        section_by_member.append(section)
        member_ids.add(member_id)
        used_sections.add(section_id)
        adjacency[node_i_id].add(node_j_id)
        adjacency[node_j_id].add(node_i_id)

    endpoints = [
        node_id for node_id, neighbors in adjacency.items() if len(neighbors) == 1
    ]
    if (
        len(endpoints) != 2
        or any(
            len(neighbors) < 1 or len(neighbors) > 2 for neighbors in adjacency.values()
        )
        or len(_connected_nodes(adjacency, node_ids[0])) != node_count
    ):
        _fail_compile(
            "rc_fiber_frame_topology_not_serial_chain",
            "/elements",
            "Only one connected, unbranched, acyclic member chain is supported.",
        )

    if len(model.supports) != 1:
        _fail_compile(
            "rc_fiber_frame_support_count_unsupported",
            "/supports",
            "Exactly one zero-displacement endpoint support is required.",
        )
    support = model.supports[0]
    _exact_keys(support, {"node", "dofs"}, "/supports/0")
    support_node_id = support["node"]
    if type(support_node_id) is not str or support_node_id not in endpoints:
        _fail_compile(
            "rc_fiber_frame_support_node_invalid",
            "/supports/0/node",
            "The single support must be located at a chain endpoint.",
        )
    support_dofs = support["dofs"]
    if (
        type(support_dofs) is not list
        or len(support_dofs) != 3
        or set(support_dofs) != set(_ACTIVE_COMPONENTS)
    ):
        _fail_compile(
            "rc_fiber_frame_support_dofs_invalid",
            "/supports/0/dofs",
            "The endpoint must restrain exactly UX, UY, and RZ at zero.",
        )
    support_index = node_index[support_node_id]
    fixed_global_dofs = tuple(3 * support_index + offset for offset in range(3))

    if len(model.loads) < 1 or len(model.loads) > _MAX_LOAD_ROWS:
        _fail_compile(
            "rc_fiber_frame_load_count_unsupported",
            "/loads",
            f"Expected between 1 and {_MAX_LOAD_ROWS} nodal load rows.",
        )
    reference_loads: list[tuple[int, float]] = []
    loaded_nodes: set[str] = set()
    for index, row in enumerate(model.loads):
        path = f"/loads/{index}"
        _exact_keys(row, {"node", "components"}, path)
        load_node_id = row["node"]
        if type(load_node_id) is not str or load_node_id not in node_index:
            _fail_compile(
                "rc_fiber_frame_load_node_invalid",
                f"{path}/node",
                "Nodal load must reference a declared node.",
            )
        if load_node_id == support_node_id:
            _fail_compile(
                "rc_fiber_frame_support_load_unsupported",
                f"{path}/node",
                "Loads applied directly to the fully fixed endpoint are unsupported.",
            )
        if load_node_id in loaded_nodes:
            _fail_compile(
                "rc_fiber_frame_load_node_duplicate",
                f"{path}/node",
                "Use exactly one proportional load row per loaded node.",
            )
        components = row["components"]
        if type(components) is not dict or set(components) != set(_LOAD_COMPONENTS):
            _fail_compile(
                "rc_fiber_frame_load_components_invalid",
                f"{path}/components",
                "Components must contain exactly FX, FY, FZ, MX, MY, and MZ.",
            )
        values = {
            name: _finite_number(components[name], f"{path}/components/{name}")
            for name in _LOAD_COMPONENTS
        }
        if values["FZ"] != 0.0 or values["MX"] != 0.0 or values["MY"] != 0.0:
            _fail_compile(
                "rc_fiber_frame_out_of_plane_load_unsupported",
                f"{path}/components",
                "FZ, MX, and MY must be exactly zero for the XY-plane profile.",
            )
        active_values = (values["FX"], values["FY"], values["MZ"])
        if not any(value != 0.0 for value in active_values):
            _fail_compile(
                "rc_fiber_frame_zero_load_row_invalid",
                f"{path}/components",
                "Every load row must contain a nonzero in-plane component.",
            )
        base_dof = 3 * node_index[load_node_id]
        reference_loads.extend(
            (base_dof + offset, value)
            for offset, value in enumerate(active_values)
            if value != 0.0
        )
        loaded_nodes.add(load_node_id)

    if used_sections != set(sections):
        _fail_compile(
            "rc_fiber_frame_unused_section_unsupported",
            "/sections",
            "Every declared section must be referenced by at least one member.",
        )
    used_materials = {
        material_id
        for section_id in used_sections
        for material_id in section_material_ids[section_id]
    }
    if used_materials != set(materials):
        _fail_compile(
            "rc_fiber_frame_unused_material_unsupported",
            "/materials",
            "Every declared material must be referenced by a used section.",
        )

    rotation_scale = max(member.element.length_m for member in members)
    digest = model.canonical_model_checksum.removeprefix("sha256:")[:20]
    try:
        problem = StatefulFiberFrame2DProblem(
            case_id=f"public_rc_fiber_frame_{digest}",
            node_coordinates_m=tuple(coordinates),
            members=tuple(members),
            fixed_global_dofs=fixed_global_dofs,
            reference_external_loads=tuple(sorted(reference_loads)),
            rotation_coordinate_scale_m=rotation_scale,
        )
    except ValueError as exc:
        _fail_compile(
            "rc_fiber_frame_problem_contract_invalid",
            "/",
            str(exc),
        )
    return _CompiledPublicRCFiberFrame(
        problem=problem,
        node_ids=tuple(node_ids),
        section_by_member=tuple(section_by_member),
        support_node_id=support_node_id,
    )


def _run_load_path(
    compiled: _CompiledPublicRCFiberFrame,
    config: PublicRCFiberFrameConfig,
    *,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None,
) -> _ExecutionArtifacts:
    problem = compiled.problem
    factors = config.target_load_factors
    solver_config = NewtonRaphsonConfig(
        residual_tolerance=config.residual_tolerance,
        increment_tolerance=config.increment_tolerance_m,
        max_iterations=config.maximum_iterations,
    )
    restart_supplied = restart_checkpoint_chain is not None
    replayed_prefix_count = 0

    if restart_checkpoint_chain is None:
        path = run_stateful_fiber_frame2d_load_path(
            problem,
            factors,
            config=solver_config,
        )
        newly_solved_count = len(path.steps)
    else:
        loaded = load_stateful_fiber_frame2d_checkpoint_chain_bytes(
            restart_checkpoint_chain,
            problem,
        )
        prefix_count = len(loaded.checkpoints) - 1
        if prefix_count > len(factors):
            raise ValueError(
                "restart checkpoint chain exceeds the configured load path"
            )
        expected_prefix = factors[:prefix_count]
        actual_prefix = tuple(
            checkpoint.load_factor for checkpoint in loaded.checkpoints[1:]
        )
        if actual_prefix != expected_prefix:
            raise ValueError(
                "restart checkpoint load factors are not an exact configured prefix"
            )
        if prefix_count:
            replay = run_stateful_fiber_frame2d_load_path(
                problem,
                expected_prefix,
                config=solver_config,
            )
            if replay.status != "ready" or not replay.contract_pass:
                raise ValueError("restart prefix could not be replayed as a ready path")
            replayed_checkpoints = (
                replay.initial_checkpoint,
                *(step.accepted_checkpoint for step in replay.steps),
            )
            if any(
                actual.canonical_bytes() != expected.canonical_bytes()
                for actual, expected in zip(
                    replayed_checkpoints,
                    loaded.checkpoints,
                    strict=True,
                )
            ):
                raise ValueError("restart checkpoint bytes do not match exact replay")
            prefix_path = replay
        else:
            root = initial_stateful_fiber_frame2d_checkpoint(problem)
            if root.canonical_bytes() != loaded.root_checkpoint.canonical_bytes():
                raise ValueError("restart root checkpoint does not match exact genesis")
            prefix_path = StatefulFiberFrame2DLoadPathResult(
                status="ready",
                initial_checkpoint=root,
                final_checkpoint=root,
                steps=(),
            )
        replayed_prefix_count = prefix_count
        remaining = factors[prefix_count:]
        if remaining:
            suffix = run_stateful_fiber_frame2d_load_path(
                problem,
                remaining,
                initial_checkpoint=prefix_path.final_checkpoint,
                config=solver_config,
            )
            path = StatefulFiberFrame2DLoadPathResult(
                status=suffix.status,
                initial_checkpoint=prefix_path.initial_checkpoint,
                final_checkpoint=suffix.final_checkpoint,
                steps=prefix_path.steps + suffix.steps,
            )
            newly_solved_count = len(suffix.steps)
        else:
            path = prefix_path
            newly_solved_count = 0

    committed_checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps if step.committed),
    )
    chain = make_stateful_fiber_frame2d_checkpoint_chain(
        problem,
        committed_checkpoints,
    )
    artifact = dump_stateful_fiber_frame2d_checkpoint_chain_bytes(problem, chain)
    return _ExecutionArtifacts(
        path=path,
        checkpoint_chain=chain,
        checkpoint_bytes=artifact,
        restart_supplied=restart_supplied,
        replayed_prefix_step_count=replayed_prefix_count,
        newly_solved_step_count=newly_solved_count,
    )


def _create_authority_artifacts(
    model: CanonicalModel,
    compiled: _CompiledPublicRCFiberFrame,
    execution: _ExecutionArtifacts,
    config: PublicRCFiberFrameConfig,
) -> _AuthorityArtifacts:
    problem = compiled.problem
    path = execution.path
    chain = execution.checkpoint_chain
    plan = compile_stateful_fiber_frame2d_execution_topology(
        problem,
        model_ir_content_hash=model.canonical_model_checksum,
        node_ids=compiled.node_ids,
    )
    scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
    kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
        problem,
        plan,
        chain,
    )
    material = create_fiber_frame_material_state_projection_chain(
        problem,
        chain,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hashes=kinematic.solver_state_hashes,
    )
    binding = create_fiber_frame_nonlinear_execution_state_binding(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
    )
    terminal = create_fiber_frame_nonlinear_terminal_receipt(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
    )
    digest = model.canonical_model_checksum.removeprefix("sha256:")[:20]
    adapter = create_fiber_frame_nonlinear_numerical_result_adapter(
        problem,
        plan,
        scaling,
        chain,
        kinematic,
        material,
        binding,
        path,
        terminal,
        result_id=f"result.public_rc_fiber_frame.{digest}",
    )
    recovery = create_fiber_frame_nonlinear_recovery_operator(adapter)
    engineering = create_fiber_frame_nonlinear_engineering_result_ir(
        engineering_result_id=f"engineering.public_rc_fiber_frame.{digest}",
        source_adapter=adapter,
        recovery_operator=recovery,
    )
    if engineering.load_factor != config.target_load_factors[-1]:
        raise ValueError("engineering result load factor does not match configuration")
    return _AuthorityArtifacts(adapter=adapter, engineering_result=engineering)


def _build_public_result(
    model: CanonicalModel,
    *,
    configuration: Mapping[str, Any],
    status: str,
    compiled: _CompiledPublicRCFiberFrame | None,
    execution: _ExecutionArtifacts | None,
    authority: _AuthorityArtifacts | None,
    unsupported: list[Mapping[str, Any]],
    warnings: list[str],
) -> PublicRCFiberFrameResult:
    bindings: dict[str, Any] = {}
    checkpoint: dict[str, Any] = {"available": False}
    node_rows: tuple[Mapping[str, Any], ...] = ()
    reaction_rows: tuple[Mapping[str, Any], ...] = ()
    member_rows: tuple[Mapping[str, Any], ...] = ()
    section_rows: tuple[Mapping[str, Any], ...] = ()
    fiber_rows: tuple[Mapping[str, Any], ...] = ()
    history: tuple[Mapping[str, Any], ...] = ()
    authority_axes: dict[str, str] = {
        key: "not_authoritative"
        for key in FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES
    }
    metrics: dict[str, Any] = {
        "solver_executed": execution is not None,
        "exact_engineering_recovery": False,
        "committed_step_count": 0,
        "replayed_prefix_step_count": 0,
        "newly_solved_step_count": 0,
        "fallback_count": 0,
        "regularization_count": 0,
        "rollback_exact": None,
    }

    if compiled is not None:
        bindings["problem_contract_hash"] = compiled.problem.contract_hash
    if execution is not None:
        path = execution.path
        chain = execution.checkpoint_chain
        artifact_hash = stateful_fiber_frame2d_checkpoint_chain_artifact_hash(
            execution.checkpoint_bytes
        )
        bindings["checkpoint_chain_hash"] = chain.chain_hash
        bindings["checkpoint_chain_artifact_hash"] = artifact_hash
        checkpoint = {
            "available": True,
            "storage_profile": "canonical-signed-zero-preserving-utf8-json.v1",
            "chain_hash": chain.chain_hash,
            "artifact_hash": artifact_hash,
            "artifact_byte_length": len(execution.checkpoint_bytes),
            "root_state_hash": chain.root_checkpoint.state_hash,
            "terminal_state_hash": chain.terminal_checkpoint.state_hash,
            "terminal_epoch": chain.terminal_checkpoint.epoch,
            "terminal_load_factor": chain.terminal_checkpoint.load_factor,
            "prefix_export_supported": True,
        }
        failed_steps = [step for step in path.steps if not step.committed]
        history = tuple(
            {
                "load_step": step_index,
                "target_load_factor": step.metrics["target_load_factor"],
                "committed": step.committed,
                **dict(row),
            }
            for step_index, step in enumerate(path.steps, start=1)
            for row in step.trial_solution.convergence_history
        )
        metrics.update(
            {
                "solver_executed": bool(
                    execution.replayed_prefix_step_count
                    or execution.newly_solved_step_count
                ),
                "restart_supplied": execution.restart_supplied,
                "committed_step_count": sum(int(step.committed) for step in path.steps),
                "replayed_prefix_step_count": (execution.replayed_prefix_step_count),
                "newly_solved_step_count": execution.newly_solved_step_count,
                "fallback_count": sum(
                    int(bool(step.metrics.get("fallback_used"))) for step in path.steps
                ),
                "regularization_count": sum(
                    int(bool(step.metrics.get("regularization_used")))
                    for step in path.steps
                ),
                "rollback_exact": (
                    failed_steps[-1].metrics.get("rollback_exact")
                    if failed_steps
                    else None
                ),
                "terminal_epoch": chain.terminal_checkpoint.epoch,
                "terminal_load_factor": chain.terminal_checkpoint.load_factor,
                "terminal_checkpoint_state_hash": (
                    chain.terminal_checkpoint.state_hash
                ),
            }
        )

    ready = bool(
        status == "ready"
        and compiled is not None
        and execution is not None
        and authority is not None
        and not unsupported
    )
    if ready:
        assert compiled is not None
        assert execution is not None
        assert authority is not None
        adapter = authority.adapter
        engineering = authority.engineering_result
        operator = engineering._recovery_operator
        numerical = adapter.numerical_result
        authority_axes = dict(FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES)
        bindings.update(
            {
                "execution_topology_plan_hash": (
                    engineering.execution_topology_plan_hash
                ),
                "source_result_adapter_hash": adapter.adapter_hash,
                "numerical_result_hash": numerical.result_hash,
                "engineering_result_hash": engineering.engineering_result_hash,
                "recovery_operator_hash": engineering.recovery_operator_hash,
                "terminal_kinematic_state_hash": (
                    engineering.terminal_kinematic_state_hash
                ),
                "terminal_material_state_bundle_hash": (
                    engineering.terminal_material_state_bundle_hash
                ),
                "engineering_array_bundle_hash": engineering.array_bundle_hash,
            }
        )
        node_rows = _node_displacement_rows(compiled, numerical.displacement_global_si)
        reaction_rows = _reaction_rows(compiled, engineering.reaction_global_si)
        member_rows = _member_force_rows(compiled, engineering)
        section_rows, fiber_rows = _section_and_fiber_rows(compiled, engineering)
        metrics.update(
            {
                "exact_engineering_recovery": True,
                "free_residual_scaled_linf": engineering.free_residual_scaled_linf,
                "total_dissipated_energy_mj": (engineering.total_dissipated_energy_mj),
                "authored_reaction_count": engineering.authored_reaction_count,
                "member_count": engineering.member_count,
                "integration_point_count": engineering.integration_point_count,
                "fiber_output_count": engineering.fiber_output_count,
                "state_bytes_exact": operator.state_bytes_exact,
                "all_recovery_gates_passed": True,
            }
        )

    provisional = PublicRCFiberFrameResult(
        status="ready" if ready else "blocked",
        contract_pass=ready,
        result_hash="sha256:" + "0" * 64,
        canonical_model_checksum=model.canonical_model_checksum,
        input_checksum=model.input_checksum,
        solver_id=PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
        compiler_profile=PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
        configuration=dict(configuration),
        contract_bindings=bindings,
        checkpoint=checkpoint,
        authority=authority_axes,
        node_displacements=node_rows,
        support_reactions=reaction_rows,
        member_end_forces=member_rows,
        section_results=section_rows,
        fiber_results=fiber_rows,
        convergence_history=history,
        metrics=metrics,
        unsupported_features=tuple(dict(row) for row in unsupported),
        warnings=tuple(warnings),
        _problem=compiled.problem
        if compiled is not None and execution is not None
        else None,
        _checkpoint_chain=(
            execution.checkpoint_chain if execution is not None else None
        ),
    )
    result_hash = canonical_hash(
        _public_result_payload(provisional, include_hash=False)
    )
    return replace(provisional, result_hash=result_hash)


def _node_displacement_rows(
    compiled: _CompiledPublicRCFiberFrame,
    displacement_global_si: Any,
) -> tuple[Mapping[str, Any], ...]:
    values = np.asarray(displacement_global_si, dtype=np.float64).reshape((-1, 6))
    return tuple(
        {
            "node_id": node_id,
            "UX_m": float(row[0]),
            "UY_m": float(row[1]),
            "UZ_m": float(row[2]),
            "RX_rad": float(row[3]),
            "RY_rad": float(row[4]),
            "RZ_rad": float(row[5]),
        }
        for node_id, row in zip(compiled.node_ids, values, strict=True)
    )


def _reaction_rows(
    compiled: _CompiledPublicRCFiberFrame,
    reaction_global_si: Any,
) -> tuple[Mapping[str, Any], ...]:
    values = np.asarray(reaction_global_si, dtype=np.float64).reshape((-1, 6))
    node_index = compiled.node_ids.index(compiled.support_node_id)
    return tuple(
        {
            "node_id": compiled.support_node_id,
            "dof": component,
            "value_si": float(values[node_index, _ACTIVE_TO_CANONICAL[component]]),
            "unit": "N" if component in {"UX", "UY"} else "N*m",
        }
        for component in _ACTIVE_COMPONENTS
    )


def _member_force_rows(
    compiled: _CompiledPublicRCFiberFrame,
    engineering: FiberFrameNonlinearEngineeringResultIR,
) -> tuple[Mapping[str, Any], ...]:
    values = np.asarray(engineering.member_local_end_force_si, dtype=np.float64)
    return tuple(
        {
            "member_id": member.member_id,
            "node_i": compiled.node_ids[member.node_i],
            "node_j": compiled.node_ids[member.node_j],
            "local_end_i": {
                "FX_N": float(row[0]),
                "FY_N": float(row[1]),
                "MZ_Nm": float(row[2]),
            },
            "local_end_j": {
                "FX_N": float(row[3]),
                "FY_N": float(row[4]),
                "MZ_Nm": float(row[5]),
            },
        }
        for member, row in zip(compiled.problem.members, values, strict=True)
    )


def _section_and_fiber_rows(
    compiled: _CompiledPublicRCFiberFrame,
    engineering: FiberFrameNonlinearEngineeringResultIR,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
    operator = engineering._recovery_operator
    ip_offsets = np.asarray(operator.array("integration_point_offsets"), dtype=np.int64)
    ip_xi = np.asarray(operator.array("integration_point_xi"), dtype=np.float64)
    ip_weights = np.asarray(
        operator.array("integration_point_weights"),
        dtype=np.float64,
    )
    generalized = np.asarray(
        operator.array("section_generalized_strain"),
        dtype=np.float64,
    )
    resultants = np.asarray(engineering.section_resultant_si, dtype=np.float64)
    section_energy = np.asarray(
        operator.array("section_dissipated_energy_mj_per_m"),
        dtype=np.float64,
    )
    fiber_offsets = np.asarray(operator.array("fiber_offsets"), dtype=np.int64)
    fiber_y = np.asarray(operator.array("fiber_y_m"), dtype=np.float64)
    fiber_area = np.asarray(operator.array("fiber_area_m2"), dtype=np.float64)
    fiber_strain = np.asarray(engineering.fiber_strain, dtype=np.float64)
    fiber_stress = np.asarray(engineering.fiber_stress_mpa, dtype=np.float64)
    fiber_energy = np.asarray(
        operator.array("fiber_dissipated_energy_density_mj_per_m3"),
        dtype=np.float64,
    )
    sections: list[Mapping[str, Any]] = []
    fibers: list[Mapping[str, Any]] = []
    for member_index, (member, section) in enumerate(
        zip(
            compiled.problem.members,
            compiled.section_by_member,
            strict=True,
        )
    ):
        for flat_ip in range(ip_offsets[member_index], ip_offsets[member_index + 1]):
            local_ip = flat_ip - ip_offsets[member_index]
            sections.append(
                {
                    "member_id": member.member_id,
                    "integration_point_index": int(local_ip),
                    "xi": float(ip_xi[flat_ip]),
                    "weight": float(ip_weights[flat_ip]),
                    "axial_strain": float(generalized[flat_ip, 0]),
                    "curvature_z_per_m": float(generalized[flat_ip, 1]),
                    "axial_force_N": float(resultants[flat_ip, 0]),
                    "moment_z_Nm": float(resultants[flat_ip, 1]),
                    "dissipated_energy_MJ_per_m": float(section_energy[flat_ip]),
                }
            )
            start = int(fiber_offsets[flat_ip])
            stop = int(fiber_offsets[flat_ip + 1])
            if stop - start != len(section.fibers):
                raise ValueError(
                    "recovered fiber count does not match compiled section"
                )
            for fiber_index, (flat_fiber, fiber) in enumerate(
                zip(range(start, stop), section.fibers, strict=True)
            ):
                fibers.append(
                    {
                        "member_id": member.member_id,
                        "integration_point_index": int(local_ip),
                        "fiber_index": fiber_index,
                        "fiber_id": fiber.fiber_id,
                        "material_kind": fiber.material_kind,
                        "y_m": float(fiber_y[flat_fiber]),
                        "area_m2": float(fiber_area[flat_fiber]),
                        "strain": float(fiber_strain[flat_fiber]),
                        "stress_MPa": float(fiber_stress[flat_fiber]),
                        "dissipated_energy_density_MJ_per_m3": float(
                            fiber_energy[flat_fiber]
                        ),
                    }
                )
    return tuple(sections), tuple(fibers)


def _public_result_payload(
    result: PublicRCFiberFrameResult,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": PUBLIC_RC_FIBER_FRAME_SCHEMA_VERSION,
        "status": result.status,
        "contract_pass": result.contract_pass,
        "result_hash": result.result_hash,
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
    if not include_hash:
        payload.pop("result_hash")
    return payload


def _connected_nodes(adjacency: Mapping[str, set[str]], start: str) -> set[str]:
    visited: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency[current] - visited)
    return visited


def _exact_keys(row: Mapping[str, Any], expected: set[str], path: str) -> None:
    if type(row) is not dict or set(row) != expected:
        actual = sorted(row) if isinstance(row, Mapping) else []
        _fail_compile(
            "rc_fiber_frame_row_keys_invalid",
            path,
            f"Expected exact keys {sorted(expected)}; got {actual}.",
        )


def _stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID.fullmatch(value) is None:
        _fail_compile(
            "rc_fiber_frame_stable_id_invalid",
            path,
            "Expected a stable identifier beginning with an ASCII letter.",
        )
    return value


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail_compile(
            "rc_fiber_frame_number_invalid",
            path,
            "Expected a finite JSON number.",
        )
    result = float(value)
    if not math.isfinite(result):
        _fail_compile(
            "rc_fiber_frame_number_invalid",
            path,
            "Expected a finite JSON number.",
        )
    return result


def _positive_number(value: Any, path: str) -> float:
    result = _finite_number(value, path)
    if result <= 0.0:
        _fail_compile(
            "rc_fiber_frame_number_not_positive",
            path,
            "Expected a positive number.",
        )
    return result


def _positive_config_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


def _nonnegative_number(value: Any, path: str) -> float:
    result = _finite_number(value, path)
    if result < 0.0:
        _fail_compile(
            "rc_fiber_frame_number_negative",
            path,
            "Expected a non-negative number.",
        )
    return result


def _integer_range(value: Any, path: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        _fail_compile(
            "rc_fiber_frame_integer_out_of_range",
            path,
            f"Expected an integer in [{minimum}, {maximum}].",
        )
    return value


def _fail_compile(kind: str, path: str, detail: str) -> None:
    raise _PublicRCFiberFrameCompileError(kind, path, detail)


__all__ = [
    "PUBLIC_RC_FIBER_FRAME_CLAIM_BOUNDARY",
    "PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE",
    "PUBLIC_RC_FIBER_FRAME_REPORT_SCHEMA_VERSION",
    "PUBLIC_RC_FIBER_FRAME_SCHEMA_VERSION",
    "PUBLIC_RC_FIBER_FRAME_SOLVER_ID",
    "PublicRCFiberFrameConfig",
    "PublicRCFiberFrameResult",
    "PublicRCFiberFrameValidationReport",
    "analyze_public_rc_fiber_frame",
    "validate_public_rc_fiber_frame_result",
]
