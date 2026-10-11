"""Synthetic beam integration; no specimen calibration or general frame claim."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile, _reaction_rows
from structural_analysis.api.rc_fiber_frame_direct_control import (
    analyze_bounded_rc_fiber_direct_control,
    validate_bounded_rc_fiber_direct_control_artifacts,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def beam():
    data = json.loads(
        (
            Path(__file__).parents[1] / "examples/public_rc_fiber_frame_cantilever.json"
        ).read_text()
    )
    stations = (0.0, 0.2, 0.7, 0.95, 1.2, 1.7, 1.9)
    data["nodes"] = [
        {"id": f"N{i + 1}", "coordinates": [x, 0.0, 0.0]}
        for i, x in enumerate(stations)
    ]
    data["elements"] = [
        dict(data["elements"][0], id=f"M{i + 1}", nodes=[f"N{i + 1}", f"N{i + 2}"])
        for i in range(6)
    ]
    data["supports"] = [
        {"node": "N2", "dofs": ["UX", "UY"]},
        {"node": "N6", "dofs": ["UY"]},
    ]
    data["loads"] = [
        dict(deepcopy(data["loads"][0]), node=node) for node in ("N3", "N5")
    ]
    return data


def model(data=None):
    return load_neutral_json_bytes(
        json.dumps(beam() if data is None else data).encode()
    )


def request(targets=(-1e-6,)):
    return BoundedRCFiberDirectControlRequest(
        10, tuple(targets), experimental_pin_roller_beam=True
    )


def test_explicit_profile_transport_and_legacy_rejection():
    value = request()
    assert value.to_dict()["schema_version"].endswith(".v4")
    assert decode_bounded_rc_fiber_direct_control_request(value.to_dict()) == value
    assert (
        analyze_bounded_rc_fiber_direct_control(
            model(), (-1e-6,), control_global_dof=10
        ).to_dict()["status"]
        == "unsupported"
    )
    for bad in (False, 1, "true", None):
        payload = value.to_dict() | {"experimental_pin_roller_beam": bad}
        with pytest.raises(ValueError):
            decode_bounded_rc_fiber_direct_control_request(payload)
    payload = value.to_dict()
    del payload["experimental_pin_roller_beam"]
    with pytest.raises(ValueError):
        decode_bounded_rc_fiber_direct_control_request(payload)
    payload = value.to_dict() | {
        "schema_version": "bounded-rc-fiber-direct-control-request.v1"
    }
    with pytest.raises(ValueError):
        decode_bounded_rc_fiber_direct_control_request(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "two_pins",
        "two_rollers",
        "rotation",
        "duplicate",
        "inclined",
        "folded",
        "load_on_support",
    ],
)
def test_invalid_beam_boundaries_fail_before_solve(mutation):
    data = beam()
    if mutation == "two_pins":
        data["supports"][1]["dofs"] = ["UX", "UY"]
    elif mutation == "two_rollers":
        data["supports"][0]["dofs"] = ["UY"]
    elif mutation == "rotation":
        data["supports"][0]["dofs"] = ["UX", "UY", "RZ"]
    elif mutation == "duplicate":
        data["supports"][1]["node"] = "N2"
    elif mutation == "inclined":
        data["nodes"][3]["coordinates"][1] = 0.1
    elif mutation == "folded":
        data["nodes"][2]["coordinates"][0] = 1.1
    else:
        data["loads"][0]["node"] = "N2"
    compiled, blockers, _ = _compile(
        model(data).detached_analysis_snapshot(), experimental_pin_roller_beam=True
    )
    assert compiled is None and blockers


def test_only_restrained_components_project_to_support_reactions():
    import numpy as np

    compiled, blockers, _ = _compile(
        model().detached_analysis_snapshot(), experimental_pin_roller_beam=True
    )
    assert not blockers
    assert compiled.problem.fixed_global_dofs == (3, 4, 16)
    rows = _reaction_rows(compiled, np.ones(42))
    assert [(row["node_id"], row["dof"]) for row in rows] == [
        ("N2", "UX"),
        ("N2", "UY"),
        ("N6", "UY"),
    ]


def test_pin_roller_split_restart_and_fresh_source_validation():
    original = model()
    first_request = request()
    first = analyze_bounded_rc_fiber_direct_control(
        original, first_request.targets_m, **first_request.api_kwargs()
    )
    assert first.to_dict()["contract_pass"]
    suffix_request = request((-2e-6,))
    resumed = analyze_bounded_rc_fiber_direct_control(
        original,
        suffix_request.targets_m,
        restart=first.checkpoint_artifact_bytes(),
        **suffix_request.api_kwargs(),
    )
    whole_request = request((-1e-6, -2e-6))
    whole = analyze_bounded_rc_fiber_direct_control(
        original, whole_request.targets_m, **whole_request.api_kwargs()
    )
    assert resumed.to_dict()["contract_pass"] and whole.to_dict()["contract_pass"]
    assert resumed.checkpoint_artifact_bytes() == whole.checkpoint_artifact_bytes()
    checked = validate_bounded_rc_fiber_direct_control_artifacts(
        original,
        whole_request.targets_m,
        result=whole.result_artifact_bytes(),
        checkpoint=whole.checkpoint_artifact_bytes(),
        **whole_request.api_kwargs(),
    )
    assert checked.to_dict()["artifact_contract_pass"]
    wrong = whole_request.api_kwargs() | {"experimental_pin_roller_beam": False}
    rejected = validate_bounded_rc_fiber_direct_control_artifacts(
        original,
        whole_request.targets_m,
        result=whole.result_artifact_bytes(),
        checkpoint=whole.checkpoint_artifact_bytes(),
        **wrong,
    )
    assert not rejected.to_dict()["artifact_contract_pass"]


def test_pin_roller_durable_resume_and_quantity_report(tmp_path):
    from structural_analysis.execution.job_service import DurableJobService
    from structural_analysis.execution.rc_fiber_direct_control_worker import (
        execute_rc_fiber_direct_control_claim,
    )
    from structural_analysis.execution.rc_fiber_job_contract import (
        validate_rc_fiber_job_request,
    )

    tenant = {
        "tenant_id": "a",
        "authorization_token": "synthetic-tenant-token-0123456789",
    }
    worker = {
        "worker_id": "w",
        "authorization_token": "synthetic-worker-token-0123456789",
    }

    def service():
        return DurableJobService(
            tmp_path / "store",
            tenant_tokens={"a": tenant["authorization_token"]},
            worker_tokens={"w": worker["authorization_token"]},
        )

    original = {
        "schema_version": "structural-analysis-job-request.v4",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "pin-roller-software-test",
        "model": beam(),
        "config": request((-1e-6, -2e-6)).to_dict(),
        "source_revision": "a" * 40,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 8},
    }
    for altered in (
        original | {"schema_version": "structural-analysis-job-request.v3"},
        original
        | {"config": BoundedRCFiberDirectControlRequest(10, (-1e-6,)).to_dict()},
    ):
        with pytest.raises(ValueError, match="schema and support profile"):
            validate_rc_fiber_job_request(altered)
    current = service()
    job = current.submit_job(**tenant, idempotency_key="pin-roller", request=original)
    first = execute_rc_fiber_direct_control_claim(
        current, current.claim_next(**worker), **worker
    )
    assert first.status == "checkpointed" and first.progress_completed == 1
    current = service()
    final = execute_rc_fiber_direct_control_claim(
        current, current.claim_next(**worker), **worker
    )
    assert final.status == "succeeded"
    result = json.loads(current.read_result(job.job_id, **tenant))
    assert result["execution_budget"]["reserved_attempts"] == 4
    report = current.create_rc_quantity_report(
        job.job_id,
        **tenant,
        expected_request_hash=final.request.content_hash,
        expected_result_artifact_hash=final.result.content_hash,
        declared_prices=None,
    )
    retained = json.loads(
        service().read_rc_quantity_report(job.job_id, report["report_id"], **tenant)
    )
    assert len(retained["quantities"]["members"]) == 6
    assert retained["quantities"]["totals"][
        "gross_concrete_volume_m3"
    ] == pytest.approx(0.4 * 0.6 * 1.9)
    assert current.validate_integrity(job.job_id, **tenant)["contract_pass"]
