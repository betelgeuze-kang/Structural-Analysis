"""Real subprocess development checks; no reserved evaluation packet is loaded."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import time

import pytest

from structural_analysis.benchmark import rc_control_heldout_launcher as launcher
from structural_analysis.benchmark import rc_control_heldout_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from tests.test_rc_control_heldout_runtime import plan, selected
from tests.test_rc_control_runtime_selection import original as runtime_original


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    return runtime_original.__wrapped__(tmp_path_factory)


@pytest.fixture
def development(source, tmp_path, monkeypatch):
    # Only this synthetic fixture bypasses clean-source validation. The real
    # entrypoint and source guard are separately exercised below.
    monkeypatch.setattr(runtime, "_require_clean_source", lambda _: None)
    return source, plan(source), tmp_path / "packet"


def _launch(development, slot_index=0, *, reuse_assembly=False, **kwargs):
    source, frozen, root = development
    return launcher.launch_heldout_slot(
        frozen, source[0], selected(source, reuse_assembly=reuse_assembly), slot_index=slot_index,
        packet_root=root, **kwargs,
    )


def _driver(monkeypatch, code):
    monkeypatch.setattr(launcher, "_child_command", lambda input_path, output, digest:
                        [sys.executable, "-c", code, str(input_path), str(output), digest])


_REAL_DEVELOPMENT_CHILD = '''
import sys
from pathlib import Path
from structural_analysis.benchmark import rc_control_heldout_launcher as launch
launch.runtime._require_clean_source = lambda _: None
print("original stdout", flush=True)
print("original stderr", file=sys.stderr, flush=True)
raise SystemExit(launch._child(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))
'''


_STARTED_CHILD = '''
import os, sys, time
from pathlib import Path
from structural_analysis.benchmark import rc_control_heldout_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes
value = runtime._read_receipt(Path(sys.argv[1]))
root = Path(sys.argv[2]); root.mkdir()
slot = value["plan"]["schedule"][value["slot_index"]]
started = {"plan_hash": value["plan"]["plan_hash"], "slot": slot,
           "process_identity": [os.getpid(), time.time_ns()],
           "status": "started", "unknown_work_until_outcome": True}
(root / "started.json").write_bytes(_bytes(started))
print("before exit", flush=True)
'''


@pytest.mark.parametrize("reuse_assembly", [False, True])
def test_actual_full_path_child_binds_original_bytes_and_preserves_missing_slots(
    development, monkeypatch, reuse_assembly,
):
    source, _, root = development
    development = source, plan(source, reuse_assembly=reuse_assembly), root
    _driver(monkeypatch, _REAL_DEVELOPMENT_CHILD)
    result = _launch(development, reuse_assembly=reuse_assembly)
    _, frozen, root = development
    attempt = result["attempt"]
    assert attempt["return_code"] == 0
    assert attempt["child_pid"] != __import__("os").getpid()
    assert (root / attempt["stdout"]["path"]).read_bytes() == b"original stdout\n"
    assert (root / attempt["stderr"]["path"]).read_bytes() == b"original stderr\n"
    assert attempt["started"]["sha256"] == _sha((root / "slot-0000/started.json").read_bytes())
    outcome = runtime._read_receipt(root / "slot-0000/outcome.json")
    assert outcome["status"] == "completed"
    report = runtime._read_receipt(root / "slot-0000/benchmark/comparison.json")
    assert ("line_search_assembly_reuse" in report) is reuse_assembly
    assert all(row["full_history_pass"] for row in report["comparisons"].values())
    assert attempt["wall_ns"] >= outcome["wall_ns"]
    assert attempt["cpu_ns"] is None
    costs = result["lifecycle_audit"]
    assert costs["declared_denominator"] == 3
    assert costs["original_slot_audit"]["unknown_or_missing_slots"] == 2
    assert costs["all_declared_launcher_wall_ns_sum"] is None
    assert result["attempt_audit"]["observed_attempt_wall_ns_sum"] == attempt["wall_ns"]
    assert result["attempt_audit"]["observed_wall_ns_absent_from_v1_launcher_sum"] == 0
    assert costs["actual_total_evaluation_wall_ns"] is None
    assert not costs["net_benefit_proved"]
    assert costs["selected_strategy"] == "secant"
    with pytest.raises(ValueError, match="no replacement"):
        _launch(development, reuse_assembly=reuse_assembly)
    changed = root / attempt["stdout"]["path"]
    changed.write_bytes(b"changed stdout")
    with pytest.raises(ValueError, match="byte binding"):
        launcher.audit_heldout_launch_attempts(frozen, root)


def test_child_rejection_before_start_keeps_measured_cost_and_all_slots(development):
    # Actual fixed module command; fake fixture revision fails child clean-source
    # admission before started.json. The parent still measures and saves its exit.
    result = _launch(development)
    _, frozen, root = development
    assert result["attempt"]["return_code"] != 0
    assert result["attempt"]["started"] is None
    assert result["attempt"]["wall_ns"] > 0
    assert result["lifecycle_audit"]["original_slot_audit"]["unknown_or_missing_slots"] == 3
    assert result["lifecycle_audit"]["observed_launcher_wall_ns_sum"] == 0
    audit = result["attempt_audit"]
    assert audit["observed_wall_ns_absent_from_v1_launcher_sum"] == result["attempt"]["wall_ns"]
    assert audit["all_declared_attempt_wall_ns_sum"] is None
    with pytest.raises(FileExistsError):
        _launch(development)
    attempt_path = root / "launch-attempts/slot-0000/attempt.json"
    receipt = runtime._read_receipt(attempt_path)
    receipt["source_revision"] = "b" * 40
    receipt.pop("attempt_hash")
    attempt_path.write_bytes(_bytes(launcher._seal(receipt, "attempt_hash")))
    with pytest.raises(ValueError, match="source-bound"):
        launcher.audit_heldout_launch_attempts(frozen, root)


def test_popen_failure_is_not_dropped(development, monkeypatch):
    monkeypatch.setattr(launcher, "_child_command", lambda *_: ["/nonexistent/rc-python"])
    result = _launch(development)
    attempt = result["attempt"]
    assert attempt["child_pid"] is None
    assert attempt["return_code"] is None
    assert attempt["launch_error"] == "FileNotFoundError"
    assert result["attempt_audit"]["observed_attempt_wall_ns_sum"] == attempt["wall_ns"] > 0
    assert not result["lifecycle_audit"]["launcher_exits_successful"]


def test_nonzero_exit_after_start_keeps_original_interrupted_receipt(development, monkeypatch):
    _driver(monkeypatch, _STARTED_CHILD + "raise SystemExit(7)\n")
    result = _launch(development)
    assert result["attempt"]["return_code"] == 7
    assert result["attempt"]["outcome"] is None
    assert result["lifecycle_audit"]["original_slot_audit"]["slots"][0]["status"] == "interrupted"
    assert result["lifecycle_audit"]["observed_launcher_wall_ns_sum"] > 0
    assert not result["lifecycle_audit"]["launcher_exits_successful"]


def test_timeout_kills_child_and_includes_final_capture(development, monkeypatch):
    _driver(monkeypatch, _STARTED_CHILD + "time.sleep(60)\n")
    result = _launch(development, timeout_seconds=2)
    assert result["attempt"]["timed_out"]
    assert result["attempt"]["return_code"] == -9
    assert result["attempt"]["wall_ns"] >= 2_000_000_000
    root = development[2]
    assert (root / result["attempt"]["stdout"]["path"]).read_bytes() == b"before exit\n"
    assert result["lifecycle_audit"]["original_slot_audit"]["unknown_or_missing_slots"] == 3


def test_single_parent_interval_encloses_stdout_stderr_and_exit(tmp_path, monkeypatch):
    times = []
    def clock():
        times.append(time.perf_counter_ns())
        return times[-1]
    monkeypatch.setattr(launcher, "perf_counter_ns", clock)
    stdout, stderr = tmp_path / "stdout", tmp_path / "stderr"
    observed = launcher._observe(
        [sys.executable, "-c", 'import sys,time; time.sleep(.05); print("out"); print("err",file=sys.stderr)'],
        stdout, stderr, 5,
    )
    assert len(times) == 2
    assert observed["wall_ns"] == times[1] - times[0] >= 50_000_000
    assert stdout.read_bytes() == b"out\n"
    assert stderr.read_bytes() == b"err\n"
    assert observed["return_code"] == 0
    assert observed["cpu_ns"] is None


def test_parent_rejects_mutation_and_source_before_launch(source, tmp_path):
    frozen = plan(source)
    with pytest.raises(ValueError, match="exact clean committed"):
        launcher.launch_heldout_slot(frozen, source[0], selected(source), slot_index=0,
                                     packet_root=tmp_path / "packet")
    assert not (tmp_path / "packet").exists()
    frozen["source_revision"] = "b" * 40
    with pytest.raises(ValueError, match="plan hash"):
        launcher.launch_heldout_slot(frozen, source[0], selected(source), slot_index=0,
                                     packet_root=tmp_path / "packet")


def test_transport_roundtrip_and_changed_model_rejected(source):
    payload = launcher._case_payload(source[0][0])
    decoded = launcher._decode_case(payload)
    assert decoded.model.canonical_model_checksum == source[0][0].model.canonical_model_checksum
    assert decoded.request.to_dict() == source[0][0].request.to_dict()
    changed = deepcopy(payload)
    changed["model"]["canonical_model_checksum"] = _sha(b"different")
    with pytest.raises(ValueError, match="serialized case"):
        launcher._decode_case(changed)


def test_symlink_and_existing_lock_prevent_launch(development, tmp_path):
    root = development[2]
    root.symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        _launch(development)
    root.unlink()
    root.mkdir()
    (root / "launcher.lock").write_text("existing writer")
    with pytest.raises(FileExistsError):
        _launch(development)
    assert (root / "launcher.lock").read_text() == "existing writer"
    assert not (root / "launch-attempts").exists()


def test_missing_parent_receipt_remains_unknown(development, monkeypatch):
    _driver(monkeypatch, "raise SystemExit(2)")
    _launch(development)
    _, frozen, root = development
    (root / "launch-attempts/slot-0000/attempt.json").unlink()
    audited = launcher.audit_heldout_launch_attempts(frozen, root)["attempt_audit"]
    assert audited["declared_denominator"] == 3
    assert audited["slots"][0]["status"] == "missing_parent_receipt"
    assert not audited["parent_receipts_complete"]
    assert audited["all_declared_attempt_wall_ns_sum"] is None


def test_raised_original_outcome_is_preserved_and_exits_nonzero(development, monkeypatch):
    code = _REAL_DEVELOPMENT_CHILD.replace(
        'print("original stdout", flush=True)',
        'def fail(*args, **kwargs): raise RuntimeError("synthetic failure")\n'
        'launch.runtime.learning.benchmark_rc_control_seed_paths = fail\n'
        'print("original stdout", flush=True)',
    )
    _driver(monkeypatch, code)
    result = _launch(development)
    assert result["attempt"]["return_code"] == 1
    assert result["attempt"]["outcome"] is not None
    audit = result["lifecycle_audit"]
    assert audit["original_slot_audit"]["slots"][0]["status"] == "raised"
    assert audit["original_slot_audit"]["failed_or_ineligible_slots"] == 3
    assert not audit["launcher_exits_successful"]


def test_timeout_before_start_preserves_cost_outside_v1_sum(development, monkeypatch):
    _driver(monkeypatch, 'import time; print("starting", flush=True); time.sleep(60)')
    result = _launch(development, timeout_seconds=.2)
    assert result["attempt"]["timed_out"]
    assert result["attempt"]["started"] is None
    assert result["attempt"]["return_code"] == -9
    assert result["attempt_audit"]["observed_wall_ns_absent_from_v1_launcher_sum"] > 0
    assert not result["lifecycle_audit"]["launcher_observations_complete"]


def test_all_failed_attempts_keep_complete_attempt_cost_but_no_lifecycle_claim(
    development, monkeypatch,
):
    _driver(monkeypatch, 'raise SystemExit(9)')
    observations = [_launch(development, index) for index in range(3)]
    final = observations[-1]
    expected = sum(row["attempt"]["wall_ns"] for row in observations)
    assert final["attempt_audit"]["declared_denominator"] == 3
    assert final["attempt_audit"]["all_declared_attempt_wall_ns_sum"] == expected
    assert final["attempt_audit"]["observed_wall_ns_absent_from_v1_launcher_sum"] == expected
    assert final["lifecycle_audit"]["all_declared_launcher_wall_ns_sum"] is None
    assert final["lifecycle_audit"]["original_slot_audit"]["failed_or_ineligible_slots"] == 3
    assert not final["attempt_audit"]["net_benefit_proved"]
    assert final["attempt_audit"]["actual_total_evaluation_wall_ns"] is None


def test_attempt_and_v1_timing_cannot_diverge_after_resealing(development, monkeypatch):
    _driver(monkeypatch, _STARTED_CHILD + "raise SystemExit(7)\n")
    _launch(development)
    _, frozen, root = development
    path = root / "launch-attempts/slot-0000/attempt.json"
    receipt = runtime._read_receipt(path)
    receipt.pop("attempt_hash")
    receipt["wall_ns"] += 100
    path.write_bytes(_bytes(launcher._seal(receipt, "attempt_hash")))
    with pytest.raises(ValueError, match="attempt and v1 launcher differ"):
        launcher.audit_heldout_launch_attempts(frozen, root)
    with pytest.raises(ValueError, match="attempt and v1 launcher differ"):
        _launch(development, 1)
    assert not (root / "launch-attempts/slot-0001").exists()


def test_child_executes_only_the_single_hash_checked_input(tmp_path, monkeypatch):
    original = {"plan": {"identity": "original"}, "cases": [],
                "selection": {}, "slot_index": 0}
    replacement = {**original, "plan": {"identity": "replacement"}}
    path = tmp_path / "input.json"
    raw = _bytes(original)
    path.write_bytes(raw)
    read_bytes = Path.read_bytes
    reads = []
    executed = []

    def swap_after_read(self):
        observed = read_bytes(self)
        if self == path:
            reads.append(observed)
            self.write_bytes(_bytes(replacement))
        return observed

    def run(plan, *args, **kwargs):
        executed.append(plan)
        return {"status": "completed"}

    monkeypatch.setattr(Path, "read_bytes", swap_after_read)
    monkeypatch.setattr(runtime, "run_heldout_slot", run)
    assert launcher._child(path, tmp_path / "slot-0000", _sha(raw)) == 0
    assert reads == [raw]
    assert executed == [original["plan"]]
    assert read_bytes(path) == _bytes(replacement)


@pytest.mark.parametrize("raw", [b'{"plan": {}, "plan": {}}', b'{"plan": NaN}'])
def test_child_hash_match_does_not_admit_duplicate_or_nonfinite_json(tmp_path, monkeypatch, raw):
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    monkeypatch.setattr(runtime, "run_heldout_slot", lambda *args, **kwargs: pytest.fail("must not execute"))
    with pytest.raises(ValueError, match="invalid JSON object"):
        launcher._child(path, tmp_path / "slot-0000", _sha(raw))


def test_child_hash_mismatch_never_executes(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_bytes(b'{"changed": true}')
    monkeypatch.setattr(runtime, "run_heldout_slot", lambda *args, **kwargs: pytest.fail("must not execute"))
    with pytest.raises(ValueError, match="input bytes changed"):
        launcher._child(path, tmp_path / "slot-0000", _sha(b"original"))


def test_child_exiting_during_timeout_kill_is_reaped_without_launch_error(tmp_path, monkeypatch):
    class ExitingChild:
        pid = 123
        returncode = None
        calls = 0

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("synthetic-child", timeout)
            self.returncode = 0
            return self.returncode

        def poll(self):
            return self.returncode

    child = ExitingChild()
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: child)
    def already_exited(*args):
        raise ProcessLookupError("child exited after timeout")
    monkeypatch.setattr(launcher.os, "killpg", already_exited)
    observed = launcher._observe(["synthetic-child"], tmp_path / "stdout", tmp_path / "stderr", .1)
    assert child.calls == 2
    assert observed["return_code"] == 0
    assert observed["timed_out"] is True
    assert observed["launch_error"] is None
    assert observed["wall_ns"] > 0


@pytest.mark.parametrize("downgrade", [False, True])
def test_parent_rejects_selected_profile_mismatch_before_packet_creation(source, tmp_path, downgrade):
    choice = selected(source, reuse_assembly=True)
    frozen = plan(source, reuse_assembly=True)
    if downgrade:
        frozen["schema_version"] = "rc-heldout-runtime-plan.v1"
        frozen.pop("execution_profile")
    else:
        frozen["execution_profile"]["reuse_line_search_assembly"] = False
    frozen["plan_hash"] = _sha(_bytes({
        k: v for k, v in frozen.items() if k != "plan_hash"
    }))
    root = tmp_path / "packet"
    with pytest.raises(ValueError, match="execution profile differs"):
        launcher.launch_heldout_slot(
            frozen, source[0], choice, slot_index=0, packet_root=root,
        )
    assert not root.exists()
