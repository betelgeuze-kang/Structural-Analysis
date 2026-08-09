"""Bounded ModelIR-facing API for multi-member Frame3D load control."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from importlib import resources
import json
import math
from types import MappingProxyType
from typing import Any, Literal, Mapping, NoReturn

from jsonschema import Draft202012Validator, validators
import numpy as np

from structural_analysis.adapters.bounded_frame3d_load_control_model_ir import (
    BoundedFrame3DLoadControlModelIRAdapter,
    BoundedFrame3DLoadControlModelIRAdapterError,
    adapt_bounded_frame3d_load_control_model_ir_v2,
    validate_bounded_frame3d_load_control_model_ir_adapter,
)
from structural_analysis.assembly.corotational_frame3d_global import (
    COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY,
    COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
    COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION,
    CorotationalFrame3DGlobalCheckpoint,
    CorotationalFrame3DGlobalConfig,
    CorotationalFrame3DGlobalError,
    CorotationalFrame3DGlobalSolution,
    CorotationalFrame3DGlobalStep,
    CorotationalFrame3DMemberResult,
    CorotationalFrame3DModel,
    assemble_corotational_frame3d_global,
    initial_corotational_frame3d_global_checkpoint,
    solve_corotational_frame3d_global_load_path,
    validate_corotational_frame3d_global_checkpoint,
)
from structural_analysis.elements.frame3d import FRAME_DOF_LABELS
from structural_analysis.engine_v2.contracts import (
    bind_equation_scaling_to_execution_plan,
    commit_trial_state,
    create_equation_scaling,
    create_execution_plan,
    create_execution_plan_reduced_csr,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateInput,
    commit_trial_material_state_bundle,
    create_initial_material_state_bundle,
    open_trial_material_state_bundle,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    create_nonlinear_numerical_result_ir,
    create_nonlinear_terminal_receipt,
    validate_nonlinear_result_manifest,
)
from structural_analysis.model_ir.types import ModelIRDocument
from structural_analysis.solvers.equation_scaling_6dof import (
    create_equation_scaling_6dof,
    scaled_residual_metrics_6dof,
)


BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE = (
    "bounded_multimember_frame3d_load_control_model_ir_api.v1"
)
BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_VERSION = (
    "bounded-frame3d-load-control-config.v1"
)
BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION = (
    "bounded-frame3d-load-control-result.v1"
)
BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_SCHEMA_VERSION = (
    "bounded-frame3d-load-control-checkpoint-artifact.v1"
)
BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_PATH = (
    "bounded_frame3d_load_control_result_v1.schema.json"
)
BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_SCHEMA_PATH = (
    "bounded_frame3d_load_control_checkpoint_v1.schema.json"
)
BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_PATH = (
    "bounded_frame3d_load_control_config_v1.schema.json"
)
BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_MAX_BYTES = 4 * 1024 * 1024
BOUNDED_FRAME3D_LOAD_CONTROL_CLAIM_BOUNDARY = (
    "This bounded candidate API executes one source-bound 3-16 node, 2-32 member "
    "elastic ModelIR v2 Frame3D load-control path. It returns authoritative "
    "nonlinear numerical ResultIR displacement/convergence, exact durable "
    "checkpoint restart, and bounded solver-derived reactions, member recovery, "
    "and full-node equilibrium. It has no stateful material, distributed load, "
    "offset/release, external-V&V, design, public-product, release, or commercial "
    "authority."
)
_RESULT_ID = "bounded.frame3d.multimember.load-control"
_HASH_ZERO = "sha256:" + "0" * 64
_TRANSLATION_COMPONENTS = ("FX", "FY", "FZ")
_MOMENT_COMPONENTS = ("MX", "MY", "MZ")

_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class BoundedFrame3DLoadControlError(ValueError):
    """Stable candidate API error carrying a code and JSON-pointer path."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class BoundedFrame3DLoadControlConfig:
    load_pattern_id: str
    load_factors: tuple[float, ...]
    solver_config: CorotationalFrame3DGlobalConfig = field(
        default_factory=CorotationalFrame3DGlobalConfig
    )

    def __post_init__(self) -> None:
        if not isinstance(self.load_pattern_id, str) or not self.load_pattern_id:
            raise ValueError("load_pattern_id must be a non-empty stable identifier")
        if type(self.solver_config) is not CorotationalFrame3DGlobalConfig:
            raise ValueError("solver_config must be an exact Frame3D global config")
        if not isinstance(self.load_factors, tuple) or not self.load_factors:
            raise ValueError("load_factors must be a non-empty tuple")
        if len(self.load_factors) > 64:
            raise ValueError("load_factors exceeds the bounded length of 64")
        normalized: list[float] = []
        previous = 0.0
        for index, value in enumerate(self.load_factors):
            if isinstance(value, bool) or type(value) not in (int, float):
                raise ValueError(f"load_factors[{index}] must be finite")
            factor = float(value)
            if not math.isfinite(factor) or factor <= previous:
                raise ValueError(
                    "load_factors must be finite, positive, and increasing"
                )
            normalized.append(factor)
            previous = factor
        if normalized[-1] > 1.0:
            raise ValueError("bounded load_factors must not exceed 1.0")
        solver = self.solver_config
        if solver.maximum_iterations > 100:
            raise ValueError("maximum_iterations exceeds the bounded limit of 100")
        if solver.maximum_condition_number > 1.0e16:
            raise ValueError("maximum_condition_number exceeds the bounded limit")
        if len(solver.line_search_alphas) > 16:
            raise ValueError("line_search_alphas exceeds the bounded length of 16")
        for name in ("residual_relative_tolerance", "increment_relative_tolerance"):
            if getattr(solver, name) > 1.0:
                raise ValueError(f"{name} exceeds the bounded limit of 1.0")
        if solver.residual_absolute_tolerance_kn > 1.0e9:
            raise ValueError("residual_absolute_tolerance_kn exceeds the bounded limit")
        if solver.increment_absolute_tolerance_m > 1.0e6:
            raise ValueError("increment_absolute_tolerance_m exceeds the bounded limit")
        object.__setattr__(self, "load_factors", tuple(normalized))

    @property
    def request_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_VERSION,
            "profile": BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE,
            "load_pattern_id": self.load_pattern_id,
            "load_factors": list(self.load_factors),
            "solver_config": self.solver_config.to_manifest(),
        }


def parse_bounded_frame3d_load_control_config(
    payload: Mapping[str, Any],
) -> BoundedFrame3DLoadControlConfig:
    """Parse the exact JSON-facing bounded solver configuration."""

    if not isinstance(payload, Mapping):
        _fail(
            "bounded_frame3d_load_config_manifest_type_invalid",
            "/config",
            "Configuration manifest must be an object.",
        )
    thawed = _thaw_json(payload)
    _validate_schema(thawed, BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_PATH)
    solver = thawed["solver_config"]
    try:
        config = BoundedFrame3DLoadControlConfig(
            load_pattern_id=thawed["load_pattern_id"],
            load_factors=tuple(thawed["load_factors"]),
            solver_config=CorotationalFrame3DGlobalConfig(
                residual_relative_tolerance=solver["residual_relative_tolerance"],
                residual_absolute_tolerance_kn=solver["residual_absolute_tolerance_kn"],
                increment_relative_tolerance=solver["increment_relative_tolerance"],
                increment_absolute_tolerance_m=solver["increment_absolute_tolerance_m"],
                maximum_iterations=solver["maximum_iterations"],
                maximum_condition_number=solver["maximum_condition_number"],
                line_search_alphas=tuple(solver["line_search"]["alphas"]),
            ),
        )
    except (TypeError, ValueError, OverflowError) as error:
        _fail(
            "bounded_frame3d_load_config_manifest_invalid",
            "/config",
            str(error),
        )
    if not _same_json_scalar_domain(thawed, config.to_dict()):
        _fail(
            "bounded_frame3d_load_config_numeric_domain_mismatch",
            "/config",
            "Configuration changed JSON scalar domains during typed reconstruction.",
        )
    return config


