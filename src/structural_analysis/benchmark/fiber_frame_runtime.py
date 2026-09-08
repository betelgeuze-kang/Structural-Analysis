"""Volatile runtime comparison for the bounded public RC fiber-frame profile.

The numerical solver, checkpoints, and J1--J5 recovery chain remain the result
authority.  This module records local monotonic timing in a separate sidecar and
never inserts elapsed values into deterministic solver payloads.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import math
import platform
import re
from statistics import fmean, median, pstdev
from time import perf_counter_ns
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from structural_analysis.ai.fiber_frame_solver_episode_adapter import (
    FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE,
    create_fiber_frame_solver_episode_adapter,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
    assemble_stateful_fiber_frame2d,
    initial_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_checkpoint_chain_io import (
    make_stateful_fiber_frame2d_checkpoint_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_execution_topology import (
    compile_stateful_fiber_frame2d_execution_topology,
)
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    create_fiber_frame_nonlinear_kinematic_state_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_projection_chain import (
    create_fiber_frame_material_state_projection_chain,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    create_fiber_frame_nonlinear_execution_state_binding,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_recovery import (
    create_fiber_frame_nonlinear_engineering_result_ir,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    create_fiber_frame_nonlinear_numerical_result_adapter,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
    create_fiber_frame_nonlinear_terminal_receipt,
)
from structural_analysis.assembly.stateful_fiber_frame2d_physical_equation_scaling import (
    create_stateful_fiber_frame2d_physical_equation_scaling,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
    StatefulFiberFrame2DLoadStepRuntimeRecorder,
    StatefulFiberFrame2DLoadStepResult,
    solve_stateful_fiber_frame2d_load_step,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.trial_runtime import (
    MATERIAL_TRIAL_TIMING_SCOPE,
    MaterialTrialRuntimeRecorder,
    MaterialTrialTimingError,
)
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_INCREMENT_TIMING_SCOPE,
    NewtonRaphsonConfig,
)

if TYPE_CHECKING:
    from structural_analysis.ai.fiber_frame_warm_start_features import (
        FiberFrameWarmStartModelFeatures,
    )


FIBER_FRAME_RUNTIME_BENCHMARK_SCHEMA_VERSION = (
    "public-rc-fiber-frame-warm-start-runtime.v1"
)
FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE = (
    "volatile-local-monotonic-sidecar.perf-counter-ns.v1"
)
FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE = "volatile-caller-injected-monotonic-ns.v1"
FIBER_FRAME_REFERENCE_STRATEGY = "accepted_checkpoint_newton"
FIBER_FRAME_NON_AI_STRATEGY = "deterministic_secant_warm_start"
FIBER_FRAME_AI_STRATEGY = "opt_in_ai_displacement_warm_start"
MATERIAL_RUNTIME_ACCOUNTING_SCOPE = (
    "measured_runs_attempted_newton_terminal_and_guard_assembly_material_trials;"
    "excludes_warmups_compilation_checkpoint_validation_and_full_j1_j5_replays;"
    "subset_of_inclusive_assembly_time_not_an_additional_cost"
)

FIBER_FRAME_RUNTIME_CLAIM_BOUNDARY = MappingProxyType(
    {
        "same_public_compiler_profile": True,
        "same_problem_load_history_and_solver_config": True,
        "solver_owns_equilibrium_and_convergence": True,
        "constitutive_model_owns_material_trial_and_commit": True,
        "warm_start_changes_initial_solver_coordinates_only": True,
        "failed_seeded_attempt_requires_exact_rollback": True,
        "selected_paths_require_full_j1_j5_recovery": True,
        "timing_is_local_volatile_observation": True,
        "timing_enters_numerical_identity": False,
        "generalized_speedup_claim": False,
        "training_cost_measured": False,
        "candidate_search_cost_measured": False,
        "construction_quantity_or_cost_change": False,
        "confirmed_currency_savings": False,
        "design_or_code_authority": False,
        "commercial_readiness": False,
    }
)

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class FiberFrameRuntimeBenchmarkError(ValueError):
    """Fail-closed configuration or execution error for the runtime sidecar."""


@dataclass(frozen=True)
class FiberFrameWarmStartInput:
    """Pre-step information available to an opt-in displacement predictor."""

    problem_contract_hash: str
    parent_checkpoint_state_hash: str
    previous_checkpoint_state_hash: str | None
    parent_load_factor: float
    previous_load_factor: float | None
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    physical_coordinate_scale: tuple[float, ...]
    parent_free_coordinates_m: tuple[float, ...]
    previous_free_coordinates_m: tuple[float, ...] | None
    model_features: FiberFrameWarmStartModelFeatures | None = None


@dataclass(frozen=True)
class FiberFrameWarmStartProposal:
    """Displacement-only AI proposal; no material state is accepted here."""

    free_coordinates_m: tuple[float, ...]
    uncertainty: float
    ood: bool

    def __post_init__(self) -> None:
        try:
            coordinates = tuple(float(value) for value in self.free_coordinates_m)
        except (TypeError, ValueError, OverflowError) as exc:
            raise FiberFrameRuntimeBenchmarkError(
                "free_coordinates_m must be a finite one-dimensional sequence"
            ) from exc
        if not all(math.isfinite(value) for value in coordinates):
            raise FiberFrameRuntimeBenchmarkError(
                "free_coordinates_m must contain only finite values"
            )
        uncertainty = _finite(self.uncertainty, "uncertainty")
        if uncertainty < 0.0 or uncertainty > 1.0:
            raise FiberFrameRuntimeBenchmarkError("uncertainty must be in [0, 1]")
        if type(self.ood) is not bool:
            raise FiberFrameRuntimeBenchmarkError("ood must be a boolean")
        object.__setattr__(self, "free_coordinates_m", coordinates)
        object.__setattr__(self, "uncertainty", uncertainty)


class FiberFrameWarmStartPolicy(Protocol):
    """Local opt-in predictor contract used only to propose solver coordinates."""

    policy_id: str
    policy_version: str
    artifact_hash: str

    def propose(self, value: FiberFrameWarmStartInput) -> FiberFrameWarmStartProposal:
        """Return one displacement-only proposal."""


@dataclass(frozen=True)
class FiberFrameRuntimeBenchmarkConfig:
    repetitions: int = 3
    warmup_repetitions: int = 1
    guard_max_relative_residual_ratio: float = 1.0
    maximum_ai_uncertainty: float = 1.0
    damping_factors: tuple[float, ...] = (1.0, 0.5, 0.25)
    response_absolute_tolerance: float = 1.0e-10
    response_relative_tolerance: float = 1.0e-8
    terminal_polishing: bool = False

    def __post_init__(self) -> None:
        if type(self.terminal_polishing) is not bool:
            raise FiberFrameRuntimeBenchmarkError(
                "terminal_polishing must be a boolean"
            )
        if type(self.repetitions) is not int or not 1 <= self.repetitions <= 50:
            raise FiberFrameRuntimeBenchmarkError("repetitions must be in [1, 50]")
        if (
            type(self.warmup_repetitions) is not int
            or not 0 <= self.warmup_repetitions <= 20
        ):
            raise FiberFrameRuntimeBenchmarkError(
                "warmup_repetitions must be in [0, 20]"
            )
        residual_ratio = _finite(
            self.guard_max_relative_residual_ratio,
            "guard_max_relative_residual_ratio",
        )
        if residual_ratio <= 0.0:
            raise FiberFrameRuntimeBenchmarkError(
                "guard_max_relative_residual_ratio must be positive"
            )
        uncertainty = _finite(self.maximum_ai_uncertainty, "maximum_ai_uncertainty")
        if uncertainty < 0.0 or uncertainty > 1.0:
            raise FiberFrameRuntimeBenchmarkError(
                "maximum_ai_uncertainty must be in [0, 1]"
            )
        if not isinstance(self.damping_factors, tuple) or not self.damping_factors:
            raise FiberFrameRuntimeBenchmarkError(
                "damping_factors must be a non-empty tuple"
            )
        damping = tuple(
            _finite(value, "damping_factor") for value in self.damping_factors
        )
        if any(value <= 0.0 or value > 1.0 for value in damping):
            raise FiberFrameRuntimeBenchmarkError("damping_factors must be in (0, 1]")
        if len(set(damping)) != len(damping):
            raise FiberFrameRuntimeBenchmarkError("damping_factors must be unique")
        absolute = _finite(
            self.response_absolute_tolerance,
            "response_absolute_tolerance",
        )
        relative = _finite(
            self.response_relative_tolerance,
            "response_relative_tolerance",
        )
        if absolute < 0.0 or relative < 0.0:
            raise FiberFrameRuntimeBenchmarkError(
                "response tolerances must be non-negative"
            )
        object.__setattr__(self, "guard_max_relative_residual_ratio", residual_ratio)
        object.__setattr__(self, "maximum_ai_uncertainty", uncertainty)
        object.__setattr__(self, "damping_factors", damping)
        object.__setattr__(self, "response_absolute_tolerance", absolute)
        object.__setattr__(self, "response_relative_tolerance", relative)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repetitions": self.repetitions,
            "warmup_repetitions": self.warmup_repetitions,
            "guard_max_relative_residual_ratio": (
                self.guard_max_relative_residual_ratio
            ),
            "maximum_ai_uncertainty": self.maximum_ai_uncertainty,
            "damping_factors": list(self.damping_factors),
            "response_absolute_tolerance": self.response_absolute_tolerance,
            "response_relative_tolerance": self.response_relative_tolerance,
            **({"terminal_polishing": True} if self.terminal_polishing else {}),
        }


@dataclass(frozen=True)
class FiberFrameRuntimeBenchmarkResult:
    """Serializable volatile report plus caller-local numerical paths."""

    status: str
    measurement_contract_pass: bool
    report_hash: str
    experiment_identity_hash: str
    _payload: Mapping[str, Any] = field(repr=False, compare=False)
    _paths: Mapping[str, tuple[StatefulFiberFrame2DLoadPathResult, ...]] = field(
        repr=False,
        compare=False,
    )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self._payload))

    def path(
        self,
        strategy: str,
        repetition: int = 0,
    ) -> StatefulFiberFrame2DLoadPathResult:
        try:
            rows = self._paths[strategy]
            return rows[repetition]
        except (KeyError, IndexError) as exc:
            raise KeyError(
                f"No measured path for strategy={strategy!r}, repetition={repetition}"
            ) from exc


@dataclass(frozen=True)
class _Attempt:
    result: StatefulFiberFrame2DLoadStepResult | None
    solve_wall_ns: int
    stateful_runtime: Mapping[str, Any]
    newton_runtime: Mapping[str, Any]
    parent_checkpoint_state_hash: str
    initial_coordinates_hash: str | None
    exception_type: str | None = None


@dataclass(frozen=True)
class _VariantExecution:
    path: StatefulFiberFrame2DLoadPathResult
    wall_ns: int
    selected_solve_wall_ns: int
    attempted_solve_wall_ns: int
    inference_wall_ns: int
    guard_wall_ns: int
    seeded_attempt_wall_ns: int
    baseline_recovery_wall_ns: int
    guard_assembly_call_count: int
    attempted_newton_iteration_count: int
    attempted_line_search_evaluation_count: int
    selected_stateful_runtime: Mapping[str, Any]
    attempted_stateful_runtime: Mapping[str, Any]
    selected_newton_runtime: Mapping[str, Any]
    attempted_newton_runtime: Mapping[str, Any]
    step_rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _EpisodeReplaySource:
    problem: Any
    plan: Any
    scaling: Any
    chain: Any
    kinematic: Any
    material: Any
    binding: Any
    path: StatefulFiberFrame2DLoadPathResult
    terminal: Any


def benchmark_public_rc_fiber_frame_warm_starts(
    model: CanonicalModel,
    config: public_api.PublicRCFiberFrameConfig | None = None,
    *,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig | None = None,
    ai_opt_in: bool = False,
    ai_policy: FiberFrameWarmStartPolicy | None = None,
    source_revision: str | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
) -> FiberFrameRuntimeBenchmarkResult:
    """Measure reference, non-AI secant, and optional guarded AI warm starts.

    No speed threshold is a correctness gate.  ``measurement_contract_pass``
    means the arms were comparable and the selected paths passed the full
    deterministic recovery chain within the declared response tolerances.
    """

    if type(model) is not CanonicalModel:
        raise FiberFrameRuntimeBenchmarkError("model must be a CanonicalModel")
    if config is not None and type(config) is not public_api.PublicRCFiberFrameConfig:
        raise FiberFrameRuntimeBenchmarkError(
            "config must be a PublicRCFiberFrameConfig"
        )
    if type(ai_opt_in) is not bool:
        raise FiberFrameRuntimeBenchmarkError("ai_opt_in must be a boolean")
    if not callable(clock_ns):
        raise FiberFrameRuntimeBenchmarkError("clock_ns must be callable")
    measurement_profile = (
        FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE
        if clock_ns is perf_counter_ns
        else FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE
    )
    perf_counter_clock = measurement_profile == FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE
    cfg = public_api.PublicRCFiberFrameConfig() if config is None else config
    measure_cfg = benchmark_config or FiberFrameRuntimeBenchmarkConfig()
    policy_identity = _policy_identity(ai_policy) if ai_opt_in else None
    if ai_opt_in and ai_policy is None:
        raise FiberFrameRuntimeBenchmarkError(
            "ai_policy is required when ai_opt_in is true"
        )
    revision = _optional_source_revision(source_revision)
    timing_evidence_available = bool(revision is not None and perf_counter_clock)

    snapshot = model.detached_analysis_snapshot()
    compile_started = _tick(clock_ns)
    compiled, unsupported, warnings = public_api._compile(snapshot)
    compile_wall_ns = _elapsed(clock_ns, compile_started)
    if compiled is None:
        reason = unsupported[0].get("kind", "unsupported_public_profile")
        raise FiberFrameRuntimeBenchmarkError(
            f"model is outside the bounded public RC fiber profile: {reason}"
        )
    problem = compiled.problem
    load_factors = cfg.target_load_factors
    solver_config = NewtonRaphsonConfig(
        residual_tolerance=cfg.residual_tolerance,
        increment_tolerance=cfg.increment_tolerance_m,
        max_iterations=cfg.maximum_iterations,
        terminal_polishing=measure_cfg.terminal_polishing,
    )
    coordinate_binding_hash = canonical_hash(
        {
            "problem_contract_hash": problem.contract_hash,
            "free_global_dofs": list(problem.free_global_dofs),
            "physical_coordinate_scale": problem.physical_coordinate_scale.tolist(),
            "coordinate_profile": "generalized-free-solver-coordinates-m.v1",
        }
    )
    solver_config_hash = canonical_hash(_solver_config_payload(solver_config))
    load_history_hash = canonical_hash(list(load_factors))
    experiment_identity_hash = canonical_hash(
        {
            "schema_version": FIBER_FRAME_RUNTIME_BENCHMARK_SCHEMA_VERSION,
            "canonical_model_checksum": snapshot.canonical_model_checksum,
            "problem_contract_hash": problem.contract_hash,
            "compiler_profile": public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
            "solver_id": public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
            "load_history_hash": load_history_hash,
            "solver_config_hash": solver_config_hash,
            "coordinate_binding_hash": coordinate_binding_hash,
            "benchmark_configuration": measure_cfg.to_dict(),
            "measurement_profile": measurement_profile,
            "ai_opt_in": ai_opt_in,
            "policy": policy_identity,
            "source_revision": revision,
        }
    )

    strategies = [FIBER_FRAME_REFERENCE_STRATEGY, FIBER_FRAME_NON_AI_STRATEGY]
    if ai_opt_in:
        strategies.append(FIBER_FRAME_AI_STRATEGY)

    if measure_cfg.warmup_repetitions:
        warmup_started = _tick(clock_ns)
        measured_warmup_strategy_wall_ns = {strategy: 0 for strategy in strategies}
        for warmup_index in range(measure_cfg.warmup_repetitions):
            for strategy in _rotated(strategies, warmup_index):
                run = _run_strategy(
                    strategy,
                    problem,
                    load_factors,
                    solver_config,
                    measure_cfg,
                    ai_policy=ai_policy,
                    clock_ns=clock_ns,
                )
                measured_warmup_strategy_wall_ns[strategy] += run.wall_ns
        warmup_total_wall_ns: int | None = _elapsed(clock_ns, warmup_started)
        warmup_strategy_wall_ns: dict[str, int | None] = dict(
            measured_warmup_strategy_wall_ns
        )
    else:
        warmup_total_wall_ns = None
        warmup_strategy_wall_ns = {strategy: None for strategy in strategies}

    run_rows: list[dict[str, Any]] = []
    paths: dict[str, list[StatefulFiberFrame2DLoadPathResult]] = {
        strategy: [] for strategy in strategies
    }
    reference_episode_hashes: set[str] = set()
    reference_episode_adapter_hashes: set[str] = set()
    reference_episode_sources: list[tuple[int, _EpisodeReplaySource | None]] = []
    for repetition in range(measure_cfg.repetitions):
        order = _rotated(strategies, repetition)
        executions: dict[str, _VariantExecution] = {}
        rows_for_repetition: dict[str, dict[str, Any]] = {}
        for order_index, strategy in enumerate(order):
            outer_started = _tick(clock_ns)
            execution = _run_strategy(
                strategy,
                problem,
                load_factors,
                solver_config,
                measure_cfg,
                ai_policy=ai_policy,
                clock_ns=clock_ns,
            )
            verification_started = _tick(clock_ns)
            verification, episode_source = _verify_selected_path(
                snapshot,
                compiled,
                execution.path,
            )
            verification_wall_ns = _elapsed(clock_ns, verification_started)
            total_wall_ns = _elapsed(clock_ns, outer_started)
            if strategy == FIBER_FRAME_REFERENCE_STRATEGY:
                reference_episode_sources.append((repetition, episode_source))
            row = {
                "repetition": repetition,
                "execution_order_index": order_index,
                "strategy": strategy,
                "status": execution.path.status,
                "contract_pass": execution.path.contract_pass,
                "path_hash": canonical_hash(execution.path.to_dict()),
                "terminal_checkpoint_state_hash": (
                    execution.path.final_checkpoint.state_hash
                ),
                "load_step_count": len(execution.path.steps),
                "committed_step_count": sum(
                    int(step.committed) for step in execution.path.steps
                ),
                "newton_iteration_count": sum(
                    len(step.trial_solution.convergence_history)
                    for step in execution.path.steps
                ),
                "attempted_newton_iteration_count": (
                    execution.attempted_newton_iteration_count
                ),
                "attempted_line_search_evaluation_count": (
                    execution.attempted_line_search_evaluation_count
                ),
                "wall_ns": execution.wall_ns,
                "selected_solve_wall_ns": execution.selected_solve_wall_ns,
                "attempted_solve_wall_ns": execution.attempted_solve_wall_ns,
                "verification_wall_ns": verification_wall_ns,
                "execution_and_authority_verification_wall_ns": total_wall_ns,
                "inference_wall_ns": execution.inference_wall_ns,
                "guard_wall_ns": execution.guard_wall_ns,
                "seeded_attempt_wall_ns": execution.seeded_attempt_wall_ns,
                "baseline_recovery_wall_ns": execution.baseline_recovery_wall_ns,
                "guard_assembly_call_count": execution.guard_assembly_call_count,
                "selected_stateful_runtime": dict(execution.selected_stateful_runtime),
                "attempted_stateful_runtime": dict(
                    execution.attempted_stateful_runtime
                ),
                "selected_newton_runtime": dict(execution.selected_newton_runtime),
                "attempted_newton_runtime": dict(execution.attempted_newton_runtime),
                "steps": [dict(step) for step in execution.step_rows],
                "authority_verification": verification,
            }
            executions[strategy] = execution
            rows_for_repetition[strategy] = row
            paths[strategy].append(execution.path)

        reference = executions[FIBER_FRAME_REFERENCE_STRATEGY].path
        for strategy, row in rows_for_repetition.items():
            comparison_started = _tick(clock_ns)
            comparison = _compare_paths(
                reference,
                executions[strategy].path,
                absolute_tolerance=measure_cfg.response_absolute_tolerance,
                relative_tolerance=measure_cfg.response_relative_tolerance,
            )
            comparison_wall_ns = _elapsed(clock_ns, comparison_started)
            row["reference_comparison"] = comparison
            row["comparison_wall_ns"] = comparison_wall_ns
            row["verified_end_to_end_wall_ns"] = (
                int(row["execution_and_authority_verification_wall_ns"])
                + comparison_wall_ns
            )
            run_rows.append(row)

    reference_episode_rows: list[dict[str, Any]] = []
    for repetition, source in reference_episode_sources:
        episode_started = _tick(clock_ns)
        episode_verification = _verify_reference_solver_episode(source)
        episode_wall_ns = _elapsed(clock_ns, episode_started)
        reference_episode_rows.append(
            {
                "repetition": repetition,
                "wall_ns": episode_wall_ns,
                **episode_verification,
            }
        )
        if episode_verification.get("contract_pass") is True:
            reference_episode_adapter_hashes.add(
                str(episode_verification["solver_episode_adapter_hash"])
            )
            reference_episode_hashes.add(
                str(episode_verification["solver_episode_hash"])
            )

    summaries = {
        strategy: _strategy_summary(
            [row for row in run_rows if row["strategy"] == strategy]
        )
        for strategy in strategies
    }
    comparisons = {
        strategy: _observed_comparison(
            summaries[FIBER_FRAME_REFERENCE_STRATEGY],
            summaries[strategy],
            timing_evidence_available=timing_evidence_available,
        )
        for strategy in strategies
        if strategy != FIBER_FRAME_REFERENCE_STRATEGY
    }
    required_rows = run_rows
    measurement_contract_pass = bool(
        required_rows
        and len(required_rows) == measure_cfg.repetitions * len(strategies)
        and revision is not None
        and len(reference_episode_hashes) == 1
        and len(reference_episode_adapter_hashes) == 1
        and len(reference_episode_rows) == measure_cfg.repetitions
        and all(row["contract_pass"] for row in reference_episode_rows)
        and all(row["contract_pass"] for row in required_rows)
        and all(
            row["authority_verification"].get("contract_pass") is True
            for row in required_rows
        )
        and all(
            row["reference_comparison"].get("full_history_response_match") is True
            for row in required_rows
        )
    )
    status = "ready" if measurement_contract_pass else "blocked"
    inference_total = sum(int(row["inference_wall_ns"]) for row in run_rows)
    guard_total = sum(int(row["guard_wall_ns"]) for row in run_rows)
    recovery_total = sum(int(row["baseline_recovery_wall_ns"]) for row in run_rows)
    verification_total = sum(
        int(row["verification_wall_ns"]) + int(row["comparison_wall_ns"])
        for row in run_rows
    )
    material_total = _aggregate_material_trial(
        [_run_material_trial(row) for row in run_rows]
    )
    payload: dict[str, Any] = {
        "schema_version": FIBER_FRAME_RUNTIME_BENCHMARK_SCHEMA_VERSION,
        "report_hash": "sha256:" + "0" * 64,
        "status": status,
        "measurement_contract_pass": measurement_contract_pass,
        "experiment_identity_hash": experiment_identity_hash,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_profile": measurement_profile,
        "measurement_eligibility": {
            "source_revision_bound": revision is not None,
            "local_timing_evidence_eligible": timing_evidence_available,
            "injected_clock_for_contract_testing_only": not perf_counter_clock,
        },
        "bindings": {
            "canonical_model_checksum": snapshot.canonical_model_checksum,
            "input_checksum": snapshot.input_checksum,
            "problem_contract_hash": problem.contract_hash,
            "compiler_profile": public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE,
            "solver_id": public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID,
            "load_history_hash": load_history_hash,
            "solver_config_hash": solver_config_hash,
            "free_coordinate_binding_hash": coordinate_binding_hash,
            "source_revision": revision,
            "source_revision_bound": revision is not None,
            "reference_solver_episode_hash": _only_value_or_none(
                reference_episode_hashes
            ),
            "reference_solver_episode_adapter_hash": _only_value_or_none(
                reference_episode_adapter_hashes
            ),
            "reference_solver_episode_runtime_profile": (
                FIBER_FRAME_SOLVER_EPISODE_RUNTIME_PROFILE
            ),
        },
        "configuration": {
            "public_solver": {
                "load_factors": list(load_factors),
                **_solver_config_payload(solver_config),
            },
            "benchmark": measure_cfg.to_dict(),
            "ai_opt_in": ai_opt_in,
            "policy": policy_identity,
            "policy_execution_contract": {
                "instance_owner": "caller",
                "same_instance_reused_across_warmups_and_repetitions": ai_opt_in,
                "automatic_state_reset_between_runs": False,
                "deterministic_inference_asserted": False,
            },
        },
        "environment": _environment_payload(measurement_profile),
        "compile_wall_ns": compile_wall_ns,
        "warnings": list(warnings),
        "warmup": {
            "repetitions": measure_cfg.warmup_repetitions,
            "total_wall_ns": warmup_total_wall_ns,
            "strategy_wall_ns": warmup_strategy_wall_ns,
            "included_in_measured_summaries": False,
        },
        "runs": sorted(run_rows, key=lambda row: (row["repetition"], row["strategy"])),
        "reference_solver_episode_verification": {
            "comparable_arm_timing": False,
            "reason": "baseline_step_size_episode_schema_cannot_label_warm_start_execution",
            "runs": reference_episode_rows,
        },
        "summaries": summaries,
        "observed_comparisons": comparisons,
        "calculation_cost_accounting": {
            "linear_solve_scope": VECTOR_INCREMENT_TIMING_SCOPE,
            "individual_solve_wall_time": {
                strategy: {
                    "selected_solver_wall_ns": summaries[strategy][
                        "selected_solver_wall_ns"
                    ],
                    "attempted_solver_wall_ns": summaries[strategy][
                        "attempted_solver_wall_ns"
                    ],
                    "attempted_newton_total_wall_ns": summaries[strategy][
                        "attempted_newton_total_wall_ns"
                    ],
                    "attempted_stateful_total_wall_ns": summaries[strategy][
                        "attempted_stateful_total_wall_ns"
                    ],
                    "attempted_newton_assembly_wall_ns": summaries[strategy][
                        "attempted_newton_assembly_wall_ns"
                    ],
                    "attempted_linear_solve_wall_ns": summaries[strategy][
                        "attempted_linear_solve_wall_ns"
                    ],
                    "attempted_terminal_trial_assembly_wall_ns": summaries[strategy][
                        "attempted_terminal_trial_assembly_wall_ns"
                    ],
                    "attempted_material_trial_wall_ns": summaries[strategy][
                        "attempted_material_trial_wall_ns"
                    ],
                    "attempted_residual_assembly_call_count": summaries[strategy][
                        "attempted_residual_assembly_call_count"
                    ],
                }
                for strategy in strategies
            },
            "data_generation_wall_ns": None,
            "data_generation_reason": "not_run_by_this_benchmark",
            "training_wall_ns": None,
            "training_reason": "not_run_by_this_benchmark",
            "inference_wall_ns": inference_total if ai_opt_in else None,
            "inference_reason": ("measured" if ai_opt_in else "ai_not_opted_in"),
            "guard_wall_ns": guard_total,
            "full_path_verification_wall_ns": verification_total,
            "reference_solver_episode_verification_wall_ns": sum(
                int(row["wall_ns"]) for row in reference_episode_rows
            ),
            "failure_recovery_wall_ns": recovery_total,
            "candidate_search_wall_ns": None,
            "candidate_search_reason": "one_model_runtime_comparison_only",
            "material_update_wall_ns": (
                material_total["wall_ns"]
                if material_total["coverage_complete"]
                else None
            ),
            "material_update_reason": (
                "measured_material_integrate_api_calls"
                if material_total["coverage_complete"]
                else "material_trial_coverage_incomplete"
            ),
            "material_update_scope": MATERIAL_RUNTIME_ACCOUNTING_SCOPE,
            "material_trial": material_total,
            "io_wall_ns": None,
            "io_reason": "model_loading_and_report_persistence_not_run_by_benchmark",
            "cpu_process_time_ns": None,
            "gpu_time_ns": None,
            "peak_memory_bytes": None,
        },
        "construction_cost_accounting": {
            "physical_design_changed": False,
            "baseline_quantities": None,
            "candidate_quantities": None,
            "price_table_hash": None,
            "currency": None,
            "confirmed_currency_savings": None,
            "reason": "identical_physical_model_runtime_comparison_only",
        },
        "claims": {
            "observed_local_timing_available": timing_evidence_available,
            "injected_clock_timing_is_evidentiary": False,
            "positive_speedup_required_for_contract": False,
            "generalized_speedup_claimed": False,
            "physical_performance_improvement_claimed": False,
            "construction_savings_claimed": False,
        },
        "claim_boundary": {
            **FIBER_FRAME_RUNTIME_CLAIM_BOUNDARY,
            "timing_is_local_volatile_observation": timing_evidence_available,
        },
    }
    payload["report_hash"] = canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )
    return FiberFrameRuntimeBenchmarkResult(
        status=status,
        measurement_contract_pass=measurement_contract_pass,
        report_hash=str(payload["report_hash"]),
        experiment_identity_hash=experiment_identity_hash,
        _payload=payload,
        _paths=MappingProxyType(
            {
                strategy: tuple(strategy_paths)
                for strategy, strategy_paths in paths.items()
            }
        ),
    )


def _run_strategy(
    strategy: str,
    problem: StatefulFiberFrame2DProblem,
    load_factors: tuple[float, ...],
    solver_config: NewtonRaphsonConfig,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig,
    *,
    ai_policy: FiberFrameWarmStartPolicy | None,
    clock_ns: Callable[[], int],
) -> _VariantExecution:
    started = _tick(clock_ns)
    first = initial_stateful_fiber_frame2d_checkpoint(problem)
    accepted = first
    checkpoints = [first]
    selected_steps: list[StatefulFiberFrame2DLoadStepResult] = []
    step_rows: list[dict[str, Any]] = []
    selected_attempts: list[_Attempt] = []
    all_attempts: list[_Attempt] = []
    selected_solve_wall_ns = 0
    attempted_solve_wall_ns = 0
    inference_wall_ns = 0
    guard_wall_ns = 0
    seeded_attempt_wall_ns = 0
    baseline_recovery_wall_ns = 0
    guard_assembly_call_count = 0

    for step_index, target_load_factor in enumerate(load_factors):
        parent = accepted
        parent_bytes = parent.canonical_bytes()
        proposal: tuple[float, ...] | None = None
        proposal_source = "reference"
        proposal_hash: str | None = None
        uncertainty: float | None = None
        ood: bool | None = None
        proposal_reason = "reference_seed"
        inference_ns = 0
        if strategy == FIBER_FRAME_NON_AI_STRATEGY:
            proposal_source = "non_ai_secant"
            proposal, proposal_reason = _secant_proposal(
                problem, checkpoints, target_load_factor
            )
        elif strategy == FIBER_FRAME_AI_STRATEGY:
            proposal_source = "ai_policy"
            inference_started = _tick(clock_ns)
            proposal, uncertainty, ood, proposal_reason = _ai_proposal(
                ai_policy,
                problem,
                checkpoints,
                target_load_factor,
                benchmark_config,
            )
            inference_ns = _elapsed(clock_ns, inference_started)
            inference_wall_ns += inference_ns
        elif strategy != FIBER_FRAME_REFERENCE_STRATEGY:
            raise FiberFrameRuntimeBenchmarkError(f"unknown strategy: {strategy}")

        if proposal is not None:
            proposal_hash = canonical_hash(
                {
                    "coordinate_binding_hash": canonical_hash(
                        {
                            "problem_contract_hash": problem.contract_hash,
                            "free_global_dofs": list(problem.free_global_dofs),
                            "physical_coordinate_scale": (
                                problem.physical_coordinate_scale.tolist()
                            ),
                        }
                    ),
                    "proposal_source": proposal_source,
                    "parent_checkpoint_state_hash": parent.state_hash,
                    "target_load_factor": target_load_factor,
                    "free_coordinates_m": list(proposal),
                }
            )
        if parent.canonical_bytes() != parent_bytes:
            raise FiberFrameRuntimeBenchmarkError(
                "warm-start proposal mutated the accepted checkpoint"
            )

        guard_material = MaterialTrialRuntimeRecorder(clock_ns=clock_ns)
        guard_started = _tick(clock_ns)
        guarded_seed, guard_row = _guard_proposal(
            problem,
            parent,
            target_load_factor,
            proposal,
            benchmark_config,
            solver_config,
            clock_ns=clock_ns,
            material_runtime=guard_material,
        )
        guard_ns = _elapsed(clock_ns, guard_started)
        guard_wall_ns += guard_ns
        guard_assembly_call_count += int(guard_row["assembly_count"])
        if parent.canonical_bytes() != parent_bytes:
            raise FiberFrameRuntimeBenchmarkError(
                "warm-start guard mutated the accepted checkpoint"
            )

        seeded_attempt: _Attempt | None = None
        recovery_attempt: _Attempt | None = None
        baseline_attempt: _Attempt | None = None
        selected_source = "reference"
        rollback_exact: bool | None = None
        if guarded_seed is not None:
            seeded_attempt = _timed_solve(
                problem,
                parent,
                target_load_factor,
                solver_config,
                initial_free_coordinates_m=guarded_seed,
                clock_ns=clock_ns,
                capture_failure=True,
            )
            seeded_attempt_wall_ns += seeded_attempt.solve_wall_ns
            all_attempts.append(seeded_attempt)
            if seeded_attempt.result is not None and seeded_attempt.result.committed:
                selected = seeded_attempt.result
                selected_attempt = seeded_attempt
                selected_source = proposal_source
            else:
                rollback_exact = _rollback_exact(
                    seeded_attempt.result,
                    parent,
                    parent_bytes,
                )
                if not rollback_exact:
                    raise FiberFrameRuntimeBenchmarkError(
                        "failed seeded Newton attempt did not roll back exactly"
                    )
                recovery_attempt = _timed_solve(
                    problem,
                    parent,
                    target_load_factor,
                    solver_config,
                    initial_free_coordinates_m=None,
                    clock_ns=clock_ns,
                )
                baseline_recovery_wall_ns += recovery_attempt.solve_wall_ns
                all_attempts.append(recovery_attempt)
                if recovery_attempt.result is None:
                    raise FiberFrameRuntimeBenchmarkError(
                        "baseline recovery did not return a solver result"
                    )
                selected = recovery_attempt.result
                selected_attempt = recovery_attempt
                selected_source = "baseline_recovery"
        else:
            baseline_attempt = _timed_solve(
                problem,
                parent,
                target_load_factor,
                solver_config,
                initial_free_coordinates_m=None,
                clock_ns=clock_ns,
            )
            all_attempts.append(baseline_attempt)
            if baseline_attempt.result is None:
                raise FiberFrameRuntimeBenchmarkError(
                    "baseline solve did not return a solver result"
                )
            selected = baseline_attempt.result
            selected_attempt = baseline_attempt
            selected_source = (
                "reference" if proposal is None else "guard_rejected_baseline"
            )

        selected_attempts.append(selected_attempt)
        selected_solve_wall_ns += selected_attempt.solve_wall_ns
        attempted_solve_wall_ns += sum(
            attempt.solve_wall_ns
            for attempt in (seeded_attempt, recovery_attempt, baseline_attempt)
            if attempt is not None
        )
        selected_steps.append(selected)
        step_rows.append(
            {
                "step_index": step_index,
                "target_load_factor": target_load_factor,
                "proposal_source": proposal_source,
                "proposal_available": proposal is not None,
                "proposal_hash": proposal_hash,
                "proposal_reason": proposal_reason,
                "uncertainty": uncertainty,
                "ood": ood,
                "inference_wall_ns": inference_ns,
                "guard_wall_ns": guard_ns,
                "guard": guard_row,
                "guard_material_trial": guard_material.to_dict(),
                "seeded_attempt": _attempt_payload(seeded_attempt),
                "baseline_attempt": _attempt_payload(baseline_attempt),
                "baseline_recovery": _attempt_payload(recovery_attempt),
                "failed_seeded_attempt_rollback_exact": rollback_exact,
                "selected_source": selected_source,
                "selected_attempt": _attempt_payload(selected_attempt),
                "selected_committed": selected.committed,
                "selected_step_hash": canonical_hash(selected.to_dict()),
            }
        )
        if not selected.committed:
            break
        accepted = selected.accepted_checkpoint
        checkpoints.append(accepted)

    path = StatefulFiberFrame2DLoadPathResult(
        status=(
            "ready"
            if len(selected_steps) == len(load_factors)
            and all(step.committed for step in selected_steps)
            else "blocked"
        ),
        initial_checkpoint=first,
        final_checkpoint=accepted,
        steps=tuple(selected_steps),
    )
    return _VariantExecution(
        path=path,
        wall_ns=_elapsed(clock_ns, started),
        selected_solve_wall_ns=selected_solve_wall_ns,
        attempted_solve_wall_ns=attempted_solve_wall_ns,
        inference_wall_ns=inference_wall_ns,
        guard_wall_ns=guard_wall_ns,
        seeded_attempt_wall_ns=seeded_attempt_wall_ns,
        baseline_recovery_wall_ns=baseline_recovery_wall_ns,
        guard_assembly_call_count=guard_assembly_call_count,
        attempted_newton_iteration_count=sum(
            len(attempt.result.trial_solution.convergence_history)
            for attempt in all_attempts
            if attempt.result is not None
        ),
        attempted_line_search_evaluation_count=sum(
            sum(
                int(row.get("attempt_count", len(row.get("attempts", ()))))
                for row in attempt.result.trial_solution.line_search_history
            )
            for attempt in all_attempts
            if attempt.result is not None
        ),
        selected_stateful_runtime=_aggregate_stateful_runtime(selected_attempts),
        attempted_stateful_runtime=_aggregate_stateful_runtime(all_attempts),
        selected_newton_runtime=_aggregate_newton_runtime(selected_attempts),
        attempted_newton_runtime=_aggregate_newton_runtime(all_attempts),
        step_rows=tuple(step_rows),
    )


def _timed_solve(
    problem: StatefulFiberFrame2DProblem,
    parent: Any,
    target_load_factor: float,
    solver_config: NewtonRaphsonConfig,
    *,
    initial_free_coordinates_m: tuple[float, ...] | None,
    clock_ns: Callable[[], int],
    capture_failure: bool = False,
) -> _Attempt:
    runtime = StatefulFiberFrame2DLoadStepRuntimeRecorder(clock_ns=clock_ns)
    started = _tick(clock_ns)
    try:
        result = solve_stateful_fiber_frame2d_load_step(
            problem,
            parent,
            target_load_factor=target_load_factor,
            config=solver_config,
            initial_free_coordinates_m=initial_free_coordinates_m,
            runtime_recorder=runtime,
        )
    except Exception as exc:
        if isinstance(exc, MaterialTrialTimingError):
            raise
        _check_material_timing(runtime)
        if not capture_failure:
            raise
        result = None
        exception_type = type(exc).__name__
    else:
        _check_material_timing(runtime)
        exception_type = None
    wall_ns = _elapsed(clock_ns, started)
    return _Attempt(
        result=result,
        solve_wall_ns=wall_ns,
        stateful_runtime=runtime.to_dict(),
        newton_runtime=runtime.newton.to_dict(),
        parent_checkpoint_state_hash=parent.state_hash,
        initial_coordinates_hash=(
            canonical_hash(list(initial_free_coordinates_m))
            if initial_free_coordinates_m is not None
            else None
        ),
        exception_type=exception_type,
    )


def _check_material_timing(
    runtime: StatefulFiberFrame2DLoadStepRuntimeRecorder,
) -> None:
    # An outer timing finally can replace an inner instrumentation exception.
    # Never classify that attempt as a recoverable physical solver failure.
    if (
        runtime.newton.material.timing_error_count
        or runtime.terminal_material.timing_error_count
    ):
        raise MaterialTrialTimingError("material trial timing failed during solve")


def _guard_proposal(
    problem: StatefulFiberFrame2DProblem,
    parent: Any,
    target_load_factor: float,
    proposal: tuple[float, ...] | None,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig,
    solver_config: NewtonRaphsonConfig,
    *,
    clock_ns: Callable[[], int],
    material_runtime: MaterialTrialRuntimeRecorder | None = None,
) -> tuple[tuple[float, ...] | None, dict[str, Any]]:
    if proposal is None:
        return None, {
            "status": "not_applicable",
            "reason_code": "proposal_unavailable",
            "baseline_relative_residual": None,
            "accepted_relative_residual": None,
            "accepted_damping_factor": None,
            "assembly_count": 0,
            "assembly_wall_ns": 0,
            "guard_receipt_hash": None,
        }
    expected_shape = (len(problem.free_global_dofs),)
    candidate = np.asarray(proposal, dtype=np.float64)
    if candidate.shape != expected_shape or not np.all(np.isfinite(candidate)):
        return None, _guard_rejection("proposal_shape_or_finite_invalid")
    parent_coordinates = np.asarray(
        _free_coordinates(problem, parent), dtype=np.float64
    )
    baseline_started = _tick(clock_ns)
    try:
        baseline_assembly = assemble_stateful_fiber_frame2d(
            problem,
            parent,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=parent_coordinates,
            material_runtime=material_runtime,
        )
    finally:
        baseline_wall_ns = _elapsed(clock_ns, baseline_started)
    baseline_relative_residual = _relative_residual(
        problem, baseline_assembly.residual_kn
    )
    limit = max(
        baseline_relative_residual * benchmark_config.guard_max_relative_residual_ratio,
        solver_config.residual_tolerance,
    )
    attempts: list[dict[str, Any]] = []
    assembly_count = 1
    assembly_wall_ns = baseline_wall_ns
    accepted: tuple[float, ...] | None = None
    accepted_relative_residual: float | None = None
    accepted_damping: float | None = None
    for damping in benchmark_config.damping_factors:
        damped = parent_coordinates + damping * (candidate - parent_coordinates)
        assembly_started = _tick(clock_ns)
        assembly_count += 1
        try:
            assembly = assemble_stateful_fiber_frame2d(
                problem,
                parent,
                target_load_factor=target_load_factor,
                trial_free_coordinates_m=damped,
                material_runtime=material_runtime,
            )
            relative_residual = _relative_residual(problem, assembly.residual_kn)
        except (TypeError, ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
            attempt_wall_ns = _elapsed(clock_ns, assembly_started)
            assembly_wall_ns += attempt_wall_ns
            attempts.append(
                {
                    "damping_factor": damping,
                    "status": "assembly_error",
                    "relative_residual": None,
                    "assembly_wall_ns": attempt_wall_ns,
                    "exception_type": type(exc).__name__,
                }
            )
            continue
        attempt_wall_ns = _elapsed(clock_ns, assembly_started)
        assembly_wall_ns += attempt_wall_ns
        attempts.append(
            {
                "damping_factor": damping,
                "status": "assembled",
                "relative_residual": relative_residual,
                "assembly_wall_ns": attempt_wall_ns,
                "exception_type": None,
            }
        )
        if relative_residual <= limit:
            accepted = tuple(float(value) for value in damped)
            accepted_relative_residual = relative_residual
            accepted_damping = damping
            break
    body = {
        "status": "accepted" if accepted is not None else "rejected",
        "reason_code": (
            "physical_residual_guard_passed"
            if accepted is not None
            else "physical_residual_guard_failed"
        ),
        "baseline_relative_residual": baseline_relative_residual,
        "maximum_accepted_relative_residual": limit,
        "accepted_relative_residual": accepted_relative_residual,
        "accepted_damping_factor": accepted_damping,
        "assembly_count": assembly_count,
        "assembly_wall_ns": assembly_wall_ns,
        "baseline_assembly_wall_ns": baseline_wall_ns,
        "attempts": attempts,
        "parent_checkpoint_state_hash": parent.state_hash,
        "target_load_factor": target_load_factor,
    }
    body["guard_receipt_hash"] = canonical_hash(body)
    return accepted, body


def _guard_rejection(reason_code: str) -> dict[str, Any]:
    body = {
        "status": "rejected",
        "reason_code": reason_code,
        "baseline_relative_residual": None,
        "maximum_accepted_relative_residual": None,
        "accepted_relative_residual": None,
        "accepted_damping_factor": None,
        "assembly_count": 0,
        "assembly_wall_ns": 0,
        "attempts": [],
    }
    body["guard_receipt_hash"] = canonical_hash(body)
    return body


def _secant_proposal(
    problem: StatefulFiberFrame2DProblem,
    checkpoints: list[Any],
    target_load_factor: float,
) -> tuple[tuple[float, ...] | None, str]:
    if len(checkpoints) < 2:
        return None, "insufficient_accepted_history"
    previous = checkpoints[-2]
    current = checkpoints[-1]
    denominator = current.load_factor - previous.load_factor
    if denominator <= 0.0:
        return None, "non_increasing_accepted_history"
    previous_coordinates = np.asarray(_free_coordinates(problem, previous))
    current_coordinates = np.asarray(_free_coordinates(problem, current))
    factor = (target_load_factor - current.load_factor) / denominator
    proposed = current_coordinates + factor * (
        current_coordinates - previous_coordinates
    )
    if not np.all(np.isfinite(proposed)):
        return None, "nonfinite_secant_prediction"
    return tuple(float(value) for value in proposed), "secant_prediction_available"


def _ai_proposal(
    policy: FiberFrameWarmStartPolicy | None,
    problem: StatefulFiberFrame2DProblem,
    checkpoints: list[Any],
    target_load_factor: float,
    benchmark_config: FiberFrameRuntimeBenchmarkConfig,
) -> tuple[tuple[float, ...] | None, float | None, bool | None, str]:
    if policy is None:
        return None, None, None, "policy_unavailable"
    model_features = None
    try:
        model_feature_profile = getattr(policy, "model_feature_profile", None)
        if model_feature_profile is not None:
            from structural_analysis.ai.fiber_frame_warm_start_features import (
                MODEL_FEATURE_PROFILE,
                fiber_frame_warm_start_model_features,
            )

            if model_feature_profile != MODEL_FEATURE_PROFILE:
                return None, None, None, "policy_model_feature_profile_unsupported"
            # Only immutable authored geometry/material/load metadata is read.
            # This call is inside the existing inference timing interval.
            model_features = fiber_frame_warm_start_model_features(problem)
    except Exception:
        return None, None, None, "policy_model_feature_preparation_failed"
    parent = checkpoints[-1]
    previous = checkpoints[-2] if len(checkpoints) >= 2 else None
    policy_input = FiberFrameWarmStartInput(
        problem_contract_hash=problem.contract_hash,
        parent_checkpoint_state_hash=parent.state_hash,
        previous_checkpoint_state_hash=(
            previous.state_hash if previous is not None else None
        ),
        parent_load_factor=parent.load_factor,
        previous_load_factor=(previous.load_factor if previous is not None else None),
        target_load_factor=target_load_factor,
        free_global_dofs=problem.free_global_dofs,
        physical_coordinate_scale=tuple(
            float(problem.physical_coordinate_scale[dof])
            for dof in problem.free_global_dofs
        ),
        parent_free_coordinates_m=_free_coordinates(problem, parent),
        previous_free_coordinates_m=(
            _free_coordinates(problem, previous) if previous is not None else None
        ),
        model_features=model_features,
    )
    try:
        proposal = policy.propose(policy_input)
    except Exception:
        return None, None, None, "policy_inference_failed"
    if type(proposal) is not FiberFrameWarmStartProposal:
        return None, None, None, "policy_output_type_invalid"
    if len(proposal.free_coordinates_m) != len(problem.free_global_dofs):
        return None, proposal.uncertainty, proposal.ood, "policy_output_shape_invalid"
    if proposal.ood:
        return None, proposal.uncertainty, proposal.ood, "policy_reported_ood"
    if proposal.uncertainty > benchmark_config.maximum_ai_uncertainty:
        return None, proposal.uncertainty, proposal.ood, "policy_uncertainty_rejected"
    return (
        proposal.free_coordinates_m,
        proposal.uncertainty,
        proposal.ood,
        "policy_prediction_available",
    )


def _verify_selected_path(
    model: CanonicalModel,
    compiled: Any,
    path: StatefulFiberFrame2DLoadPathResult,
) -> tuple[dict[str, Any], _EpisodeReplaySource | None]:
    if path.status != "ready" or not path.contract_pass:
        return (
            {
                "status": "blocked",
                "contract_pass": False,
                "reason_code": "selected_path_not_ready",
                "terminal_receipt_hash": None,
                "numerical_result_hash": None,
                "engineering_result_hash": None,
            },
            None,
        )
    problem = compiled.problem
    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps if step.committed),
    )
    try:
        chain = make_stateful_fiber_frame2d_checkpoint_chain(problem, checkpoints)
        plan = compile_stateful_fiber_frame2d_execution_topology(
            problem,
            model_ir_content_hash=model.canonical_model_checksum,
            node_ids=compiled.node_ids,
        )
        scaling = create_stateful_fiber_frame2d_physical_equation_scaling(problem, plan)
        kinematic = create_fiber_frame_nonlinear_kinematic_state_chain(
            problem,
            plan,
            chain,
        )
        material = create_fiber_frame_material_state_projection_chain(
            problem,
            chain,
            model_ir_content_hash=plan.model_ir_content_hash,
            execution_plan_hash=plan.plan_hash,
            solver_state_hashes=kinematic.solver_state_hashes,
        )
        binding = create_fiber_frame_nonlinear_execution_state_binding(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
        )
        terminal = create_fiber_frame_nonlinear_terminal_receipt(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
        )
        digest = model.canonical_model_checksum.removeprefix("sha256:")[:20]
        numerical_adapter = create_fiber_frame_nonlinear_numerical_result_adapter(
            problem,
            plan,
            scaling,
            chain,
            kinematic,
            material,
            binding,
            path,
            terminal,
            result_id=f"result.public_rc_fiber_frame.{digest}",
        )
        engineering = create_fiber_frame_nonlinear_engineering_result_ir(
            engineering_result_id=f"engineering.public_rc_fiber_frame.{digest}",
            source_adapter=numerical_adapter,
        )
    except (TypeError, ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        return (
            {
                "status": "blocked",
                "contract_pass": False,
                "reason_code": type(exc).__name__,
                "terminal_receipt_hash": None,
                "numerical_result_hash": None,
                "engineering_result_hash": None,
            },
            None,
        )
    return (
        {
            "status": "ready",
            "contract_pass": True,
            "reason_code": "full_j1_j5_recovery_passed",
            "checkpoint_chain_hash": chain.chain_hash,
            "terminal_receipt_hash": terminal.terminal_receipt_hash,
            "numerical_result_hash": numerical_adapter.numerical_result.result_hash,
            "engineering_result_hash": engineering.engineering_result_hash,
            "terminal_material_state_bundle_hash": (
                engineering.terminal_material_state_bundle_hash
            ),
            "free_residual_scaled_linf": engineering.free_residual_scaled_linf,
            "total_dissipated_energy_mj": engineering.total_dissipated_energy_mj,
        },
        _EpisodeReplaySource(
            problem=problem,
            plan=plan,
            scaling=scaling,
            chain=chain,
            kinematic=kinematic,
            material=material,
            binding=binding,
            path=path,
            terminal=terminal,
        ),
    )


def _verify_reference_solver_episode(
    source: _EpisodeReplaySource | None,
) -> dict[str, Any]:
    if source is None:
        return {
            "status": "blocked",
            "contract_pass": False,
            "reason_code": "reference_path_verification_unavailable",
            "solver_episode_adapter_hash": None,
            "solver_episode_hash": None,
        }
    try:
        adapter = create_fiber_frame_solver_episode_adapter(
            source.problem,
            source.plan,
            source.scaling,
            source.chain,
            source.kinematic,
            source.material,
            source.binding,
            source.path,
            terminal_receipt=source.terminal,
            episode_mode="baseline",
        )
    except (TypeError, ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        return {
            "status": "blocked",
            "contract_pass": False,
            "reason_code": type(exc).__name__,
            "solver_episode_adapter_hash": None,
            "solver_episode_hash": None,
        }
    return {
        "status": "ready",
        "contract_pass": True,
        "reason_code": "reference_baseline_solver_episode_replay_passed",
        "solver_episode_adapter_hash": adapter.adapter_hash,
        "solver_episode_hash": adapter.episode.episode_hash,
    }


def _path_comparison_snapshot(
    path: StatefulFiberFrame2DLoadPathResult,
) -> dict[str, Any]:
    """Detach exactly the checkpoint and trial fields used by path comparison.

    Canonical checkpoint bytes retain signed zero and every material-state bit.
    This transport snapshot is not an independently replayed solver authority.
    """

    checkpoints = (
        path.initial_checkpoint,
        *(step.accepted_checkpoint for step in path.steps if step.committed),
    )
    payload = {
        "schema_version": "public-rc-fiber-frame-path-comparison-snapshot.v1",
        "status": path.status,
        "contract_pass": path.contract_pass,
        "checkpoints": [
            {
                **checkpoint.to_dict(),
                "canonical_bytes_hex": checkpoint.canonical_bytes().hex(),
            }
            for checkpoint in checkpoints
        ],
        "trial_assemblies": [step.trial_assembly.to_dict() for step in path.steps],
    }
    payload["snapshot_hash"] = canonical_hash(payload)
    return deepcopy(payload)


def _comparison_json_value(value: Any, *, depth: int = 0) -> None:
    """Reject unbounded, non-JSON and non-finite transport values."""

    if depth > 32:
        raise FiberFrameRuntimeBenchmarkError(
            "comparison snapshot nesting exceeds limit"
        )
    if type(value) is dict:
        if len(value) > 100_000 or any(type(key) is not str for key in value):
            raise FiberFrameRuntimeBenchmarkError(
                "comparison snapshot object is invalid"
            )
        for child in value.values():
            _comparison_json_value(child, depth=depth + 1)
    elif type(value) is list:
        if len(value) > 100_000:
            raise FiberFrameRuntimeBenchmarkError(
                "comparison snapshot array exceeds limit"
            )
        for child in value:
            _comparison_json_value(child, depth=depth + 1)
    elif type(value) is str:
        if len(value) > 8 * 1024 * 1024:
            raise FiberFrameRuntimeBenchmarkError(
                "comparison snapshot string exceeds limit"
            )
    elif type(value) in (int, float):
        if not math.isfinite(value):
            raise FiberFrameRuntimeBenchmarkError(
                "comparison snapshot number is not finite"
            )
    elif value is not None and type(value) is not bool:
        raise FiberFrameRuntimeBenchmarkError("comparison snapshot value is not JSON")


def _validate_comparison_checkpoint(row: dict[str, Any]) -> None:
    # Reuse the checkpoint schema and existing typed canonical encoders.  No
    # problem is available here: source/model/replay authority remains separate.
    from dataclasses import fields

    from structural_analysis.assembly import (
        stateful_fiber_frame2d_checkpoint_io as codec,
    )
    from structural_analysis.assembly.stateful_fiber_frame2d_state import (
        StatefulFiberFrame2DCheckpoint,
    )
    from structural_analysis.elements.stateful_fiber_beam2d_state import (
        StatefulFiberBeam2DState,
    )
    from structural_analysis.materials.concrete_damage import ConcreteDamageState
    from structural_analysis.materials.stateful_fiber_section import (
        StatefulFiberSectionState,
    )
    from structural_analysis.materials.uniaxial_plasticity import (
        UniaxialPlasticityState,
    )

    if type(row) is not dict or type(row.get("canonical_bytes_hex")) is not str:
        raise FiberFrameRuntimeBenchmarkError("comparison checkpoint bytes are missing")
    payload = {key: value for key, value in row.items() if key != "canonical_bytes_hex"}
    raw = codec._artifact_json_bytes(payload)
    if len(raw) > codec.STATEFUL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES:
        raise FiberFrameRuntimeBenchmarkError(
            "comparison checkpoint exceeds byte limit"
        )
    codec._validate_schema(payload)
    classes = {
        "stateful-fiber-frame2d-checkpoint.v1": StatefulFiberFrame2DCheckpoint,
        "stateful-fiber-beam2d-state.v1": StatefulFiberBeam2DState,
        "stateful-rc-fiber-section-state.v1": StatefulFiberSectionState,
        "uniaxial-combined-hardening-state.v1": UniaxialPlasticityState,
        "uniaxial-asymmetric-concrete-damage-state.v1": ConcreteDamageState,
    }

    def restore(item: dict[str, Any]) -> Any:
        cls = classes[item["schema_version"]]
        values = {field.name: item[field.name] for field in fields(cls) if field.init}
        for key in ("element_states", "integration_point_states", "fiber_states"):
            if key in values:
                values[key] = tuple(restore(child) for child in values[key])
        for key in ("global_displacements", "local_displacements"):
            if key in values:
                values[key] = tuple(values[key])
        restored = cls(**values)
        codec._require_roundtrip(item, restored, path="comparison checkpoint")
        return restored

    restored = restore(payload)
    if restored.canonical_bytes().hex() != row["canonical_bytes_hex"]:
        raise FiberFrameRuntimeBenchmarkError(
            "comparison checkpoint canonical bytes disagree with fields"
        )


def _validate_path_comparison_snapshot(snapshot: Any) -> None:
    if type(snapshot) is not dict or set(snapshot) != {
        "schema_version",
        "status",
        "contract_pass",
        "checkpoints",
        "trial_assemblies",
        "snapshot_hash",
    }:
        raise FiberFrameRuntimeBenchmarkError("comparison snapshot fields are invalid")
    _comparison_json_value(snapshot)
    if (
        snapshot["schema_version"]
        != "public-rc-fiber-frame-path-comparison-snapshot.v1"
        or snapshot["status"] not in ("ready", "blocked")
        or type(snapshot["contract_pass"]) is not bool
        or type(snapshot["checkpoints"]) is not list
        or not 1 <= len(snapshot["checkpoints"]) <= 65
        or type(snapshot["trial_assemblies"]) is not list
        or not 0 <= len(snapshot["trial_assemblies"]) <= 64
        or any(type(row) is not dict for row in snapshot["trial_assemblies"])
    ):
        raise FiberFrameRuntimeBenchmarkError("comparison snapshot contract is invalid")
    if snapshot["snapshot_hash"] != canonical_hash(
        {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    ):
        raise FiberFrameRuntimeBenchmarkError("comparison snapshot hash does not match")
    for row in snapshot["checkpoints"]:
        _validate_comparison_checkpoint(row)


def _compare_paths(
    reference: StatefulFiberFrame2DLoadPathResult,
    candidate: StatefulFiberFrame2DLoadPathResult,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    return _compare_path_comparison_snapshots(
        _path_comparison_snapshot(reference),
        _path_comparison_snapshot(candidate),
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
    )


def _compare_path_comparison_snapshots(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    """Compare internally validated transport data using the legacy response rule.

    Rehashed contradictions are rejected; this is not source authentication or a
    substitute for the worker's full selected-path and reference-episode replay.
    """

    for tolerance in (absolute_tolerance, relative_tolerance):
        if (
            type(tolerance) not in (int, float)
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            raise FiberFrameRuntimeBenchmarkError("comparison tolerance is invalid")
    _validate_path_comparison_snapshot(reference)
    _validate_path_comparison_snapshot(candidate)
    reference_checkpoints = reference["checkpoints"]
    candidate_checkpoints = candidate["checkpoints"]
    schedule_match = tuple(
        (checkpoint["epoch"], checkpoint["load_factor"])
        for checkpoint in reference_checkpoints
    ) == tuple(
        (checkpoint["epoch"], checkpoint["load_factor"])
        for checkpoint in candidate_checkpoints
    )
    structure_match = len(reference_checkpoints) == len(candidate_checkpoints)
    exact_checkpoint_match = structure_match and all(
        left["canonical_bytes_hex"] == right["canonical_bytes_hex"]
        for left, right in zip(
            reference_checkpoints, candidate_checkpoints, strict=True
        )
    )
    displacement_max_abs = 0.0
    displacement_max_rel = 0.0
    material_max_abs = 0.0
    material_max_rel = 0.0
    material_structure_match = structure_match
    displacement_tolerance_match = structure_match
    material_tolerance_match = structure_match
    if structure_match:
        for left, right in zip(
            reference_checkpoints, candidate_checkpoints, strict=True
        ):
            left_displacement = np.asarray(
                left["global_displacements"], dtype=np.float64
            )
            right_displacement = np.asarray(
                right["global_displacements"], dtype=np.float64
            )
            abs_difference, rel_difference = _array_difference(
                left_displacement,
                right_displacement,
            )
            displacement_max_abs = max(displacement_max_abs, abs_difference)
            displacement_max_rel = max(displacement_max_rel, rel_difference)
            displacement_tolerance_match = bool(
                displacement_tolerance_match
                and np.allclose(
                    left_displacement,
                    right_displacement,
                    rtol=relative_tolerance,
                    atol=absolute_tolerance,
                )
            )
            (
                compatible,
                abs_difference,
                rel_difference,
                within_tolerance,
            ) = _numeric_payload_difference(
                left["element_states"],
                right["element_states"],
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            material_structure_match = material_structure_match and compatible
            material_tolerance_match = material_tolerance_match and within_tolerance
            material_max_abs = max(material_max_abs, abs_difference)
            material_max_rel = max(material_max_rel, rel_difference)
    trial_response_structure_match = len(reference["trial_assemblies"]) == len(
        candidate["trial_assemblies"]
    )
    trial_response_tolerance_match = trial_response_structure_match
    trial_response_max_abs = 0.0
    trial_response_max_rel = 0.0
    if trial_response_structure_match:
        for left_step, right_step in zip(
            reference["trial_assemblies"],
            candidate["trial_assemblies"],
            strict=True,
        ):
            (
                compatible,
                abs_difference,
                rel_difference,
                within_tolerance,
            ) = _numeric_payload_difference(
                left_step,
                right_step,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            trial_response_structure_match = (
                trial_response_structure_match and compatible
            )
            trial_response_tolerance_match = (
                trial_response_tolerance_match and within_tolerance
            )
            trial_response_max_abs = max(
                trial_response_max_abs,
                abs_difference,
            )
            trial_response_max_rel = max(
                trial_response_max_rel,
                rel_difference,
            )
    response_match = bool(
        reference["status"] == candidate["status"] == "ready"
        and reference["contract_pass"]
        and candidate["contract_pass"]
        and schedule_match
        and structure_match
        and material_structure_match
        and trial_response_structure_match
        and displacement_tolerance_match
        and material_tolerance_match
        and trial_response_tolerance_match
    )
    return {
        "same_object_identity_required": False,
        "load_schedule_match": schedule_match,
        "checkpoint_count_match": structure_match,
        "checkpoint_bytes_exact": exact_checkpoint_match,
        "displacement_max_abs_difference": displacement_max_abs,
        "displacement_max_relative_difference": displacement_max_rel,
        "displacement_within_elementwise_tolerance": (displacement_tolerance_match),
        "material_state_structure_match": material_structure_match,
        "material_state_max_abs_difference": material_max_abs,
        "material_state_max_relative_difference": material_max_rel,
        "material_state_within_elementwise_tolerance": material_tolerance_match,
        "trial_force_response_structure_match": trial_response_structure_match,
        "trial_force_response_max_abs_difference": trial_response_max_abs,
        "trial_force_response_max_relative_difference": trial_response_max_rel,
        "trial_force_response_within_elementwise_tolerance": (
            trial_response_tolerance_match
        ),
        "tolerance_rule": "abs_delta <= atol + rtol * max(abs(left), abs(right))",
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "full_history_response_match": response_match,
    }


def _numeric_payload_difference(
    left: Any,
    right: Any,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> tuple[bool, float, float, bool]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        left_keys = {key for key in left if not _is_identity_key(key)}
        right_keys = {key for key in right if not _is_identity_key(key)}
        if left_keys != right_keys:
            return False, math.inf, math.inf, False
        compatible = True
        within_tolerance = True
        max_abs = 0.0
        max_rel = 0.0
        for key in left_keys:
            (
                row_compatible,
                row_abs,
                row_rel,
                row_within_tolerance,
            ) = _numeric_payload_difference(
                left[key],
                right[key],
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            compatible = compatible and row_compatible
            within_tolerance = within_tolerance and row_within_tolerance
            max_abs = max(max_abs, row_abs)
            max_rel = max(max_rel, row_rel)
        return compatible, max_abs, max_rel, within_tolerance
    if isinstance(left, Sequence) and not isinstance(left, (str, bytes)):
        if not isinstance(right, Sequence) or isinstance(right, (str, bytes)):
            return False, math.inf, math.inf, False
        if len(left) != len(right):
            return False, math.inf, math.inf, False
        compatible = True
        within_tolerance = True
        max_abs = 0.0
        max_rel = 0.0
        for left_value, right_value in zip(left, right, strict=True):
            (
                row_compatible,
                row_abs,
                row_rel,
                row_within_tolerance,
            ) = _numeric_payload_difference(
                left_value,
                right_value,
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
            )
            compatible = compatible and row_compatible
            within_tolerance = within_tolerance and row_within_tolerance
            max_abs = max(max_abs, row_abs)
            max_rel = max(max_rel, row_rel)
        return compatible, max_abs, max_rel, within_tolerance
    if (
        isinstance(left, (int, float, np.integer, np.floating))
        and not isinstance(left, (bool, np.bool_))
        and isinstance(right, (int, float, np.integer, np.floating))
        and not isinstance(right, (bool, np.bool_))
    ):
        left_value = float(left)
        right_value = float(right)
        if not math.isfinite(left_value) or not math.isfinite(right_value):
            return False, math.inf, math.inf, False
        difference = abs(left_value - right_value)
        relative = difference / max(abs(left_value), abs(right_value), 1.0e-300)
        within_tolerance = difference <= absolute_tolerance + (
            relative_tolerance * max(abs(left_value), abs(right_value))
        )
        return True, difference, relative, within_tolerance
    equal = left == right
    return equal, 0.0, 0.0, equal


def _is_identity_key(value: Any) -> bool:
    key = str(value)
    return key.endswith("hash") or key.endswith("hashes")


def _array_difference(left: np.ndarray, right: np.ndarray) -> tuple[float, float]:
    if (
        left.shape != right.shape
        or not np.all(np.isfinite(left))
        or not np.all(np.isfinite(right))
    ):
        return math.inf, math.inf
    if left.size == 0:
        return 0.0, 0.0
    difference = np.abs(left - right)
    maximum = float(np.max(difference))
    relative = float(
        np.max(
            difference / np.maximum(np.maximum(np.abs(left), np.abs(right)), 1.0e-300)
        )
    )
    return maximum, relative


def _strategy_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    wall = [int(row["wall_ns"]) for row in rows]
    selected_solver_wall = [int(row["selected_solve_wall_ns"]) for row in rows]
    attempted_solver_wall = [int(row["attempted_solve_wall_ns"]) for row in rows]
    end_to_end = [int(row["verified_end_to_end_wall_ns"]) for row in rows]
    iterations = [int(row["newton_iteration_count"]) for row in rows]
    attempted_iterations = [
        int(row["attempted_newton_iteration_count"]) for row in rows
    ]
    attempted_line_search = [
        int(row["attempted_line_search_evaluation_count"]) for row in rows
    ]
    attempted_newton_total = [
        int(row["attempted_newton_runtime"]["total_wall_ns"]) for row in rows
    ]
    attempted_assembly = [
        int(row["attempted_newton_runtime"]["assemble_wall_ns"]) for row in rows
    ]
    attempted_linear_solve = [
        row["attempted_newton_runtime"]["linear_solve_wall_ns"] for row in rows
    ]
    attempted_stateful_total = [
        int(row["attempted_stateful_runtime"]["total_wall_ns"]) for row in rows
    ]
    attempted_terminal_assembly = [
        int(row["attempted_stateful_runtime"]["terminal_trial_assembly_wall_ns"])
        for row in rows
    ]
    material_rows = [_run_material_trial(row) for row in rows]
    material_total = _aggregate_material_trial(material_rows)
    attempted_residual_assembly_count = [
        int(row["attempted_newton_runtime"]["assemble_call_count"])
        + int(row["attempted_stateful_runtime"]["terminal_trial_assembly_call_count"])
        + int(row["guard_assembly_call_count"])
        for row in rows
    ]
    seeded_attempt_count = sum(
        int(step["seeded_attempt"] is not None) for row in rows for step in row["steps"]
    )
    baseline_recovery_count = sum(
        int(step["baseline_recovery"] is not None)
        for row in rows
        for step in row["steps"]
    )
    return {
        "run_count": len(rows),
        "ready_count": sum(int(row["contract_pass"]) for row in rows),
        "strategy_execution_wall_ns": _distribution(wall),
        "selected_solver_wall_ns": _distribution(selected_solver_wall),
        "attempted_solver_wall_ns": _distribution(attempted_solver_wall),
        "attempted_newton_total_wall_ns": _distribution(attempted_newton_total),
        "attempted_stateful_total_wall_ns": _distribution(attempted_stateful_total),
        "attempted_newton_assembly_wall_ns": _distribution(attempted_assembly),
        "attempted_linear_solve_wall_ns": (
            _distribution([int(value) for value in attempted_linear_solve])
            if all(value is not None for value in attempted_linear_solve)
            else _unmeasured_distribution("not_separately_instrumented")
        ),
        "attempted_terminal_trial_assembly_wall_ns": _distribution(
            attempted_terminal_assembly
        ),
        "attempted_material_trial_wall_ns": (
            _distribution([row["wall_ns"] for row in material_rows])
            if material_total["coverage_complete"]
            else _unmeasured_distribution("material_trial_coverage_incomplete")
        ),
        "material_trial": material_total,
        "material_trial_accounting_scope": MATERIAL_RUNTIME_ACCOUNTING_SCOPE,
        "attempted_residual_assembly_call_count": _distribution(
            attempted_residual_assembly_count
        ),
        "verified_end_to_end_wall_ns": _distribution(end_to_end),
        "newton_iteration_count": _distribution(iterations),
        "attempted_newton_iteration_count": _distribution(attempted_iterations),
        "attempted_line_search_evaluation_count": _distribution(attempted_line_search),
        "seeded_attempt_count": seeded_attempt_count,
        "baseline_recovery_count": baseline_recovery_count,
        "all_full_history_matches_reference": all(
            row["reference_comparison"]["full_history_response_match"] for row in rows
        ),
        "all_full_j1_j5_recovery_passed": all(
            row["authority_verification"]["contract_pass"] for row in rows
        ),
    }


def _distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "mean": None,
            "maximum": None,
            "population_standard_deviation": None,
            "coefficient_of_variation": None,
        }
    mean = fmean(values)
    deviation = pstdev(values)
    return {
        "count": len(values),
        "minimum": min(values),
        "median": median(values),
        "mean": mean,
        "maximum": max(values),
        "population_standard_deviation": deviation,
        "coefficient_of_variation": deviation / mean if mean > 0.0 else None,
    }


def _unmeasured_distribution(reason: str) -> dict[str, int | float | str | None]:
    return {
        "count": 0,
        "minimum": None,
        "median": None,
        "mean": None,
        "maximum": None,
        "population_standard_deviation": None,
        "coefficient_of_variation": None,
        "reason": reason,
    }


def _median_ratio(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> float | None:
    reference_median = reference.get("median")
    candidate_median = candidate.get("median")
    if (
        isinstance(reference_median, (int, float))
        and not isinstance(reference_median, bool)
        and isinstance(candidate_median, (int, float))
        and not isinstance(candidate_median, bool)
        and candidate_median > 0
    ):
        return float(reference_median) / float(candidate_median)
    return None


def _observed_comparison(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    timing_evidence_available: bool,
) -> dict[str, Any]:
    selected_ratio = (
        _median_ratio(
            reference["selected_solver_wall_ns"],
            candidate["selected_solver_wall_ns"],
        )
        if timing_evidence_available
        else None
    )
    execution_ratio = (
        _median_ratio(
            reference["strategy_execution_wall_ns"],
            candidate["strategy_execution_wall_ns"],
        )
        if timing_evidence_available
        else None
    )
    end_to_end_ratio = (
        _median_ratio(
            reference["verified_end_to_end_wall_ns"],
            candidate["verified_end_to_end_wall_ns"],
        )
        if timing_evidence_available
        else None
    )
    return {
        "timing_evidence_available": timing_evidence_available,
        "observed_reference_over_candidate_selected_solver_wall_ratio": (
            selected_ratio
        ),
        "observed_reference_over_candidate_execution_wall_ratio": execution_ratio,
        "observed_reference_over_candidate_verified_end_to_end_wall_ratio": (
            end_to_end_ratio
        ),
        "positive_local_selected_solver_difference_observed": bool(
            selected_ratio is not None and selected_ratio > 1.0
        ),
        "positive_local_verified_end_to_end_difference_observed": bool(
            end_to_end_ratio is not None and end_to_end_ratio > 1.0
        ),
        "generalized_speedup_confirmed": False,
        "performance_threshold_applied": False,
        "same_full_history_response": candidate["all_full_history_matches_reference"],
    }


def _aggregate_newton_runtime(attempts: Sequence[_Attempt]) -> dict[str, Any]:
    measured_fields = (
        "total_wall_ns",
        "assemble_wall_ns",
        "unattributed_wall_ns",
        "run_count",
        "completed_run_count",
        "exception_run_count",
        "assemble_call_count",
        "assemble_exception_count",
        "linear_solve_wall_ns",
        "linear_solve_call_count",
        "linear_solve_exception_count",
    )
    payload: dict[str, Any] = {
        name: sum(int(attempt.newton_runtime.get(name, 0)) for attempt in attempts)
        for name in measured_fields
    }
    payload.update(
        {
            "linear_solve_reason": "measured_increment_backend",
            "linear_solve_scope": VECTOR_INCREMENT_TIMING_SCOPE,
            "material_trial": _aggregate_material_trial(
                [attempt.newton_runtime.get("material_trial") for attempt in attempts]
            ),
        }
    )
    return payload


def _aggregate_stateful_runtime(attempts: Sequence[_Attempt]) -> dict[str, Any]:
    fields = (
        "total_wall_ns",
        "terminal_trial_assembly_wall_ns",
        "unattributed_wall_ns",
        "run_count",
        "completed_run_count",
        "exception_run_count",
        "terminal_trial_assembly_call_count",
        "terminal_trial_assembly_exception_count",
    )
    payload = {
        name: sum(int(attempt.stateful_runtime.get(name, 0)) for attempt in attempts)
        for name in fields
    }
    return {
        **payload,
        "terminal_material_trial": _aggregate_material_trial(
            [
                attempt.stateful_runtime.get("terminal_material_trial")
                for attempt in attempts
            ]
        ),
    }


def _aggregate_material_trial(rows: Sequence[Any]) -> dict[str, Any]:
    """Sum observed subsets, retaining missing/unsupported coverage as unavailable."""

    payload = MaterialTrialRuntimeRecorder().to_dict()
    totals = (
        "wall_ns",
        "call_count",
        "exception_count",
        "timing_error_count",
        "instrumented_section_call_count",
        "unmeasured_section_call_count",
    )
    material_fields = ("wall_ns", "call_count", "exception_count")
    reasons: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            reasons.add("material_trial_metadata_missing")
            continue
        materials = row.get("materials")
        valid = (
            row.get("schema_version") == payload["schema_version"]
            and row.get("scope") == MATERIAL_TRIAL_TIMING_SCOPE
            and type(row.get("coverage_complete")) is bool
            and isinstance(row.get("unavailable_reasons"), list)
            and all(isinstance(value, str) for value in row["unavailable_reasons"])
            and all(type(row.get(key)) is int and row[key] >= 0 for key in totals)
            and isinstance(materials, Mapping)
            and all(
                isinstance(materials.get(kind), Mapping)
                and all(
                    type(materials[kind].get(key)) is int and materials[kind][key] >= 0
                    for key in material_fields
                )
                for kind in ("steel", "concrete")
            )
        )
        if not valid or any(
            row[key] != sum(materials[kind][key] for kind in ("steel", "concrete"))
            for key in material_fields
        ):
            reasons.add("material_trial_metadata_invalid")
            continue
        for key in totals:
            payload[key] += row[key]
        for kind in ("steel", "concrete"):
            for key in material_fields:
                payload["materials"][kind][key] += materials[kind][key]
        reasons.update(row["unavailable_reasons"])
        if not row["coverage_complete"]:
            reasons.add("material_trial_coverage_incomplete")
        if row["unmeasured_section_call_count"]:
            reasons.add("section_material_trial_instrumentation_unavailable")
        if row["timing_error_count"]:
            reasons.add("material_trial_clock_invalid")
    payload["coverage_complete"] = not reasons
    payload["unavailable_reasons"] = sorted(reasons)
    return payload


def _run_material_trial(row: Mapping[str, Any]) -> dict[str, Any]:
    return _aggregate_material_trial(
        [
            row["attempted_newton_runtime"].get("material_trial"),
            row["attempted_stateful_runtime"].get("terminal_material_trial"),
            *(step.get("guard_material_trial") for step in row["steps"]),
        ]
    )


def _attempt_payload(attempt: _Attempt | None) -> dict[str, Any] | None:
    if attempt is None:
        return None
    if attempt.result is None:
        return {
            "status": "error",
            "committed": False,
            "step_hash": None,
            "solve_wall_ns": attempt.solve_wall_ns,
            "stateful_runtime": deepcopy(dict(attempt.stateful_runtime)),
            "newton_runtime": dict(attempt.newton_runtime),
            "parent_checkpoint_state_hash": (attempt.parent_checkpoint_state_hash),
            "initial_coordinates_hash": attempt.initial_coordinates_hash,
            "rollback_exact": None,
            "terminal_reason": None,
            "exception_type": attempt.exception_type,
            "convergence_iteration_count": None,
        }
    return {
        "status": attempt.result.status,
        "committed": attempt.result.committed,
        "step_hash": canonical_hash(attempt.result.to_dict()),
        "solve_wall_ns": attempt.solve_wall_ns,
        "stateful_runtime": deepcopy(dict(attempt.stateful_runtime)),
        "newton_runtime": dict(attempt.newton_runtime),
        "parent_checkpoint_state_hash": attempt.parent_checkpoint_state_hash,
        "initial_coordinates_hash": attempt.initial_coordinates_hash,
        "rollback_exact": attempt.result.metrics.get("rollback_exact"),
        "terminal_reason": attempt.result.metrics.get("terminal_reason"),
        "exception_type": attempt.exception_type,
        "convergence_iteration_count": len(
            attempt.result.trial_solution.convergence_history
        ),
        **(
            {
                "terminal_polishing": deepcopy(
                    attempt.result.trial_solution.metrics["terminal_polishing"]
                ),
                "linear_solve_count": attempt.result.trial_solution.metrics[
                    "linear_solve_count"
                ],
            }
            if "terminal_polishing" in attempt.result.trial_solution.metrics
            else {}
        ),
    }


def _rollback_exact(
    result: StatefulFiberFrame2DLoadStepResult | None,
    parent: Any,
    parent_bytes: bytes,
) -> bool:
    parent_unchanged = parent.canonical_bytes() == parent_bytes
    if result is None:
        return parent_unchanged
    return bool(
        not result.committed
        and result.accepted_checkpoint is parent
        and result.accepted_checkpoint.state_hash == parent.state_hash
        and result.accepted_checkpoint.canonical_bytes() == parent_bytes
        and parent_unchanged
        and result.metrics.get("rollback_exact") is True
    )


def _free_coordinates(
    problem: StatefulFiberFrame2DProblem, checkpoint: Any
) -> tuple[float, ...]:
    generalized = (
        np.asarray(
            checkpoint.global_displacements,
            dtype=np.float64,
        )
        / problem.physical_coordinate_scale
    )
    return tuple(float(generalized[dof]) for dof in problem.free_global_dofs)


def _relative_residual(
    problem: StatefulFiberFrame2DProblem, residual: np.ndarray
) -> float:
    return float(np.linalg.norm(np.asarray(residual), ord=np.inf)) / (
        problem.reference_force_scale()
    )


def _policy_identity(policy: FiberFrameWarmStartPolicy | None) -> dict[str, str]:
    if policy is None:
        raise FiberFrameRuntimeBenchmarkError("ai_policy is required")
    policy_id = str(getattr(policy, "policy_id", "")).strip()
    policy_version = str(getattr(policy, "policy_version", "")).strip()
    artifact_hash = str(getattr(policy, "artifact_hash", "")).strip()
    if not _STABLE_ID_PATTERN.fullmatch(policy_id):
        raise FiberFrameRuntimeBenchmarkError("policy_id is invalid")
    if not _STABLE_ID_PATTERN.fullmatch(policy_version):
        raise FiberFrameRuntimeBenchmarkError("policy_version is invalid")
    if not _HASH_PATTERN.fullmatch(artifact_hash):
        raise FiberFrameRuntimeBenchmarkError("policy artifact_hash is invalid")
    if not callable(getattr(policy, "propose", None)):
        raise FiberFrameRuntimeBenchmarkError("policy propose must be callable")
    return {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_artifact_hash": artifact_hash,
    }


def _solver_config_payload(config: NewtonRaphsonConfig) -> dict[str, Any]:
    return {
        "residual_tolerance": config.residual_tolerance,
        "increment_tolerance": config.increment_tolerance,
        "max_iterations": config.max_iterations,
        "matrix_backend": config.matrix_backend,
        "line_search_alphas": list(config.line_search_alphas),
        **(
            {
                "terminal_polishing": True,
                "terminal_polishing_profile": "newton-vector-terminal-polishing.v1",
            }
            if config.terminal_polishing
            else {}
        ),
    }


def _environment_payload(measurement_profile: str) -> dict[str, Any]:
    numpy_configuration = getattr(np.__config__, "CONFIG", None)
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "numpy_version": np.__version__,
        "numpy_build_configuration_hash": (
            canonical_hash(numpy_configuration)
            if isinstance(numpy_configuration, Mapping)
            else None
        ),
        "scipy_version": _installed_package_version("scipy"),
        "structural_analysis_package_version": _installed_package_version(
            "structural-analysis"
        ),
        "thread_runtime_configuration": None,
        "thread_runtime_configuration_reason": "not_captured",
        "clock": (
            "time.perf_counter_ns"
            if measurement_profile == FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE
            else "caller_injected_monotonic_ns"
        ),
    }


def _installed_package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def _rotated(values: list[str], offset: int) -> list[str]:
    if not values:
        return []
    pivot = offset % len(values)
    return [*values[pivot:], *values[:pivot]]


def _tick(clock_ns: Callable[[], int]) -> int:
    value = clock_ns()
    if isinstance(value, bool) or not isinstance(value, int):
        raise FiberFrameRuntimeBenchmarkError(
            "clock_ns must return an integer nanosecond value"
        )
    return value


def _elapsed(clock_ns: Callable[[], int], started_ns: int) -> int:
    finished_ns = _tick(clock_ns)
    if finished_ns < started_ns:
        raise FiberFrameRuntimeBenchmarkError("clock_ns must be monotonic")
    return finished_ns - started_ns


def _finite(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise FiberFrameRuntimeBenchmarkError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise FiberFrameRuntimeBenchmarkError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise FiberFrameRuntimeBenchmarkError(f"{name} must be finite")
    return normalized


def _optional_source_revision(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not (
        _HASH_PATTERN.fullmatch(normalized)
        or re.fullmatch(r"[0-9a-f]{40}", normalized)
        or re.fullmatch(r"[0-9a-f]{64}", normalized)
    ):
        raise FiberFrameRuntimeBenchmarkError(
            "source_revision must be a lowercase Git object ID or sha256 hash"
        )
    return normalized


def _only_value_or_none(values: set[str]) -> str | None:
    if len(values) != 1:
        return None
    return next(iter(values))


__all__ = [
    "FIBER_FRAME_AI_STRATEGY",
    "FIBER_FRAME_NON_AI_STRATEGY",
    "FIBER_FRAME_REFERENCE_STRATEGY",
    "FIBER_FRAME_RUNTIME_BENCHMARK_SCHEMA_VERSION",
    "FIBER_FRAME_RUNTIME_CLAIM_BOUNDARY",
    "FIBER_FRAME_RUNTIME_INJECTED_CLOCK_PROFILE",
    "FIBER_FRAME_RUNTIME_MEASUREMENT_PROFILE",
    "FiberFrameRuntimeBenchmarkConfig",
    "FiberFrameRuntimeBenchmarkError",
    "FiberFrameRuntimeBenchmarkResult",
    "FiberFrameWarmStartInput",
    "FiberFrameWarmStartPolicy",
    "FiberFrameWarmStartProposal",
    "benchmark_public_rc_fiber_frame_warm_starts",
]
