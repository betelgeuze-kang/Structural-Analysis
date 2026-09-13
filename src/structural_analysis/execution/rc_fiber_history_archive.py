"""Experimental RC histories with per-step artifacts and full-prefix replay.

This local archive is separate from the bounded v1 API and durable HTTP transport.
Only the original solver accepts states. Resume recomputes every stored step;
artifact hashes do not establish physical reachability or independent validation.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from tempfile import mkdtemp
from time import perf_counter_ns
from uuid import uuid4

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control import _recover_step
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    _counts,
    _directions,
    _execute_raw,
    _integer,
    _json,
    _targets,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    StatefulFiberFrame2DDisplacementControlStepAdapter,
)
from structural_analysis.model.schema import CanonicalModel


PROFILE = "experimental-rc-fiber-history-archive.v1"
MAX_TARGETS = 16384
MAX_ENTRY_BYTES = 64 * 1024 * 1024
CLAIMS = {
    "experimental_small_displacement_rc_control": True,
    "source_revision_is_caller_attestation": True,
    "independent_physical_validation": False,
    "hashes_authenticate_execution": False,
    "learned_policy_used": False,
    "durable_http_integration": False,
    "workbench_integration": False,
    "performance_improvement": False,
    "release_approval": False,
}


def _hash(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _publish_raw(path, raw):
    if len(raw) > MAX_ENTRY_BYTES:
        raise ValueError("archive entry exceeds byte bound")
    temporary = path.parent / (".pending-" + uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic, exclusive publication: a concurrent writer cannot overwrite
        # a previously accepted step or its original invocation outcome.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _publish(path, payload):
    document = payload | {"artifact_hash": _hash(_json(payload))}
    _publish_raw(path, _json(document))
    return document


def _read(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("archive entries cannot be symbolic links")
    with path.open("rb") as stream:
        raw = stream.read(MAX_ENTRY_BYTES + 1)
    document = strict_json_object_bytes(raw, maximum_bytes=MAX_ENTRY_BYTES)
    payload = dict(document)
    digest = payload.pop("artifact_hash", None)
    if digest != _hash(_json(payload)) or raw != _json(document):
        raise ValueError("archive canonical entry/hash mismatch")
    return document


def run_rc_fiber_history_archive(
    model,
    targets_m,
    *,
    control_global_dof,
    output_directory,
    source_revision,
    config=None,
    allow_reversals=False,
    maximum_reversals=0,
    maximum_targets=MAX_TARGETS,
    resume=False,
    stop_after=None,
):
    """Execute authored targets without retaining a cumulative response payload.

    ``stop_after`` limits newly accepted targets, after complete prefix replay.
    Zero explicitly verifies a stored prefix without adding targets. Every new
    invocation creates a run ledger, including replay and failed/unknown work.
    An interrupted run is never inferred to have completed from a started file.
    Concurrent accepted publication fails exclusively; callers serialize runs.
    """
    invocation_start = perf_counter_ns()
    if type(model) is not CanonicalModel or type(resume) is not bool:
        raise ValueError("exact canonical model and boolean resume required")
    if not isinstance(source_revision, str) or not re.fullmatch(
        "[0-9a-f]{40}", source_revision
    ):
        raise ValueError("explicit source revision required")
    _integer(maximum_targets, "maximum_targets", MAX_TARGETS, 1)
    _integer(maximum_reversals, "maximum_reversals", maximum_targets - 1)
    _integer(control_global_dof, "control_global_dof", 47)
    if control_global_dof % 3 not in (0, 1):
        raise ValueError("translational control DOF required")
    if type(allow_reversals) is not bool or (not allow_reversals and maximum_reversals):
        raise ValueError("explicit reversal opt-in and budget required")
    if stop_after is not None:
        _integer(stop_after, "stop_after", maximum_targets)
    targets = _targets(targets_m, maximum_targets)
    if not targets:
        raise ValueError("complete nonempty authored target sequence required")
    _, reversals = _directions(targets)
    if reversals > maximum_reversals:
        raise ValueError("complete sequence exceeds reversal budget")
    cfg = (
        config
        if config is not None
        else StatefulFiberFrame2DDisplacementControlConfig()
    )
    if type(cfg) is not StatefulFiberFrame2DDisplacementControlConfig:
        raise ValueError("exact solver configuration required")
    snapshot = model.detached_analysis_snapshot()
    compiled, unsupported, _ = _compile(snapshot)
    if compiled is None or unsupported:
        raise ValueError("supported canonical RC model required")
    problem = compiled.problem
    parent = initial_stateful_fiber_frame2d_checkpoint(problem)
    StatefulFiberFrame2DDisplacementControlStepAdapter(
        problem, parent, control_global_dof, targets[0], cfg
    )
    manifest = {
        "profile": PROFILE,
        "model": snapshot.to_dict(),
        "source_revision": source_revision,
        "problem_contract_hash": problem.contract_hash,
        "configuration": cfg.to_manifest(),
        "configuration_hash": cfg.contract_hash,
        "control_global_dof": control_global_dof,
        "targets_m": list(targets),
        "allow_reversals": allow_reversals,
        "maximum_reversals": maximum_reversals,
        "maximum_targets": maximum_targets,
        "claims": CLAIMS,
    }
    root = Path(output_directory)
    if root.is_symlink():
        raise ValueError("archive root cannot be a symbolic link")
    if resume:
        original = _read(root / "manifest.json")
        if _json(original) != _json(
            manifest | {"artifact_hash": _hash(_json(manifest))}
        ):
            raise ValueError("archive model/request/source identity changed")
    else:
        root.mkdir(parents=True, exist_ok=False)
        (root / "accepted").mkdir()
        (root / "runs").mkdir()
        original = _publish(root / "manifest.json", manifest)
    if (root / "accepted").is_symlink() or (root / "runs").is_symlink():
        raise ValueError("archive directories cannot be symbolic links")
    # An interrupted exclusive publication can leave its private temporary
    # file. It has no accepted index and is retained, never promoted or deleted.
    accepted_files = sorted(
        path
        for path in (root / "accepted").iterdir()
        if not re.fullmatch(r"\.pending-[0-9a-f]{32}", path.name)
    )
    if [path.name for path in accepted_files] != [
        f"{i:05d}.json" for i in range(len(accepted_files))
    ]:
        raise ValueError("accepted archive must be a consecutive prefix")
    prefix_count = len(accepted_files)
    if prefix_count > len(targets):
        raise ValueError("archive exceeds declared history")
    end = (
        len(targets)
        if stop_after is None
        else min(len(targets), prefix_count + stop_after)
    )
    run = Path(mkdtemp(prefix="run-", dir=root / "runs"))
    preflight_wall_ns = perf_counter_ns() - invocation_start
    _publish(
        run / "started.json",
        {
            "manifest_hash": original["artifact_hash"],
            "prefix_count": prefix_count,
            "requested_end": end,
            "preflight_wall_ns": preflight_wall_ns,
        },
    )
    start = perf_counter_ns()
    work = {phase: _counts(()) for phase in ("prefix_replay", "suffix")}
    unknown = []
    verified = 0
    failure = None
    core_wall_ns = recovery_wall_ns = 0
    for index, target in enumerate(targets[:end]):
        phase = "prefix_replay" if index < prefix_count else "suffix"
        stem = f"{phase}-{index:05d}"
        _publish(
            run / (stem + "-started.json"),
            {
                "manifest_hash": original["artifact_hash"],
                "target_index": index,
                "target_m": target,
                "parent_hash": parent.state_hash,
                "unknown_solver_work_until_outcome": True,
            },
        )
        core_start = perf_counter_ns()
        try:
            child, steps, attempts = _execute_raw(
                problem,
                parent,
                (target,),
                control_global_dof,
                cfg,
                manifest["problem_contract_hash"],
                phase=phase,
            )
        except Exception as exc:
            core_wall_ns += perf_counter_ns() - core_start
            failure = {
                "stage": "core_execution",
                "kind": type(exc).__name__,
                "index": index,
            }
            details = exc.to_dict() if hasattr(exc, "to_dict") else None
            unknown.append({"phase": phase, "index": index})
            _publish(
                run / (stem + "-failure.json"),
                failure | {"details": details, "unknown_solver_work": True},
            )
            break
        elapsed = perf_counter_ns() - core_start
        core_wall_ns += elapsed
        for key, value in _counts(attempts).items():
            work[phase][key] += value
        outcome_path = run / (stem + "-outcome.json")
        outcome = _publish(
            outcome_path, {"attempts": attempts, "core_wall_ns": elapsed}
        )
        if len(steps) != 1 or not steps[0].committed:
            failure = {"stage": "unaccepted_step", "index": index}
            break
        recovery_start = perf_counter_ns()
        try:
            child, response = _recover_step(
                compiled,
                parent,
                steps[0],
                cfg,
                control_global_dof,
                target,
                manifest["problem_contract_hash"],
            )
            if phase == "prefix_replay":
                saved = _read(accepted_files[index])
                relative = saved["outcome_path"]
                if not re.fullmatch(
                    r"runs/run-[A-Za-z0-9_]+/suffix-[0-9]{5}-outcome\.json", relative
                ):
                    raise ValueError("invalid original outcome path")
                previous = _read(root / relative)
                if (
                    saved["manifest_hash"] != original["artifact_hash"]
                    or saved["target_index"] != index
                    or saved["target_m"] != target
                    or saved["outcome_hash"] != previous["artifact_hash"]
                    or _json(previous["attempts"]) != _json(attempts)
                    or _json(saved["response"]) != _json(response)
                ):
                    raise ValueError(
                        "full-prefix original step/response replay mismatch"
                    )
            else:
                _publish(
                    root / "accepted" / f"{index:05d}.json",
                    {
                        "manifest_hash": original["artifact_hash"],
                        "target_index": index,
                        "target_m": target,
                        "outcome_path": outcome_path.relative_to(root).as_posix(),
                        "outcome_hash": outcome["artifact_hash"],
                        "response": response,
                    },
                )
        except Exception as exc:
            failure = {
                "stage": "recovery_or_prefix_verification",
                "kind": type(exc).__name__,
                "index": index,
            }
            break
        finally:
            recovered_ns = perf_counter_ns() - recovery_start
            recovery_wall_ns += recovered_ns
        _publish(
            run / (stem + "-verified.json"),
            {
                "response_hash": _hash(_json(response)),
                "accepted_checkpoint_hash": child.state_hash,
                "recovery_wall_ns": recovered_ns,
            },
        )
        parent = child
        verified += 1
    checkpoint = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, parent)
    _publish_raw(run / "verified-terminal-checkpoint.json", checkpoint)
    return _publish(
        run / "result.json",
        {
            "profile": PROFILE,
            "manifest_hash": original["artifact_hash"],
            "status": "blocked"
            if failure
            else "complete"
            if verified == len(targets)
            else "paused",
            "complete": failure is None and verified == len(targets),
            "prefix_count_before": prefix_count,
            "verified_target_count": verified,
            "failure": failure,
            "work": work,
            "unavailable_core_invocations": unknown,
            "checkpoint_sha256": _hash(checkpoint),
            "checkpoint_epoch": parent.epoch,
            "run_directory": run.name,
            "run_wall_ns": perf_counter_ns() - start,
            "preflight_wall_ns": preflight_wall_ns,
            "invocation_wall_ns_before_result_publication": perf_counter_ns()
            - invocation_start,
            "core_wall_ns": core_wall_ns,
            "recovery_wall_ns": recovery_wall_ns,
            "timing_scope": "core and recovery/publication are nested in run time; preflight recorded separately; final result publication excluded",
            "work_scope": "this run only; inspect every retained run for total archive work",
            "claims": CLAIMS,
        },
    )


def inspect_rc_fiber_history_archive_work(output_directory):
    """Account for every reserved invocation, including interrupted older runs.

    This is read-only ledger inspection, not numerical or execution-authenticity
    validation. Missing outcomes never become zero-cost successful work.
    """
    root = Path(output_directory)
    manifest = _read(root / "manifest.json")
    if (root / "runs").is_symlink():
        raise ValueError("original run directory required")
    work = {phase: _counts(()) for phase in ("prefix_replay", "suffix")}
    unknown_core = []
    unknown_recovery = []
    runs_without_terminal = []
    reserved = core_wall_ns = recovery_wall_ns = 0
    preflight_wall_ns = 0
    for run in sorted((root / "runs").iterdir()):
        if run.is_symlink() or not run.is_dir():
            raise ValueError("original run directory required")
        opening = _read(run / "started.json")
        if opening["manifest_hash"] != manifest["artifact_hash"]:
            raise ValueError("run manifest binding mismatch")
        elapsed = opening["preflight_wall_ns"]
        if type(elapsed) is not int or elapsed < 0:
            raise ValueError("invalid preflight elapsed time")
        preflight_wall_ns += elapsed
        if not (run / "result.json").exists():
            runs_without_terminal.append(run.name)
        for started in sorted(run.glob("*-started.json")):
            match = re.fullmatch(
                r"(prefix_replay|suffix)-([0-9]{5})-started\.json", started.name
            )
            if match is None:
                raise ValueError("invalid reserved invocation name")
            phase, index = match[1], int(match[2])
            opening = _read(started)
            if (
                opening["manifest_hash"] != manifest["artifact_hash"]
                or opening["target_index"] != index
                or opening["target_m"] != manifest["targets_m"][index]
            ):
                raise ValueError("reserved invocation binding mismatch")
            reserved += 1
            stem = started.name.removesuffix("-started.json")
            outcome = run / (stem + "-outcome.json")
            identity = {"run": run.name, "phase": phase, "index": index}
            if not outcome.exists():
                unknown_core.append(identity)
                continue
            result = _read(outcome)
            if type(result["core_wall_ns"]) is not int or result["core_wall_ns"] < 0:
                raise ValueError("invalid core elapsed time")
            if type(result["attempts"]) is not list or len(result["attempts"]) != 1:
                raise ValueError("one original core attempt per reservation required")
            for key, value in _counts(result["attempts"]).items():
                work[phase][key] += value
            core_wall_ns += result["core_wall_ns"]
            verified = run / (stem + "-verified.json")
            if verified.exists():
                recovery = _read(verified)
                elapsed = recovery["recovery_wall_ns"]
                if type(elapsed) is not int or elapsed < 0:
                    raise ValueError("invalid recovery elapsed time")
                recovery_wall_ns += elapsed
            elif result["attempts"][0]["committed"]:
                unknown_recovery.append(identity)
    return {
        "manifest_hash": manifest["artifact_hash"],
        "reserved_step_invocations": reserved,
        "reported_work": work,
        "unavailable_core_invocations": unknown_core,
        "unavailable_recovery_outcomes": unknown_recovery,
        "runs_without_terminal_record": runs_without_terminal,
        "core_wall_ns": core_wall_ns,
        "recovery_wall_ns": recovery_wall_ns,
        "preflight_wall_ns": preflight_wall_ns,
        "unpublished_accepted_temporaries": sorted(
            path.name for path in (root / "accepted").glob(".pending-*")
        ),
        "numerical_validation_performed": False,
        "claims": CLAIMS,
    }
