"""Pure transport tests; synthetic receipts never establish physical evidence.

The native decoder is replaced only in the synthetic multi-chunk fixture. Its
physics-rich states are tested by the existing native checkpoint tests and the
worker integration slice. No solver or numerical artifact verifier runs here.
"""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution import rc_fiber_job_contract as contract


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def forbid_numerical_execution(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Pure durable contract test attempted numerical execution")

    monkeypatch.setattr(api, "analyze_bounded_rc_fiber_direct_control", forbidden)
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", forbidden
    )
    monkeypatch.setattr(api, "run_stateful_fiber_frame2d_control_path", forbidden)
    from structural_analysis.assembly import stateful_fiber_frame2d_control_path as path
    from structural_analysis.solvers.nonlinear import newton

    monkeypatch.setattr(path, "_execute_raw", forbidden)
    monkeypatch.setattr(newton, "newton_raphson_vector", forbidden)


def _request():
    typed = BoundedRCFiberDirectControlRequest(
        control_global_dof=7, targets_m=(-1e-6, -2e-6, -3e-6, -4e-6, -5e-6)
    )
    return {
        "schema_version": contract.RC_FIBER_JOB_REQUEST_SCHEMA_VERSION,
        "operation": contract.RC_FIBER_JOB_OPERATION,
        "case_id": "pure-rc-contract",
        "model": json.loads(
            (
                ROOT / "examples/public_rc_fiber_frame_l_frame_material_history.json"
            ).read_bytes()
        ),
        "config": typed.to_dict(),
        "source_revision": "e" * 40,
        "result_contract": contract.RC_FIBER_JOB_RESULT_SCHEMA_VERSION,
        "execution_config": {"chunk_target_count": 2, "maximum_api_invocations": 10},
    }


def _budget(reserved):
    return {
        "maximum_attempts": 10,
        "reserved_attempts": reserved,
        "remaining_attempts": 10 - reserved,
    }


def _rehash(value, key):
    value[key] = contract._hash(
        {name: item for name, item in value.items() if name != key}
    )


def _rebind_result(value):
    api_value = value["api_result"]
    _rehash(api_value["path"], "path_hash")
    _rehash(api_value, "result_hash")
    tail = value["receipts"][-1]
    tail["path_hash"] = api_value["path"]["path_hash"]
    tail["result_hash"] = api_value["result_hash"]
    tail["result_artifact_sha256"] = contract._hash(api_value)
    tail["validation_report"]["verified_result_hash"] = api_value["result_hash"]
    _rehash(tail, "receipt_hash")
    _rehash(value, "result_hash")


def test_request_compiles_supported_model_without_solving_and_detaches():
    request = _request()
    model, typed = contract.validate_rc_fiber_job_request(request)
    assert typed.to_dict() == request["config"]
    assert model.source_path == "<durable-rc-model>"
    assert model.input_checksum == contract._hash(request["model"])
    request["model"]["nodes"][0]["coordinates"][0] = 123.0
    assert model.nodes[0]["coordinates"][0] == 0.0


def test_constant_load_request_cannot_enter_proportional_only_durable_receipts():
    request = _request()
    request["config"] = BoundedRCFiberDirectControlRequest(
        control_global_dof=7,
        targets_m=(-1e-6,),
        constant_nodal_loads=(("N3", 0.0, -600.0, 0.0),),
    ).to_dict()
    with pytest.raises(ValueError, match="preload-aware durable receipts"):
        contract.validate_rc_fiber_job_request(request)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(restart="AA=="),
        lambda r: r.update(schema_version="structural-analysis-job-request.v2"),
        lambda r: r.update(source_revision="main"),
        lambda r: r["config"].pop("allow_reversals"),
        lambda r: r["config"]["solver_config"]["newton"].pop("terminal_polishing"),
        lambda r: r["config"].update(targets_m=[]),
        lambda r: r["config"].update(targets_m=[0.0]),
        lambda r: r["config"].update(targets_m=[-1e-6, 1e-6]),
        lambda r: r["config"].update(control_global_dof=0),
        lambda r: r["config"].update(control_global_dof=8),
        lambda r: r["model"].update(
            unsupported_features=[{"code": "unsupported-test"}]
        ),
        lambda r: r["execution_config"].update(chunk_target_count=True),
        lambda r: r["execution_config"].update(chunk_target_count=0),
        lambda r: r["execution_config"].update(chunk_target_count=256),
        lambda r: r["execution_config"].update(maximum_api_invocations=1),
        lambda r: r["execution_config"].update(maximum_api_invocations=4097),
    ],
)
def test_request_rejects_incomplete_unsupported_or_changed_profile(mutate):
    request = _request()
    mutate(request)
    with pytest.raises(ValueError):
        contract.validate_rc_fiber_job_request(request)


