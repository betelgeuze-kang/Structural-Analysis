"""RC CLI transport/orchestration stubs and one explicitly bounded real fixture."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control_cli as cli
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    REQUEST_SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/public_rc_fiber_frame_cantilever.json"


def _inputs(tmp_path):
    model = tmp_path / "model.json"
    model.write_bytes(MODEL.read_bytes())
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": REQUEST_SCHEMA_VERSION,
                "control_global_dof": 4,
                "targets_m": [-1e-5, -2e-5],
            }
        )
    )
    return {
        "model": model,
        "request": request,
        "output": tmp_path / "result.json",
        "report": tmp_path / "report.json",
        "checkpoint-output": tmp_path / "checkpoint.json",
    }


def _argv(paths, command="run"):
    return [
        command,
        *(value for key, path in paths.items() for value in ("--" + key, str(path))),
    ]


def _forbid(*args, **kwargs):
    pytest.fail("invalid transport must not enter analysis or verification")


def _old_outputs(paths):
    old = {}
    for key in ("output", "report", "checkpoint-output"):
        if key in paths:
            paths[key].write_bytes(f"old {key}\n".encode())
            old[key] = paths[key].read_bytes()
    return old


def _assert_old(paths, old):
    assert {key: paths[key].read_bytes() for key in old} == old


@dataclass
class _Result:
    # Explicit orchestration-only stub: no physical claims or typed API validation.
    status: str = "ready"
    contract_pass: bool = True
    checkpoint: bytes | None = b'{"stub":"checkpoint"}'

    def to_dict(self):
        return {
            "schema_version": "synthetic-cli-test.v1",
            "status": self.status,
            "contract_pass": self.contract_pass,
            "result_hash": self.result_hash,
            "metrics": {"response_reassembly_attempts": 2},
            "path": {
                "metrics": {
                    "requested_target_count": 2,
                    "attempted_target_count": 2,
                    "accepted_target_count": 1 if self.status == "blocked" else 2,
                    "failed_target_count": int(self.status == "blocked"),
                    "unattempted_target_count": 0,
                }
            },
        }

    @property
    def result_hash(self):
        return "sha256:" + hashlib.sha256(self.status.encode()).hexdigest()

    def result_artifact_bytes(self):
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode()

    def checkpoint_artifact_bytes(self):
        if self.checkpoint is None:
            raise ValueError("unavailable")
        return self.checkpoint


@dataclass
class _Validation:
    artifact_contract_pass: bool = True
    contract_pass: bool = True
    status: str = "verified"

    def to_dict(self):
        return {
            "status": self.status,
            "artifact_contract_pass": self.artifact_contract_pass,
            "contract_pass": self.contract_pass,
            "replay_control_work": {"attempted_step_count": 2},
        }


def _stubs(monkeypatch, result=None, validation=None):
    result = result or _Result()
    validation = validation or _Validation(contract_pass=result.contract_pass)
    calls = []

    def analyze(model, targets, **kwargs):
        calls.append(("analyze", model, targets, kwargs))
        return result

    def validate(model, targets, **kwargs):
        calls.append(("validate", model, targets, kwargs))
        return validation

    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", analyze)
    monkeypatch.setattr(
        cli.api, "validate_bounded_rc_fiber_direct_control_artifacts", validate
    )
    return result, validation, calls


@pytest.mark.parametrize(
    "status,passed,checkpoint",
    [
        ("ready", True, b"checkpoint"),
        ("blocked", False, b"partial checkpoint"),
        ("unsupported", False, None),
        ("invalid_execution", False, None),
        ("invalid_recovery", False, None),
    ],
)
def test_run_mandatory_source_validation_and_failed_status_accounting(
    tmp_path, monkeypatch, status, passed, checkpoint
):
    paths = _inputs(tmp_path)
    _old_outputs(paths)
    result, _, calls = _stubs(monkeypatch, _Result(status, passed, checkpoint))
    assert cli.main(_argv(paths)) == (0 if passed else 2)
    assert [row[0] for row in calls] == ["analyze", "validate"]
    assert calls[0][1] is calls[1][1] and calls[0][2] == calls[1][2]
    assert calls[1][3]["result"] == result.result_artifact_bytes()
    assert calls[1][3]["checkpoint"] == checkpoint
    assert calls[1][3]["config"] == calls[0][3]["config"]
    report = json.loads(paths["report"].read_bytes())
    assert report["analysis_status"] == status and report["contract_pass"] is passed
    assert report["verification"]["replay_control_work"]["attempted_step_count"] == 2
    assert report["analysis_control_accounting"] == result.to_dict()["path"]["metrics"]
    for key in (
        "analysis_api_timing",
        "verification_api_timing",
        "result_serialization_timing",
    ):
        assert report[key]["wall_ns"] >= 0 and report[key]["process_cpu_ns"] >= 0
    assert all(value is False for value in report["claims"].values())
    assert json.loads(paths["output"].read_bytes()) == result.to_dict()
    if checkpoint is None:
        assert not paths["checkpoint-output"].exists()
    else:
        assert paths["checkpoint-output"].read_bytes() == checkpoint


def test_verifier_rejection_writes_failed_receipt_without_checkpoint_authority(
    tmp_path, monkeypatch
):
    paths = _inputs(tmp_path)
    _old_outputs(paths)
    _stubs(monkeypatch, validation=_Validation(False, False, "mismatch"))
    assert cli.main(_argv(paths)) == 2
    report = json.loads(paths["report"].read_bytes())
    assert report["artifact_contract_pass"] is False
    assert not paths["checkpoint-output"].exists()


@pytest.mark.parametrize("physical_complete", [True, False])
def test_verify_checks_original_bytes_without_cli_analysis_and_separates_physical_status(
    tmp_path, monkeypatch, physical_complete
):
    paths = _inputs(tmp_path)
    paths["result"] = paths.pop("output")
    paths["checkpoint"] = paths.pop("checkpoint-output")
    paths["result"].write_bytes(b'{ "synthetic": true }\n')
    paths["checkpoint"].write_bytes(b"exact raw checkpoint")
    _, _, calls = _stubs(monkeypatch, validation=_Validation(True, physical_complete))
    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    assert cli.main(_argv(paths, "verify")) == 0
    assert [row[0] for row in calls] == ["validate"]
    assert calls[0][3]["result"] == paths["result"].read_bytes()
    assert calls[0][3]["checkpoint"] == paths["checkpoint"].read_bytes()
    report = json.loads(paths["report"].read_bytes())
    assert report["contract_pass"] is physical_complete
    assert report["analysis_api_timing"] is None


@pytest.mark.parametrize(
    "role,raw",
    [
        ("request", b'{"schema_version":1,"schema_version":2}'),
        ("model", b'{"nodes":[],"nodes":[]}'),
        ("model", b'{"value":NaN}'),
        ("request", b'{"x":1e999}'),
        ("request", b"\xff"),
    ],
)
def test_bad_bytes_reject_before_any_api_and_preserve_outputs(
    tmp_path, monkeypatch, role, raw
):
    paths = _inputs(tmp_path)
    old = _old_outputs(paths)
    paths[role].write_bytes(raw)
    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    monkeypatch.setattr(
        cli.api, "validate_bounded_rc_fiber_direct_control_artifacts", _forbid
    )
    with pytest.raises(SystemExit) as error:
        cli.main(_argv(paths))
    assert error.value.code == 2
    _assert_old(paths, old)


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink", "nested"])
def test_collision_preflight_before_reads_or_api(tmp_path, monkeypatch, alias):
    paths = _inputs(tmp_path)
    alias_path = tmp_path / "alias"
    if alias == "same":
        alias_path = paths["model"]
    elif alias == "symlink":
        alias_path.symlink_to(paths["model"])
    elif alias == "hardlink":
        alias_path.hardlink_to(paths["model"])
    else:
        alias_path = paths["model"] / "nested.json"
    paths["output"] = alias_path
    monkeypatch.setattr(cli, "_read_bounded", _forbid)
    with pytest.raises(SystemExit) as error:
        cli.main(_argv(paths))
    assert error.value.code == 2


@pytest.mark.parametrize("change", ["input_bytes", "output_symlink"])
def test_postexecution_rebinding_prevents_publication(tmp_path, monkeypatch, change):
    paths = _inputs(tmp_path)
    old = _old_outputs(paths)
    result, _, _ = _stubs(monkeypatch)
    other = tmp_path / "other.json"
    other.write_bytes(b"untouched")

    def analyze(*args, **kwargs):
        if change == "input_bytes":
            paths["model"].write_bytes(paths["model"].read_bytes() + b" ")
        else:
            paths["output"].unlink()
            paths["output"].symlink_to(other)
        return result

    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", analyze)
    with pytest.raises(SystemExit):
        cli.main(_argv(paths))
    assert paths["report"].read_bytes() == old["report"]
    assert paths["checkpoint-output"].read_bytes() == old["checkpoint-output"]
    assert other.read_bytes() == b"untouched"
    if change == "input_bytes":
        assert paths["output"].read_bytes() == old["output"]


def test_oversized_output_records_completed_work_without_relabeling_physics(
    tmp_path, monkeypatch
):
    paths = _inputs(tmp_path)
    old = _old_outputs(paths)
    _stubs(monkeypatch)
    monkeypatch.setattr(cli, "RESULT_MAX_BYTES", 4)
    monkeypatch.setattr(
        cli.api, "validate_bounded_rc_fiber_direct_control_artifacts", _forbid
    )
    assert cli.main(_argv(paths)) == 2
    report = json.loads(paths["report"].read_bytes())
    assert report["status"] == "output_limit_exceeded"
    assert (
        report["analysis_status"]
        == report["physical_result_status_unchanged"]
        == "ready"
    )
    assert report["analysis_control_accounting"]["attempted_target_count"] == 2
    assert report["verification_performed"] is False
    assert paths["output"].read_bytes() == old["output"]
    assert paths["checkpoint-output"].read_bytes() == old["checkpoint-output"]


def test_api_export_error_preserves_executed_work_without_replay_or_result_publication(
    tmp_path, monkeypatch
):
    paths = _inputs(tmp_path)
    old = _old_outputs(paths)
    metrics = {
        "control_work": {
            "attempted_step_count": 2,
            "known_linear_solve_count": 4,
            "unknown_solver_work_attempt_count": 0,
        },
        "response_reassembly_attempts": 2,
    }
    failure = cli.api.BoundedRCFiberDirectControlArtifactError(
        "declared output byte limit exceeded",
        {
            "model": {"synthetic": True},
            "request": {"synthetic": True},
            "status": "ready",
            "metrics": metrics,
        },
    )

    def analyze(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", analyze)
    monkeypatch.setattr(
        cli.api, "validate_bounded_rc_fiber_direct_control_artifacts", _forbid
    )
    assert cli.main(_argv(paths)) == 2
    report = json.loads(paths["report"].read_bytes())
    assert report["analysis_export_failure"] == failure.to_dict()
    assert report["analysis_metrics"] == metrics
    assert report["analysis_control_work"] == metrics["control_work"]
    assert report["physical_result_status_unchanged"] == "ready"
    assert report["status"] == "artifact_export_failed"
    assert (
        report["artifact_contract_pass"] is False
        and report["verification_performed"] is False
    )
    assert report["analysis_api_timing"]["wall_ns"] >= 0
    assert paths["output"].read_bytes() == old["output"]
    assert paths["checkpoint-output"].read_bytes() == old["checkpoint-output"]


def test_caught_output_replace_failure_rolls_back_bundle(tmp_path, monkeypatch):
    paths = _inputs(tmp_path)
    old = _old_outputs(paths)
    _stubs(monkeypatch)
    original = cli.output.os.replace
    failed = False

    def replace(source, target):
        nonlocal failed
        if Path(target) == paths["report"] and not failed:
            failed = True
            raise OSError("injected replacement failure")
        return original(source, target)

    monkeypatch.setattr(cli.output.os, "replace", replace)
    with pytest.raises(SystemExit):
        cli.main(_argv(paths))
    _assert_old(paths, old)
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize(
    "role,constant",
    [
        ("request", "REQUEST_MAX_BYTES"),
        ("model", "MODEL_MAX_BYTES"),
        ("restart", "CONTROL_RESTART_MAX_BYTES"),
    ],
)
def test_each_bounded_input_rejects_before_any_api(
    tmp_path, monkeypatch, role, constant
):
    paths = _inputs(tmp_path)
    old = _old_outputs(paths)
    if role == "restart":
        paths[role] = tmp_path / "restart.json"
        paths[role].write_bytes(b"five!")
    monkeypatch.setattr(cli, constant, 4)
    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    monkeypatch.setattr(
        cli.api, "validate_bounded_rc_fiber_direct_control_artifacts", _forbid
    )
    with pytest.raises(SystemExit):
        cli.main(_argv(paths))
    _assert_old(paths, old)


@pytest.mark.parametrize("role", ["result", "checkpoint"])
def test_verify_output_cannot_alias_its_original_artifact_inputs(
    tmp_path, monkeypatch, role
):
    paths = _inputs(tmp_path)
    paths["result"] = paths.pop("output")
    paths["checkpoint"] = paths.pop("checkpoint-output")
    paths["result"].write_bytes(b"{}")
    paths["checkpoint"].write_bytes(b"checkpoint")
    paths["report"] = paths[role]
    original = paths[role].read_bytes()
    monkeypatch.setattr(cli, "_read_bounded", _forbid)
    with pytest.raises(SystemExit):
        cli.main(_argv(paths, "verify"))
    assert paths[role].read_bytes() == original


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"{}     "])
def test_verify_malformed_or_oversized_result_does_not_replay(
    tmp_path, monkeypatch, raw
):
    paths = _inputs(tmp_path)
    paths["result"] = paths.pop("output")
    paths.pop("checkpoint-output")
    paths["result"].write_bytes(raw)
    paths["report"].write_bytes(b"old report")
    if raw == b"{}     ":
        monkeypatch.setattr(cli, "RESULT_MAX_BYTES", 4)
    monkeypatch.setattr(cli.api, "analyze_bounded_rc_fiber_direct_control", _forbid)
    monkeypatch.setattr(
        cli.api, "validate_bounded_rc_fiber_direct_control_artifacts", _forbid
    )
    with pytest.raises(SystemExit):
        cli.main(_argv(paths, "verify"))
    assert paths["report"].read_bytes() == b"old report"


def test_unrequested_checkpoint_output_is_not_removed(tmp_path, monkeypatch):
    paths = _inputs(tmp_path)
    checkpoint = paths.pop("checkpoint-output")
    checkpoint.write_bytes(b"unrequested old checkpoint")
    _stubs(monkeypatch, _Result("unsupported", False, None))
    assert cli.main(_argv(paths)) == 2
    assert checkpoint.read_bytes() == b"unrequested old checkpoint"


@pytest.fixture(scope="module")
def actual_cli():
    # Run only after root authorizes the ready API. One 2-target run+mandatory
    # validation, then verify: 3 API path invocations / 6 attempted control steps.
    workspace = Path(tempfile.mkdtemp(prefix="structural-rc-control-cli-integration-"))
    paths = _inputs(workspace)
    code = cli.main(_argv(paths))
    return workspace, paths, code


def test_actual_cli_run_and_verify_original_artifact_bytes(actual_cli):
    workspace, paths, code = actual_cli
    assert code == 0
    saved = {key: path.read_bytes() for key, path in paths.items()}
    verify = {
        "model": paths["model"],
        "request": paths["request"],
        "result": paths["output"],
        "checkpoint": paths["checkpoint-output"],
        "report": workspace / "verification.json",
    }
    assert cli.main(_argv(verify, "verify")) == 0
    assert {key: path.read_bytes() for key, path in paths.items()} == saved
    report = json.loads(verify["report"].read_bytes())
    assert report["artifact_contract_pass"] is True and report["contract_pass"] is True
    assert report["verification_performed"] is True
    assert report["analysis_performed_by_cli"] is False
