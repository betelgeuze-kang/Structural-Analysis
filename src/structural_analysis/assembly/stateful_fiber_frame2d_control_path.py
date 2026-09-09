"""Bounded authored RC displacement paths and explicit full-prefix replay restart.

This experimental contract does not alter the public load-control/J1--J5 path.
Restart validation performs real solves; hashes alone do not prove reachability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Iterable

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    initial_stateful_fiber_frame2d_checkpoint,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_io import (
    dump_stateful_fiber_frame2d_checkpoint_bytes,
    load_stateful_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    StatefulFiberFrame2DDisplacementControlStepAdapter,
    StatefulFiberFrame2DDisplacementControlStepResult,
    solve_stateful_fiber_frame2d_displacement_control_step,
    validate_stateful_fiber_frame2d_control_problem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)

from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadStepResult,
    solve_stateful_fiber_frame2d_constant_load_preload,
)

CONTROL_PATH_SCHEMA = "stateful-fiber-frame2d-control-path.v1"
CONTROL_RESTART_SCHEMA = "stateful-fiber-frame2d-control-restart.v1"
CONSTANT_CONTROL_PATH_SCHEMA = "stateful-fiber-frame2d-control-path.v2"
CONSTANT_CONTROL_RESTART_SCHEMA = "stateful-fiber-frame2d-control-restart.v2"
CONTROL_RESTART_MAX_BYTES = 8 * 1024 * 1024
_CLAIMS = {
    "experimental_small_displacement_rc_control": True,
    "public_j1_j5_authority": False,
    "independent_physical_validation": False,
    "general_cyclic_material_validation": False,
    "global_capacity_verified": False,
    "performance_improvement_claimed": False,
    "design_authority": False,
    "production_promotion_eligible": False,
    "hashes_authenticate_source": False,
}


def _json(value: Any) -> bytes:
    """Exact canonical JSON including the sign of zero, as in checkpoint I/O."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _integer(value: Any, name: str, maximum: int, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _number(value: Any) -> float:
    if type(value) not in (int, float) or (
        type(value) is int and abs(value) > 2**53 - 1
    ):
        raise ValueError("control targets must be finite exact numeric values")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("control targets must be finite") from exc
    if not math.isfinite(number):
        raise ValueError("control targets must be finite")
    return number


def _targets(values: Iterable[float], maximum: int) -> tuple[float, ...]:
    if isinstance(values, (str, bytes, bytearray, dict)):
        raise ValueError("targets_m must be an iterable of numbers")
    try:
        iterator = iter(values)
    except TypeError as exc:
        raise ValueError("targets_m must be an iterable of numbers") from exc
    result: list[float] = []
    for value in iterator:
        if len(result) >= maximum:
            raise ValueError("cumulative target budget exceeded")
        result.append(_number(value))
    return tuple(result)


def _directions(
    targets: tuple[float, ...], origin: float = 0.0
) -> tuple[tuple[int, ...], int]:
    previous = origin
    directions: list[int] = []
    reversals = 0
    for target in targets:
        if target == previous:
            raise ValueError("successive control targets must differ")
        direction = 1 if target > previous else -1
        reversals += bool(directions and direction != directions[-1])
        directions.append(direction)
        previous = target
    return tuple(directions), reversals


def _scope(
    problem,
    config,
    control_global_dof,
    allow_reversals,
    maximum_reversals,
    maximum_targets,
):
    return {
        "problem_contract_hash": problem.contract_hash,
        "case_id": problem.case_id,
        "configuration": config.to_manifest(),
        "configuration_hash": config.contract_hash,
        "control_global_dof": control_global_dof,
        "control_unit": "m",
        "allow_reversals": allow_reversals,
        "maximum_reversals": maximum_reversals,
        "maximum_targets": maximum_targets,
    }


def _duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("restart contains duplicate JSON keys")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("restart contains a non-finite number")


