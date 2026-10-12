"""Experimental corotational RC artifacts with fresh numerical verification.

Replay is charged work. Artifact equality is not independent physical validation
or managed execution authority; durable workers must reserve each invocation.
"""

from dataclasses import asdict, dataclass
import hashlib
from itertools import islice
import json

from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision import (
    run_corotational_control_subdivision,
    _source_identity,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    _controlled_free_index,
    _finite,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


SCHEMA = "experimental-rc-corotational-control-result.v1"
MAX_BYTES = 64 * 1024 * 1024


def _json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class RCCorotationalControlArtifacts:
    result_bytes: bytes
    continuation_bytes: bytes | None


class RCCorotationalControlExecutionError(RuntimeError):
    def __init__(self, work):
        self.work = dict(work, unavailable_execution_work=True)
        super().__init__(
            "corotational execution failed; partial work may be unavailable"
        )


def _prepare(model, targets_m, options):
    compiled = compile_rc_corotational_control_model(
        model,
        fixed_nodal_loads=options["fixed_nodal_loads"],
        experimental_pin_roller_beam=options["experimental_pin_roller_beam"],
        experimental_fixed_guided_axial=options["experimental_fixed_guided_axial"],
    )
    targets = tuple(
        _finite(v, name="control displacement") for v in islice(targets_m, 256)
    )
    if not 1 <= len(targets) <= 255 or any(
        a == b for a, b in zip(targets, targets[1:])
    ):
        raise ValueError(
            "targets require 1 to 255 finite entries without adjacent duplicates"
        )
    node, component = options["control_node_id"], options["control_component"]
    if type(node) is not str or node not in compiled.node_ids:
        raise ValueError("unknown control node")
    if type(component) is not str or component not in ("UX", "UY"):
        raise ValueError("control component must be UX or UY")
    dof = 3 * compiled.node_ids.index(node) + (component == "UY")
    _controlled_free_index(compiled.problem, dof)
    budget, depth, limit = (
        options[k]
        for k in (
            "maximum_attempt_count",
            "maximum_subdivision_depth",
            "attempt_limit_per_call",
        )
    )
    if type(budget) is not int or not 1 <= budget <= 4096:
        raise ValueError("maximum_attempt_count must be in [1, 4096]")
    if type(depth) is not int or not 0 <= depth <= 20:
        raise ValueError("maximum_subdivision_depth must be in [0, 20]")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 4096):
        raise ValueError("attempt_limit_per_call must be in [1, 4096]")
    config = options["config"]
    if config is None:
        config = StatefulCorotationalFiberFrame2DDisplacementControlConfig()
    if type(config) is not StatefulCorotationalFiberFrame2DDisplacementControlConfig:
        raise ValueError("invalid control config")
    preload_config = options["preload_config"]
    if preload_config is None:
        preload_config = NewtonRaphsonConfig()
    if type(preload_config) is not NewtonRaphsonConfig:
        raise ValueError("invalid preload config")
    if preload_config.max_iterations > 200:
        raise ValueError("preload maximum iterations must not exceed 200")
    restart, prior_spent = options["restart"], 0
    if restart is not None:
        envelope = strict_json_object_bytes(restart, maximum_bytes=16 * 1024 * 1024)
        if (
            set(envelope) != {"payload", "sha256"}
            or type(envelope["payload"]) is not dict
        ):
            raise ValueError("invalid restart envelope")
        if envelope["sha256"] != _sha(_json(envelope["payload"])):
            raise ValueError("restart checksum mismatch")
        prior_spent = envelope["payload"].get("spent")
        if type(prior_spent) is not int or not 1 <= prior_spent <= budget:
            raise ValueError("invalid restart spent budget")
    request = {
        "model_checksum": compiled.source_model_checksum,
        "input_checksum": compiled.source_input_checksum,
        "problem_hash": compiled.problem.contract_hash,
        "source_identity": _source_identity(),
        "targets_m": targets,
        "control_global_dof": dof,
        "config": asdict(config),
        "preload_config": asdict(preload_config),
        "maximum_attempt_count": budget,
        "maximum_subdivision_depth": depth,
        "attempt_limit_per_call": limit,
        "restart_sha256": None if restart is None else _sha(restart),
    }
    _json(request)
    return compiled, targets, dof, config, preload_config, prior_spent, request


def _response(compiled, step, phase):
    child, assembly = step.accepted_checkpoint, step.trial_assembly
    if (
        not step.committed
        or assembly.parent_checkpoint_hash != step.parent_checkpoint.state_hash
    ):
        raise ValueError("response has no committed source transition")
    if tuple(s.canonical_bytes() for s in assembly.trial_element_states) != tuple(
        s.canonical_bytes() for s in child.element_states
    ):
        raise ValueError("response material state differs from accepted checkpoint")
    return {
        "phase": phase,
        "checkpoint_hash": child.state_hash,
        "parent_checkpoint_hash": step.parent_checkpoint.state_hash,
        "load_factor": child.load_factor,
        "nodes": [
            {
                "node_id": node,
                "displacements_m_rad": assembly.global_displacements[
                    3 * i : 3 * i + 3
                ].tolist(),
                "external_loads_kn_knm": assembly.external_loads_global[
                    3 * i : 3 * i + 3
                ].tolist(),
                "reactions_kn_knm": assembly.reactions_global[
                    3 * i : 3 * i + 3
                ].tolist(),
            }
            for i, node in enumerate(compiled.node_ids)
        ],
        "members": [member.to_dict() for member in assembly.member_assemblies],
    }


