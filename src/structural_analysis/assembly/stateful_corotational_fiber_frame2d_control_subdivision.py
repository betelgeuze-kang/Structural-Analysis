"""Bounded retry subdivision for internal corotational displacement histories."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from itertools import islice
from typing import Iterable

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepResult,
    LinearPhysicalDisplacementObservation,
    _validate_control_selection,
    _accepted_control_value,
    _finite,
    _require_connected_member_graph,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)


@dataclass(frozen=True)
class CorotationalControlSubdivisionResult:
    status: str
    terminal_reason: str
    authored_targets: tuple[float, ...]
    completed_target_count: int
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    attempts: tuple[StatefulCorotationalFiberFrame2DDisplacementControlStepResult, ...]

    total_attempt_count: int
    continuation: bytes

    @property
    def contract_pass(self) -> bool:
        return self.status == "ready" and self.completed_target_count == len(
            self.authored_targets
        )


_MAX_CONTINUATION_BYTES = 16 * 1024 * 1024
_TERMINAL_REASONS = {
    "subdivision_depth_exhausted",
    "subdivision_has_no_representable_progress",
}


def _json_bytes(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _source_identity() -> str:
    # Conservative source binding: any Python source change requires a new run.
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate continuation field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite continuation value")


def _encode_continuation(
    problem, context, first, accepted, pending, completed, spent, terminal
):
    payload = {
        "schema": 1,
        "context": context,
        "first": json.loads(
            dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(problem, first)
        ),
        "accepted": json.loads(
            dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(problem, accepted)
        ),
        "pending": pending,
        "completed": completed,
        "spent": spent,
        "terminal": terminal,
    }
    raw = _json_bytes(
        {"payload": payload, "sha256": hashlib.sha256(_json_bytes(payload)).hexdigest()}
    )
    if len(raw) > _MAX_CONTINUATION_BYTES:
        raise ValueError("continuation exceeds byte limit")
    return raw


def _decode_continuation(raw, problem, context, targets, budget, max_depth):
    if type(raw) is not bytes or len(raw) > _MAX_CONTINUATION_BYTES:
        raise ValueError("continuation must be bounded bytes")
    try:
        envelope = json.loads(
            raw, object_pairs_hook=_strict_object, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid continuation JSON") from exc
    if type(envelope) is not dict or set(envelope) != {"payload", "sha256"}:
        raise ValueError("invalid continuation envelope")
    payload = envelope["payload"]
    if type(payload) is not dict or set(payload) != {
        "schema",
        "context",
        "first",
        "accepted",
        "pending",
        "completed",
        "spent",
        "terminal",
    }:
        raise ValueError("invalid continuation schema")
    if envelope["sha256"] != hashlib.sha256(_json_bytes(payload)).hexdigest():
        raise ValueError("continuation checksum mismatch")
    if type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("invalid continuation schema version")
    if payload["context"] != context:
        raise ValueError("continuation input, policy or source mismatch")
    completed, spent = payload["completed"], payload["spent"]
    if type(spent) is not int or not 0 <= spent <= budget:
        raise ValueError("invalid continuation spent budget")
    if type(completed) is not int or not 0 <= completed <= min(len(targets), spent):
        raise ValueError("invalid continuation completed count")
    terminal = payload["terminal"]
    if type(terminal) is not str or terminal not in _TERMINAL_REASONS | {""}:
        raise ValueError("invalid continuation terminal reason")
    pending = payload["pending"]
    if type(pending) is not list or len(pending) > len(targets) + max_depth:
        raise ValueError("invalid continuation pending size")
    indices = []
    for entry in pending:
        if type(entry) is not list or len(entry) != 3:
            raise ValueError("invalid continuation pending entry")
        value, depth, index = entry
        _finite(value, name="pending target")
        if (
            type(value) not in (int, float)
            or type(depth) is not int
            or not 0 <= depth <= max_depth
        ):
            raise ValueError("invalid continuation pending depth or target")
        if type(index) is not int or not completed <= index < len(targets):
            raise ValueError("invalid continuation pending index")
        indices.append(index)
    if indices != sorted(indices, reverse=True) or set(indices) != set(
        range(completed, len(targets))
    ):
        raise ValueError("invalid continuation pending order")
    for index in set(indices):
        if pending[indices.index(index)][0] != targets[index]:
            raise ValueError("continuation omits authored target")
    if terminal and (not pending or not spent):
        raise ValueError("invalid continuation terminal state")
    first = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        _json_bytes(payload["first"]), problem
    )
    accepted = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        _json_bytes(payload["accepted"]), problem
    )
    if spent == 0 and accepted.canonical_bytes() != first.canonical_bytes():
        raise ValueError("unspent continuation changed accepted state")
    return first, accepted, pending, completed, spent, terminal


def run_corotational_control_subdivision(
    problem: StatefulCorotationalFiberFrame2DProblem,
    control_displacements_m: Iterable[float],
    *,
    control_global_dof: int | None = None,
    control_observation: LinearPhysicalDisplacementObservation | None = None,
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    maximum_attempt_count: int = 255,
    maximum_subdivision_depth: int = 8,
    config: StatefulCorotationalFiberFrame2DDisplacementControlConfig | None = None,
    continuation: bytes | None = None,
    attempt_limit_per_call: int | None = None,
) -> CorotationalControlSubdivisionResult:
    """Retry failed increments by bisection; every solver attempt spends budget.

    Cooperative pauses serialize the queue and cumulative budget. Checksums detect
    corruption, not hostile rewriting or replay: managed budget authority and
    abrupt process-death accounting remain the caller's responsibility.
    """
    if type(maximum_attempt_count) is not int or not 1 <= maximum_attempt_count <= 4096:
        raise ValueError("maximum_attempt_count must be an integer in [1, 4096]")
    if (
        type(maximum_subdivision_depth) is not int
        or not 0 <= maximum_subdivision_depth <= 20
    ):
        raise ValueError("maximum_subdivision_depth must be an integer in [0, 20]")
    targets = tuple(
        _finite(v, name="control displacement")
        for v in islice(control_displacements_m, 256)
    )
    if not 1 <= len(targets) <= 255:
        raise ValueError("control targets must contain 1 to 255 entries")
    _require_connected_member_graph(problem)
    _validate_control_selection(problem, control_global_dof, control_observation)
    first = (
        initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
        if initial_checkpoint is None
        else initial_checkpoint
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, first)
    cfg = (
        StatefulCorotationalFiberFrame2DDisplacementControlConfig()
        if config is None
        else config
    )
    if type(cfg) is not StatefulCorotationalFiberFrame2DDisplacementControlConfig:
        raise ValueError("config type is invalid")
    if attempt_limit_per_call is not None and (
        type(attempt_limit_per_call) is not int
        or not 1 <= attempt_limit_per_call <= 4096
    ):
        raise ValueError("attempt_limit_per_call must be an integer in [1, 4096]")
    context = hashlib.sha256(
        _json_bytes(
            {
                "case": problem.case_id,
                "problem": problem.contract_hash,
                "source": _source_identity(),
                "targets": targets,
                "control": (
                    control_global_dof
                    if control_observation is None
                    else control_observation.to_dict()
                ),
                "budget": maximum_attempt_count,
                "depth": maximum_subdivision_depth,
                "config": asdict(cfg),
            }
        )
    ).hexdigest()
    accepted = first
    attempts = []
    completed = spent = 0
    terminal = ""
    reason = "all_authored_targets_reached"
    pending = [(value, 0, i) for i, value in reversed(tuple(enumerate(targets)))]
    if continuation is not None:
        original = first
        first, accepted, pending, completed, spent, terminal = _decode_continuation(
            continuation,
            problem,
            context,
            targets,
            maximum_attempt_count,
            maximum_subdivision_depth,
        )
        if (
            initial_checkpoint is not None
            and original.canonical_bytes() != first.canonical_bytes()
        ):
            raise ValueError("continuation initial checkpoint mismatch")
    previous = _accepted_control_value(
        problem, first, control_global_dof, control_observation
    )
    for target in targets:
        if target == previous:
            raise ValueError("consecutive control targets must differ")
        previous = target
    while pending:
        if terminal:
            reason = terminal
            break
        if spent >= maximum_attempt_count:
            reason = "attempt_budget_exhausted"
            break
        if (
            attempt_limit_per_call is not None
            and len(attempts) >= attempt_limit_per_call
        ):
            reason = "cooperative_pause"
            break
        target, depth, authored_index = pending.pop()
        parent_bytes = accepted.canonical_bytes()
        start = _accepted_control_value(
            problem, accepted, control_global_dof, control_observation
        )
        step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            problem,
            accepted,
            control_global_dof=control_global_dof,
            control_observation=control_observation,
            target_control_displacement_m=target,
            config=cfg,
        )
        attempts.append(step)
        spent += 1
        if accepted.canonical_bytes() != parent_bytes:
            raise ValueError("solver changed the accepted parent")
        if step.committed:
            accepted = step.accepted_checkpoint
            if target == targets[authored_index]:
                completed += 1
            continue
        if step.accepted_checkpoint.canonical_bytes() != parent_bytes:
            raise ValueError("failed solver attempt did not preserve accepted state")
        if depth >= maximum_subdivision_depth:
            reason = terminal = "subdivision_depth_exhausted"
            pending.append((target, depth, authored_index))
            break
        midpoint = start / 2.0 + target / 2.0
        if midpoint == start or midpoint == target:
            reason = terminal = "subdivision_has_no_representable_progress"
            pending.append((target, depth, authored_index))
            break
        pending.extend(
            ((target, depth + 1, authored_index), (midpoint, depth + 1, authored_index))
        )
    ready = not pending and completed == len(targets)
    return CorotationalControlSubdivisionResult(
        "ready" if ready else "paused" if reason == "cooperative_pause" else "blocked",
        reason,
        targets,
        completed,
        first,
        accepted,
        tuple(attempts),
        spent,
        _encode_continuation(
            problem, context, first, accepted, pending, completed, spent, terminal
        ),
    )
