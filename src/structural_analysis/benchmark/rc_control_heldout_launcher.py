"""Fresh-process slot observations, without a campaign or promotion decision.

Only explicitly supplied cases are loaded. The parent measures launch through
capture and exit once. Pre-start failures have separate attempt receipts: the
v1 lifecycle auditor cannot accept a launcher without an original started file.
"""

import argparse
from contextlib import contextmanager
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import perf_counter_ns

from structural_analysis.api.frame3d_direct_control_request import strict_json_object_bytes
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import rc_control_heldout_runtime as runtime
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_heldout_lifecycle_costs import (
    LAUNCHER_SCHEMA,
    MANIFEST_SCHEMA,
    audit_heldout_lifecycle_costs,
)
from structural_analysis.benchmark.rc_control_learning import RCControlLearningCase
from structural_analysis.benchmark.rc_control_process_costs import PROCESS_SCOPE
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


_SOURCE_ROOT = Path(__file__).resolve().parents[3]
_CASE_FIELDS = ("case_id", "project_id", "geometry_family_id", "load_history_id", "split")


def _seal(value, key):
    return {**value, key: _sha(_bytes(value))}


def _write(path, value):
    with path.open("xb") as stream:
        stream.write(_bytes(value))


def _reference(root, path):
    raw = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha(raw), "bytes": len(raw)}


def _plain_path(path):
    path = Path(os.path.abspath(path))
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("packet symlinks are not allowed")
    if path.is_relative_to(_SOURCE_ROOT):
        raise ValueError("packet must be outside the source checkout")
    return path


@contextmanager
def _packet_lock(root):
    # One writer, including separate processes. An interrupted parent leaves the
    # lock for explicit inspection; neither retries nor recovery are automatic.
    path = root / "launcher.lock"
    with path.open("x") as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        path.unlink()


def _case_payload(case):
    if type(case) is not RCControlLearningCase or case.measurement_source is not None:
        raise ValueError("typed cases without measured-workbook sources required")
    return {**{key: getattr(case, key) for key in _CASE_FIELDS},
            "model": case.model.to_dict(), "request": case.request.to_dict()}


def _decode_case(value):
    model = dict(value["model"])
    expected_hash = model.pop("canonical_model_checksum")
    model["units"] = UnitSystem(**model["units"])
    model["coordinate_system"] = CoordinateSystem(
        axis_order=tuple(model["coordinate_system"]["axis_order"]),
        up_axis=model["coordinate_system"]["up_axis"],
    )
    decoded = CanonicalModel(**model)
    if decoded.canonical_model_checksum != expected_hash:
        raise ValueError("serialized case model changed")
    return RCControlLearningCase(
        **{key: value[key] for key in _CASE_FIELDS}, model=decoded,
        request=decode_bounded_rc_fiber_direct_control_request(_bytes(value["request"])),
    )


def _child_command(input_path, output_path, input_hash):
    return [sys.executable, "-m", __name__, "--input", str(input_path),
            "--output", str(output_path), "--input-sha256", input_hash]


