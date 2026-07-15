from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    ExecutionPlanV2,
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.contracts.result_ir_v2 import (  # noqa: E402
    ResultIRV2,
    ResultIRV2Error,
    ResultIRV2SourceProvenance,
    SourceProvenance,
    _array_artifact,
    _numerical_hash,
    _receipt_hash,
    build_result_ir_v2,
    validate_result_ir_v2,
    validate_result_ir_v2_manifest,
    validate_result_ir_v2_physics,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    StateIR,
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.operators.sparse_linear_static import (  # noqa: E402
    solve_sparse_execution_plan_v2,
)
from structural_analysis.model_ir import parse_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/result_ir_v2.schema.json"
MODULE = REPO_ROOT / "src/structural_analysis/engine_v2/contracts/result_ir_v2.py"


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _payload() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _chain_payload(node_count: int) -> dict[str, Any]:
    payload = _payload()
    node_template = deepcopy(payload["nodes"][0])
    element_template = deepcopy(payload["elements"][0])
    payload["nodes"] = []
    for index in range(node_count):
        node = deepcopy(node_template)
        node.update(
            {
                "id": f"N{index + 1}",
                "index": index,
                "coordinates_m": [2.0 * index, 0.0, 0.0],
                "source_id": f"generated:N{index + 1}",
            }
        )
        payload["nodes"].append(node)
    payload["elements"] = []
    for index in range(node_count - 1):
        element = deepcopy(element_template)
        element.update(
            {
                "id": f"E{index + 1}",
                "index": index,
                "node_ids": [f"N{index + 1}", f"N{index + 2}"],
                "source_id": f"generated:E{index + 1}",
            }
        )
        payload["elements"].append(element)
    for pattern in payload["load_patterns"]:
        pattern["nodal_loads"][0]["node_id"] = f"N{node_count}"
    return payload


def _provenance(
    displacement: np.ndarray,
    plan: ExecutionPlanV2,
    exported_free_residual: np.ndarray,
) -> SourceProvenance:
    free_solution = immutable_array(
        displacement[np.asarray(plan.free_dofs, dtype=np.int64)], dtype="<f8"
    )
    exported = immutable_array(exported_free_residual, dtype="<f8")
    return SourceProvenance(
        case_id="frame_single_axial",
        case_parity_receipt_hash=_hash("1"),
        terminal_observation_receipt_hash=_hash("2"),
        completion_export_receipt_hash=_hash("3"),
        completion_export_payload_hash=_hash("4"),
        device_identity_receipt_hash=_hash("5"),
        solution_payload_sha256=array_data_hash(free_solution),
        exported_free_residual_payload_sha256=array_data_hash(exported),
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_uuid_bytes_hex="0123456789abcdef0123456789abcdef",
        device_pci_bdf="0000:03:00.0",
    )


def _pipeline(
    payload: dict[str, Any] | None = None,
) -> tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2]:
    buffers = pack_solver_model_buffers(
        parse_model_ir_v2(_payload() if payload is None else payload),
        load_pattern_id="LC_AXIAL",
    )
    plan = compile_execution_plan_v2(buffers)
    direct_result = solve_sparse_execution_plan_v2(plan)
    displacement = (
        np.asarray(direct_result.displacements_si, dtype="<f8").reshape(-1).copy()
    )

    # Keep a deterministic, resolvable non-zero free residual below tolerance.
    # This makes the F-Ku versus Ku-F sign test meaningful instead of relying on
    # direct-solve round-off residuals that may compare equal to zero.
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    constrained = np.asarray(plan.constrained_dofs, dtype=np.int64)
    direction = np.zeros(plan.dof_count, dtype="<f8")
    direction[free] = np.linspace(1.0, 2.0, free.size, dtype="<f8")
    effect = plan.jvp(direction)[free]
    load = plan.array("global_load")
    load_scale = max(1.0, float(np.max(np.abs(load[free]))))
    target_linf = 0.2 * plan.residual_tolerance * load_scale
    displacement += direction * (target_linf / float(np.max(np.abs(effect))))
    displacement[constrained] = 0.0
    residual = np.asarray(plan.residual(displacement), dtype="<f8")
    assert 1.0e-3 * target_linf < float(np.max(np.abs(residual[free])))
    assert float(np.max(np.abs(residual[free]))) / load_scale < plan.residual_tolerance
    exported = np.ascontiguousarray(-residual[free], dtype="<f8")

    accepted = create_initial_state(plan)
    trial = open_trial_state(
        accepted,
        displacement,
        load_step=1,
        iteration=4,
        load_factor=1.0,
        expected_plan=plan,
    )
    committed = commit_trial_state(accepted, trial, expected_plan=plan)
    receipt = build_result_ir_v2(
        plan,
        trial,
        committed,
        displacement,
        exported,
        _provenance(displacement, plan, exported),
    )
    return plan, trial, committed, receipt


