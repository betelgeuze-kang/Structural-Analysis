"""Train-only cyclic-control proposals; original reference solves retain authority."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

import numpy as np

from structural_analysis.ai.fiber_frame_physical_identity import (
    fiber_frame_physical_model_payload,
)
from structural_analysis.ai.fiber_frame_warm_start_features import (
    fiber_frame_warm_start_model_features,
)
from structural_analysis.api import nonlinear_fiber_frame as public
from structural_analysis.api.rc_fiber_frame_direct_control import _with_constant_loading
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha, _save
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
    HISTORY_FEATURE_NAMES,
    control_history_features,
    history_sample_fields,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext,
    _with_strain_evaluation,
    _with_coordinate_precision,
    _with_material_arithmetic,
    _with_fiber_strain_evaluation,
    _with_force_accumulation,
    _with_terminal_coordinate_precision,
    benchmark_rc_control_seed_paths,
    secant_seed,
)
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.io.measured_response_workbook import MeasuredResponseWorkbook
from structural_analysis.units.schema import CoordinateSystem, UnitSystem

_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")
_HASH = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True, init=False)
class RCControlLearningCase:
    case_id: str
    project_id: str
    geometry_family_id: str
    load_history_id: str
    split: str
    request: BoundedRCFiberDirectControlRequest
    measurement_source: MeasuredResponseWorkbook | None = field(repr=False)
    _model_json: str = field(repr=False)

    def __init__(
        self,
        case_id,
        project_id,
        geometry_family_id,
        load_history_id,
        split,
        model,
        request,
        *,
        measurement_source=None,
    ):
        for name, value in [
            ("case_id", case_id),
            ("project_id", project_id),
            ("geometry_family_id", geometry_family_id),
            ("load_history_id", load_history_id),
        ]:
            if type(value) is not str or not _ID.fullmatch(value):
                raise ValueError(f"{name}: stable identity required")
            object.__setattr__(self, name, value)
        if (
            split not in ("train", "validation", "holdout")
            or type(model) is not CanonicalModel
            or type(request) is not BoundedRCFiberDirectControlRequest
        ):
            raise ValueError("typed model/request and supported split required")
        object.__setattr__(self, "split", split)
        if (
            measurement_source is not None
            and type(measurement_source) is not MeasuredResponseWorkbook
        ):
            raise ValueError("decoded measured source or None required")
        object.__setattr__(self, "measurement_source", measurement_source)
        object.__setattr__(
            self,
            "request",
            decode_bounded_rc_fiber_direct_control_request(_bytes(request.to_dict())),
        )
        object.__setattr__(
            self,
            "_model_json",
            _bytes(model.detached_analysis_snapshot().to_dict()).decode(),
        )

    @property
    def model(self):
        value = json.loads(self._model_json)
        value.pop("canonical_model_checksum")
        value["units"] = UnitSystem(**value["units"])
        value["coordinate_system"] = CoordinateSystem(
            axis_order=tuple(value["coordinate_system"]["axis_order"]),
            up_axis=value["coordinate_system"]["up_axis"],
        )
        return CanonicalModel(**value)


def _history_shape(targets):
    # Conservatively group amplitude/sign aliases and complete-prefix reuse.
    first = next((float(x) for x in targets if x != 0), None)
    if first is None:
        raise ValueError("nonzero control history required")
    ratios = tuple(float(x) / first for x in targets)
    if not all(np.isfinite(r) for r in ratios):
        raise ValueError("finite normalized control history required")
    return tuple(format(r, ".12g") for r in ratios)


RETAINED_LEARNING_ARITHMETIC_PROFILE = "retained-twofold-refinement.v1"


def _arithmetic_manifest(profile):
    if type(profile) is not str or profile not in (
        "binary64",
        RETAINED_LEARNING_ARITHMETIC_PROFILE,
    ):
        raise ValueError("unsupported RC learning arithmetic profile")
    if profile == "binary64":
        return None
    return {
        "profile": RETAINED_LEARNING_ARITHMETIC_PROFILE,
        "strain_evaluation": "exact-rational",
        "coordinate_precision": "twofold-increment",
        "material_arithmetic": "retained-strain",
        "fiber_strain_evaluation": "retained-coordinate",
        "force_accumulation": "rational",
        "terminal_coordinate_precision": "twofold",
        "terminal_refinement_limit": 2,
    }


def _arithmetic_kwargs(profile):
    manifest = _arithmetic_manifest(profile)
    return (
        {}
        if manifest is None
        else {k: v for k, v in manifest.items() if k != "profile"}
    )


def _learning_compiled_arithmetic(compiled, profile):
    if _arithmetic_manifest(profile) is None:
        return compiled
    return _with_terminal_coordinate_precision(
        _with_force_accumulation(
            _with_fiber_strain_evaluation(
                _with_material_arithmetic(
                    _with_coordinate_precision(
                        _with_strain_evaluation(compiled, "exact-rational"),
                        "twofold-increment",
                    ),
                    "retained-strain",
                ),
                "retained-coordinate",
            ),
            "rational",
        ),
        "twofold",
        2,
    )


def _preflight(cases, arithmetic_profile="binary64", *, measurement_screen=None):
    arithmetic = _arithmetic_manifest(arithmetic_profile)
    if not 2 <= len(cases) <= 32 or any(
        type(c) is not RCControlLearningCase for c in cases
    ):
        raise ValueError("two to 32 exact learning cases required")
    if (
        len({c.case_id for c in cases}) != len(cases)
        or not any(c.split == "train" for c in cases)
        or not any(c.split != "train" for c in cases)
    ):
        raise ValueError("unique cases, training and evaluation cases required")
    from structural_analysis.benchmark.rc_control_learning_split import (
        validate_control_learning_split_shapes,
    )

    from structural_analysis.benchmark.measured_response_split import (
        validate_measured_response_split_sources,
    )

    measured = validate_measured_response_split_sources(
        (case.case_id, case.split, case.measurement_source) for case in cases
    )
    if measurement_screen is not None:
        measurement_screen.update(measured)

    shape_records = {
        row["case_id"]: row
        for row in validate_control_learning_split_shapes(cases)["cases"]
    }
    owners: dict[tuple[str, str], str] = {}
    shapes: list[tuple[tuple[str, ...], str]] = []
    prepared = {}
    training_profile = None
    for case in cases:
        from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
            _directions,
        )

        _, reversals = (
            _directions(case.request.targets_m)
            if not case.request.constant_nodal_loads
            else ((), 0)
        )
        if (
            len(case.request.targets_m) > case.request.maximum_targets
            or reversals > case.request.maximum_reversals
            or (reversals and not case.request.allow_reversals)
        ):
            raise ValueError("declared control path budget exceeded")
        model = case.model
        physical = fiber_frame_physical_model_payload(model)
        # Separate geometry from section/material/load changes and entity names.
        geometry = {k: physical[k] for k in ("node_coordinates_m", "fixed_global_dofs")}
        geometry["members"] = [m["nodes"] for m in physical["members"]]
        shape = _history_shape(case.request.targets_m)
        for previous, split in shapes:
            if split != case.split and (
                previous == shape[: len(previous)] or shape == previous[: len(shape)]
            ):
                raise ValueError("split_leakage: control_history_shape_or_prefix")
        shapes.append((shape, case.split))
        keys = [
            (k, getattr(case, k))
            for k in ("project_id", "geometry_family_id", "load_history_id")
        ]
        keys += [
            ("geometry_hash", _sha(_bytes(geometry))),
            ("physical_model_hash", _sha(_bytes(physical))),
        ]
        for key in keys:
            if key in owners and owners[key] != case.split:
                raise ValueError(f"split_leakage: {key[0]}")
            owners[key] = case.split
        compiled, blockers, _ = public._compile(model)
        if compiled is None or blockers:
            raise ValueError("supported RC learning model required")
        compiled = _with_constant_loading(compiled, case.request.constant_nodal_loads)
        physical_compiled = compiled
        if (
            arithmetic is not None
            and not case.request.solver_config.newton.terminal_polishing
        ):
            raise ValueError(
                "retained RC learning arithmetic requires enabled terminal polishing"
            )
        compiled = _learning_compiled_arithmetic(compiled, arithmetic_profile)
        from structural_analysis.assembly import (
            initial_stateful_fiber_frame2d_checkpoint,
        )
        from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
            StatefulFiberFrame2DDisplacementControlStepAdapter,
            validate_stateful_fiber_frame2d_control_problem,
        )

        if not case.request.targets_m:
            raise ValueError("nonempty control path required")
        if case.request.constant_nodal_loads:
            validate_stateful_fiber_frame2d_control_problem(
                compiled.problem, case.request.control_global_dof
            )
        else:
            StatefulFiberFrame2DDisplacementControlStepAdapter(
                compiled.problem,
                initial_stateful_fiber_frame2d_checkpoint(compiled.problem),
                case.request.control_global_dof,
                case.request.targets_m[0],
                case.request.solver_config,
            )
        # Static declaration features retain the original public exact-type guards.
        # Only this experimental learning context binds the transformed solver.
        model_features = fiber_frame_warm_start_model_features(
            physical_compiled.problem
        )
        if arithmetic is not None:
            model_features = replace(
                model_features,
                problem_contract_hash=compiled.problem.contract_hash,
                context_hash=_sha(
                    _bytes(
                        {
                            "schema_version": "rc-control-learning-arithmetic-context.v1",
                            "base_model_context_hash": model_features.context_hash,
                            "arithmetic_profile": arithmetic,
                        }
                    )
                ),
            )
        if case.split == "train":
            current_profile = (
                model_features.context_hash,
                model_features.feature_names,
                compiled.problem.free_global_dofs,
                case.request.control_global_dof,
                case.request.solver_config.contract_hash,
            )
            if training_profile is not None and current_profile != training_profile:
                raise ValueError("training contexts must match before label collection")
            training_profile = current_profile
        prepared[case.case_id] = (
            model,
            compiled,
            model_features,
            dict(keys) | {"conservative_shape_screen": shape_records[case.case_id]},
            shape,
        )
    return prepared


def _features(context, model_features):
    if (
        type(context) is not RCControlSeedContext
        or context.problem_contract_hash != model_features.problem_contract_hash
    ):
        raise ValueError("proposal context must bind the compiled model")
    q = np.asarray(context.accepted_augmented_coordinates_m, dtype=float)
    t = np.asarray(context.accepted_targets_m, dtype=float)
    if (
        q.ndim != 2
        or len(q) != len(t)
        or not 1 <= len(t) <= 255
        or not np.all(np.isfinite(q))
        or not np.all(np.isfinite(t))
        or type(context.control_free_index) is not int
        or not 0 <= context.control_free_index < q.shape[1] - 1
    ):
        raise ValueError("finite original accepted-prefix coordinates required")
    if not np.isfinite(context.target_m):
        raise ValueError("finite target required")
    dq = q[-1] - q[-2] if len(t) > 1 else np.zeros(q.shape[1])
    dt = t[-1] - t[-2] if len(t) > 1 else 0.0
    return np.concatenate(
        [
            model_features.values,
            [context.target_m, context.target_m - t[-1], dt, len(t) - 1],
            q[-1],
            dq,
        ]
    )


@dataclass(frozen=True)
class RCControlSeedPolicy:
    """Immutable detached JSON; weights and preprocessing contain train rows only."""

    _json: str = field(repr=False)

    def __post_init__(self):
        if type(self._json) is not str:
            raise ValueError("policy JSON text required")
        d = strict_json_object_bytes(self._json.encode(), maximum_bytes=8 * 1024 * 1024)
        expected = {
            "schema_version",
            "model_context_hash",
            "model_feature_names",
            "free_global_dofs",
            "control_free_index",
            "solver_config_hash",
            "feature_mean",
            "feature_scale",
            "feature_min",
            "feature_max",
            "target_scale",
            "weights",
            "training_sample_hashes",
            "ridge",
            "ood_margin",
            "policy_hash",
        }
        history_profile = (
            d.get("schema_version")
            == "experimental-rc-control-secant-correction-policy.v3"
        )
        if history_profile:
            expected.update(
                {
                    "feature_profile",
                    "load_factor_coordinate_scale_m",
                    "arithmetic_profile",
                }
            )
            if d.get("feature_profile") != HISTORY_FEATURE_PROFILE:
                raise ValueError("exact control-history feature profile required")
            coordinate_scale = d.get("load_factor_coordinate_scale_m")
            if (
                not isinstance(coordinate_scale, (int, float))
                or isinstance(coordinate_scale, bool)
                or not np.isfinite(coordinate_scale)
                or coordinate_scale <= 0
            ):
                raise ValueError(
                    "positive finite policy load-coordinate scale required"
                )
            if d.get("arithmetic_profile") is not None and _bytes(
                d.get("arithmetic_profile")
            ) != _bytes(_arithmetic_manifest(RETAINED_LEARNING_ARITHMETIC_PROFILE)):
                raise ValueError("exact RC policy arithmetic profile required")
        elif (
            d.get("schema_version")
            == "experimental-rc-control-secant-correction-policy.v2"
        ):
            expected.add("arithmetic_profile")
            if _bytes(d.get("arithmetic_profile")) != _bytes(
                _arithmetic_manifest(RETAINED_LEARNING_ARITHMETIC_PROFILE)
            ):
                raise ValueError("exact RC policy arithmetic profile required")
        elif (
            d.get("schema_version")
            != "experimental-rc-control-secant-correction-policy.v1"
        ):
            raise ValueError("exact RC policy schema required")
        if set(d) != expected:
            raise ValueError("exact RC policy schema required")
        h = d.pop("policy_hash")
        if h != _sha(_bytes(d)):
            raise ValueError("RC policy hash mismatch")
        for k in ["model_context_hash", "solver_config_hash"]:
            if type(d[k]) is not str or not _HASH.fullmatch(d[k]):
                raise ValueError("policy source hash required")
        for k in ["ridge", "ood_margin"]:
            if (
                type(d[k]) not in (int, float)
                or not np.isfinite(d[k])
                or d[k] < 0
                or (k == "ridge" and d[k] == 0)
            ):
                raise ValueError("finite policy hyperparameter required")
        if (
            type(d["free_global_dofs"]) is not list
            or any(type(x) is not int or not 0 <= x < 48 for x in d["free_global_dofs"])
            or len(set(d["free_global_dofs"])) != len(d["free_global_dofs"])
        ):
            raise ValueError("unique original DOF order required")
        if (
            type(d["model_feature_names"]) is not list
            or any(
                type(x) is not str or not _ID.fullmatch(x)
                for x in d["model_feature_names"]
            )
            or len(set(d["model_feature_names"])) != len(d["model_feature_names"])
        ):
            raise ValueError("unique model feature names required")

        def numeric_array(value):
            if type(value) is list:
                return all(numeric_array(x) for x in value)
            return type(value) in (int, float) and (
                type(value) is not int or abs(value) <= 2**53 - 1
            )

        width = len(d["feature_mean"])
        count = len(d["free_global_dofs"]) + 1
        if (
            not 1 <= width <= 2200
            or not 2 <= count <= 49
            or type(d["control_free_index"]) is not int
            or not 0 <= d["control_free_index"] < count - 1
        ):
            raise ValueError("bounded policy dimensions required")
        for k, shape in [
            ("feature_mean", (width,)),
            ("feature_scale", (width,)),
            ("feature_min", (width,)),
            ("feature_max", (width,)),
            ("target_scale", (count,)),
            ("weights", (width + 1, count)),
        ]:
            if type(d[k]) is not list or not numeric_array(d[k]):
                raise ValueError("exact finite numeric policy arrays required")
            a = np.asarray(d[k])
            if (
                a.dtype.kind not in "if"
                or a.shape != shape
                or not np.all(np.isfinite(a))
            ):
                raise ValueError("finite matching policy arrays required")
            if k in ("feature_scale", "target_scale") and np.any(a <= 0):
                raise ValueError("positive policy scales required")
        dynamic_width = 3 + len(HISTORY_FEATURE_NAMES) if history_profile else 4
        if width != len(d["model_feature_names"]) + dynamic_width + 2 * count:
            raise ValueError("policy feature layout mismatch")
        if np.any(np.asarray(d["feature_min"]) > d["feature_max"]):
            raise ValueError("ordered policy bounds required")
        if (
            not 2 <= len(d["training_sample_hashes"]) <= 8160
            or any(
                type(h) is not str or not _HASH.fullmatch(h)
                for h in d["training_sample_hashes"]
            )
            or len(set(d["training_sample_hashes"])) != len(d["training_sample_hashes"])
        ):
            raise ValueError("unique original training sample hashes required")

    @property
    def policy_hash(self):
        return self.to_dict()["policy_hash"]

    def to_dict(self):
        return json.loads(self._json)

    def propose(
        self,
        context,
        model_features,
        free_global_dofs,
        solver_config_hash,
        *,
        arithmetic_profile="binary64",
        load_factor_coordinate_scale_m=None,
    ):
        d = self.to_dict()
        try:
            arithmetic = _arithmetic_manifest(arithmetic_profile)
        except ValueError:
            return None
        if d.get("arithmetic_profile") != arithmetic:
            return None
        if (
            d["model_context_hash"] != model_features.context_hash
            or d["model_feature_names"] != list(model_features.feature_names)
            or d["free_global_dofs"] != list(free_global_dofs)
            or d["solver_config_hash"] != solver_config_hash
            or d["control_free_index"] != context.control_free_index
            or len(context.accepted_targets_m) < 2
        ):
            return None
        history_profile = d.get("feature_profile") == HISTORY_FEATURE_PROFILE
        if history_profile:
            if load_factor_coordinate_scale_m != d["load_factor_coordinate_scale_m"]:
                return None
            x, correction_scales = control_history_features(
                context, model_features, load_factor_coordinate_scale_m
            )
        else:
            x = _features(context, model_features)
            correction_scales = 1.0
        low, high = np.asarray(d["feature_min"]), np.asarray(d["feature_max"])
        if x.shape != low.shape:
            return None
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            slack = np.maximum((high - low) * d["ood_margin"], 1e-12)
            if np.any((x < low - slack) | (x > high + slack)):
                return None
            seed = secant_seed(context)
            if seed is None:
                return None
            z = (x - d["feature_mean"]) / d["feature_scale"]
            value = (
                np.asarray(seed)
                + (np.append(z, 1.0) @ np.asarray(d["weights"]))
                * d["target_scale"]
                * correction_scales
            )
            value[context.control_free_index] = context.target_m
            return (
                tuple(float(x) for x in value) if np.all(np.isfinite(value)) else None
            )


def _fit(samples, profile, ridge, ood_margin):
    if len(samples) < 2:
        raise ValueError("at least two original training pairs required")
    x = np.asarray([s["features"] for s in samples])
    y = np.asarray([s["correction"] for s in samples])
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        mean = x.mean(axis=0)
        scale = x.std(axis=0)
        scale = np.where(scale > 0, scale, 1.0)
        target = y.std(axis=0)
        target = np.where(target > 0, target, 1.0)
        z = np.column_stack([(x - mean) / scale, np.ones(len(x))])
        weights = np.linalg.solve(
            z.T @ z + ridge * np.eye(z.shape[1]), z.T @ (y / target)
        )
    d = {
        "schema_version": "experimental-rc-control-secant-correction-policy.v3"
        if profile.get("feature_profile") == HISTORY_FEATURE_PROFILE
        else "experimental-rc-control-secant-correction-policy.v2"
        if "arithmetic_profile" in profile
        else "experimental-rc-control-secant-correction-policy.v1",
        **profile,
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "feature_min": x.min(axis=0).tolist(),
        "feature_max": x.max(axis=0).tolist(),
        "target_scale": target.tolist(),
        "weights": weights.tolist(),
        "training_sample_hashes": [s["sample_hash"] for s in samples],
        "ridge": ridge,
        "ood_margin": ood_margin,
    }
    d["policy_hash"] = _sha(_bytes(d))
    return RCControlSeedPolicy(_bytes(d).decode())


def _execution_work(rows):
    known = {"core_calls": 0, "newton_iterations": 0, "linear_solves": 0}
    unknown = False
    for row in rows:
        if row.get("status") == "not_attempted":
            continue
        report = row.get("report")
        if report is None:
            unknown = True
            continue
        for arm in [*report["arms"].values(), report["fresh_reference"]]:
            invocations = [
                *arm.get("preload_invocations", []),
                *(i for entry in arm["entries"] for i in entry["invocations"]),
            ]
            for invocation in invocations:
                unknown = unknown or invocation["unknown_work"]
                for key in known:
                    value = (invocation.get("work") or {}).get(key)
                    if type(value) is int and value >= 0:
                        known[key] += value
                    else:
                        unknown = True
    return {"known_work": known, "unknown_work": unknown}


def run_rc_control_learning_study(
    cases,
    *,
    source_revision,
    output_directory,
    ridge=1e-6,
    ood_margin=0.1,
    generation_arm_order=("reference", "secant"),
    evaluation_arm_order=("reference", "secant", "proposal"),
    arithmetic_profile="binary64",
    feature_profile="legacy",
):
    """Preflight every split, collect only train labels, freeze once, then evaluate."""
    wall, cpu = perf_counter_ns(), process_time_ns()
    cases = tuple(cases)
    if type(feature_profile) is not str or feature_profile not in (
        "legacy",
        HISTORY_FEATURE_PROFILE,
    ):
        raise ValueError("supported RC learning feature profile required")
    if type(source_revision) is not str or not re.fullmatch(
        "[0-9a-f]{40}", source_revision
    ):
        raise ValueError("exact source revision required")
    for k, v in [("ridge", ridge), ("ood_margin", ood_margin)]:
        if (
            type(v) not in (int, float)
            or not np.isfinite(v)
            or v < 0
            or (k == "ridge" and v == 0)
        ):
            raise ValueError("finite declared hyperparameters required")
    for order, expected in [
        (generation_arm_order, ("reference", "secant")),
        (evaluation_arm_order, ("reference", "secant", "proposal")),
    ]:
        if (
            type(order) is not tuple
            or len(order) != len(expected)
            or set(order) != set(expected)
        ):
            raise ValueError("each declared strategy must occur once in its arm order")
    arithmetic = _arithmetic_manifest(arithmetic_profile)
    measurement_screen: dict[str, Any] = {}
    prepared = _preflight(
        cases, arithmetic_profile, measurement_screen=measurement_screen
    )
    arithmetic_identity = (
        {} if arithmetic is None else {"arithmetic_profile": arithmetic}
    )
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    declarations = []
    for case in cases:
        model, compiled, features, identities, shape = prepared[case.case_id]
        declarations.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "identities": identities,
                "history_shape": list(shape),
                "model_checksum": model.canonical_model_checksum,
                "request": case.request.to_dict(),
                "model_features": features.to_dict(),
            }
        )
    _save(
        root,
        "plan.json",
        _bytes(
            {
                "source_revision": source_revision,
                **arithmetic_identity,
                **(
                    {"feature_profile": feature_profile}
                    if feature_profile != "legacy"
                    else {}
                ),
                "cases": declarations,
                "generation_arm_order": list(generation_arm_order),
                "evaluation_arm_order": list(evaluation_arm_order),
                "ridge": ridge,
                "ood_margin": ood_margin,
                "split_provenance_independent": False,
                "measured_source_split_screen": {
                    key: value
                    for key, value in measurement_screen.items()
                    if key != "screen_wall_ns"
                },
                "geometry_screen_scope": "entity-name invariant coordinates/connectivity/restraints; not general rotated/translated equivalence",
                "history_screen_scope": "12 significant-digit amplitude/sign-normalized complete histories and prefixes; conservative screen, not independent provenance",
            }
        ),
    )
    samples = []
    generation = []
    evaluation = []
    profile = None
    policy = None
    fit = None
    for case in cases:
        if case.split != "train":
            continue
        model, compiled, features, _, _ = prepared[case.case_id]
        _save(
            root,
            f"{case.case_id}-generation-started.json",
            _bytes(
                {
                    "case_id": case.case_id,
                    "status": "started",
                    "unknown_work_until_outcome": True,
                }
            ),
        )
        try:
            report = benchmark_rc_control_seed_paths(
                model,
                case.request,
                source_revision=source_revision,
                output_directory=root / case.case_id / "generation",
                arm_order=generation_arm_order,
                **_arithmetic_kwargs(arithmetic_profile),
            )
            row = {
                "case_id": case.case_id,
                "report": report,
                "labels_eligible": report["reference_repeat_exact"],
            }
            if row["labels_eligible"]:
                folder = root / case.case_id / "generation" / "reference"
                for entry in report["arms"]["reference"]["entries"]:
                    index = entry["target_index"]
                    context = RCControlSeedContext(
                        **json.loads(
                            (folder / f"{index:03d}-context.json").read_bytes()
                        )
                    )
                    # Restore immutable prefix containers before feature extraction.
                    context = RCControlSeedContext(
                        context.problem_contract_hash,
                        context.control_global_dof,
                        context.control_free_index,
                        context.target_m,
                        tuple(context.accepted_targets_m),
                        tuple(
                            tuple(q) for q in context.accepted_augmented_coordinates_m
                        ),
                    )
                    if len(context.accepted_targets_m) < 2:
                        continue
                    step_bytes = (folder / f"{index:03d}-1-step.json").read_bytes()
                    step = json.loads(step_bytes)
                    if (
                        not step["committed"]
                        or not entry["invocations"][0]["committed"]
                    ):
                        raise ValueError("original committed reference label required")
                    current = {
                        "model_context_hash": features.context_hash,
                        "model_feature_names": list(features.feature_names),
                        "free_global_dofs": list(compiled.problem.free_global_dofs),
                        "control_free_index": context.control_free_index,
                        "solver_config_hash": case.request.solver_config.contract_hash,
                        **arithmetic_identity,
                        **(
                            {
                                "feature_profile": HISTORY_FEATURE_PROFILE,
                                "load_factor_coordinate_scale_m": case.request.solver_config.load_factor_coordinate_scale_m,
                                "arithmetic_profile": arithmetic,
                            }
                            if feature_profile == HISTORY_FEATURE_PROFILE
                            else {}
                        ),
                    }
                    if profile is not None and current != profile:
                        raise ValueError("training contexts must match")
                    profile = current
                    label = np.asarray(
                        step["trial_solution"]["augmented_coordinates_m"]
                    )
                    sample = {
                        "case_id": case.case_id,
                        "split": "train",
                        "target_index": index,
                        "original_step_bytes_hash": _sha(step_bytes),
                        "parent_hash": entry["parent_hash"],
                        "context": json.loads(_bytes(context.__dict__)),
                        "features": _features(context, features).tolist(),
                        "accepted_coordinates": label.tolist(),
                        "correction": (
                            label - np.asarray(secant_seed(context))
                        ).tolist(),
                    }
                    if arithmetic is not None:
                        sample.update(
                            arithmetic_profile=arithmetic,
                            label_representation="accepted-high-component-for-binary64-start.v1",
                            accepted_coordinate_compensation_m=step["trial_solution"][
                                "augmented_coordinate_compensation_m"
                            ],
                        )
                    if feature_profile == HISTORY_FEATURE_PROFILE:
                        sample.update(
                            history_sample_fields(
                                context,
                                features,
                                case.request.solver_config.load_factor_coordinate_scale_m,
                                sample["correction"],
                            )
                        )
                    sample["sample_hash"] = _sha(_bytes(sample))
                    samples.append(sample)
        except Exception as exc:
            row = {
                "case_id": case.case_id,
                "labels_eligible": False,
                "exception_kind": type(exc).__name__,
                "unknown_work": True,
            }
        generation.append(row)
        _save(root, f"{case.case_id}-generation-outcome.json", _bytes(row))
    _save(root, "training-samples.json", _bytes(samples))
    if generation and all(row["labels_eligible"] for row in generation):
        _save(
            root,
            "fit-started.json",
            _bytes(
                {
                    "status": "started",
                    "sample_count": len(samples),
                    "unknown_fit_work_until_outcome": True,
                }
            ),
        )
        fw, fc = perf_counter_ns(), process_time_ns()
        try:
            policy = _fit(samples, profile, float(ridge), float(ood_margin))
            fit = {
                "status": "completed",
                "policy_hash": policy.policy_hash,
                "sample_count": len(samples),
            }
            _save(root, "policy.json", _bytes(policy.to_dict()))
        except Exception as exc:
            fit = {
                "status": "failed",
                "exception_kind": type(exc).__name__,
                "unknown_fit_work": True,
            }
        finally:
            if fit is not None:
                fit["wall_ns"] = perf_counter_ns() - fw
                fit["cpu_ns"] = process_time_ns() - fc
        _save(root, "fit-outcome.json", _bytes(fit))
    frozen = None if policy is None else _bytes(policy.to_dict())
    for case in cases:
        if case.split == "train":
            continue
        if policy is None:
            row = {
                "case_id": case.case_id,
                "split": case.split,
                "status": "not_attempted",
                "reason": "training_not_completed",
            }
        else:
            model, compiled, features, _, _ = prepared[case.case_id]
            decisions = []

            def propose(context):
                value = policy.propose(
                    context,
                    features,
                    compiled.problem.free_global_dofs,
                    case.request.solver_config.contract_hash,
                    arithmetic_profile=arithmetic_profile,
                    load_factor_coordinate_scale_m=case.request.solver_config.load_factor_coordinate_scale_m,
                )
                decisions.append(
                    {
                        "accepted_prefix_count": len(context.accepted_targets_m),
                        "target_m": context.target_m,
                        "decision": "abstained_to_reference"
                        if value is None
                        else "proposed",
                    }
                )
                return value

            _save(
                root,
                f"{case.case_id}-evaluation-started.json",
                _bytes(
                    {
                        "status": "started",
                        "policy_hash": policy.policy_hash,
                        "unknown_work_until_outcome": True,
                    }
                ),
            )
            try:
                report = benchmark_rc_control_seed_paths(
                    model,
                    case.request,
                    source_revision=source_revision,
                    output_directory=root / case.case_id / "evaluation",
                    proposal=propose,
                    proposal_identity=policy.policy_hash,
                    arm_order=evaluation_arm_order,
                    **_arithmetic_kwargs(arithmetic_profile),
                )
                if _bytes(policy.to_dict()) != frozen:
                    raise ValueError("policy changed during evaluation")
                row = {
                    "case_id": case.case_id,
                    "split": case.split,
                    "status": "returned",
                    "report": report,
                    "proposal_decisions": decisions,
                }
            except Exception as exc:
                row = {
                    "case_id": case.case_id,
                    "split": case.split,
                    "status": "raised",
                    "exception_kind": type(exc).__name__,
                    "unknown_work": True,
                    "proposal_decisions": decisions,
                }
        evaluation.append(row)
        _save(root, f"{case.case_id}-evaluation-outcome.json", _bytes(row))
    report = {
        "schema_version": "experimental-rc-control-learning-study.v1",
        **arithmetic_identity,
        **({"feature_profile": feature_profile} if feature_profile != "legacy" else {}),
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "generation": generation,
        "fit": fit,
        "generation_work": _execution_work(generation),
        "evaluation_work": _execution_work(evaluation),
        "evaluation": evaluation,
        "policy": None if policy is None else policy.to_dict(),
        "training_case_ids": [c.case_id for c in cases if c.split == "train"],
        "evaluation_case_ids": [c.case_id for c in cases if c.split != "train"],
        "measured_source_split_screen": measurement_screen,
        "whole_study_wall_ns": perf_counter_ns() - wall,
        "whole_study_cpu_ns": process_time_ns() - cpu,
        "timing_scope": "preflight_all_generation_reference_secant_fresh_verification_fit_all_evaluation_proposals_recovery_and_io_excluding_final_report_write",
        "claims": {
            "policy_training_performed": policy is not None,
            "independent_validation": False,
            "performance_improvement": False,
            "design_approval": False,
        },
    }
    report["report_hash"] = _sha(_bytes(report))
    _save(root, "learning-study.json", _bytes(report))
    return report
