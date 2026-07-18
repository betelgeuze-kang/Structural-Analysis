from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts.equation_scaling import (  # noqa: E402
    EQUATION_SCALING_EXTENSION_KEY,
    REFERENCE_EQUATION_SCOPE,
    EquationScalingError,
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
    execution_plan_scaling_hash,
    trace_scaled_residual,
    validate_equation_scaling,
    validate_equation_scaling_binding,
    validate_equation_scaling_manifest,
    validate_scaled_residual_trace,
    validate_scaled_residual_trace_manifest,
    _scaling_payload,
    _source_commitment_payload,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    EXECUTION_PLAN_CAPABILITY_PROFILE,
    EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY,
    EXECUTION_PLAN_SCALED_CAPABILITY_PROFILE,
    ExecutionPlanError,
    create_execution_plan,
    validate_execution_plan,
    validate_execution_plan_manifest,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _plan(*, fully_constrained: bool = False):
    dof_count = 12
    constrained_dofs = (
        np.arange(dof_count, dtype="<i4")
        if fully_constrained
        else np.arange(6, dtype="<i4")
    )
    free_dofs = (
        np.asarray([], dtype="<i4")
        if fully_constrained
        else np.arange(6, dof_count, dtype="<i4")
    )
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free_dofs] = np.arange(free_dofs.size, dtype="<i4")
    return create_execution_plan(
        model_ir_content_hash=_hash("1"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="LC1",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained_dofs,
        free_dofs=free_dofs,
        csr_row_ptr=np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    )


def _source_arrays():
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8")
    loads = np.zeros(12, dtype="<f8")
    loads[6] = 10.0
    loads[11] = 40.0
    return coordinates, loads


def _scaling(plan=None):
    plan = _plan() if plan is None else plan
    coordinates, loads = _source_arrays()
    return create_equation_scaling(
        execution_plan=plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )


def _bind(plan, scaling=None):
    scaling = _scaling(plan) if scaling is None else scaling
    coordinates, loads = _source_arrays()
    return bind_equation_scaling_to_execution_plan(
        plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )


def _coherently_rehash_scaling(scaling, **changes):
    provisional = replace(
        scaling,
        **changes,
        source_commitment_hash=_hash("0"),
        scaling_hash=_hash("0"),
    )
    provisional = replace(
        provisional,
        source_commitment_hash=canonical_hash(
            _source_commitment_payload(provisional, include_commitment_hash=False)
        ),
    )
    return replace(
        provisional,
        scaling_hash=canonical_hash(
            _scaling_payload(provisional, include_scaling_hash=False)
        ),
    )


def test_force_and_moment_scaling_is_deterministic_immutable_and_si_explicit() -> None:
    plan = _plan()
    first = _scaling(plan)
    second = _scaling(plan)
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    reference_loads = np.zeros(12)
    reference_loads[6] = 10.0
    reference_loads[11] = 40.0
    constrained_loads = reference_loads.copy()
    constrained_loads[0] = 1.0e9
    constrained_loads[3] = 1.0e9
    constrained_only_change = create_equation_scaling(
        execution_plan=plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=constrained_loads,
    )

    assert first.characteristic_length_m == 2.0
    assert first.reference_force_n == 20.0
    assert first.reference_equation_scope == REFERENCE_EQUATION_SCOPE
    np.testing.assert_array_equal(
        first.scale_divisors_si,
        np.asarray([20.0] * 3 + [40.0] * 3 + [20.0] * 3 + [40.0] * 3),
    )
    assert first.scaling_hash == second.scaling_hash
    assert first.scale_vector_content_hash == second.scale_vector_content_hash
    assert constrained_only_change.reference_force_n == first.reference_force_n
    np.testing.assert_array_equal(
        constrained_only_change.scale_divisors_si, first.scale_divisors_si
    )
    assert (
        constrained_only_change.source_reference_load_content_hash
        != first.source_reference_load_content_hash
    )
    assert constrained_only_change.scaling_hash != first.scaling_hash
    manifest = first.to_manifest()
    assert manifest["source_commitment"]["model_ir_content_hash"] == _hash("1")
    assert manifest["source_commitment"]["load_pattern_id"] == "LC1"
    assert manifest["source_commitment"]["reference_equation_scope"] == "free_equations"
    free_descriptor = next(row for row in plan.descriptors if row.name == "free_dofs")
    assert (
        manifest["source_commitment"]["free_dofs_content_hash"]
        == free_descriptor.content_hash
    )
    validate_equation_scaling(
        first,
        execution_plan=plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_loads,
    )
    changed_loads = reference_loads.copy()
    changed_loads[6] = 11.0
    with pytest.raises(EquationScalingError, match="source_commitment_mismatch"):
        validate_equation_scaling(
            first,
            execution_plan=plan,
            node_coordinates_m=coordinates,
            reference_equation_load_si=changed_loads,
        )
    assert not first.scale_divisors_si.flags.writeable
    with pytest.raises(ValueError):
        first.scale_divisors_si.setflags(write=True)


def test_scaling_binding_changes_plan_hash_and_state_binds_the_new_plan() -> None:
    base = _plan()
    scaling = _scaling(base)
    bound = _bind(base, scaling)

    assert bound.plan_hash != base.plan_hash
    assert base.capability_profile == EXECUTION_PLAN_CAPABILITY_PROFILE
    assert bound.capability_profile == EXECUTION_PLAN_SCALED_CAPABILITY_PROFILE
    assert execution_plan_scaling_hash(base) is None
    assert execution_plan_scaling_hash(bound) == scaling.scaling_hash
    assert bound.required_extensions == (EQUATION_SCALING_EXTENSION_KEY,)
    assert (
        bound.extensions[EQUATION_SCALING_EXTENSION_KEY]["base_plan_hash"]
        == base.plan_hash
    )
    assert (
        bound.extensions[EQUATION_SCALING_EXTENSION_KEY]["scale_vector_hash"]
        == scaling.scale_vector_content_hash
    )
    validate_execution_plan(bound)
    validate_equation_scaling_binding(bound, scaling=scaling)
    payload = deepcopy(bound.to_dict())
    del payload["extensions"][EQUATION_SCALING_EXTENSION_KEY]
    payload["capability_profile"] = EXECUTION_PLAN_CAPABILITY_PROFILE
    without_hash = dict(payload)
    without_hash.pop("plan_hash")
    payload["plan_hash"] = canonical_hash(without_hash)
    with pytest.raises(ExecutionPlanError) as missing_extension:
        validate_execution_plan_manifest(payload)
    assert missing_extension.value.code == "required_extension_missing"

    payload = deepcopy(bound.to_dict())
    del payload["extensions"][EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY]
    without_hash = dict(payload)
    without_hash.pop("plan_hash")
    payload["plan_hash"] = canonical_hash(without_hash)
    with pytest.raises(ExecutionPlanError) as optional_extension:
        validate_execution_plan_manifest(payload)
    assert optional_extension.value.code == "required_extension_declaration_missing"
    state = create_initial_state(bound)
    assert state.execution_plan_hash == bound.plan_hash


def test_binding_requires_exact_source_replay() -> None:
    base = _plan()
    scaling = _scaling(base)
    coordinates, loads = _source_arrays()

    with pytest.raises(EquationScalingError, match="source_replay_required"):
        bind_equation_scaling_to_execution_plan(
            base,
            scaling,
            node_coordinates_m=None,
            reference_equation_load_si=None,
        )

    changed_coordinates = coordinates.copy()
    changed_coordinates[1, 0] = 3.0
    with pytest.raises(EquationScalingError, match="source_commitment_mismatch"):
        bind_equation_scaling_to_execution_plan(
            base,
            scaling,
            node_coordinates_m=changed_coordinates,
            reference_equation_load_si=loads,
        )

    changed_loads = loads.copy()
    changed_loads[6] = 11.0
    with pytest.raises(EquationScalingError, match="source_commitment_mismatch"):
        bind_equation_scaling_to_execution_plan(
            base,
            scaling,
            node_coordinates_m=coordinates,
            reference_equation_load_si=changed_loads,
        )


def test_fully_constrained_plan_uses_no_solve_path_instead_of_scaling() -> None:
    plan = _plan(fully_constrained=True)
    coordinates, loads = _source_arrays()

    assert plan.free_dofs == ()
    with pytest.raises(EquationScalingError) as create_error:
        create_equation_scaling(
            execution_plan=plan,
            node_coordinates_m=coordinates,
            reference_equation_load_si=loads,
        )
    assert create_error.value.code == "free_equation_space_empty"

    with pytest.raises(EquationScalingError) as bind_error:
        bind_equation_scaling_to_execution_plan(
            plan,
            _scaling(),
            node_coordinates_m=coordinates,
            reference_equation_load_si=loads,
        )
    assert bind_error.value.code == "free_equation_space_empty"

    bound_manifest = deepcopy(_bind(_plan()).to_dict())
    bound_manifest["array_descriptors"]["free_dofs"]["shape"] = [0]
    without_hash = dict(bound_manifest)
    without_hash.pop("plan_hash")
    bound_manifest["plan_hash"] = canonical_hash(without_hash)
    with pytest.raises(EquationScalingError) as manifest_error:
        validate_execution_plan_manifest(bound_manifest)
    assert manifest_error.value.code == "free_equation_space_empty"


@pytest.mark.parametrize(
    ("changes", "error_code"),
    [
        ({"source_model_ir_content_hash": _hash("9")}, "source_model_ir_mismatch"),
        ({"source_load_pattern_id": "LC2"}, "source_load_pattern_mismatch"),
        (
            {"source_free_dofs_content_hash": _hash("9")},
            "source_free_dofs_mismatch",
        ),
    ],
)
def test_binding_rejects_self_consistent_scaling_for_another_source(
    changes, error_code
) -> None:
    base = _plan()
    scaling = _scaling(base)
    forged = _coherently_rehash_scaling(scaling, **changes)
    bound = _bind(base, scaling)

    validate_equation_scaling(forged)
    with pytest.raises(EquationScalingError) as error:
        validate_equation_scaling_binding(bound, scaling=forged)
    assert error.value.code == error_code


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("base_plan_hash", _hash("9"), "base_plan_hash_mismatch"),
        ("equation_order_hash", _hash("9"), "equation_order_hash_mismatch"),
        (
            "source_model_ir_content_hash",
            _hash("9"),
            "binding_source_model_ir_mismatch",
        ),
        (
            "source_load_pattern_id",
            "LC2",
            "binding_source_load_pattern_mismatch",
        ),
        (
            "source_free_dofs_content_hash",
            _hash("9"),
            "binding_source_free_dofs_mismatch",
        ),
    ],
)
def test_manifest_only_validation_rejects_coherently_rehashed_typed_binding(
    field, value, error_code
) -> None:
    base = _plan()
    bound = _bind(base)
    payload = deepcopy(bound.to_dict())
    payload["extensions"][EQUATION_SCALING_EXTENSION_KEY][field] = value
    without_hash = dict(payload)
    without_hash.pop("plan_hash")
    payload["plan_hash"] = canonical_hash(without_hash)

    with pytest.raises(EquationScalingError) as error:
        validate_execution_plan_manifest(payload)
    assert error.value.code == error_code