@pytest.fixture(scope="module")
def pipeline() -> tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2]:
    return _pipeline()


def _rehash(receipt: ResultIRV2, **changes: Any) -> ResultIRV2:
    forged = replace(receipt, **changes)
    forged = replace(
        forged,
        numerical_result_hash=_numerical_hash(
            forged.arrays, forged.convergence, forged.energy
        ),
    )
    return replace(forged, result_ir_hash=_receipt_hash(forged.to_dict()))


def _replace_array(receipt: ResultIRV2, name: str, values: np.ndarray) -> ResultIRV2:
    original = getattr(receipt.arrays, name)
    replacement = _array_artifact(
        name,
        values,
        axis_labels=original.axis_labels,
        component_labels=original.component_labels,
        component_units=original.component_units,
    )
    return _rehash(receipt, arrays=replace(receipt.arrays, **{name: replacement}))


def test_result_ir_v2_recovers_six_arrays_and_all_physical_identities(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
) -> None:
    plan, trial, committed, receipt = pipeline
    assert validate_result_ir_v2(receipt) is receipt
    assert (
        validate_result_ir_v2_physics(
            receipt,
            expected_plan=plan,
            expected_evaluated_trial_state=trial,
            expected_committed_state=committed,
        )
        is receipt
    )

    arrays = receipt.arrays
    assert tuple(row.name for row in arrays.ordered()) == (
        "displacements_si",
        "residual_si",
        "reactions_si",
        "element_end_forces_local_si",
        "element_strain_energy_j",
        "exported_free_residual_si",
    )
    displacement = arrays.displacements_si.values.reshape(-1)
    residual = arrays.residual_si.values.reshape(-1)
    reactions = arrays.reactions_si.values.reshape(-1)
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    constrained = np.asarray(plan.constrained_dofs, dtype=np.int64)
    np.testing.assert_array_equal(displacement, trial.displacement_si)
    np.testing.assert_allclose(
        residual, plan.residual(displacement), rtol=0.0, atol=0.0
    )
    np.testing.assert_array_equal(reactions[free], np.zeros(free.size))
    np.testing.assert_allclose(
        reactions[constrained], residual[constrained], rtol=0.0, atol=0.0
    )
    np.testing.assert_allclose(
        arrays.exported_free_residual_si.values,
        -residual[free],
        rtol=0.0,
        atol=0.0,
    )

    expected_forces = np.zeros((plan.element_count, 2, 6), dtype="<f8")
    expected_element_energy = np.zeros(plan.element_count, dtype="<f8")
    element_dofs = plan.array("element_global_dofs")
    transforms = plan.array("recovery_transform_global_to_local")
    stiffness = plan.array("recovery_stiffness_local")
    for index in range(plan.element_count):
        local_displacement = transforms[index] @ displacement[element_dofs[index]]
        local_force = stiffness[index] @ local_displacement
        expected_forces[index] = local_force.reshape(2, 6)
        expected_element_energy[index] = 0.5 * float(local_displacement @ local_force)
    np.testing.assert_allclose(
        arrays.element_end_forces_local_si.values,
        expected_forces,
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        arrays.element_strain_energy_j.values,
        expected_element_energy,
        rtol=0.0,
        atol=0.0,
    )

    load = plan.array("global_load")
    element_sum = float(np.sum(expected_element_energy))
    global_energy = 0.5 * float(displacement @ (residual + load))
    external_energy = 0.5 * float(displacement @ load)
    residual_work = 0.5 * float(displacement @ residual)
    assert receipt.energy.total_strain_energy_j == pytest.approx(element_sum)
    assert receipt.energy.global_strain_energy_j == pytest.approx(global_energy)
    assert global_energy - external_energy == pytest.approx(residual_work)
    assert receipt.energy.balance_error_j == pytest.approx(0.0, abs=1.0e-15)


def test_manifest_is_strict_descriptor_only_and_arrays_are_bytes_backed_immutable(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
) -> None:
    _, _, _, receipt = pipeline
    manifest = receipt.to_manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(manifest))

    for name, descriptor in manifest["arrays"].items():
        assert "values" not in descriptor
        assert "_values" not in descriptor
        artifact = getattr(receipt.arrays, name)
        assert artifact.values.dtype.str == "<f8"
        assert artifact.values.flags.c_contiguous
        assert not artifact.values.flags.writeable
        assert has_immutable_bytes_backing(artifact.values)
        with pytest.raises(ValueError):
            artifact.values.setflags(write=True)

    for path in (("unknown",), ("arrays", "residual_si", "values")):
        forged = deepcopy(manifest)
        target = forged
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = []
        assert list(validator.iter_errors(forged))
        with pytest.raises(ResultIRV2Error) as error:
            validate_result_ir_v2_manifest(forged)
        assert error.value.code == "result_ir_v2_schema_invalid"


