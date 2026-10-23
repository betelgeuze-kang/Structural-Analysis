"""Bounded portal admission and replay; synthetic software verification only."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, ValidationError
import pytest

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_corotational_control import (
    RCCorotationalControlExecutionError,
    analyze_rc_corotational_control,
    validate_rc_corotational_control_artifacts,
)
from structural_analysis.api.rc_corotational_control_model import (
    RC_COROTATIONAL_PORTAL_MODEL_PROFILE,
    compile_rc_corotational_control_model,
)
from structural_analysis.execution.rc_corotational_job_request import (
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)
from structural_analysis.execution.rc_corotational_phase_supervisor import (
    run_rc_corotational_phase,
)
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from tests.test_rc_corotational_durable_worker import TENANT, WORKER, service_at
from tests.test_rc_corotational_job_request import request as legacy_request
from tests.test_rc_corotational_phase_policy import policy


EXAMPLE = (
    Path(__file__).parents[1]
    / "examples/public_rc_portal_frame_corotational_request.json"
)


def request():
    return json.loads(EXAMPLE.read_bytes())


def set_value(payload, path, value):
    cursor = payload
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def test_portal_admission_preserves_native_geometry_load_split_and_identity(
    monkeypatch,
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure portal admission invoked a numerical solve")

    monkeypatch.setattr(
        "structural_analysis.api.rc_corotational_control.analyze_rc_corotational_control",
        forbidden,
    )
    payload = request()
    before = deepcopy(payload)
    admitted = validate_rc_corotational_job_request(payload)
    assert payload == before
    assert admitted.to_dict() == before
    assert admitted.request_bytes == rc_corotational_job_canonical_bytes(before)
    assert (
        admitted.request_hash
        == "sha256:" + hashlib.sha256(admitted.request_bytes).hexdigest()
    )
    assert admitted.config.experimental_portal_frame is True
    assert admitted.api_kwargs()["experimental_portal_frame"] is True
    compiled = compile_rc_corotational_control_model(
        admitted.model,
        fixed_nodal_loads=admitted.config.fixed_nodal_loads,
        experimental_portal_frame=True,
    )
    assert compiled.compiler_profile == RC_COROTATIONAL_PORTAL_MODEL_PROFILE
    assert compiled.node_ids == ("N1", "N2", "N3", "N4")
    assert compiled.support_node_ids == ("N1", "N2")
    assert compiled.problem.fixed_global_dofs == (0, 1, 2, 3, 4, 5)
    assert compiled.problem.reference_external_loads == ((9, 1.0),)
    assert compiled.problem.fixed_external_loads == ((7, -1.0), (10, -1.0))
    assert [(m.member_id, m.node_i, m.node_j) for m in compiled.problem.members] == [
        ("column-left", 0, 2),
        ("beam-top", 2, 3),
        ("column-right", 3, 1),
    ]
    assert compiled.source_model_checksum == admitted.source_model_checksum
    assert compiled.problem.contract_hash == admitted.problem_contract_hash
    # Opt-in does not widen the earlier fixed-chord cantilever compiler.
    fixed, unsupported, _warnings = _compile(admitted.model)
    assert fixed is None and unsupported


@pytest.mark.parametrize("isolated", [False, True])
def test_legacy_v6_v7_exact_bytes_and_options_have_no_injected_portal_field(isolated):
    payload = legacy_request()
    if isolated:
        payload["schema_version"] = "structural-analysis-job-request.v7"
        payload["execution_config"]["phase_execution_policy"] = policy()
    raw = rc_corotational_job_canonical_bytes(payload)
    admitted = validate_rc_corotational_job_request(raw)
    assert admitted.request_bytes == raw
    assert admitted.to_dict() == payload
    assert admitted.request_hash == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert admitted.config.experimental_portal_frame is False
    assert "experimental_portal_frame" not in admitted.api_kwargs()


def test_portal_v7_keeps_isolated_phase_contract_and_optional_profile():
    payload = request()
    payload["schema_version"] = "structural-analysis-job-request.v7"
    payload["execution_config"]["phase_execution_policy"] = policy()
    admitted = validate_rc_corotational_job_request(payload)
    assert admitted.to_dict() == payload
    assert admitted.execution_config.phase_execution_policy is not None
    assert admitted.api_kwargs()["experimental_portal_frame"] is True


@pytest.mark.parametrize(
    "path,value",
    [
        (("config", "experimental_portal_frame"), False),
        (("config", "experimental_portal_frame"), 1),
        (("config", "experimental_portal_frame"), "true"),
        (("config", "experimental_pin_roller_beam"), True),
        (("config", "experimental_fixed_guided_axial"), True),
        (("config", "control_node_id"), "N1"),
        (("config", "control_component"), "UY"),
        (("config", "fixed_nodal_loads"), []),
        (("config", "fixed_nodal_loads"), [["N3", "FY", -1.0]]),
        (("config", "fixed_nodal_loads", 0), ["N3", "FX", -1.0]),
        (("config", "fixed_nodal_loads", 0), ["N1", "FY", -1.0]),
        (("config", "fixed_nodal_loads", 0, 2), 0.0),
        (("config", "fixed_nodal_loads", 0, 2), 1.0),
        (("config", "fixed_nodal_loads", 1, 0), "N3"),
        (("model", "nodes", 3, "coordinates", 1), 3.1),
        (("model", "nodes", 3, "coordinates", 2), 0.1),
        (("model", "elements", 1, "nodes"), ["N1", "N2"]),
        (("model", "elements", 1, "type"), "stateful_rc_fiber_frame2d"),
        (("model", "supports", 1, "dofs"), ["UX", "UY"]),
        (("model", "supports", 1, "dofs"), ["UX", "UY", "RZ", "RZ"]),
        (("model", "supports", 1, "node"), "N4"),
        (("model", "loads", 0, "node"), "N1"),
        (("model", "loads", 0, "components", "FY"), -1.0),
        (("model", "loads", 0, "components", "MZ"), 1.0),
        (("model", "metadata"), {"case_id": "portal", "profile": "portal"}),
        (
            ("model", "unsupported_features"),
            [{"code": "unmodeled", "message": "unsupported"}],
        ),
    ],
)
def test_portal_rejects_inputs_outside_the_explicit_profile(path, value):
    payload = request()
    set_value(payload, path, value)
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)


def test_portal_rejects_missing_opt_in_and_observation_control():
    payload = request()
    del payload["config"]["experimental_portal_frame"]
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)
    payload = request()
    del payload["config"]["control_node_id"], payload["config"]["control_component"]
    payload["config"]["control_observation"] = {
        "schema_version": "linear-physical-displacement-observation.v1",
        "terms": [{"node_id": "N4", "component": "UX", "coefficient": 1.0}],
    }
    with pytest.raises(ValueError, match="portal control"):
        validate_rc_corotational_job_request(payload)


def test_direct_portal_api_cannot_bypass_lateral_control_admission():
    admitted = validate_rc_corotational_job_request(EXAMPLE.read_bytes())
    options = admitted.api_kwargs()
    options["control_component"] = "UY"
    with pytest.raises(ValueError, match="portal control"):
        analyze_rc_corotational_control(admitted.model, admitted.targets_m, **options)
    options = admitted.api_kwargs()
    options["experimental_portal_frame"] = 1
    with pytest.raises(ValueError, match="boolean flags"):
        analyze_rc_corotational_control(admitted.model, admitted.targets_m, **options)


def test_portal_reordered_ids_remain_authored_and_shape_is_not_position_inferred():
    payload = request()
    payload["model"]["nodes"].reverse()
    payload["model"]["supports"].reverse()
    admitted = validate_rc_corotational_job_request(payload)
    compiled = compile_rc_corotational_control_model(
        admitted.model,
        experimental_portal_frame=True,
        fixed_nodal_loads=admitted.config.fixed_nodal_loads,
    )
    assert compiled.node_ids == ("N4", "N3", "N2", "N1")
    assert compiled.support_node_ids == ("N2", "N1")
    assert compiled.problem.reference_external_loads == ((0, 1.0),)
    assert compiled.problem.fixed_external_loads == ((1, -1.0), (4, -1.0))


def test_portal_gravity_reversals_saved_restart_and_fresh_verification(tmp_path):
    admitted = validate_rc_corotational_job_request(EXAMPLE.read_bytes())
    full_options = admitted.api_kwargs()
    full_options["attempt_limit_per_call"] = None
    full = analyze_rc_corotational_control(
        admitted.model, admitted.targets_m, **full_options
    )
    full_result = json.loads(full.result_bytes)
    assert full_result["contract_pass"] and full_result["status"] == "ready"
    assert full_result["completed_target_count"] == 3
    assert full_result["total_control_attempts"] == 3
    assert [row["phase"] for row in full_result["responses"]] == [
        "preload",
        "control",
        "control",
        "control",
    ]
    for row, target in zip(
        full_result["responses"][1:], admitted.targets_m, strict=True
    ):
        controlled = next(node for node in row["nodes"] if node["node_id"] == "N4")
        assert controlled["displacements_m_rad"][0] == pytest.approx(target, abs=1e-12)
    assert [row["load_factor"] > 0 for row in full_result["responses"][1:]] == [
        True,
        False,
        True,
    ]
    first = analyze_rc_corotational_control(
        admitted.model, admitted.targets_m, **admitted.api_kwargs()
    )
    assert json.loads(first.result_bytes)["status"] == "paused"
    saved_request, saved_restart = tmp_path / "request.json", tmp_path / "restart.json"
    saved_request.write_bytes(admitted.request_bytes)
    saved_restart.write_bytes(first.continuation_bytes)
    reopened = validate_rc_corotational_job_request(saved_request.read_bytes())
    resumed = analyze_rc_corotational_control(
        reopened.model,
        reopened.targets_m,
        restart=saved_restart.read_bytes(),
        **full_options,
    )
    result = json.loads(resumed.result_bytes)
    assert result["contract_pass"]
    assert result["responses"] == full_result["responses"]
    assert resumed.continuation_bytes == full.continuation_bytes
    assert result["work"]["restart_replay_solver_calls"] == 1
    verification = validate_rc_corotational_control_artifacts(
        reopened.model,
        reopened.targets_m,
        result=resumed.result_bytes,
        continuation=resumed.continuation_bytes,
        restart=saved_restart.read_bytes(),
        **full_options,
    )
    assert verification["artifact_contract_pass"] and verification["contract_pass"]
    assert not verification["independent_physical_validation"]
    changed = request()
    changed["config"]["fixed_nodal_loads"][0][2] = -2.0
    changed = validate_rc_corotational_job_request(changed)
    with pytest.raises(RCCorotationalControlExecutionError):
        analyze_rc_corotational_control(
            changed.model,
            changed.targets_m,
            restart=saved_restart.read_bytes(),
            **changed.api_kwargs(),
        )


def test_portal_bridge_does_not_mutate_the_original_canonical_model():
    payload = request()
    model = load_neutral_json_bytes(
        rc_corotational_job_canonical_bytes(payload["model"])
    )
    before = model.to_dict()
    compile_rc_corotational_control_model(
        model,
        fixed_nodal_loads=(("N3", "FY", -1.0), ("N4", "FY", -1.0)),
        experimental_portal_frame=True,
    )
    assert model.to_dict() == before


@pytest.mark.skipif(sys.platform != "linux", reason="authored Linux phase profile")
def test_portal_v7_actual_child_analysis_and_fresh_child_verification(monkeypatch):
    """Exercise the real subprocess transport; this is not durable lease evidence."""

    def forbidden(*_args, **_kwargs):
        pytest.fail("isolated portal execution called the parent numerical API")

    for name in (
        "analyze_rc_corotational_control",
        "validate_rc_corotational_control_artifacts",
    ):
        monkeypatch.setattr(
            f"structural_analysis.api.rc_corotational_control.{name}", forbidden
        )
    payload = request()
    payload["schema_version"] = "structural-analysis-job-request.v7"
    payload["execution_config"]["phase_execution_policy"] = policy()
    payload["execution_config"]["attempt_limit_per_call"] = 3
    admitted = validate_rc_corotational_job_request(payload)
    options = dict(
        request_bytes=admitted.request_bytes,
        completed_before=0,
        completed_after=3,
        restart=None,
        policy=admitted.execution_config.phase_execution_policy,
        lease_check=lambda: None,
    )
    analysis = run_rc_corotational_phase(phase="analysis", **options)
    assert analysis.status == "returned"
    result = json.loads(analysis.raw_result)
    assert result["status"] == "ready" and result["contract_pass"]
    assert result["completed_target_count"] == 3
    assert result["work"]["control_solver_calls"] == 3
    verified = run_rc_corotational_phase(
        phase="verification",
        result=analysis.raw_result,
        checkpoint=analysis.native_checkpoint,
        **options,
    )
    assert verified.status == "returned"
    assert verified.verification_report["artifact_contract_pass"]
    assert verified.verification_report["contract_pass"]
    assert verified.verification_report["replay_work"]["control_solver_calls"] == 3
    assert not verified.verification_report["independent_physical_validation"]


def test_actual_portal_durable_report_preserves_opt_in_without_new_execution(
    tmp_path, monkeypatch
):
    payload = request()
    payload["execution_config"]["attempt_limit_per_call"] = 3
    service = service_at(tmp_path / "store")
    job = service.submit_job(**TENANT, idempotency_key="portal-report", request=payload)
    claim = service.claim_next(**WORKER, lease_seconds=300)
    completed = execute_job_claim(service, claim, **WORKER)
    assert completed.status == "succeeded"

    def forbidden(*_args, **_kwargs):
        pytest.fail("saved portal report invoked new numerical/source work")

    for name in (
        "analyze_rc_corotational_control",
        "validate_rc_corotational_control_artifacts",
        "solve_stateful_corotational_fiber_frame2d_load_step",
        "run_corotational_control_subdivision",
        "_source_identity",
    ):
        monkeypatch.setattr(
            f"structural_analysis.api.rc_corotational_control.{name}", forbidden
        )
    raw = service.read_rc_corotational_report(
        job.job_id,
        **TENANT,
        expected_request_hash=completed.request.content_hash,
        expected_result_artifact_hash=completed.result.content_hash,
        expected_evidence_artifact_hash=completed.evidence.content_hash,
    )
    report = json.loads(raw)
    assert report["declarations"]["config"] == payload["config"]
    assert report["progress"]["accepted_response_states"] == 4
    assert report["progress"]["authored_targets"] == {"completed": 3, "total": 3}
    assert [row["phase"] for row in report["responses"]] == [
        "preload",
        "control",
        "control",
        "control",
    ]
    assert report["derivation"]["fresh_analysis_invocations"] == 0
    assert report["derivation"]["fresh_verification_invocations"] == 0
    assert report["derivation"]["source_fingerprint_invocations"] == 0
    schema = json.loads(
        (
            Path(__file__).parents[1]
            / "src/structural_analysis/schemas/rc_corotational_report_v1.schema.json"
        ).read_bytes()
    )
    validator = Draft202012Validator(schema)
    validator.validate(report)
    for invalid in (False, 1, "true"):
        forged = deepcopy(report)
        forged["declarations"]["config"]["experimental_portal_frame"] = invalid
        with pytest.raises(ValidationError):
            validator.validate(forged)
