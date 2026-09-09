"""Experimental control-path starts, with complete original transition recovery.

Reference, deterministic secant and optional caller proposals run from their own
accepted states. A separate full reference run follows all experimental arms.
This is development timing/equivalence evidence, not public solver authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns

import numpy as np

from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.assembly import initial_stateful_fiber_frame2d_checkpoint
from structural_analysis.assembly.stateful_fiber_frame2d import (
    assemble_stateful_fiber_frame2d,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import _directions
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlStepAdapter,
    solve_stateful_fiber_frame2d_displacement_control_step,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    _numeric_payload_difference,
    _is_identity_key,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _save, _sha
from structural_analysis.model.schema import CanonicalModel


@dataclass(frozen=True)
class RCControlSeedContext:
    """Only this arm's already accepted coordinates are given to a proposer."""

    problem_contract_hash: str
    control_global_dof: int
    control_free_index: int
    target_m: float
    accepted_targets_m: tuple[float, ...]
    accepted_augmented_coordinates_m: tuple[tuple[float, ...], ...]


def secant_seed(context: RCControlSeedContext) -> tuple[float, ...] | None:
    if len(context.accepted_targets_m) < 2:
        return None
    a, b = context.accepted_targets_m[-2:]
    if b == a:
        return None
    ratio = (context.target_m - b) / (b - a)
    previous, current = map(np.asarray, context.accepted_augmented_coordinates_m[-2:])
    result = current + ratio * (current - previous)
    result[context.control_free_index] = context.target_m
    return tuple(float(x) for x in result)


def _recover(compiled, step, request):
    """Replay the exact original Newton coordinates against the original parent."""
    parent = step.parent_checkpoint
    coordinates = step.trial_solution.free_displacements_m
    low = None
    if compiled.problem.coordinate_precision != "binary64":
        coordinates, low = step.trial_solution.problem.absolute_coordinates(
            coordinates, step.trial_solution.free_displacement_compensation_m
        )
        factor = step.trial_solution.problem.load_factor_at(coordinates, low)
        if not np.array_equal(
            coordinates, step.metrics["absolute_augmented_coordinates_m"]
        ) or not np.array_equal(
            low, step.metrics["absolute_augmented_coordinate_compensation_m"]
        ):
            raise ValueError("original twofold solver-coordinate binding differs")
    else:
        factor = (
            float(coordinates[-1])
            / request.solver_config.load_factor_coordinate_scale_m
        )
    fresh = assemble_stateful_fiber_frame2d(
        compiled.problem,
        parent,
        target_load_factor=factor,
        trial_free_coordinates_m=coordinates[:-1],
        **(
            {"trial_free_coordinate_compensation_m": low[:-1]}
            if low is not None
            else {}
        ),
    )
    child = StatefulFiberFrame2DCheckpoint(
        case_id=compiled.problem.case_id,
        problem_contract_hash=compiled.problem.contract_hash,
        epoch=parent.epoch + 1,
        step_index=parent.step_index + 1,
        load_factor=factor,
        parent_state_hash=parent.state_hash,
        global_displacements=tuple(float(x) for x in fresh.global_displacements),
        element_states=fresh.trial_element_states,
        free_coordinates_m=tuple(float(v) for v in coordinates[:-1])
        if low is not None
        else None,
        free_coordinate_compensation_m=tuple(float(v) for v in low[:-1])
        if low is not None
        else None,
    )
    validate_stateful_fiber_frame2d_checkpoint(compiled.problem, child)
    if child.canonical_bytes() != step.accepted_checkpoint.canonical_bytes() or _bytes(
        fresh.to_dict()
    ) != _bytes(step.trial_assembly.to_dict()):
        raise ValueError("original transition recovery mismatch")
    relative = (
        float(np.linalg.norm(fresh.residual_kn, ord=np.inf))
        / compiled.problem.reference_force_scale()
    )
    error = abs(
        child.global_displacements[request.control_global_dof]
        - step.metrics["target_control_displacement_m"]
    )
    if low is not None:
        from fractions import Fraction

        index = compiled.problem.free_global_dofs.index(request.control_global_dof)
        error = abs(
            float(
                Fraction(float(coordinates[index]))
                + Fraction(float(low[index]))
                - Fraction(step.metrics["target_control_displacement_m"])
            )
        )
    if (
        relative > request.solver_config.newton.residual_tolerance
        or error > request.solver_config.control_tolerance_m
    ):
        raise ValueError("recovered equilibrium or control gate failed")
    return api._response_rows(compiled, fresh, child, step.step_hash)