def test_storage_and_descriptor_tampering_fail_structural_validation(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
) -> None:
    _, _, _, receipt = pipeline
    original = receipt.arrays.residual_si
    mutable_row = replace(original, _values=original.values.copy())
    mutable = replace(receipt, arrays=replace(receipt.arrays, residual_si=mutable_row))
    with pytest.raises(ResultIRV2Error) as mutable_error:
        validate_result_ir_v2(mutable)
    assert mutable_error.value.code == "result_ir_v2_array_storage_invalid"

    stale_row = replace(original, byte_length=original.byte_length + 8)
    stale = replace(receipt, arrays=replace(receipt.arrays, residual_si=stale_row))
    with pytest.raises(ResultIRV2Error) as descriptor_error:
        validate_result_ir_v2(stale)
    assert descriptor_error.value.code == "result_ir_v2_array_descriptor_mismatch"

    reactions = receipt.arrays.reactions_si
    signed_zero_values = reactions.values.copy()
    zero_index = int(np.flatnonzero(signed_zero_values.reshape(-1) == 0.0)[0])
    signed_zero_values.reshape(-1)[zero_index] = -0.0
    signed_zero_row = replace(
        reactions,
        _values=immutable_array(signed_zero_values, dtype="<f8"),
    )
    signed_zero = replace(
        receipt, arrays=replace(receipt.arrays, reactions_si=signed_zero_row)
    )
    assert has_immutable_bytes_backing(signed_zero_row.values)
    assert np.signbit(signed_zero_row.values.reshape(-1)[zero_index])
    with pytest.raises(ResultIRV2Error) as signed_zero_error:
        validate_result_ir_v2(signed_zero)
    assert signed_zero_error.value.code == "result_ir_v2_signed_zero_not_normalized"


def test_manifest_rejects_python_numeric_aliases_after_schema_validation(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
) -> None:
    _, _, _, receipt = pipeline
    manifest = receipt.to_manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path, alias in (
        (("convergence", "load_scale"), int(receipt.convergence.load_scale)),
        (("energy", "balance_error_j"), 0),
        (
            ("ordering", "constrained_dofs", 0),
            float(receipt.ordering.constrained_dofs[0]),
        ),
        (
            ("arrays", "residual_si", "byte_length"),
            float(receipt.arrays.residual_si.byte_length),
        ),
        (("source_provenance", "additional_solve_count"), 0.0),
    ):
        forged = deepcopy(manifest)
        target: Any = forged
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = alias
        assert not list(validator.iter_errors(forged))
        with pytest.raises(ResultIRV2Error) as error:
            validate_result_ir_v2_manifest(forged)
        assert error.value.code == "result_ir_v2_scalar_type_invalid"


@pytest.mark.parametrize(
    ("name", "expected_code"),
    (
        ("residual_si", "result_ir_v2_residual_invariant_failed"),
        ("reactions_si", "result_ir_v2_reaction_invariant_failed"),
        (
            "element_end_forces_local_si",
            "result_ir_v2_member_force_invariant_failed",
        ),
        ("element_strain_energy_j", "result_ir_v2_element_energy_invariant_failed"),
    ),
)
def test_fully_rehashed_physical_array_tampering_fails_source_replay(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
    name: str,
    expected_code: str,
) -> None:
    plan, trial, committed, receipt = pipeline
    values = getattr(receipt.arrays, name).values.copy()
    values.reshape(-1)[0] += 1.0
    forged = _replace_array(receipt, name, values)
    assert validate_result_ir_v2(forged) is forged

    with pytest.raises(ResultIRV2Error) as error:
        validate_result_ir_v2_physics(
            forged,
            expected_plan=plan,
            expected_evaluated_trial_state=trial,
            expected_committed_state=committed,
        )
    assert error.value.code == expected_code


