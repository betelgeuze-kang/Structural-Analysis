"""Pure isolated-policy admission: no child launch, numerical solve or source claim."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from structural_analysis.execution import rc_corotational_job_contract as contract
from structural_analysis.execution.rc_corotational_job_request import (
    ISOLATED_RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
    RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
    RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSIONS,
    RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION,
    rc_corotational_job_canonical_bytes,
    validate_rc_corotational_job_request,
)
from structural_analysis.execution.rc_corotational_phase_policy import (
    RC_COROTATIONAL_PHASE_POLICY_SCHEMA_VERSION,
    RCCorotationalPhasePolicy,
    decode_rc_corotational_phase_policy,
)
from tests.test_rc_corotational_job_request import request as legacy_request


@pytest.fixture(autouse=True)
def no_numerical_execution_or_source_identity(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure isolated policy admission invoked numerical/source execution")

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
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision",
            (
                "solve_stateful_corotational_fiber_frame2d_displacement_control_step",
                "_source_identity",
            ),
        ),
    ):
        for name in names:
            monkeypatch.setattr(f"{module}.{name}", forbidden)


def policy():
    return {
        "schema_version": RC_COROTATIONAL_PHASE_POLICY_SCHEMA_VERSION,
        "analysis_timeout_ms": 30000,
        "verification_timeout_ms": 30000,
        "termination_grace_ms": 50,
    }


def request():
    payload = legacy_request()
    payload["schema_version"] = ISOLATED_RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION
    payload["execution_config"]["phase_execution_policy"] = policy()
    return payload


@pytest.mark.parametrize("bounds", [(1, 1, 1), (3600000, 3600000, 5000)])
def test_exact_integer_policy_bounds_roundtrip_and_frozen_state(bounds):
    typed = RCCorotationalPhasePolicy(*bounds)
    encoded = rc_corotational_job_canonical_bytes(typed.to_dict())
    assert decode_rc_corotational_phase_policy(encoded) == typed
    assert decode_rc_corotational_phase_policy(typed.to_dict()) == typed
    assert typed.analysis_timeout_seconds == bounds[0] / 1000
    assert typed.verification_timeout_seconds == bounds[1] / 1000
    assert typed.termination_grace_seconds == bounds[2] / 1000
    copied = typed.to_dict()
    copied["analysis_timeout_ms"] = 123
    assert typed.analysis_timeout_ms == bounds[0]
    with pytest.raises(FrozenInstanceError):
        typed.analysis_timeout_ms = 123


@pytest.mark.parametrize(
    "field", ["analysis_timeout_ms", "verification_timeout_ms", "termination_grace_ms"]
)
@pytest.mark.parametrize("bad", [True, False, 0, -1, 3600001, 1.0, "1", None, [], {}])
def test_policy_rejects_ambiguous_noninteger_or_out_of_bound_values(field, bad):
    payload = policy()
    payload[field] = bad
    with pytest.raises(ValueError):
        decode_rc_corotational_phase_policy(payload)


def test_grace_specific_limit_and_strict_policy_transport():
    payload = policy()
    payload["termination_grace_ms"] = 5001
    with pytest.raises(ValueError):
        decode_rc_corotational_phase_policy(payload)
    for invalid in (
        dict(policy(), extra="ignored"),
        dict(policy(), schema_version="bounded-rc-fiber-phase-execution-policy.v1"),
        dict(policy(), schema_version=True),
        [],
        None,
        b'{"schema_version":"a","schema_version":"b"}',
        b'{"analysis_timeout_ms":NaN}',
        b"[]",
        b"not json",
        b" " * 4097,
    ):
        with pytest.raises(ValueError):
            decode_rc_corotational_phase_policy(invalid)
    for field in policy():
        incomplete = policy()
        del incomplete[field]
        with pytest.raises(ValueError):
            decode_rc_corotational_phase_policy(incomplete)


def test_v6_keeps_exact_legacy_bytes_hash_and_two_execution_fields():
    payload = legacy_request()
    raw = rc_corotational_job_canonical_bytes(payload)
    typed = validate_rc_corotational_job_request(raw)
    assert typed.request_bytes == raw and typed.to_dict() == payload
    assert typed.request_hash == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert typed.execution_config.phase_execution_policy is None
    assert set(typed.to_dict()["execution_config"]) == {
        "attempt_limit_per_call",
        "maximum_api_invocations",
    }
    assert (
        RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION
        == "structural-analysis-job-request.v6"
    )
    assert RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSIONS == (
        RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
        ISOLATED_RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION,
    )
    payload["execution_config"]["phase_execution_policy"] = policy()
    with pytest.raises(ValueError, match="exactly"):
        validate_rc_corotational_job_request(payload)


def test_v7_requires_policy_and_binds_it_without_leaking_to_numerical_api():
    original = legacy_request()
    old = validate_rc_corotational_job_request(original)
    payload = request()
    isolated = validate_rc_corotational_job_request(payload)
    assert (
        isolated.execution_config.phase_execution_policy
        == decode_rc_corotational_phase_policy(policy())
    )
    assert isolated.api_kwargs() == old.api_kwargs()
    assert "phase_execution_policy" not in isolated.api_kwargs()
    assert isolated.config == old.config
    assert isolated.targets_m == old.targets_m
    assert isolated.progress_total == old.progress_total
    assert isolated.source_model_checksum == old.source_model_checksum
    assert isolated.source_input_checksum == old.source_input_checksum
    assert isolated.problem_contract_hash == old.problem_contract_hash
    assert isolated.request_hash != old.request_hash
    assert isolated.resume_contract_hash != old.resume_contract_hash
    assert isolated.to_dict() == payload
    assert isolated.source_revision_is_execution_attestation is False
    assert (
        isolated.to_dict()["result_contract"]
        == RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION
    )
    for field in (
        "phase_execution_policy",
        "attempt_limit_per_call",
        "maximum_api_invocations",
    ):
        missing = request()
        del missing["execution_config"][field]
        with pytest.raises(ValueError):
            validate_rc_corotational_job_request(missing)
    for invalid in (None, False, {}, dict(policy(), extra=1)):
        missing = request()
        missing["execution_config"]["phase_execution_policy"] = invalid
        with pytest.raises(ValueError):
            validate_rc_corotational_job_request(missing)


@pytest.mark.parametrize(
    "field,value",
    [
        ("analysis_timeout_ms", 30001),
        ("verification_timeout_ms", 30001),
        ("termination_grace_ms", 51),
    ],
)
def test_every_authored_phase_deadline_changes_request_and_resume_identity(
    field, value
):
    payload = request()
    before = validate_rc_corotational_job_request(payload)
    payload["execution_config"]["phase_execution_policy"][field] = value
    after = validate_rc_corotational_job_request(payload)
    assert after.request_hash != before.request_hash
    assert after.resume_contract_hash != before.resume_contract_hash
    assert after.api_kwargs() == before.api_kwargs()


def test_policy_snapshot_is_detached_and_pure_result_contract_accepts_versioned_request_binding():
    payload = request()
    typed = validate_rc_corotational_job_request(payload)
    retained = deepcopy(payload)
    payload["execution_config"]["phase_execution_policy"]["analysis_timeout_ms"] = 1
    assert typed.to_dict() == retained
    assert typed.execution_config.phase_execution_policy.analysis_timeout_ms == 30000
    with pytest.raises(FrozenInstanceError):
        typed.execution_config.phase_execution_policy = None
    bound = contract.rc_corotational_chunk_binding(typed, 0, None)
    assert bound["job_request_hash"] == typed.request_hash
    assert bound == contract.rc_corotational_chunk_binding(retained, 0, None)
    assert bound["planned_after"] == typed.execution_config.attempt_limit_per_call
    legacy = validate_rc_corotational_job_request(legacy_request())
    assert contract._expected_api_request(
        typed, 0, None, "a" * 64
    ) == contract._expected_api_request(legacy, 0, None, "a" * 64)


def test_v7_schema_requires_exact_policy_and_preserves_existing_budget_limits():
    root = Path(__file__).parents[1] / "src/structural_analysis/schemas"
    schema = json.loads((root / "job_request_v7.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(request())
    execution = schema["properties"]["execution_config"]
    assert set(execution["required"]) == {
        "attempt_limit_per_call",
        "maximum_api_invocations",
        "phase_execution_policy",
    }
    assert execution["properties"]["attempt_limit_per_call"]["maximum"] == 4096
    assert execution["properties"]["maximum_api_invocations"]["maximum"] == 100000
    assert (
        schema["properties"]["result_contract"]["const"]
        == "bounded-rc-corotational-job-result.v1"
    )
    legacy_schema = json.loads((root / "job_request_v6.schema.json").read_bytes())
    assert set(legacy_schema["properties"]["execution_config"]["required"]) == {
        "attempt_limit_per_call",
        "maximum_api_invocations",
    }
    for invalid in (
        legacy_request(),
        dict(request(), unexpected=True),
    ):
        with pytest.raises(ValidationError):
            validator.validate(invalid)
    payload = request()
    payload["execution_config"]["phase_execution_policy"]["termination_grace_ms"] = 5001
    with pytest.raises(ValidationError):
        validator.validate(payload)


@pytest.mark.parametrize(
    "path,value",
    [
        (("config", "maximum_attempt_count"), 4097),
        (("config", "maximum_subdivision_depth"), 21),
        (("config", "targets_m"), [True]),
        (("execution_config", "attempt_limit_per_call"), 4097),
        (("execution_config", "maximum_api_invocations"), 100001),
        (("model", "nodes", 1, "coordinates", 2), 0.5),
    ],
)
def test_v7_does_not_relax_model_numerical_input_or_execution_limits(path, value):
    payload = request()
    parent = payload
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value
    with pytest.raises(ValueError):
        validate_rc_corotational_job_request(payload)
