"""Original two-base portal bytes through bounded public RC control.

The public fixed-chord result is a software integration check, not independent
physical validation of the 20 mm portal or the separate corotational study.
"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from structural_analysis.api import rc_fiber_frame_direct_control_cli as cli
from structural_analysis.api.rc_fiber_frame_direct_control import (
    analyze_bounded_rc_fiber_direct_control,
    validate_bounded_rc_fiber_direct_control_artifacts,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    TWO_FIXED_ENDPOINT_REQUEST_SCHEMA_VERSION,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


ROOT = (
    Path(__file__).resolve().parents[1]
    / "examples/research/rc_internal_portal_20mm"
)


def test_original_two_base_portal_requested_targets_replay_with_both_reaction_sets():
    model_bytes = (ROOT / "original-model.json").read_bytes()
    request_bytes = (ROOT / "original-request.json").read_bytes()
    assert hashlib.sha256(model_bytes).hexdigest() == (
        "6f8eec155f5fcf2f9ae942c021a8692e79ae1efd0d1b98342f8aea0b642d0ed6"
    )
    assert hashlib.sha256(request_bytes).hexdigest() == (
        "e0cbc4995e2c98f4a30a0902ac321b4a0e66a9baa61ed20a88e5e73809df627e"
    )
    model = load_neutral_json_bytes(model_bytes)
    original = decode_bounded_rc_fiber_direct_control_request(request_bytes)
    assert original.targets_m == (-0.01, -0.02, 0.01)
    experimental = replace(original, experimental_two_fixed_endpoints=True)
    assert experimental.to_dict()["schema_version"] == (
        TWO_FIXED_ENDPOINT_REQUEST_SCHEMA_VERSION
    )
    derived_bytes = (ROOT / "experimental-two-fixed-endpoints-request.json").read_bytes()
    assert hashlib.sha256(derived_bytes).hexdigest() == (
        "92e94d3580bdf76edabef458ac0f769e054087ab04f897178f3692b2098c0e45"
    )
    assert decode_bounded_rc_fiber_direct_control_request(derived_bytes) == experimental
    assert experimental.resume_contract_hash != original.resume_contract_hash

    result = analyze_bounded_rc_fiber_direct_control(
        model, experimental.targets_m, **experimental.api_kwargs()
    )
    payload = result.to_dict()
    assert result.status == "ready" and result.contract_pass is True
    assert payload["request"]["constant_nodal_loads"] == [
        {"node_id": "N3", "FX_kN": 0.0, "FY_kN": -25.0, "MZ_kNm": 0.0},
        {"node_id": "N4", "FX_kN": 0.0, "FY_kN": -25.0, "MZ_kNm": 0.0},
    ]
    assert payload["request"]["experimental_two_fixed_endpoints"] is True
    assert len(payload["response_history"]) == 3
    assert [(row["node_id"], row["dof"]) for row in payload["terminal_response"][
        "support_reactions"
    ]] == [
        (node, dof)
        for node in ("N1", "N2")
        for dof in ("UX", "UY", "RZ")
    ]
    for response in payload["response_history"]:
        reactions = response["support_reactions"]
        rx = sum(row["value_si"] for row in reactions if row["dof"] == "UX")
        ry = sum(row["value_si"] for row in reactions if row["dof"] == "UY")
        assert abs(rx + response["load_factor"] * 150_000.0) < 0.1
        assert abs(ry - 50_000.0) < 0.1

    verified = validate_bounded_rc_fiber_direct_control_artifacts(
        model,
        experimental.targets_m,
        result=result.result_artifact_bytes(),
        checkpoint=result.checkpoint_artifact_bytes(),
        **experimental.api_kwargs(),
    )
    assert verified.status == "valid_artifact"
    assert verified.contract_pass is True


def test_original_two_base_portal_v3_cli_runs_and_replay_verifies(tmp_path):
    model = tmp_path / "model.json"
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    report = tmp_path / "report.json"
    checkpoint = tmp_path / "checkpoint.json"
    model.write_bytes((ROOT / "original-model.json").read_bytes())
    request.write_bytes(
        (ROOT / "experimental-two-fixed-endpoints-request.json").read_bytes()
    )
    assert cli.main(
        [
            "run",
            "--model",
            str(model),
            "--request",
            str(request),
            "--output",
            str(result),
            "--report",
            str(report),
            "--checkpoint-output",
            str(checkpoint),
        ]
    ) == 0
    observed = json.loads(result.read_bytes())
    receipt = json.loads(report.read_bytes())
    assert checkpoint.is_file()
    assert observed["request"]["experimental_two_fixed_endpoints"] is True
    assert len(observed["response_history"]) == 3
    assert len(observed["terminal_response"]["support_reactions"]) == 6
    assert receipt["request"]["schema_version"] == (
        TWO_FIXED_ENDPOINT_REQUEST_SCHEMA_VERSION
    )
    assert receipt["contract_pass"] is True
    assert receipt["verification"]["fresh_source_execution_invoked"] is True
