from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.contracts import (
    DIAGNOSTIC_AUTHORITY_PROFILE,
    DIAGNOSTIC_IR_SCHEMA_VERSION,
    NUMERICAL_RESULT_AUTHORITY_PROFILE,
    NUMERICAL_RESULT_IR_SCHEMA_VERSION,
    DiagnosticIR,
    DiagnosticIRSourceSnapshot,
    NumericalResultIR,
    ResultIRError,
    bind_equation_scaling_to_execution_plan,
    commit_trial_state,
    create_diagnostic_entry,
    create_diagnostic_ir,
    create_adapter_bound_diagnostic_ir,
    create_equation_scaling,
    create_execution_plan,
    create_execution_plan_reduced_csr,
    create_initial_state,
    create_numerical_result_ir,
    open_trial_state,
    validate_diagnostic_ir_manifest,
    validate_diagnostic_ir,
    validate_numerical_result_displacement_bytes,
    validate_numerical_result_ir_manifest,
    write_numerical_result_displacement_artifact,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)


ROOT = Path(__file__).resolve().parents[1]


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _base_plan():
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


def _fixture():
    base = _base_plan()
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8")
    loads = np.zeros(12, dtype="<f8")
    loads[6] = 10.0
    loads[11] = 40.0
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )
    reduced = create_execution_plan_reduced_csr(
        plan,
        operator_numeric_values_hash=_hash("6"),
    )
    initial = create_initial_state(plan)
    displacement = np.zeros(12, dtype="<f8")
    displacement[6:] = np.asarray([0.001, -0.002, 0.003, 0.004, -0.005, 0.006])
    trial = open_trial_state(
        initial,
        displacement,
        load_step=1,
        iteration=4,
        load_factor=1.0,
        time_s=0.0,
        expected_plan=plan,
    )
    state = commit_trial_state(initial, trial, expected_plan=plan)
    free_solution = immutable_array(
        state.displacement_si[plan.array("free_dofs")], dtype="<f8"
    )
    return plan, scaling, reduced, state, array_data_hash(free_solution)


def _result(**overrides) -> NumericalResultIR:
    plan, scaling, reduced, state, solution_hash = _fixture()
    values = {
        "result_id": "result.linear.lc1",
        "execution_plan": plan,
        "equation_scaling": scaling,
        "reduced_csr": reduced,
        "committed_state": state,
        "source_run_schema_version": "structural-analysis-cpu-fgmres-run.v1",
        "source_run_hash": _hash("7"),
        "source_terminal_reason": "converged_scaled_residual",
        "source_solution_data_hash": solution_hash,
        "convergence_receipt_hash": _hash("8"),
        "full_residual_receipt_hash": _hash("9"),
        "boundary_condition_receipt_hash": _hash("a"),
        "backend_role": "cpu_reference",
        "backend_receipt_hash": _hash("b"),
        "diagnostic_ir_hashes": (_hash("c"),),
    }
    values.update(overrides)
    return create_numerical_result_ir(**values)


def _rehash(payload: dict, field: str) -> None:
    without_hash = dict(payload)
    without_hash.pop(field)
    payload[field] = canonical_hash(without_hash)


