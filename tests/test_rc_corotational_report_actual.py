"""Actual tiny source/restore/report workflow; no measured specimen authority."""

import base64
import json
import signal
import sys

import pytest

from structural_analysis.api.strict_json import strict_json_object_bytes
from .frontend.rc_corotational_review_snapshot import (
    authored_request,
    generate_snapshot,
    sha,
)


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux managed restore")


@pytest.mark.parametrize("profile", ["v6", "v7"])
def test_original_request_json_boundary(profile):
    original = json.dumps(authored_request(profile), indent=2).encode("utf-8")
    assert strict_json_object_bytes(original) == authored_request(profile)


@pytest.mark.parametrize("raw", [b'{"duplicate":1,"duplicate":1}', b'{"value":NaN}'])
def test_invalid_original_json_fails_before_store_or_worker(tmp_path, raw):
    workspace = tmp_path / "invalid"
    with pytest.raises(ValueError):
        generate_snapshot(workspace, "v7", raw)
    assert not workspace.exists()


@pytest.mark.parametrize("profile", ["v6", "v7"])
def test_actual_process_terminate_managed_restore_reopen_and_report(tmp_path, profile):
    # Whitespace and JSON key order represent the browser's original file;
    # persisted canonical request values, raw report and hash identity are checked.
    original = json.dumps(authored_request(profile), indent=2).encode("utf-8")
    snapshot = generate_snapshot(tmp_path / profile, profile, original)
    report_bytes = base64.b64decode(snapshot["report"]["body_base64"], validate=True)
    report = json.loads(report_bytes)
    assert snapshot["request"] == authored_request(profile)
    assert base64.b64decode(snapshot["submitted_request_base64"]) == original
    assert report["bindings"]["original_artifacts"] == {
        role: snapshot["job"][role]
        for role in ("request", "checkpoint", "result", "evidence")
    }
    assert report["progress"] == {
        "control_solver_attempts": {"completed": 3, "maximum": 255},
        "authored_targets": {"completed": 3, "total": 3},
        "accepted_response_states": 4,
    }
    assert [row["phase"] for row in report["responses"]] == [
        "preload",
        "control",
        "control",
        "control",
    ]
    controls = [row["control_displacement_m"] for row in report["responses"][1:]]
    assert controls == pytest.approx([-1e-6, -2e-6, 1e-6], abs=1e-12)
    factors = [row["load_factor"] for row in report["responses"][1:]]
    assert min(factors) < 0 < max(factors)
    for row in report["responses"]:
        assert row["nodes"][2]["external_loads_kn_knm"][0] == -0.01
        # Control UY is free: the stored reaction 0 is not the applied lateral load.
        assert row["nodes"][2]["reactions_kn_knm"][1] == 0.0
    assert report["execution"]["pending_ordinals"] == [3]
    assert report["execution"]["unknown_execution_work"] is True
    assert [row["ordinal"] for row in report["execution"]["invocations"]] == [
        1,
        2,
        4,
        5,
    ]
    assert snapshot["report"]["headers"]["x-structural-report-sha256"] == sha(
        report_bytes
    )
    assert (
        snapshot["report"]["headers"]["x-structural-report-id"]
        == "rcc_" + sha(report_bytes)[7:]
    )
    proof = snapshot["proof"]
    assert proof["first_worker"]["returncode"] == -signal.SIGKILL
    assert proof["first_worker"]["reaped"] and proof["fresh_worker"]["reaped"]
    assert proof["fresh_worker"]["returncode"] == 0
    assert (
        proof["restored_checkpoint_byte_identical"] and proof["retired_source_rejected"]
    )
    assert (
        proof["numerical_state_before_report_sha256"]
        == proof["numerical_state_after_report_sha256"]
    )
    assert proof["report_reads_numerical_invocations"] == 0
    assert proof["report_reads_source_fingerprint_invocations"] == 0
    assert proof["reopened_report_byte_identical"]
    assert len(proof["numerical_children"]) == (4 if profile == "v7" else 0)
    assert not proof["independent_physical_validation"]
    assert not proof["design_authority"] and not proof["release_approved"]
