"""Strict Phase 0 AI correction proposal contract.

The proposal is an immutable, unevaluated overlay for the ``initial_guess``
hook.  It has no authority to become a final result or to mutate/commit a
``StateIR``.  A fixed-rank projection maps bounded coefficients ``y`` to
scaled reduced coordinates ``Q y`` and then to physical free-DOF coordinates
``D Q y``.  Authoritative residual, energy, boundary-condition, and
constitutive replay remain mandatory before any future promotion path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.ai.projection import (
    MAX_PROJECTION_RANK,
    FixedRankProjection,
    validate_fixed_rank_projection,
)
from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    StateIR,
    validate_state_ir,
)

AI_CORRECTION_PROPOSAL_SCHEMA_VERSION = (
    "structural-analysis-ai-correction-proposal.v1"
)
AI_CORRECTION_PROPOSAL_CAPABILITY_PROFILE = (
    "phase0_fixed_rank_initial_guess_proposal"
)
AI_CORRECTION_PROPOSAL_CLAIM_BOUNDARY = (
    "phase0_unevaluated_initial_guess_proposal_only"
)
BASIS_GRAM_CONDITION_LIMIT = 1.00000001
SCALED_ENERGY_COORDINATE_UNITS = "sqrt_joule_energy_coordinate"

_ARRAY_NAMES = ("coefficients_y", "correction_scaled", "correction_free")
_ARRAY_AXES = {
    "coefficients_y": ("basis_rank",),
    "correction_scaled": ("free_dof",),
    "correction_free": ("free_dof",),
}
_ARRAY_UNITS = {
    "coefficients_y": SCALED_ENERGY_COORDINATE_UNITS,
    "correction_scaled": SCALED_ENERGY_COORDINATE_UNITS,
    "correction_free": "m_or_rad_by_global_dof",
}


class AICorrectionProposalError(ValueError):
    """Fail-closed proposal contract error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class ProposalArrayDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    axis_labels: tuple[str, ...]
    units: str
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        payload["axis_labels"] = list(self.axis_labels)
        return payload