def test_scaled_capability_profile_is_mandatory_for_bound_manifest() -> None:
    bound = _bind(_plan())
    payload = deepcopy(bound.to_dict())
    payload["capability_profile"] = EXECUTION_PLAN_CAPABILITY_PROFILE
    without_hash = dict(payload)
    without_hash.pop("plan_hash")
    payload["plan_hash"] = canonical_hash(without_hash)

    with pytest.raises(ExecutionPlanError) as error:
        validate_execution_plan_manifest(payload)
    assert error.value.code == "execution_plan_schema_invalid"

    unbound_payload = deepcopy(_plan().to_dict())
    unbound_payload["capability_profile"] = EXECUTION_PLAN_SCALED_CAPABILITY_PROFILE
    without_hash = dict(unbound_payload)
    without_hash.pop("plan_hash")
    unbound_payload["plan_hash"] = canonical_hash(without_hash)
    with pytest.raises(ExecutionPlanError) as unbound_error:
        validate_execution_plan_manifest(unbound_payload)
    assert unbound_error.value.code == "execution_plan_schema_invalid"


def test_inputs_normalized_to_si_replay_exact_vector_and_hashes() -> None:
    plan = _plan()
    direct = _scaling(plan)
    coordinates_mm = np.asarray([[0.0, 0.0, 0.0], [2000.0, 0.0, 0.0]])
    loads_kn_knm = np.zeros(12)
    loads_kn_knm[6] = 0.01
    loads_kn_knm[11] = 0.04
    normalized = create_equation_scaling(
        execution_plan=plan,
        node_coordinates_m=coordinates_mm / 1000.0,
        reference_equation_load_si=loads_kn_knm * 1000.0,
    )

    np.testing.assert_array_equal(
        direct.scale_divisors_si, normalized.scale_divisors_si
    )
    assert direct.to_manifest() == normalized.to_manifest()


