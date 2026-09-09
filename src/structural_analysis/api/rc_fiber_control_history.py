"""Streaming authored RC histories with exact source-prefix replay.

One original transition is retained at a time. Consumers own storage and must keep
record order and original bytes; an accepted checkpoint alone is not a replay proof.
This profile does not reinterpret measured responses as commanded displacements.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable
from itertools import chain
import json
from typing import Any

from structural_analysis.api.nonlinear_fiber_frame import _compile
from structural_analysis.api.rc_fiber_frame_direct_control import (
    _CLAIMS,
    _hash,
    _json,
    _recover_preload,
    _recover_step,
    _with_constant_loading,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    StatefulFiberFrame2DControlExecutionError,
    _counts,
    _directions,
    _execute_preload,
    _execute_raw,
    _integer,
    _targets,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    validate_stateful_fiber_frame2d_control_problem,
)
from structural_analysis.model.schema import CanonicalModel

HISTORY_MAX_TARGETS = 4096
HISTORY_RECORD_MAX_BYTES = 16 * 1024 * 1024
HISTORY_HEADER_SCHEMA = "rc-fiber-control-history-header.v1"
HISTORY_RECORD_SCHEMA = "rc-fiber-control-history-transition.v1"


class RCFiberControlHistoryError(ValueError):
    """An interrupted stream retains observed work without granting a restart."""

    def __init__(self, message, report):
        super().__init__(message)
        self._report = _json(report)

    def to_dict(self):
        return json.loads(self._report)


class RCFiberControlHistoryStream:
    """Single-use iterator; ``report`` is a detached snapshot of actual work.

    Closing the iterator pauses at its last emitted accepted transition. Resume
    requires the original header and complete original prefix records. Replayed
    records are yielded again so a consumer can write a new self-contained stream.
    Consumer persistence/fsync is outside this API's authority.
    ``ready`` requires exhausting the iterator (including checking for trailing
    prior records); closing after any yield reports ``paused`` instead.
    """

    def __init__(self, compiled, config, header, targets, prior_records):
        self._compiled = compiled
        self._config = config
        self._header = _json(header)
        self._targets = targets
        self._prior = None if prior_records is None else iter(prior_records)
        self._resume_requested = prior_records is not None
        self._started = False
        self._report: dict[str, Any] = {
            "schema_version": "rc-fiber-control-history-report.v1",
            "status": "not_started",
            "header_sha256": _hash(self._header),
            "requested_target_count": len(targets),
            "accepted_target_count": 0,
            "emitted_transition_count": 0,
            "replayed_transition_count": 0,
            "core_invocations_started": 0,
            "preload_work": _counts([]),
            "replay_work": _counts([]),
            "new_work": _counts([]),
            "total_work": _counts([]),
            "response_reassembly_attempts": 0,
            "response_reassembly_verified_count": 0,
            "last_record_hash": _hash(self._header),
            "last_emitted_checkpoint_hash": None,
            "failure": None,
            "claims": dict(_CLAIMS),
            "storage_durability_verified": False,
        }

    @property
    def report(self):
        return json.loads(_json(self._report))

    def _prior_record(self):
        if self._prior is None:
            return None
        try:
            raw = next(self._prior)
        except StopIteration:
            self._prior = None
            return None
        if type(raw) is not bytes or not raw or len(raw) > HISTORY_RECORD_MAX_BYTES:
            raise ValueError("prior history requires bounded nonempty original bytes")
        return raw

    def _charge(self, attempts, *, replay, preload):
        work = _counts(attempts)
        for key in ("total_work", "replay_work" if replay else "new_work"):
            for field, value in work.items():
                self._report[key][field] += value
        if preload:
            for field, value in work.items():
                self._report["preload_work"][field] += value

    def __iter__(self) -> Generator[bytes, None, None]:
        if self._started:
            raise ValueError("history stream is single-use")
        self._started = True
        return self._records()

    def _records(self) -> Generator[bytes, None, None]:
        report = self._report
        report["status"] = "running"
        problem = self._compiled.problem
        source_hash = problem.contract_hash
        cfg = self._config
        config_hash = cfg.contract_hash
        parent = initial_stateful_fiber_frame2d_checkpoint(problem)
        header = json.loads(self._header)
        control_dof = header["request"]["control_global_dof"]
        try:
            supplied_header = self._prior_record()
            if self._resume_requested and supplied_header is None:
                raise ValueError("prior history must contain its original header")
            if supplied_header is not None and supplied_header != self._header:
                raise ValueError("prior history header/source/request mismatch")
            yield self._header
            # Targets are a bounded immutable tuple; full response/step objects
            # are never collected in a cumulative list.
            phases = chain(
                (("preload", None),) if problem.constant_external_loads else (),
                (("control", index) for index in range(len(self._targets))),
            )
            origin = 0.0
            directions_checked = False
            for kind, index in phases:
                if (
                    problem.contract_hash != source_hash
                    or cfg.contract_hash != config_hash
                ):
                    raise ValueError(
                        "history model/configuration changed during execution"
                    )
                if kind == "control" and not directions_checked:
                    _, reversals = _directions(self._targets, origin)
                    if reversals > header["request"]["maximum_reversals"]:
                        raise ValueError("history cumulative reversal budget exceeded")
                    directions_checked = True
                expected = self._prior_record()
                # Reading a caller-owned iterator is also an execution boundary.
                if (
                    problem.contract_hash != source_hash
                    or cfg.contract_hash != config_hash
                ):
                    raise ValueError(
                        "history source changed while reading prior records"
                    )
                replay = expected is not None
                report["core_invocations_started"] += 1
                try:
                    if kind == "preload":
                        step, attempt = _execute_preload(problem, cfg)
                        attempts = [attempt]
                    else:
                        assert index is not None
                        target = self._targets[index]
                        _, steps, attempts = _execute_raw(
                            problem,
                            parent,
                            (target,),
                            control_dof,
                            cfg,
                            source_hash,
                            phase="history_replay" if replay else "history_new",
                        )
                        step = steps[0] if steps else None
                except StatefulFiberFrame2DControlExecutionError as exc:
                    failed = exc.to_dict()
                    self._charge(
                        failed["attempts"], replay=replay, preload=kind == "preload"
                    )
                    report["execution_failure"] = failed
                    raise
                except BaseException:
                    # Cancellation can escape the core's ordinary Exception
                    # handling. Retain the started call with unavailable work.
                    self._charge(
                        [{"step": None, "solver_work": None}],
                        replay=replay,
                        preload=kind == "preload",
                    )
                    raise
                self._charge(attempts, replay=replay, preload=kind == "preload")
                response = None
                child = parent
                if step is not None and step.committed:
                    report["response_reassembly_attempts"] += 1
                    if kind == "preload":
                        child, response = _recover_preload(self._compiled, step, cfg)
                        origin = child.global_displacements[control_dof]
                    else:
                        assert index is not None
                        child, response = _recover_step(
                            self._compiled,
                            parent,
                            step,
                            cfg,
                            control_dof,
                            self._targets[index],
                            source_hash,
                        )
                    report["response_reassembly_verified_count"] += 1
                record = {
                    "schema_version": HISTORY_RECORD_SCHEMA,
                    "header_sha256": report["header_sha256"],
                    "sequence": report["emitted_transition_count"],
                    "kind": kind,
                    "target_index": index,
                    "target_m": None if index is None else self._targets[index],
                    "previous_record_hash": report["last_record_hash"],
                    "attempt": attempts[0],
                    "response": response,
                    "accepted_checkpoint": child.to_dict(),
                }
                # _execute_raw's phase is confined to error context; successful
                # record bytes do not depend on whether this call is replay.
                record["record_hash"] = _hash(_json(record))
                raw = _json(record)
                if len(raw) > HISTORY_RECORD_MAX_BYTES:
                    raise ValueError("history transition exceeds record byte bound")
                if expected is not None and expected != raw:
                    raise ValueError(
                        "prior history differs from original source replay"
                    )
                if (
                    problem.contract_hash != source_hash
                    or cfg.contract_hash != config_hash
                ):
                    raise ValueError("history source changed during response recovery")
                parent = child
                report["emitted_transition_count"] += 1
                report["replayed_transition_count"] += int(replay)
                report["last_record_hash"] = record["record_hash"]
                report["last_emitted_checkpoint_hash"] = parent.state_hash
                if kind == "control" and step is not None and step.committed:
                    report["accepted_target_count"] += 1
                yield raw
                if step is None or not step.committed:
                    if self._prior_record() is not None:
                        raise ValueError(
                            "prior history continues after a failed transition"
                        )
                    report["status"] = "blocked"
                    return
            if self._prior_record() is not None:
                raise ValueError(
                    "prior history contains records beyond requested targets"
                )
            if problem.contract_hash != source_hash or cfg.contract_hash != config_hash:
                raise ValueError("history source changed before stream completion")
            report["status"] = "ready"
        except GeneratorExit:
            report["status"] = "paused"
            raise
        except BaseException as exc:
            report["status"] = (
                "invalid_execution" if isinstance(exc, Exception) else "interrupted"
            )
            report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, Exception):
                raise RCFiberControlHistoryError(str(exc), self.report) from exc
            raise


def stream_rc_fiber_control_history(
    model: CanonicalModel,
    targets_m: Iterable[float],
    *,
    control_global_dof: int,
    config: StatefulFiberFrame2DDisplacementControlConfig | None = None,
    constant_nodal_loads: tuple[tuple[str, float, float, float], ...] = (),
    allow_reversals: bool = False,
    maximum_reversals: int = 0,
    maximum_targets: int = HISTORY_MAX_TARGETS,
    prior_records: Iterable[bytes] | None = None,
) -> RCFiberControlHistoryStream:
    """Prepare a bounded-memory original-transition stream, without solving yet.

    Up to 4096 authored targets are supported. Existing 255-target cumulative API
    and durable/Workbench contracts are unchanged. Resume is explicit full-prefix
    replay and its costs are separate; no checkpoint-only trust or hidden cutback.
    """
    if type(model) is not CanonicalModel:
        raise ValueError("model must be an exact CanonicalModel")
    _integer(maximum_targets, "maximum_targets", HISTORY_MAX_TARGETS, 1)
    _integer(maximum_reversals, "maximum_reversals", HISTORY_MAX_TARGETS - 1)
    if type(allow_reversals) is not bool or (not allow_reversals and maximum_reversals):
        raise ValueError("reversals require explicit opt-in and budget")
    targets = _targets(targets_m, maximum_targets)
    if not targets:
        raise ValueError("history targets must be nonempty")
    if any(a == b for a, b in zip(targets, targets[1:])):
        raise ValueError("successive authored targets must differ")
    # Reuse exact existing config/constant/control transport checks; no targets
    # are analyzed through the legacy cumulative request.
    template = BoundedRCFiberDirectControlRequest(
        control_global_dof,
        (),
        solver_config=(
            config
            if config is not None
            else StatefulFiberFrame2DDisplacementControlConfig()
        ),
        constant_nodal_loads=constant_nodal_loads,
    )
    snapshot = model.detached_analysis_snapshot()
    _json(snapshot.to_dict())
    compiled, unsupported, _ = _compile(snapshot)
    if compiled is None or unsupported:
        raise ValueError("history uses an unsupported canonical RC model")
    compiled = _with_constant_loading(compiled, template.constant_nodal_loads)
    validate_stateful_fiber_frame2d_control_problem(
        compiled.problem, control_global_dof
    )
    request = template.to_dict() | {
        "schema_version": "rc-fiber-control-history-request.v1",
        "targets_m": list(targets),
        "maximum_targets": maximum_targets,
        "allow_reversals": allow_reversals,
        "maximum_reversals": maximum_reversals,
    }
    header = {
        "schema_version": HISTORY_HEADER_SCHEMA,
        "request": request,
        "canonical_model_checksum": snapshot.canonical_model_checksum,
        "input_checksum": snapshot.input_checksum,
        "problem_contract_hash": compiled.problem.contract_hash,
        "record_max_bytes": HISTORY_RECORD_MAX_BYTES,
        "claims": dict(_CLAIMS),
    }
    return RCFiberControlHistoryStream(
        compiled, template.solver_config, header, targets, prior_records
    )
