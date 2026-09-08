"""Collect research warm-start targets from complete public physical solves.

Declared dataset identities are checked for overlap. They are not independent
project, licensing, external-validation, or model-family provenance evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
import json
import re
from time import perf_counter_ns
from typing import Any

import numpy as np

from structural_analysis.ai.fiber_frame_warm_start_learning import (
    FiberFrameWarmStartLearningError,
    FiberFrameWarmStartSample,
    WarmStartDatasetSplit,
    validate_fiber_frame_warm_start_dataset,
)
from structural_analysis.ai.fiber_frame_physical_identity import (
    PHYSICAL_MODEL_IDENTITY_PROFILE,
    fiber_frame_physical_model_identity,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.benchmark.fiber_frame_runtime import FiberFrameWarmStartInput
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class FiberFrameWarmStartDataError(ValueError):
    """Invalid collection request before physical execution."""


@dataclass(frozen=True, init=False)
class FiberFrameWarmStartDataCase:
    case_id: str
    project_id: str
    geometry_family_id: str
    load_history_id: str
    split: WarmStartDatasetSplit
    config: public_api.PublicRCFiberFrameConfig
    _model_json: str = field(repr=False)

    def __init__(
        self,
        case_id: str,
        project_id: str,
        geometry_family_id: str,
        load_history_id: str,
        split: WarmStartDatasetSplit,
        model: CanonicalModel,
        config: public_api.PublicRCFiberFrameConfig,
    ) -> None:
        for name, value in (
            ("case_id", case_id),
            ("project_id", project_id),
            ("geometry_family_id", geometry_family_id),
            ("load_history_id", load_history_id),
        ):
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise FiberFrameWarmStartDataError(f"{name}: stable identity required")
            object.__setattr__(self, name, value)
        if split not in ("train", "validation", "holdout"):
            raise FiberFrameWarmStartDataError("split: unsupported dataset split")
        if (
            type(model) is not CanonicalModel
            or type(config) is not public_api.PublicRCFiberFrameConfig
        ):
            raise FiberFrameWarmStartDataError(
                "case: exact model and config types required"
            )
        if not isinstance(model.input_checksum, str) or not _HASH.fullmatch(
            model.input_checksum
        ):
            raise FiberFrameWarmStartDataError("case: source input checksum required")
        try:
            snapshot = model.detached_analysis_snapshot()
            # Validate finite JSON before storing an immutable private snapshot.
            model_json = json.dumps(
                snapshot.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            config_snapshot = public_api.PublicRCFiberFrameConfig(**asdict(config))
        except (TypeError, ValueError, OverflowError) as exc:
            raise FiberFrameWarmStartDataError(
                "case: finite JSON model snapshot required"
            ) from exc
        object.__setattr__(self, "split", split)
        object.__setattr__(self, "config", config_snapshot)
        object.__setattr__(self, "_model_json", model_json)

    @property
    def model(self) -> CanonicalModel:
        """Return a fresh model; neither caller mutation nor access changes the case."""
        payload = json.loads(self._model_json)
        payload.pop("canonical_model_checksum")
        payload["units"] = UnitSystem(**payload["units"])
        coordinates = payload["coordinate_system"]
        payload["coordinate_system"] = CoordinateSystem(
            axis_order=tuple(coordinates["axis_order"]), up_axis=coordinates["up_axis"]
        )
        return CanonicalModel(**payload)


@dataclass(frozen=True)
class FiberFrameWarmStartDataResult:
    status: str
    samples: tuple[FiberFrameWarmStartSample, ...]
    _report_json: str = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._report_json)


def _physical_model_identity(model: CanonicalModel) -> str:
    return fiber_frame_physical_model_identity(model)


def _preflight_physical_splits(
    cases: tuple[FiberFrameWarmStartDataCase, ...],
) -> dict[str, str | None]:
    """Reject declared-group or supported-model leakage before producing labels."""

    identities: dict[str, str | None] = {}
    owners: dict[tuple[str, str], str] = {}
    for case in cases:
        keys = [
            (name, getattr(case, name))
            for name in ("project_id", "geometry_family_id", "load_history_id")
        ]
        try:
            identity = _physical_model_identity(case.model)
        except ValueError:
            # An unsupported case still receives the public producer's own
            # diagnostics below, but can never contribute an accepted target.
            identity = None
        identities[case.case_id] = identity
        if identity is not None:
            keys.append(("model_identity_hash", identity))
        for key in keys:
            if key in owners and owners[key] != case.split:
                raise FiberFrameWarmStartDataError(f"split_leakage: {key[0]}")
            owners[key] = case.split
    return identities


def _free_coordinates(problem: Any, checkpoint: Any) -> tuple[float, ...]:
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        coordinates = (
            np.asarray(checkpoint.global_displacements, dtype=np.float64)
            / problem.physical_coordinate_scale
        )
    return tuple(float(coordinates[dof]) for dof in problem.free_global_dofs)


def _case_samples(
    case: FiberFrameWarmStartDataCase,
    result: public_api.PublicRCFiberFrameResult,
    model_identity: str,
    source_revision: str,
) -> tuple[tuple[FiberFrameWarmStartSample, ...], list[dict[str, Any]]]:
    problem, chain = result._problem, result._checkpoint_chain
    if problem is None or chain is None:
        raise FiberFrameWarmStartDataError("accepted result has no checkpoint ancestry")
    if len(chain.checkpoints) != case.config.load_steps + 1:
        raise FiberFrameWarmStartDataError(
            "accepted result has incomplete checkpoint ancestry"
        )
    if (
        result.contract_bindings.get("checkpoint_chain_hash") != chain.chain_hash
        or result.contract_bindings.get("problem_contract_hash")
        != problem.contract_hash
    ):
        raise FiberFrameWarmStartDataError("accepted result source bindings mismatch")
    checkpoints = chain.checkpoints
    samples: list[FiberFrameWarmStartSample] = []
    bindings: list[dict[str, Any]] = []
    for epoch in range(1, len(checkpoints)):
        parent, target = checkpoints[epoch - 1], checkpoints[epoch]
        previous = checkpoints[epoch - 2] if epoch >= 2 else None
        if (
            target.epoch != epoch
            or target.load_factor != case.config.target_load_factors[epoch - 1]
        ):
            raise FiberFrameWarmStartDataError(
                "accepted target does not match configured load path"
            )
        runtime_input = FiberFrameWarmStartInput(
            problem_contract_hash=problem.contract_hash,
            parent_checkpoint_state_hash=parent.state_hash,
            previous_checkpoint_state_hash=previous.state_hash
            if previous is not None
            else None,
            parent_load_factor=parent.load_factor,
            previous_load_factor=previous.load_factor if previous is not None else None,
            target_load_factor=target.load_factor,
            free_global_dofs=problem.free_global_dofs,
            physical_coordinate_scale=tuple(
                float(problem.physical_coordinate_scale[dof])
                for dof in problem.free_global_dofs
            ),
            parent_free_coordinates_m=_free_coordinates(problem, parent),
            previous_free_coordinates_m=_free_coordinates(problem, previous)
            if previous is not None
            else None,
        )
        sample_id = "sample-" + canonical_hash(
            {"case_id": case.case_id, "epoch": epoch}
        ).removeprefix("sha256:")
        sample = FiberFrameWarmStartSample(
            sample_id=sample_id,
            project_id=case.project_id,
            geometry_family_id=case.geometry_family_id,
            load_history_id=case.load_history_id,
            model_identity_hash=model_identity,
            physical_problem_identity_hash=problem.contract_hash,
            split=case.split,
            runtime_input=runtime_input,
            accepted_target_free_coordinates_m=_free_coordinates(problem, target),
        )
        binding = {
            "sample_id": sample.sample_id,
            "sample_hash": sample.sample_hash,
            "case_id": case.case_id,
            "source_revision": source_revision,
            "canonical_model_checksum": result.canonical_model_checksum,
            "input_checksum": result.input_checksum,
            "physical_model_identity_hash": model_identity,
            "physical_model_identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
            "public_result_hash": result.result_hash,
            "checkpoint_chain_hash": chain.chain_hash,
            "target_checkpoint_state_hash": target.state_hash,
            "target_epoch": epoch,
            "parent_checkpoint_state_hash": parent.state_hash,
            "previous_checkpoint_state_hash": previous.state_hash
            if previous is not None
            else None,
            "solver_target_source": "accepted_checkpoint_from_complete_public_j1_j5_recovery",
            "independent_external_target_verification": False,
        }
        bindings.append({**binding, "binding_hash": canonical_hash(binding)})
        samples.append(sample)
    return tuple(samples), bindings


def collect_fiber_frame_warm_start_data(
    cases: Sequence[FiberFrameWarmStartDataCase],
    *,
    source_revision: str,
) -> FiberFrameWarmStartDataResult:
    """Execute each detached case and retain only complete, validated targets."""
    if not isinstance(source_revision, str) or not _REVISION.fullmatch(source_revision):
        raise FiberFrameWarmStartDataError(
            "source_revision: full lowercase Git SHA required"
        )
    cases = tuple(cases)
    if not cases or any(
        type(case) is not FiberFrameWarmStartDataCase for case in cases
    ):
        raise FiberFrameWarmStartDataError(
            "cases: nonempty data-case sequence required"
        )
    if len({case.case_id for case in cases}) != len(cases):
        raise FiberFrameWarmStartDataError("cases: duplicate case_id")
    started = perf_counter_ns()
    identities = _preflight_physical_splits(cases)
    samples: list[FiberFrameWarmStartSample] = []
    rows: list[dict[str, Any]] = []
    sample_bindings: list[dict[str, Any]] = []
    for case in cases:
        case_started = perf_counter_ns()
        model = case.model
        physical_identity = identities[case.case_id]
        row: dict[str, Any] = {
            "case_id": case.case_id,
            "project_id": case.project_id,
            "geometry_family_id": case.geometry_family_id,
            "load_history_id": case.load_history_id,
            "split": case.split,
            "canonical_model_checksum": model.canonical_model_checksum,
            "input_checksum": model.input_checksum,
            "physical_model_identity_hash": physical_identity,
            "physical_model_identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
            "configuration": asdict(case.config),
            "status": "blocked",
            "sample_count": 0,
            "public_result_hash": None,
            "checkpoint_chain_hash": None,
            "solver_executed": None,
            "blockers": [],
        }
        try:
            result = public_api.analyze_public_rc_fiber_frame(model, case.config)
            validation = public_api.validate_public_rc_fiber_frame_result(result)
            expected_configuration = {
                "load_steps": case.config.load_steps,
                "target_load_factors": list(case.config.target_load_factors),
                "scaled_residual_tolerance": case.config.residual_tolerance,
                "solver_coordinate_increment_tolerance_m": case.config.increment_tolerance_m,
                "maximum_iterations": case.config.maximum_iterations,
                "matrix_backend": "numpy_dense_ndarray",
                "restart_supplied": False,
                "restart_checkpoint_artifact_hash": None,
            }
            if (
                result.canonical_model_checksum != model.canonical_model_checksum
                or result.input_checksum != model.input_checksum
                or dict(result.configuration) != expected_configuration
                or result.solver_id != public_api.PUBLIC_RC_FIBER_FRAME_SOLVER_ID
                or result.compiler_profile
                != public_api.PUBLIC_RC_FIBER_FRAME_COMPILER_PROFILE
            ):
                raise FiberFrameWarmStartDataError(
                    "public result does not bind the requested source and configuration"
                )
            row.update(
                {
                    "public_result_hash": result.result_hash,
                    "checkpoint_chain_hash": result.contract_bindings.get(
                        "checkpoint_chain_hash"
                    ),
                    "solver_executed": result.metrics.get("solver_executed"),
                    "validation_report": validation.to_dict(),
                }
            )
            if (
                result.status != "ready"
                or not result.contract_pass
                or not validation.contract_pass
            ):
                row["blockers"] = [
                    str(item.get("kind", "public_result_blocked"))
                    for item in result.unsupported_features
                ] or ["public_result_blocked"]
            else:
                if physical_identity is None:
                    raise FiberFrameWarmStartDataError(
                        "accepted target requires a supported physical model identity"
                    )
                case_samples, case_bindings = _case_samples(
                    case, result, physical_identity, source_revision
                )
                samples.extend(case_samples)
                sample_bindings.extend(case_bindings)
                row.update(status="ready", sample_count=len(case_samples))
        except Exception as exc:
            # Keep the failed case, but never manufacture labels from its prefix.
            row["blockers"] = ["physical_collection_failed"]
            row["exception_type"] = type(exc).__name__
        row["data_generation_wall_ns"] = perf_counter_ns() - case_started
        rows.append(row)
    blockers: list[str] = []
    dataset_report: dict[str, Any] | None = None
    try:
        dataset_report = validate_fiber_frame_warm_start_dataset(samples)
    except FiberFrameWarmStartLearningError as exc:
        blockers.append(str(exc))
    failed_count = sum(row["status"] != "ready" for row in rows)
    complete = failed_count == 0 and dataset_report is not None
    if complete:
        status = "ready"
    elif samples and failed_count:
        status = "partial"
    else:
        status = "blocked"
    if failed_count:
        blockers.append("one_or_more_physical_cases_blocked")
    identity = {
        "schema_version": "fiber-frame-warm-start-data-collection.v1",
        "physical_model_identity_profile": PHYSICAL_MODEL_IDENTITY_PROFILE,
        "source_revision": source_revision,
        "status": status,
        "dataset_complete": complete,
        "case_count": len(rows),
        "failed_case_count": failed_count,
        "sample_count": len(samples),
        "cases": [
            {
                key: value
                for key, value in row.items()
                if key != "data_generation_wall_ns"
            }
            for row in rows
        ],
        "samples": [sample.to_dict() for sample in samples],
        "sample_source_bindings": sample_bindings,
        "dataset_report": dataset_report,
        "blockers": blockers,
        "claim_boundary": {
            "solver_produced_targets_only": True,
            "incomplete_case_targets_retained": False,
            "split_scope": "caller_declared_synthetic_or_research_identities",
            "split_labels_prove_independent_projects": False,
            "external_provenance_verified": False,
            "source_revision_verified_against_checkout": False,
            "source_licensing_verified": False,
            "production_promotion_eligible": False,
            "generalized_speedup_claimed": False,
            "timing_enters_dataset_identity": False,
        },
    }
    report = {
        **identity,
        "collection_hash": canonical_hash(identity),
        "cases": rows,
        "data_generation_wall_ns": perf_counter_ns() - started,
        "timing_profile": "local-perf-counter-ns-sidecar.v1",
    }
    return FiberFrameWarmStartDataResult(
        status, tuple(samples), json.dumps(report, sort_keys=True, allow_nan=False)
    )
