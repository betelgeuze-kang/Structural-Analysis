from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    immutable_array,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (  # noqa: E402
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    create_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (  # noqa: E402
    EXECUTION_PLAN_REDUCED_CSR_SCHEMA_VERSION,
    ExecutionPlanReducedCSRError,
    _array_descriptor,
    _free_pattern_hash,
    _identity_hash,
    create_execution_plan_reduced_csr,
    validate_execution_plan_reduced_csr,
    validate_execution_plan_reduced_csr_manifest,
)

SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/execution_plan_reduced_csr_v1.schema.json"
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _inputs(*, fully_constrained: bool = False) -> dict[str, object]:
    dof_count = 12
    free = (
        np.asarray([], dtype="<i4")
        if fully_constrained
        else np.arange(6, dof_count, dtype="<i4")
    )
    constrained = (
        np.arange(dof_count, dtype="<i4")
        if fully_constrained
        else np.arange(6, dtype="<i4")
    )
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    return {
        "model_ir_content_hash": _hash("1"),
        "solver_buffer_schema_version": "solver-model-buffers.v1",
        "solver_numeric_buffer_hash": _hash("2"),
        "solver_entity_mapping_hash": _hash("3"),
        "solver_artifact_hash": _hash("4"),
        "load_pattern_id": "LC1",
        "operator_id": "linear-static-operator",
        "operator_version": "linear-static-operator.v1",
        "operator_hash": _hash("5"),
        "node_ids": ("N1", "N2"),
        "element_ids": ("E1",),
        "node_dof_indices": np.arange(dof_count, dtype="<i4").reshape(2, 6),
        "global_to_free": global_to_free,
        "element_global_dofs": np.arange(dof_count, dtype="<i4").reshape(1, 12),
        "constrained_dofs": constrained,
        "free_dofs": free,
        "csr_row_ptr": np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        "csr_column_indices": np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    }


def _plan(*, fully_constrained: bool = False):
    return create_execution_plan(**_inputs(fully_constrained=fully_constrained))


def test_reduced_csr_identity_is_deterministic_strict_and_exactly_ordered() -> None:
    first = create_execution_plan_reduced_csr(
        _plan(), operator_numeric_values_hash=_hash("6")
    )
    second = create_execution_plan_reduced_csr(
        _plan(), operator_numeric_values_hash=_hash("6")
    )
    manifest = first.to_manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert first.schema_version == EXECUTION_PLAN_REDUCED_CSR_SCHEMA_VERSION
    assert first.identity_hash == second.identity_hash
    assert first.free_count == 6
    assert first.free_nnz == 36
    assert first.terminal_disposition == "solve_free_equations"
    np.testing.assert_array_equal(
        first.array("free_csr_row_ptr"), np.arange(0, 37, 6, dtype="<i8")
    )
    np.testing.assert_array_equal(
        first.array("free_csr_column_indices"),
        np.tile(np.arange(6, dtype="<i4"), 6),
    )
    expected_positions = np.concatenate(
        [np.arange(row * 12 + 6, row * 12 + 12) for row in range(6, 12)]
    )
    np.testing.assert_array_equal(
        first.array("free_csr_global_value_indices"), expected_positions
    )
    assert manifest["global_csr"]["numeric_values_scope"] == (
        "global_csr_values_in_global_pattern_order"
    )
    assert manifest["claim_boundary"]["numeric_values_embedded"] is False


def test_fully_constrained_plan_has_explicit_no_solve_reduced_identity() -> None:
    identity = create_execution_plan_reduced_csr(
        _plan(fully_constrained=True), operator_numeric_values_hash=_hash("6")
    )

    assert identity.free_count == 0
    assert identity.free_nnz == 0
    assert identity.terminal_disposition == "no_solve_reaction_only"
    np.testing.assert_array_equal(
        identity.array("free_csr_row_ptr"), np.asarray([0], dtype="<i8")
    )
    assert identity.array("free_csr_column_indices").size == 0
    assert identity.array("free_csr_global_value_indices").size == 0


def test_reduced_identity_binds_the_scaled_execution_plan_hash() -> None:
    base = _plan()
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    loads = np.arange(1.0, 13.0, dtype="<f8")
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )
    bound = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )

    identity = create_execution_plan_reduced_csr(
        bound, operator_numeric_values_hash=_hash("6")
    )

    assert identity.execution_plan_hash == bound.plan_hash
    assert identity.execution_plan_hash != base.plan_hash
    validate_execution_plan_reduced_csr(identity, execution_plan=bound)
    with pytest.raises(ExecutionPlanReducedCSRError) as error:
        validate_execution_plan_reduced_csr(identity, execution_plan=base)
    assert error.value.code == "reduced_csr_source_plan_mismatch"


