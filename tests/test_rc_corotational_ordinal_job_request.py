"""Complete-source admission, explicit load roles, and pure snapshot isolation."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    RC_ORDINAL_JOB_OPERATION,
    RC_ORDINAL_JOB_REQUEST_SCHEMA_VERSION,
    RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION,
    validate_rc_corotational_ordinal_job_request,
)


def ordinal_request(rows=None):
    if rows is None:
        rows = [(-1e-6, 0.01), (-1e-6, 0.01), (-1e-6, 0.02), (-0.5e-6, 0.02)]
    model = json.loads(
        (
            Path(__file__).parents[1]
            / "examples/public_rc_fiber_frame_l_frame_material_history.json"
        ).read_bytes()
    )
    source = [
        dict(
            ordinal=i,
            source_row=i + 2,
            source_row_sha256="sha256:" + hashlib.sha256(str(i).encode()).hexdigest(),
            target_m=g,
            axial_load_kn=p,
        )
        for i, (g, p) in enumerate(rows)
    ]
    return json.loads(
        json.dumps(
            {
                "schema_version": RC_ORDINAL_JOB_REQUEST_SCHEMA_VERSION,
                "operation": RC_ORDINAL_JOB_OPERATION,
                "case_id": "authored-ordinal-software-test",
                "source_revision": "b" * 40,
                "result_contract": RC_ORDINAL_JOB_RESULT_SCHEMA_VERSION,
                "model": model,
                "history_plan": {
                    "schema": "source-ordinal-history-plan.v1",
                    "source_id": "authored-software-fixture",
                    "source_sha256": "sha256:" + "a" * 64,
                    "mapping_hash": "sha256:" + "c" * 64,
                    "rows": source,
                },
                "observed_force_reference": {
                    "schema_version": "ordinal-observed-force-reference.v1",
                    "unit": "kN",
                    "rows": [
                        dict(
                            ordinal=r["ordinal"],
                            source_row_sha256=r["source_row_sha256"],
                            observed_force_kn=float(r["ordinal"]),
                        )
                        for r in source
                    ],
                },
                "config": {
                    "maximum_solver_attempts": 100,
                    "maximum_subdivision_depth": 4,
                    "solver_config": asdict(
                        StatefulCorotationalFiberFrame2DDisplacementControlConfig()
                    ),
                    "fixed_nodal_loads": [],
                    "control_observation": {
                        "schema_version": "linear-physical-displacement-observation.v1",
                        "terms": [
                            {"node_id": "N3", "component": "UY", "coefficient": 1.0}
                        ],
                    },
                    "axial_load_pattern": [
                        {"node_id": "N3", "component": "FX", "coefficient": -1.0}
                    ],
                    "independent_axial_load_role": "source_total_dead_global",
                    "initialization": "authored_virgin_zero_reference",
                    "experimental_pin_roller_beam": False,
                    "experimental_fixed_guided_axial": False,
                },
                "execution_config": {
                    "maximum_api_invocations": 20,
                    "production_solver_budget": 100,
                    "verification_solver_budget": 100,
                    "attempt_limit_per_call": 2,
                    "record_limit_per_call": 3,
                    "phase_execution_policy": {
                        "schema_version": "bounded-rc-corotational-phase-execution-policy.v1",
                        "analysis_timeout_ms": 30000,
                        "verification_timeout_ms": 30000,
                        "termination_grace_ms": 500,
                    },
                },
            }
        )
    )


def test_admission_preserves_holds_changing_p_all_observations_and_detached_snapshot(
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        pytest.fail("request admission must not execute the native solver")

    monkeypatch.setattr(
        "structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_driver.run_ordinal_history",
        forbidden,
    )
    payload = ordinal_request()
    original = deepcopy(payload)
    request = validate_rc_corotational_ordinal_job_request(payload)
    assert (
        request.progress_total == 4
        and request.progress_unit == "completed_source_ordinals"
    )
    assert request.plan._solve_prefix_count == (0, 1, 1, 2, 3)
    assert request.to_dict() == original
    payload["history_plan"]["rows"].clear()
    payload["observed_force_reference"]["rows"].clear()
    escaped = request.to_dict()
    escaped["model"]["nodes"].clear()
    assert request.to_dict() == original
    assert request.source_revision_is_execution_attestation is False
    assert (
        request.context_hash
        == validate_rc_corotational_ordinal_job_request(
            request.request_bytes
        ).context_hash
    )


@pytest.mark.parametrize(
    "path,value",
    [
        (("history_plan", "rows", 1, "ordinal"), True),
        (("history_plan", "rows", 1, "ordinal"), 2),
        (("history_plan", "rows", 1, "source_row"), 2),
        (("history_plan", "rows", 1, "source_row_sha256"), "wrong"),
        (("history_plan", "rows", 1, "target_m"), True),
        (("history_plan", "rows", 1, "target_m"), float("inf")),
        (("history_plan", "rows", 1, "axial_load_kn"), "744"),
        (("observed_force_reference", "unit"), "kip"),
        (("observed_force_reference", "rows", 1, "ordinal"), 0),
        (
            ("observed_force_reference", "rows", 1, "source_row_sha256"),
            "sha256:" + "d" * 64,
        ),
        (("observed_force_reference", "rows", 1, "observed_force_kn"), True),
        (("config", "initialization"), "experimental_tare"),
        (("config", "independent_axial_load_role"), "additional_dead_global"),
        (("config", "maximum_subdivision_depth"), 9),
        (("config", "maximum_solver_attempts"), 1000001),
        (("config", "axial_load_pattern", 0, "component"), "MZ"),
        (("config", "axial_load_pattern", 0, "node_id"), "missing"),
        (("config", "axial_load_pattern", 0, "coefficient"), 0.0),
        (("execution_config", "record_limit_per_call"), 256),
        (("execution_config", "attempt_limit_per_call"), True),
        (("execution_config", "production_solver_budget"), 0),
    ],
)
def test_rejects_ambiguous_or_corrupt_inputs(path, value):
    payload = ordinal_request()
    cursor = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValueError):
        validate_rc_corotational_ordinal_job_request(payload)


@pytest.mark.parametrize("baseline", ["fixed", "proportional"])
def test_source_total_axial_rejects_baseline_double_counting(baseline):
    payload = ordinal_request()
    if baseline == "fixed":
        payload["config"]["fixed_nodal_loads"] = [["N3", "FX", -0.01]]
    else:
        payload["model"]["loads"][0]["components"]["FX"] = -0.01
    with pytest.raises(ValueError, match="overlaps"):
        validate_rc_corotational_ordinal_job_request(payload)


def test_model_cap_is_checked_before_dense_compile(monkeypatch):
    payload = ordinal_request()
    payload["model"]["nodes"] *= 17

    def forbidden(*args, **kwargs):
        pytest.fail("oversized model reached dense compilation")

    monkeypatch.setattr(
        "structural_analysis.execution.rc_corotational_ordinal_job_request.compile_rc_corotational_control_model",
        forbidden,
    )
    with pytest.raises(ValueError, match="bounded before"):
        validate_rc_corotational_ordinal_job_request(payload)


def test_historical_owner_source_decode_does_not_fingerprint_current_sources(
    monkeypatch,
):
    def forbidden():
        pytest.fail("historical admission fingerprinted current code")

    monkeypatch.setattr(
        "structural_analysis.execution.rc_corotational_ordinal_job_request._source_identity",
        forbidden,
    )
    request = validate_rc_corotational_ordinal_job_request(
        ordinal_request(), recorded_source_identity="sha256:" + "f" * 64
    )
    assert request.execution_source_identity == "sha256:" + "f" * 64


def test_duplicate_transport_key_and_truncated_observations_rejected():
    payload = ordinal_request()
    payload["observed_force_reference"]["rows"].pop()
    with pytest.raises(ValueError, match="all source ordinals"):
        validate_rc_corotational_ordinal_job_request(payload)
    with pytest.raises(ValueError, match="duplicate JSON"):
        validate_rc_corotational_ordinal_job_request(
            b'{"schema_version":1,"schema_version":2}'
        )