@dataclass(frozen=True)
class BoundedFrame3DLoadControlResult:
    schema_version: str
    profile: str
    status: Literal["ready"]
    contract_pass: bool
    result_hash: str
    source_binding: Mapping[str, Any]
    load_factors: tuple[float, ...]
    solver: Mapping[str, Any]
    numerical_result_ir: Mapping[str, Any]
    node_displacements: tuple[Mapping[str, Any], ...]
    support_reactions: tuple[Mapping[str, Any], ...]
    member_recovery: tuple[Mapping[str, Any], ...]
    full_node_equilibrium: tuple[Mapping[str, Any], ...]
    checkpoint_artifact: Mapping[str, Any]
    metrics: Mapping[str, Any]
    authority: Mapping[str, Any]
    warnings: tuple[str, ...]
    claim_boundary: str = BOUNDED_FRAME3D_LOAD_CONTROL_CLAIM_BOUNDARY
    _adapter: BoundedFrame3DLoadControlModelIRAdapter | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _config: BoundedFrame3DLoadControlConfig | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _checkpoint_artifact_bytes: bytes | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "source_binding",
            "solver",
            "numerical_result_ir",
            "node_displacements",
            "support_reactions",
            "member_recovery",
            "full_node_equilibrium",
            "checkpoint_artifact",
            "metrics",
            "authority",
            "warnings",
        ):
            object.__setattr__(self, name, _deep_freeze_json(getattr(self, name)))

    def checkpoint_artifact_bytes(self) -> bytes:
        if self._checkpoint_artifact_bytes is None:
            raise ValueError("no exact checkpoint artifact is available")
        return self._checkpoint_artifact_bytes

    def manifest_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    def to_dict(self) -> dict[str, Any]:
        return _result_payload(self, include_result_hash=True)


def analyze_bounded_frame3d_load_control_model_ir(
    document: ModelIRDocument,
    config: BoundedFrame3DLoadControlConfig,
    *,
    restart_checkpoint_artifact: bytes | bytearray | memoryview | None = None,
) -> BoundedFrame3DLoadControlResult:
    """Run one exact bounded multi-member Frame3D load-control request."""

    return _analyze_bounded_frame3d_load_control_model_ir(
        document,
        config,
        restart_checkpoint_artifact=restart_checkpoint_artifact,
        maximum_new_steps=None,
    )


def advance_bounded_frame3d_load_control_model_ir(
    document: ModelIRDocument,
    config: BoundedFrame3DLoadControlConfig,
    *,
    maximum_new_steps: int,
    restart_checkpoint_artifact: bytes | bytearray | memoryview | None = None,
) -> BoundedFrame3DLoadControlResult:
    """Advance at most ``maximum_new_steps`` of one full bound load schedule."""

    if type(maximum_new_steps) is not int or maximum_new_steps < 1:
        _fail(
            "bounded_frame3d_load_maximum_new_steps_invalid",
            "/maximum_new_steps",
            "maximum_new_steps must be a positive integer.",
        )
    return _analyze_bounded_frame3d_load_control_model_ir(
        document,
        config,
        restart_checkpoint_artifact=restart_checkpoint_artifact,
        maximum_new_steps=maximum_new_steps,
    )


def bounded_frame3d_load_control_resume_contract_hash(
    document: ModelIRDocument,
    config: BoundedFrame3DLoadControlConfig,
) -> str:
    """Return the public full-schedule checkpoint resume contract hash."""

    if (
        type(document) is not ModelIRDocument
        or type(config) is not BoundedFrame3DLoadControlConfig
    ):
        _fail(
            "bounded_frame3d_load_resume_contract_input_invalid",
            "/",
            "Expected an exact ModelIR document and load-control config.",
        )
    try:
        adapter = adapt_bounded_frame3d_load_control_model_ir_v2(
            document,
            load_pattern_id=config.load_pattern_id,
        )
    except BoundedFrame3DLoadControlModelIRAdapterError as error:
        _fail(error.code, error.path, error.detail)
    return _resume_contract_hash(adapter, config)


def _analyze_bounded_frame3d_load_control_model_ir(
    document: ModelIRDocument,
    config: BoundedFrame3DLoadControlConfig,
    *,
    restart_checkpoint_artifact: bytes | bytearray | memoryview | None,
    maximum_new_steps: int | None,
) -> BoundedFrame3DLoadControlResult:

    if type(document) is not ModelIRDocument:
        _fail(
            "bounded_frame3d_load_document_type_invalid",
            "/",
            "Expected ModelIRDocument.",
        )
    if type(config) is not BoundedFrame3DLoadControlConfig:
        _fail(
            "bounded_frame3d_load_config_type_invalid",
            "/config",
            "Expected exact config.",
        )
    try:
        adapter = adapt_bounded_frame3d_load_control_model_ir_v2(
            document,
            load_pattern_id=config.load_pattern_id,
        )
    except BoundedFrame3DLoadControlModelIRAdapterError as error:
        _fail(error.code, error.path, error.detail)
    model = adapter.model
    resume_from = None
    if restart_checkpoint_artifact is not None:
        if not isinstance(restart_checkpoint_artifact, (bytes, bytearray, memoryview)):
            _fail(
                "bounded_frame3d_load_checkpoint_artifact_type_invalid",
                "/restart_checkpoint_artifact",
                "Checkpoint artifact must be bytes-like.",
            )
        resume_from = _checkpoint_from_artifact(
            bytes(restart_checkpoint_artifact),
            adapter=adapter,
            config=config,
        )
    start_checkpoint = (
        initial_corotational_frame3d_global_checkpoint(
            model,
            config=config.solver_config,
        )
        if resume_from is None
        else resume_from
    )
    completed_prefix_count = _completed_prefix_count(
        config.load_factors,
        start_checkpoint.load_factor,
    )
    remaining_factors = config.load_factors[completed_prefix_count:]
    if maximum_new_steps is not None:
        remaining_factors = remaining_factors[:maximum_new_steps]
    if not remaining_factors:
        _fail(
            "bounded_frame3d_load_schedule_already_complete",
            "/restart_checkpoint_artifact/checkpoint/load_factor",
            "The checkpoint already completes the configured load schedule.",
        )
    try:
        solution = solve_corotational_frame3d_global_load_path(
            model,
            remaining_factors,
            config=config.solver_config,
            resume_from=resume_from,
        )
    except (CorotationalFrame3DGlobalError, ValueError) as error:
        _fail("bounded_frame3d_load_solver_failed", "/solver", str(error))
    if not solution.contract_pass:
        _fail(
            "bounded_frame3d_load_solver_contract_blocked",
            "/solver/contract_pass",
            "Solver did not close every convergence gate.",
        )

    terminal = solution.steps[-1]
    displacement = np.asarray(solution.final_checkpoint.displacement, dtype="<f8")
    recovery = _recovery_payload(
        adapter=adapter,
        model=model,
        displacement=displacement,
        load_factor=solution.final_checkpoint.load_factor,
        terminal_members=terminal.members,
        solver_config=config.solver_config,
    )
    if not recovery["full_node_equilibrium_pass"]:
        _fail(
            "bounded_frame3d_load_full_node_equilibrium_failed",
            "/full_node_equilibrium",
            "Final reassembled all-node balance exceeded tolerance.",
        )
    source_solver_receipt = _source_solver_receipt(solution)
    step_rows = tuple(step.to_dict() for step in solution.steps)
    path_history = _result_ir_path_history(step_rows)
    numerical_result_ir = _create_result_ir(
        adapter=adapter,
        model=model,
        config=config,
        source_result_hash=solution.result_hash,
        step_rows=step_rows,
        path_history=path_history,
    )
    checkpoint_payload, checkpoint_bytes = _checkpoint_artifact(
        adapter=adapter,
        config=config,
        checkpoint=solution.final_checkpoint,
    )
    solver = {
        "source_receipt": source_solver_receipt,
        "execution": {
            "start_checkpoint": start_checkpoint.to_dict(),
            "requested_load_factors": list(config.load_factors),
            "accepted_load_factors": [step.load_factor for step in solution.steps],
            "maximum_new_steps": maximum_new_steps,
            "completed_prefix_count": completed_prefix_count + len(solution.steps),
            "remaining_load_factor_count": (
                len(config.load_factors) - completed_prefix_count - len(solution.steps)
            ),
            "state_epoch_scope": "current_request_suffix",
        },
        "full_node_equilibrium": {
            "equilibrium_scaling_hash": recovery["equation_scaling_hash"],
            "scaled_tolerance": recovery["scaled_tolerance"],
            "maximum_scaled_balance_residual": recovery["maximum_scaled_balance"],
            "maximum_force_balance_residual_n": recovery["maximum_force_balance_n"],
            "maximum_moment_balance_residual_n_m": recovery[
                "maximum_moment_balance_n_m"
            ],
            "force_tolerance_n": recovery["force_tolerance_n"],
            "moment_tolerance_n_m": recovery["moment_tolerance_n_m"],
            "contract_pass": recovery["full_node_equilibrium_pass"],
        },
    }
    metrics = {
        "final_load_factor": solution.final_checkpoint.load_factor,
        "accepted_step_count": len(solution.steps),
        "numerical_result_state_epoch": len(solution.steps),
        "state_epoch_scope": "current_request_suffix",
        "completed_prefix_count": completed_prefix_count + len(solution.steps),
        "remaining_load_factor_count": (
            len(config.load_factors) - completed_prefix_count - len(solution.steps)
        ),
        "node_count": len(adapter.node_ids),
        "member_count": len(adapter.member_ids),
        "fallback_count": 0,
        "regularization_count": 0,
    }
    authority = {
        "candidate_api_exposed": True,
        "capability_registry_public": False,
        "workbench_execution": False,
        "numerical_result_ir": "authoritative_bounded",
        "numerical_result_ir_reaction_authority": False,
        "numerical_result_ir_member_force_authority": False,
        "solver_derived_reaction_recovery": "bounded_candidate",
        "solver_derived_member_recovery": "bounded_candidate",
        "full_node_equilibrium": "authoritative_reassembled",
        "external_vv_level": 0,
        "independent_operator_attached": False,
        "design_authority": False,
        "public_product_promotion": False,
        "release_eligible": False,
        "commercial_use": False,
    }
    provisional = BoundedFrame3DLoadControlResult(
        schema_version=BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION,
        profile=BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE,
        status="ready",
        contract_pass=True,
        result_hash=_HASH_ZERO,
        source_binding={
            **adapter.to_dict(),
            "request_hash": config.request_hash,
        },
        load_factors=config.load_factors,
        solver=solver,
        numerical_result_ir=numerical_result_ir,
        node_displacements=recovery["node_displacements"],
        support_reactions=recovery["support_reactions"],
        member_recovery=recovery["member_recovery"],
        full_node_equilibrium=recovery["full_node_equilibrium"],
        checkpoint_artifact=checkpoint_payload,
        metrics=metrics,
        authority=authority,
        warnings=(
            "experimental_bounded_multimember_frame3d_load_control",
            "public_product_promotion_false",
            "external_vv_not_attached",
        ),
        _adapter=adapter,
        _config=config,
        _checkpoint_artifact_bytes=checkpoint_bytes,
    )
    result = replace(
        provisional,
        result_hash=canonical_hash(
            _result_payload(provisional, include_result_hash=False)
        ),
    )
    return validate_bounded_frame3d_load_control_result(result)