def analyze_rc_corotational_control(
    model,
    targets_m,
    *,
    control_node_id,
    control_component,
    fixed_nodal_loads=(),
    config=None,
    preload_config=None,
    maximum_attempt_count=255,
    maximum_subdivision_depth=8,
    attempt_limit_per_call=None,
    restart=None,
    experimental_pin_roller_beam=False,
    experimental_fixed_guided_axial=False,
):
    options = dict(locals())
    compiled, targets, dof, cfg, preload_cfg, prior_spent, request = _prepare(
        model, targets_m, options
    )
    work = {
        "preload_solver_calls": 0,
        "restart_replay_solver_calls": 0,
        "control_solver_calls": 0,
        "unavailable_execution_work": False,
    }
    responses, continuation, path = [], None, None
    response_bytes = 0

    def append_response(step, phase):
        nonlocal response_bytes
        row = _response(compiled, step, phase)
        response_bytes += len(_json(row)) + 1
        if response_bytes > MAX_BYTES:
            raise ValueError("response history exceeds bounded size")
        responses.append(row)

    try:
        p = compiled.problem
        work["preload_solver_calls"] += 1
        preload = solve_stateful_corotational_fiber_frame2d_load_step(
            p,
            initial_stateful_corotational_fiber_frame2d_checkpoint(p),
            target_load_factor=0.0,
            config=preload_cfg,
        )
        reason, status = "preload_failed", "blocked"
        if preload.committed:
            append_response(preload, "preload")
            kwargs = dict(
                control_global_dof=dof,
                initial_checkpoint=preload.accepted_checkpoint,
                maximum_attempt_count=maximum_attempt_count,
                maximum_subdivision_depth=maximum_subdivision_depth,
                config=cfg,
            )
            if restart is not None:
                replay = run_corotational_control_subdivision(
                    p, targets, attempt_limit_per_call=prior_spent, **kwargs
                )
                work["restart_replay_solver_calls"] = len(replay.attempts)
                if replay.continuation != restart:
                    raise ValueError(
                        "restart differs from fresh complete-prefix replay"
                    )
                for step in replay.attempts:
                    if step.committed:
                        append_response(step, "control")
            path = run_corotational_control_subdivision(
                p,
                targets,
                continuation=restart,
                attempt_limit_per_call=attempt_limit_per_call,
                **kwargs,
            )
            work["control_solver_calls"] = len(path.attempts)
            for step in path.attempts:
                if step.committed:
                    append_response(step, "control")
            reason, status, continuation = (
                path.terminal_reason,
                path.status,
                path.continuation,
            )
        payload = {
            "schema": SCHEMA,
            "request": request,
            "status": status,
            "terminal_reason": reason,
            "contract_pass": path is not None and path.contract_pass,
            "completed_target_count": 0
            if path is None
            else path.completed_target_count,
            "total_control_attempts": 0 if path is None else path.total_attempt_count,
            "continuation_sha256": None if continuation is None else _sha(continuation),
            "work": work,
            "responses": responses,
            "claims": {
                "independent_physical_validation": False,
                "managed_budget_authority": False,
                "design_authority": False,
            },
        }
        raw = _json(payload)
        if len(raw) > MAX_BYTES:
            raise ValueError("result artifact exceeds bounded size")
        return RCCorotationalControlArtifacts(raw, continuation)
    except Exception as exc:
        raise RCCorotationalControlExecutionError(work) from exc


def validate_rc_corotational_control_artifacts(
    model, targets_m, *, result, continuation, **options
):
    """Execute the caller's original request again; account for every replay call."""
    supplied = strict_json_object_bytes(result, maximum_bytes=MAX_BYTES)
    if supplied.get("schema") != SCHEMA or _json(supplied) != result:
        raise ValueError("result must use the canonical corotational artifact schema")
    if continuation is not None and (
        type(continuation) is not bytes or len(continuation) > 16 * 1024 * 1024
    ):
        raise ValueError("continuation must be bounded bytes")
    expected_hash = None if continuation is None else _sha(continuation)
    if supplied.get("continuation_sha256") != expected_hash:
        raise ValueError("result/continuation binding mismatch")
    fresh = analyze_rc_corotational_control(model, targets_m, **options)
    observed = json.loads(fresh.result_bytes)
    same = fresh.result_bytes == result and fresh.continuation_bytes == continuation
    return {
        "artifact_contract_pass": same,
        "physical_path_complete": same and observed["contract_pass"],
        "fresh_source_execution_invoked": True,
        "solver_replay_performed": True,
        "replay_work": observed["work"],
        "independent_physical_validation": False,
        "contract_pass": same and observed["contract_pass"],
    }