def _decode_restart(data, problem, scope):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("restart must be canonical bytes")
    raw = bytes(data)
    if len(raw) > CONTROL_RESTART_MAX_BYTES:
        raise ValueError("restart exceeds byte bound")
    # Bound nesting before recursive JSON decoding; checkpoint states fit well below 64.
    text = raw.decode("utf-8")
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 64:
                raise ValueError("restart nesting exceeds bound")
        elif char in "]}":
            depth -= 1
    payload = json.loads(text, object_pairs_hook=_duplicates, parse_constant=_nonfinite)
    expected_keys = {
        "schema_version",
        "scope",
        "accepted_targets_m",
        "accepted_step_bindings",
        "direction",
        "reversal_count",
        "terminal_checkpoint",
        "terminal_checkpoint_sha256",
        "claims",
        "artifact_hash",
    }
    if problem.constant_external_loads:
        expected_keys |= {"preload_checkpoint", "preload_step_hash"}
    if type(payload) is not dict or set(payload) != expected_keys:
        raise ValueError("restart fields invalid")
    if _json(payload) != raw:
        raise ValueError("restart is not canonical JSON")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_hash"}
    if payload["artifact_hash"] != _hash(_json(unsigned)):
        raise ValueError("restart artifact hash mismatch")
    schema = (
        CONSTANT_CONTROL_RESTART_SCHEMA
        if problem.constant_external_loads
        else CONTROL_RESTART_SCHEMA
    )
    if payload["schema_version"] != schema or _json(payload["scope"]) != _json(scope):
        raise ValueError("restart source/configuration/control/budget mismatch")
    if _json(payload["claims"]) != _json(_CLAIMS):
        raise ValueError("restart claims mismatch")
    if type(payload["accepted_targets_m"]) is not list:
        raise ValueError("restart target prefix invalid")
    prefix = _targets(payload["accepted_targets_m"], scope["maximum_targets"])
    if _json(list(prefix)) != _json(payload["accepted_targets_m"]):
        raise ValueError("restart target numeric representation changed")
    genesis = initial_stateful_fiber_frame2d_checkpoint(problem)
    origin = 0.0
    previous_hash = genesis.state_hash
    epoch_offset = 0
    if problem.constant_external_loads:
        preload = load_stateful_fiber_frame2d_checkpoint_bytes(
            _json(payload["preload_checkpoint"]), problem
        )
        if (
            preload.epoch != 1
            or preload.step_index != 1
            or preload.load_factor != 0.0
            or preload.parent_state_hash != genesis.state_hash
        ):
            raise ValueError("restart preload ancestry invalid")
        if type(payload["preload_step_hash"]) is not str or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", payload["preload_step_hash"]
        ):
            raise ValueError("restart preload step hash invalid")
        previous_hash = preload.state_hash
        origin = preload.global_displacements[scope["control_global_dof"]]
        epoch_offset = 1
    directions, reversals = _directions(prefix, origin)
    if type(payload["direction"]) is not int or payload["direction"] != (
        directions[-1] if directions else 0
    ):
        raise ValueError("restart direction mismatch")
    if (
        type(payload["reversal_count"]) is not int
        or payload["reversal_count"] != reversals
    ):
        raise ValueError("restart reversal count mismatch")
    bindings = payload["accepted_step_bindings"]
    if type(bindings) is not list or len(bindings) != len(prefix):
        raise ValueError("restart accepted step bindings invalid")
    binding_keys = {
        "target_control_displacement_m",
        "step_hash",
        "parent_checkpoint_hash",
        "accepted_checkpoint_hash",
        "direction",
        "reversal_count",
    }
    for index, binding in enumerate(bindings):
        if type(binding) is not dict or set(binding) != binding_keys:
            raise ValueError("restart step binding fields invalid")
        if _json(binding["target_control_displacement_m"]) != _json(prefix[index]):
            raise ValueError("restart step target binding mismatch")
        if (
            type(binding["direction"]) is not int
            or binding["direction"] != directions[index]
        ):
            raise ValueError("restart step direction invalid")
        expected_reversals = sum(
            a != b for a, b in zip(directions[:index], directions[1 : index + 1])
        )
        if (
            type(binding["reversal_count"]) is not int
            or binding["reversal_count"] != expected_reversals
        ):
            raise ValueError("restart step reversal count invalid")
        for key in ("step_hash", "parent_checkpoint_hash", "accepted_checkpoint_hash"):
            if type(binding[key]) is not str or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", binding[key]
            ):
                raise ValueError("restart step hash invalid")
        if binding["parent_checkpoint_hash"] != previous_hash:
            raise ValueError("restart step parent chain mismatch")
        previous_hash = binding["accepted_checkpoint_hash"]
    checkpoint_bytes = _json(payload["terminal_checkpoint"])
    if _hash(checkpoint_bytes) != payload["terminal_checkpoint_sha256"]:
        raise ValueError("restart checkpoint byte hash mismatch")
    checkpoint = load_stateful_fiber_frame2d_checkpoint_bytes(checkpoint_bytes, problem)
    if checkpoint.state_hash != previous_hash:
        raise ValueError("restart terminal step hash mismatch")
    if (
        checkpoint.epoch != len(prefix) + epoch_offset
        or checkpoint.step_index != len(prefix) + epoch_offset
    ):
        raise ValueError("restart checkpoint epoch/prefix mismatch")
    if (
        prefix
        and abs(
            checkpoint.global_displacements[scope["control_global_dof"]] - prefix[-1]
        )
        > scope["configuration"]["control_tolerance_m"]
    ):
        raise ValueError("restart terminal control coordinate mismatch")
    return payload, prefix, checkpoint