def _source_solver_receipt(
    solution: CorotationalFrame3DGlobalSolution,
) -> dict[str, Any]:
    payload = {
        "schema_version": solution.schema_version,
        "profile": solution.profile,
        "model_hash": solution.model_hash,
        "solver_contract_hash": solution.solver_contract_hash,
        "start_checkpoint_hash": solution.start_checkpoint_hash,
        "steps": [step.to_dict() for step in solution.steps],
        "maximum_free_residual_inf_norm_kn": (
            solution.maximum_free_residual_inf_norm_kn
        ),
        "maximum_scaled_residual_inf_norm": (solution.maximum_scaled_residual_inf_norm),
        "maximum_scaled_increment_inf_norm": (
            solution.maximum_scaled_increment_inf_norm
        ),
        "equation_scaling": solution.equation_scaling,
        "exact_checkpoint_resume_supported": (
            solution.exact_checkpoint_resume_supported
        ),
        "regularization_used": solution.regularization_used,
        "fallback_used": solution.fallback_used,
        "contract_pass": solution.contract_pass,
        "claim_boundary": solution.claim_boundary,
    }
    if canonical_hash(payload) != solution.result_hash:
        _fail(
            "bounded_frame3d_load_source_solver_hash_mismatch",
            "/solver/source_receipt/result_hash",
            "Source solver receipt hash is inconsistent.",
        )
    return {**payload, "result_hash": solution.result_hash}


def _result_ir_path_history(
    step_rows: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {
            "load_factor": row["load_factor"],
            "checkpoint_hash": row["checkpoint"]["checkpoint_hash"],
            "converged_iterations": row["checkpoint"]["converged_iterations"],
            "scaled_residual_inf_norm": row["scaled_residual_inf_norm"],
            "scaled_residual_tolerance": row["scaled_residual_tolerance"],
            "scaled_increment_inf_norm": row["scaled_increment_inf_norm"],
            "scaled_increment_tolerance": row["scaled_increment_tolerance"],
        }
        for row in step_rows
    )


