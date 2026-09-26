"""Pinned internal 20 mm portal comparison; no public or physical qualification.

This runner deliberately uses the preserved two-base source bytes. Only the three
member formulation tags change before the private corotational compilation. Each
arm starts from a fresh genesis checkpoint and solves the same constant preload.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from threading import Lock
from time import perf_counter_ns, process_time_ns
from typing import Any
from unittest.mock import patch

import numpy as np

from structural_analysis.api.nonlinear_frame import _compile_portal
from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepResult,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    StatefulCorotationalFiberFrame2DLoadStepAdapter,
    StatefulCorotationalFiberFrame2DLoadStepResult,
    solve_stateful_corotational_fiber_frame2d_load_step,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


SCHEMA_VERSION = "internal-rc-portal-20mm-comparison.v1"
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3] / "examples/research/rc_internal_portal_20mm"
)
ORIGINAL_MODEL_SHA256 = (
    "6f8eec155f5fcf2f9ae942c021a8692e79ae1efd0d1b98342f8aea0b642d0ed6"
)
ORIGINAL_REQUEST_SHA256 = (
    "e0cbc4995e2c98f4a30a0902ac321b4a0e66a9baa61ed20a88e5e73809df627e"
)
CANDIDATE_MODEL_HASH = (
    "sha256:431b960cf5d73d684bf8bac896669991b4e26bc64d4475c2b8650ee1bdc7cdfa"
)
INTERNAL_PROBLEM_HASH = (
    "sha256:5d53352c5d85cc8e47ad49df1d2c37bd671c81e4b6d45f1bcc1b5807254cbb51"
)
PREFLIGHT_PRELOAD_HASH = (
    "sha256:bdfbc4f719c8ea8d3565dab9a4f05dcbc0890e17d114c5aa3b5b01a60a426e70"
)
CONTROL_DOF = 9
TARGETS_M = (-0.01, -0.02, 0.01)
ARM_ORDERS = (
    ("reference", "secant", "frozen_parent_recovery", "fresh_reference"),
    ("fresh_reference", "frozen_parent_recovery", "secant", "reference"),
)
MODE_ORDERS = (("fixed", "adaptive"), ("adaptive", "fixed"))
_WORK_KEYS = (
    "iteration_count",
    "linear_solve_count",
    "assembly_call_count",
    "assembly_exception_count",
    "line_search_step_count",
    "line_search_trial_count",
)
_PRELOAD_LOCK = Lock()


@dataclass(frozen=True)
class _Case:
    problem: StatefulCorotationalFiberFrame2DProblem
    control_config: StatefulCorotationalFiberFrame2DDisplacementControlConfig
    preload_config: NewtonRaphsonConfig
    original_model_hash: str
    original_request_hash: str
    candidate_model_hash: str


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        default=_json_scalar,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_scalar(value: Any) -> bool | int | float:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        finite = float(value)
        if math.isfinite(finite):
            return finite
        raise ValueError("non-finite NumPy scalar in campaign artifact")
    raise TypeError(f"unsupported campaign artifact value: {type(value).__name__}")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write(root: Path, name: str, payload: Any) -> str:
    raw = _json_bytes(payload)
    with (root / name).open("xb") as handle:
        handle.write(raw)
    return _sha(raw)


def prepare_case(
    *,
    model_path: Path = FIXTURE_ROOT / "original-model.json",
    request_path: Path = FIXTURE_ROOT / "original-request.json",
) -> _Case:
    """Verify original bytes and the exact internal transformation before a solve."""

    original_raw = model_path.read_bytes()
    request_raw = request_path.read_bytes()
    if hashlib.sha256(original_raw).hexdigest() != ORIGINAL_MODEL_SHA256:
        raise ValueError("original 20 mm portal model bytes changed")
    if hashlib.sha256(request_raw).hexdigest() != ORIGINAL_REQUEST_SHA256:
        raise ValueError("original 20 mm portal request bytes changed")
    original = json.loads(original_raw)
    request = json.loads(request_raw)
    if (
        tuple(request["targets_m"]) != TARGETS_M
        or request["control_global_dof"] != CONTROL_DOF
        or request["allow_reversals"] is not True
        or request["maximum_reversals"] != 2
        or request["constant_nodal_loads"]
        != [
            {"node_id": "N3", "FX_kN": 0.0, "FY_kN": -25.0, "MZ_kNm": 0.0},
            {"node_id": "N4", "FX_kN": 0.0, "FY_kN": -25.0, "MZ_kNm": 0.0},
        ]
    ):
        raise ValueError("original 20 mm portal request contract changed")
    candidate = deepcopy(original)
    expected_elements = (
        ("left", ["N1", "N3"]),
        ("right", ["N2", "N4"]),
        ("beam", ["N3", "N4"]),
    )
    if len(candidate["elements"]) != len(expected_elements):
        raise ValueError("original portal member roster changed")
    for row, (member_id, nodes) in zip(
        candidate["elements"], expected_elements, strict=True
    ):
        if (
            row["id"] != member_id
            or row["nodes"] != nodes
            or row["type"] != "stateful_rc_fiber_frame2d"
        ):
            raise ValueError("original portal member contract changed")
        row["type"] = "stateful_corotational_rc_fiber_frame2d"
    candidate_model = load_neutral_json_bytes(
        _json_bytes(candidate), source_path="memory://internal-portal-20mm.json"
    )
    if candidate_model.canonical_model_checksum != CANDIDATE_MODEL_HASH:
        raise ValueError("corotational portal transformation hash changed")
    problem = replace(
        _compile_portal(candidate_model).problem,
        constant_external_loads=((7, -25.0), (10, -25.0)),
    )
    if (
        problem.contract_hash != INTERNAL_PROBLEM_HASH
        or problem.fixed_global_dofs != (0, 1, 2, 3, 4, 5)
        or problem.reference_external_loads != ((9, 150.0),)
    ):
        raise ValueError("internal portal problem differs from pinned preflight")
    newton = request["solver_config"]["newton"]
    control = StatefulCorotationalFiberFrame2DDisplacementControlConfig(
        residual_tolerance=newton["residual_tolerance"],
        control_tolerance_m=request["solver_config"]["control_tolerance_m"],
        increment_tolerance_m=newton["increment_tolerance"],
        maximum_iterations=newton["max_iterations"],
        line_search_alphas=tuple(newton["line_search_alphas"]),
        load_factor_coordinate_scale_m=(
            request["solver_config"]["load_factor_coordinate_scale_m"]
        ),
    )
    preload = NewtonRaphsonConfig(
        residual_tolerance=newton["residual_tolerance"],
        increment_tolerance=newton["increment_tolerance"],
        max_iterations=newton["max_iterations"],
        line_search_alphas=tuple(newton["line_search_alphas"]),
        matrix_backend=newton["matrix_backend"],
        terminal_polishing=False,
    )
    return _Case(
        problem=problem,
        control_config=control,
        preload_config=preload,
        original_model_hash=_sha(original_raw),
        original_request_hash=_sha(request_raw),
        candidate_model_hash=candidate_model.canonical_model_checksum,
    )


def campaign_plan(source_revision: str, case: _Case) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise ValueError("exact 40-character source revision required")
    plan = {
        "schema_version": SCHEMA_VERSION,
        "source_revision": source_revision,
        "original_model_hash": case.original_model_hash,
        "original_request_hash": case.original_request_hash,
        "candidate_model_hash": case.candidate_model_hash,
        "internal_problem_contract_hash": case.problem.contract_hash,
        "preload_constant_loads_kn": [[7, -25.0], [10, -25.0]],
        "reference_loads_kn": [[9, 150.0]],
        "control_global_dof": CONTROL_DOF,
        "targets_m": list(TARGETS_M),
        "mode_orders": [list(order) for order in MODE_ORDERS],
        "arm_orders": [list(order) for order in ARM_ORDERS],
        "planned_comparisons": 4,
        "planned_paths": 16,
        "fixed_recovery_stages": 16,
        "adaptive_recovery_maximum_trials": 64,
        "adaptive_minimum_fraction_increment": 2**-20,
        "recovery_trigger": "only_after_frozen_parent_recovery_arm_direct_failure",
        "deterministic_secant_seed": "q_last+(target-t_last)*(q_last-q_previous)/(t_last-t_previous)",
        "learned_policy_present": False,
        "learned_benefit_conclusion": None,
        "original_request_terminal_polishing": True,
        "internal_direct_terminal_polishing_supported": False,
        "internal_preload_terminal_polishing": False,
        "preload": "fresh_genesis_then_one_load_control_step_at_lambda_zero_per_arm",
        "differences_from_original_48_path_plan": [
            "20mm_only_excludes_40mm_and_80mm_conditions",
            "16_paths_across_4_comparisons_instead_of_48_paths_across_12",
            "three_member_tags_converted_to_corotational_internal_formulation",
            "no_public_direct_control_compiler_admission",
            "no_internal_direct_terminal_polishing",
            "one_step_internal_preload_uses_default_unpolished_load_solver",
            "deterministic_frozen_parent_recovery_replaces_unavailable_learned_proposal",
        ],
        "independent_physical_validation": False,
        "performance_or_policy_qualification": False,
        "runner_source_hash": _sha(Path(__file__).read_bytes()),
        "execution_profile": "single_process_sequential_scoped_preload_assembly_observation",
        "wall_budget_scope": "soft_deadline_checked_between_solver_invocations_only",
    }
    plan["plan_hash"] = _sha(_json_bytes(plan))
    return plan


def _empty_work() -> dict[str, int]:
    return {
        "core_calls": 0,
        **{name: 0 for name in _WORK_KEYS},
    }


def _add_work(total: dict[str, int], observed: dict[str, Any]) -> None:
    total["core_calls"] += 1
    for name in _WORK_KEYS:
        value = observed.get(name)
        if type(value) is not int or value < 0:
            raise ValueError(f"missing or invalid {name} work counter")
        total[name] += value


def _augmented_checkpoint_coordinates(
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    case: _Case,
) -> tuple[float, ...]:
    generalized = np.asarray(checkpoint.global_displacements, dtype=np.float64)
    generalized /= case.problem.physical_coordinate_scale
    return (
        *(float(generalized[index]) for index in case.problem.free_global_dofs),
        checkpoint.load_factor * case.control_config.load_factor_coordinate_scale_m,
    )


def _secant_seed(
    target_m: float,
    targets: list[float],
    coordinates: list[tuple[float, ...]],
    *,
    control_free_index: int,
) -> tuple[float, ...] | None:
    if len(targets) < 2 or len(targets) != len(coordinates):
        return None
    span = targets[-1] - targets[-2]
    if span == 0.0:
        return None
    factor = (target_m - targets[-1]) / span
    previous = np.asarray(coordinates[-2], dtype=np.float64)
    latest = np.asarray(coordinates[-1], dtype=np.float64)
    seed = latest + factor * (latest - previous)
    seed[control_free_index] = target_m
    if not np.all(np.isfinite(seed)):
        return None
    return tuple(float(value) for value in seed)


def _preload(
    case: _Case, root: Path, work: dict[str, int]
) -> tuple[StatefulCorotationalFiberFrame2DCheckpoint | None, dict[str, Any]]:
    """Count adapter dispatches without changing the load solver's return values."""

    genesis = initial_stateful_corotational_fiber_frame2d_checkpoint(case.problem)
    genesis_bytes = genesis.canonical_bytes()
    record: dict[str, Any] = {
        "phase": "constant_preload",
        "status": "started",
        "unknown_work": True,
        "genesis_hash": genesis.state_hash,
        "target_load_factor": 0.0,
    }
    _write(root, "preload-started.json", record)
    adapter_calls = 0
    adapter_exceptions = 0
    original_assemble = StatefulCorotationalFiberFrame2DLoadStepAdapter.assemble

    def observed_assemble(
        adapter: StatefulCorotationalFiberFrame2DLoadStepAdapter,
        coordinates_m: np.ndarray,
    ) -> tuple[np.ndarray, Any]:
        nonlocal adapter_calls, adapter_exceptions
        adapter_calls += 1
        try:
            return original_assemble(adapter, coordinates_m)
        except Exception:
            adapter_exceptions += 1
            raise

    wall_started, cpu_started = perf_counter_ns(), process_time_ns()
    step: StatefulCorotationalFiberFrame2DLoadStepResult | None = None
    try:
        with (
            _PRELOAD_LOCK,
            patch.object(
                StatefulCorotationalFiberFrame2DLoadStepAdapter,
                "assemble",
                observed_assemble,
            ),
        ):
            step = solve_stateful_corotational_fiber_frame2d_load_step(
                case.problem,
                genesis,
                target_load_factor=0.0,
                config=case.preload_config,
            )
        if genesis.canonical_bytes() != genesis_bytes:
            raise ValueError("preload mutated genesis checkpoint")
        checkpoint = step.accepted_checkpoint
        if step.committed:
            coordinates = _augmented_checkpoint_coordinates(checkpoint, case)
            validation = assemble_stateful_corotational_fiber_frame2d(
                case.problem,
                checkpoint,
                target_load_factor=0.0,
                trial_free_coordinates_m=np.asarray(coordinates[:-1]),
            )
            validated = bool(
                validation.parent_checkpoint_hash == checkpoint.state_hash
                and float(np.linalg.norm(validation.residual_kn, ord=np.inf))
                <= case.control_config.residual_tolerance
                * case.problem.reference_force_scale()
            )
        else:
            validated = False
        solution = step.trial_solution
        preload_work: dict[str, Any] = {
            "iteration_count": solution.metrics.get("iteration_count"),
            "linear_solve_count": solution.metrics.get("linear_solve_count"),
            # The returned wrapper assembles once; accepted validation above adds one.
            "assembly_call_count": adapter_calls + 1 + int(step.committed),
            "assembly_exception_count": adapter_exceptions,
            "line_search_step_count": solution.metrics.get("line_search_step_count"),
            "line_search_trial_count": sum(
                row["attempt_count"] for row in solution.line_search_history
            ),
        }
        _add_work(work, preload_work)
        complete = bool(
            step.committed
            and validated
            and checkpoint.state_hash == PREFLIGHT_PRELOAD_HASH
            and step.metrics["parent_checkpoint_immutable"] is True
        )
        record.update(
            status="ready" if complete else "blocked",
            unknown_work=False,
            committed=step.committed,
            validation_passed=validated,
            checkpoint_hash=checkpoint.state_hash,
            work=preload_work,
            work_scope="adapter_dispatches_plus_returned_wrapper_and_validation",
            step_artifact_hash=_write(root, "preload-step.json", step.to_dict()),
        )
        return (checkpoint if complete else None), record
    except Exception as exc:
        record.update(
            status="raised",
            unknown_work=True,
            error_type=type(exc).__name__,
            known_adapter_assembly_calls=adapter_calls,
            known_adapter_assembly_exceptions=adapter_exceptions,
        )
        return None, record
    finally:
        record["wall_ns"] = perf_counter_ns() - wall_started
        record["process_cpu_ns"] = process_time_ns() - cpu_started
        record["genesis_immutable"] = genesis.canonical_bytes() == genesis_bytes
        _write(root, "preload-outcome.json", record)