def test_fully_rehashed_exported_residual_sign_inversion_fails_physics(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
) -> None:
    plan, trial, committed, receipt = pipeline
    free = np.asarray(plan.free_dofs, dtype=np.int64)
    wrong_sign = np.ascontiguousarray(
        receipt.arrays.residual_si.values.reshape(-1)[free], dtype="<f8"
    )
    forged = _replace_array(receipt, "exported_free_residual_si", wrong_sign)
    forged = _rehash(
        forged,
        source_provenance=replace(
            forged.source_provenance,
            exported_free_residual_payload_sha256=(
                forged.arrays.exported_free_residual_si.data_hash
            ),
        ),
    )
    assert validate_result_ir_v2(forged) is forged

    with pytest.raises(ResultIRV2Error) as error:
        validate_result_ir_v2_physics(
            forged,
            expected_plan=plan,
            expected_evaluated_trial_state=trial,
            expected_committed_state=committed,
        )
    assert error.value.code == "result_ir_v2_exported_residual_sign_mismatch"


@pytest.mark.parametrize("field", ("execution_plan_hash", "committed_state_hash"))
def test_fully_rehashed_plan_and_state_binding_tampering_fails_closed(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
    field: str,
) -> None:
    plan, trial, committed, receipt = pipeline
    bindings = replace(receipt.input_bindings, **{field: _hash("e")})
    forged = _rehash(receipt, input_bindings=bindings)
    assert validate_result_ir_v2(forged) is forged

    with pytest.raises(ResultIRV2Error) as error:
        validate_result_ir_v2_physics(
            forged,
            expected_plan=plan,
            expected_evaluated_trial_state=trial,
            expected_committed_state=committed,
        )
    assert error.value.code == "result_ir_v2_input_binding_mismatch"


def test_source_provenance_is_exact_typed_and_claims_remain_bounded_false(
    pipeline: tuple[ExecutionPlanV2, StateIR, StateIR, ResultIRV2],
) -> None:
    plan, trial, committed, receipt = pipeline
    provenance = receipt.source_provenance
    assert type(provenance) is SourceProvenance
    assert ResultIRV2SourceProvenance is SourceProvenance
    for field in (
        "additional_device_operation_count",
        "additional_d2h_operation_count",
        "additional_solve_count",
        "additional_export_count",
        "fallback_count",
    ):
        assert type(getattr(provenance, field)) is int
        assert getattr(provenance, field) == 0
    assert provenance.live_authority_serialized is False

    positive_claims = {
        "result_ir_verified",
        "result_ir_ready",
        "state_ir_lineage_verified",
        "reaction_recovery_verified",
        "member_force_recovery_verified",
        "energy_identities_verified",
    }
    for field, value in receipt.claims.to_dict().items():
        assert value is (field in positive_claims)

    class ProvenanceSubclass(SourceProvenance):
        pass

    subclass = ProvenanceSubclass(**provenance.to_dict())
    with pytest.raises(ResultIRV2Error) as type_error:
        build_result_ir_v2(
            plan,
            trial,
            committed,
            receipt.arrays.displacements_si.values.reshape(-1),
            receipt.arrays.exported_free_residual_si.values,
            subclass,
        )
    assert type_error.value.code == "result_ir_v2_provenance_type_invalid"

    invalid_counter = replace(provenance, additional_solve_count=False)
    with pytest.raises(ResultIRV2Error) as counter_error:
        build_result_ir_v2(
            plan,
            trial,
            committed,
            receipt.arrays.displacements_si.values.reshape(-1),
            receipt.arrays.exported_free_residual_si.values,
            invalid_counter,
        )
    assert counter_error.value.code == "result_ir_v2_additional_operation_nonzero"

    promoted = replace(receipt, claims=replace(receipt.claims, commercial_ready=True))
    with pytest.raises(ResultIRV2Error) as claim_error:
        validate_result_ir_v2(promoted)
    assert claim_error.value.code == "result_ir_v2_claim_invalid"


def test_retained_array_bytes_follow_exact_linear_materialization_formula() -> None:
    observations: list[tuple[int, int]] = []
    for node_count in (2, 4):
        plan, _, _, receipt = _pipeline(_chain_payload(node_count))
        retained_bytes = sum(row.byte_length for row in receipt.arrays.ordered())
        expected_bytes = (
            24 * plan.dof_count + 104 * plan.element_count + 8 * len(plan.free_dofs)
        )
        assert retained_bytes == expected_bytes
        assert len(receipt.to_manifest()["arrays"]) == 6
        observations.append((plan.dof_count, retained_bytes))
    assert observations[1][0] > observations[0][0]
    assert observations[1][1] > observations[0][1]


def test_result_ir_v2_recovery_has_no_dense_conversion_or_solver_call() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    identifiers.update(
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    )
    forbidden = {
        "global_stiffness_dense",
        "toarray",
        "todense",
        "spsolve",
        "solve",
        "solve_linear_static",
        "solve_sparse_execution_plan_v2",
    }
    assert forbidden.isdisjoint(identifiers)

    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.startswith("scipy") for name in imported_modules)