def validate_bounded_frame3d_load_control_result(
    result: BoundedFrame3DLoadControlResult,
) -> BoundedFrame3DLoadControlResult:
    if type(result) is not BoundedFrame3DLoadControlResult:
        _fail("bounded_frame3d_load_result_type_invalid", "/", "Expected exact result.")
    payload = result.to_dict()
    _validate_schema(payload, BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_PATH)
    if result.result_hash != canonical_hash(
        _result_payload(result, include_result_hash=False)
    ):
        _fail(
            "bounded_frame3d_load_result_hash_mismatch",
            "/result_hash",
            "Result hash does not match canonical payload.",
        )
    try:
        validate_nonlinear_result_manifest(_thaw_json(result.numerical_result_ir))
    except ValueError as error:
        _fail(
            "bounded_frame3d_load_numerical_result_ir_invalid",
            "/numerical_result_ir",
            str(error),
        )
    adapter = result._adapter
    config = result._config
    if adapter is None or config is None:
        _fail(
            "bounded_frame3d_load_result_source_adapter_missing",
            "/source_binding",
            "In-memory validation requires retained adapter and config.",
        )
    if not _same_json_scalar_domain(
        list(result.load_factors), list(config.load_factors)
    ):
        _fail(
            "bounded_frame3d_load_result_schedule_mismatch",
            "/load_factors",
            "Result schedule does not match the retained full request.",
        )
    if (
        result.claim_boundary != BOUNDED_FRAME3D_LOAD_CONTROL_CLAIM_BOUNDARY
        or result.warnings
        != (
            "experimental_bounded_multimember_frame3d_load_control",
            "public_product_promotion_false",
            "external_vv_not_attached",
        )
    ):
        _fail(
            "bounded_frame3d_load_result_claim_boundary_mismatch",
            "/claim_boundary",
            "Result claim boundary or warnings were changed.",
        )
    validate_bounded_frame3d_load_control_model_ir_adapter(adapter)
    expected_source_binding = {
        **adapter.to_dict(),
        "request_hash": config.request_hash,
    }
    if not _same_json_scalar_domain(
        _thaw_json(result.source_binding),
        expected_source_binding,
    ):
        _fail(
            "bounded_frame3d_load_result_source_binding_mismatch",
            "/source_binding",
            "Result source binding does not match retained adapter.",
        )
    checkpoint_bytes = result.checkpoint_artifact_bytes()
    persisted_checkpoint_payload = _parse_canonical_json_object(
        checkpoint_bytes,
        code_prefix="bounded_frame3d_load_checkpoint",
        maximum_bytes=BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_MAX_BYTES,
    )
    if not _same_json_scalar_domain(
        persisted_checkpoint_payload,
        _thaw_json(result.checkpoint_artifact),
    ):
        _fail(
            "bounded_frame3d_load_result_checkpoint_artifact_mismatch",
            "/checkpoint_artifact",
            "Embedded checkpoint descriptor differs from the persisted bytes.",
        )
    checkpoint = _checkpoint_from_artifact(
        checkpoint_bytes,
        adapter=adapter,
        config=config,
    )
    step_rows = _validate_source_solver_receipt(
        result.solver,
        adapter=adapter,
        config=config,
        terminal_checkpoint=checkpoint,
    )
    displacement = _displacement_from_rows(result.node_displacements, adapter.node_ids)
    if tuple(displacement) != checkpoint.displacement:
        _fail(
            "bounded_frame3d_load_result_checkpoint_state_mismatch",
            "/node_displacements",
            "Published node displacement does not match the terminal checkpoint.",
        )
    expected = _recovery_payload(
        adapter=adapter,
        model=adapter.model,
        displacement=displacement,
        load_factor=checkpoint.load_factor,
        terminal_members=None,
        solver_config=config.solver_config,
    )
    for field_name in (
        "node_displacements",
        "support_reactions",
        "member_recovery",
        "full_node_equilibrium",
    ):
        if not _same_json_scalar_domain(
            _thaw_json(getattr(result, field_name)),
            list(expected[field_name]),
        ):
            _fail(
                "bounded_frame3d_load_result_recovery_mismatch",
                f"/{field_name}",
                "Published recovery does not replay from the terminal checkpoint.",
            )
    expected_equilibrium = {
        "equilibrium_scaling_hash": expected["equation_scaling_hash"],
        "scaled_tolerance": expected["scaled_tolerance"],
        "maximum_scaled_balance_residual": expected["maximum_scaled_balance"],
        "maximum_force_balance_residual_n": expected["maximum_force_balance_n"],
        "maximum_moment_balance_residual_n_m": expected["maximum_moment_balance_n_m"],
        "force_tolerance_n": expected["force_tolerance_n"],
        "moment_tolerance_n_m": expected["moment_tolerance_n_m"],
        "contract_pass": expected["full_node_equilibrium_pass"],
    }
    if not _same_json_scalar_domain(
        _thaw_json(result.solver["full_node_equilibrium"]),
        expected_equilibrium,
    ):
        _fail(
            "bounded_frame3d_load_result_equilibrium_metrics_mismatch",
            "/solver/full_node_equilibrium",
            "Published equilibrium metrics do not replay from the checkpoint.",
        )
    source_receipt = _thaw_json(result.solver["source_receipt"])
    path_history = _result_ir_path_history(step_rows)
    expected_numerical_result_ir = _create_result_ir(
        adapter=adapter,
        model=adapter.model,
        config=config,
        source_result_hash=source_receipt["result_hash"],
        step_rows=step_rows,
        path_history=path_history,
    )
    if not _same_json_scalar_domain(
        _thaw_json(result.numerical_result_ir),
        expected_numerical_result_ir,
    ):
        _fail(
            "bounded_frame3d_load_numerical_result_ir_binding_mismatch",
            "/numerical_result_ir",
            "Numerical ResultIR does not replay from source-bound solver steps.",
        )
    execution = _thaw_json(result.solver["execution"])
    expected_metrics = {
        "final_load_factor": checkpoint.load_factor,
        "accepted_step_count": len(step_rows),
        "numerical_result_state_epoch": len(step_rows),
        "state_epoch_scope": "current_request_suffix",
        "completed_prefix_count": execution["completed_prefix_count"],
        "remaining_load_factor_count": execution["remaining_load_factor_count"],
        "node_count": len(adapter.node_ids),
        "member_count": len(adapter.member_ids),
        "fallback_count": 0,
        "regularization_count": 0,
    }
    if not _same_json_scalar_domain(_thaw_json(result.metrics), expected_metrics):
        _fail(
            "bounded_frame3d_load_result_metrics_mismatch",
            "/metrics",
            "Result metrics do not match the replayed request suffix.",
        )
    expected_authority = {
        "candidate_api_exposed": True,
        "capability_registry_public": False,
        "workbench_execution": False,
        "numerical_result_ir": "authoritative_bounded",
        "numerical_result_ir_reaction_authority": False,
        "numerical_result_ir_member_force_authority": False,
        "solver_derived_reaction_recovery": "bounded_candidate",
        "solver_derived_member_recovery": "bounded_candidate",
        "full_node_equilibrium": "authoritative_reassembled",
        "external_vv_level": 0,
        "independent_operator_attached": False,
        "design_authority": False,
        "public_product_promotion": False,
        "release_eligible": False,
        "commercial_use": False,
    }
    if not _same_json_scalar_domain(
        _thaw_json(result.authority),
        expected_authority,
    ):
        _fail(
            "bounded_frame3d_load_result_authority_mismatch",
            "/authority",
            "Candidate authority boundary cannot be changed.",
        )
    return result


def validate_bounded_frame3d_load_control_result_manifest(
    payload_or_bytes: Mapping[str, Any] | bytes | bytearray | memoryview,
    *,
    document: ModelIRDocument,
    config: BoundedFrame3DLoadControlConfig,
    checkpoint_artifact_bytes: bytes | bytearray | memoryview,
) -> BoundedFrame3DLoadControlResult:
    """Rehydrate and replay one persisted result without hidden process state."""

    if isinstance(payload_or_bytes, (bytes, bytearray, memoryview)):
        payload = _parse_canonical_json_object(
            bytes(payload_or_bytes),
            code_prefix="bounded_frame3d_load_result_manifest",
            maximum_bytes=BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_MAX_BYTES * 8,
        )
    elif isinstance(payload_or_bytes, Mapping):
        payload = _thaw_json(payload_or_bytes)
    else:
        _fail(
            "bounded_frame3d_load_result_manifest_type_invalid",
            "/",
            "Result manifest must be a mapping or canonical JSON bytes.",
        )
    _validate_schema(payload, BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_PATH)
    if (
        type(document) is not ModelIRDocument
        or type(config) is not BoundedFrame3DLoadControlConfig
    ):
        _fail(
            "bounded_frame3d_load_result_manifest_source_invalid",
            "/source_binding",
            "Expected an exact ModelIR document and load-control config.",
        )
    if not isinstance(checkpoint_artifact_bytes, (bytes, bytearray, memoryview)):
        _fail(
            "bounded_frame3d_load_result_manifest_checkpoint_type_invalid",
            "/checkpoint_artifact",
            "Checkpoint artifact must be bytes-like.",
        )
    try:
        adapter = adapt_bounded_frame3d_load_control_model_ir_v2(
            document,
            load_pattern_id=config.load_pattern_id,
        )
    except BoundedFrame3DLoadControlModelIRAdapterError as error:
        _fail(error.code, error.path, error.detail)
    result = BoundedFrame3DLoadControlResult(
        schema_version=payload["schema_version"],
        profile=payload["profile"],
        status=payload["status"],
        contract_pass=payload["contract_pass"],
        result_hash=payload["result_hash"],
        source_binding=payload["source_binding"],
        load_factors=tuple(payload["load_factors"]),
        solver=payload["solver"],
        numerical_result_ir=payload["numerical_result_ir"],
        node_displacements=tuple(payload["node_displacements"]),
        support_reactions=tuple(payload["support_reactions"]),
        member_recovery=tuple(payload["member_recovery"]),
        full_node_equilibrium=tuple(payload["full_node_equilibrium"]),
        checkpoint_artifact=payload["checkpoint_artifact"],
        metrics=payload["metrics"],
        authority=payload["authority"],
        warnings=tuple(payload["warnings"]),
        claim_boundary=payload["claim_boundary"],
        _adapter=adapter,
        _config=config,
        _checkpoint_artifact_bytes=bytes(checkpoint_artifact_bytes),
    )
    if not _same_json_scalar_domain(payload, result.to_dict()):
        _fail(
            "bounded_frame3d_load_result_manifest_numeric_domain_mismatch",
            "/",
            "Persisted manifest changed JSON scalar domains during rehydration.",
        )
    return validate_bounded_frame3d_load_control_result(result)