@dataclass(frozen=True)
class AICorrectionProposal:
    """One immutable, plan/state/projection-bound correction overlay."""

    schema_version: str
    capability_profile: str
    proposal_id: str
    status: Literal["unevaluated"]
    model_ir_content_hash: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    operator_hash: str
    pattern_hash: str
    partition_hash: str
    load_pattern_id: str
    base_state_id: str
    base_state_hash: str
    base_state_epoch: int
    projection_hash: str
    hook: Literal["initial_guess"]
    target_vector_space: Literal["scaled_reduced_free_dof"]
    free_dof_count: int
    retained_rank: int
    rank_cap: int
    basis_orthogonality_error_frobenius: float
    basis_gram_condition: float
    basis_gram_condition_limit: float
    trust_radius: float
    trust_absolute_tolerance: float
    coefficient_l2_norm: float
    correction_scaled_l2_norm: float
    ood_status: Literal["not_evaluated"]
    statistical_calibration: bool
    overlay_only: bool
    final_result: bool
    direct_state_commit: bool
    promotion_authorized: bool
    acceptance_eligible: bool
    full_residual_replay_required: bool
    energy_replay_required: bool
    boundary_condition_replay_required: bool
    constitutive_replay_required: bool
    dense_projector: bool
    descriptors: tuple[ProposalArrayDescriptor, ...]
    coefficients_y: np.ndarray
    correction_scaled: np.ndarray
    correction_free: np.ndarray
    proposal_hash: str
    _plan: ExecutionPlan
    _base_state: StateIR
    _projection: FixedRankProjection

    def array(self, name: str) -> np.ndarray:
        if name not in _ARRAY_NAMES:
            raise KeyError(f"Unknown AICorrectionProposal array: {name}")
        return getattr(self, name)

    def to_dict(self) -> dict[str, Any]:
        validate_phase0_ai_proposal(self)
        return _proposal_payload(self, include_proposal_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def build_phase0_ai_proposal(
    plan: ExecutionPlan,
    accepted_state: StateIR,
    projection: FixedRankProjection,
    coefficients_y: Any,
    trust_radius: float,
) -> AICorrectionProposal:
    """Build a bounded initial-guess proposal without changing accepted state."""

    _validate_source_contracts(plan, accepted_state, projection)
    if accepted_state.role != "committed":
        _fail(
            "ai_proposal_base_state_not_committed",
            "/base_state/role",
            "A proposal can only overlay a committed accepted state.",
        )
    radius = _require_positive_finite(
        trust_radius, "/trust/radius", "ai_proposal_trust_radius_invalid"
    )
    coefficients = _immutable_vector(
        coefficients_y,
        projection.retained_rank,
        path="/arrays/coefficients_y",
    )

    scaled = np.zeros(projection.free_dof_count, dtype="<f8")
    for column_index in range(projection.retained_rank):
        scaled += coefficients[column_index] * projection.basis_q[:, column_index]
    if not np.all(np.isfinite(scaled)):
        _fail(
            "ai_proposal_scaled_correction_nonfinite",
            "/arrays/correction_scaled",
            "Q*y produced a non-finite scaled correction.",
        )
    physical = projection.scaling_diagonal * scaled
    if not np.all(np.isfinite(physical)):
        _fail(
            "ai_proposal_physical_correction_nonfinite",
            "/arrays/correction_free",
            "D*Q*y produced a non-finite physical correction.",
        )

    arrays = {
        "coefficients_y": coefficients,
        "correction_scaled": _immutable_vector(
            scaled,
            projection.free_dof_count,
            path="/arrays/correction_scaled",
        ),
        "correction_free": _immutable_vector(
            physical,
            projection.free_dof_count,
            path="/arrays/correction_free",
        ),
    }
    coefficient_norm = _stable_norm(arrays["coefficients_y"])
    correction_norm = _stable_norm(arrays["correction_scaled"])
    trust_tolerance = _trust_tolerance(radius, coefficient_norm, correction_norm)
    if (
        coefficient_norm > radius + trust_tolerance
        or correction_norm > radius + trust_tolerance
    ):
        _fail(
            "ai_proposal_trust_radius_exceeded",
            "/trust/radius",
            "Both ||y||_2 and ||Q*y||_2 must remain within the trust radius.",
        )

    gram = projection.basis_q.T @ projection.basis_q
    gram_condition = float(np.linalg.cond(gram))
    if not math.isfinite(gram_condition) or gram_condition < 1.0:
        _fail(
            "ai_proposal_gram_condition_invalid",
            "/subspace/gram_condition",
            "Projection Gram condition must be finite and at least one.",
        )
    if gram_condition > BASIS_GRAM_CONDITION_LIMIT:
        _fail(
            "ai_proposal_gram_condition_exceeded",
            "/subspace/gram_condition",
            "Projection Gram condition exceeds the Phase 0 bound.",
        )

    descriptors = tuple(
        _array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES
    )
    proposal_id = _deterministic_proposal_id(
        execution_plan_hash=plan.plan_hash,
        base_state_hash=accepted_state.state_hash,
        projection_hash=projection.projection_hash,
        coefficients_descriptor=descriptors[0],
        trust_radius=radius,
    )
    provisional = AICorrectionProposal(
        schema_version=AI_CORRECTION_PROPOSAL_SCHEMA_VERSION,
        capability_profile=AI_CORRECTION_PROPOSAL_CAPABILITY_PROFILE,
        proposal_id=proposal_id,
        status="unevaluated",
        model_ir_content_hash=plan.model_ir_content_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
        solver_artifact_hash=plan.solver_artifact_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        pattern_hash=plan.pattern_hash,
        partition_hash=plan.partition_hash,
        load_pattern_id=plan.load_pattern_id,
        base_state_id=accepted_state.state_id,
        base_state_hash=accepted_state.state_hash,
        base_state_epoch=accepted_state.epoch,
        projection_hash=projection.projection_hash,
        hook="initial_guess",
        target_vector_space="scaled_reduced_free_dof",
        free_dof_count=projection.free_dof_count,
        retained_rank=projection.retained_rank,
        rank_cap=projection.rank_cap,
        basis_orthogonality_error_frobenius=(
            projection.orthogonality_error_frobenius
        ),
        basis_gram_condition=gram_condition,
        basis_gram_condition_limit=BASIS_GRAM_CONDITION_LIMIT,
        trust_radius=radius,
        trust_absolute_tolerance=trust_tolerance,
        coefficient_l2_norm=coefficient_norm,
        correction_scaled_l2_norm=correction_norm,
        ood_status="not_evaluated",
        statistical_calibration=False,
        overlay_only=True,
        final_result=False,
        direct_state_commit=False,
        promotion_authorized=False,
        acceptance_eligible=False,
        full_residual_replay_required=True,
        energy_replay_required=True,
        boundary_condition_replay_required=True,
        constitutive_replay_required=True,
        dense_projector=False,
        descriptors=descriptors,
        coefficients_y=arrays["coefficients_y"],
        correction_scaled=arrays["correction_scaled"],
        correction_free=arrays["correction_free"],
        proposal_hash="sha256:" + ("0" * 64),
        _plan=plan,
        _base_state=accepted_state,
        _projection=projection,
    )
    proposal = replace(
        provisional, proposal_hash=_proposal_hash(provisional)
    )
    validate_phase0_ai_proposal(
        proposal,
        expected_plan=plan,
        expected_accepted_state=accepted_state,
        expected_projection=projection,
    )
    return proposal


def validate_phase0_ai_proposal(
    proposal: AICorrectionProposal,
    *,
    expected_plan: ExecutionPlan | None = None,
    expected_accepted_state: StateIR | None = None,
    expected_projection: FixedRankProjection | None = None,
) -> None:
    """Recompute every binding, numerical invariant, descriptor, and hash."""

    if not isinstance(proposal, AICorrectionProposal):
        _fail(
            "ai_proposal_type_invalid",
            "/",
            "Expected an AICorrectionProposal instance.",
        )
    _validate_source_contracts(
        proposal._plan, proposal._base_state, proposal._projection
    )
    if proposal._base_state.role != "committed":
        _fail(
            "ai_proposal_base_state_not_committed",
            "/base_state/role",
            "The bound base state must remain committed.",
        )

    if expected_plan is not None:
        try:
            validate_execution_plan(expected_plan)
        except Exception as exc:
            raise AICorrectionProposalError(
                "ai_proposal_expected_plan_invalid", "/input_bindings", str(exc)
            ) from exc
        if expected_plan.plan_hash != proposal._plan.plan_hash:
            _fail(
                "ai_proposal_expected_plan_mismatch",
                "/input_bindings/execution_plan_hash",
                "Expected ExecutionPlan differs from the proposal plan.",
            )
    if expected_accepted_state is not None:
        try:
            validate_state_ir(
                expected_accepted_state,
                expected_plan=expected_plan or proposal._plan,
            )
        except Exception as exc:
            raise AICorrectionProposalError(
                "ai_proposal_expected_state_invalid", "/base_state", str(exc)
            ) from exc
        if expected_accepted_state.state_hash != proposal._base_state.state_hash:
            _fail(
                "ai_proposal_expected_state_mismatch",
                "/input_bindings/base_state_hash",
                "Expected accepted StateIR differs from the proposal base state.",
            )
    if expected_projection is not None:
        try:
            validate_fixed_rank_projection(
                expected_projection,
                expected_plan=expected_plan or proposal._plan,
            )
        except Exception as exc:
            raise AICorrectionProposalError(
                "ai_proposal_expected_projection_invalid",
                "/subspace/projection_hash",
                str(exc),
            ) from exc
        if expected_projection.projection_hash != proposal._projection.projection_hash:
            _fail(
                "ai_proposal_expected_projection_mismatch",
                "/subspace/projection_hash",
                "Expected projection differs from the proposal subspace.",
            )

    plan = proposal._plan
    state = proposal._base_state
    projection = proposal._projection
    expected_bindings = {
        "model_ir_content_hash": plan.model_ir_content_hash,
        "solver_numeric_buffer_hash": plan.solver_numeric_buffer_hash,
        "solver_entity_mapping_hash": plan.solver_entity_mapping_hash,
        "solver_artifact_hash": plan.solver_artifact_hash,
        "execution_plan_hash": plan.plan_hash,
        "operator_hash": plan.operator_hash,
        "pattern_hash": plan.pattern_hash,
        "partition_hash": plan.partition_hash,
        "load_pattern_id": plan.load_pattern_id,
        "base_state_id": state.state_id,
        "base_state_hash": state.state_hash,
        "base_state_epoch": state.epoch,
        "projection_hash": projection.projection_hash,
    }
    for field, expected in expected_bindings.items():
        if getattr(proposal, field) != expected:
            _fail(
                "ai_proposal_binding_mismatch",
                f"/input_bindings/{field}",
                f"Proposal {field} is stale or forged.",
            )

    constant_fields = {
        "schema_version": AI_CORRECTION_PROPOSAL_SCHEMA_VERSION,
        "capability_profile": AI_CORRECTION_PROPOSAL_CAPABILITY_PROFILE,
        "status": "unevaluated",
        "hook": "initial_guess",
        "target_vector_space": "scaled_reduced_free_dof",
        "basis_gram_condition_limit": BASIS_GRAM_CONDITION_LIMIT,
        "ood_status": "not_evaluated",
        "statistical_calibration": False,
        "overlay_only": True,
        "final_result": False,
        "direct_state_commit": False,
        "promotion_authorized": False,
        "acceptance_eligible": False,
        "full_residual_replay_required": True,
        "energy_replay_required": True,
        "boundary_condition_replay_required": True,
        "constitutive_replay_required": True,
        "dense_projector": False,
    }
    for field, expected in constant_fields.items():
        if getattr(proposal, field) != expected:
            _fail(
                "ai_proposal_authority_invariant_violated",
                f"/{field}",
                f"{field} must be {expected!r}.",
            )

    if proposal.free_dof_count != projection.free_dof_count:
        _fail(
            "ai_proposal_free_dof_count_mismatch",
            "/target/free_dof_count",
            "Free DOF count differs from the projection.",
        )
    if (
        proposal.retained_rank != projection.retained_rank
        or proposal.rank_cap != projection.rank_cap
        or not 1 <= proposal.retained_rank <= proposal.rank_cap <= MAX_PROJECTION_RANK
    ):
        _fail(
            "ai_proposal_rank_mismatch",
            "/subspace/retained_rank",
            "Proposal rank is not the exact bounded projection rank.",
        )

    if not isinstance(proposal.descriptors, tuple) or any(
        not isinstance(row, ProposalArrayDescriptor) for row in proposal.descriptors
    ):
        _fail(
            "ai_proposal_descriptor_set_invalid",
            "/arrays",
            "Array descriptors must be an immutable descriptor tuple.",
        )
    descriptor_names = tuple(row.name for row in proposal.descriptors)
    if descriptor_names != _ARRAY_NAMES or len(set(descriptor_names)) != len(
        _ARRAY_NAMES
    ):
        _fail(
            "ai_proposal_descriptor_set_invalid",
            "/arrays",
            "Proposal requires exactly three ordered array descriptors.",
        )
    expected_shapes = {
        "coefficients_y": (proposal.retained_rank,),
        "correction_scaled": (proposal.free_dof_count,),
        "correction_free": (proposal.free_dof_count,),
    }
    for descriptor in proposal.descriptors:
        array = proposal.array(descriptor.name)
        if not isinstance(array, np.ndarray) or array.dtype.str != "<f8":
            _fail(
                "ai_proposal_array_dtype_invalid",
                f"/arrays/{descriptor.name}/dtype",
                "Proposal arrays must use little-endian FP64.",
            )
        if array.shape != expected_shapes[descriptor.name]:
            _fail(
                "ai_proposal_array_shape_invalid",
                f"/arrays/{descriptor.name}/shape",
                f"Expected shape {expected_shapes[descriptor.name]}.",
            )
        if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
            _fail(
                "ai_proposal_array_storage_invalid",
                f"/arrays/{descriptor.name}",
                "Proposal arrays must be C-contiguous immutable bytes views.",
            )
        if not np.all(np.isfinite(array)):
            _fail(
                "ai_proposal_array_nonfinite",
                f"/arrays/{descriptor.name}",
                "Proposal arrays must contain only finite values.",
            )
        if descriptor != _array_descriptor(descriptor.name, array):
            _fail(
                "ai_proposal_array_descriptor_mismatch",
                f"/arrays/{descriptor.name}",
                "Array descriptor does not match exact FP64 bytes.",
            )

    expected_proposal_id = _deterministic_proposal_id(
        execution_plan_hash=proposal.execution_plan_hash,
        base_state_hash=proposal.base_state_hash,
        projection_hash=proposal.projection_hash,
        coefficients_descriptor=proposal.descriptors[0],
        trust_radius=proposal.trust_radius,
    )
    if proposal.proposal_id != expected_proposal_id:
        _fail(
            "ai_proposal_id_mismatch",
            "/proposal_id",
            "Proposal ID is not the deterministic ID of its bound inputs.",
        )

    expected_scaled = np.zeros(proposal.free_dof_count, dtype="<f8")
    for column_index in range(proposal.retained_rank):
        expected_scaled += (
            proposal.coefficients_y[column_index]
            * projection.basis_q[:, column_index]
        )
    expected_scaled = _immutable_vector(
        expected_scaled,
        proposal.free_dof_count,
        path="/arrays/correction_scaled",
    )
    if not np.array_equal(proposal.correction_scaled, expected_scaled):
        _fail(
            "ai_proposal_scaled_correction_mismatch",
            "/arrays/correction_scaled",
            "Scaled correction is not Q*y for the bound projection.",
        )
    expected_free = _immutable_vector(
        projection.scaling_diagonal * expected_scaled,
        proposal.free_dof_count,
        path="/arrays/correction_free",
    )
    if not np.array_equal(proposal.correction_free, expected_free):
        _fail(
            "ai_proposal_free_correction_mismatch",
            "/arrays/correction_free",
            "Physical correction is not D*Q*y for the bound projection.",
        )

    expected_orthogonality = projection.orthogonality_error_frobenius
    if (
        not math.isfinite(proposal.basis_orthogonality_error_frobenius)
        or proposal.basis_orthogonality_error_frobenius != expected_orthogonality
    ):
        _fail(
            "ai_proposal_orthogonality_mismatch",
            "/subspace/orthogonality_error_frobenius",
            "Orthogonality receipt differs from the projection.",
        )
    gram = projection.basis_q.T @ projection.basis_q
    expected_condition = float(np.linalg.cond(gram))
    if (
        not math.isfinite(proposal.basis_gram_condition)
        or proposal.basis_gram_condition != expected_condition
        or proposal.basis_gram_condition < 1.0
        or proposal.basis_gram_condition > proposal.basis_gram_condition_limit
    ):
        _fail(
            "ai_proposal_gram_condition_mismatch",
            "/subspace/gram_condition",
            "Gram condition receipt is stale or exceeds its bound.",
        )

    radius = _require_positive_finite(
        proposal.trust_radius,
        "/trust/radius",
        "ai_proposal_trust_radius_invalid",
    )
    coefficient_norm = _stable_norm(proposal.coefficients_y)
    correction_norm = _stable_norm(proposal.correction_scaled)
    tolerance = _trust_tolerance(radius, coefficient_norm, correction_norm)
    trust_receipt = (
        (proposal.coefficient_l2_norm, coefficient_norm),
        (proposal.correction_scaled_l2_norm, correction_norm),
        (proposal.trust_absolute_tolerance, tolerance),
    )
    if any(
        not math.isfinite(actual) or actual != expected
        for actual, expected in trust_receipt
    ):
        _fail(
            "ai_proposal_trust_receipt_mismatch",
            "/trust",
            "Trust-region norm or tolerance receipt is stale.",
        )
    if coefficient_norm > radius + tolerance or correction_norm > radius + tolerance:
        _fail(
            "ai_proposal_trust_radius_exceeded",
            "/trust/radius",
            "Proposal correction exceeds its scaled L2 trust radius.",
        )

    schema_errors = sorted(
        _proposal_schema_validator().iter_errors(
            _proposal_payload(proposal, include_proposal_hash=True)
        ),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if schema_errors:
        error = schema_errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("ai_proposal_schema_invalid", path or "/", error.message)
    if proposal.proposal_hash != _proposal_hash(proposal):
        _fail(
            "ai_proposal_hash_mismatch",
            "/proposal_hash",
            "Proposal aggregate hash does not match its canonical payload.",
        )


def _validate_source_contracts(
    plan: ExecutionPlan,
    accepted_state: StateIR,
    projection: FixedRankProjection,
) -> None:
    try:
        validate_execution_plan(plan)
    except Exception as exc:
        raise AICorrectionProposalError(
            "ai_proposal_plan_invalid", "/input_bindings", str(exc)
        ) from exc
    try:
        validate_state_ir(accepted_state, expected_plan=plan)
    except Exception as exc:
        raise AICorrectionProposalError(
            "ai_proposal_base_state_invalid", "/base_state", str(exc)
        ) from exc
    try:
        validate_fixed_rank_projection(projection, expected_plan=plan)
    except Exception as exc:
        raise AICorrectionProposalError(
            "ai_proposal_projection_invalid", "/subspace", str(exc)
        ) from exc


def _immutable_vector(value: Any, count: int, *, path: str) -> np.ndarray:
    source = np.asarray(value)
    if source.dtype.kind not in "iuf":
        _fail(
            "ai_proposal_vector_type_invalid",
            path,
            "Proposal vectors must contain real numeric values.",
        )
    try:
        array = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AICorrectionProposalError(
            "ai_proposal_vector_type_invalid",
            path,
            "Proposal vector cannot be represented as FP64.",
        ) from exc
    if array.ndim != 1 or array.shape != (count,):
        _fail(
            "ai_proposal_vector_shape_invalid",
            path,
            f"Expected a flat vector with {count} entries.",
        )
    if not np.all(np.isfinite(array)):
        _fail(
            "ai_proposal_vector_nonfinite",
            path,
            "Proposal vectors must contain only finite values.",
        )
    normalized = np.ascontiguousarray(array, dtype="<f8").copy()
    normalized[normalized == 0.0] = 0.0
    try:
        return immutable_array(normalized, dtype="<f8")
    except CanonicalContractError as exc:  # pragma: no cover - preconditions above
        raise AICorrectionProposalError(
            "ai_proposal_vector_invalid", path, str(exc)
        ) from exc


def _stable_norm(vector: np.ndarray) -> float:
    scale = float(np.max(np.abs(vector))) if vector.size else 0.0
    if scale == 0.0:
        return 0.0
    normalized = vector / scale
    result = scale * float(np.sqrt(np.dot(normalized, normalized)))
    if not math.isfinite(result):
        _fail(
            "ai_proposal_norm_nonfinite",
            "/trust",
            "Proposal norm overflowed or became non-finite.",
        )
    return result


def _trust_tolerance(radius: float, coefficient_norm: float, correction_norm: float) -> float:
    return float(
        64.0
        * np.finfo(np.float64).eps
        * max(1.0, radius, coefficient_norm, correction_norm)
    )


def _require_positive_finite(value: Any, path: str, code: str) -> float:
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, float, np.integer, np.floating))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        _fail(code, path, "Expected a finite positive real number.")
    return float(value)


