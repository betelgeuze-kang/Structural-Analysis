"""Summary refusal and identity checks require no numerical execution."""

import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "rc_learning_repetition_verifier",
    Path(__file__).resolve().parents[1] / "scripts/verify_rc_learning_repetitions.py",
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_live_bundle_cannot_produce_completed_summary(tmp_path):
    # No plan/inventory read is needed to reject the actual active-driver layout.
    (tmp_path / "driver-started.json").write_text('{"pid": 1234}')
    with pytest.raises(ValueError, match="driver is incomplete"):
        verifier.verify(tmp_path)


def test_repeating_one_worker_receipt_does_not_establish_fresh_processes(tmp_path):
    slots = [dict(id=name) for name in ["r1", "r2", "r3"]]
    (tmp_path / "plan.json").write_text(json.dumps(dict(slots=slots)))
    (tmp_path / "suite-outcome.json").write_text(
        json.dumps(
            dict(
                all_processes_exited=True,
                outcomes=[dict(slot_id=slot["id"], pid=1234) for slot in slots],
            )
        )
    )
    with pytest.raises(ValueError, match="distinct worker PIDs"):
        verifier.verify(tmp_path)


def test_live_pid_refuses_terminal_receipt():
    with pytest.raises(ValueError, match="still present"):
        verifier.terminal(dict(pid=verifier.os.getpid(), exit_code=0))


def test_changed_saved_cost_cannot_reuse_original_report_hash(tmp_path):
    payload = dict(whole_study_wall_ns=20)
    identity = "sha256:" + verifier.digest(verifier.encoded(payload))
    path = tmp_path / "report.json"
    path.write_text(json.dumps(dict(payload, report_hash=identity)))
    assert verifier.checked(path, "report_hash")["whole_study_wall_ns"] == 20
    path.write_text(json.dumps(dict(whole_study_wall_ns=1, report_hash=identity)))
    with pytest.raises(ValueError, match="hash differs"):
        verifier.checked(path, "report_hash")


def test_paired_dispersion_retains_slower_and_faster_samples():
    # Signed secant-minus-policy samples must not discard a losing repeat.
    result = verifier.distribution([-3.0, 1.0, 2.0])
    assert result["samples"] == [-3.0, 1.0, 2.0]
    assert result["median"] == 1.0
    assert result["minimum"] == -3.0
    assert result["sample_stdev"] == pytest.approx(7**0.5)


def timing_path():
    return dict(
        wall_ns=100,
        cpu_ns=90,
        entries=[
            dict(
                proposal_wall_ns=2,
                proposal_cpu_ns=1,
                recovery_wall_ns=4,
                recovery_cpu_ns=3,
                invocations=[
                    dict(committed=False, wall_ns=20, cpu_ns=15),
                    dict(committed=True, wall_ns=30, cpu_ns=25),
                ],
            )
        ],
    )


def test_nested_costs_include_rejected_attempt_without_adding_to_parent_time():
    result = verifier.path_timing_ns(timing_path())
    assert result == dict(
        path_wall_ns=100,
        path_cpu_ns=90,
        core_wall_ns=50,
        core_cpu_ns=40,
        proposal_wall_ns=2,
        proposal_cpu_ns=1,
        recovery_wall_ns=4,
        recovery_cpu_ns=3,
    )


@pytest.mark.parametrize("bad", [-1, True, 0.5])
def test_invalid_attempt_time_cannot_hide_in_a_positive_aggregate(bad):
    path = timing_path()
    path["entries"][0]["invocations"][0]["wall_ns"] = bad
    with pytest.raises(ValueError, match="integer measured timings"):
        verifier.path_timing_ns(path)