def _binding(step, target, direction, reversals):
    return {
        "target_control_displacement_m": target,
        "step_hash": step.step_hash,
        "parent_checkpoint_hash": step.parent_checkpoint.state_hash,
        "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
        "direction": direction,
        "reversal_count": reversals,
    }


def _counts(attempts):
    linear = iterations = unknown = 0
    for attempt in attempts:
        if attempt["step"] is None:
            unknown += 1
            continue
        metrics = attempt["solver_work"]
        solves = metrics.get("linear_solve_count")
        count = metrics.get("iteration_count")
        if type(solves) is int and solves >= 0 and type(count) is int and count >= 0:
            linear += solves
            iterations += count
        else:
            unknown += 1
    return {
        "attempted_step_count": len(attempts),
        "known_linear_solve_count": linear,
        "known_newton_iteration_count": iterations,
        "unknown_solver_work_attempt_count": unknown,
    }


class StatefulFiberFrame2DControlExecutionError(ValueError):
    """Invalid execution, with observed calls retained but no state export authority."""

    def __init__(self, message, attempts, context, *, replay_attempts=()):
        super().__init__(message)
        self._report = _json(
            {
                "status": "invalid_execution",
                "failure": message,
                "context": context,
                "attempts": attempts,
                "work": _counts(attempts),
                "prior_replay_attempts": list(replay_attempts),
                "prior_replay_work": _counts(replay_attempts),
                "total_work": _counts([*replay_attempts, *attempts]),
                "state_or_restart_export_available": False,
            }
        )

    def to_dict(self):
        return json.loads(self._report)