def _path(compiled, request, strategy, proposal, root):
    wall, cpu = perf_counter_ns(), process_time_ns()
    root.mkdir(exist_ok=False)
    accepted = initial_stateful_fiber_frame2d_checkpoint(compiled.problem)
    source_hash = compiled.problem.contract_hash
    coordinates = [
        tuple(
            StatefulFiberFrame2DDisplacementControlStepAdapter(
                compiled.problem,
                accepted,
                request.control_global_dof,
                request.targets_m[0],
                request.solver_config,
            ).initial_free_displacements_m()
        )
    ]
    targets, history, entries = [0.0], [], []
    failure = None
    for index, target in enumerate(request.targets_m):
        context = RCControlSeedContext(
            source_hash,
            request.control_global_dof,
            compiled.problem.free_global_dofs.index(request.control_global_dof),
            target,
            tuple(targets),
            tuple(coordinates),
        )
        before = accepted.canonical_bytes()
        entry = {
            "target_index": index,
            "target_m": target,
            "parent_hash": accepted.state_hash,
            "proposal": None,
            "proposal_wall_ns": None,
            "proposal_cpu_ns": None,
            "invocations": [],
        }
        entries.append(entry)
        _save(root, f"{index:03d}-context.json", _bytes(asdict(context)))
        _save(
            root,
            f"{index:03d}-proposal-started.json",
            _bytes(
                {
                    "status": "started",
                    "target_index": index,
                    "unknown_proposal_work_until_outcome": True,
                }
            ),
        )
        pw, pc = perf_counter_ns(), process_time_ns()
        try:
            seed = (
                None
                if strategy == "reference"
                else secant_seed(context)
                if strategy == "secant"
                else proposal(context)
            )
            if seed is not None:
                seed = StatefulFiberFrame2DDisplacementControlStepAdapter(
                    compiled.problem,
                    accepted,
                    request.control_global_dof,
                    target,
                    request.solver_config,
                    seed,
                ).initial_augmented_coordinates_m
            entry["proposal"] = None if seed is None else list(seed)
        except Exception as exc:
            entry["proposal_error"] = {
                "phase": "proposal",
                "kind": type(exc).__name__,
                "target_index": index,
            }
            seed = None
            entry["proposal_rejected_to_reference"] = True
        finally:
            entry["proposal_wall_ns"] = perf_counter_ns() - pw
            entry["proposal_cpu_ns"] = process_time_ns() - pc
        _save(root, f"{index:03d}-proposal.json", _bytes(entry))
        if failure:
            break
        # A rejected numerical proposal may fall back exactly once, with both
        # attempts retained. An exception leaves unknown work and stops the path.
        for attempt, current in enumerate(
            (seed, None) if seed is not None else (None,)
        ):
            inv = {
                "ordinal": attempt + 1,
                "seed_used": current is not None,
                "status": "started",
                "work": None,
                "unknown_work": True,
                "rollback_exact": None,
            }
            entry["invocations"].append(inv)
            stem = f"{index:03d}-{attempt + 1}"
            _save(root, stem + "-started.json", _bytes(inv))
            sw, sc = perf_counter_ns(), process_time_ns()
            step = None
            try:
                step = solve_stateful_fiber_frame2d_displacement_control_step(
                    compiled.problem,
                    accepted,
                    control_global_dof=request.control_global_dof,
                    target_control_displacement_m=target,
                    config=request.solver_config,
                    initial_augmented_coordinates_m=current,
                )
                if (
                    accepted.canonical_bytes() != before
                    or compiled.problem.contract_hash != source_hash
                ):
                    raise ValueError("source changed during numerical entry")
                metrics = step.trial_solution.metrics
                counts = tuple(
                    value if type(value) is int and value >= 0 else None
                    for value in (
                        metrics.get("iteration_count"),
                        metrics.get("linear_solve_count"),
                    )
                )
                inv.update(
                    status="returned",
                    work={
                        "core_calls": 1,
                        "newton_iterations": counts[0],
                        "linear_solves": counts[1],
                    },
                    unknown_work=any(value is None for value in counts),
                    committed=step.committed,
                    rollback_exact=step.metrics["rollback_exact"],
                )
            except Exception as exc:
                inv.update(status="raised", exception_kind=type(exc).__name__)
                failure = {
                    "phase": "numerical",
                    "kind": type(exc).__name__,
                    "target_index": index,
                }
            finally:
                inv["wall_ns"], inv["cpu_ns"] = (
                    perf_counter_ns() - sw,
                    process_time_ns() - sc,
                )
            _save(root, stem + "-outcome.json", _bytes(inv))
            if step is not None:
                _save(root, stem + "-step.json", _bytes(step.to_dict()))
            if failure:
                break
            if step.committed:
                rw, rc = perf_counter_ns(), process_time_ns()
                try:
                    response = _recover(compiled, step, request)
                    history.append(response)
                    accepted = step.accepted_checkpoint
                    targets.append(target)
                    coordinates.append(
                        tuple(
                            float(x)
                            for x in step.metrics.get(
                                "absolute_augmented_coordinates_m",
                                step.trial_solution.free_displacements_m,
                            )
                        )
                    )
                except Exception as exc:
                    failure = {
                        "phase": "recovery",
                        "kind": type(exc).__name__,
                        "target_index": index,
                    }
                finally:
                    entry["recovery_wall_ns"], entry["recovery_cpu_ns"] = (
                        perf_counter_ns() - rw,
                        process_time_ns() - rc,
                    )
                break
            if (
                step.accepted_checkpoint is not accepted
                or step.metrics["rollback_exact"] is not True
            ):
                failure = {
                    "phase": "rollback",
                    "kind": "rollback_not_exact",
                    "target_index": index,
                }
                break
        if failure or not step.committed:
            failure = failure or {
                "phase": "numerical",
                "kind": "all_attempts_blocked",
                "target_index": index,
            }
            break
    result = {
        "schema_version": "experimental-rc-control-seed-path.v1",
        "strategy": strategy,
        "status": "complete"
        if failure is None and len(history) == len(request.targets_m)
        else "incomplete",
        "requested_targets_m": list(request.targets_m),
        "accepted_target_count": len(history),
        "entries": entries,
        "response_history": history,
        "terminal_checkpoint": accepted.to_dict(),
        "failure": failure,
        "wall_ns": perf_counter_ns() - wall,
        "cpu_ns": process_time_ns() - cpu,
        "timing_scope": "whole_path_including_proposal_numerical_attempts_recovery_and_step_io_excluding_final_path_write",
        "source_problem_hash": source_hash,
    }
    result["path_hash"] = _sha(_bytes(result))
    _save(root, "path.json", _bytes(result))
    return result