def test_residual_trace_separates_dimensions_and_uses_scaled_tie_break() -> None:
    base = _plan()
    scaling = _scaling(base)
    bound = _bind(base, scaling)
    raw = np.zeros(12)
    raw[6:12] = [10.0, -20.0, 0.0, 20.0, 0.0, -40.0]
    trace = trace_scaled_residual(
        execution_plan=bound, scaling=scaling, raw_residual_si=raw
    )

    np.testing.assert_array_equal(
        trace.scaled_residual[6:12], [0.5, -1.0, 0.0, 0.5, 0.0, -1.0]
    )
    assert trace.raw_translation_l2_n == math.sqrt(500.0)
    assert trace.raw_translation_linf_n == 20.0
    assert trace.raw_rotation_l2_nm == math.sqrt(2000.0)
    assert trace.raw_rotation_linf_nm == 40.0
    assert trace.scaled_l2 == math.sqrt(2.5)
    assert trace.scaled_linf == 1.0
    assert trace.equation_scope == "free_equations"
    assert trace.active_equations == bound.free_dofs
    assert (trace.governing_equation, trace.governing_node_id, trace.governing_dof) == (
        7,
        "N2",
        "UY",
    )
    assert trace.to_manifest()["authority"] == "non_authoritative_diagnostic"
    assert "converged" not in trace.to_manifest()
    with pytest.raises(EquationScalingError, match="residual_scope_mismatch"):
        trace_scaled_residual(
            execution_plan=bound,
            scaling=scaling,
            raw_residual_si=raw,
            active_equations=[6],
        )