def _invoke_step(
    case: _Case,
    root: Path,
    name: str,
    parent: StatefulCorotationalFiberFrame2DCheckpoint,
    target_m: float,
    seed: tuple[float, ...] | None,
    work: dict[str, int],
) -> tuple[
    StatefulCorotationalFiberFrame2DDisplacementControlStepResult | None,
    dict[str, Any],
]:
    parent_bytes = parent.canonical_bytes()
    record: dict[str, Any] = {
        "status": "started",
        "unknown_work": True,
        "target_m": target_m,
        "parent_hash": parent.state_hash,
        "seed": list(seed) if seed is not None else None,
    }
    _write(root, f"{name}-started.json", record)
    wall_started, cpu_started = perf_counter_ns(), process_time_ns()
    step = None
    try:
        step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            case.problem,
            parent,
            control_global_dof=CONTROL_DOF,
            target_control_displacement_m=target_m,
            config=case.control_config,
            augmented_coordinate_seed_m=seed,
        )
        if parent.canonical_bytes() != parent_bytes:
            raise ValueError("direct-control attempt mutated its parent checkpoint")
        observed = {name: step.metrics.get(name) for name in _WORK_KEYS}
        _add_work(work, observed)
        record.update(
            status="returned",
            unknown_work=False,
            committed=step.committed,
            accepted_checkpoint_hash=step.accepted_checkpoint.state_hash,
            rollback_exact=step.metrics["rollback_exact"],
            parent_immutable=step.metrics["parent_checkpoint_immutable"],
            terminal_reason=step.trial_solution.metrics["terminal_reason"],
            work=observed,
            step_artifact_hash=_write(root, f"{name}-step.json", step.to_dict()),
        )
    except Exception as exc:
        record.update(
            status="raised",
            unknown_work=True,
            error_type=type(exc).__name__,
            parent_immutable=parent.canonical_bytes() == parent_bytes,
        )
        step = None
    finally:
        record["wall_ns"] = perf_counter_ns() - wall_started
        record["process_cpu_ns"] = process_time_ns() - cpu_started
        _write(root, f"{name}-outcome.json", record)
    return step, record