def test_reversal_budget_includes_first_leg_from_genesis():
    request = _request()
    request["config"].update(
        targets_m=[-1e-6, 1e-6], allow_reversals=True, maximum_reversals=1
    )
    _, typed = contract.validate_rc_fiber_job_request(request)
    assert typed.targets_m == (-1e-6, 1e-6)


def test_request_schema_requires_full_configuration_and_rejects_initial_restart():
    schema = json.loads(
        (
            ROOT / "src/structural_analysis/schemas/job_request_v3.schema.json"
        ).read_bytes()
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    request = _request()
    validator.validate(request)
    for changed in (request | {"restart": None}, request | {"config": {}}):
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(changed)


@pytest.mark.parametrize(
    "value", [{1: "coerced"}, {"a": (1, 2)}, {"a": float("nan")}, {"a": object()}]
)
def test_canonical_transport_rejects_non_json_values(value):
    with pytest.raises(ValueError):
        contract.rc_fiber_job_canonical_bytes(value)


@pytest.fixture
def synthetic_chunks(monkeypatch):
    request = _request()
    config, compiled, scope, model, control = contract._context(request)
    genesis = contract.initial_stateful_fiber_frame2d_checkpoint(compiled.problem)
    bindings, states = [], [genesis.to_dict()]
    for index, target in enumerate(config.targets_m, 1):
        state_hash = contract._hash({"synthetic_state": index})
        bindings.append(
            {
                "target_control_displacement_m": target,
                "step_hash": contract._hash({"synthetic_step": index}),
                "parent_checkpoint_hash": states[-1]["state_hash"],
                "accepted_checkpoint_hash": state_hash,
                "direction": -1,
                "reversal_count": 0,
            }
        )
        states.append({"state_hash": state_hash, "epoch": index, "step_index": index})

    def decode_synthetic(raw, problem, expected_scope):
        value = contract._mapping(raw)
        contract._self_hash(value, "artifact_hash")
        assert problem is not None
        if not contract._same(value["scope"], expected_scope):
            raise ValueError("synthetic native scope mismatch")
        terminal = value["terminal_checkpoint"]
        return (
            value,
            tuple(value["accepted_targets_m"]),
            SimpleNamespace(
                state_hash=terminal["state_hash"], to_dict=lambda: deepcopy(terminal)
            ),
        )

    monkeypatch.setattr(contract, "_decode_restart", decode_synthetic)

    def work(count):
        return {
            "attempted_step_count": count,
            "known_linear_solve_count": count,
            "known_newton_iteration_count": count,
            "unknown_solver_work_attempt_count": 0,
        }

    def one(before, after, restart):
        checkpoint = {
            "scope": scope,
            "accepted_targets_m": list(config.targets_m[:after]),
            "accepted_step_bindings": deepcopy(bindings[:after]),
            "terminal_checkpoint": states[after],
        }
        _rehash(checkpoint, "artifact_hash")
        cp_raw = contract.rc_fiber_job_canonical_bytes(checkpoint)
        restart_hash = None if restart is None else contract._sha(restart)
        chunk = replace(config, targets_m=config.targets_m[before:after])
        path = {
            "schema_version": contract.CONTROL_PATH_SCHEMA,
            "status": "ready",
            "scope": scope,
            "targets_m": list(chunk.targets_m),
            "accepted_target_prefix_m": list(config.targets_m[:after]),
            "unattempted_targets_m": [],
            "requested_directions": [-1] * after,
            "requested_reversal_count": 0,
            "accepted_direction": -1,
            "accepted_reversal_count": 0,
            "initial_checkpoint": states[before],
            "final_checkpoint": states[after],
            "restart_input_sha256": restart_hash,
            "restart_artifact_hash": checkpoint["artifact_hash"],
            "claims": contract._PATH_CLAIMS,
            "attempts": [{}] * (after - before),
            "replay_attempts": [{}] * before,
            "metrics": {
                "requested_target_count": after - before,
                "attempted_target_count": after - before,
                "accepted_target_count": after - before,
                "failed_target_count": 0,
                "unattempted_target_count": 0,
                "cumulative_accepted_target_count": after,
                "prefix_replayed_step_count": before,
                "hidden_retries_or_cutbacks": 0,
                "restart_verification_scope": "full_genesis_prefix_solver_replay"
                if before
                else "not_requested",
                "prefix_replay_work": work(before),
                "suffix_work": work(after - before),
                "total_work": work(after),
            },
        }
        _rehash(path, "path_hash")
        history = [
            {
                "epoch": index,
                "step_index": index,
                "parent_checkpoint_hash": binding["parent_checkpoint_hash"],
                "checkpoint_hash": binding["accepted_checkpoint_hash"],
                "source_step_hash": binding["step_hash"],
                "recovery_scope": "exact_previous_parent_original_newton_coordinates_constitutive_transition",
            }
            for index, binding in enumerate(bindings[:after], 1)
        ]
        result = {
            "schema_version": api.BOUNDED_RC_FIBER_DIRECT_CONTROL_SCHEMA_VERSION,
            "status": "ready",
            "contract_pass": True,
            "model": model,
            "request": contract._api_request(chunk, restart_hash),
            "control": control,
            "path": path,
            "response_history": history,
            "terminal_response": history[-1],
            "checkpoint": {"sha256": contract._sha(cp_raw), "byte_length": len(cp_raw)},
            "unsupported_features": [],
            "warnings": [],
            "failure": None,
            "claims": contract._API_CLAIMS,
            "metrics": {
                "control_work": work(after),
                "response_reassembly_attempts": after,
                "response_reassembly_verified_count": after,
                "current_epoch": None,
                "response_history_scope": "cumulative_accepted_prefix",
                "whole_accepted_history_recovered": True,
                "explicit_validation_solver_replay_performed": False,
            },
        }
        _rehash(result, "result_hash")
        report = {
            "schema_version": "bounded-rc-fiber-direct-control-validation.v1",
            "status": "valid_artifact",
            "artifact_contract_pass": True,
            "contract_pass": True,
            "physical_path_complete": True,
            "fresh_source_execution_invoked": True,
            "solver_replay_performed": True,
            "unavailable_execution_work": False,
            "replay_control_work": work(after),
            "response_reassembly_attempts": after,
            "response_reassembly_verified_count": after,
            "verified_result_hash": result["result_hash"],
            "errors": [],
            "claims": contract._API_CLAIMS,
            "verification_scope": "fresh_complete_request_solver_and_original_transition_replay",
        }
        typed_result = api.BoundedRCFiberDirectControlResult(
            contract.rc_fiber_job_canonical_bytes(result), cp_raw
        )
        return typed_result, report, cp_raw

    receipts, checkpoints, results = [], [], []
    restart = None
    # Gaps are abandoned/retried invocations, not fabricated completed solver work.
    for before, after, ordinals in ((0, 2, (1, 2)), (2, 4, (5, 6)), (4, 5, (8, 9))):
        result, report, cp_raw = one(before, after, restart)
        receipt = contract.build_rc_fiber_job_receipt(
            request,
            completed_before=before,
            result=result,
            verification_report=report,
            restart_checkpoint=restart,
            analysis_ordinal=ordinals[0],
            verification_ordinal=ordinals[1],
            analysis_timing={"wall_ns": 10, "process_cpu_ns": 9},
            verification_timing={"wall_ns": 12, "process_cpu_ns": 11},
        )
        receipts.append(receipt)
        results.append(result)
        complete = after == len(config.targets_m)
        checkpoints.append(
            contract.build_rc_fiber_job_payload(
                request,
                receipts=deepcopy(receipts),
                execution_budget=_budget(ordinals[1]),
                terminal_checkpoint=cp_raw,
                complete=complete,
                api_result=result if complete else None,
            )
        )
        restart = cp_raw
    return request, checkpoints, results


def test_fixed_chunks_short_final_prefix_and_explicit_api_units(synthetic_chunks):
    request, (first, second, result), _ = synthetic_chunks
    assert [r["completed_after"] for r in result["receipts"]] == [2, 4, 5]
    assert "api_result" not in first and "api_result" not in second
    assert all("api_result" not in receipt for receipt in result["receipts"])
    assert len(result["api_result"]["response_history"]) == 5
    assert result["execution_budget_unit"] == "reserved_api_invocations"
    assert result["authority"]["service_numerical_verification_performed"] is False
    contract.validate_rc_fiber_job_checkpoint(
        second,
        request=request,
        progress_completed=4,
        execution_budget=_budget(9),
        checkpoint=first,
    )
    validation = contract.validate_rc_fiber_job_result(
        result, request=request, execution_budget=_budget(9), checkpoint=second
    )
    assert validation["contract_pass"] is True
    assert validation["receipt_hashes"] == [
        r["receipt_hash"] for r in result["receipts"]
    ]


def test_prior_receipt_prefix_is_exact_even_when_final_chunk_short(synthetic_chunks):
    request, (_, checkpoint, result), _ = synthetic_chunks
    changed = deepcopy(result)
    changed["receipts"][0]["analysis_timing"]["wall_ns"] += 1
    _rehash(changed["receipts"][0], "receipt_hash")
    _rehash(changed, "result_hash")
    with pytest.raises(ValueError, match="receipt prefix"):
        contract.validate_rc_fiber_job_result(
            changed, request=request, execution_budget=_budget(9), checkpoint=checkpoint
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("contract_pass", False),
        ("artifact_contract_pass", False),
        ("physical_path_complete", False),
        ("fresh_source_execution_invoked", False),
        ("solver_replay_performed", False),
        ("unavailable_execution_work", True),
        ("verified_result_hash", "sha256:" + "0" * 64),
        ("errors", ["source mismatch"]),
        ("status", "invalid_artifact"),
    ],
)
def test_rehashed_receipt_cannot_promote_failed_or_detached_report(
    synthetic_chunks, key, value
):
    request, (_, _, result), _ = synthetic_chunks
    changed = deepcopy(result)
    changed["receipts"][0]["validation_report"][key] = value
    _rehash(changed["receipts"][0], "receipt_hash")
    _rehash(changed, "result_hash")
    with pytest.raises(ValueError, match="attestation"):
        contract.validate_rc_fiber_job_result(
            changed, request=request, execution_budget=_budget(9)
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("analysis_ordinal", True),
        ("analysis_ordinal", 2),
        ("verification_ordinal", 1),
        ("verification_ordinal", 11),
        ("completed_after", 3),
        ("restart_input_sha256", "sha256:" + "f" * 64),
    ],
)
def test_rehashed_receipt_rejects_bad_reservations_or_chunk_identity(
    synthetic_chunks, key, value
):
    request, (_, _, result), _ = synthetic_chunks
    changed = deepcopy(result)
    changed["receipts"][0][key] = value
    _rehash(changed["receipts"][0], "receipt_hash")
    _rehash(changed, "result_hash")
    with pytest.raises(ValueError):
        contract.validate_rc_fiber_job_result(
            changed, request=request, execution_budget=_budget(9)
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["api_result"]["response_history"].reverse(),
        lambda r: r["api_result"]["response_history"].pop(0),
        lambda r: r["api_result"]["path"]["accepted_target_prefix_m"].reverse(),
        lambda r: r["api_result"]["request"].update(targets_m=[-4e-6]),
        lambda r: r["api_result"]["model"].update(input_checksum="sha256:" + "0" * 64),
        lambda r: r["api_result"]["control"].update(global_dof=6),
        lambda r: r["api_result"]["claims"].update(design_authority=True),
        lambda r: r["api_result"]["path"]["initial_checkpoint"].update(epoch=0),
        lambda r: r["api_result"]["path"].update(metrics=[]),
    ],
)
def test_fully_rehashed_final_artifact_rejects_changed_source_or_history(
    synthetic_chunks, mutate
):
    request, (_, _, result), _ = synthetic_chunks
    changed = deepcopy(result)
    mutate(changed)
    _rebind_result(changed)
    with pytest.raises(ValueError):
        contract.validate_rc_fiber_job_result(
            changed, request=request, execution_budget=_budget(9)
        )


