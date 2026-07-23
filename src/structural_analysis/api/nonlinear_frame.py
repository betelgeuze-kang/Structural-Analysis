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
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


UNIFIED_NONLINEAR_FRAME_SCHEMA_VERSION = "unified-nonlinear-frame-result.v1"
UNIFIED_NONLINEAR_FRAME_REPORT_SCHEMA_VERSION = (
    "unified-nonlinear-frame-validation-report.v1"
)
FIXED_CHORD_SERIAL_PROFILE: Final[Literal["fixed_chord_serial_cantilever.v1"]] = (
    "fixed_chord_serial_cantilever.v1"
)
COROTATIONAL_PORTAL_PROFILE: Final[Literal["corotational_one_bay_portal.v1"]] = (
    "corotational_one_bay_portal.v1"
)
UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY = (
    "The unified API selects one explicit bounded profile. The fixed-chord serial "
    "cantilever retains its existing Developer Preview authority. The corotational "
    "one-bay portal profile binds J1-J5, exact terminal engineering recovery, and "
    "epoch-zero checkpoint-chain replay, but remains a candidate until two independent "
    "Level 2 comparisons pass. No profile grants "
    "design-code, final-design, commercial, or release-readiness authority."
)

NonlinearFrameProfile = Literal[
    "fixed_chord_serial_cantilever.v1",
    "corotational_one_bay_portal.v1",
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

    def __post_init__(self) -> None:
        if self.profile not in (
            FIXED_CHORD_SERIAL_PROFILE,
            COROTATIONAL_PORTAL_PROFILE,
        ):
            raise ValueError("profile is not a supported nonlinear frame profile")
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
class _CompiledPortal:
    problem: StatefulCorotationalFiberFrame2DProblem
    compilation: CorotationalFiberFramePortalCompilation
    node_ids: tuple[str, ...]
    section_by_member: tuple[StatefulRCFiberSection, ...]
    support_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class _CorotationalExecution:
    path: StatefulCorotationalFiberFrame2DLoadPathResult
    chain: StatefulCorotationalFiberFrame2DCheckpointChain
    checkpoint_bytes: bytes
    restart_supplied: bool
    replayed_prefix_step_count: int
    newly_solved_step_count: int


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
    return _analyze_corotational_portal(snapshot, cfg, restart_checkpoint_chain)


def validate_nonlinear_frame_result(
    result: NonlinearFrameResult,
) -> NonlinearFrameValidationReport:
    if type(result) is not NonlinearFrameResult:
        raise ValueError("result must be a NonlinearFrameResult")
    expected_hash = canonical_hash(_result_payload(result, include_hash=False))
    if result.result_hash != expected_hash:
        raise ValueError("result_hash does not match the unified result payload")
    _validate_result_schema(result.to_dict())
    exact_recovery = bool(result.metrics.get("exact_engineering_recovery"))
    exact_replay = bool(result.metrics.get("exact_checkpoint_chain_replay"))
    fallback_count = int(result.metrics.get("fallback_count", 0))
    regularization_count = int(result.metrics.get("regularization_count", 0))
    ready = bool(
        result.status == "ready"
        and result.contract_pass
        and not result.unsupported_features
        and exact_recovery
        and exact_replay
        and fallback_count == 0
        and regularization_count == 0
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
) -> NonlinearFrameResult:
    configuration = {
        "profile": config.profile,
        "load_steps": config.load_steps,
        "target_load_factors": list(config.target_load_factors),
        "scaled_residual_tolerance": config.residual_tolerance,
        "solver_coordinate_increment_tolerance_m": config.increment_tolerance_m,
        "maximum_iterations": config.maximum_iterations,
        "matrix_backend": VECTOR_MATRIX_BACKEND,
        "stiffness_storage": "numpy_dense_ndarray",
        "restart_supplied": restart is not None,
        "restart_checkpoint_artifact_hash": (
            _artifact_hash(restart) if restart is not None else None
        ),
    }
    unsupported: list[Mapping[str, Any]] = [
        dict(row) for row in model.unsupported_features
    ]
    warnings = list(model.warnings)
    compiled: _CompiledPortal | None = None
    execution: _CorotationalExecution | None = None
    adapter: CorotationalEngineeringSourceAdapter | None = None
    engineering: CorotationalFiberFrameEngineeringResultIR | None = None
    if not unsupported:
        try:
            compiled = _compile_portal(model)
            execution = _run_corotational_path(compiled, config, restart)
            if execution.path.status != "ready" or not execution.path.contract_pass:
                raise NonlinearFrameError(
                    "corotational_portal_solver_blocked",
                    "/solver",
                    "The configured load path did not commit exactly.",
                )
            adapter = create_corotational_fiber_frame_j1_j5_adapter(
                compiled.compilation,
                execution.path,
            )
            digest = model.canonical_model_checksum.removeprefix("sha256:")[:20]
            engineering = create_corotational_fiber_frame_engineering_result_ir(
                engineering_result_id=f"engineering.corotational_portal.{digest}",
                source_adapter=adapter,
            )
        except (
            NonlinearFrameError,
            StatefulCorotationalFiberFrame2DCheckpointChainArtifactError,
            ValueError,
        ) as exc:
            code = str(getattr(exc, "code", "corotational_portal_execution_failed"))
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
        and not unsupported
    )
    if not ready:
        return _make_result(
            status="blocked",
            profile=config.profile,
            source_result_hash=None,
            model=model,
            solver_id="public_cpu_corotational_rc_fiber_frame_newton_v1",
            compiler_profile=(
                "planar_one_bay_one_story_portal_explicit_fiber_section.v1"
            ),
            configuration=configuration,
            contract_bindings=(
                {"problem_contract_hash": compiled.problem.contract_hash}
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
                "fallback_count": 0,
                "regularization_count": 0,
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
        "fallback_count": sum(
            int(bool(step.metrics.get("fallback_used")))
            for step in execution.path.steps
        ),
        "regularization_count": sum(
            int(bool(step.metrics.get("regularization_used")))
            for step in execution.path.steps
        ),
        "external_level2_attached": False,
        **dict(engineering.metrics),
    }
    return _make_result(
        status="ready",
        profile=config.profile,
        source_result_hash=engineering.engineering_result_hash,
        model=model,
        solver_id="public_cpu_corotational_rc_fiber_frame_newton_v1",
        compiler_profile=adapter.compiler_profile,
        configuration=configuration,
        contract_bindings={
            "problem_contract_hash": compiled.problem.contract_hash,
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


def _compile_portal(model: CanonicalModel) -> _CompiledPortal:
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
    if len(model.nodes) != 4:
        _fail(
            "corotational_portal_node_count_invalid",
            "/nodes",
            "Exactly four portal nodes are required.",
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
    if len(model.elements) != 3:
        _fail(
            "corotational_portal_member_count_invalid",
            "/elements",
            "Exactly three portal members are required.",
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
        _keys(row, required_element_keys, path)
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
        element_coordinates = (coordinates[node_i], coordinates[node_j])
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
            )
        )
        member_sections.append(section)
        member_ids.add(member_id)
        used_sections.add(section_id)

    if len(model.supports) != 2:
        _fail(
            "corotational_portal_support_count_invalid",
            "/supports",
            "Both portal bases must be supported.",
        )
    support_ids: list[str] = []
    fixed: list[int] = []
    for index, row in enumerate(model.supports):
        path = f"/supports/{index}"
        _keys(row, {"node", "dofs"}, path)
        node_id = _stable(row["node"], f"{path}/node")
        raw_dofs = row["dofs"]
        valid_portal_dofs = bool(
            type(raw_dofs) is list
            and all(type(value) is str for value in raw_dofs)
            and set(raw_dofs) == set(_ACTIVE_COMPONENTS)
        )
        if node_id not in node_index or node_id in support_ids or not valid_portal_dofs:
            _fail(
                "corotational_portal_support_invalid",
                path,
                "Two unique nodes must restrain exactly UX, UY and RZ.",
            )
        support_ids.append(node_id)
        dof_offsets = {label: offset for offset, label in enumerate(_ACTIVE_COMPONENTS)}
        support_dofs = tuple(str(value) for value in raw_dofs)
        fixed.extend(
            3 * node_index[node_id] + dof_offsets[label] for label in support_dofs
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
    if not reference_loads:
        _fail(
            "corotational_portal_loads_missing",
            "/loads",
            "At least one nonzero nodal load is required.",
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
            case_id=f"public_corotational_portal_{digest}",
            node_coordinates_m=tuple(coordinates),
            members=tuple(members),
            fixed_global_dofs=tuple(sorted(fixed)),
            reference_external_loads=tuple(sorted(reference_loads)),
            rotation_coordinate_scale_m=_binary_coordinate_scale(max(lengths)),
        )
        compilation = compile_corotational_fiber_frame_portal_profile(
            problem,
            model_content_hash=model.canonical_model_checksum,
        )
    except CorotationalFiberFrameJ1J5Error:
        raise
    except ValueError as exc:
        _fail("corotational_portal_problem_invalid", "/", str(exc))
    return _CompiledPortal(
        problem=problem,
        compilation=compilation,
        node_ids=tuple(node_ids),
        section_by_member=tuple(member_sections),
        support_node_ids=tuple(support_ids),
    )


def _run_corotational_path(
    compiled: _CompiledPortal,
    config: NonlinearFrameConfig,
    restart: bytes | bytearray | memoryview | None,
) -> _CorotationalExecution:
    problem = compiled.problem
    targets = config.target_load_factors
    solver_config = NewtonRaphsonConfig(
        residual_tolerance=config.residual_tolerance,
        increment_tolerance=config.increment_tolerance_m,
        max_iterations=config.maximum_iterations,
        matrix_backend=VECTOR_MATRIX_BACKEND,
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
        path = run_segment(targets)
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
            "end_force_definition": "element_internal_force",
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
        unsupported_features=tuple(dict(row) for row in unsupported_features),
        warnings=tuple(str(row) for row in warnings),
        _checkpoint_bytes=checkpoint_bytes,
    )
    return replace(
        provisional,
        result_hash=canonical_hash(_result_payload(provisional, include_hash=False)),
    )


def _blocked_authority() -> Mapping[str, str]:
    return MappingProxyType(
        {
            "convergence": "not_authoritative",
            "displacement": "not_authoritative",
            "reaction": "not_authoritative",
            "member_force": "not_authoritative",
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


def _artifact_hash(data: bytes | bytearray | memoryview) -> str:
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


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
    "COROTATIONAL_PORTAL_PROFILE",
    "FIXED_CHORD_SERIAL_PROFILE",
    "UNIFIED_NONLINEAR_FRAME_CLAIM_BOUNDARY",
    "UNIFIED_NONLINEAR_FRAME_REPORT_SCHEMA_VERSION",
    "UNIFIED_NONLINEAR_FRAME_SCHEMA_VERSION",
    "NonlinearFrameConfig",
    "NonlinearFrameError",
    "NonlinearFrameProfile",
    "NonlinearFrameResult",
    "NonlinearFrameValidationReport",
    "analyze_nonlinear_frame",
    "validate_nonlinear_frame_manifest",
    "validate_nonlinear_frame_result",
]