def test_numerical_result_ir_is_deterministic_bound_and_schema_valid() -> None:
    import structural_analysis.engine_v2 as engine_v2

    first = _result()
    second = _result()
    manifest = first.to_manifest()
    schema = json.loads(
        (ROOT / "src/structural_analysis/schemas/numerical_result_ir_v1.schema.json")
        .read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert first.schema_version == NUMERICAL_RESULT_IR_SCHEMA_VERSION
    assert engine_v2.NumericalResultIR is NumericalResultIR
    assert engine_v2.DiagnosticIR is DiagnosticIR
    assert not hasattr(engine_v2, "ResultIR")
    assert first.authority_profile == NUMERICAL_RESULT_AUTHORITY_PROFILE
    assert first.result_hash == second.result_hash
    assert manifest["authority"] == {
        "numerical_state": "authoritative",
        "convergence": "authoritative",
        "displacement": "authoritative",
        "reaction": "not_evaluated",
        "member_force": "not_evaluated",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
    assert manifest["claim_boundary"]["engineering_result_recovery"] is False
    assert manifest["claim_boundary"]["reaction_authority"] is False
    assert manifest["claim_boundary"]["member_force_authority"] is False
    assert manifest["source_terminal"]["fallback_count"] == 0
    assert manifest["source_terminal"]["regularization_count"] == 0
    assert first.displacement_artifact.data_hash == first._committed_state.vector_hashes[
        "displacement"
    ]
    assert first.displacement_global_si.flags.writeable is False
    with pytest.raises(ValueError):
        first.displacement_global_si.setflags(write=True)


def test_numerical_result_artifact_roundtrip_is_hash_bound_and_no_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _result()
    target = tmp_path / "displacement_global.f64le"

    written = write_numerical_result_displacement_artifact(result, target)
    restored = validate_numerical_result_displacement_bytes(
        result, written.read_bytes()
    )
    np.testing.assert_array_equal(restored, result.displacement_global_si)

    tampered = bytearray(written.read_bytes())
    tampered[-1] ^= 1
    with pytest.raises(ResultIRError) as tamper_error:
        validate_numerical_result_displacement_bytes(result, tampered)
    assert tamper_error.value.code == "numerical_result_artifact_hash_mismatch"

    with pytest.raises(ResultIRError) as overwrite_error:
        write_numerical_result_displacement_artifact(result, target)
    assert overwrite_error.value.code == "numerical_result_artifact_target_exists"

    race_target = tmp_path / "race" / "displacement_global.f64le"
    original_open = Path.open

    def racing_open(path: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path == race_target and mode == "xb" and not path.exists():
            with original_open(path, "wb") as winner:
                winner.write(b"concurrent-winner")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    with pytest.raises(ResultIRError) as race_error:
        write_numerical_result_displacement_artifact(result, race_target)
    assert race_error.value.code == "numerical_result_artifact_target_exists"
    assert race_target.read_bytes() == b"concurrent-winner"


def test_numerical_result_rejects_unbound_solution_and_nonconverged_terminal() -> None:
    with pytest.raises(ResultIRError) as solution_error:
        _result(source_solution_data_hash=_hash("f"))
    assert solution_error.value.code == "result_source_solution_state_mismatch"

    with pytest.raises(ResultIRError) as terminal_error:
        _result(source_terminal_reason="max_iterations")
    assert terminal_error.value.code == "result_source_terminal_not_converged"

    plan, scaling, reduced, _state, solution_hash = _fixture()
    initial = create_initial_state(plan)
    with pytest.raises(ResultIRError) as state_error:
        create_numerical_result_ir(
            result_id="result.initial.invalid",
            execution_plan=plan,
            equation_scaling=scaling,
            reduced_csr=reduced,
            committed_state=initial,
            source_run_schema_version="structural-analysis-cpu-fgmres-run.v1",
            source_run_hash=_hash("7"),
            source_terminal_reason="initial_residual_satisfied",
            source_solution_data_hash=solution_hash,
            convergence_receipt_hash=_hash("8"),
            full_residual_receipt_hash=_hash("9"),
            boundary_condition_receipt_hash=_hash("a"),
            backend_role="cpu_reference",
            backend_receipt_hash=_hash("b"),
        )
    assert state_error.value.code == "result_state_not_committed_terminal"


def test_numerical_result_manifest_cannot_coherently_promote_engineering_authority() -> None:
    manifest = deepcopy(_result().to_manifest())
    manifest["authority"]["reaction"] = "authoritative"
    manifest["claim_boundary"]["reaction_authority"] = True
    _rehash(manifest, "result_hash")

    with pytest.raises(ResultIRError) as error:
        validate_numerical_result_ir_manifest(manifest)
    assert error.value.code == "numerical_result_schema_invalid"


def test_numerical_result_manifest_rejects_impossible_cross_bindings() -> None:
    epoch = deepcopy(_result().to_manifest())
    epoch["numerical_state"]["epoch"] += 1
    _rehash(epoch, "result_hash")
    with pytest.raises(ResultIRError) as epoch_error:
        validate_numerical_result_ir_manifest(epoch)
    assert epoch_error.value.code == "numerical_result_state_epoch_mismatch"

    value_count = deepcopy(_result().to_manifest())
    value_count["source_terminal"]["free_solution_value_count"] = (
        value_count["numerical_state"]["dof_count"] + 1
    )
    _rehash(value_count, "result_hash")
    with pytest.raises(ResultIRError) as count_error:
        validate_numerical_result_ir_manifest(value_count)
    assert count_error.value.code == "result_source_solution_size_impossible"

    noncanonical_hash = deepcopy(_result().to_manifest())
    noncanonical_hash["bindings"]["state_hash"] += "\n"
    _rehash(noncanonical_hash, "result_hash")
    with pytest.raises(ResultIRError) as hash_error:
        validate_numerical_result_ir_manifest(noncanonical_hash)
    assert hash_error.value.code == "numerical_result_schema_invalid"


def test_diagnostic_ir_is_sanitized_non_authoritative_and_canonical() -> None:
    plan, scaling, reduced, state, _solution_hash = _fixture()
    fallback = create_diagnostic_entry(
        code="backend_fallback_observed",
        path="/backend/fallback",
        severity="warning",
        disposition="fallback",
        evidence_hashes=(_hash("e"),),
    )
    unsupported = create_diagnostic_entry(
        code="member_force_recovery_unavailable",
        path="/result/member_force",
        severity="warning",
        disposition="unsupported",
        evidence_hashes=(_hash("d"),),
    )
    diagnostic = create_diagnostic_ir(
        diagnostic_id="diagnostic.linear.lc1",
        execution_plan=plan,
        state=state,
        equation_scaling=scaling,
        reduced_csr=reduced,
        source_authority_profile="non_authoritative_solver_recurrence",
        source_receipt_schema_version="structural-analysis-cpu-fgmres-run.v1",
        source_receipt_hash=_hash("7"),
        backend_receipt_hash=_hash("b"),
        entries=(unsupported, fallback),
    )
    manifest = diagnostic.to_manifest()
    schema = json.loads(
        (ROOT / "src/structural_analysis/schemas/diagnostic_ir_v1.schema.json")
        .read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert isinstance(diagnostic, DiagnosticIR)
    assert diagnostic.schema_version == DIAGNOSTIC_IR_SCHEMA_VERSION
    assert diagnostic.authority_profile == DIAGNOSTIC_AUTHORITY_PROFILE
    assert diagnostic.status == "partial"
    assert [row["code"] for row in manifest["entries"]] == [
        "backend_fallback_observed",
        "member_force_recovery_unavailable",
    ]
    assert manifest["summary"]["fallback_count"] == 1
    assert manifest["summary"]["unsupported_count"] == 1
    assert set(manifest["authority"].values()) == {"not_authoritative"}
    assert manifest["claim_boundary"]["raw_exception_or_payload_included"] is False
    assert "message" not in json.dumps(manifest)


def test_adapter_bound_diagnostic_replays_source_without_fabricating_plan() -> None:
    plan, scaling, reduced, state, _solution_hash = _fixture()
    entry = create_diagnostic_entry(
        code="actual_backend_observed",
        path="/backend/execution",
        severity="info",
        disposition="observed",
        evidence_hashes=(_hash("d"),),
    )
    snapshot = DiagnosticIRSourceSnapshot(
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        load_pattern_id=plan.load_pattern_id,
        state_hash=state.state_hash,
        state_epoch=state.epoch,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        source_authority_profile="backend_probe",
        source_receipt_schema_version="actual-backend-receipt.v1",
        source_receipt_hash=_hash("e"),
        backend_receipt_hash=_hash("f"),
        entries=(entry,),
    )

    class Adapter:
        def validate_diagnostic_ir_source(self):
            return snapshot

    diagnostic = create_adapter_bound_diagnostic_ir(
        diagnostic_id="diagnostic.adapter.actual",
        source_adapter=Adapter(),
    )
    manifest = diagnostic.to_manifest()
    assert diagnostic._execution_plan is None
    assert manifest["status"] == "observed"
    assert manifest["bindings"]["state_hash"] == state.state_hash
    assert validate_diagnostic_ir_manifest(manifest) == manifest

    with pytest.raises(ResultIRError, match="diagnostic_binding_mismatch"):
        validate_diagnostic_ir(replace(diagnostic, operator_hash=_hash("0")))


def test_diagnostic_manifest_rejects_authority_status_and_raw_shape_tampering() -> None:
    plan, _scaling, _reduced, _state, _solution_hash = _fixture()
    failed = create_diagnostic_entry(
        code="solver_terminal_failed",
        path="/terminal/reason",
        severity="error",
        disposition="failed",
    )
    diagnostic = create_diagnostic_ir(
        diagnostic_id="diagnostic.failed.lc1",
        execution_plan=plan,
        source_authority_profile="validation_gate",
        source_receipt_schema_version="solver-validation-gate.v1",
        source_receipt_hash=_hash("7"),
        entries=(failed,),
    )
    assert diagnostic.status == "blocked"

    authority = deepcopy(diagnostic.to_manifest())
    authority["authority"]["convergence"] = "authoritative"
    _rehash(authority, "diagnostic_hash")
    with pytest.raises(ResultIRError) as authority_error:
        validate_diagnostic_ir_manifest(authority)
    assert authority_error.value.code == "diagnostic_schema_invalid"

    status = deepcopy(diagnostic.to_manifest())
    status["status"] = "observed"
    _rehash(status, "diagnostic_hash")
    with pytest.raises(ResultIRError) as status_error:
        validate_diagnostic_ir_manifest(status)
    assert status_error.value.code == "diagnostic_status_mismatch"

    unknown = deepcopy(diagnostic.to_manifest())
    unknown["entries"][0]["raw_exception"] = "private solver detail"
    _rehash(unknown, "diagnostic_hash")
    with pytest.raises(ResultIRError) as unknown_error:
        validate_diagnostic_ir_manifest(unknown)
    assert unknown_error.value.code == "diagnostic_schema_invalid"

    raw_extension = deepcopy(diagnostic.to_manifest())
    raw_extension["extensions"]["private:raw_exception"] = "solver stack trace"
    _rehash(raw_extension, "diagnostic_hash")
    with pytest.raises(ResultIRError) as extension_error:
        validate_diagnostic_ir_manifest(raw_extension)
    assert extension_error.value.code == "diagnostic_schema_invalid"

    control_path = deepcopy(diagnostic.to_manifest())
    control_path["entries"][0]["path"] = "/solver\nprivate"
    _rehash(control_path, "diagnostic_hash")
    with pytest.raises(ResultIRError) as path_error:
        validate_diagnostic_ir_manifest(control_path)
    assert path_error.value.code == "diagnostic_schema_invalid"


def test_diagnostic_entry_rejects_unstable_or_inconsistent_public_metadata() -> None:
    with pytest.raises(ResultIRError) as code_error:
        create_diagnostic_entry(
            code="Raw Exception",
            path="/solver",
            severity="warning",
            disposition="partial",
        )
    assert code_error.value.code == "diagnostic_code_invalid"

    with pytest.raises(ResultIRError) as path_error:
        create_diagnostic_entry(
            code="solver_partial",
            path="solver\nprivate",
            severity="warning",
            disposition="partial",
        )
    assert path_error.value.code == "diagnostic_path_invalid"

    plan = _base_plan()
    entry = create_diagnostic_entry(
        code="solver_partial",
        path="/solver",
        severity="warning",
        disposition="partial",
    )
    with pytest.raises(ResultIRError) as extension_error:
        create_diagnostic_ir(
            diagnostic_id="diagnostic.extensions.invalid",
            execution_plan=plan,
            source_authority_profile="validation_gate",
            source_receipt_schema_version="solver-validation-gate.v1",
            source_receipt_hash=_hash("7"),
            entries=(entry,),
            extensions={"private:raw_exception": "solver stack trace"},
        )
    assert extension_error.value.code == "diagnostic_extensions_not_supported"

    with pytest.raises(ResultIRError) as severity_error:
        create_diagnostic_entry(
            code="solver_failed",
            path="/solver",
            severity="warning",
            disposition="failed",
        )
    assert severity_error.value.code == "diagnostic_failed_severity_invalid"
