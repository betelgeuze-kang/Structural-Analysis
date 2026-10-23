"""Stored response projections; one tiny software fixture, no physical claims."""

from copy import deepcopy
import json

import pytest

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.execution import rc_corotational_detail_report as detail
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.execution.rc_corotational_job_request import (
    validate_rc_corotational_job_request,
)
from . import test_rc_corotational_report as nodal
from .test_rc_corotational_durable_worker import TENANT, WORKER, service_at
from .test_rc_portal_control import request


@pytest.fixture(scope="module")
def saved(tmp_path_factory):
    payload = request()
    payload["execution_config"]["attempt_limit_per_call"] = 3
    service = service_at(tmp_path_factory.mktemp("saved-detail"))
    job = service.submit_job(**TENANT, idempotency_key="detail", request=payload)
    claim = service.claim_next(**WORKER, lease_seconds=300)
    job = execute_job_claim(service, claim, **WORKER)
    assert job.status == "succeeded"
    original = json.loads(service.read_result(job.job_id, **TENANT))
    raw_nodal = service.read_rc_corotational_report(
        job.job_id, **TENANT, **nodal.expected(job)
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("saved report read invoked numerical/recovery/source execution")

    with pytest.MonkeyPatch.context() as patch:
        for module, names in (
            (
                "structural_analysis.api.rc_corotational_control",
                (
                    "analyze_rc_corotational_control",
                    "validate_rc_corotational_control_artifacts",
                    "solve_stateful_corotational_fiber_frame2d_load_step",
                    "run_corotational_control_subdivision",
                    "_source_identity",
                ),
            ),
            (
                "structural_analysis.elements.stateful_corotational_fiber_beam2d.StatefulCorotationalFiberBeam2D",
                ("integrate",),
            ),
            (
                "structural_analysis.elements.stateful_fiber_beam2d.StatefulFiberBeam2D",
                ("integrate",),
            ),
        ):
            for name in names:
                patch.setattr(f"{module}.{name}", forbidden)
        yield {
            "service": service,
            "job": job,
            "request": validate_rc_corotational_job_request(payload),
            "result": original,
            "nodal": raw_nodal,
        }


def project(saved, result=None):
    return detail.build_rc_corotational_detail_report(
        request=saved["request"],
        result=saved["result"] if result is None else result,
        nodal_report=saved["nodal"],
    )


def test_projection_is_exact_source_order_with_declared_units_and_reverse_orientation(
    saved,
):
    before = deepcopy(saved["result"])
    raw = project(saved)
    report = json.loads(raw)
    assert raw == project(saved)
    assert saved["result"] == before
    assert (
        report["schema_version"] == detail.RC_COROTATIONAL_DETAIL_REPORT_SCHEMA_VERSION
    )
    assert report["nodal_report_hash"] == json.loads(saved["nodal"])["report_hash"]
    assert report["bindings"] == json.loads(saved["nodal"])["bindings"]
    assert report["units"] == detail.RC_COROTATIONAL_DETAIL_REPORT_UNITS
    assert report["report_hash"] == detail._sha(
        detail.rc_corotational_job_canonical_bytes(
            {key: value for key, value in report.items() if key != "report_hash"}
        )
    )
    assert [row["load_factor"] for row in report["responses"]] == [
        row["load_factor"] for row in before["api_result"]["responses"]
    ]
    assert (
        report["responses"][1]["load_factor"]
        > 0
        > report["responses"][2]["load_factor"]
    )
    for index, (row, source) in enumerate(
        zip(report["responses"], before["api_result"]["responses"], strict=True)
    ):
        assert row["state_index"] == index
        for member, original in zip(row["members"], source["members"], strict=True):
            assert member["member_id"] == original["member_id"]
            assert (
                member["end_force_global_kn_knm"]
                == original["member_feature_response"]["element_net_end_force_global"]
            )
            assert "tangent" not in member and "internal_force_local" not in member
            c, s = member["current_direction"]
            for offset in (0, 3):
                x, y, moment = member["end_force_local_kn_knm"][offset : offset + 3]
                assert [c * x - s * y, s * x + c * y, moment] == pytest.approx(
                    member["end_force_global_kn_knm"][offset : offset + 3], abs=1e-12
                )
            beam = original["element_response"]["fiber_beam_response"]
            for point, section in enumerate(member["sections"]):
                source_section = beam["section_responses"][point]
                assert section["integration_point_index"] == point
                assert section["xi"] == beam["integration_point_xi"][point]
                assert (
                    section["axial_force_kn"]
                    == source_section["resultants"]["axial_force_kn"]
                )
                assert (
                    section["moment_z_kn_m"]
                    == source_section["resultants"]["moment_z_kn_m"]
                )
                assert [fiber["fiber_index"] for fiber in section["fibers"]] == [
                    0,
                    1,
                    2,
                    3,
                ]
                assert [fiber["material_kind"] for fiber in section["fibers"]] == [
                    "concrete",
                    "concrete",
                    "steel",
                    "steel",
                ]
                assert [
                    fiber["strain"] for fiber in section["fibers"]
                ] == source_section["fiber_strains"]
                assert [
                    fiber["stress_mpa"] for fiber in section["fibers"]
                ] == source_section["fiber_stresses_mpa"]
        right = row["members"][2]
        assert (right["node_i"], right["node_j"]) == ("N4", "N2")
        assert right["current_direction"][1] < -0.99
    assert report["derivation"]["fresh_analysis_invocations"] == 0
    assert report["derivation"]["fresh_verification_invocations"] == 0
    assert report["derivation"]["source_fingerprint_invocations"] == 0


@pytest.mark.parametrize(
    "case",
    [
        "member_order",
        "duplicate_member",
        "boolean_dof",
        "feature_hash",
        "force_bool",
        "force_nan",
        "net_force_definition",
        "direction",
        "length",
        "ip_order",
        "ip_count",
        "section_state",
        "fiber_state",
        "fiber_count",
        "fiber_bool",
        "fiber_string",
        "section_force_bool",
        "section_curvature",
        "checkpoint_binding",
        "accepted_order",
    ],
)
def test_malformed_nested_original_fails_closed(saved, case):
    result = deepcopy(saved["result"])
    row = result["api_result"]["responses"][0]
    member = row["members"][0]
    response = member["element_response"]
    feature = member["member_feature_response"]
    beam = response["fiber_beam_response"]
    section = beam["section_responses"][0]
    if case == "member_order":
        row["members"].reverse()
    elif case == "duplicate_member":
        row["members"][1] = deepcopy(member)
    elif case == "boolean_dof":
        member["global_dofs"][0] = False
    elif case == "feature_hash":
        feature["response_hash"] = "sha256:" + "0" * 64
    elif case == "force_bool":
        feature["element_net_end_force_global"][0] = False
    elif case == "force_nan":
        feature["element_net_end_force_global"][0] = float("nan")
    elif case == "net_force_definition":
        feature["element_net_end_force_global"][0] += 1
    elif case == "direction":
        response["kinematics"]["current_direction"] = [1.0, 0.0]
    elif case == "length":
        response["kinematics"]["current_length_m"] *= 2
    elif case == "ip_order":
        beam["integration_point_xi"].reverse()
    elif case == "ip_count":
        beam["section_responses"].pop()
    elif case == "section_state":
        section["trial_state"]["section_id"] = "different"
    elif case == "fiber_state":
        section["fiber_responses"][0]["trial_state"]["state_hash"] = (
            "sha256:" + "0" * 64
        )
    elif case == "fiber_count":
        section["fiber_strains"].append(0.0)
    elif case == "fiber_bool":
        section["fiber_strains"][0] = False
    elif case == "fiber_string":
        section["fiber_stresses_mpa"][0] = "0"
    elif case == "section_force_bool":
        section["resultants"]["axial_force_kn"] = True
    elif case == "section_curvature":
        section["generalized_strain"]["curvature_z_per_m"] += 0.1
    elif case == "checkpoint_binding":
        row["checkpoint_hash"] = "sha256:" + "0" * 64
    elif case == "accepted_order":
        result["api_result"]["responses"].reverse()
    # Rehash nested feature data, proving shape/linkage guards independently of
    # the source hash guard. The NaN and stale-hash cases intentionally cannot.
    if case not in {"feature_hash", "force_nan"}:
        feature["element_response"] = deepcopy(response)
        feature["response_hash"] = canonical_hash(
            {key: value for key, value in feature.items() if key != "response_hash"}
        )
    with pytest.raises((ValueError, TypeError, KeyError, IndexError)):
        project(saved, result)


def test_service_and_http_are_read_only_exact_and_keep_nodal_bytes(saved):
    service, job = saved["service"], saved["job"]
    before = nodal.numerical_state(service, job)
    api = DurableJobHttpApi(service)
    headers = nodal.headers(job) | {
        "X-Structural-Tenant": TENANT["tenant_id"],
        "Authorization": "Bearer " + TENANT["authorization_token"],
    }
    route = f"/v1/jobs/{job.job_id}/rc-corotational-detail-report"
    reply = api.handle("GET", route, headers=headers)
    assert reply.status == 200
    assert reply.body == project(saved)
    assert (
        reply.headers["x-structural-report-id"] == "rcd_" + detail._sha(reply.body)[7:]
    )
    assert reply.headers["x-structural-report-sha256"] == detail._sha(reply.body)
    assert "-detail-report.json" in reply.headers["content-disposition"]
    assert api.handle("POST", route, headers=headers).status == 405
    assert api.handle("GET", route, headers=headers, body=b"{}").status == 400
    assert api.handle("GET", route, headers={}).status == 401
    assert (
        api.handle(
            "GET",
            route,
            headers=headers
            | {"X-Structural-Expected-Result-Hash": "sha256:" + "0" * 64},
        ).status
        == 409
    )
    assert (
        api.handle(
            "GET",
            route,
            headers={
                key: value
                for key, value in headers.items()
                if key != "X-Structural-Expected-Evidence-Hash"
            },
        ).status
        == 400
    )
    assert (
        service.read_rc_corotational_report(job.job_id, **TENANT, **nodal.expected(job))
        == saved["nodal"]
    )
    assert nodal.numerical_state(service, job) == before


def test_stored_equivalent_load_is_already_scaled_not_multiplied_twice(saved):
    # Synthetic algebra probe of stored load semantics, not an equilibrium test
    # or a claim that member dead loading is supported by this portal request.
    result = deepcopy(saved["result"])
    row = result["api_result"]["responses"][1]
    assert row["load_factor"] != 1.0
    member = row["members"][0]
    feature = member["member_feature_response"]
    feature["element_equivalent_external_load_global"][0] = 2.0
    feature["nodal_equivalent_external_load_global"][0] = 2.0
    member["equivalent_external_load_global"][0] = 2.0
    feature["element_net_end_force_global"][0] = (
        feature["element_internal_load_global"][0] - 2.0
    )
    feature["response_hash"] = canonical_hash(
        {key: value for key, value in feature.items() if key != "response_hash"}
    )
    report = json.loads(project(saved, result))
    assert report["responses"][1]["members"][0]["end_force_global_kn_knm"][0] == (
        feature["element_internal_load_global"][0] - 2.0
    )


def test_detail_byte_cap_is_independent_of_nodal_report(saved, monkeypatch):
    monkeypatch.setattr(detail, "RC_COROTATIONAL_DETAIL_REPORT_MAX_BYTES", 1)
    service, job = saved["service"], saved["job"]
    with pytest.raises(
        JobServiceError, match="rc_corotational_detail_report_too_large"
    ):
        service.read_rc_corotational_detail_report(
            job.job_id, **TENANT, **nodal.expected(job)
        )
    assert (
        service.read_rc_corotational_report(job.job_id, **TENANT, **nodal.expected(job))
        == saved["nodal"]
    )


@pytest.mark.parametrize("version", ["v6", "v7"])
def test_old_saved_nodal_original_without_nested_member_fields_remains_readable(
    tmp_path, monkeypatch, version
):
    service, job = nodal.make_completed(tmp_path, monkeypatch, version)
    before = nodal.read(service, job)
    with pytest.raises(
        JobServiceError, match="rc_corotational_detail_report_original_invalid"
    ):
        service.read_rc_corotational_detail_report(
            job.job_id, **nodal.seams.tenant(), **nodal.expected(job)
        )
    assert nodal.read(service, job) == before
