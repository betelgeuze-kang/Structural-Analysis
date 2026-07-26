"""Leakage-safe offline counterfactual dataset and shadow-policy scorecard.

The contracts in this module evaluate already-recorded shadow proposals against
independently replayed local interventions.  They never execute a proposal in a
product solve and never grant result, engineering, or guarded-execution
authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
import json
import math
import re
from typing import Any, Final, Literal, NoReturn

from jsonschema import Draft202012Validator

from structural_analysis.ai.fiber_frame_solver_episode_adapter import (
    FiberFrameSolverEpisodeAdapter,
    validate_fiber_frame_solver_episode_adapter_shape,
)
from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DProblem,
)
from structural_analysis.assembly.stateful_fiber_frame2d_solver import (
    StatefulFiberFrame2DLoadPathResult,
    solve_stateful_fiber_frame2d_load_step,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig


OFFLINE_COUNTERFACTUAL_DATASET_SCHEMA_VERSION = (
    "structural-analysis-offline-counterfactual-dataset.v1"
)
SHADOW_POLICY_SCORECARD_SCHEMA_VERSION = (
    "structural-analysis-shadow-policy-scorecard.v1"
)
COUNTERFACTUAL_OUTCOME_SCHEMA_VERSION = (
    "structural-analysis-counterfactual-transition-outcome.v1"
)
OFFLINE_COUNTERFACTUAL_PROFILE = "replay_bound_single_transition_evaluation_only.v1"
FIBER_FRAME_COUNTERFACTUAL_EVALUATOR_PROFILE = (
    "stateful-fiber-frame2d.single-transition-replay.v1"
)
OFFLINE_COUNTERFACTUAL_CLAIM_BOUNDARY = (
    "This artifact is an offline, evaluation-only comparison of non-executed "
    "shadow proposals with replayed local interventions. It is not a long-horizon "
    "causal claim, online policy qualification, guarded-execution approval, solver "
    "truth, engineering authority, or release evidence."
)

DatasetSplit = Literal["calibration", "validation", "holdout"]
OfflineSourceKind = Literal[
    "repository_generated_contract_fixture",
    "independent_replay_receipts",
]
_SPLITS: Final = ("calibration", "validation", "holdout")
_SOURCE_KINDS: Final = {
    "repository_generated_contract_fixture",
    "independent_replay_receipts",
}
_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_FEATURE_KEYS = {
    "observation_index",
    "load_factor",
    "residual_linf",
    "scaled_residual_l2",
    "increment_linf",
    "accepted",
    "rollback",
    "current_step_size",
    "baseline_next_step_size",
    "proposed_step_size",
    "residual_ratio",
    "uncertainty",
    "ood",
    "reason_code",
}


class OfflineCounterfactualError(ValueError):
    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class CounterfactualTransitionOutcome:
    transition_index: int
    transition_binding_hash: str
    parent_checkpoint_state_hash: str
    intervention_action_payload_hash: str
    proposed_step_size: float
    target_load_factor: float
    evaluator_profile: str
    replay_engine_artifact_hash: str
    evaluator_receipt_hash: str
    committed: bool
    rollback_exact: bool
    iteration_count: int
    final_relative_residual: float
    fallback_count: int
    regularization_count: int
    outcome_checkpoint_state_hash: str
    outcome_hash: str = _HASH_ZERO

    def __post_init__(self) -> None:
        _index(self.transition_index, "/transition_index")
        for name in (
            "transition_binding_hash",
            "parent_checkpoint_state_hash",
            "intervention_action_payload_hash",
            "replay_engine_artifact_hash",
            "outcome_checkpoint_state_hash",
        ):
            _hash(getattr(self, name), f"/{name}")
        _positive(self.proposed_step_size, "/proposed_step_size")
        _finite(self.target_load_factor, "/target_load_factor")
        _stable(self.evaluator_profile, "/evaluator_profile")
        if type(self.committed) is not bool or type(self.rollback_exact) is not bool:
            _fail(
                "counterfactual_outcome_disposition_invalid",
                "/committed",
                "Outcome dispositions must be exact booleans.",
            )
        if self.committed == self.rollback_exact:
            _fail(
                "counterfactual_outcome_disposition_invalid",
                "/committed",
                "An intervention must commit or roll back exactly, but not both.",
            )
        for name in ("iteration_count", "fallback_count", "regularization_count"):
            _index(getattr(self, name), f"/{name}")
        _nonnegative(self.final_relative_residual, "/final_relative_residual")
        if (
            self.rollback_exact
            and self.outcome_checkpoint_state_hash != self.parent_checkpoint_state_hash
        ):
            _fail(
                "counterfactual_rollback_state_mismatch",
                "/outcome_checkpoint_state_hash",
                "An exact rollback must preserve its parent checkpoint hash.",
            )
        expected_receipt = canonical_hash(self._evaluator_receipt_payload())
        if self.evaluator_receipt_hash == _HASH_ZERO:
            object.__setattr__(self, "evaluator_receipt_hash", expected_receipt)
        elif (
            _hash(self.evaluator_receipt_hash, "/evaluator_receipt_hash")
            != expected_receipt
        ):
            _fail(
                "counterfactual_evaluator_receipt_hash_mismatch",
                "/evaluator_receipt_hash",
                "Evaluator receipt hash does not bind the exact replay input and outcome.",
            )
        expected = canonical_hash(self._payload(include_hash=False))
        if self.outcome_hash == _HASH_ZERO:
            object.__setattr__(self, "outcome_hash", expected)
        elif _hash(self.outcome_hash, "/outcome_hash") != expected:
            _fail(
                "counterfactual_outcome_hash_mismatch",
                "/outcome_hash",
                "Outcome hash does not match canonical content.",
            )

    def _evaluator_receipt_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "structural-analysis-counterfactual-evaluator-receipt.v1",
            "transition_index": self.transition_index,
            "transition_binding_hash": self.transition_binding_hash,
            "parent_checkpoint_state_hash": self.parent_checkpoint_state_hash,
            "intervention_action_payload_hash": self.intervention_action_payload_hash,
            "proposed_step_size": self.proposed_step_size,
            "target_load_factor": self.target_load_factor,
            "evaluator_profile": self.evaluator_profile,
            "replay_engine_artifact_hash": self.replay_engine_artifact_hash,
            "committed": self.committed,
            "rollback_exact": self.rollback_exact,
            "iteration_count": self.iteration_count,
            "final_relative_residual": self.final_relative_residual,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "outcome_checkpoint_state_hash": self.outcome_checkpoint_state_hash,
        }

    def _payload(self, *, include_hash: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": COUNTERFACTUAL_OUTCOME_SCHEMA_VERSION,
            "transition_index": self.transition_index,
            "transition_binding_hash": self.transition_binding_hash,
            "parent_checkpoint_state_hash": self.parent_checkpoint_state_hash,
            "intervention_action_payload_hash": self.intervention_action_payload_hash,
            "proposed_step_size": self.proposed_step_size,
            "target_load_factor": self.target_load_factor,
            "evaluator_profile": self.evaluator_profile,
            "replay_engine_artifact_hash": self.replay_engine_artifact_hash,
            "evaluator_receipt_hash": self.evaluator_receipt_hash,
            "committed": self.committed,
            "rollback_exact": self.rollback_exact,
            "iteration_count": self.iteration_count,
            "final_relative_residual": self.final_relative_residual,
            "fallback_count": self.fallback_count,
            "regularization_count": self.regularization_count,
            "outcome_checkpoint_state_hash": self.outcome_checkpoint_state_hash,
        }
        if include_hash:
            payload["outcome_hash"] = self.outcome_hash
        return payload

    def to_dict(self) -> dict[str, Any]:
        return self._payload(include_hash=True)


@dataclass(frozen=True)
class OfflineCounterfactualSource:
    model_group_id: str
    split: DatasetSplit
    adapter: FiberFrameSolverEpisodeAdapter
    outcomes: tuple[CounterfactualTransitionOutcome, ...]

    def __post_init__(self) -> None:
        _stable(self.model_group_id, "/model_group_id")
        if self.split not in _SPLITS:
            _fail(
                "counterfactual_split_invalid",
                "/split",
                "Split must be calibration, validation, or holdout.",
            )
        if type(self.adapter) is not FiberFrameSolverEpisodeAdapter:
            _fail(
                "counterfactual_adapter_invalid",
                "/adapter",
                "Expected an exact FiberFrameSolverEpisodeAdapter.",
            )
        validate_fiber_frame_solver_episode_adapter_shape(self.adapter)
        if type(self.outcomes) is not tuple or any(
            type(row) is not CounterfactualTransitionOutcome for row in self.outcomes
        ):
            _fail(
                "counterfactual_outcomes_invalid",
                "/outcomes",
                "Outcomes must be an immutable tuple of exact outcome receipts.",
            )


@dataclass(frozen=True)
class OfflineCounterfactualDataset:
    _canonical_bytes: bytes

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical_bytes.decode("utf-8"))

    @property
    def dataset_hash(self) -> str:
        return str(self.to_dict()["dataset_hash"])


@dataclass(frozen=True)
class ShadowPolicyScorecard:
    _canonical_bytes: bytes

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical_bytes.decode("utf-8"))

    @property
    def scorecard_hash(self) -> str:
        return str(self.to_dict()["scorecard_hash"])


def replay_fiber_frame_counterfactual_transition(
    problem: StatefulFiberFrame2DProblem,
    load_path: StatefulFiberFrame2DLoadPathResult,
    adapter: FiberFrameSolverEpisodeAdapter,
    transition_index: int,
    *,
    config: NewtonRaphsonConfig | None = None,
) -> CounterfactualTransitionOutcome:
    """Replay one non-executed proposal from its exact source parent checkpoint."""

    if type(problem) is not StatefulFiberFrame2DProblem:
        _fail(
            "counterfactual_problem_invalid",
            "/problem",
            "Expected an exact StatefulFiberFrame2DProblem.",
        )
    if type(load_path) is not StatefulFiberFrame2DLoadPathResult:
        _fail(
            "counterfactual_load_path_invalid",
            "/load_path",
            "Expected an exact StatefulFiberFrame2DLoadPathResult.",
        )
    validate_fiber_frame_solver_episode_adapter_shape(adapter)
    index = _index(transition_index, "/transition_index")
    if index >= len(adapter.transition_bindings):
        _fail(
            "counterfactual_transition_index_invalid",
            "/transition_index",
            "Transition index is outside the source adapter.",
        )
    if problem.contract_hash != adapter.problem_contract_hash:
        _fail(
            "counterfactual_problem_binding_mismatch",
            "/problem/contract_hash",
            "Problem contract differs from the source adapter.",
        )
    transition = adapter.transition_bindings[index]
    source_position = transition.source_step_index - 1
    if source_position < 0 or source_position >= len(load_path.steps):
        _fail(
            "counterfactual_source_step_missing",
            "/load_path/steps",
            "The source load path does not contain the bound transition.",
        )
    source_step = load_path.steps[source_position]
    if (
        canonical_hash(source_step.to_dict()) != transition.source_step_replay_hash
        or source_step.parent_checkpoint.state_hash
        != transition.parent_checkpoint_state_hash
    ):
        _fail(
            "counterfactual_source_step_binding_mismatch",
            f"/load_path/steps/{source_position}",
            "The source step or parent checkpoint differs from the adapter binding.",
        )
    proposed_step = transition.shadow_proposed_step_size
    if proposed_step is None or transition.shadow_action_payload_hash is None:
        _fail(
            "counterfactual_shadow_binding_missing",
            f"/adapter/transitions/{index}",
            "The selected transition has no shadow intervention binding.",
        )
    if (
        transition.shadow_ood is not False
        or transition.shadow_disposition != "shadow_only"
    ):
        _fail(
            "counterfactual_shadow_proposal_ineligible",
            f"/adapter/transitions/{index}",
            "Rejected or OOD proposals cannot be replayed as policy evidence.",
        )
    if math.isclose(
        proposed_step,
        transition.baseline_step_size,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        _fail(
            "counterfactual_intervention_not_distinct",
            f"/adapter/transitions/{index}/shadow_proposed_step_size",
            "The proposal is numerically identical to the baseline action.",
        )
    selected_config = config or NewtonRaphsonConfig()
    config_payload = _newton_config_payload(selected_config)
    config_hash = canonical_hash(config_payload)
    if config_hash != adapter.solver_config_hash:
        _fail(
            "counterfactual_solver_config_mismatch",
            "/config",
            "Counterfactual replay must use the source episode's Newton configuration.",
        )
    target_load_factor = source_step.parent_checkpoint.load_factor + proposed_step
    replay = solve_stateful_fiber_frame2d_load_step(
        problem,
        source_step.parent_checkpoint,
        target_load_factor=target_load_factor,
        config=selected_config,
    )
    relative_residual = _nonnegative(
        replay.trial_solution.metrics.get("relative_residual"),
        "/replay/trial_solution/metrics/relative_residual",
    )
    rollback_exact = bool(
        not replay.committed and replay.metrics.get("rollback_exact") is True
    )
    replay_engine_hash = canonical_hash(
        {
            "profile": FIBER_FRAME_COUNTERFACTUAL_EVALUATOR_PROFILE,
            "problem_contract_hash": problem.contract_hash,
            "solver_config": config_payload,
            "solver_config_hash": config_hash,
            "source_backend_receipt_hash": adapter.backend_receipt_hash,
        }
    )
    return CounterfactualTransitionOutcome(
        transition_index=index,
        transition_binding_hash=transition.transition_binding_hash,
        parent_checkpoint_state_hash=transition.parent_checkpoint_state_hash,
        intervention_action_payload_hash=transition.shadow_action_payload_hash,
        proposed_step_size=proposed_step,
        target_load_factor=target_load_factor,
        evaluator_profile=FIBER_FRAME_COUNTERFACTUAL_EVALUATOR_PROFILE,
        replay_engine_artifact_hash=replay_engine_hash,
        evaluator_receipt_hash=_HASH_ZERO,
        committed=replay.committed,
        rollback_exact=rollback_exact,
        iteration_count=len(replay.trial_solution.convergence_history),
        final_relative_residual=relative_residual,
        fallback_count=int(bool(replay.trial_solution.metrics.get("fallback_used"))),
        regularization_count=int(
            bool(replay.trial_solution.metrics.get("regularization_used"))
        ),
        outcome_checkpoint_state_hash=replay.accepted_checkpoint.state_hash,
    )


def build_offline_counterfactual_dataset(
    sources: Sequence[OfflineCounterfactualSource],
    *,
    source_kind: OfflineSourceKind = "repository_generated_contract_fixture",
) -> OfflineCounterfactualDataset:
    if source_kind not in _SOURCE_KINDS:
        _fail(
            "counterfactual_source_kind_invalid",
            "/source_kind",
            "Unsupported offline replay source kind.",
        )
    if isinstance(sources, (str, bytes, bytearray)) or not isinstance(
        sources, Sequence
    ):
        _fail(
            "counterfactual_sources_invalid",
            "/sources",
            "Sources must be a non-string sequence.",
        )
    normalized = tuple(sources)
    if not normalized:
        _fail(
            "counterfactual_sources_empty",
            "/sources",
            "At least one source is required.",
        )
    if any(type(source) is not OfflineCounterfactualSource for source in normalized):
        _fail(
            "counterfactual_sources_invalid",
            "/sources",
            "Every source must use the exact source contract.",
        )
    normalized = tuple(
        sorted(
            normalized, key=lambda row: (_SPLITS.index(row.split), row.model_group_id)
        )
    )

    model_split: dict[str, str] = {}
    group_split: dict[str, str] = {}
    state_split: dict[str, str] = {}
    episode_hashes: set[str] = set()
    policy_identity: tuple[str, str, str] | None = None
    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    eligible_total = 0
    evaluated_total = 0
    rejected_total = 0
    ood_total = 0
    identical_action_total = 0
    executed_ai_action_count = 0

    for source_index, source in enumerate(normalized):
        adapter = source.adapter
        episode = adapter.episode
        source_eligible_before = eligible_total
        if episode.episode_mode != "shadow":
            _fail(
                "counterfactual_source_not_shadow",
                f"/sources/{source_index}/adapter/episode_mode",
                "Offline policy rows require a shadow episode.",
            )
        if (
            episode.data_use.training_eligible
            or not episode.data_use.evaluation_only
            or episode.data_use.raw_customer_payload_included
        ):
            _fail(
                "counterfactual_source_data_use_invalid",
                f"/sources/{source_index}/adapter/data_use",
                "The v1 dataset accepts evaluation-only sources without raw customer payloads.",
            )
        if episode.episode_hash in episode_hashes:
            _fail(
                "counterfactual_episode_duplicate",
                f"/sources/{source_index}",
                "One source episode may appear only once.",
            )
        episode_hashes.add(episode.episode_hash)
        prior_split = model_split.setdefault(
            episode.model_ir_content_hash, source.split
        )
        if prior_split != source.split:
            _fail(
                "counterfactual_model_split_leakage",
                f"/sources/{source_index}/split",
                "One model lineage may not cross dataset splits.",
            )
        prior_group_split = group_split.setdefault(source.model_group_id, source.split)
        if prior_group_split != source.split:
            _fail(
                "counterfactual_group_split_leakage",
                f"/sources/{source_index}/split",
                "One model group may not cross dataset splits.",
            )
        if any(action.source == "ai_proposal" for action in episode.executed_actions):
            _fail(
                "counterfactual_source_ai_action_executed",
                f"/sources/{source_index}/adapter/executed_actions",
                "Shadow source episodes may execute baseline actions only.",
            )
        executed_ai_action_count += sum(
            int(action.source == "ai_proposal") for action in episode.executed_actions
        )
        outcomes = {row.transition_index: row for row in source.outcomes}
        if len(outcomes) != len(source.outcomes):
            _fail(
                "counterfactual_outcome_duplicate",
                f"/sources/{source_index}/outcomes",
                "Each transition may have at most one intervention outcome.",
            )

        evaluated_indices: set[int] = set()
        source_policy_hashes: set[str] = set()
        for transition in adapter.transition_bindings:
            if transition.shadow_policy_artifact_hash is None:
                _fail(
                    "counterfactual_shadow_binding_missing",
                    f"/sources/{source_index}/transitions/{transition.transition_index}",
                    "Every shadow transition requires a proposal binding.",
                )
            source_policy_hashes.add(transition.shadow_policy_artifact_hash)
            disposition = str(transition.shadow_disposition)
            ood = bool(transition.shadow_ood)
            if ood:
                ood_total += 1
            if disposition == "rejected":
                rejected_total += 1
                if transition.transition_index in outcomes:
                    _fail(
                        "counterfactual_rejected_proposal_evaluated",
                        f"/sources/{source_index}/outcomes",
                        "Rejected/OOD proposals are excluded from intervention evaluation.",
                    )
                continue
            if disposition != "shadow_only" or ood:
                _fail(
                    "counterfactual_shadow_disposition_invalid",
                    f"/sources/{source_index}/transitions/{transition.transition_index}",
                    "Evaluated proposals must be non-OOD and shadow_only.",
                )
            if transition.shadow_proposed_step_size is None:
                _fail(
                    "counterfactual_shadow_step_missing",
                    f"/sources/{source_index}/transitions/{transition.transition_index}",
                    "An eligible shadow proposal must bind a proposed step size.",
                )
            if math.isclose(
                float(transition.shadow_proposed_step_size),
                float(transition.baseline_step_size),
                rel_tol=0.0,
                abs_tol=1.0e-15,
            ):
                identical_action_total += 1
                if transition.transition_index in outcomes:
                    _fail(
                        "counterfactual_identical_action_evaluated",
                        f"/sources/{source_index}/outcomes",
                        "A numerically identical baseline action is not a counterfactual intervention.",
                    )
                continue
            eligible_total += 1
            outcome = outcomes.get(transition.transition_index)
            if outcome is not None:
                evaluated_indices.add(transition.transition_index)
                evaluated_total += 1
                _validate_outcome_binding(
                    outcome, transition, source_index=source_index
                )
            observation = episode.observations[transition.from_observation_index]
            prior_state_split = state_split.setdefault(
                observation.state_hash,
                source.split,
            )
            if prior_state_split != source.split:
                _fail(
                    "counterfactual_state_split_leakage",
                    f"/sources/{source_index}/transitions/{transition.transition_index}",
                    "One pre-action state may not cross dataset splits.",
                )
            next_observation = episode.observations[transition.to_observation_index]
            baseline_iterations = next_observation.iteration - observation.iteration
            baseline_step = float(transition.baseline_step_size)
            proposed_step = float(transition.shadow_proposed_step_size)
            baseline_density = baseline_iterations / baseline_step
            comparison: dict[str, Any] | None = None
            if outcome is not None:
                counterfactual_density = outcome.iteration_count / proposed_step
                non_regression = bool(
                    outcome.committed
                    and outcome.fallback_count == 0
                    and outcome.regularization_count == 0
                    and (
                        counterfactual_density <= baseline_density
                        or math.isclose(
                            counterfactual_density,
                            baseline_density,
                            rel_tol=1.0e-12,
                            abs_tol=1.0e-12,
                        )
                    )
                )
                comparison = {
                    "baseline_iterations_per_load_increment": baseline_density,
                    "counterfactual_iterations_per_load_increment": counterfactual_density,
                    "iteration_density_advantage": (
                        baseline_density - counterfactual_density
                    ),
                    "counterfactual_safe": bool(
                        outcome.committed
                        and outcome.fallback_count == 0
                        and outcome.regularization_count == 0
                    ),
                    "local_non_regression": non_regression,
                }
            feature = {
                "observation_index": observation.observation_index,
                "load_factor": observation.load_factor,
                "residual_linf": observation.residual_linf,
                "scaled_residual_l2": observation.scaled_residual_l2,
                "increment_linf": observation.increment_linf,
                "accepted": observation.accepted,
                "rollback": observation.rollback,
                "current_step_size": transition.shadow_current_step_size,
                "baseline_next_step_size": transition.shadow_baseline_next_step_size,
                "proposed_step_size": transition.shadow_proposed_step_size,
                "residual_ratio": transition.shadow_residual_ratio,
                "uncertainty": transition.shadow_uncertainty,
                "ood": transition.shadow_ood,
                "reason_code": transition.shadow_reason_code,
            }
            if set(feature) != _FEATURE_KEYS:
                raise AssertionError("offline feature schema drift")
            row_body = {
                "row_id": (
                    f"cf.{source.split}.{source.model_group_id}."
                    f"{transition.transition_index}"
                ),
                "split": source.split,
                "model_group_id": source.model_group_id,
                "lineage": {
                    "adapter_hash": adapter.adapter_hash,
                    "episode_hash": episode.episode_hash,
                    "model_ir_content_hash": episode.model_ir_content_hash,
                    "execution_plan_hash": episode.execution_plan_hash,
                    "problem_contract_hash": adapter.problem_contract_hash,
                    "transition_binding_hash": transition.transition_binding_hash,
                    "source_step_replay_hash": transition.source_step_replay_hash,
                    "parent_checkpoint_state_hash": transition.parent_checkpoint_state_hash,
                    "observation_state_hash": observation.state_hash,
                    "baseline_action_payload_hash": transition.baseline_action_payload_hash,
                    "proposal_action_payload_hash": transition.shadow_action_payload_hash,
                    "policy_artifact_hash": transition.shadow_policy_artifact_hash,
                    "counterfactual_outcome_hash": (
                        None if outcome is None else outcome.outcome_hash
                    ),
                    "evaluator_receipt_hash": (
                        None if outcome is None else outcome.evaluator_receipt_hash
                    ),
                },
                "features": feature,
                "labels": {
                    "baseline": {
                        "target_load_factor": transition.target_load_factor,
                        "step_size": baseline_step,
                        "committed": transition.committed,
                        "rollback_exact": transition.rollback_exact,
                        "iteration_count": baseline_iterations,
                        "final_scaled_residual_linf": next_observation.residual_linf,
                        "outcome_checkpoint_state_hash": transition.outcome_checkpoint_state_hash,
                    },
                    "counterfactual": (None if outcome is None else outcome.to_dict()),
                    "comparison": comparison,
                },
            }
            row_body["row_hash"] = canonical_hash(row_body)
            rows.append(row_body)
        if set(outcomes) != evaluated_indices:
            _fail(
                "counterfactual_outcome_unbound",
                f"/sources/{source_index}/outcomes",
                "Every supplied outcome must bind one eligible transition.",
            )
        if len(source_policy_hashes) != 1:
            _fail(
                "counterfactual_source_policy_mixed",
                f"/sources/{source_index}/adapter",
                "One source episode must use one locked policy artifact.",
            )
        proposal = episode.proposals[0]
        identity = (
            proposal.policy_id,
            proposal.policy_version,
            next(iter(source_policy_hashes)),
        )
        if policy_identity is None:
            policy_identity = identity
        elif policy_identity != identity:
            _fail(
                "counterfactual_policy_split_leakage",
                f"/sources/{source_index}/adapter",
                "All splits must evaluate the same pre-locked policy artifact.",
            )
        source_rows.append(
            {
                "model_group_id": source.model_group_id,
                "split": source.split,
                "adapter_hash": adapter.adapter_hash,
                "episode_hash": episode.episode_hash,
                "model_ir_content_hash": episode.model_ir_content_hash,
                "problem_contract_hash": adapter.problem_contract_hash,
                "eligible_row_count": eligible_total - source_eligible_before,
                "evaluated_row_count": len(evaluated_indices),
                "training_eligible": False,
                "evaluation_only": True,
                "raw_customer_payload_included": False,
                "ai_action_executed": False,
            }
        )

    assert policy_identity is not None
    present_splits = {source.split for source in normalized}
    if present_splits != set(_SPLITS):
        _fail(
            "counterfactual_split_coverage_invalid",
            "/sources",
            "Calibration, validation, and holdout model groups are all required.",
        )
    row_ids = [str(row["row_id"]) for row in rows]
    if len(row_ids) != len(set(row_ids)):
        _fail(
            "counterfactual_row_duplicate",
            "/rows",
            "Counterfactual row identifiers must be unique.",
        )
    split_counts = {
        split: sum(int(row["split"] == split) for row in rows) for split in _SPLITS
    }
    lineage_root_hash = canonical_hash(
        {
            "sources": source_rows,
            "outcome_hashes": sorted(
                row["lineage"]["counterfactual_outcome_hash"]
                for row in rows
                if row["lineage"]["counterfactual_outcome_hash"] is not None
            ),
        }
    )
    body: dict[str, Any] = {
        "schema_version": OFFLINE_COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
        "profile": OFFLINE_COUNTERFACTUAL_PROFILE,
        "source_kind": source_kind,
        "authority": "offline_evaluation_only",
        "policy": {
            "policy_id": policy_identity[0],
            "policy_version": policy_identity[1],
            "policy_artifact_hash": policy_identity[2],
            "locked_before_holdout": True,
        },
        "data_use": {
            "training_eligible": False,
            "evaluation_only": True,
            "raw_customer_payload_included": False,
        },
        "split_profile": "explicit_model_group_partition.v1",
        "split_counts": split_counts,
        "source_count": len(source_rows),
        "eligible_proposal_count": eligible_total,
        "evaluated_counterfactual_count": evaluated_total,
        "missing_counterfactual_count": eligible_total - evaluated_total,
        "rejected_proposal_count": rejected_total,
        "ood_proposal_count": ood_total,
        "identical_action_proposal_count": identical_action_total,
        "executed_ai_action_count": executed_ai_action_count,
        "feature_columns": sorted(_FEATURE_KEYS),
        "label_columns": ["baseline", "counterfactual", "comparison"],
        "leakage_checks": {
            "model_group_id_split_exclusive": True,
            "model_group_split_exclusive": True,
            "physical_problem_split_exclusive": True,
            "pre_action_state_split_exclusive": True,
            "source_episode_unique": True,
            "row_id_unique": True,
            "policy_locked_across_splits": True,
            "feature_schema_exact": True,
            "future_outcomes_excluded_from_features": True,
            "evaluation_only_sources": True,
            "raw_customer_payload_absent": True,
            "lineage_complete": True,
        },
        "lineage_root_hash": lineage_root_hash,
        "sources": source_rows,
        "rows": rows,
        "ai_action_executed": False,
        "result_authority": False,
        "guarded_execution_eligible": False,
        "empirical_performance_claim": False,
        "claim_boundary": OFFLINE_COUNTERFACTUAL_CLAIM_BOUNDARY,
    }
    body["dataset_hash"] = canonical_hash(body)
    validated = validate_offline_counterfactual_dataset(body)
    return OfflineCounterfactualDataset(_canonical_json_bytes(validated))


def build_shadow_policy_scorecard(
    dataset: OfflineCounterfactualDataset | Mapping[str, Any],
    *,
    minimum_evaluated_rows: int = 6,
    minimum_local_non_regression_rate: float = 0.8,
    minimum_holdout_non_regression_rate: float = 0.8,
) -> ShadowPolicyScorecard:
    payload = validate_offline_counterfactual_dataset(
        dataset.to_dict()
        if isinstance(dataset, OfflineCounterfactualDataset)
        else dataset
    )
    _index(minimum_evaluated_rows, "/thresholds/minimum_evaluated_rows")
    if minimum_evaluated_rows < 1:
        _fail(
            "scorecard_threshold_invalid",
            "/thresholds/minimum_evaluated_rows",
            "At least one evaluated row is required.",
        )
    for name, value in (
        ("minimum_local_non_regression_rate", minimum_local_non_regression_rate),
        ("minimum_holdout_non_regression_rate", minimum_holdout_non_regression_rate),
    ):
        normalized = _finite(value, f"/thresholds/{name}")
        if not 0.0 <= normalized <= 1.0:
            _fail(
                "scorecard_threshold_invalid",
                f"/thresholds/{name}",
                "Rate thresholds must be in [0, 1].",
            )
    rows = payload["rows"]
    evaluated_rows = [
        row for row in rows if row["labels"]["counterfactual"] is not None
    ]
    evaluated = len(evaluated_rows)
    eligible = int(payload["eligible_proposal_count"])
    non_regression_count = sum(
        int(row["labels"]["comparison"]["local_non_regression"])
        for row in evaluated_rows
    )
    safe_count = sum(
        int(row["labels"]["comparison"]["counterfactual_safe"])
        for row in evaluated_rows
    )
    holdout_eligible = [row for row in rows if row["split"] == "holdout"]
    holdout = [
        row for row in holdout_eligible if row["labels"]["counterfactual"] is not None
    ]
    holdout_non_regression_count = sum(
        int(row["labels"]["comparison"]["local_non_regression"]) for row in holdout
    )
    fallback_count = sum(
        int(row["labels"]["counterfactual"]["fallback_count"]) for row in evaluated_rows
    )
    regularization_count = sum(
        int(row["labels"]["counterfactual"]["regularization_count"])
        for row in evaluated_rows
    )
    coverage = evaluated / eligible if eligible else 0.0
    non_regression_rate = non_regression_count / evaluated if evaluated else 0.0
    holdout_rate = holdout_non_regression_count / len(holdout) if holdout else 0.0
    safety_rate = safe_count / evaluated if evaluated else 0.0
    advantages = sorted(
        float(row["labels"]["comparison"]["iteration_density_advantage"])
        for row in evaluated_rows
    )
    median_advantage = (
        advantages[len(advantages) // 2]
        if len(advantages) % 2 == 1
        else (advantages[len(advantages) // 2 - 1] + advantages[len(advantages) // 2])
        / 2.0
        if advantages
        else 0.0
    )
    gates = {
        "dataset_integrity_pass": True,
        "leakage_checks_pass": all(payload["leakage_checks"].values()),
        "policy_locked_before_holdout": payload["policy"]["locked_before_holdout"]
        is True,
        "counterfactual_coverage_pass": coverage == 1.0,
        "holdout_coverage_pass": bool(holdout_eligible)
        and len(holdout) == len(holdout_eligible),
        "minimum_rows_pass": evaluated >= minimum_evaluated_rows,
        "local_non_regression_pass": non_regression_rate
        >= minimum_local_non_regression_rate,
        "holdout_non_regression_pass": bool(holdout)
        and holdout_rate >= minimum_holdout_non_regression_rate,
        "fallback_free_pass": fallback_count == 0,
        "regularization_free_pass": regularization_count == 0,
        "shadow_execution_isolation_pass": payload["executed_ai_action_count"] == 0,
        "raw_customer_payload_absent": payload["data_use"][
            "raw_customer_payload_included"
        ]
        is False,
    }
    gates_passed = all(gates.values())
    # v1 has no signed independent-source attestation contract.  A caller-set
    # provenance label must therefore never promote a policy gate.
    policy_gate_passed = False
    body: dict[str, Any] = {
        "schema_version": SHADOW_POLICY_SCORECARD_SCHEMA_VERSION,
        "status": (
            "contract_fixture_pass"
            if gates_passed
            and payload["source_kind"] == "repository_generated_contract_fixture"
            else "blocked"
        ),
        "contract_pass": True,
        "policy_gate_pass": policy_gate_passed,
        "source_kind": payload["source_kind"],
        "dataset_hash": payload["dataset_hash"],
        "lineage_root_hash": payload["lineage_root_hash"],
        "policy": payload["policy"],
        "thresholds": {
            "minimum_evaluated_rows": minimum_evaluated_rows,
            "minimum_counterfactual_coverage": 1.0,
            "minimum_local_non_regression_rate": minimum_local_non_regression_rate,
            "minimum_holdout_non_regression_rate": minimum_holdout_non_regression_rate,
            "maximum_fallback_count": 0,
            "maximum_regularization_count": 0,
            "maximum_executed_ai_action_count": 0,
        },
        "metrics": {
            "eligible_proposal_count": eligible,
            "evaluated_counterfactual_count": evaluated,
            "counterfactual_coverage": coverage,
            "counterfactual_safe_count": safe_count,
            "counterfactual_safety_rate": safety_rate,
            "local_non_regression_count": non_regression_count,
            "local_non_regression_rate": non_regression_rate,
            "holdout_row_count": len(holdout),
            "holdout_eligible_row_count": len(holdout_eligible),
            "holdout_non_regression_count": holdout_non_regression_count,
            "holdout_non_regression_rate": holdout_rate,
            "median_iteration_density_advantage": median_advantage,
            "fallback_count": fallback_count,
            "regularization_count": regularization_count,
            "executed_ai_action_count": payload["executed_ai_action_count"],
            "ood_proposal_count": payload["ood_proposal_count"],
            "rejected_proposal_count": payload["rejected_proposal_count"],
            "identical_action_proposal_count": payload[
                "identical_action_proposal_count"
            ],
        },
        "gates": gates,
        "recommendation": "retain_shadow_only",
        "ai_action_executed": False,
        "result_authority": False,
        "guarded_execution_eligible": False,
        "empirical_performance_claim": False,
        "claim_boundary": OFFLINE_COUNTERFACTUAL_CLAIM_BOUNDARY,
    }
    body["scorecard_hash"] = canonical_hash(body)
    validated = validate_shadow_policy_scorecard(body)
    return ShadowPolicyScorecard(_canonical_json_bytes(validated))


def validate_offline_counterfactual_dataset(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalized_mapping(payload, "/")
    _validate_schema(
        normalized,
        "offline_counterfactual_dataset_v1.schema.json",
        "/",
    )
    claimed = str(normalized["dataset_hash"])
    body = {key: value for key, value in normalized.items() if key != "dataset_hash"}
    if claimed != canonical_hash(body):
        _fail(
            "counterfactual_dataset_hash_mismatch",
            "/dataset_hash",
            "Dataset hash does not match canonical content.",
        )
    if set(normalized["feature_columns"]) != _FEATURE_KEYS:
        _fail(
            "counterfactual_feature_schema_invalid",
            "/feature_columns",
            "Feature columns differ from the leakage-safe v1 schema.",
        )
    row_ids: set[str] = set()
    model_splits: dict[str, str] = {}
    problem_splits: dict[str, str] = {}
    group_splits: dict[str, str] = {}
    state_splits: dict[str, str] = {}
    episode_hashes: set[str] = set()
    source_by_group: dict[str, dict[str, Any]] = {}
    for source_index, source in enumerate(normalized["sources"]):
        model_hash = str(source["model_ir_content_hash"])
        split = str(source["split"])
        if model_hash in model_splits and model_splits[model_hash] != split:
            _fail(
                "counterfactual_model_split_leakage",
                f"/sources/{source_index}/split",
                "One model lineage appears in multiple splits.",
            )
        model_splits[model_hash] = split
        problem_hash = str(source["problem_contract_hash"])
        if problem_hash in problem_splits and problem_splits[problem_hash] != split:
            _fail(
                "counterfactual_problem_split_leakage",
                f"/sources/{source_index}/split",
                "One physical problem contract appears in multiple splits.",
            )
        problem_splits[problem_hash] = split
        group_id = str(source["model_group_id"])
        if group_id in source_by_group:
            _fail(
                "counterfactual_group_duplicate",
                f"/sources/{source_index}/model_group_id",
                "Each model group must have exactly one source episode.",
            )
        source_by_group[group_id] = source
        if group_id in group_splits and group_splits[group_id] != split:
            _fail(
                "counterfactual_group_split_leakage",
                f"/sources/{source_index}/split",
                "One model group appears in multiple splits.",
            )
        group_splits[group_id] = split
        episode_hash = str(source["episode_hash"])
        if episode_hash in episode_hashes:
            _fail(
                "counterfactual_episode_duplicate",
                f"/sources/{source_index}/episode_hash",
                "One episode appears more than once.",
            )
        episode_hashes.add(episode_hash)
    if int(normalized["source_count"]) != len(normalized["sources"]) or set(
        group_splits.values()
    ) != set(_SPLITS):
        _fail(
            "counterfactual_source_coverage_mismatch",
            "/source_count",
            "Source count or calibration/validation/holdout coverage is inconsistent.",
        )
    for index, row in enumerate(normalized["rows"]):
        row_id = str(row["row_id"])
        if row_id in row_ids:
            _fail(
                "counterfactual_row_duplicate",
                f"/rows/{index}/row_id",
                "Row identifiers must be unique.",
            )
        row_ids.add(row_id)
        group_id = str(row["model_group_id"])
        source = source_by_group.get(group_id)
        if source is None:
            _fail(
                "counterfactual_row_source_missing",
                f"/rows/{index}/model_group_id",
                "Every row must bind one declared model-group source.",
            )
        state_hash = str(row["lineage"]["observation_state_hash"])
        split = str(row["split"])
        if (
            split != source["split"]
            or row["lineage"]["adapter_hash"] != source["adapter_hash"]
            or row["lineage"]["episode_hash"] != source["episode_hash"]
            or row["lineage"]["model_ir_content_hash"]
            != source["model_ir_content_hash"]
            or row["lineage"]["problem_contract_hash"]
            != source["problem_contract_hash"]
            or row["lineage"]["policy_artifact_hash"]
            != normalized["policy"]["policy_artifact_hash"]
        ):
            _fail(
                "counterfactual_row_source_binding_mismatch",
                f"/rows/{index}/lineage",
                "Row split, source lineage, or locked policy binding is inconsistent.",
            )
        if state_hash in state_splits and state_splits[state_hash] != split:
            _fail(
                "counterfactual_state_split_leakage",
                f"/rows/{index}/split",
                "One pre-action state appears in multiple splits.",
            )
        state_splits[state_hash] = split
        if set(row["features"]) != _FEATURE_KEYS:
            _fail(
                "counterfactual_feature_schema_invalid",
                f"/rows/{index}/features",
                "Feature rows contain missing, future, label, or unknown fields.",
            )
        expected_row_hash = canonical_hash(
            {key: value for key, value in row.items() if key != "row_hash"}
        )
        if row["row_hash"] != expected_row_hash:
            _fail(
                "counterfactual_row_hash_mismatch",
                f"/rows/{index}/row_hash",
                "Row hash does not match canonical content.",
            )
        outcome = row["labels"]["counterfactual"]
        comparison = row["labels"]["comparison"]
        lineage = row["lineage"]
        if outcome is None:
            if comparison is not None or any(
                lineage[key] is not None
                for key in (
                    "counterfactual_outcome_hash",
                    "evaluator_receipt_hash",
                )
            ):
                _fail(
                    "counterfactual_missing_outcome_lineage_invalid",
                    f"/rows/{index}/labels",
                    "Missing outcomes require null comparison and evaluator lineage.",
                )
            continue
        if comparison is None:
            _fail(
                "counterfactual_comparison_missing",
                f"/rows/{index}/labels/comparison",
                "Evaluated outcomes require a comparison label.",
            )
        evaluator_body = {
            key: value
            for key, value in outcome.items()
            if key not in {"evaluator_receipt_hash", "outcome_hash", "schema_version"}
        }
        evaluator_body["schema_version"] = (
            "structural-analysis-counterfactual-evaluator-receipt.v1"
        )
        if outcome["evaluator_receipt_hash"] != canonical_hash(evaluator_body):
            _fail(
                "counterfactual_evaluator_receipt_hash_mismatch",
                f"/rows/{index}/labels/counterfactual/evaluator_receipt_hash",
                "Evaluator receipt hash does not bind the exact replay input and outcome.",
            )
        expected_outcome_hash = canonical_hash(
            {key: value for key, value in outcome.items() if key != "outcome_hash"}
        )
        if outcome["outcome_hash"] != expected_outcome_hash:
            _fail(
                "counterfactual_outcome_hash_mismatch",
                f"/rows/{index}/labels/counterfactual/outcome_hash",
                "Outcome hash does not match canonical content.",
            )
        if (
            lineage["counterfactual_outcome_hash"] != outcome["outcome_hash"]
            or lineage["evaluator_receipt_hash"] != outcome["evaluator_receipt_hash"]
            or lineage["transition_binding_hash"] != outcome["transition_binding_hash"]
            or lineage["proposal_action_payload_hash"]
            != outcome["intervention_action_payload_hash"]
            or lineage["parent_checkpoint_state_hash"]
            != outcome["parent_checkpoint_state_hash"]
            or row["features"]["proposed_step_size"] != outcome["proposed_step_size"]
        ):
            _fail(
                "counterfactual_row_lineage_mismatch",
                f"/rows/{index}/lineage",
                "Feature/label lineage does not bind the exact intervention.",
            )
        baseline = row["labels"]["baseline"]
        parent_load_factor = baseline["target_load_factor"] - baseline["step_size"]
        expected_target = parent_load_factor + outcome["proposed_step_size"]
        committed = outcome["committed"] is True
        rollback_exact = outcome["rollback_exact"] is True
        if (
            not _number_equal(outcome["target_load_factor"], expected_target)
            or committed == rollback_exact
            or (
                rollback_exact
                and outcome["outcome_checkpoint_state_hash"]
                != outcome["parent_checkpoint_state_hash"]
            )
        ):
            _fail(
                "counterfactual_outcome_semantics_invalid",
                f"/rows/{index}/labels/counterfactual",
                "Outcome target, disposition, or exact rollback semantics are invalid.",
            )
        baseline_density = baseline["iteration_count"] / baseline["step_size"]
        counterfactual_density = (
            outcome["iteration_count"] / outcome["proposed_step_size"]
        )
        counterfactual_safe = bool(
            committed
            and outcome["fallback_count"] == 0
            and outcome["regularization_count"] == 0
        )
        local_non_regression = bool(
            counterfactual_safe
            and (
                counterfactual_density <= baseline_density
                or _number_equal(counterfactual_density, baseline_density)
            )
        )
        if (
            not _number_equal(
                comparison["baseline_iterations_per_load_increment"],
                baseline_density,
            )
            or not _number_equal(
                comparison["counterfactual_iterations_per_load_increment"],
                counterfactual_density,
            )
            or not _number_equal(
                comparison["iteration_density_advantage"],
                baseline_density - counterfactual_density,
            )
            or comparison["counterfactual_safe"] is not counterfactual_safe
            or comparison["local_non_regression"] is not local_non_regression
        ):
            _fail(
                "counterfactual_comparison_mismatch",
                f"/rows/{index}/labels/comparison",
                "Comparison labels differ from their bound baseline and replay outcome.",
            )
    evaluated_count = sum(
        int(row["labels"]["counterfactual"] is not None) for row in normalized["rows"]
    )
    eligible_count = int(normalized["eligible_proposal_count"])
    if (
        int(normalized["evaluated_counterfactual_count"]) != evaluated_count
        or int(normalized["missing_counterfactual_count"])
        != eligible_count - evaluated_count
        or eligible_count != len(normalized["rows"])
    ):
        _fail(
            "counterfactual_count_mismatch",
            "/evaluated_counterfactual_count",
            "Eligible, evaluated, missing, and retained row counts disagree.",
        )
    expected_split_counts = {
        split: sum(int(row["split"] == split) for row in normalized["rows"])
        for split in _SPLITS
    }
    if normalized["split_counts"] != expected_split_counts:
        _fail(
            "counterfactual_split_count_mismatch",
            "/split_counts",
            "Split counts differ from retained eligible rows.",
        )
    for source_index, source in enumerate(normalized["sources"]):
        group_id = source["model_group_id"]
        group_rows = [
            row for row in normalized["rows"] if row["model_group_id"] == group_id
        ]
        group_evaluated = sum(
            int(row["labels"]["counterfactual"] is not None) for row in group_rows
        )
        if (
            source["eligible_row_count"] != len(group_rows)
            or source["evaluated_row_count"] != group_evaluated
        ):
            _fail(
                "counterfactual_source_count_mismatch",
                f"/sources/{source_index}",
                "Source eligible/evaluated counts differ from bound rows.",
            )
    expected_lineage_root = canonical_hash(
        {
            "sources": normalized["sources"],
            "outcome_hashes": sorted(
                row["lineage"]["counterfactual_outcome_hash"]
                for row in normalized["rows"]
                if row["lineage"]["counterfactual_outcome_hash"] is not None
            ),
        }
    )
    if normalized["lineage_root_hash"] != expected_lineage_root:
        _fail(
            "counterfactual_lineage_root_mismatch",
            "/lineage_root_hash",
            "Lineage root does not bind source rows and replay outcome hashes.",
        )
    if not all(normalized["leakage_checks"].values()):
        _fail(
            "counterfactual_leakage_gate_blocked",
            "/leakage_checks",
            "All leakage and lineage checks must pass.",
        )
    if (
        normalized["ai_action_executed"] is not False
        or normalized["result_authority"] is not False
        or normalized["guarded_execution_eligible"] is not False
        or normalized["empirical_performance_claim"] is not False
    ):
        _fail(
            "counterfactual_authority_promotion_forbidden",
            "/guarded_execution_eligible",
            "Offline data cannot grant execution or result authority.",
        )
    return normalized


def validate_shadow_policy_scorecard(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalized_mapping(payload, "/")
    _validate_schema(normalized, "shadow_policy_scorecard_v1.schema.json", "/")
    claimed = str(normalized["scorecard_hash"])
    body = {key: value for key, value in normalized.items() if key != "scorecard_hash"}
    if claimed != canonical_hash(body):
        _fail(
            "shadow_scorecard_hash_mismatch",
            "/scorecard_hash",
            "Scorecard hash does not match canonical content.",
        )
    metrics = normalized["metrics"]
    thresholds = normalized["thresholds"]
    eligible = metrics["eligible_proposal_count"]
    evaluated = metrics["evaluated_counterfactual_count"]
    safe_count = metrics["counterfactual_safe_count"]
    non_regression_count = metrics["local_non_regression_count"]
    holdout_rows = metrics["holdout_row_count"]
    holdout_eligible = metrics["holdout_eligible_row_count"]
    holdout_non_regression = metrics["holdout_non_regression_count"]
    expected_coverage = evaluated / eligible if eligible else 0.0
    expected_safety_rate = safe_count / evaluated if evaluated else 0.0
    expected_non_regression_rate = (
        non_regression_count / evaluated if evaluated else 0.0
    )
    expected_holdout_rate = (
        holdout_non_regression / holdout_rows if holdout_rows else 0.0
    )
    if (
        evaluated > eligible
        or safe_count > evaluated
        or non_regression_count > evaluated
        or holdout_rows > holdout_eligible
        or holdout_non_regression > holdout_rows
        or not _number_equal(metrics["counterfactual_coverage"], expected_coverage)
        or not _number_equal(
            metrics["counterfactual_safety_rate"], expected_safety_rate
        )
        or not _number_equal(
            metrics["local_non_regression_rate"],
            expected_non_regression_rate,
        )
        or not _number_equal(
            metrics["holdout_non_regression_rate"],
            expected_holdout_rate,
        )
    ):
        _fail(
            "shadow_scorecard_metric_mismatch",
            "/metrics",
            "Scorecard counts and derived rates are internally inconsistent.",
        )
    expected_metric_gates = {
        "counterfactual_coverage_pass": expected_coverage
        >= thresholds["minimum_counterfactual_coverage"],
        "holdout_coverage_pass": bool(holdout_eligible)
        and holdout_rows == holdout_eligible,
        "minimum_rows_pass": evaluated >= thresholds["minimum_evaluated_rows"],
        "local_non_regression_pass": expected_non_regression_rate
        >= thresholds["minimum_local_non_regression_rate"],
        "holdout_non_regression_pass": bool(holdout_rows)
        and expected_holdout_rate >= thresholds["minimum_holdout_non_regression_rate"],
        "fallback_free_pass": metrics["fallback_count"]
        <= thresholds["maximum_fallback_count"],
        "regularization_free_pass": metrics["regularization_count"]
        <= thresholds["maximum_regularization_count"],
        "shadow_execution_isolation_pass": metrics["executed_ai_action_count"]
        <= thresholds["maximum_executed_ai_action_count"],
    }
    for gate, expected in expected_metric_gates.items():
        if normalized["gates"][gate] is not expected:
            _fail(
                "shadow_scorecard_gate_mismatch",
                f"/gates/{gate}",
                "Scorecard gate differs from its metric and threshold.",
            )
    gates_passed = all(normalized["gates"].values())
    policy_gate_passed = False
    expected_status = (
        "contract_fixture_pass"
        if gates_passed
        and normalized["source_kind"] == "repository_generated_contract_fixture"
        else "blocked"
    )
    if (
        normalized["contract_pass"] is not True
        or normalized["policy_gate_pass"] is not policy_gate_passed
        or normalized["status"] != expected_status
    ):
        _fail(
            "shadow_scorecard_status_mismatch",
            "/status",
            "Scorecard status differs from its explicit gates.",
        )
    if (
        normalized["recommendation"] != "retain_shadow_only"
        or normalized["ai_action_executed"] is not False
        or normalized["result_authority"] is not False
        or normalized["guarded_execution_eligible"] is not False
        or normalized["empirical_performance_claim"] is not False
    ):
        _fail(
            "shadow_scorecard_authority_promotion_forbidden",
            "/guarded_execution_eligible",
            "An offline scorecard cannot authorize AI execution or result truth.",
        )
    return normalized


def _validate_outcome_binding(
    outcome: CounterfactualTransitionOutcome,
    transition: Any,
    *,
    source_index: int,
) -> None:
    path = f"/sources/{source_index}/outcomes/{transition.transition_index}"
    expected = {
        "transition_index": transition.transition_index,
        "transition_binding_hash": transition.transition_binding_hash,
        "parent_checkpoint_state_hash": transition.parent_checkpoint_state_hash,
        "intervention_action_payload_hash": transition.shadow_action_payload_hash,
        "proposed_step_size": transition.shadow_proposed_step_size,
    }
    for name, value in expected.items():
        if getattr(outcome, name) != value:
            _fail(
                "counterfactual_outcome_binding_mismatch",
                f"{path}/{name}",
                "Outcome is not bound to the exact shadow transition proposal.",
            )
    parent_load_factor = transition.target_load_factor - transition.baseline_step_size
    expected_target = parent_load_factor + transition.shadow_proposed_step_size
    if not math.isclose(
        outcome.target_load_factor,
        expected_target,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        _fail(
            "counterfactual_target_load_mismatch",
            f"{path}/target_load_factor",
            "Intervention target does not equal parent load plus proposed step.",
        )


def _validate_schema(payload: Mapping[str, Any], name: str, path: str) -> None:
    resource = resources.files("structural_analysis").joinpath("schemas").joinpath(name)
    try:
        schema = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail(
            "offline_schema_unavailable",
            path,
            "The packaged offline-evaluation schema is unavailable.",
        )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(dict(payload)),
        key=lambda row: list(row.absolute_path),
    )
    if errors:
        first = errors[0]
        suffix = "/".join(str(value) for value in first.absolute_path)
        _fail(
            "offline_schema_invalid",
            "/" + suffix if suffix else path,
            first.message,
        )


def _normalized_mapping(payload: Mapping[str, Any], path: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        _fail("offline_manifest_invalid", path, "Expected a JSON object.")
    try:
        value = json.loads(_canonical_json_bytes(dict(payload)).decode("utf-8"))
    except (TypeError, ValueError, OverflowError):
        _fail(
            "offline_manifest_json_invalid",
            path,
            "Manifest must contain finite JSON values.",
        )
    if type(value) is not dict:
        _fail("offline_manifest_invalid", path, "Expected a JSON object.")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _newton_config_payload(config: NewtonRaphsonConfig) -> dict[str, Any]:
    return {
        "residual_tolerance": config.residual_tolerance,
        "increment_tolerance": config.increment_tolerance,
        "max_iterations": config.max_iterations,
        "line_search_alphas": list(config.line_search_alphas),
        "matrix_backend": config.matrix_backend,
    }


def _number_equal(left: Any, right: Any) -> bool:
    return math.isclose(
        _finite(left, "/number/left"),
        _finite(right, "/number/right"),
        rel_tol=1.0e-12,
        abs_tol=1.0e-12,
    )


def _stable(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID.fullmatch(value) is None:
        _fail("offline_stable_id_invalid", path, "Expected a stable ASCII identifier.")
    return value


def _hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail("offline_hash_invalid", path, "Expected sha256:<64 lowercase hex>.")
    return value


def _index(value: Any, path: str) -> int:
    if type(value) is not int or not 0 <= value <= 2**31 - 1:
        _fail("offline_index_invalid", path, "Expected a bounded non-negative integer.")
    return value


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail("offline_number_invalid", path, "Expected a finite number.")
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail("offline_number_invalid", path, "Expected a finite number.")
    return normalized


def _nonnegative(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized < 0.0:
        _fail("offline_nonnegative_invalid", path, "Expected a non-negative number.")
    return normalized


def _positive(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized <= 0.0:
        _fail("offline_positive_invalid", path, "Expected a positive number.")
    return normalized


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise OfflineCounterfactualError(code, path, detail)


__all__ = [
    "COUNTERFACTUAL_OUTCOME_SCHEMA_VERSION",
    "FIBER_FRAME_COUNTERFACTUAL_EVALUATOR_PROFILE",
    "OFFLINE_COUNTERFACTUAL_CLAIM_BOUNDARY",
    "OFFLINE_COUNTERFACTUAL_DATASET_SCHEMA_VERSION",
    "OFFLINE_COUNTERFACTUAL_PROFILE",
    "SHADOW_POLICY_SCORECARD_SCHEMA_VERSION",
    "CounterfactualTransitionOutcome",
    "DatasetSplit",
    "OfflineSourceKind",
    "OfflineCounterfactualDataset",
    "OfflineCounterfactualError",
    "OfflineCounterfactualSource",
    "ShadowPolicyScorecard",
    "build_offline_counterfactual_dataset",
    "build_shadow_policy_scorecard",
    "replay_fiber_frame_counterfactual_transition",
    "validate_offline_counterfactual_dataset",
    "validate_shadow_policy_scorecard",
]