def _validate_source_solver_receipt(
    solver_value: Mapping[str, Any],
    *,
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    config: BoundedFrame3DLoadControlConfig,
    terminal_checkpoint: CorotationalFrame3DGlobalCheckpoint,
) -> tuple[Mapping[str, Any], ...]:
    solver = _thaw_json(solver_value)
    if set(solver) != {"source_receipt", "execution", "full_node_equilibrium"}:
        _fail(
            "bounded_frame3d_load_solver_envelope_invalid",
            "/solver",
            "Solver envelope fields are not exact.",
        )
    receipt = solver["source_receipt"]
    receipt_fields = {
        "schema_version",
        "profile",
        "model_hash",
        "solver_contract_hash",
        "start_checkpoint_hash",
        "steps",
        "maximum_free_residual_inf_norm_kn",
        "maximum_scaled_residual_inf_norm",
        "maximum_scaled_increment_inf_norm",
        "equation_scaling",
        "result_hash",
        "exact_checkpoint_resume_supported",
        "regularization_used",
        "fallback_used",
        "contract_pass",
        "claim_boundary",
    }
    if not isinstance(receipt, dict) or set(receipt) != receipt_fields:
        _fail(
            "bounded_frame3d_load_source_solver_receipt_shape_invalid",
            "/solver/source_receipt",
            "Source solver receipt fields are not exact.",
        )
    _require_finite_json(receipt, "/solver/source_receipt")
    hash_payload = {
        key: value for key, value in receipt.items() if key != "result_hash"
    }
    if receipt["result_hash"] != canonical_hash(hash_payload):
        _fail(
            "bounded_frame3d_load_source_solver_hash_mismatch",
            "/solver/source_receipt/result_hash",
            "Source solver receipt hash mismatch.",
        )
    expected_scaling = create_equation_scaling_6dof(
        source_identity_hash=adapter.model.model_hash,
        node_coordinates_m=adapter.model.node_coordinates_m,
        reference_equation_load=adapter.model.reference_load_kn,
        free_dofs=adapter.model.free_dofs,
    ).to_manifest()
    expected_header = {
        "schema_version": COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION,
        "profile": COROTATIONAL_FRAME3D_GLOBAL_PROFILE,
        "model_hash": adapter.model_hash,
        "solver_contract_hash": config.solver_config.contract_hash,
        "equation_scaling": expected_scaling,
        "exact_checkpoint_resume_supported": True,
        "regularization_used": False,
        "fallback_used": False,
        "contract_pass": True,
        "claim_boundary": COROTATIONAL_FRAME3D_GLOBAL_CLAIM_BOUNDARY,
    }
    for name, expected in expected_header.items():
        if receipt[name] != expected:
            _fail(
                "bounded_frame3d_load_source_solver_binding_mismatch",
                f"/solver/source_receipt/{name}",
                "Source solver receipt is detached from the request.",
            )

    execution = solver["execution"]
    execution_fields = {
        "start_checkpoint",
        "requested_load_factors",
        "accepted_load_factors",
        "maximum_new_steps",
        "completed_prefix_count",
        "remaining_load_factor_count",
        "state_epoch_scope",
    }
    if not isinstance(execution, dict) or set(execution) != execution_fields:
        _fail(
            "bounded_frame3d_load_execution_envelope_invalid",
            "/solver/execution",
            "Execution envelope fields are not exact.",
        )
    start_checkpoint = _checkpoint_from_payload(
        execution["start_checkpoint"],
        path="/solver/execution/start_checkpoint",
        model=adapter.model,
        config=config.solver_config,
    )
    if start_checkpoint.checkpoint_hash != receipt["start_checkpoint_hash"]:
        _fail(
            "bounded_frame3d_load_start_checkpoint_hash_mismatch",
            "/solver/source_receipt/start_checkpoint_hash",
            "Start checkpoint hash does not match the persisted start state.",
        )
    if not _same_json_scalar_domain(
        execution["requested_load_factors"],
        list(config.load_factors),
    ):
        _fail(
            "bounded_frame3d_load_requested_schedule_mismatch",
            "/solver/execution/requested_load_factors",
            "Execution schedule does not match the full request contract.",
        )
    maximum_new_steps = execution["maximum_new_steps"]
    if maximum_new_steps is not None and (
        type(maximum_new_steps) is not int or maximum_new_steps < 1
    ):
        _fail(
            "bounded_frame3d_load_execution_step_bound_invalid",
            "/solver/execution/maximum_new_steps",
            "maximum_new_steps must be null or a positive integer.",
        )
    start_count = _completed_prefix_count(
        config.load_factors,
        start_checkpoint.load_factor,
    )
    available = config.load_factors[start_count:]
    expected_factors = (
        available if maximum_new_steps is None else available[:maximum_new_steps]
    )
    steps = receipt["steps"]
    if not isinstance(steps, list) or not steps:
        _fail(
            "bounded_frame3d_load_source_steps_invalid",
            "/solver/source_receipt/steps",
            "Source solver receipt must contain accepted steps.",
        )
    accepted_factors = [
        row.get("load_factor") for row in steps if isinstance(row, dict)
    ]
    if (
        len(accepted_factors) != len(steps)
        or not _same_json_scalar_domain(accepted_factors, list(expected_factors))
        or not _same_json_scalar_domain(
            execution["accepted_load_factors"],
            accepted_factors,
        )
    ):
        _fail(
            "bounded_frame3d_load_accepted_schedule_mismatch",
            "/solver/execution/accepted_load_factors",
            "Accepted factors are not the exact next configured schedule prefix.",
        )
    try:
        replayed_solution = solve_corotational_frame3d_global_load_path(
            adapter.model,
            expected_factors,
            config=config.solver_config,
            resume_from=start_checkpoint,
        )
    except (CorotationalFrame3DGlobalError, ValueError) as error:
        _fail(
            "bounded_frame3d_load_source_solver_replay_failed",
            "/solver/source_receipt",
            str(error),
        )
    expected_receipt = _source_solver_receipt(replayed_solution)
    if not _same_json_scalar_domain(receipt, expected_receipt):
        _fail(
            "bounded_frame3d_load_source_solver_replay_mismatch",
            "/solver/source_receipt",
            "Persisted solver receipt differs from deterministic source replay.",
        )
    steps = expected_receipt["steps"]
    completed_count = start_count + len(steps)
    if (
        type(execution["completed_prefix_count"]) is not int
        or execution["completed_prefix_count"] != completed_count
        or type(execution["remaining_load_factor_count"]) is not int
        or execution["remaining_load_factor_count"]
        != len(config.load_factors) - completed_count
        or execution["state_epoch_scope"] != "current_request_suffix"
    ):
        _fail(
            "bounded_frame3d_load_execution_progress_mismatch",
            "/solver/execution",
            "Execution progress does not match accepted checkpoint lineage.",
        )

    expected_step_fields = set(CorotationalFrame3DGlobalStep.__dataclass_fields__)
    expected_member_fields = set(CorotationalFrame3DMemberResult.__dataclass_fields__)
    previous_hash = start_checkpoint.checkpoint_hash
    checkpoints: list[CorotationalFrame3DGlobalCheckpoint] = []
    for index, row in enumerate(steps):
        path = f"/solver/source_receipt/steps/{index}"
        if not isinstance(row, dict) or set(row) != expected_step_fields:
            _fail(
                "bounded_frame3d_load_source_step_shape_invalid",
                path,
                "Source step fields are not exact.",
            )
        for name in (
            "residual_gate_passed",
            "increment_gate_passed",
            "line_search_valid",
            "final_reassembled_equilibrium_passed",
            "parent_state_immutable",
        ):
            if row[name] is not True:
                _fail(
                    "bounded_frame3d_load_source_step_gate_failed",
                    f"{path}/{name}",
                    "Every accepted source step gate must pass.",
                )
        if row["equation_scaling_hash"] != expected_scaling["scaling_hash"]:
            _fail(
                "bounded_frame3d_load_source_step_scaling_mismatch",
                f"{path}/equation_scaling_hash",
                "Step equation scaling is detached from the model.",
            )
        checkpoint = _checkpoint_from_payload(
            row["checkpoint"],
            path=f"{path}/checkpoint",
            model=adapter.model,
            config=config.solver_config,
        )
        if (
            checkpoint.parent_checkpoint_hash != previous_hash
            or checkpoint.load_factor != expected_factors[index]
            or row["load_factor"] != checkpoint.load_factor
        ):
            _fail(
                "bounded_frame3d_load_source_checkpoint_lineage_mismatch",
                f"{path}/checkpoint",
                "Accepted checkpoint lineage or load factor is invalid.",
            )
        expected_applied = [
            checkpoint.load_factor * value for value in adapter.model.reference_load_kn
        ]
        if not _same_json_scalar_domain(row["applied_load"], expected_applied):
            _fail(
                "bounded_frame3d_load_source_applied_load_mismatch",
                f"{path}/applied_load",
                "Applied load does not match factor times reference load.",
            )
        members = row["members"]
        if (
            not isinstance(members, (list, tuple))
            or [member.get("member_id") for member in members]
            != list(adapter.member_ids)
            or any(
                not isinstance(member, dict) or set(member) != expected_member_fields
                for member in members
            )
        ):
            _fail(
                "bounded_frame3d_load_source_member_order_mismatch",
                f"{path}/members",
                "Source member recovery order is detached from the adapter.",
            )
        previous_hash = checkpoint.checkpoint_hash
        checkpoints.append(checkpoint)
    if not _same_json_scalar_domain(
        checkpoints[-1].to_dict(),
        terminal_checkpoint.to_dict(),
    ):
        _fail(
            "bounded_frame3d_load_terminal_checkpoint_mismatch",
            "/checkpoint_artifact/checkpoint",
            "Terminal source checkpoint differs from the persisted artifact.",
        )
    expected_maxima = {
        "maximum_free_residual_inf_norm_kn": max(
            row["free_residual_inf_norm_kn"] for row in steps
        ),
        "maximum_scaled_residual_inf_norm": max(
            row["scaled_residual_inf_norm"] for row in steps
        ),
        "maximum_scaled_increment_inf_norm": max(
            row["scaled_increment_inf_norm"] for row in steps
        ),
    }
    for name, expected in expected_maxima.items():
        if receipt[name] != expected:
            _fail(
                "bounded_frame3d_load_source_solver_summary_mismatch",
                f"/solver/source_receipt/{name}",
                "Source solver summary does not match accepted steps.",
            )
    return tuple(steps)