def test_current_budget_checkpoint_progress_and_terminal_artifact_are_bound(
    synthetic_chunks,
):
    request, (first, _, result), _ = synthetic_chunks
    with pytest.raises(ValueError, match="reservation budget"):
        contract.validate_rc_fiber_job_result(
            result, request=request, execution_budget=_budget(10)
        )
    with pytest.raises(ValueError, match="cursor"):
        contract.validate_rc_fiber_job_checkpoint(
            first, request=request, progress_completed=1, execution_budget=_budget(2)
        )
    changed = deepcopy(result)
    changed["terminal_checkpoint_artifact_base64"] = first[
        "terminal_checkpoint_artifact_base64"
    ]
    _rehash(changed, "result_hash")
    with pytest.raises(ValueError, match="target prefix"):
        contract.validate_rc_fiber_job_result(
            changed, request=request, execution_budget=_budget(9)
        )


def test_replay_work_and_checkpoint_budget_cannot_be_relabelled(synthetic_chunks):
    request, (first, second, result), _ = synthetic_chunks
    changed = deepcopy(result)
    receipt = changed["receipts"][0]
    receipt["validation_report"]["replay_control_work"]["known_linear_solve_count"] += 1
    receipt["verification_metrics"] = contract._verification_metrics(
        receipt["validation_report"]
    )
    _rehash(receipt, "receipt_hash")
    _rehash(changed, "result_hash")
    with pytest.raises(ValueError, match="replay work"):
        contract.validate_rc_fiber_job_result(
            changed, request=request, execution_budget=_budget(9)
        )
    prior = deepcopy(first)
    prior["execution_budget"] = _budget(8)
    _rehash(prior, "checkpoint_hash")
    with pytest.raises(ValueError, match="receipt prefix"):
        contract.validate_rc_fiber_job_checkpoint(
            second, request=request, execution_budget=_budget(9), checkpoint=prior
        )