def _kill_and_wait(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        # The child may have exited after wait timed out. Still reap it and
        # retain the observed timeout without inventing a process-launch error.
        pass
    process.wait()


def _observe(command, stdout_path, stderr_path, timeout_seconds):
    """A single parent interval includes Popen, output capture, wait and close."""
    process = None
    failure = None
    timed_out = False
    start = perf_counter_ns()
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            try:
                process = subprocess.Popen(
                    command, cwd=_SOURCE_ROOT, stdout=stdout, stderr=stderr,
                    env={**os.environ, "PYTHONPATH": str(_SOURCE_ROOT / "src")},
                    start_new_session=True,
                )
                try:
                    process.wait(timeout=timeout_seconds)
                except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                    timed_out = isinstance(exc, subprocess.TimeoutExpired)
                    failure = None if timed_out else "KeyboardInterrupt"
                    _kill_and_wait(process)
            except OSError as exc:
                failure = type(exc).__name__
    finally:
        # A parent interruption must not leave a slot running unnoticed.
        if process is not None and process.poll() is None:
            _kill_and_wait(process)
        wall_ns = perf_counter_ns() - start
    return {
        "wall_ns": wall_ns, "cpu_ns": None, "scope": PROCESS_SCOPE,
        "child_pid": process.pid if process is not None else None,
        "return_code": process.returncode if process is not None else None,
        "launch_error": failure, "timed_out": timed_out,
    }


def launch_heldout_slot(
    plan, cases, selection, *, slot_index, packet_root, timeout_seconds=300,
):
    """Launch exactly one explicit slot and audit the whole declared denominator.

    No implicit case discovery, replacement, retries, training, or promotion.
    Existing packet manifests are audited before adding one original launcher.
    Attempt directories are exclusive, including attempts that never started.
    Measured workbook input transport is not supported by this first producer.
    """
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("finite positive timeout required")
    # Verify the immutable declaration before any filesystem or process effects.
    runtime.summarize_heldout_runtime(plan, {})
    if type(slot_index) is not int or not 0 <= slot_index < len(plan["schedule"]):
        raise ValueError("declared slot index required")
    if plan["selection_result_hash"] != selection.get("result_hash"):
        raise ValueError("development selection changed")
    policy = runtime._selected_policy(selection, plan["source_revision"])
    runtime._plan_assembly_reuse(plan, selection)
    if policy.policy_hash != plan["policy_hash"]:
        raise ValueError("selected policy changed")
    runtime._require_clean_source(plan["source_revision"])
    payload = {"plan": plan, "selection": selection, "slot_index": slot_index,
               "cases": [_case_payload(case) for case in cases]}
    root = _plain_path(packet_root)
    root.mkdir(parents=True, exist_ok=True)
    with _packet_lock(root):
        manifest_path = root / "lifecycle-manifest.json"
        if manifest_path.exists() or manifest_path.is_symlink():
            audit_heldout_launch_attempts(plan, root)
            manifest = runtime._read_receipt(manifest_path)
            manifest.pop("manifest_hash")
        else:
            manifest = {
                "schema_version": MANIFEST_SCHEMA, "plan_hash": plan["plan_hash"],
                "source_revision": plan["source_revision"],
                "selection_result_hash": plan["selection_result_hash"],
                "launchers": [], "selection_receipt": None, "label_receipts": [],
                "training_cost_reuse_count": plan["training_cost_reuse_assumption"],
            }
            _write(manifest_path, _seal(manifest, "manifest_hash"))
            audit_heldout_lifecycle_costs(plan, root)
        slot_path = root / f"slot-{slot_index:04d}"
        if slot_path.exists() or slot_path.is_symlink():
            raise ValueError("slot already exists; no replacement or retry")
        attempts = root / "launch-attempts"
        if attempts.is_symlink():
            raise ValueError("packet symlinks are not allowed")
        attempts.mkdir(exist_ok=True)
        attempt = attempts / f"slot-{slot_index:04d}"
        attempt.mkdir(exist_ok=False)
        input_path = attempt / "input.json"
        _write(input_path, payload)
        input_ref = _reference(root, input_path)
        stdout, stderr = attempt / "stdout.bin", attempt / "stderr.bin"
        command = _child_command(input_path, slot_path, input_ref["sha256"])
        observation = _observe(command, stdout, stderr, timeout_seconds)
        started_path, outcome_path = slot_path / "started.json", slot_path / "outcome.json"
        for path in (slot_path, started_path, outcome_path):
            if path.is_symlink():
                raise ValueError("original slot receipt symlink is not allowed")
        started_ref = _reference(root, started_path) if started_path.is_file() else None
        outcome_ref = _reference(root, outcome_path) if outcome_path.is_file() else None
        attempt_receipt = _seal({
            "schema_version": "rc-heldout-launch-attempt.v1",
            "plan_hash": plan["plan_hash"], "source_revision": plan["source_revision"],
            "slot": plan["schedule"][slot_index], "input": input_ref,
            **observation, "stdout": _reference(root, stdout),
            "stderr": _reference(root, stderr), "started": started_ref,
            "outcome": outcome_ref, "unknown_evaluation_cost": True,
            "net_benefit_proved": False,
        }, "attempt_hash")
        # Preserve costs even if the slot never wrote started.json. Such costs
        # cannot be admitted to the older v1 launcher sum and remain explicit.
        _write(attempt / "attempt.json", attempt_receipt)
        if started_ref is not None:
            started = runtime._read_receipt(started_path)
            if started.get("process_identity", [None])[0] != observation["child_pid"]:
                raise ValueError("original start differs from launched child PID")
            launcher = _seal({
                "schema_version": LAUNCHER_SCHEMA, "plan_hash": plan["plan_hash"],
                "source_revision": plan["source_revision"], "slot_index": slot_index,
                "process_identity": started["process_identity"],
                "started_file_sha256": started_ref["sha256"],
                "outcome_file_sha256": outcome_ref["sha256"] if outcome_ref else None,
                "return_code": observation["return_code"], "scope": PROCESS_SCOPE,
                "wall_ns": observation["wall_ns"], "cpu_ns": None,
            }, "launcher_hash")
            launcher_path = attempt / "launcher.json"
            _write(launcher_path, launcher)
            manifest["launchers"].append({"slot_index": slot_index,
                                         "file": _reference(root, launcher_path)})
        temporary = root / "lifecycle-manifest.pending.json"
        _write(temporary, _seal(manifest, "manifest_hash"))
        temporary.replace(manifest_path)
        audit = audit_heldout_launch_attempts(plan, root)
        return {"attempt": attempt_receipt, **audit}


def _check_reference(root, reference, expected):
    if (type(reference) is not dict
            or set(reference) != {"path", "sha256", "bytes"}
            or reference["path"] != expected
            or type(reference["bytes"]) is not int or reference["bytes"] < 0):
        raise ValueError("exact attempt original file reference required")
    path = root / expected
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("attempt original symlink is not allowed")
    if not path.is_file() or reference != _reference(root, path):
        raise ValueError("attempt original byte binding mismatch")
    return path


def audit_heldout_launch_attempts(plan, packet_root):
    """Reconcile all declared attempts, including costs absent from v1 launchers.

    Missing parent receipts remain unknown even if a child wrote its own files.
    These hashes provide integrity checks, not producer or clock attestation.
    """
    root = _plain_path(packet_root)
    if (root / "launch-attempts").is_symlink():
        raise ValueError("attempt original symlink is not allowed")
    lifecycle = audit_heldout_lifecycle_costs(plan, root)
    launchers = {row["slot_index"]: row for row in lifecycle["launcher_observations"]}
    rows = []
    for slot in plan["schedule"]:
        index = slot["slot_index"]
        prefix = f"launch-attempts/slot-{index:04d}"
        directory = root / prefix
        path = directory / "attempt.json"
        if directory.is_symlink() or path.is_symlink():
            raise ValueError("attempt original symlink is not allowed")
        if not path.is_file():
            rows.append({"slot_index": index, "status": "missing_parent_receipt",
                         "wall_ns": None, "included_in_v1_launcher_sum": index in launchers})
            continue
        value = runtime._read_receipt(path)
        unhashed = {key: item for key, item in value.items() if key != "attempt_hash"}
        if (value.get("attempt_hash") != _sha(_bytes(unhashed))
                or value.get("schema_version") != "rc-heldout-launch-attempt.v1"
                or value.get("plan_hash") != plan["plan_hash"]
                or value.get("source_revision") != plan["source_revision"]
                or value.get("slot") != slot
                or value.get("scope") != PROCESS_SCOPE
                or type(value.get("wall_ns")) is not int or value["wall_ns"] <= 0
                or value.get("cpu_ns") is not None
                or type(value.get("timed_out")) is not bool
                or value.get("unknown_evaluation_cost") is not True
                or value.get("net_benefit_proved") is not False):
            raise ValueError("invalid source-bound attempt observation")
        if value["child_pid"] is None:
            if value["return_code"] is not None or type(value["launch_error"]) is not str:
                raise ValueError("invalid failed launch observation")
        elif (type(value["child_pid"]) is not int or value["child_pid"] <= 0
              or type(value["return_code"]) is not int):
            raise ValueError("invalid child exit observation")
        input_path = _check_reference(root, value["input"], prefix + "/input.json")
        inputs = runtime._read_receipt(input_path)
        if (inputs.get("plan") != plan or inputs.get("slot_index") != index
                or inputs.get("selection", {}).get("result_hash") != plan["selection_result_hash"]):
            raise ValueError("attempt input differs from frozen plan")
        for name in ("stdout", "stderr"):
            _check_reference(root, value[name], prefix + f"/{name}.bin")
        for name in ("started", "outcome"):
            expected = f"slot-{index:04d}/{name}.json"
            if value[name] is not None:
                _check_reference(root, value[name], expected)
            elif (root / expected).exists() or (root / expected).is_symlink():
                raise ValueError("unbound original slot receipt")
        included = index in launchers
        if value["started"] is None:
            if included or value["outcome"] is not None:
                raise ValueError("pre-start failure cannot have a v1 launcher")
        else:
            started = runtime._read_receipt(root / value["started"]["path"])
            if (not included or started["process_identity"][0] != value["child_pid"]
                    or launchers[index]["wall_ns"] != value["wall_ns"]
                    or launchers[index]["return_code"] != value["return_code"]):
                raise ValueError("attempt and v1 launcher differ")
        rows.append({"slot_index": index, "status": "observed",
                     "wall_ns": value["wall_ns"], "return_code": value["return_code"],
                     "timed_out": value["timed_out"], "launch_error": value["launch_error"],
                     "included_in_v1_launcher_sum": included,
                     "attempt_file_sha256": _sha(path.read_bytes())})
    observed = sum(row["wall_ns"] or 0 for row in rows)
    complete = all(row["wall_ns"] is not None for row in rows)
    return {"lifecycle_audit": lifecycle, "attempt_audit": {
        "schema_version": "rc-heldout-launch-attempt-audit.v1",
        "plan_hash": plan["plan_hash"], "declared_denominator": len(plan["schedule"]),
        "slots": rows, "parent_receipts_complete": complete,
        "observed_attempt_wall_ns_sum": observed,
        "all_declared_attempt_wall_ns_sum": observed if complete else None,
        "observed_wall_ns_absent_from_v1_launcher_sum": sum(
            row["wall_ns"] or 0 for row in rows if not row["included_in_v1_launcher_sum"]),
        "attempt_intervals_replace_v1_launcher_intervals": True,
        "intervals_are_campaign_elapsed_time": False,
        "producer_and_clock_authenticated": False,
        "actual_total_evaluation_wall_ns": None, "unknown_evaluation_cost": True,
        "lifecycle_costs_audited": False, "net_benefit_proved": False,
        "selected_strategy": "secant",
    }}


def _child(input_path, output_path, input_hash):
    raw = input_path.read_bytes()
    if _sha(raw) != input_hash:
        raise ValueError("launcher input bytes changed")
    # Parse the bytes whose digest was checked, never reopen the mutable path.
    value = strict_json_object_bytes(raw, maximum_bytes=64 * 1024 * 1024)
    outcome = runtime.run_heldout_slot(
        value["plan"], [_decode_case(case) for case in value["cases"]],
        value["selection"], slot_index=value["slot_index"], output_directory=output_path,
    )
    return 0 if outcome["status"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args()
    return _child(args.input, args.output, args.input_sha256)


if __name__ == "__main__":
    sys.exit(main())