def _frozen_parent_seed(
    case: _Case,
    root: Path,
    parent: StatefulCorotationalFiberFrame2DCheckpoint,
    target_m: float,
    mode: str,
    work: dict[str, int],
    deadline_ns: int,
) -> tuple[tuple[float, ...] | None, list[dict[str, Any]], bool, str]:
    """Try coordinate-only continuation; no intermediate checkpoint is adopted."""

    origin_m = parent.global_displacements[CONTROL_DOF]
    parent_bytes = parent.canonical_bytes()
    fraction, increment = 0.0, 1.0 / 16.0
    seed: tuple[float, ...] | None = None
    stages: list[dict[str, Any]] = []
    limit = 16 if mode == "fixed" else 64
    for index in range(limit):
        if perf_counter_ns() >= deadline_ns:
            return None, stages, False, "campaign_wall_budget_exhausted"
        proposed = (
            (index + 1) / 16.0 if mode == "fixed" else min(1.0, fraction + increment)
        )
        stage_target = (
            target_m if proposed == 1.0 else origin_m + (target_m - origin_m) * proposed
        )
        stage, record = _invoke_step(
            case,
            root,
            f"continuation-{index:03d}",
            parent,
            stage_target,
            seed,
            work,
        )
        record = {
            **record,
            "fraction": proposed,
            "last_accepted_fraction": fraction,
            "fraction_increment": increment,
            "intermediate_checkpoint_adopted": False,
        }
        stages.append(record)
        if parent.canonical_bytes() != parent_bytes or record["unknown_work"]:
            return None, stages, True, "continuation_unknown_work"
        if stage is None:
            return None, stages, True, "continuation_step_missing"
        if not stage.committed and (
            stage.accepted_checkpoint is not parent
            or stage.metrics["rollback_exact"] is not True
        ):
            return None, stages, False, "continuation_rollback_not_exact"
        if stage.committed:
            seed = tuple(float(x) for x in stage.trial_solution.augmented_coordinates_m)
            if mode == "adaptive":
                fraction = proposed
                increment = min(1.0 / 16.0, 2.0 * increment)
            if proposed == 1.0:
                return seed, stages, False, "target_coordinate_reached"
        elif mode == "adaptive":
            increment /= 2.0
            if increment < 2**-20:
                return None, stages, False, "minimum_fraction_increment_exhausted"
        else:
            return None, stages, False, "fixed_stage_blocked"
    return None, stages, False, "continuation_trial_budget_exhausted"


