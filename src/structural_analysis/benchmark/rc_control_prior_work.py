"""Opt-in consistency checks for one arm's original prior accepted transition.

These checks bind recorded bytes to the runtime's independently supplied current
parent. They do not authenticate a caller's source label, admit training data or
confer solver acceptance. Missing work remains unavailable.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
import re

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.engine_v2.contracts._canonical import canonical_hash

PRIOR_WORK_PROFILE = "rc-control-prior-accepted-transition-work.v1"
BINDING_PROFILE = "rc-control-prior-work-binding.v1"
MAX_PRIOR_WORK_BYTES = 32 * 1024 * 1024
_BINDING_KEYS = {
    "schema_version",
    "arm_identity",
    "problem_contract_hash",
    "control_global_dof",
    "control_free_index",
    "request_hash",
    "solver_config_hash",
    "source_binding_hash",
    "current_parent_hash",
    "current_parent_predecessor_hash",
    "current_parent_epoch",
    "current_parent_step_index",
    "accepted_prefix_sha256",
    "previous_target_index",
}
_PHASES = {
    "primary_iteration",
    "line_search",
    "terminal_refinement",
    "no_free_equations",
    "final_observation",
    "blocked_observation",
}


@dataclass(frozen=True)
class RCControlPriorWork:
    core_calls: int
    newton_iterations: int
    linear_solves: int
    assembly_dispatches: int | None
    line_search_dispatches: int | None
    terminal_refinement_dispatches: int | None
    parent_state_hash: str
    predecessor_state_hash: str
    epoch: int


def _natural(value):
    if type(value) is not int or value < 0:
        raise ValueError("prior work requires exact nonnegative integers")
    return value


def _identity(value):
    if type(value) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("prior work requires an exact identity")
    return value


def _prefix(context):
    return {
        "accepted_targets_m": context.accepted_targets_m,
        "accepted_augmented_coordinates_m": context.accepted_augmented_coordinates_m,
    }


def make_rc_control_prior_work_binding(
    context,
    *,
    accepted_checkpoint,
    arm_identity,
    request_hash,
    solver_config_hash,
    source_binding_hash,
):
    """Runtime-only expected metadata, taken from its actual committed state."""
    return {
        "schema_version": BINDING_PROFILE,
        "arm_identity": arm_identity,
        "problem_contract_hash": context.problem_contract_hash,
        "control_global_dof": context.control_global_dof,
        "control_free_index": context.control_free_index,
        "request_hash": request_hash,
        "solver_config_hash": solver_config_hash,
        "source_binding_hash": source_binding_hash,
        "current_parent_hash": accepted_checkpoint.state_hash,
        "current_parent_predecessor_hash": accepted_checkpoint.parent_state_hash,
        "current_parent_epoch": accepted_checkpoint.epoch,
        "current_parent_step_index": accepted_checkpoint.step_index,
        "accepted_prefix_sha256": _sha(_bytes(_prefix(context))),
        "previous_target_index": len(context.accepted_targets_m) - 2,
    }


def make_rc_control_prior_work_record(binding, original_invocations):
    """Preserve already-written outcome and step bytes without substituting totals."""
    rows = []
    for ordinal, (outcome, step) in enumerate(original_invocations, 1):
        if type(outcome) is not bytes or type(step) is not bytes:
            raise ValueError("original outcome and step bytes required")
        rows.append(
            {
                "ordinal": ordinal,
                "outcome_json": outcome.decode("utf-8"),
                "outcome_sha256": _sha(outcome),
                "step_json": step.decode("utf-8"),
                "step_sha256": _sha(step),
            }
        )
    return {
        "schema_version": PRIOR_WORK_PROFILE,
        "binding": dict(binding),
        "invocations": rows,
    }


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate prior-work JSON key")
        result[key] = value
    return result


def _original(row, name):
    text = row[name + "_json"]
    if type(text) is not str:
        raise ValueError("original prior-work JSON bytes required")
    raw = text.encode("utf-8")
    if (
        not raw
        or len(raw) > MAX_PRIOR_WORK_BYTES
        or _sha(raw) != _identity(row[name + "_sha256"])
    ):
        raise ValueError("original prior-work byte identity differs")
    value = json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("nonfinite prior-work JSON")
        ),
    )
    if type(value) is not dict or _bytes(value) != raw:
        raise ValueError("canonical original prior-work bytes required")
    return value


def _assembly(outcome):
    work = outcome.get("newton_assembly_work")
    if work is None:
        return None
    if (
        type(work) is not dict
        or work.get("schema_version") != "vector-newton-assembly-dispatch-work.v1"
        or work.get("scope") != "vector_newton_problem_assembly_dispatches_only"
    ):
        raise ValueError("unsupported prior assembly work")
    calls = work["calls"]
    if type(calls) is not list:
        raise ValueError("original assembly dispatch list required")
    statuses, phases = Counter(), Counter()
    for ordinal, call in enumerate(calls, 1):
        if (
            type(call) is not dict
            or _natural(call["ordinal"]) != ordinal
            or call["phase"] not in _PHASES
            or type(call["phase"]) is not str
            or call["status"] not in ("returned", "raised")
        ):
            raise ValueError("complete ordered prior assembly dispatches required")
        statuses[call["status"]] += 1
        phases[call["phase"]] += 1
    for key, expected in (
        ("call_count", len(calls)),
        ("returned_count", statuses["returned"]),
        ("exception_count", statuses["raised"]),
        ("in_flight_count", 0),
    ):
        if _natural(work[key]) != expected:
            raise ValueError("prior assembly totals differ")
    return len(calls), phases["line_search"], phases["terminal_refinement"]


def validate_rc_control_prior_work(context) -> RCControlPriorWork:
    """Return immutable counters or raise ValueError for deterministic abstention.

    Only completed dispatch counts are available here. Element/material evaluation,
    outside-Newton work and unrecorded phases are not inferred from Newton counts.
    """
    try:
        return _validate(context)
    except (
        AttributeError,
        KeyError,
        TypeError,
        IndexError,
        OverflowError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("malformed or unavailable causal prior work") from exc


def _validate(context):
    from structural_analysis.benchmark.rc_control_seed_runtime import (
        RCControlSeedContext,
    )

    if type(context) is not RCControlSeedContext:
        raise ValueError("exact RC seed context required")
    binding, record = context.prior_work_binding, context.prior_accepted_transition_work
    if type(binding) is not dict or type(record) is not dict:
        raise ValueError("original prior accepted transition is unavailable")
    if (
        len(_bytes(record)) > MAX_PRIOR_WORK_BYTES
        or set(binding) != _BINDING_KEYS
        or binding["schema_version"] != BINDING_PROFILE
        or set(record) != {"schema_version", "binding", "invocations"}
        or record["schema_version"] != PRIOR_WORK_PROFILE
        or _bytes(record["binding"]) != _bytes(binding)
    ):
        raise ValueError("prior accepted transition binding differs")
    for name in (
        "arm_identity",
        "problem_contract_hash",
        "request_hash",
        "solver_config_hash",
        "source_binding_hash",
        "current_parent_hash",
        "current_parent_predecessor_hash",
        "accepted_prefix_sha256",
    ):
        _identity(binding[name])
    for name in (
        "control_global_dof",
        "control_free_index",
        "current_parent_epoch",
        "current_parent_step_index",
        "previous_target_index",
    ):
        _natural(binding[name])
    if (
        binding["problem_contract_hash"] != context.problem_contract_hash
        or binding["control_global_dof"] != _natural(context.control_global_dof)
        or binding["control_free_index"] != _natural(context.control_free_index)
        or binding["accepted_prefix_sha256"] != _sha(_bytes(_prefix(context)))
        or binding["previous_target_index"] != len(context.accepted_targets_m) - 2
        or len(context.accepted_targets_m) < 2
        or len(context.accepted_targets_m)
        != len(context.accepted_augmented_coordinates_m)
    ):
        raise ValueError("current accepted prefix differs from prior work")
    for value in (
        *context.accepted_targets_m,
        *(v for row in context.accepted_augmented_coordinates_m for v in row),
    ):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("finite exact accepted prefix numbers required")
    rows = record["invocations"]
    if type(rows) is not list or not rows or len(rows) > 3:
        raise ValueError("complete prior-transition invocation list required")
    totals = [0, 0, 0]
    assembly = [0, 0, 0]
    assembly_known = True
    predecessor_bytes = None
    for ordinal, row in enumerate(rows, 1):
        if (
            type(row) is not dict
            or set(row)
            != {"ordinal", "outcome_json", "outcome_sha256", "step_json", "step_sha256"}
            or _natural(row["ordinal"]) != ordinal
        ):
            raise ValueError("ordered original prior invocation records required")
        outcome, step = _original(row, "outcome"), _original(row, "step")
        final = ordinal == len(rows)
        if (
            _natural(outcome["ordinal"]) != ordinal
            or outcome["status"] != "returned"
            or outcome["unknown_work"] is not False
            or outcome["committed"] is not final
            or step["schema_version"] != "small-displacement-rc-fiber-control-step.v1"
            or step["committed"] is not final
            or step["status"] != ("ready" if final else "blocked")
            or step["step_hash"]
            != canonical_hash({k: v for k, v in step.items() if k != "step_hash"})
        ):
            raise ValueError("complete original transition outcome required")
        work, metrics = outcome["work"], step["trial_solution"]["metrics"]
        if (
            type(work) is not dict
            or set(work) != {"core_calls", "newton_iterations", "linear_solves"}
            or _natural(work["core_calls"]) != 1
            or _natural(work["newton_iterations"])
            != _natural(metrics["iteration_count"])
            or _natural(work["linear_solves"])
            != _natural(metrics["linear_solve_count"])
        ):
            raise ValueError("original solver counters differ from invocation work")
        for i, name in enumerate(("core_calls", "newton_iterations", "linear_solves")):
            totals[i] += work[name]
        parent, child, controls = (
            step["parent_checkpoint"],
            step["accepted_checkpoint"],
            step["metrics"],
        )
        for checkpoint in (parent, child):
            if (
                checkpoint["role"] != "committed"
                or checkpoint["problem_contract_hash"]
                != binding["problem_contract_hash"]
            ):
                raise ValueError("prior native problem differs")
            _identity(checkpoint["state_hash"])
            _natural(checkpoint["epoch"])
            _natural(checkpoint["step_index"])
        if (
            parent["state_hash"] != binding["current_parent_predecessor_hash"]
            or parent["epoch"] + 1 != binding["current_parent_epoch"]
            or parent["step_index"] + 1 != binding["current_parent_step_index"]
            or _natural(controls["control_global_dof"]) != context.control_global_dof
            or controls["config_hash"] != binding["solver_config_hash"]
            or controls["target_control_displacement_m"]
            != context.accepted_targets_m[-1]
        ):
            raise ValueError("prior parent, epoch, request or target differs")
        if predecessor_bytes is None:
            predecessor_bytes = _bytes(parent)
        elif _bytes(parent) != predecessor_bytes:
            raise ValueError("retry did not retain the original predecessor")
        if final:
            if (
                child["state_hash"] != binding["current_parent_hash"]
                or child["parent_state_hash"] != parent["state_hash"]
                or child["epoch"] != binding["current_parent_epoch"]
                or child["step_index"] != binding["current_parent_step_index"]
                or _bytes(step["trial_solution"]["augmented_coordinates_m"])
                != _bytes(context.accepted_augmented_coordinates_m[-1])
            ):
                raise ValueError(
                    "prior step does not lead to the current accepted parent"
                )
        elif (
            _bytes(child) != predecessor_bytes
            or outcome["rollback_exact"] is not True
            or controls["rollback_exact"] is not True
        ):
            raise ValueError("prior rejected invocation rollback differs")
        counts = _assembly(outcome)
        if counts is None:
            assembly_known = False
        else:
            assembly = [a + b for a, b in zip(assembly, counts, strict=True)]
    return RCControlPriorWork(
        *totals,
        *(assembly if assembly_known else (None, None, None)),
        binding["current_parent_hash"],
        binding["current_parent_predecessor_hash"],
        binding["current_parent_epoch"],
    )