def _array_descriptor(name: str, array: np.ndarray) -> ProposalArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "layout": "C",
        "axis_labels": list(_ARRAY_AXES[name]),
        "units": _ARRAY_UNITS[name],
        "byte_length": int(array.nbytes),
    }
    return ProposalArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        axis_labels=_ARRAY_AXES[name],
        units=_ARRAY_UNITS[name],
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _deterministic_proposal_id(
    *,
    execution_plan_hash: str,
    base_state_hash: str,
    projection_hash: str,
    coefficients_descriptor: ProposalArrayDescriptor,
    trust_radius: float,
) -> str:
    seed_hash = canonical_hash(
        {
            "execution_plan_hash": execution_plan_hash,
            "base_state_hash": base_state_hash,
            "projection_hash": projection_hash,
            "coefficients_y": coefficients_descriptor.to_dict(),
            "trust_radius": trust_radius,
        }
    )
    return f"AIProposal:{seed_hash.removeprefix('sha256:')[:24]}"


def _array_payload(
    descriptor: ProposalArrayDescriptor, array: np.ndarray
) -> dict[str, Any]:
    return {**descriptor.to_dict(), "values": array.tolist()}


def _proposal_payload(
    proposal: AICorrectionProposal,
    *,
    include_proposal_hash: bool,
) -> dict[str, Any]:
    descriptors = {row.name: row for row in proposal.descriptors}
    payload: dict[str, Any] = {
        "schema_version": proposal.schema_version,
        "capability_profile": proposal.capability_profile,
        "proposal_id": proposal.proposal_id,
        "status": proposal.status,
        "input_bindings": {
            "model_ir_content_hash": proposal.model_ir_content_hash,
            "solver_numeric_buffer_hash": proposal.solver_numeric_buffer_hash,
            "solver_entity_mapping_hash": proposal.solver_entity_mapping_hash,
            "solver_artifact_hash": proposal.solver_artifact_hash,
            "execution_plan_hash": proposal.execution_plan_hash,
            "operator_hash": proposal.operator_hash,
            "pattern_hash": proposal.pattern_hash,
            "partition_hash": proposal.partition_hash,
            "load_pattern_id": proposal.load_pattern_id,
            "base_state_hash": proposal.base_state_hash,
            "projection_hash": proposal.projection_hash,
        },
        "base_state": {
            "state_id": proposal.base_state_id,
            "role": "committed",
            "epoch": proposal.base_state_epoch,
            "state_hash": proposal.base_state_hash,
        },
        "hook": {
            "name": proposal.hook,
            "overlay_only": proposal.overlay_only,
            "final_result": proposal.final_result,
            "direct_state_commit": proposal.direct_state_commit,
            "promotion_authorized": proposal.promotion_authorized,
        },
        "target": {
            "vector_space": proposal.target_vector_space,
            "coordinate_map": "u_free=D*x,D=diag(K_ff)^-1/2",
            "free_dof_count": proposal.free_dof_count,
            "scaled_units": SCALED_ENERGY_COORDINATE_UNITS,
            "physical_units": "m_or_rad_by_global_dof",
        },
        "subspace": {
            "projection_hash": proposal.projection_hash,
            "retained_rank": proposal.retained_rank,
            "rank_cap": proposal.rank_cap,
            "orthogonality_error_frobenius": (
                proposal.basis_orthogonality_error_frobenius
            ),
            "gram_condition": proposal.basis_gram_condition,
            "gram_condition_limit": proposal.basis_gram_condition_limit,
            "within_condition_bound": (
                proposal.basis_gram_condition
                <= proposal.basis_gram_condition_limit
            ),
            "dense_projector": proposal.dense_projector,
        },
        "trust": {
            "norm": "scaled_reduced_free_dof_l2",
            "units": SCALED_ENERGY_COORDINATE_UNITS,
            "radius": proposal.trust_radius,
            "absolute_tolerance": proposal.trust_absolute_tolerance,
            "coefficient_l2_norm": proposal.coefficient_l2_norm,
            "correction_scaled_l2_norm": proposal.correction_scaled_l2_norm,
            "within_bound": (
                proposal.coefficient_l2_norm
                <= proposal.trust_radius + proposal.trust_absolute_tolerance
                and proposal.correction_scaled_l2_norm
                <= proposal.trust_radius + proposal.trust_absolute_tolerance
            ),
        },
        "uncertainty": {
            "ood_status": proposal.ood_status,
            "statistical_calibration": proposal.statistical_calibration,
            "acceptance_eligible": proposal.acceptance_eligible,
        },
        "required_replay": {
            "full_residual": proposal.full_residual_replay_required,
            "energy": proposal.energy_replay_required,
            "boundary_conditions": proposal.boundary_condition_replay_required,
            "constitutive_admissibility": proposal.constitutive_replay_required,
            "required_before_promotion": True,
        },
        "arrays": {
            name: _array_payload(descriptors[name], proposal.array(name))
            for name in _ARRAY_NAMES
        },
        "implementation_constraints": {
            "correction_formula": "correction_scaled=Q*y",
            "physical_coordinate_formula": (
                "correction_free=D*correction_scaled"
            ),
            "explicit_dense_projector": proposal.dense_projector,
            "reverse_mode_autograd": False,
            "legacy_ai_runtime": False,
        },
        "claim_boundary": AI_CORRECTION_PROPOSAL_CLAIM_BOUNDARY,
        "extensions": {},
    }
    if include_proposal_hash:
        payload["proposal_hash"] = proposal.proposal_hash
    return payload


def _proposal_hash(proposal: AICorrectionProposal) -> str:
    return canonical_hash(
        _proposal_payload(proposal, include_proposal_hash=False)
    )


@lru_cache(maxsize=1)
def _proposal_schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "ai_correction_proposal_v1.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise AICorrectionProposalError(code, path, message)


__all__ = [
    "AI_CORRECTION_PROPOSAL_CAPABILITY_PROFILE",
    "AI_CORRECTION_PROPOSAL_CLAIM_BOUNDARY",
    "AI_CORRECTION_PROPOSAL_SCHEMA_VERSION",
    "BASIS_GRAM_CONDITION_LIMIT",
    "SCALED_ENERGY_COORDINATE_UNITS",
    "AICorrectionProposal",
    "AICorrectionProposalError",
    "ProposalArrayDescriptor",
    "build_phase0_ai_proposal",
    "validate_phase0_ai_proposal",
]