def test_operator_numeric_values_hash_changes_identity_not_free_pattern() -> None:
    first = create_execution_plan_reduced_csr(
        _plan(), operator_numeric_values_hash=_hash("6")
    )
    second = create_execution_plan_reduced_csr(
        _plan(), operator_numeric_values_hash=_hash("7")
    )

    assert first.free_pattern_hash == second.free_pattern_hash
    assert first.identity_hash != second.identity_hash


def test_validator_rejects_fully_rehashed_reduced_projection_tamper() -> None:
    identity = create_execution_plan_reduced_csr(
        _plan(), operator_numeric_values_hash=_hash("6")
    )
    arrays = dict(identity._arrays)
    positions = np.asarray(arrays["free_csr_global_value_indices"]).copy()
    positions[0] += 1
    arrays["free_csr_global_value_indices"] = immutable_array(positions, dtype="<i8")
    frozen_arrays = MappingProxyType(arrays)
    descriptors = tuple(
        _array_descriptor(row.name, frozen_arrays[row.name])
        for row in identity.descriptors
    )
    descriptor_by_name = {row.name: row for row in descriptors}
    forged = replace(
        identity,
        descriptors=descriptors,
        _arrays=frozen_arrays,
        free_pattern_hash=_free_pattern_hash(
            global_pattern_hash=identity.global_pattern_hash,
            global_to_free_content_hash=identity.global_to_free_content_hash,
            free_dofs_content_hash=identity.free_dofs_content_hash,
            descriptor_by_name=descriptor_by_name,
        ),
        identity_hash=_hash("0"),
    )
    forged = replace(forged, identity_hash=_identity_hash(forged))

    with pytest.raises(ExecutionPlanReducedCSRError) as error:
        validate_execution_plan_reduced_csr(forged)

    assert error.value.code == "reduced_csr_derivation_mismatch"


def test_manifest_rejects_wrong_descriptor_semantics_and_stale_hash() -> None:
    identity = create_execution_plan_reduced_csr(
        _plan(), operator_numeric_values_hash=_hash("6")
    )
    wrong_dtype = deepcopy(identity.to_manifest())
    wrong_dtype["array_descriptors"]["free_csr_row_ptr"]["dtype"] = "<i4"
    with pytest.raises(ExecutionPlanReducedCSRError) as dtype_error:
        validate_execution_plan_reduced_csr_manifest(wrong_dtype)
    assert dtype_error.value.code == "reduced_csr_descriptor_semantics_invalid"

    stale = deepcopy(identity.to_manifest())
    stale["global_csr"]["operator_numeric_values_hash"] = _hash("9")
    with pytest.raises(ExecutionPlanReducedCSRError) as stale_error:
        validate_execution_plan_reduced_csr_manifest(stale)
    assert stale_error.value.code == "reduced_csr_identity_hash_mismatch"


def test_reduced_csr_public_api_exports_contract() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.contracts as contracts

    assert engine_v2.ExecutionPlanReducedCSR is contracts.ExecutionPlanReducedCSR
    assert (
        engine_v2.create_execution_plan_reduced_csr
        is contracts.create_execution_plan_reduced_csr
    )