@pytest.mark.parametrize(
    "active",
    ([6, 6], [7, 6], [True, 7], [6.0, 7], [-1, 6], [6, 12], []),
)
def test_active_equations_fail_closed(active) -> None:
    base = _plan()
    scaling = _scaling(base)
    bound = _bind(base, scaling)
    with pytest.raises(EquationScalingError, match="active_equations_invalid"):
        trace_scaled_residual(
            execution_plan=bound,
            scaling=scaling,
            raw_residual_si=np.zeros(12),
            active_equations=active,
        )


@pytest.mark.parametrize(
    ("coordinates", "loads", "message"),
    [
        (
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            np.zeros(12),
            "characteristic_length_invalid",
        ),
        ([[0.0, 0.0], [2.0, 0.0]], np.zeros(12), "array_shape_invalid"),
        ([[0.0, 0.0, 0.0], [2.0, 0.0, math.nan]], np.zeros(12), "array_invalid"),
        ([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], np.zeros(11), "array_shape_invalid"),
        ([[False, 0.0, 0.0], [2.0, 0.0, 0.0]], np.zeros(12), "array_invalid"),
        (
            [[1.0e308, 0.0, 0.0], [1.0e308, 0.0, 0.0]],
            np.zeros(12),
            "characteristic_length_invalid",
        ),
    ],
)
def test_invalid_geometry_and_load_contracts_fail_closed(
    coordinates, loads, message
) -> None:
    with pytest.raises(EquationScalingError, match=message):
        create_equation_scaling(
            execution_plan=_plan(),
            node_coordinates_m=coordinates,
            reference_equation_load_si=loads,
        )


