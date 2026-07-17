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
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    create_execution_plan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _plan():
    dof_count = 12
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
        global_to_free=np.asarray(
            [-1, -1, -1, -1, -1, -1, 0, 1, 2, 3, 4, 5], dtype="<i4"
        ),
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=np.arange(6, dtype="<i4"),
        free_dofs=np.arange(6, dof_count, dtype="<i4"),
        csr_row_ptr=np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    )


def _scaling(plan=None):
    plan = _plan() if plan is None else plan
    loads = np.zeros(12, dtype="<f8")
    loads[6] = 10.0
    loads[11] = 40.0
    return create_equation_scaling(
        execution_plan=plan,
        node_coordinates_m=[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        reference_equation_load_si=loads,
    )


def test_force_and_moment_scaling_is_deterministic_immutable_and_si_explicit() -> None:
    plan = _plan()
    first = _scaling(plan)
    second = _scaling(plan)

    assert first.characteristic_length_m == 2.0
    assert first.reference_force_n == 20.0
    np.testing.assert_array_equal(
        first.scale_divisors_si,
        np.asarray([20.0] * 3 + [40.0] * 3 + [20.0] * 3 + [40.0] * 3),
    )
    assert first.scaling_hash == second.scaling_hash
    assert first.scale_vector_content_hash == second.scale_vector_content_hash
    assert not first.scale_divisors_si.flags.writeable
    with pytest.raises(ValueError):
        first.scale_divisors_si.setflags(write=True)


def test_scaling_binding_changes_plan_hash_and_state_binds_the_new_plan() -> None:
    base = _plan()
    scaling = _scaling(base)
    bound = bind_equation_scaling_to_execution_plan(base, scaling)

    assert bound.plan_hash != base.plan_hash
    assert execution_plan_scaling_hash(base) is None
    assert execution_plan_scaling_hash(bound) == scaling.scaling_hash
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
    state = create_initial_state(bound)
    assert state.execution_plan_hash == bound.plan_hash


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
    bound = bind_equation_scaling_to_execution_plan(base, scaling)
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
    assert (trace.governing_equation, trace.governing_node_id, trace.governing_dof) == (
        7,
        "N2",
        "UY",
    )
    assert trace.to_manifest()["authority"] == "non_authoritative_diagnostic"
    assert "converged" not in trace.to_manifest()


@pytest.mark.parametrize(
    "active",
    ([6, 6], [7, 6], [True, 7], [6.0, 7], [-1, 6], [6, 12], []),
)
def test_active_equations_fail_closed(active) -> None:
    base = _plan()
    scaling = _scaling(base)
    bound = bind_equation_scaling_to_execution_plan(base, scaling)
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

    bound = bind_equation_scaling_to_execution_plan(base, scaling)
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

    bound = bind_equation_scaling_to_execution_plan(base, scaling)
    trace = trace_scaled_residual(
        execution_plan=bound, scaling=scaling, raw_residual_si=np.zeros(12)
    )
    with pytest.raises(EquationScalingError, match="trace_metric_mismatch"):
        validate_scaled_residual_trace(replace(trace, scaled_l2=1.0))