def _physical_mismatch_locations(
    left, right, *, absolute_tolerance, relative_tolerance
):
    """Bound diagnostic size without dropping mismatches from the verdict/count."""
    summary = {
        "mismatch_count": 0,
        "by_response_field": {},
        "examples": [],
        "example_limit": 20,
    }

    def record(path, kind, **values):
        summary["mismatch_count"] += 1
        field = str(path[1]) if len(path) > 1 else "history_structure"
        counts = summary["by_response_field"]
        counts[field] = counts.get(field, 0) + 1
        if len(summary["examples"]) < summary["example_limit"]:
            summary["examples"].append({"path": list(path), "kind": kind, **values})

    def walk(a, b, path):
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            ak = {k for k in a if not _is_identity_key(k)}
            bk = {k for k in b if not _is_identity_key(k)}
            if ak != bk:
                record(path, "mapping_keys_differ")
            for key in sorted(ak & bk):
                walk(a[key], b[key], (*path, key))
        elif isinstance(a, Sequence) and not isinstance(a, (str, bytes)):
            if not isinstance(b, Sequence) or isinstance(b, (str, bytes)):
                record(path, "sequence_type_differ")
                return
            if len(a) != len(b):
                record(
                    path,
                    "sequence_lengths_differ",
                    reference_length=len(a),
                    arm_length=len(b),
                )
            for index, (x, y) in enumerate(zip(a, b)):
                walk(x, y, (*path, index))
        else:
            structure, difference, _, within = _numeric_payload_difference(
                a,
                b,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            if not structure or not within:
                if structure and np.isfinite(difference):
                    record(
                        path,
                        "numeric_tolerance_exceeded",
                        reference=a,
                        arm=b,
                        absolute_difference=difference,
                        allowed_difference=absolute_tolerance
                        + relative_tolerance * max(abs(a), abs(b)),
                    )
                else:
                    record(path, "value_or_type_differ")

    walk(left, right, ())
    summary["examples_truncated"] = summary["mismatch_count"] > len(summary["examples"])
    return summary


def _with_strain_evaluation(compiled, strain_evaluation):
    """Bind an explicit experimental arithmetic profile to native contracts."""
    if type(strain_evaluation) is not str or strain_evaluation not in (
        "matrix",
        "exact-rational",
    ):
        raise ValueError("unsupported fiber beam strain evaluation")
    if strain_evaluation != "matrix":
        # Same physical model, explicitly different numerical contracts for every
        # member. Native parents/recovery must use that same compiled profile.
        problem = replace(
            compiled.problem,
            members=tuple(
                replace(
                    member,
                    element=replace(
                        member.element, strain_evaluation=strain_evaluation
                    ),
                )
                for member in compiled.problem.members
            ),
        )
        compiled = replace(compiled, problem=problem)
    return compiled


def _with_coordinate_precision(compiled, coordinate_precision):
    if type(coordinate_precision) is not str or coordinate_precision not in (
        "binary64",
        "twofold-increment",
    ):
        raise ValueError("unsupported coordinate precision")
    if coordinate_precision == "binary64":
        return compiled
    problem = replace(
        compiled.problem,
        coordinate_precision=coordinate_precision,
        members=tuple(
            replace(
                member,
                element=replace(
                    member.element, coordinate_precision=coordinate_precision
                ),
            )
            for member in compiled.problem.members
        ),
    )
    return replace(compiled, problem=problem)


def _with_material_arithmetic(compiled, profile):
    if type(profile) is not str or profile not in (
        "binary64",
        "stable-stress",
        "retained-strain",
    ):
        raise ValueError("unsupported material arithmetic")
    if profile == "binary64":
        return compiled
    from structural_analysis.materials.stable_stress import stable_stress_section
    from structural_analysis.materials.retained_fiber_strain import (
        retained_fiber_section,
    )

    section_factory = (
        retained_fiber_section
        if profile == "retained-strain"
        else stable_stress_section
    )

    problem = replace(
        compiled.problem,
        members=tuple(
            replace(
                member,
                element=replace(
                    member.element,
                    section=section_factory(member.element.section),
                ),
            )
            for member in compiled.problem.members
        ),
    )
    return replace(
        compiled,
        problem=problem,
        section_by_member=tuple(member.element.section for member in problem.members),
    )


def _with_fiber_strain_evaluation(compiled, profile):
    if type(profile) is not str or profile not in (
        "generalized",
        "direct-coordinate",
        "retained-coordinate",
    ):
        raise ValueError("unsupported fiber strain evaluation")
    if profile == "retained-coordinate":
        from structural_analysis.materials.retained_fiber_strain import (
            RetainedFiberRCSection,
        )

        if any(
            type(m.element.section) is not RetainedFiberRCSection
            for m in compiled.problem.members
        ):
            raise ValueError("retained-coordinate requires retained-strain materials")
        return compiled
    if profile == "generalized":
        return compiled
    from structural_analysis.materials.direct_fiber_strain import direct_fiber_section

    problem = replace(
        compiled.problem,
        members=tuple(
            replace(
                member,
                element=replace(
                    member.element, section=direct_fiber_section(member.element.section)
                ),
            )
            for member in compiled.problem.members
        ),
    )
    return replace(
        compiled,
        problem=problem,
        section_by_member=tuple(m.element.section for m in problem.members),
    )


def _with_force_accumulation(compiled, profile):
    if type(profile) is not str or profile not in ("binary64", "rational"):
        raise ValueError("unsupported force accumulation")
    if profile == "binary64":
        return compiled
    from structural_analysis.materials.rational_force_section import (
        rational_force_section,
    )

    problem = replace(
        compiled.problem,
        members=tuple(
            replace(
                m,
                element=replace(
                    m.element, section=rational_force_section(m.element.section)
                ),
            )
            for m in compiled.problem.members
        ),
    )
    return replace(
        compiled,
        problem=problem,
        section_by_member=tuple(m.element.section for m in problem.members),
    )


def _with_terminal_coordinate_precision(compiled, profile):
    if type(profile) is not str or profile not in ("binary64", "twofold"):
        raise ValueError("unsupported terminal coordinate precision")
    if profile == "binary64":
        return compiled
    return replace(
        compiled,
        problem=replace(compiled.problem, terminal_coordinate_precision=profile),
    )


def benchmark_rc_control_seed_paths(
    model: CanonicalModel,
    request: BoundedRCFiberDirectControlRequest,
    *,
    source_revision: str,
    output_directory: Path,
    proposal: Callable[[RCControlSeedContext], tuple[float, ...] | None] | None = None,
    proposal_identity: str | None = None,
    arm_order: tuple[str, ...] | None = None,
    absolute_tolerance: float = 1e-10,
    relative_tolerance: float = 1e-8,
    strain_evaluation: str = "matrix",
    coordinate_precision: str = "binary64",
    material_arithmetic: str = "binary64",
    fiber_strain_evaluation: str = "generalized",
    force_accumulation: str = "binary64",
    terminal_coordinate_precision: str = "binary64",
):
    """Run all arms independently, then a fresh reference; never refit a proposal."""
    started, started_cpu = perf_counter_ns(), process_time_ns()
    if type(force_accumulation) is not str or force_accumulation not in (
        "binary64",
        "rational",
    ):
        raise ValueError("unsupported force accumulation")
    if force_accumulation == "rational" and (
        material_arithmetic != "retained-strain"
        or fiber_strain_evaluation != "retained-coordinate"
    ):
        raise ValueError(
            "rational accumulation requires retained rational material inputs"
        )
    if type(fiber_strain_evaluation) is not str or fiber_strain_evaluation not in (
        "generalized",
        "direct-coordinate",
        "retained-coordinate",
    ):
        raise ValueError("unsupported fiber strain evaluation")
    if fiber_strain_evaluation == "direct-coordinate" and (
        material_arithmetic != "stable-stress" or strain_evaluation != "exact-rational"
    ):
        raise ValueError(
            "direct fiber strain requires stable-stress and exact-rational profiles"
        )
    if (fiber_strain_evaluation == "retained-coordinate") != (
        material_arithmetic == "retained-strain"
    ) or (
        material_arithmetic == "retained-strain"
        and strain_evaluation != "exact-rational"
    ):
        raise ValueError(
            "retained strain requires paired retained-coordinate and exact-rational profiles"
        )
    if type(material_arithmetic) is not str or material_arithmetic not in (
        "binary64",
        "stable-stress",
        "retained-strain",
    ):
        raise ValueError("unsupported material arithmetic")
    if type(coordinate_precision) is not str or coordinate_precision not in (
        "binary64",
        "twofold-increment",
    ):
        raise ValueError("unsupported coordinate precision")
    if type(strain_evaluation) is not str or strain_evaluation not in (
        "matrix",
        "exact-rational",
    ):
        raise ValueError("unsupported fiber beam strain evaluation")
    if coordinate_precision != "binary64" and strain_evaluation != "exact-rational":
        raise ValueError("twofold coordinates require exact-rational strain evaluation")
    if (
        type(model) is not CanonicalModel
        or type(request) is not BoundedRCFiberDirectControlRequest
    ):
        raise ValueError("exact model and control request required")
    if not isinstance(source_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ):
        raise ValueError("exact caller source revision required")
    if proposal is not None and not callable(proposal):
        raise ValueError("proposal must be callable")
    if (proposal is None) != (proposal_identity is None) or (
        proposal_identity is not None
        and (
            not isinstance(proposal_identity, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", proposal_identity)
        )
    ):
        raise ValueError("caller proposal requires its declared identity hash")
    expected_arms = (
        "reference",
        "secant",
        *(("proposal",) if proposal is not None else ()),
    )
    order = expected_arms if arm_order is None else arm_order
    if (
        type(order) is not tuple
        or len(order) != len(expected_arms)
        or set(order) != set(expected_arms)
    ):
        raise ValueError("arm order must contain each requested strategy exactly once")
    for tolerance in (absolute_tolerance, relative_tolerance):
        if (
            type(tolerance) not in (int, float)
            or not np.isfinite(tolerance)
            or tolerance < 0
        ):
            raise ValueError("finite nonnegative comparison tolerances required")
    request = decode_bounded_rc_fiber_direct_control_request(_bytes(request.to_dict()))
    if not request.targets_m:
        raise ValueError("nonempty target path required")
    _, reversals = _directions(request.targets_m)
    if (
        len(request.targets_m) > request.maximum_targets
        or reversals > request.maximum_reversals
        or (reversals and not request.allow_reversals)
    ):
        raise ValueError("declared path budget exceeded")
    model = model.detached_analysis_snapshot()
    compiled, blockers, _ = public._compile(model)
    if compiled is None or blockers:
        raise ValueError("supported RC model required")
    compiled = _with_strain_evaluation(compiled, strain_evaluation)
    compiled = _with_coordinate_precision(compiled, coordinate_precision)
    compiled = _with_material_arithmetic(compiled, material_arithmetic)
    compiled = _with_fiber_strain_evaluation(compiled, fiber_strain_evaluation)
    compiled = _with_force_accumulation(compiled, force_accumulation)
    compiled = _with_terminal_coordinate_precision(
        compiled, terminal_coordinate_precision
    )
    if (
        terminal_coordinate_precision != "binary64"
        and not request.solver_config.newton.terminal_polishing
    ):
        raise ValueError(
            "twofold terminal coordinates require enabled original polishing"
        )
    StatefulFiberFrame2DDisplacementControlStepAdapter(
        compiled.problem,
        initial_stateful_fiber_frame2d_checkpoint(compiled.problem),
        request.control_global_dof,
        request.targets_m[0],
        request.solver_config,
    )
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    identity = {
        "schema_version": "experimental-rc-control-seed-comparison.v1",
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        **(
            {
                "force_accumulation": force_accumulation,
                "compiled_problem_contract_hash": compiled.problem.contract_hash,
            }
            if force_accumulation != "binary64"
            else {}
        ),
        **(
            {
                "fiber_strain_evaluation": fiber_strain_evaluation,
                "compiled_problem_contract_hash": compiled.problem.contract_hash,
            }
            if fiber_strain_evaluation != "generalized"
            else {}
        ),
        **(
            {
                "terminal_coordinate_precision": terminal_coordinate_precision,
                "compiled_problem_contract_hash": compiled.problem.contract_hash,
            }
            if terminal_coordinate_precision != "binary64"
            else {}
        ),
        "model_checksum": model.canonical_model_checksum,
        **(
            {
                "material_arithmetic": material_arithmetic,
                "compiled_problem_contract_hash": compiled.problem.contract_hash,
            }
            if material_arithmetic != "binary64"
            else {}
        ),
        **(
            {
                "coordinate_precision": coordinate_precision,
                "solver_coordinate_role": "increment_from_native_parent",
                "proposal_coordinate_representation": "binary64_initial_estimate",
                "native_checkpoint_coordinate_representation": "twofold",
            }
            if coordinate_precision != "binary64"
            else {}
        ),
        **(
            {
                "strain_evaluation": strain_evaluation,
                "compiled_problem_contract_hash": compiled.problem.contract_hash,
            }
            if strain_evaluation != "matrix"
            else {}
        ),
        "request": request.to_dict(),
        "proposal_requested": proposal is not None,
        "proposal_identity": proposal_identity,
        "proposal_identity_is_attestation": False,
        "arm_order": list(order),
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
    }
    _save(root, "request.json", _bytes(identity))
    _save(root, "model.json", _bytes(model.canonical_payload()))
    arms = {
        name: _path(compiled, request, name, proposal, root / name) for name in order
    }
    fresh = _path(compiled, request, "reference", None, root / "fresh-reference")
    comparisons = {}
    for name, arm in arms.items():
        structure, maximum_absolute, maximum_relative, within = (
            _numeric_payload_difference(
                fresh["response_history"],
                arm["response_history"],
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
        )
        comparisons[name] = {
            "full_history_pass": fresh["status"] == arm["status"] == "complete"
            and structure
            and within,
            "structure_match": structure,
            "mismatch_locations": _physical_mismatch_locations(
                fresh["response_history"],
                arm["response_history"],
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            ),
            "physical_values_within_tolerance": within,
            "maximum_absolute_difference_mixed_SI_fields": maximum_absolute
            if np.isfinite(maximum_absolute)
            else None,
            "maximum_relative_difference": maximum_relative
            if np.isfinite(maximum_relative)
            else None,
            "exact_terminal_checkpoint": _bytes(fresh["terminal_checkpoint"])
            == _bytes(arm["terminal_checkpoint"]),
        }
    reference = comparisons["reference"]
    report = {
        **identity,
        "arms": {
            name: {
                k: v
                for k, v in arm.items()
                if k not in ("response_history", "terminal_checkpoint")
            }
            for name, arm in arms.items()
        },
        "fresh_reference": {
            k: v
            for k, v in fresh.items()
            if k not in ("response_history", "terminal_checkpoint")
        },
        "comparisons": comparisons,
        "reference_repeat_exact": reference["full_history_pass"]
        and reference["exact_terminal_checkpoint"]
        and _bytes(arms["reference"]["response_history"])
        == _bytes(fresh["response_history"]),
        "whole_study_wall_ns": perf_counter_ns() - started,
        "whole_study_cpu_ns": process_time_ns() - started_cpu,
        "whole_study_timing_scope": "validation_compilation_input_io_all_arms_fresh_reference_recovery_comparison_excluding_final_report_hash_and_write",
        "all_execution_work_reported": not any(
            inv["unknown_work"]
            for arm in (*arms.values(), fresh)
            for entry in arm["entries"]
            for inv in entry["invocations"]
        ),
        "claims": {
            "experimental_control": True,
            "policy_training_performed": False,
            "independent_validation": False,
            "performance_improvement": False,
            "design_approval": False,
        },
    }
    report["report_hash"] = _sha(_bytes(report))
    _save(root, "comparison.json", _bytes(report))
    return report