def test_manifests_reject_unknown_fields_wrong_json_types_and_stale_hashes() -> None:
    base = _plan()
    scaling = _scaling(base)
    scaling_payload = deepcopy(scaling.to_manifest())
    scaling_payload["unexpected"] = True
    with pytest.raises(EquationScalingError, match="equation_scaling_schema_invalid"):
        validate_equation_scaling_manifest(scaling_payload)

    scaling_payload = deepcopy(scaling.to_manifest())
    scaling_payload["dof_count"] = 12.0
    with pytest.raises(EquationScalingError, match="equation_scaling_schema_invalid"):
        validate_equation_scaling_manifest(scaling_payload)

    bound = _bind(base, scaling)
    trace = trace_scaled_residual(
        execution_plan=bound, scaling=scaling, raw_residual_si=np.zeros(12)
    )
    trace_payload = deepcopy(trace.to_manifest())
    trace_payload["norms"]["scaled_l2"] = 1.0
    with pytest.raises(EquationScalingError, match="trace_metric_mismatch"):
        validate_scaled_residual_trace_manifest(trace_payload)

    scaling_payload = deepcopy(scaling.to_manifest())
    scaling_payload["scale_vector"]["values"][0] = 21.0
    scaling_without_hash = dict(scaling_payload)
    scaling_without_hash.pop("scaling_hash")
    scaling_payload["scaling_hash"] = canonical_hash(scaling_without_hash)
    with pytest.raises(EquationScalingError, match="scale_vector_hash_mismatch"):
        validate_equation_scaling_manifest(scaling_payload)

    scaling_payload = deepcopy(scaling.to_manifest())
    scaling_payload["source_commitment"]["load_pattern_id"] = "LC2"
    scaling_without_hash = dict(scaling_payload)
    scaling_without_hash.pop("scaling_hash")
    scaling_payload["scaling_hash"] = canonical_hash(scaling_without_hash)
    with pytest.raises(EquationScalingError, match="source_commitment_hash_mismatch"):
        validate_equation_scaling_manifest(scaling_payload)

    trace_payload = deepcopy(trace.to_manifest())
    trace_payload["vectors"]["raw_residual_si"][6] = 1.0
    trace_without_hash = dict(trace_payload)
    trace_without_hash.pop("trace_hash")
    trace_payload["trace_hash"] = canonical_hash(trace_without_hash)
    with pytest.raises(EquationScalingError, match="residual_hash_mismatch"):
        validate_scaled_residual_trace_manifest(trace_payload)


def test_tampered_artifacts_fail_closed() -> None:
    base = _plan()
    scaling = _scaling(base)
    with pytest.raises(EquationScalingError, match="scale_vector_hash_mismatch"):
        validate_equation_scaling(replace(scaling, scale_vector_data_hash=_hash("f")))

    bound = _bind(base, scaling)
    trace = trace_scaled_residual(
        execution_plan=bound, scaling=scaling, raw_residual_si=np.zeros(12)
    )
    with pytest.raises(EquationScalingError, match="trace_metric_mismatch"):
        validate_scaled_residual_trace(replace(trace, scaled_l2=1.0))
