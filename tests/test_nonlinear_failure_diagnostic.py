"""Actual failed solver source plus adversarial diagnostic transport checks."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.execution.nonlinear_failure_diagnostic import (
    NonlinearFailureBinding,
    build_nonlinear_failure_diagnostic,
    validate_nonlinear_failure_diagnostic,
)
from structural_analysis.model_ir import parse_model_ir_v2


def raw(value):
    return json.dumps(value, indent=2, allow_nan=False).encode()


def rehash(source):
    source.pop("result_hash", None)
    source["result_hash"] = canonical_hash(source)
    return raw(source)


@pytest.fixture(scope="module")
def failed_source():
    payload = json.loads(
        (Path(__file__).parents[1] / "examples/planar_frame_rc_portal.json").read_text()
    )
    result = analyze_nonlinear_frame_model_ir(
        parse_model_ir_v2(payload, require_analysis_ready=True),
        NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE, load_steps=4, maximum_iterations=1
        ),
    ).to_dict()
    assert result["status"] == "blocked"
    assert result["metrics"]["observed_load_path"]["convergence_history_row_count"] > 0
    binding = NonlinearFailureBinding(
        job_id="job_" + "a" * 32,
        request_hash="sha256:" + "b" * 64,
        attempt=1,
        source_revision="c" * 40,
        input_checksum=result["input_checksum"],
        configuration_hash=canonical_hash(result["configuration"]),
    )
    return result, binding


def test_exact_original_failed_result_roundtrip_and_binding(failed_source):
    result, binding = failed_source
    original = raw(result) + b"\n"
    diagnostic = build_nonlinear_failure_diagnostic(original, binding=binding)
    assert (
        validate_nonlinear_failure_diagnostic(diagnostic, expected_binding=binding)
        == original
    )
    assert (
        json.loads(diagnostic)["authority"]
        == "diagnostic_only_no_numerical_design_or_release_authority"
    )
    assert result["checkpoint"] == {"available": False}
    for field, value in (
        ("attempt", 2),
        ("request_hash", "sha256:" + "e" * 64),
        ("job_id", "job_" + "e" * 32),
        ("source_revision", "e" * 40),
    ):
        with pytest.raises(ValueError, match="binding mismatch"):
            validate_nonlinear_failure_diagnostic(
                diagnostic, expected_binding=replace(binding, **{field: value})
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt", True),
        ("attempt", 0),
        ("job_id", "job_wrong"),
        ("request_hash", "b" * 64),
        ("source_revision", "main"),
    ],
)
def test_binding_rejects_ambiguous_identity(failed_source, field, value):
    with pytest.raises(ValueError):
        replace(failed_source[1], **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempted_step_count", True),
        ("attempted_step_count", 2),
        ("committed_step_count", 1),
        ("convergence_history_row_count", 999),
        ("newly_attempted_step_count", 0),
        ("replayed_prefix_step_count", 1),
        ("total_api_work_accounted", True),
        ("scope", "total_api_work"),
    ],
)
def test_rehashed_inconsistent_observation_is_rejected(failed_source, field, value):
    source, binding = failed_source
    source = deepcopy(source)
    source["metrics"]["observed_load_path"][field] = value
    with pytest.raises(ValueError):
        build_nonlinear_failure_diagnostic(rehash(source), binding=binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_load_factor", True),
        ("target_load_factor", 0.5),
        ("committed", 0),
        ("failed_step_rollback_exact", None),
        ("convergence_history_row_count", True),
        ("terminal_reason", []),
    ],
)
def test_rehashed_invalid_step_is_rejected(failed_source, field, value):
    source, binding = failed_source
    source = deepcopy(source)
    source["metrics"]["observed_load_path"]["steps"][0][field] = value
    with pytest.raises(ValueError):
        build_nonlinear_failure_diagnostic(rehash(source), binding=binding)


def test_unknown_work_and_negative_rollback_are_not_promoted(failed_source):
    source, binding = failed_source
    for observed in (None, deepcopy(source["metrics"]["observed_load_path"])):
        candidate = deepcopy(source)
        if observed is not None:
            observed["steps"][0]["failed_step_rollback_exact"] = False
        candidate["metrics"]["observed_load_path"] = observed
        original = rehash(candidate)
        diagnostic = build_nonlinear_failure_diagnostic(original, binding=binding)
        assert (
            validate_nonlinear_failure_diagnostic(diagnostic, expected_binding=binding)
            == original
        )


def test_source_authority_identity_and_json_ambiguity_fail_closed(failed_source):
    source, binding = failed_source
    bad = deepcopy(source)
    bad["authority"]["convergence"] = "authoritative"
    with pytest.raises(ValueError):
        build_nonlinear_failure_diagnostic(rehash(bad), binding=binding)
    with pytest.raises(ValueError):
        build_nonlinear_failure_diagnostic(
            raw(source),
            binding=replace(binding, configuration_hash="sha256:" + "e" * 64),
        )
    duplicate = raw(source)[:-1] + b',"status":"blocked"}'
    with pytest.raises(ValueError):
        build_nonlinear_failure_diagnostic(duplicate, binding=binding)
    diagnostic = build_nonlinear_failure_diagnostic(raw(source), binding=binding)
    for field, value in (
        ("result_artifact_hash", "sha256:" + "e" * 64),
        ("result_byte_length", True),
        ("result_bytes_base64", "!"),
        ("authority", "numerical_authority"),
    ):
        envelope = json.loads(diagnostic)
        envelope[field] = value
        with pytest.raises(ValueError):
            validate_nonlinear_failure_diagnostic(
                raw(envelope), expected_binding=binding
            )
    envelope = json.loads(diagnostic)
    envelope["binding"]["attempt"] = True
    with pytest.raises(ValueError):
        validate_nonlinear_failure_diagnostic(raw(envelope), expected_binding=binding)


def test_successful_result_cannot_be_packaged_as_failure(failed_source):
    payload = json.loads(
        (Path(__file__).parents[1] / "examples/planar_frame_rc_portal.json").read_text()
    )
    source = analyze_nonlinear_frame_model_ir(
        parse_model_ir_v2(payload, require_analysis_ready=True),
        NonlinearFrameConfig(profile=COROTATIONAL_GENERAL_PROFILE, load_steps=4),
    ).to_dict()
    assert source["status"] == "ready"
    binding = replace(
        failed_source[1], configuration_hash=canonical_hash(source["configuration"])
    )
    with pytest.raises(ValueError, match="blocked corotational result"):
        build_nonlinear_failure_diagnostic(raw(source), binding=binding)