def _create_result_ir(
    *,
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    model: CorotationalFrame3DModel,
    config: BoundedFrame3DLoadControlConfig,
    source_result_hash: str,
    step_rows: tuple[Mapping[str, Any], ...],
    path_history: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    if not step_rows:
        _fail(
            "bounded_frame3d_load_result_ir_path_empty",
            "/solver/source_receipt/steps",
            "At least one accepted source step is required.",
        )
    total_dofs = model.total_dofs
    reference_load_n = immutable_array(
        np.asarray(model.reference_load_kn, dtype="<f8") * 1000.0,
        dtype="<f8",
    )
    operator_hash = canonical_hash(
        {
            "model_hash": model.model_hash,
            "solver_contract_hash": config.solver_config.contract_hash,
        }
    )
    restrained = np.asarray(model.restrained_dofs, dtype="<i4")
    free = np.asarray(model.free_dofs, dtype="<i4")
    global_to_free = np.full(total_dofs, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    element_global_dofs = np.asarray(
        [
            list(range(6 * member.node_i, 6 * member.node_i + 6))
            + list(range(6 * member.node_j, 6 * member.node_j + 6))
            for member in model.members
        ],
        dtype="<i4",
    )
    base_plan = create_execution_plan(
        model_ir_content_hash=adapter.model_ir_content_hash,
        solver_buffer_schema_version="bounded-frame3d-load-control-buffers.v1",
        solver_numeric_buffer_hash=canonical_hash(
            {
                "model_hash": model.model_hash,
                "reference_load_hash": array_data_hash(reference_load_n),
            }
        ),
        solver_entity_mapping_hash=adapter.entity_mapping_hash,
        solver_artifact_hash=canonical_hash(
            {"profile": COROTATIONAL_FRAME3D_GLOBAL_PROFILE}
        ),
        load_pattern_id=adapter.load_pattern_id,
        operator_id="bounded-multimember-corotational-frame3d-load-control",
        operator_version="bounded-multimember-corotational-frame3d-load-control.v1",
        operator_hash=operator_hash,
        node_ids=adapter.node_ids,
        element_ids=adapter.member_ids,
        node_dof_indices=np.arange(total_dofs, dtype="<i4").reshape((-1, 6)),
        global_to_free=global_to_free,
        element_global_dofs=element_global_dofs,
        constrained_dofs=restrained,
        free_dofs=free,
        csr_row_ptr=np.arange(0, total_dofs * total_dofs + 1, total_dofs, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(total_dofs, dtype="<i4"), total_dofs),
    )
    coordinates = np.asarray(model.node_coordinates_m, dtype="<f8")
    scaling = create_equation_scaling(
        execution_plan=base_plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load_n,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base_plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load_n,
    )
    reduced = create_execution_plan_reduced_csr(
        plan, operator_numeric_values_hash=operator_hash
    )
    committed_state = create_initial_state(plan)
    initial_entries = tuple(
        MaterialStateInput(
            entity_id=f"element.{member_id}",
            integration_point_id="ip.0",
            material_type_id="linear.elastic.isotropic",
            material_schema_version="elastic-no-history.v1",
            state_bytes=f"elastic-no-history:{member_id}".encode("utf-8"),
        )
        for member_id in adapter.member_ids
    )
    bundle = create_initial_material_state_bundle(
        bundle_id="bounded.frame3d.multimember.elastic.initial",
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        solver_state_hash=committed_state.state_hash,
        entries=initial_entries,
    )
    for index, row in enumerate(step_rows, start=1):
        checkpoint = row["checkpoint"]
        displacement = immutable_array(checkpoint["displacement"], dtype="<f8")
        trial_state = open_trial_state(
            committed_state,
            displacement,
            load_step=index,
            iteration=int(checkpoint["converged_iterations"]),
            load_factor=float(row["load_factor"]),
            time_s=0.0,
            expected_plan=plan,
        )
        next_state = commit_trial_state(
            committed_state,
            trial_state,
            expected_plan=plan,
        )
        accepted_entries = tuple(
            MaterialStateInput(
                entity_id=descriptor.entity_id,
                integration_point_id=descriptor.integration_point_id,
                material_type_id=descriptor.material_type_id,
                material_schema_version=descriptor.material_schema_version,
                state_bytes=bundle.state_bytes(descriptor.index),
                parent_state_data_hash=descriptor.data_hash,
            )
            for descriptor in bundle.entries
        )
        trial_bundle = open_trial_material_state_bundle(
            bundle,
            solver_state_hash=trial_state.state_hash,
            entries=accepted_entries,
        )
        bundle = commit_trial_material_state_bundle(
            bundle,
            trial_bundle,
            solver_state_hash=next_state.state_hash,
        )
        committed_state = next_state
    terminal = step_rows[-1]
    displacement = immutable_array(
        terminal["checkpoint"]["displacement"],
        dtype="<f8",
    )
    free_solution = immutable_array(displacement[free], dtype="<f8")
    terminal_receipt = create_nonlinear_terminal_receipt(
        source_solver_schema_version=COROTATIONAL_FRAME3D_GLOBAL_SCHEMA_VERSION,
        source_solver_receipt_hash=source_result_hash,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_solution_data_hash=array_data_hash(free_solution),
        solver_coordinate_scaling_receipt_hash=canonical_hash(
            {"equation_scaling_hash": scaling.scaling_hash}
        ),
        state_hash=committed_state.state_hash,
        material_state_bundle_hash=bundle.bundle_hash,
        path_history_hash=canonical_hash(list(path_history)),
        terminal_reason="converged_residual_and_increment",
        converged=True,
        final_residual_linf=float(terminal["scaled_residual_inf_norm"]),
        residual_tolerance_linf=float(terminal["scaled_residual_tolerance"]),
        final_increment_linf=float(terminal["scaled_increment_inf_norm"]),
        increment_tolerance_linf=float(terminal["scaled_increment_tolerance"]),
        accepted_step_count=len(step_rows),
        fallback_count=0,
        regularization_count=0,
    )
    result = create_nonlinear_numerical_result_ir(
        result_id=_RESULT_ID,
        execution_plan=plan,
        equation_scaling=scaling,
        reduced_csr=reduced,
        committed_state=committed_state,
        material_state_bundle=bundle,
        terminal_receipt=terminal_receipt,
        full_residual_receipt_hash=canonical_hash(
            {
                "checkpoint_hash": terminal["checkpoint"]["checkpoint_hash"],
                "scaled_residual_inf_norm": terminal["scaled_residual_inf_norm"],
            }
        ),
        boundary_condition_receipt_hash=canonical_hash(
            {"restrained_global_dofs": list(model.restrained_dofs), "prescribed": 0.0}
        ),
        backend_role="cpu_reference",
        backend_receipt_hash=canonical_hash(
            {"fallback_count": 0, "regularization_count": 0}
        ),
    )
    manifest = result.to_manifest()
    validate_nonlinear_result_manifest(manifest)
    return manifest


def _recovery_payload(
    *,
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    model: CorotationalFrame3DModel,
    displacement: np.ndarray,
    load_factor: float,
    terminal_members: Any,
    solver_config: CorotationalFrame3DGlobalConfig,
) -> dict[str, Any]:
    assembly = assemble_corotational_frame3d_global(model, displacement)
    raw_residual = assembly.internal_force - load_factor * np.asarray(
        model.reference_load_kn
    )
    reaction = np.zeros(model.total_dofs, dtype=np.float64)
    reaction[list(model.restrained_dofs)] = raw_residual[list(model.restrained_dofs)]
    balance = raw_residual - reaction
    recovered_members = terminal_members
    if recovered_members is None:
        recovered_members = tuple(
            CorotationalFrame3DMemberResult(
                member_id=member.member_id,
                node_i=member.node_i,
                node_j=member.node_j,
                initial_length_m=response.initial_length_m,
                current_length_m=response.current_length_m,
                strain_energy_kn_m=response.strain_energy_kn_m,
                basic_deformations=tuple(
                    float(value) for value in response.basic_deformations
                ),
                basic_forces=tuple(float(value) for value in response.basic_forces),
                global_end_forces=tuple(
                    float(value) for value in response.internal_force_global
                ),
            )
            for member, response in zip(
                model.members,
                assembly.member_responses,
                strict=True,
            )
        )
    node_displacements = tuple(
        {
            "node_id": node_id,
            "components": {
                component: float(displacement[6 * index + component_index])
                for component_index, component in enumerate(FRAME_DOF_LABELS)
            },
            "unit_profile": "ux_uy_uz_m_rx_ry_rz_rad.v1",
        }
        for index, node_id in enumerate(adapter.node_ids)
    )
    support_reactions = tuple(
        {
            "node_id": node_id,
            "force_n": {
                component: float(reaction[6 * index + component_index] * 1000.0)
                for component_index, component in enumerate(_TRANSLATION_COMPONENTS)
            },
            "moment_n_m": {
                component: float(reaction[6 * index + component_index + 3] * 1000.0)
                for component_index, component in enumerate(_MOMENT_COMPONENTS)
            },
        }
        for index, node_id in enumerate(adapter.node_ids)
        if any(6 * index + offset in model.restrained_dofs for offset in range(6))
    )
    member_recovery = tuple(
        {
            "member_id": row.member_id,
            "node_ids": [adapter.node_ids[row.node_i], adapter.node_ids[row.node_j]],
            "initial_length_m": row.initial_length_m,
            "current_length_m": row.current_length_m,
            "strain_energy_kn_m": row.strain_energy_kn_m,
            "basic_deformations": list(row.basic_deformations),
            "basic_forces_solver_units": list(row.basic_forces),
            "global_end_forces_solver_units": list(row.global_end_forces),
            "force_unit_profile": "forces_kn_moments_kn_m.v1",
        }
        for row in recovered_members
    )
    full_node_equilibrium = tuple(
        {
            "node_id": node_id,
            "internal_minus_applied_force_n": [
                float(raw_residual[6 * index + offset] * 1000.0) for offset in range(3)
            ],
            "internal_minus_applied_moment_n_m": [
                float(raw_residual[6 * index + offset] * 1000.0)
                for offset in range(3, 6)
            ],
            "reaction_force_n": [
                float(reaction[6 * index + offset] * 1000.0) for offset in range(3)
            ],
            "reaction_moment_n_m": [
                float(reaction[6 * index + offset] * 1000.0) for offset in range(3, 6)
            ],
            "balance_residual_force_n": [
                float(balance[6 * index + offset] * 1000.0) for offset in range(3)
            ],
            "balance_residual_moment_n_m": [
                float(balance[6 * index + offset] * 1000.0) for offset in range(3, 6)
            ],
        }
        for index, node_id in enumerate(adapter.node_ids)
    )
    scaling = create_equation_scaling_6dof(
        source_identity_hash=model.model_hash,
        node_coordinates_m=model.node_coordinates_m,
        reference_equation_load=model.reference_load_kn,
        free_dofs=model.free_dofs,
    )
    scaled_metrics = scaled_residual_metrics_6dof(
        balance[list(model.free_dofs)],
        model.free_dofs,
        scaling,
    )
    scaled_tolerance = (
        solver_config.residual_absolute_tolerance_kn / scaling.reference_force
        + solver_config.residual_relative_tolerance
    )
    force_balance_kn = np.asarray(
        [balance[index] for index in range(model.total_dofs) if index % 6 < 3]
    )
    moment_balance_kn_m = np.asarray(
        [balance[index] for index in range(model.total_dofs) if index % 6 >= 3]
    )
    maximum_force_balance_n = float(
        np.linalg.norm(force_balance_kn * 1000.0, ord=np.inf)
    )
    maximum_moment_balance_n_m = float(
        np.linalg.norm(moment_balance_kn_m * 1000.0, ord=np.inf)
    )
    force_tolerance_n = scaled_tolerance * scaling.residual_translation_scale * 1000.0
    moment_tolerance_n_m = scaled_tolerance * scaling.residual_rotation_scale * 1000.0
    equilibrium_pass = bool(
        scaled_metrics["scaled"] <= scaled_tolerance
        and maximum_force_balance_n <= force_tolerance_n
        and maximum_moment_balance_n_m <= moment_tolerance_n_m
    )
    return {
        "node_displacements": node_displacements,
        "support_reactions": support_reactions,
        "member_recovery": member_recovery,
        "full_node_equilibrium": full_node_equilibrium,
        "equation_scaling_hash": scaling.scaling_hash,
        "maximum_scaled_balance": scaled_metrics["scaled"],
        "scaled_tolerance": scaled_tolerance,
        "maximum_force_balance_n": maximum_force_balance_n,
        "maximum_moment_balance_n_m": maximum_moment_balance_n_m,
        "force_tolerance_n": force_tolerance_n,
        "moment_tolerance_n_m": moment_tolerance_n_m,
        "full_node_equilibrium_pass": equilibrium_pass,
    }


def _checkpoint_artifact(
    *,
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    config: BoundedFrame3DLoadControlConfig,
    checkpoint: CorotationalFrame3DGlobalCheckpoint,
) -> tuple[dict[str, Any], bytes]:
    payload: dict[str, Any] = {
        "schema_version": BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_SCHEMA_VERSION,
        "profile": BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE,
        "artifact_hash": _HASH_ZERO,
        "model_ir_content_hash": adapter.model_ir_content_hash,
        "adapter_hash": adapter.adapter_hash,
        "model_hash": adapter.model_hash,
        "load_pattern_id": adapter.load_pattern_id,
        "node_ids": list(adapter.node_ids),
        "member_ids": list(adapter.member_ids),
        "solver_contract_hash": config.solver_config.contract_hash,
        "request_hash": config.request_hash,
        "resume_contract_hash": _resume_contract_hash(adapter, config),
        "checkpoint": checkpoint.to_dict(),
        "public_product_promotion": False,
        "release_eligible": False,
    }
    payload["artifact_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    _validate_schema(payload, BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_SCHEMA_PATH)
    return payload, canonical_json_bytes(payload) + b"\n"


def _checkpoint_from_artifact(
    artifact_bytes: bytes,
    *,
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    config: BoundedFrame3DLoadControlConfig,
) -> CorotationalFrame3DGlobalCheckpoint:
    payload = _parse_canonical_json_object(
        artifact_bytes,
        code_prefix="bounded_frame3d_load_checkpoint",
        maximum_bytes=BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_MAX_BYTES,
    )
    _validate_schema(payload, BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_SCHEMA_PATH)
    expected_hash = canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    if payload["artifact_hash"] != expected_hash:
        _fail(
            "bounded_frame3d_load_checkpoint_artifact_hash_mismatch",
            "/artifact_hash",
            "Checkpoint artifact hash mismatch.",
        )
    expected_bindings = {
        "model_ir_content_hash": adapter.model_ir_content_hash,
        "adapter_hash": adapter.adapter_hash,
        "model_hash": adapter.model_hash,
        "load_pattern_id": adapter.load_pattern_id,
        "node_ids": list(adapter.node_ids),
        "member_ids": list(adapter.member_ids),
        "solver_contract_hash": config.solver_config.contract_hash,
        "request_hash": config.request_hash,
        "resume_contract_hash": _resume_contract_hash(adapter, config),
    }
    for name, expected in expected_bindings.items():
        if payload[name] != expected:
            _fail(
                "bounded_frame3d_load_checkpoint_binding_mismatch",
                f"/{name}",
                "Checkpoint does not bind the current request source.",
            )
    return _checkpoint_from_payload(
        payload["checkpoint"],
        path="/checkpoint",
        model=adapter.model,
        config=config.solver_config,
    )


def _checkpoint_from_payload(
    row: Mapping[str, Any],
    *,
    path: str,
    model: CorotationalFrame3DModel,
    config: CorotationalFrame3DGlobalConfig,
) -> CorotationalFrame3DGlobalCheckpoint:
    if not isinstance(row, Mapping):
        _fail(
            "bounded_frame3d_load_checkpoint_shape_invalid",
            path,
            "Checkpoint row must be an object.",
        )
    thawed = _thaw_json(row)
    _validate_schema(thawed, "corotational_frame3d_global_checkpoint_v1.schema.json")
    try:
        checkpoint = CorotationalFrame3DGlobalCheckpoint(
            schema_version=thawed["schema_version"],
            profile=thawed["profile"],
            model_hash=thawed["model_hash"],
            solver_contract_hash=thawed["solver_contract_hash"],
            load_factor=float(thawed["load_factor"]),
            displacement=tuple(float(value) for value in thawed["displacement"]),
            converged_iterations=thawed["converged_iterations"],
            residual_inf_norm_kn=float(thawed["residual_inf_norm_kn"]),
            parent_checkpoint_hash=thawed["parent_checkpoint_hash"],
            checkpoint_hash=thawed["checkpoint_hash"],
        )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        _fail(
            "bounded_frame3d_load_checkpoint_value_invalid",
            path,
            str(error),
        )
    if not _same_json_scalar_domain(thawed, checkpoint.to_dict()):
        _fail(
            "bounded_frame3d_load_checkpoint_numeric_domain_mismatch",
            path,
            "Checkpoint changed JSON scalar domains during typed reconstruction.",
        )
    try:
        return validate_corotational_frame3d_global_checkpoint(
            checkpoint,
            model=model,
            config=config,
            require_equilibrium=True,
        )
    except CorotationalFrame3DGlobalError as error:
        _fail("bounded_frame3d_load_checkpoint_invalid", path, str(error))


def _completed_prefix_count(
    load_factors: tuple[float, ...],
    checkpoint_load_factor: float,
) -> int:
    if checkpoint_load_factor == 0.0:
        return 0
    try:
        return load_factors.index(checkpoint_load_factor) + 1
    except ValueError:
        _fail(
            "bounded_frame3d_load_checkpoint_not_schedule_prefix",
            "/restart_checkpoint_artifact/checkpoint/load_factor",
            "Checkpoint load factor is not an exact configured schedule prefix.",
        )


def _resume_contract_hash(
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    config: BoundedFrame3DLoadControlConfig,
) -> str:
    return canonical_hash(
        {
            "profile": BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE,
            "adapter_hash": adapter.adapter_hash,
            "model_hash": adapter.model_hash,
            "load_pattern_id": adapter.load_pattern_id,
            "solver_contract_hash": config.solver_config.contract_hash,
            "request_hash": config.request_hash,
        }
    )


def _displacement_from_rows(
    rows: Any,
    node_ids: tuple[str, ...],
) -> np.ndarray:
    thawed = _thaw_json(rows)
    if not isinstance(thawed, list) or [row.get("node_id") for row in thawed] != list(
        node_ids
    ):
        _fail(
            "bounded_frame3d_load_result_node_order_invalid",
            "/node_displacements",
            "Node displacement rows must preserve canonical adapter order.",
        )
    values = [
        float(row["components"][component])
        for row in thawed
        for component in FRAME_DOF_LABELS
    ]
    array = np.asarray(values, dtype="<f8")
    if not np.all(np.isfinite(array)):
        _fail(
            "bounded_frame3d_load_result_displacement_nonfinite",
            "/node_displacements",
            "Displacement values must be finite.",
        )
    return array


def _result_payload(
    result: BoundedFrame3DLoadControlResult,
    *,
    include_result_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version,
        "profile": result.profile,
        "status": result.status,
        "contract_pass": result.contract_pass,
        "source_binding": _thaw_json(result.source_binding),
        "load_factors": list(result.load_factors),
        "solver": _thaw_json(result.solver),
        "numerical_result_ir": _thaw_json(result.numerical_result_ir),
        "node_displacements": _thaw_json(result.node_displacements),
        "support_reactions": _thaw_json(result.support_reactions),
        "member_recovery": _thaw_json(result.member_recovery),
        "full_node_equilibrium": _thaw_json(result.full_node_equilibrium),
        "checkpoint_artifact": _thaw_json(result.checkpoint_artifact),
        "metrics": _thaw_json(result.metrics),
        "authority": _thaw_json(result.authority),
        "warnings": list(result.warnings),
        "claim_boundary": result.claim_boundary,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


def _validate_schema(payload: Mapping[str, Any], schema_name: str) -> None:
    with (
        resources.files("structural_analysis.schemas")
        .joinpath(schema_name)
        .open("r", encoding="utf-8") as handle
    ):
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        _StrictDraft202012Validator(schema).iter_errors(payload),
        key=lambda row: list(row.path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.path)
        _fail("bounded_frame3d_load_schema_invalid", path, error.message)


def _deep_freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _object_without_duplicate_keys(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in rows:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON constant: {value}")


def _parse_canonical_json_object(
    document_bytes: bytes,
    *,
    code_prefix: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    if not document_bytes or len(document_bytes) > maximum_bytes:
        _fail(
            f"{code_prefix}_size_invalid",
            "/",
            f"JSON bytes must be non-empty and at most {maximum_bytes} bytes.",
        )
    try:
        payload = json.loads(
            document_bytes,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{code_prefix}_json_invalid", "/", str(error))
    if not isinstance(payload, dict):
        _fail(f"{code_prefix}_shape_invalid", "/", "JSON object required.")
    if document_bytes != canonical_json_bytes(payload) + b"\n":
        _fail(
            f"{code_prefix}_noncanonical",
            "/",
            "Persisted JSON bytes must use repository-canonical encoding.",
        )
    return payload


def _same_json_scalar_domain(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return bool(
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and set(left) == set(right)
            and all(_same_json_scalar_domain(left[key], right[key]) for key in left)
        )
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        return bool(
            isinstance(left, (list, tuple))
            and isinstance(right, (list, tuple))
            and len(left) == len(right)
            and all(
                _same_json_scalar_domain(left_value, right_value)
                for left_value, right_value in zip(left, right, strict=True)
            )
        )
    return type(left) is type(right) and left == right


def _require_finite_json(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _require_finite_json(item, f"{path}/{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_finite_json(item, f"{path}/{index}")
        return
    if type(value) is float and not math.isfinite(value):
        _fail(
            "bounded_frame3d_load_nonfinite_json_value",
            path,
            "Persisted numerical values must be finite.",
        )


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedFrame3DLoadControlError(code, path, detail)


__all__ = [
    "BOUNDED_FRAME3D_LOAD_CONTROL_API_PROFILE",
    "BOUNDED_FRAME3D_LOAD_CONTROL_CHECKPOINT_SCHEMA_VERSION",
    "BOUNDED_FRAME3D_LOAD_CONTROL_CLAIM_BOUNDARY",
    "BOUNDED_FRAME3D_LOAD_CONTROL_CONFIG_SCHEMA_VERSION",
    "BOUNDED_FRAME3D_LOAD_CONTROL_RESULT_SCHEMA_VERSION",
    "BoundedFrame3DLoadControlConfig",
    "BoundedFrame3DLoadControlError",
    "BoundedFrame3DLoadControlResult",
    "advance_bounded_frame3d_load_control_model_ir",
    "analyze_bounded_frame3d_load_control_model_ir",
    "bounded_frame3d_load_control_resume_contract_hash",
    "parse_bounded_frame3d_load_control_config",
    "validate_bounded_frame3d_load_control_result",
    "validate_bounded_frame3d_load_control_result_manifest",
]