def _run_arm(
    case: _Case,
    root: Path,
    *,
    arm: str,
    mode: str,
    deadline_ns: int,
    targets_m: tuple[float, ...] = TARGETS_M,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=False)
    wall_started, cpu_started = perf_counter_ns(), process_time_ns()
    work = _empty_work()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "arm": arm,
        "mode": mode,
        "status": "incomplete",
        "unknown_work": False,
        "original_model_hash": case.original_model_hash,
        "original_request_hash": case.original_request_hash,
        "candidate_model_hash": case.candidate_model_hash,
        "internal_problem_contract_hash": case.problem.contract_hash,
        "target_history": [],
        "accepted_checkpoint_hashes": [],
        "known_work_lower_bound": work,
        "preload_reexecuted_from_fresh_genesis": False,
        "intermediate_material_checkpoints_adopted": False,
    }
    if perf_counter_ns() >= deadline_ns:
        report["terminal_reason"] = "campaign_wall_budget_exhausted_before_path"
    else:
        accepted, preload_record = _preload(case, root, work)
        report["preload"] = preload_record
        report["preload_reexecuted_from_fresh_genesis"] = True
        report["unknown_work"] = preload_record["unknown_work"]
        if accepted is None:
            report["terminal_reason"] = "preload_not_accepted"
        else:
            report["preload_checkpoint_hash"] = accepted.state_hash
            control_free_index = case.problem.free_global_dofs.index(CONTROL_DOF)
            previous_targets = [accepted.global_displacements[CONTROL_DOF]]
            previous_coordinates = [_augmented_checkpoint_coordinates(accepted, case)]
            for target_index, target_m in enumerate(targets_m):
                if perf_counter_ns() >= deadline_ns:
                    report["terminal_reason"] = "campaign_wall_budget_exhausted"
                    break
                parent = accepted
                parent_bytes = parent.canonical_bytes()
                entry: dict[str, Any] = {
                    "target_index": target_index,
                    "target_m": target_m,
                    "parent_hash": parent.state_hash,
                    "invocations": [],
                    "recovery_stages": [],
                }
                report["target_history"].append(entry)
                seed = (
                    _secant_seed(
                        target_m,
                        previous_targets,
                        previous_coordinates,
                        control_free_index=control_free_index,
                    )
                    if arm == "secant"
                    else None
                )
                step, attempt = _invoke_step(
                    case,
                    root,
                    f"target-{target_index:03d}-attempt-0",
                    parent,
                    target_m,
                    seed,
                    work,
                )
                entry["invocations"].append(attempt)
                if step is None or attempt["unknown_work"]:
                    report["unknown_work"] = True
                    report["terminal_reason"] = "target_invocation_raised"
                    break
                if not step.committed and (
                    step.accepted_checkpoint is not parent
                    or step.metrics["rollback_exact"] is not True
                ):
                    report["terminal_reason"] = "failed_step_rollback_not_exact"
                    break
                if not step.committed and arm == "secant" and seed is not None:
                    step, attempt = _invoke_step(
                        case,
                        root,
                        f"target-{target_index:03d}-attempt-1",
                        parent,
                        target_m,
                        None,
                        work,
                    )
                    entry["invocations"].append(attempt)
                elif not step.committed and arm == "frozen_parent_recovery":
                    recovered, stages, unknown, reason = _frozen_parent_seed(
                        case,
                        root,
                        parent,
                        target_m,
                        mode,
                        work,
                        deadline_ns,
                    )
                    entry["recovery_stages"] = stages
                    entry["recovery_reason"] = reason
                    report["unknown_work"] = bool(report["unknown_work"] or unknown)
                    if recovered is not None and perf_counter_ns() < deadline_ns:
                        step, attempt = _invoke_step(
                            case,
                            root,
                            f"target-{target_index:03d}-attempt-1",
                            parent,
                            target_m,
                            recovered,
                            work,
                        )
                        entry["invocations"].append(attempt)
                    else:
                        report["terminal_reason"] = reason
                        break
                if step is None or attempt["unknown_work"]:
                    report["unknown_work"] = True
                    report["terminal_reason"] = "target_retry_raised"
                    break
                if not step.committed:
                    report["terminal_reason"] = (
                        "target_blocked_after_retries"
                        if step.accepted_checkpoint is parent
                        and step.metrics["rollback_exact"] is True
                        else "failed_step_rollback_not_exact"
                    )
                    break
                if (
                    parent.canonical_bytes() != parent_bytes
                    or step.metrics["parent_checkpoint_immutable"] is not True
                    or step.metrics["section_and_element_parent_binding_passed"]
                    is not True
                    or step.metrics[
                        "solver_assembly_coordinate_residual_binding_passed"
                    ]
                    is not True
                    or step.metrics["solver_contract_pass"] is not True
                ):
                    report["terminal_reason"] = "accepted_step_contract_failed"
                    break
                accepted = step.accepted_checkpoint
                entry["accepted_checkpoint_hash"] = accepted.state_hash
                entry["accepted_load_factor"] = accepted.load_factor
                entry["max_abs_free_residual_kn"] = float(
                    np.linalg.norm(step.trial_assembly.residual_kn, ord=np.inf)
                )
                report["accepted_checkpoint_hashes"].append(accepted.state_hash)
                previous_targets.append(target_m)
                previous_coordinates.append(
                    tuple(
                        float(value)
                        for value in step.trial_solution.augmented_coordinates_m
                    )
                )
            else:
                report["status"] = "complete"
                report["terminal_reason"] = "all_requested_targets_committed"
            report["final_checkpoint_hash"] = accepted.state_hash
            report["final_checkpoint_bytes_sha256"] = _sha(accepted.canonical_bytes())
    report["known_work_lower_bound"] = work
    report["work_complete"] = not report["unknown_work"]
    report["wall_ns"] = perf_counter_ns() - wall_started
    report["process_cpu_ns"] = process_time_ns() - cpu_started
    report["path_hash"] = _sha(_json_bytes(report))
    _write(root, "path.json", report)
    return report


