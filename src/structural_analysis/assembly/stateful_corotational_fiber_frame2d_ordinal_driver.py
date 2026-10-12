"""Bounded native driver and corruption-strict continuation for one full history.

Checksums bind a declared input and structural accounting. They do not establish
hostile-prefix authenticity or a trusted durable execution budget. No replay,
preload or numerical solve is performed while decoding a continuation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    dump_stateful_corotational_fiber_frame2d_checkpoint_bytes,
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    _source_identity,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    _free_generalized_coordinates,
    _exact_float64_equal,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_ordinal_history import (
    PROFILE,
    FORMULA_HASH,
    MAX_SOLVER_ATTEMPTS,
    OrdinalHistoryPlan,
    ScheduledFrameProblem,
    ScheduledMechanicalCheckpoint,
    assemble_scheduled_frame,
    accepted_state_force_scale,
    initial_mechanical_checkpoint,
    validate_mechanical_checkpoint,
    solve_scheduled_control_step,
    integer,
    number,
    hash_field,
    json_bytes,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

SCHEMA = "source-ordinal-corotational-continuation.v1"
MAX_CONTINUATION_BYTES = 16 * 1024 * 1024


def _context(problem, plan, config, budget, depth, source):
    if (
        type(problem) is not ScheduledFrameProblem
        or type(plan) is not OrdinalHistoryPlan
    ):
        raise ValueError("exact scheduled problem/full ordinal plan required")
    if type(config) is not StatefulCorotationalFiberFrame2DDisplacementControlConfig:
        raise ValueError("exact scheduled solver config required")
    if len(config.line_search_alphas) > 32:
        raise ValueError("scheduled profile admits at most32 line-search alphas")
    integer(budget, "maximum_solver_attempts", 1, MAX_SOLVER_ATTEMPTS)
    integer(depth, "maximum_subdivision_depth", 0, 20)
    return canonical_hash(
        {
            "profile": PROFILE,
            "formula_hash": FORMULA_HASH,
            "problem_hash": problem.hash,
            "plan_hash": plan.hash,
            "source_identity": source,
            "config": asdict(config),
            "maximum_solver_attempts": budget,
            "maximum_subdivision_depth": depth,
            "initialization": "virgin-zero-projection-first-row-constrained-solve",
            "interpolation": "paired-target-and-dead-load-dyadic-linear",
            "support_context": "fixed-legacy-lambda-proportional",
        }
    )


def _fraction(n, d):
    integer(d, "position depth", 0, 20)
    integer(n, "position numerator", 1, 2**d)
    while d and n % 2 == 0:
        n //= 2
        d -= 1
    return n, d


def _midpoint(left, right):
    ln, ld = left
    rn, rd = right
    d = max(ld, rd)
    return _fraction((ln << (d - ld)) + (rn << (d - rd)), d + 1)


def _target(plan, state, ordinal, position, genesis):
    row = plan.rows[ordinal]
    if ordinal:
        previous = plan.rows[ordinal - 1]
        g0, p0 = previous.target_m, previous.axial_load_kn
    else:
        g0, p0 = genesis.prescribed_target_m, 0.0
    f = position[0] / 2 ** position[1]
    if f == 1:
        return row.target_m, row.axial_load_kn
    # Convex form avoids overflow in end-minus-start for admitted finite values.
    return number((1 - f) * g0 + f * row.target_m, "interpolated target"), number(
        (1 - f) * p0 + f * row.axial_load_kn, "interpolated axial"
    )


@dataclass(frozen=True)
class OrdinalContinuation:
    context_hash: str
    source_identity: str
    plan_hash: str
    mechanical: ScheduledMechanicalCheckpoint
    next_ordinal: int = 0
    pending_positions: tuple[tuple[int, int], ...] = ()
    reserved_attempts: int = 0
    solver_invocations: int = 0
    mechanical_commits: int = 0
    failed_attempts: int = 0
    completed_solve_records: int = 0
    hold_records: int = 0
    linear_solve_attempts: int = 0
    failed_assembly_attempts: int = 0
    assembly_attempts: int = 0
    hold_assembly_attempts: int = 0
    entry_count: int = 0
    resume_verification_assembly_attempts: int = 0
    terminal_failure: str | None = None
    ledger_hash: str = "sha256:" + "0" * 64

    def semantic_dict(self):
        return {
            "schema_version": SCHEMA,
            **{k: v for k, v in self.__dict__.items() if k != "mechanical"},
            "pending_positions": [list(p) for p in self.pending_positions],
            "mechanical": {
                **self.mechanical.semantic_dict(),
                "state_hash": self.mechanical.state_hash,
            },
        }


@dataclass(frozen=True)
class OrdinalHistoryResult:
    status: str
    continuation: OrdinalContinuation
    events: tuple[dict[str, Any], ...]
    detail: str | None
    source_checks: int = 2
    preload_solver_invocations: int = 0
    replay_solver_invocations: int = 0


def _validate(problem, plan, config, budget, depth, source, continuation):
    context = _context(problem, plan, config, budget, depth, source)
    if type(continuation) is not OrdinalContinuation:
        raise ValueError(
            "exact native ordinal continuation required; bare v1 frame is only a projection"
        )
    for key in ("context_hash", "source_identity", "plan_hash", "ledger_hash"):
        hash_field(getattr(continuation, key), key)
    if (
        continuation.context_hash != context
        or continuation.source_identity != source
        or continuation.plan_hash != plan.hash
    ):
        raise ValueError(
            "continuation full source/model/operator/path/budget/config identity mismatch"
        )
    validate_mechanical_checkpoint(problem, context, continuation.mechanical)
    for key in (
        "next_ordinal",
        "reserved_attempts",
        "solver_invocations",
        "mechanical_commits",
        "failed_attempts",
        "completed_solve_records",
        "hold_records",
        "assembly_attempts",
        "hold_assembly_attempts",
        "linear_solve_attempts",
        "failed_assembly_attempts",
        "entry_count",
        "resume_verification_assembly_attempts",
    ):
        integer(getattr(continuation, key), key, 0, MAX_SOLVER_ATTEMPTS * 10000)
    c = continuation
    m = c.mechanical
    if not (
        c.next_ordinal <= len(plan.rows)
        and c.reserved_attempts == c.solver_invocations <= budget
        and c.mechanical_commits + c.failed_attempts == c.solver_invocations
        and c.mechanical_commits == m.frame_checkpoint.epoch
        and c.completed_solve_records + c.hold_records == c.next_ordinal
        and c.completed_solve_records <= c.mechanical_commits
        and c.assembly_attempts >= c.solver_invocations
        and c.hold_assembly_attempts
        == c.hold_records
        + (
            c.terminal_failure
            == "held_authored_row_failed_equilibrium_or_state_verification"
        )
    ):
        raise ValueError("continuation cumulative accounting is inconsistent")
    if (
        type(c.pending_positions) is not tuple
        or len(c.pending_positions) > depth + 1
        or any(type(p) is not tuple or len(p) != 2 for p in c.pending_positions)
    ):
        raise ValueError("invalid bounded pending dyadic stack")
    for p in c.pending_positions:
        if p != _fraction(*p) or p[1] > depth:
            raise ValueError("noncanonical pending dyadic position")
    if (
        c.completed_solve_records != plan._solve_prefix_count[c.next_ordinal]
        or c.hold_records != c.next_ordinal - plan._solve_prefix_count[c.next_ordinal]
    ):
        raise ValueError(
            "completed mechanical/hold counts do not match authored prefix"
        )
    if m.certified and m.last_mechanical_ordinal >= len(plan.rows):
        raise ValueError("mechanical sample is beyond supplied plan")
    if (
        m.certified
        and plan._hold_run_start[m.last_mechanical_ordinal] != m.last_mechanical_ordinal
    ):
        raise ValueError("mechanical commit cannot occur on an authored hold row")
    if (
        c.pending_positions
        and c.next_ordinal < len(plan.rows)
        and plan._hold_run_start[c.next_ordinal] != c.next_ordinal
    ):
        raise ValueError("authored hold row cannot have a pending mechanical target")
    if c.pending_positions and (
        c.next_ordinal == len(plan.rows)
        or c.pending_positions[-1] != (1, 0)
        or any(
            a[0] / 2 ** a[1] >= b[0] / 2 ** b[1]
            for a, b in zip(c.pending_positions, c.pending_positions[1:])
        )
    ):
        raise ValueError("pending dyadic stack must end at the current authored row")
    if c.terminal_failure not in (
        None,
        "held_authored_row_failed_equilibrium_or_state_verification",
        "maximum_paired_subdivision_depth_exceeded",
        "paired_midpoint_not_representable",
        "resume_equilibrium_verification_failed",
    ):
        raise ValueError("invalid terminal failure")
    if (
        c.entry_count > budget + len(plan.rows) + 1
        or c.resume_verification_assembly_attempts > c.entry_count
    ):
        raise ValueError("continuation entry/verification resource budget exceeded")
    genesis = initial_mechanical_checkpoint(problem, context)
    if m.certified and (
        (m.position_numerator, m.position_depth)
        != _fraction(m.position_numerator, m.position_depth)
        or m.position_depth > depth
    ):
        raise ValueError("noncanonical accepted mechanical dyadic position")
    if c.pending_positions:
        left = (
            (m.position_numerator, m.position_depth)
            if m.last_mechanical_ordinal == c.next_ordinal
            else (0, 0)
        )
        for right in c.pending_positions:
            d = max(left[1], right[1])
            ln = left[0] << (d - left[1])
            rn = right[0] << (d - right[1])
            length = rn - ln
            if length <= 0 or length & (length - 1) or ln % length:
                raise ValueError(
                    "pending queue is not an aligned dyadic remaining cover"
                )
            left = right
    if (
        c.linear_solve_attempts > c.solver_invocations * (config.maximum_iterations + 1)
        or c.failed_assembly_attempts > c.assembly_attempts
        or c.assembly_attempts
        > c.solver_invocations
        * ((config.maximum_iterations + 1) * (len(config.line_search_alphas) + 1) + 2)
    ):
        raise ValueError("continuation numerical cost exceeds admitted kernel bounds")
    if not m.certified:
        if c.next_ordinal or c.mechanical_commits or c.hold_records:
            raise ValueError("uncertified genesis cannot carry completed records")
    else:
        if (
            m.last_mechanical_ordinal > c.next_ordinal
            or m.last_mechanical_ordinal >= len(plan.rows)
        ):
            raise ValueError("mechanical sample is beyond observation cursor")
        if m.last_mechanical_ordinal == c.next_ordinal:
            if (
                not c.pending_positions
                or m.position_numerator / 2**m.position_depth
                >= c.pending_positions[0][0] / 2 ** c.pending_positions[0][1]
            ):
                raise ValueError(
                    "pending target does not follow accepted mechanical position"
                )
        elif (m.position_numerator, m.position_depth) != (1, 0):
            raise ValueError("completed mechanical sample must be its endpoint")
        g, p = _target(
            plan,
            m,
            m.last_mechanical_ordinal,
            (m.position_numerator, m.position_depth),
            genesis,
        )
        if m.prescribed_target_m != g or m.axial_load_kn != p:
            raise ValueError(
                "mechanical load/target does not match declared segment position"
            )
        if (
            abs(
                problem.observation.evaluate(m.frame_checkpoint.global_displacements)
                - g
            )
            > config.control_tolerance_m
        ):
            raise ValueError("accepted mechanical control exceeds declared tolerance")
        if m.last_mechanical_ordinal < c.next_ordinal:
            # Every intervening completed row must be an exact authored hold.
            if plan._hold_run_start[c.next_ordinal - 1] > m.last_mechanical_ordinal:
                raise ValueError("observation cursor skips a mechanical source change")
    if c.solver_invocations == 0 and (
        c.ledger_hash != "sha256:" + "0" * 64 or c.assembly_attempts
    ):
        raise ValueError("genesis ledger cannot contain hidden work")
    return context


def run_ordinal_history(
    problem,
    plan,
    *,
    maximum_solver_attempts,
    per_call_attempt_limit=255,
    per_call_record_limit=255,
    maximum_subdivision_depth=8,
    config=None,
    continuation=None,
):
    """Advance a bounded slice of one immutable full path, preserving its budget.

    ``maximum_solver_attempts`` is a required whole-path admission. The <=255
    call bounds govern returned work/memory; they never reset cumulative cost.
    """
    integer(per_call_attempt_limit, "per_call_attempt_limit", 1, 255)
    integer(per_call_record_limit, "per_call_record_limit", 1, 255)
    if config is None:
        config = StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    source = "sha256:" + _source_identity()
    context = _context(
        problem,
        plan,
        config,
        maximum_solver_attempts,
        maximum_subdivision_depth,
        source,
    )
    if continuation is None:
        continuation = OrdinalContinuation(
            context, source, plan.hash, initial_mechanical_checkpoint(problem, context)
        )
    _validate(
        problem,
        plan,
        config,
        maximum_solver_attempts,
        maximum_subdivision_depth,
        source,
        continuation,
    )
    values = {k: v for k, v in continuation.__dict__.items()}
    events = []
    call_attempts = 0
    call_records = 0
    detail = None
    status = "paused"
    genesis = initial_mechanical_checkpoint(problem, context)
    if values["entry_count"] >= maximum_solver_attempts + len(plan.rows) + 1:
        raise ValueError("whole-path entry resource budget exhausted")
    values["entry_count"] += 1
    if values["mechanical"].certified and not values["terminal_failure"]:
        parent = values["mechanical"]
        values["resume_verification_assembly_attempts"] += 1
        trial = assemble_scheduled_frame(
            problem,
            parent,
            context,
            target_axial_load_kn=parent.axial_load_kn,
            target_load_factor=parent.frame_checkpoint.load_factor,
            trial_free_coordinates_m=_free_generalized_coordinates(
                problem.frame_problem, parent.frame_checkpoint
            ),
        )
        scale = accepted_state_force_scale(problem, parent.axial_load_kn)
        if (
            float(np.linalg.norm(trial.residual_kn, ord=np.inf)) / scale
            > config.residual_tolerance
        ):
            values["terminal_failure"] = "resume_equilibrium_verification_failed"
    if values["terminal_failure"]:
        status = "blocked"
        detail = values["terminal_failure"]
    while (
        not values["terminal_failure"]
        and values["next_ordinal"] < len(plan.rows)
        and call_records < per_call_record_limit
        and len(events) < 255
    ):
        ordinal = values["next_ordinal"]
        row = plan.rows[ordinal]
        parent = values["mechanical"]
        previous = None if ordinal == 0 else plan.rows[ordinal - 1]
        hold = bool(
            not values["pending_positions"]
            and previous is not None
            and (previous.target_m, previous.axial_load_kn)
            == (row.target_m, row.axial_load_kn)
        )
        if hold:
            before = parent.canonical_bytes()
            # Verify accepted equilibrium and control without solving/committing.
            values["hold_assembly_attempts"] += 1
            trial = assemble_scheduled_frame(
                problem,
                parent,
                context,
                target_axial_load_kn=row.axial_load_kn,
                target_load_factor=parent.frame_checkpoint.load_factor,
                trial_free_coordinates_m=_free_generalized_coordinates(
                    problem.frame_problem, parent.frame_checkpoint
                ),
            )
            scale = accepted_state_force_scale(problem, row.axial_load_kn)
            if (
                not parent.certified
                or abs(
                    problem.observation.evaluate(trial.global_displacements)
                    - row.target_m
                )
                > config.control_tolerance_m
                or float(np.linalg.norm(trial.residual_kn, ord=np.inf)) / scale
                > config.residual_tolerance
                or parent.canonical_bytes() != before
            ):
                status = "blocked"
                detail = "held_authored_row_failed_equilibrium_or_state_verification"
                values["terminal_failure"] = detail
                break
            values["hold_records"] += 1
            values["next_ordinal"] += 1
            call_records += 1
            event = {
                "kind": "verified_hold",
                "ordinal": ordinal,
                "source_row": row.source_row,
                "source_row_sha256": row.source_row_sha256,
                "target_m": row.target_m,
                "axial_load_kn": row.axial_load_kn,
                "mechanical_state_hash": parent.state_hash,
                "frame_epoch": parent.frame_checkpoint.epoch,
                "solver_invocations": values["solver_invocations"],
            }
        else:
            if call_attempts >= per_call_attempt_limit:
                break
            if values["reserved_attempts"] >= maximum_solver_attempts:
                status = "budget_exhausted"
                detail = "whole_path_solver_attempt_budget_exhausted"
                break
            pending = values["pending_positions"] or ((1, 0),)
            position = pending[0]
            g, p = _target(plan, parent, ordinal, position, genesis)
            before = parent.canonical_bytes()
            values["reserved_attempts"] += 1
            values["solver_invocations"] += 1
            call_attempts += 1
            cost = [0]
            linear = {"linear_solve_attempts": 0}
            result = None
            failure = None
            try:
                result = solve_scheduled_control_step(
                    problem,
                    parent,
                    context,
                    target_m=g,
                    axial_load_kn=p,
                    ordinal=ordinal,
                    position_numerator=position[0],
                    position_depth=position[1],
                    config=config,
                    cost_counter=cost,
                    linear_counter=linear,
                )
            except (
                TypeError,
                ValueError,
                ArithmeticError,
                AttributeError,
                LookupError,
            ) as exc:
                failure = type(exc).__name__
            values["assembly_attempts"] += cost[0]
            values["linear_solve_attempts"] += linear["linear_solve_attempts"]
            committed = bool(result is not None and result.committed)
            if parent.canonical_bytes() != before:
                raise RuntimeError("scheduled parent mutated during trial")
            if committed:
                values["mechanical"] = result.accepted
                values["mechanical_commits"] += 1
                pending = pending[1:]
                if position == (1, 0):
                    values["next_ordinal"] += 1
                    values["completed_solve_records"] += 1
                    call_records += 1
                values["pending_positions"] = pending
            else:
                values["failed_attempts"] += 1
                values["failed_assembly_attempts"] += cost[0]
                left = (
                    (parent.position_numerator, parent.position_depth)
                    if parent.last_mechanical_ordinal == ordinal
                    else (0, 0)
                )
                if max(left[1], position[1]) >= maximum_subdivision_depth:
                    values["pending_positions"] = pending
                    status = "blocked"
                    detail = "maximum_paired_subdivision_depth_exceeded"
                else:
                    midpoint = _midpoint(left, position)
                    gm, pm = _target(plan, parent, ordinal, midpoint, genesis)
                    if (gm, pm) == (g, p) or (gm, pm) == _target(
                        plan, parent, ordinal, left, genesis
                    ):
                        values["pending_positions"] = pending
                        status = "blocked"
                        detail = "paired_midpoint_not_representable"
                    else:
                        values["pending_positions"] = (midpoint,) + pending
            event = {
                "kind": "mechanical_commit" if committed else "failed_attempt",
                "ordinal": ordinal,
                "source_row": row.source_row,
                "source_row_sha256": row.source_row_sha256,
                "position_numerator": position[0],
                "position_depth": position[1],
                "target_m": g,
                "axial_load_kn": p,
                "attempt_ordinal": values["solver_invocations"],
                "assembly_attempts": cost[0],
                "linear_solve_attempts": linear["linear_solve_attempts"],
                "parent_mechanical_state_hash": parent.state_hash,
                "mechanical_state_hash": values["mechanical"].state_hash,
                "frame_epoch": values["mechanical"].frame_checkpoint.epoch,
                "rollback_exact": None
                if committed
                else values["mechanical"] is parent
                and parent.canonical_bytes() == before,
                "terminal_reason": failure
                if result is None
                else result.solution.metrics.get("terminal_reason"),
            }
        if status == "blocked":
            values["terminal_failure"] = detail
        values["ledger_hash"] = canonical_hash(
            {"parent": values["ledger_hash"], "event": event}
        )
        events.append(event)
        if status == "blocked":
            break
    if values["next_ordinal"] == len(plan.rows) and not values["terminal_failure"]:
        status = "complete"
    final = OrdinalContinuation(**values)
    _validate(
        problem,
        plan,
        config,
        maximum_solver_attempts,
        maximum_subdivision_depth,
        source,
        final,
    )
    if "sha256:" + _source_identity() != source:
        raise RuntimeError("Python source changed during frozen ordinal entry")
    return OrdinalHistoryResult(status, final, tuple(events), detail)


def dump_ordinal_continuation(
    problem,
    plan,
    continuation,
    *,
    maximum_solver_attempts,
    maximum_subdivision_depth=8,
    config=None,
):
    if config is None:
        config = StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    source = "sha256:" + _source_identity()
    _validate(
        problem,
        plan,
        config,
        maximum_solver_attempts,
        maximum_subdivision_depth,
        source,
        continuation,
    )
    payload = continuation.semantic_dict()
    # The old strict codec preserves only the nested constitutive projection.
    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem.frame_problem, continuation.mechanical.frame_checkpoint
    )
    payload["frame_checkpoint"] = json.loads(raw)
    payload["artifact_hash"] = canonical_hash(payload)
    data = json_bytes(payload)
    if len(data) > MAX_CONTINUATION_BYTES:
        raise ValueError("continuation byte budget exceeded")
    return data


def _strict(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate continuation key")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError("nonfinite continuation JSON constant")


def load_ordinal_continuation(
    data,
    problem,
    plan,
    *,
    maximum_solver_attempts,
    maximum_subdivision_depth=8,
    config=None,
):
    if type(data) is not bytes or not 0 < len(data) <= MAX_CONTINUATION_BYTES:
        raise ValueError("bounded canonical continuation bytes required")
    payload = json.loads(
        data.decode("utf-8"), object_pairs_hook=_strict, parse_constant=_reject_constant
    )
    expected = set(OrdinalContinuation.__dataclass_fields__) - {"mechanical"} | {
        "schema_version",
        "mechanical",
        "frame_checkpoint",
        "artifact_hash",
    }
    if (
        type(payload) is not dict
        or set(payload) != expected
        or payload.get("schema_version") != SCHEMA
        or json_bytes(payload) != data
    ):
        raise ValueError("continuation shape/canonical encoding mismatch")
    artifact = payload.pop("artifact_hash")
    if artifact != canonical_hash(payload):
        raise ValueError("continuation artifact hash mismatch")
    mechanical = payload.pop("mechanical")
    mechanical_keys = {
        "schema",
        "context_hash",
        "constitutive_frame_state_hash",
        "load_context",
        "certified",
        "last_mechanical_ordinal",
        "position_numerator",
        "position_depth",
        "prescribed_target_m",
        "parent_hash",
        "state_hash",
    }
    if (
        type(mechanical) is not dict
        or set(mechanical) != mechanical_keys
        or mechanical["schema"] != "scheduled-corotational-mechanical-checkpoint.v1"
        or type(mechanical["load_context"]) is not dict
        or set(mechanical["load_context"]) != {"axial_load_kn", "lambda"}
    ):
        raise ValueError("mechanical checkpoint shape mismatch")
    # Strict canonical old-frame decoder rejects bools, unknown/missing fields,
    # altered material history and inconsistent binary checkpoint hashes.
    frame = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        json_bytes(payload.pop("frame_checkpoint")), problem.frame_problem
    )
    if (
        frame.state_hash != mechanical["constitutive_frame_state_hash"]
        or type(mechanical["load_context"]["lambda"]) not in (int, float)
        or not _exact_float64_equal(
            [number(mechanical["load_context"]["lambda"], "lambda")],
            [frame.load_factor],
        )
    ):
        raise ValueError("nested lambda/constitutive checkpoint binding mismatch")
    state = ScheduledMechanicalCheckpoint(
        mechanical["context_hash"],
        frame,
        mechanical["load_context"]["axial_load_kn"],
        mechanical["certified"],
        mechanical["last_mechanical_ordinal"],
        mechanical["position_numerator"],
        mechanical["position_depth"],
        mechanical["prescribed_target_m"],
        mechanical["parent_hash"],
    )
    if state.state_hash != mechanical["state_hash"]:
        raise ValueError("mechanical checkpoint hash mismatch")
    positions = payload["pending_positions"]
    if type(positions) is not list or any(
        type(p) is not list or len(p) != 2 for p in positions
    ):
        raise ValueError("invalid pending position encoding")
    payload["pending_positions"] = tuple(tuple(p) for p in positions)
    payload.pop("schema_version")
    continuation = OrdinalContinuation(mechanical=state, **payload)
    if config is None:
        config = StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    source = "sha256:" + _source_identity()
    _validate(
        problem,
        plan,
        config,
        maximum_solver_attempts,
        maximum_subdivision_depth,
        source,
        continuation,
    )
    if (
        dump_ordinal_continuation(
            problem,
            plan,
            continuation,
            maximum_solver_attempts=maximum_solver_attempts,
            maximum_subdivision_depth=maximum_subdivision_depth,
            config=config,
        )
        != data
    ):
        raise ValueError("continuation typed canonical round-trip mismatch")
    return continuation