def _execute_raw(
    problem, initial, targets, control_global_dof, config, source_hash, *, phase
):
    """Exactly one core call per authored target, without recursive restart or retries."""
    accepted = initial
    steps = []
    attempts: list[dict[str, Any]] = []
    context = {
        "phase": phase,
        "problem_contract_hash": source_hash,
        "configuration_hash": config.contract_hash,
        "control_global_dof": control_global_dof,
        "initial_checkpoint_hash": initial.state_hash,
        "requested_targets_m": list(targets),
    }
    for index, target in enumerate(targets):
        parent_bytes = accepted.canonical_bytes()
        parent_hash = accepted.state_hash

        def source_unchanged():
            try:
                return (
                    accepted.canonical_bytes() == parent_bytes
                    and problem.contract_hash == source_hash
                    and config.contract_hash == context["configuration_hash"]
                )
            except Exception:
                return False

        def reject(exc, stage):
            # Unvalidated returned metrics cannot establish known solver work.
            # The call itself is counted, even if source inspection also failed.
            current = {
                "target_control_displacement_m": target,
                "committed": False,
                "parent_checkpoint_hash": parent_hash,
                "accepted_checkpoint_hash": None,
                "parent_checkpoint_immutable": source_unchanged(),
                "rollback_exact": None,
                "step": None,
                "solver_work": None,
                "failure": {"type": type(exc).__name__, "message": str(exc)},
                "artifact_contract_pass": False,
            }
            return StatefulFiberFrame2DControlExecutionError(
                f"control execution rejected: {stage}: {exc}",
                [*attempts, current],
                context
                | {
                    "failure_stage": stage,
                    "failed_target_index": index,
                    "last_verified_checkpoint_hash": parent_hash,
                    "unattempted_targets_m": list(targets[index + 1 :]),
                },
            )

        try:
            step = solve_stateful_fiber_frame2d_displacement_control_step(
                problem,
                accepted,
                control_global_dof=control_global_dof,
                target_control_displacement_m=target,
                config=config,
            )
        except Exception as exc:
            if not source_unchanged():
                raise reject(exc, "core_exception_source_mutation") from exc
            attempts.append(
                {
                    "target_control_displacement_m": target,
                    "committed": False,
                    "parent_checkpoint_hash": accepted.state_hash,
                    "accepted_checkpoint_hash": accepted.state_hash,
                    "parent_checkpoint_immutable": True,
                    "rollback_exact": True,
                    "step": None,
                    "solver_work": None,
                    "failure": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
            break
        try:
            if not source_unchanged():
                raise ValueError("control source mutated during step")
            if type(step) is not StatefulFiberFrame2DDisplacementControlStepResult:
                raise ValueError("control step result type invalid")
            if step.parent_checkpoint.canonical_bytes() != parent_bytes:
                raise ValueError("control step parent binding mismatch")
            validate_stateful_fiber_frame2d_checkpoint(
                problem, step.accepted_checkpoint
            )
            if type(step.committed) is not bool:
                raise ValueError("control step committed flag invalid")
            if step.committed:
                child = step.accepted_checkpoint
                if (
                    step.status != "ready"
                    or child.parent_state_hash != accepted.state_hash
                    or child.epoch != accepted.epoch + 1
                    or child.step_index != accepted.step_index + 1
                ):
                    raise ValueError("control accepted checkpoint ancestry mismatch")
                if (
                    abs(child.global_displacements[control_global_dof] - target)
                    > config.control_tolerance_m
                ):
                    raise ValueError("control accepted checkpoint target mismatch")
            elif step.accepted_checkpoint.canonical_bytes() != parent_bytes:
                raise ValueError("control rejected step rollback mismatch")
            # Snapshot now: later core calls may expose mutation of a retained step.
            # Previously observed work must survive even non-finite later mutations.
            step_payload = json.loads(_json(step.to_dict()))
            solver_work = json.loads(_json(dict(step.trial_solution.metrics)))
        except Exception as exc:
            raise reject(exc, "returned_step_validation") from exc
        steps.append(step)
        attempts.append(
            {
                "target_control_displacement_m": target,
                "committed": step.committed,
                "parent_checkpoint_hash": accepted.state_hash,
                "accepted_checkpoint_hash": step.accepted_checkpoint.state_hash,
                "parent_checkpoint_immutable": True,
                "rollback_exact": None if step.committed else True,
                "step": step_payload,
                "solver_work": solver_work,
                "failure": None,
            }
        )
        if not step.committed:
            break
        accepted = step.accepted_checkpoint
    return accepted, tuple(steps), attempts


class StatefulFiberFrame2DControlRestartError(ValueError):
    """Rejected replay with its attempted verification work explicitly retained."""

    def __init__(self, message, attempts, *, execution_failure=None):
        super().__init__(message)
        report = {
            "status": "invalid_restart",
            "failure": message,
            "replay_attempts": attempts,
            "replay_work": _counts(attempts),
        }
        if execution_failure is not None:
            report["execution_failure"] = execution_failure
        self._report = _json(report)

    def to_dict(self):
        return json.loads(self._report)


def _execute_preload(problem, config):
    """One actual lambda-zero solve, with failure and source-bound work retained."""
    genesis = initial_stateful_fiber_frame2d_checkpoint(problem)
    source_hash, config_hash = problem.contract_hash, config.contract_hash
    attempt = {"phase": "constant_load_preload", "step": None, "solver_work": None}
    context = {
        "phase": "constant_load_preload",
        "problem_contract_hash": source_hash,
        "configuration_hash": config_hash,
    }
    try:
        step = solve_stateful_fiber_frame2d_constant_load_preload(
            problem, config=config.newton
        )
        if (
            type(step) is not StatefulFiberFrame2DLoadStepResult
            or problem.contract_hash != source_hash
            or config.contract_hash != config_hash
            or step.parent_checkpoint.canonical_bytes() != genesis.canonical_bytes()
            or type(step.committed) is not bool
        ):
            raise ValueError("preload source/parent/result binding mismatch")
        child = step.accepted_checkpoint
        validate_stateful_fiber_frame2d_checkpoint(problem, child)
        if step.committed:
            if (
                step.status != "ready"
                or child.epoch != 1
                or child.step_index != 1
                or child.load_factor != 0.0
                or child.parent_state_hash != genesis.state_hash
            ):
                raise ValueError("preload accepted ancestry mismatch")
        elif child.canonical_bytes() != genesis.canonical_bytes():
            raise ValueError("preload rollback mismatch")
        attempt["step"] = json.loads(_json(step.to_dict()))
        attempt["solver_work"] = json.loads(_json(dict(step.trial_solution.metrics)))
        if not step.committed:
            raise ValueError(
                "constant-load preload did not converge; control not attempted"
            )
    except Exception as exc:
        raise StatefulFiberFrame2DControlExecutionError(
            str(exc), [attempt], context
        ) from exc
    return step, attempt


@dataclass(frozen=True)
class StatefulFiberFrame2DControlPathResult:
    initial_checkpoint: StatefulFiberFrame2DCheckpoint
    final_checkpoint: StatefulFiberFrame2DCheckpoint
    steps: tuple[StatefulFiberFrame2DDisplacementControlStepResult, ...]
    replayed_steps: tuple[StatefulFiberFrame2DDisplacementControlStepResult, ...]
    _problem: StatefulFiberFrame2DProblem = field(repr=False)
    _config: StatefulFiberFrame2DDisplacementControlConfig = field(repr=False)
    _payload: bytes = field(repr=False)
    _restart: bytes = field(repr=False)
    _checkpoint_snapshots: tuple[tuple[StatefulFiberFrame2DCheckpoint, bytes], ...] = (
        field(repr=False)
    )
    _step_snapshots: tuple[bytes, ...] = field(repr=False)
    preload_step: StatefulFiberFrame2DLoadStepResult | None = field(
        default=None, repr=False
    )

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self._payload)
        if self._problem.contract_hash != payload["scope"][
            "problem_contract_hash"
        ] or _json(self._config.to_manifest()) != _json(
            payload["scope"]["configuration"]
        ):
            raise ValueError("control path source changed after execution")
        for checkpoint, key in (
            (self.initial_checkpoint, "initial_checkpoint"),
            (self.final_checkpoint, "final_checkpoint"),
        ):
            if type(checkpoint) is not StatefulFiberFrame2DCheckpoint or _json(
                checkpoint.to_dict()
            ) != _json(payload[key]):
                raise ValueError("control path checkpoint field binding changed")
        for checkpoint, raw in self._checkpoint_snapshots:
            validate_stateful_fiber_frame2d_checkpoint(self._problem, checkpoint)
            if checkpoint.canonical_bytes() != raw:
                raise ValueError("control path checkpoint changed after execution")
        for steps, key, work_key in (
            (self.replayed_steps, "replay_attempts", "prefix_replay_work"),
            (self.steps, "attempts", "suffix_work"),
        ):
            receipts = [row["step"] for row in payload[key] if row["step"] is not None]
            if type(steps) is not tuple or len(steps) != len(receipts):
                raise ValueError("control path replay/suffix step group changed")
            if _json(_counts(payload[key])) != _json(payload["metrics"][work_key]):
                raise ValueError("control path replay/suffix work binding changed")
            for step, receipt in zip(steps, receipts, strict=True):
                if type(step) is not StatefulFiberFrame2DDisplacementControlStepResult:
                    raise ValueError("control path step type changed")
                if _json(step.to_dict()) != _json(receipt):
                    raise ValueError("control path step changed in replay/suffix group")
        for step, raw in zip(
            (*self.replayed_steps, *self.steps), self._step_snapshots, strict=True
        ):
            if _json(step.to_dict()) != raw:
                raise ValueError("control path step changed after execution")
        preload_attempts = payload.get("preload_attempts", [])
        if self._problem.constant_external_loads:
            if (
                type(self.preload_step) is not StatefulFiberFrame2DLoadStepResult
                or len(preload_attempts) != 1
                or _json(self.preload_step.to_dict())
                != _json(preload_attempts[0]["step"])
                or not self.preload_step.committed
            ):
                raise ValueError("control path preload source changed")
            if _counts(preload_attempts) != payload["metrics"]["preload_work"]:
                raise ValueError("control path preload work changed")
        elif self.preload_step is not None or preload_attempts:
            raise ValueError("unexpected control path preload")
        if (
            _counts(
                [*preload_attempts, *payload["replay_attempts"], *payload["attempts"]]
            )
            != payload["metrics"]["total_work"]
        ):
            raise ValueError("control path total work changed")
        return payload

    @property
    def status(self):
        return self.to_dict()["status"]

    @property
    def path_hash(self):
        return self.to_dict()["path_hash"]

    @property
    def targets_m(self):
        return tuple(self.to_dict()["targets_m"])

    @property
    def accepted_target_prefix_m(self):
        return tuple(self.to_dict()["accepted_target_prefix_m"])

    @property
    def unattempted_targets_m(self):
        return tuple(self.to_dict()["unattempted_targets_m"])

    @property
    def metrics(self):
        return self.to_dict()["metrics"]

    def restart_artifact(self) -> bytes:
        self.to_dict()
        return self._restart


def run_stateful_fiber_frame2d_control_path(
    problem: StatefulFiberFrame2DProblem,
    targets_m: Iterable[float],
    *,
    control_global_dof: int,
    config: StatefulFiberFrame2DDisplacementControlConfig | None = None,
    allow_reversals: bool = False,
    maximum_reversals: int = 0,
    maximum_targets: int = 255,
    restart: bytes | bytearray | memoryview | None = None,
) -> StatefulFiberFrame2DControlPathResult:
    """Execute a bounded suffix; validate a restart by solving its complete prefix.

    Failed attempts stay in this result, never in the accepted restart prefix.
    Prefix verification work is separate from the newly requested denominator.
    An empty suffix is permitted only for explicit restart verification.
    """
    if type(problem) is not StatefulFiberFrame2DProblem:
        raise ValueError("problem must be a StatefulFiberFrame2DProblem")
    if (
        config is not None
        and type(config) is not StatefulFiberFrame2DDisplacementControlConfig
    ):
        raise ValueError(
            "config must be a StatefulFiberFrame2DDisplacementControlConfig"
        )
    cfg = config or StatefulFiberFrame2DDisplacementControlConfig()
    _integer(control_global_dof, "control_global_dof", problem.global_dof_count - 1)
    _integer(maximum_targets, "maximum_targets", 255, 1)
    _integer(maximum_reversals, "maximum_reversals", 254)
    if type(allow_reversals) is not bool or (
        not allow_reversals and maximum_reversals != 0
    ):
        raise ValueError("reversals require an explicit boolean opt-in and budget")
    scope = _scope(
        problem,
        cfg,
        control_global_dof,
        allow_reversals,
        maximum_reversals,
        maximum_targets,
    )
    genesis = initial_stateful_fiber_frame2d_checkpoint(problem)
    prior = None
    prefix: tuple[float, ...] = ()
    persisted = genesis
    restart_bytes_input = None
    if restart is not None:
        if not isinstance(restart, (bytes, bytearray, memoryview)):
            raise ValueError("restart must be canonical bytes")
        # Bind the bytes actually decoded, even if a caller owns a mutable buffer.
        restart_bytes_input = bytes(restart)
        prior, prefix, persisted = _decode_restart(restart_bytes_input, problem, scope)
    targets = _targets(targets_m, maximum_targets - len(prefix))
    if not targets and restart is None:
        raise ValueError("targets_m must be non-empty")
    validate_stateful_fiber_frame2d_control_problem(problem, control_global_dof)
    preload_step = None
    preload_attempts = []
    control_genesis = genesis
    origin = 0.0
    if problem.constant_external_loads:
        preload_step, preload_attempt = _execute_preload(problem, cfg)
        preload_attempts = [preload_attempt]
        control_genesis = preload_step.accepted_checkpoint
        origin = control_genesis.global_displacements[control_global_dof]
        if prior is not None and (
            _json(prior["preload_checkpoint"]) != _json(control_genesis.to_dict())
            or prior["preload_step_hash"] != _hash(_json(preload_step.to_dict()))
        ):
            raise StatefulFiberFrame2DControlRestartError(
                "restart preload differs from fresh source solve", preload_attempts
            )
    combined = prefix + targets
    try:
        directions, reversals = _directions(combined, origin)
        if reversals > maximum_reversals or (reversals and not allow_reversals):
            raise ValueError("cumulative reversal budget exceeded")
        preflight_target = combined[0] if combined else origin + 1.0
        StatefulFiberFrame2DDisplacementControlStepAdapter(
            problem, control_genesis, control_global_dof, preflight_target, cfg
        )
    except ValueError as exc:
        if preload_attempts:
            raise StatefulFiberFrame2DControlExecutionError(
                str(exc), preload_attempts, {"phase": "post_preload_control_preflight"}
            ) from exc
        raise
    replay_steps: tuple[StatefulFiberFrame2DDisplacementControlStepResult, ...] = ()
    replay_attempts = []
    initial = control_genesis
    if prior is not None:
        try:
            initial, replay_steps, replay_attempts = _execute_raw(
                problem,
                control_genesis,
                prefix,
                control_global_dof,
                cfg,
                scope["problem_contract_hash"],
                phase="prefix_replay",
            )
        except StatefulFiberFrame2DControlExecutionError as exc:
            failure = exc.to_dict()
            raise StatefulFiberFrame2DControlRestartError(
                "restart prefix execution invalid",
                [*preload_attempts, *failure["attempts"]],
                execution_failure=failure,
            ) from exc
        if len(replay_steps) != len(prefix) or not all(
            step.committed for step in replay_steps
        ):
            raise StatefulFiberFrame2DControlRestartError(
                "restart prefix could not be replayed",
                [*preload_attempts, *replay_attempts],
            )
        prefix_directions, _ = _directions(prefix, origin)
        bindings = [
            _binding(
                step,
                target,
                direction,
                sum(
                    a != b
                    for a, b in zip(
                        prefix_directions[:index], prefix_directions[1 : index + 1]
                    )
                ),
            )
            for index, (step, target, direction) in enumerate(
                zip(replay_steps, prefix, prefix_directions, strict=True)
            )
        ]
        if (
            _json(bindings) != _json(prior["accepted_step_bindings"])
            or initial.canonical_bytes() != persisted.canonical_bytes()
            or dump_stateful_fiber_frame2d_checkpoint_bytes(problem, initial)
            != _json(prior["terminal_checkpoint"])
        ):
            raise StatefulFiberFrame2DControlRestartError(
                "restart replay/checkpoint binding mismatch",
                [*preload_attempts, *replay_attempts],
            )
    try:
        final, steps, attempts = _execute_raw(
            problem,
            initial,
            targets,
            control_global_dof,
            cfg,
            scope["problem_contract_hash"],
            phase="suffix",
        )
    except StatefulFiberFrame2DControlExecutionError as exc:
        failure = exc.to_dict()
        raise StatefulFiberFrame2DControlExecutionError(
            str(exc),
            failure["attempts"],
            failure["context"],
            replay_attempts=[*preload_attempts, *replay_attempts],
        ) from exc
    accepted_count = sum(step.committed for step in steps)
    accepted_prefix = prefix + targets[:accepted_count]
    accepted_directions, accepted_reversals = _directions(accepted_prefix, origin)
    accepted_steps = (*replay_steps, *(step for step in steps if step.committed))
    accepted_bindings = [
        _binding(
            step,
            target,
            direction,
            sum(
                a != b
                for a, b in zip(
                    accepted_directions[:index], accepted_directions[1 : index + 1]
                )
            ),
        )
        for index, (step, target, direction) in enumerate(
            zip(accepted_steps, accepted_prefix, accepted_directions, strict=True)
        )
    ]
    checkpoint_bytes = dump_stateful_fiber_frame2d_checkpoint_bytes(problem, final)
    restart_payload = {
        "schema_version": (
            CONSTANT_CONTROL_RESTART_SCHEMA
            if preload_step is not None
            else CONTROL_RESTART_SCHEMA
        ),
        "scope": scope,
        "accepted_targets_m": list(accepted_prefix),
        "accepted_step_bindings": accepted_bindings,
        "direction": accepted_directions[-1] if accepted_directions else 0,
        "reversal_count": accepted_reversals,
        "terminal_checkpoint": json.loads(checkpoint_bytes),
        "terminal_checkpoint_sha256": _hash(checkpoint_bytes),
        "claims": dict(_CLAIMS),
    }
    if preload_step is not None:
        restart_payload["preload_checkpoint"] = control_genesis.to_dict()
        restart_payload["preload_step_hash"] = _hash(_json(preload_step.to_dict()))
    restart_payload["artifact_hash"] = _hash(_json(restart_payload))
    restart_bytes = _json(restart_payload)
    if len(restart_bytes) > CONTROL_RESTART_MAX_BYTES:
        raise ValueError("restart exceeds byte bound")
    status = "ready" if accepted_count == len(targets) else "blocked"
    payload = {
        "schema_version": (
            CONSTANT_CONTROL_PATH_SCHEMA
            if preload_step is not None
            else CONTROL_PATH_SCHEMA
        ),
        "status": status,
        "scope": scope,
        "targets_m": list(targets),
        "accepted_target_prefix_m": list(accepted_prefix),
        "unattempted_targets_m": list(targets[len(attempts) :]),
        "requested_directions": list(directions),
        "requested_reversal_count": reversals,
        "accepted_direction": accepted_directions[-1] if accepted_directions else 0,
        "accepted_reversal_count": accepted_reversals,
        "initial_checkpoint": initial.to_dict(),
        "final_checkpoint": final.to_dict(),
        "attempts": attempts,
        "replay_attempts": replay_attempts,
        "restart_input_sha256": None
        if restart_bytes_input is None
        else _hash(restart_bytes_input),
        "restart_artifact_hash": restart_payload["artifact_hash"],
        "metrics": {
            "requested_target_count": len(targets),
            "attempted_target_count": len(attempts),
            "accepted_target_count": accepted_count,
            "failed_target_count": len(attempts) - accepted_count,
            "unattempted_target_count": len(targets) - len(attempts),
            "cumulative_accepted_target_count": len(accepted_prefix),
            "prefix_replayed_step_count": len(replay_attempts),
            "prefix_replay_work": _counts(replay_attempts),
            "suffix_work": _counts(attempts),
            "total_work": _counts([*preload_attempts, *replay_attempts, *attempts]),
            "restart_verification_scope": "full_genesis_prefix_solver_replay"
            if restart is not None
            else "not_requested",
            "hidden_retries_or_cutbacks": 0,
        },
        "claims": dict(_CLAIMS),
    }
    if preload_step is not None:
        payload["preload_attempts"] = preload_attempts
        payload["metrics"]["preload_work"] = _counts(preload_attempts)
        payload["metrics"]["restart_verification_scope"] = (
            "full_genesis_preload_prefix_solver_replay"
            if restart is not None
            else "not_requested"
        )
    payload["path_hash"] = _hash(_json(payload))
    all_steps = (*replay_steps, *steps)
    checkpoints = (
        genesis,
        control_genesis,
        initial,
        final,
        *(step.accepted_checkpoint for step in all_steps),
    )
    result = StatefulFiberFrame2DControlPathResult(
        initial,
        final,
        steps,
        replay_steps,
        problem,
        cfg,
        _json(payload),
        restart_bytes,
        tuple((checkpoint, checkpoint.canonical_bytes()) for checkpoint in checkpoints),
        tuple(_json(step.to_dict()) for step in all_steps),
        preload_step,
    )
    result.to_dict()
    return result
