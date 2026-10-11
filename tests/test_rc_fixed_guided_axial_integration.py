"""Synthetic public transport/lifecycle coverage, not a calibrated specimen."""

from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator
from pathlib import Path

from structural_analysis.api.rc_fiber_frame_direct_control import (
    analyze_bounded_rc_fiber_direct_control,
    validate_bounded_rc_fiber_direct_control_artifacts,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.execution.rc_fiber_job_contract import (
    validate_rc_fiber_job_request,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from tests.test_rc_fixed_guided_axial_compiler import fixture


def config(targets=(-1e-6, -2e-6), axis=1):
    return BoundedRCFiberDirectControlRequest(
        3 + axis,
        tuple(targets),
        experimental_fixed_guided_axial=True,
        solver_config=StatefulFiberFrame2DDisplacementControlConfig(
            initial_guess="control_target"
        ),
    )


def request():
    return {
        "schema_version": "structural-analysis-job-request.v5",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "synthetic-fixed-guided-axial",
        "model": fixture(axis=1),
        "config": config().to_dict(),
        "source_revision": "a" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 8},
    }


def test_profile_schema_identity_and_strict_opt_in():
    value = config()
    assert decode_bounded_rc_fiber_direct_control_request(value.to_dict()) == value
    assert (
        value.to_dict()["schema_version"]
        == "bounded-rc-fiber-direct-control-request.v5"
    )
    legacy = BoundedRCFiberDirectControlRequest(
        4, value.targets_m, solver_config=value.solver_config
    )
    assert value.request_hash != legacy.request_hash
    assert value.resume_contract_hash != legacy.resume_contract_hash
    for bad in (False, 1, "true", None):
        with pytest.raises(ValueError):
            decode_bounded_rc_fiber_direct_control_request(
                value.to_dict() | {"experimental_fixed_guided_axial": bad}
            )
    for mutation in ("missing_flag", "legacy_version", "pin_version", "second_profile"):
        payload = value.to_dict()
        if mutation == "missing_flag":
            del payload["experimental_fixed_guided_axial"]
        elif mutation == "legacy_version":
            payload["schema_version"] = "bounded-rc-fiber-direct-control-request.v1"
        elif mutation == "pin_version":
            payload["schema_version"] = "bounded-rc-fiber-direct-control-request.v4"
        else:
            payload["experimental_pin_roller_beam"] = True
        with pytest.raises(ValueError):
            decode_bounded_rc_fiber_direct_control_request(payload)
    original = request()
    schema = json.loads(
        (
            Path(__file__).parents[1]
            / "src/structural_analysis/schemas/job_request_v5.schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(original)
    validate_rc_fiber_job_request(original)
    for version in ("v3", "v4"):
        with pytest.raises(ValueError, match="schema and support profile"):
            validate_rc_fiber_job_request(
                original
                | {"schema_version": f"structural-analysis-job-request.{version}"}
            )
    for key in ("experimental_fixed_guided_axial",):
        changed = deepcopy(original)
        changed["config"][key] = False
        assert list(Draft202012Validator(schema).iter_errors(changed))


@pytest.mark.parametrize("axis", [0, 1])
def test_public_control_split_restart_and_fresh_verification(axis):
    model = load_neutral_json_bytes(json.dumps(fixture(axis=axis)).encode())
    first_request = config((-1e-6,), axis)
    first = analyze_bounded_rc_fiber_direct_control(
        model, first_request.targets_m, **first_request.api_kwargs()
    )
    assert first.contract_pass
    suffix = config((-2e-6,), axis)
    restarted = analyze_bounded_rc_fiber_direct_control(
        model,
        suffix.targets_m,
        restart=first.checkpoint_artifact_bytes(),
        **suffix.api_kwargs(),
    )
    whole_request = config(axis=axis)
    whole = analyze_bounded_rc_fiber_direct_control(
        model, whole_request.targets_m, **whole_request.api_kwargs()
    )
    assert restarted.contract_pass and whole.contract_pass
    assert restarted.checkpoint_artifact_bytes() == whole.checkpoint_artifact_bytes()
    payload = whole.to_dict()
    assert "fixed_guided" in payload["model"]["compiler_profile"]
    assert len(payload["terminal_response"]["support_reactions"]) == 5
    report = validate_bounded_rc_fiber_direct_control_artifacts(
        model,
        whole_request.targets_m,
        result=whole.result_artifact_bytes(),
        checkpoint=whole.checkpoint_artifact_bytes(),
        **whole_request.api_kwargs(),
    )
    assert report.contract_pass
    wrong = whole_request.api_kwargs() | {"experimental_fixed_guided_axial": False}
    report = validate_bounded_rc_fiber_direct_control_artifacts(
        model,
        whole_request.targets_m,
        result=whole.result_artifact_bytes(),
        checkpoint=whole.checkpoint_artifact_bytes(),
        **wrong,
    )
    assert not report.contract_pass
    assert not report.to_dict()["fresh_source_execution_invoked"]


def test_process_death_restore_reopen_report_budget_and_corruption(
    tmp_path, monkeypatch
):
    from tests import test_rc_real_process_lifecycle as lifecycle

    monkeypatch.setattr(lifecycle, "request", request)
    summary = lifecycle.run_lifecycle(tmp_path / "store")
    assert summary["completed_targets"] == 2
    assert summary["reserved_api_invocations"] == 5
    assert summary["price_only_numerical_state_unchanged"]
    assert not summary["independent_physical_validation"]