def test_byte_bounds_before_decoding_and_no_duplicate_cumulative_payload(
    synthetic_chunks, monkeypatch
):
    request, (first, _, result), _ = synthetic_chunks
    with pytest.raises(ValueError):
        contract._mapping(contract.rc_fiber_job_canonical_bytes(result), maximum=100)
    monkeypatch.setattr(contract, "CONTROL_RESTART_MAX_BYTES", 1)
    with pytest.raises(ValueError, match="byte bound"):
        contract._decode_artifact(first["terminal_checkpoint_artifact_base64"])
    changed = deepcopy(result)
    changed["receipts"][0]["api_result"] = result["api_result"]
    _rehash(changed["receipts"][0], "receipt_hash")
    _rehash(changed, "result_hash")
    # Check receipt shape directly: the deliberately tiny native cap above
    # must not obscure the separate prohibition on cumulative receipt payloads.
    config, _, _, model, control = contract._context(request)
    with pytest.raises(ValueError, match="receipt fields"):
        contract._validate_receipt(
            changed["receipts"][0], request, config, model, control, 0, None, 0, 9
        )


def test_real_native_decoder_rejects_unbound_artifact_without_solving():
    request = _request()
    config, compiled, scope, _, _ = contract._context(request)
    with pytest.raises(ValueError):
        contract._native(b"{}", compiled, scope, config.targets_m[:2])