def _git_head() -> str:
    root = Path(__file__).resolve().parents[3]
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _pinned_source_unchanged(plan: dict[str, Any]) -> bool:
    """Recheck the exact runner and fixture bytes used by this campaign."""

    try:
        return bool(
            _git_head() == plan["source_revision"]
            and _sha(Path(__file__).read_bytes()) == plan["runner_source_hash"]
            and _sha((FIXTURE_ROOT / "original-model.json").read_bytes())
            == plan["original_model_hash"]
            and _sha((FIXTURE_ROOT / "original-request.json").read_bytes())
            == plan["original_request_hash"]
        )
    except (OSError, subprocess.CalledProcessError):
        return False


def run_campaign(
    source_revision: str,
    output_directory: Path,
    *,
    maximum_wall_seconds: float = 600.0,
) -> dict[str, Any]:
    """Run 16 independent paths with a bounded wall budget and retained outcomes."""

    if (
        isinstance(maximum_wall_seconds, bool)
        or not math.isfinite(maximum_wall_seconds)
        or maximum_wall_seconds <= 0.0
        or maximum_wall_seconds > 600.0
    ):
        raise ValueError("maximum_wall_seconds must be finite in (0, 600]")
    case = prepare_case()
    plan = campaign_plan(source_revision, case)
    if _git_head() != source_revision:
        raise ValueError("source revision must match the current checkout HEAD")
    root = output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _write(root, "plan.json", plan)
    started_ns = perf_counter_ns()
    deadline_ns = started_ns + int(maximum_wall_seconds * 1e9)
    rows: list[dict[str, Any]] = []
    for repeat, mode_order in enumerate(MODE_ORDERS):
        for mode in mode_order:
            identity = f"20mm-r{repeat}-{mode}"
            row: dict[str, Any] = {
                "identity": identity,
                "repeat": repeat,
                "mode": mode,
                "arm_order": list(ARM_ORDERS[repeat]),
                "status": "started",
                "unknown_work": True,
            }
            _write(root, f"{identity}-started.json", row)
            wall_started, cpu_started = perf_counter_ns(), process_time_ns()
            paths: dict[str, dict[str, Any]] = {}
            try:
                for arm in ARM_ORDERS[repeat]:
                    paths[arm] = _run_arm(
                        case,
                        root / f"{identity}-{arm}",
                        arm=arm,
                        mode=mode,
                        deadline_ns=deadline_ns,
                    )
                all_complete = all(
                    path["status"] == "complete" for path in paths.values()
                )
                hashes = [path["accepted_checkpoint_hashes"] for path in paths.values()]
                row.update(
                    status="returned",
                    unknown_work=any(path["unknown_work"] for path in paths.values()),
                    arm_statuses={name: path["status"] for name, path in paths.items()},
                    arm_path_hashes={
                        name: path["path_hash"] for name, path in paths.items()
                    },
                    accepted_checkpoint_sequence_exact_agreement=(
                        all_complete and all(item == hashes[0] for item in hashes)
                    ),
                    recovery_exercised=any(
                        entry["recovery_stages"]
                        for entry in paths["frozen_parent_recovery"]["target_history"]
                    ),
                )
            except Exception as exc:
                row.update(
                    status="raised",
                    unknown_work=True,
                    error_type=type(exc).__name__,
                    completed_arm_statuses={
                        name: path["status"] for name, path in paths.items()
                    },
                )
            finally:
                row["comparison_cost"] = {
                    "wall_ns": perf_counter_ns() - wall_started,
                    "process_cpu_ns": process_time_ns() - cpu_started,
                    "scope": "sequential_arm_calls_and_return_or_exception_classification",
                }
                _write(root, f"{identity}-outcome.json", row)
                rows.append(row)
    observations_complete = all(
        row["status"] == "returned"
        and row["unknown_work"] is False
        and all(status == "complete" for status in row["arm_statuses"].values())
        for row in rows
    )
    source_unchanged = _pinned_source_unchanged(plan)
    outcome = {
        "schema_version": SCHEMA_VERSION,
        "plan_hash": plan["plan_hash"],
        "rows": rows,
        "observations_complete": observations_complete,
        "exact_source_comparison_eligible": observations_complete and source_unchanged,
        "completed_paths": sum(
            status == "complete"
            for row in rows
            for status in row.get("arm_statuses", {}).values()
        ),
        "source_unchanged": source_unchanged,
        "campaign_wall_ns_before_outcome_write": perf_counter_ns() - started_ns,
        "qualified_fixed_adaptive_timing_ratio": None,
        "learned_benefit_conclusion": None,
        "independent_physical_validation": False,
        "public_direct_control_promotion": False,
    }
    outcome["outcome_hash"] = _sha(_json_bytes(outcome))
    _write(root, "outcome.json", outcome)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--maximum-wall-seconds", type=float, default=600.0)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    case = prepare_case()
    plan = campaign_plan(args.source_revision, case)
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "plan_hash": plan["plan_hash"],
                    "comparisons": plan["planned_comparisons"],
                    "paths": plan["planned_paths"],
                    "solver_calls": 0,
                },
                sort_keys=True,
            )
        )
        return
    if args.output_directory is None:
        parser.error("--output-directory is required for execution")
    outcome = run_campaign(
        args.source_revision,
        args.output_directory,
        maximum_wall_seconds=args.maximum_wall_seconds,
    )
    print(
        json.dumps(
            {
                "observations_complete": outcome["observations_complete"],
                "source_unchanged": outcome["source_unchanged"],
                "exact_source_comparison_eligible": outcome[
                    "exact_source_comparison_eligible"
                ],
                "completed_paths": outcome["completed_paths"],
                "outcome_hash": outcome["outcome_hash"],
            },
            sort_keys=True,
        )
    )
    if not outcome["exact_source_comparison_eligible"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
