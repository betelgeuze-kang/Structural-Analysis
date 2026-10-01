"""Development cost gate using checked, own-arm predecessor work.

The fixed measured target, ridge 1, unpenalized intercept and 0.01 threshold
come from rc_cost_margin_gate. A pure join or a self-consistent record does not
authenticate original counters or admit a historical training campaign. Online
full-path evaluation must still pay feature, guard, setup and validation costs.
"""

from copy import deepcopy
from dataclasses import dataclass, fields
import math
import re
from time import perf_counter_ns
from types import MappingProxyType

from structural_analysis.ai.fiber_frame_warm_start_features import (
    FiberFrameWarmStartModelFeatures,
    decode_fiber_frame_warm_start_model_features,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_learning import RCControlSeedPolicy
from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext

from prepare_rc_nested_switch_labels import require
from rc_cost_margin_gate import (
    TARGET_PROFILE,
    CostMarginGate,
    _fit_cost_gate,
    cost_target,
)
from rc_switch_gate import _fit_gate
from audit_rc_nested_switch_labels import label_from_repetitions
from rc_switch_prefix_features import (
    PROFILE as PREFIX_PROFILE,
    PRIOR_WORK_COUNTERS,
    PRIOR_WORK_PROFILE,
    prefix_features,
    prefix_prior_work_features,
)

SCHEMA = "rc-pre-capture-prior-work-cost-margin-gate.v1"
JOIN_PROFILE = "rc-checked-prior-work-cost-input-join.v1"
FULL_TRAINING_PROFILE = "rc-full-training-checked-prior-work-cost-input.v1"
FULL_TRAINING_GATE_SCHEMA = "rc-full-training-prior-work-cost-margin-gate.v1"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_ROW_IDENTITY = ("source_sample_hash", "policy_hash", "seed_fit_index")


def _hash(value):
    require(
        type(value) is str and _HASH.fullmatch(value), "prefixed exact hash required"
    )
    return value


def _feature_layout(names):
    require(type(names) in (list, tuple) and names, "aligned feature layout required")
    suffix = tuple("prior_work." + name for name in PRIOR_WORK_COUNTERS)
    require(
        tuple(names[-len(suffix) :]) == suffix,
        "exact predecessor counter layout required",
    )
    prefix = names[: -len(suffix)]
    width = 0
    while (
        width < len(prefix)
        and type(prefix[width]) is str
        and re.fullmatch(r"model\.[a-z][a-z0-9_]{0,127}", prefix[width])
    ):
        width += 1
    require(
        1 <= width <= 2048
        and tuple(prefix[width : width + 3])
        == ("target_m", "target_increment_m", "previous_target_increment_m"),
        "physical accepted-prefix layout required",
    )
    coordinates, remainder = divmod(len(prefix) - width - 3, 2)
    require(
        remainder == 0
        and 2 <= coordinates <= 49
        and tuple(prefix[width + 3 :])
        == (
            *(f"last_coordinate_{i}" for i in range(coordinates)),
            *(f"coordinate_increment_{i}" for i in range(coordinates)),
        ),
        "original accepted-coordinate layout required",
    )


class _UnboundPriorWorkGate(CostMarginGate):
    """Internal fixed ridge solve; never exported as an online policy."""

    _schema = SCHEMA
    _feature_profile = PRIOR_WORK_PROFILE


@dataclass(frozen=True)
class PriorWorkCostMarginGate(_UnboundPriorWorkGate):
    """Immutable checked policy, bound to the actual fold's seed policy."""

    def __post_init__(self):
        require(type(self._json) is str, "gate JSON required")
        payload = strict_json_object_bytes(
            self._json.encode(), maximum_bytes=1024 * 1024
        )
        _hash(payload.get("seed_policy_hash"))
        require(
            payload.get("policy_hash")
            == _sha(
                _bytes(
                    {
                        key: value
                        for key, value in payload.items()
                        if key != "policy_hash"
                    }
                )
            ),
            "gate hash mismatch",
        )
        _feature_layout(payload.get("feature_names"))
        base = {
            key: value
            for key, value in payload.items()
            if key not in ("seed_policy_hash", "policy_hash")
        }
        base["policy_hash"] = _sha(_bytes(base))
        # Reuse every strict legacy field/array/count check and the same solve
        # semantics. Only this new schema adds the hashed seed-policy binding.
        try:
            checked = _UnboundPriorWorkGate(_bytes(base).decode())
        except (TypeError, OverflowError) as exc:
            raise ValueError("finite typed prior-work policy arrays required") from exc
        require(
            set(payload) == set(checked._payload) | {"seed_policy_hash"},
            "exact prior-work gate fields required",
        )
        object.__setattr__(
            self,
            "_payload",
            MappingProxyType(
                {
                    key: tuple(value) if type(value) is list else value
                    for key, value in payload.items()
                }
            ),
        )

    @property
    def seed_policy_hash(self):
        return self._payload["seed_policy_hash"]

    @property
    def excluded_case_ids(self):
        return self._payload["excluded_case_ids"]

    def decision(self, features):
        require(
            type(features) is dict
            and set(features) == {"profile", "feature_names", "values"}
            and type(features["values"]) in (list, tuple),
            "exact prior-work feature fields required",
        )
        counters = features["values"][-len(PRIOR_WORK_COUNTERS) :]
        require(
            len(counters) == len(PRIOR_WORK_COUNTERS)
            and all(
                type(value) in (int, float)
                and 0 <= value <= 2**53 - 1
                and math.isfinite(value)
                and value == int(value)
                for value in counters
            ),
            "exact known predecessor inference counters required",
        )
        return super().decision(features)

    def guard(self, model_features):
        require(
            type(model_features) is FiberFrameWarmStartModelFeatures,
            "exact typed model features required",
        )

        def decide(context):
            try:
                return bool(
                    self.decision(prefix_prior_work_features(context, model_features))
                )
            except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError):
                # Missing/foreign/future/unknown predecessor data cannot trigger
                # current-target material capture or an AI correction.
                return False

        return decide


def _context(payload):
    require(type(payload) is dict, "original prior-work context required")
    required = {
        "problem_contract_hash",
        "control_global_dof",
        "control_free_index",
        "target_m",
        "accepted_targets_m",
        "accepted_augmented_coordinates_m",
        "prior_work_binding",
        "prior_accepted_transition_work",
    }
    allowed = {item.name for item in fields(RCControlSeedContext)}
    require(
        required <= set(payload) <= allowed, "exact prior-work context fields required"
    )
    require(
        type(payload["accepted_targets_m"]) in (list, tuple)
        and type(payload["accepted_augmented_coordinates_m"]) in (list, tuple)
        and all(
            type(row) in (list, tuple)
            for row in payload["accepted_augmented_coordinates_m"]
        ),
        "original prefix arrays required",
    )
    detached = deepcopy(payload)
    detached["accepted_targets_m"] = tuple(detached["accepted_targets_m"])
    detached["accepted_augmented_coordinates_m"] = tuple(
        tuple(row) for row in detached["accepted_augmented_coordinates_m"]
    )
    result = RCControlSeedContext(**detached)
    require(
        _bytes(result.to_dict()) == _bytes(payload),
        "typed original context roundtrip required",
    )
    return result


def _checked_row_inputs(row):
    context = _context(row["prior_work_context"])
    model = decode_fiber_frame_warm_start_model_features(row["model_features"])
    features = prefix_prior_work_features(context, model)
    # The helper just validated this detached context against its original step
    # bytes. Reuse its checked binding without reparsing the same record twice.
    require(
        context.prior_work_binding["current_parent_hash"] == row["parent_hash"],
        "original current parent required",
    )
    return context, model, features


def _row_key(row):
    require(type(row) is dict, "original source row required")
    for name in ("source_sample_hash", "policy_hash", "parent_hash"):
        _hash(row[name])
    require(
        type(row["seed_fit_index"]) is int
        and row["seed_fit_index"] >= 0
        and type(row["case_id"]) is str
        and row["case_id"],
        "exact producing policy and case identity required",
    )
    return tuple(row[name] for name in _ROW_IDENTITY)


def append_prior_work_inputs(tables, inputs, *, seed_policy_hash):
    """Pure fold join after original campaign and connected-split audits.

    Input rows identify each original sample AND its producing policy/fit. All
    declared train/unverified/validation joins must be present, without extras.
    Caller must independently authenticate the original predecessor records.
    No complete packet digest or excluded-row numeric data enters the fitter.
    """
    _hash(seed_policy_hash)
    require(
        type(inputs) is dict
        and set(inputs) == {"schema_version", "rows"}
        and inputs["schema_version"] == JOIN_PROFILE
        and type(inputs["rows"]) is list,
        "exact prior-work join packet required",
    )
    require(
        type(tables) is dict and set(tables) == {"training", "validation"},
        "original training and validation tables required",
    )
    result = deepcopy(tables)
    expected = {}
    for table, collections in (
        (result["training"], ("training_rows", "unverified_rows")),
        (result["validation"], ("rows",)),
    ):
        require(
            table["feature_profile"] == PREFIX_PROFILE, "original prefix table required"
        )
        for collection in collections:
            for row in table[collection]:
                key = _row_key(row)
                require(key not in expected, "unique fold source-policy join required")
                expected[key] = (row, table)
    observed = set()
    names = None
    for source in inputs["rows"]:
        require(
            type(source) is dict
            and set(source)
            == {
                "source_sample_hash",
                "policy_hash",
                "seed_fit_index",
                "case_id",
                "parent_hash",
                "prior_work_context",
                "model_features",
            },
            "exact original predecessor join fields required",
        )
        key = _row_key(source)
        require(
            key in expected and key not in observed,
            "unique declared predecessor join required",
        )
        observed.add(key)
        row, table = expected[key]
        require(
            source["case_id"] == row["case_id"]
            and source["parent_hash"] == row["parent_hash"],
            "original source case and accepted parent required",
        )
        context, model, features = _checked_row_inputs(source)
        prefix = prefix_features(context, model)
        require(
            _bytes(prefix["feature_names"]) == _bytes(table["feature_names"])
            and _bytes(prefix["values"]) == _bytes(row["values"]),
            "original accepted-prefix input correspondence required",
        )
        if names is None:
            names = features["feature_names"]
        require(
            names == features["feature_names"],
            "aligned prior-work feature schema required",
        )
        row["prior_work_context"] = deepcopy(source["prior_work_context"])
        row["model_features"] = deepcopy(source["model_features"])
        row["values"] = features["values"]
    require(
        observed == set(expected) and names is not None,
        "complete original predecessor join required",
    )
    for table in result.values():
        table["feature_profile"] = PRIOR_WORK_PROFILE
        table["feature_names"] = list(names)
        table["prior_work_join_profile"] = JOIN_PROFILE
    result["training"]["seed_policy_hash"] = seed_policy_hash
    return result


def fit_prior_work_cost_gate(training):
    """Fixed pure fit of checked in-memory rows, without campaign admission."""
    started = perf_counter_ns()
    required = {
        "outer_group_index",
        "excluded_case_ids",
        "feature_profile",
        "feature_names",
        "cost_target_profile",
        "training_rows",
        "unverified_rows",
        "verified_positive_count",
        "verified_negative_count",
        "normalization_scope",
        "gate_fitted",
        "independent_evaluation",
        "prior_work_join_profile",
        "seed_policy_hash",
    }
    require(
        type(training) is dict
        and required <= set(training) <= required | {"validation_group_index"}
        and training["prior_work_join_profile"] == JOIN_PROFILE,
        "checked prior-work input join required",
    )
    require(
        type(training["outer_group_index"]) is int
        and training["outer_group_index"] >= 0
        and (
            "validation_group_index" not in training
            or (
                type(training["validation_group_index"]) is int
                and training["validation_group_index"] >= 0
                and training["validation_group_index"] != training["outer_group_index"]
            )
        )
        and training["gate_fitted"] is False
        and training["independent_evaluation"] is False
        and type(training["normalization_scope"]) is str
        and training["normalization_scope"]
        and type(training["training_rows"]) is list
        and type(training["unverified_rows"]) is list,
        "original unpromoted training table required",
    )
    _hash(training["seed_policy_hash"])
    _feature_layout(training["feature_names"])
    require(
        training["feature_profile"] == PRIOR_WORK_PROFILE
        and type(training["excluded_case_ids"]) is list
        and training["excluded_case_ids"],
        "prior-work profile and original exclusions required",
    )
    seen = set()
    for collection in ("training_rows", "unverified_rows"):
        for row in training[collection]:
            require(
                type(row) is dict
                and set(row)
                == {
                    "case_id",
                    "source_sample_hash",
                    "parent_hash",
                    "seed_fit_index",
                    "policy_hash",
                    "values",
                    "label",
                    "cost_repetitions",
                    "cost_target",
                    "prior_work_context",
                    "model_features",
                },
                "exact causal training row fields required",
            )
            key = _row_key(row)
            require(
                key not in seen and row["case_id"] not in training["excluded_case_ids"],
                "unique training complement required",
            )
            seen.add(key)
            _, _, features = _checked_row_inputs(row)
            require(
                _bytes(features["feature_names"]) == _bytes(training["feature_names"])
                and type(row["values"]) is list
                and all(
                    type(value) in (int, float) and math.isfinite(value)
                    for value in row["values"]
                )
                and _bytes(features["values"]) == _bytes(row["values"]),
                "exact checked predecessor feature values required",
            )
            require(
                (collection == "training_rows" and type(row["label"]) is bool)
                or (collection == "unverified_rows" and row["label"] is None),
                "original verified and unknown denominators required",
            )
            if collection == "unverified_rows":
                require(
                    row["cost_target"] is None
                    and cost_target(row["cost_repetitions"]) is None
                    and label_from_repetitions(row["cost_repetitions"])["label"]
                    is None,
                    "original unknown cost denominator required",
                )
    require(
        all(
            type(training[key]) is int and training[key] >= 0
            for key in ("verified_positive_count", "verified_negative_count")
        )
        and training["verified_positive_count"]
        == sum(row["label"] is True for row in training["training_rows"])
        and training["verified_negative_count"]
        == sum(row["label"] is False for row in training["training_rows"]),
        "complete original verified label counts required",
    )
    unbound, receipt = _fit_cost_gate(training, _UnboundPriorWorkGate)
    payload = dict(unbound._payload)
    payload["seed_policy_hash"] = training["seed_policy_hash"]
    payload.pop("policy_hash")
    payload["policy_hash"] = _sha(_bytes(payload))
    gate = PriorWorkCostMarginGate(_bytes(payload).decode())
    receipt.update(
        policy_hash=gate.policy_hash,
        seed_policy_hash=gate.seed_policy_hash,
        feature_profile=PRIOR_WORK_PROFILE,
        predecessor_counter_authenticity_established=False,
        historical_training_admitted=False,
        online_extraction_cost_in_target=False,
        fit_wall_ns=perf_counter_ns() - started,
    )
    return gate, receipt


def prior_work_guard_binding(gate, *, policy, model_features, excluded_case_ids):
    """Return the selector's exact four-field factory result after strict binds."""
    require(
        type(gate) is PriorWorkCostMarginGate and type(policy) is RCControlSeedPolicy,
        "exact immutable gate and seed policies required",
    )
    require(
        type(excluded_case_ids) is tuple
        and excluded_case_ids == gate.excluded_case_ids
        and gate.seed_policy_hash == policy.policy_hash,
        "actual fold seed policy and exclusion binding required",
    )
    require(
        type(model_features) is FiberFrameWarmStartModelFeatures,
        "exact typed model features required",
    )
    seed = policy.to_dict()
    require(
        seed["model_context_hash"] == model_features.context_hash
        and tuple(seed["model_feature_names"]) == model_features.feature_names,
        "seed policy model feature binding required",
    )
    return dict(
        guard=gate.guard(model_features),
        guard_identity=gate.policy_hash,
        seed_policy_hash=gate.seed_policy_hash,
        excluded_case_ids=gate.excluded_case_ids,
    )


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _hash_roster(values, *, nonempty):
    require(
        type(values) is list and (bool(values) or not nonempty),
        "exact declared sample hash roster required",
    )
    for value in values:
        _hash(value)
    require(len(set(values)) == len(values), "unique declared sample hashes required")
    return values


@dataclass(frozen=True)
class FullTrainingPriorWorkCostMarginGate(PriorWorkCostMarginGate):
    """Full-scope gate bound to the destination seed and OOF teacher roster.

    This distinct decoder never fabricates an outer group or an exclusion.
    Recorded consistency is not original-counter or operator attestation.
    """

    _schema = FULL_TRAINING_GATE_SCHEMA

    def __post_init__(self):
        require(type(self._json) is str, "gate JSON required")
        payload = strict_json_object_bytes(
            self._json.encode(), maximum_bytes=1024 * 1024
        )
        require(
            set(payload)
            == {
                "schema_version",
                "feature_profile",
                "feature_names",
                "mean",
                "scale",
                "minimum",
                "maximum",
                "weights",
                "ridge",
                "threshold",
                "excluded_case_ids",
                "training_sample_hashes",
                "positive_count",
                "negative_count",
                "training_rows_hash",
                "policy_hash",
                "training_scope",
                "cost_target_profile",
                "seed_policy_hash",
                "teacher_roster_hash",
                "declared_training_sample_hashes",
                "unverified_sample_hashes",
                "unverified_count",
            },
            "exact full-training gate fields required",
        )
        require(
            payload["schema_version"] == self._schema
            and payload["feature_profile"] == PRIOR_WORK_PROFILE
            and payload["cost_target_profile"] == TARGET_PROFILE
            and payload["training_scope"] == "declared_training_only"
            and type(payload["excluded_case_ids"]) is list
            and payload["excluded_case_ids"] == []
            and type(payload["ridge"]) is float
            and payload["ridge"] == 1.0
            and type(payload["threshold"]) is float
            and payload["threshold"] == 0.01,
            "fixed full-training scope and cost profile required",
        )
        for key in (
            "seed_policy_hash",
            "teacher_roster_hash",
            "training_rows_hash",
            "policy_hash",
        ):
            _hash(payload[key])
        require(
            payload["policy_hash"]
            == _sha(
                _bytes(
                    {
                        key: value
                        for key, value in payload.items()
                        if key != "policy_hash"
                    }
                )
            ),
            "gate hash mismatch",
        )
        names = payload["feature_names"]
        require(
            type(names) is list
            and names
            and all(type(name) is str and name for name in names)
            and len(set(names)) == len(names),
            "unique feature names required",
        )
        _feature_layout(names)
        for key in ("mean", "scale", "minimum", "maximum", "weights"):
            values = payload[key]
            require(
                type(values) is list
                and len(values) == len(names) + (key == "weights")
                and all(_finite_number(value) for value in values),
                "finite aligned full-training gate arrays required",
            )
        require(
            all(value > 0 for value in payload["scale"])
            and all(
                low <= center <= high
                for low, center, high in zip(
                    payload["minimum"], payload["mean"], payload["maximum"]
                )
            ),
            "valid gate normalization required",
        )
        declared = _hash_roster(
            payload["declared_training_sample_hashes"], nonempty=True
        )
        known = _hash_roster(payload["training_sample_hashes"], nonempty=True)
        unknown = _hash_roster(payload["unverified_sample_hashes"], nonempty=False)
        require(
            not (set(known) & set(unknown))
            and set(declared) == set(known) | set(unknown)
            and known == [value for value in declared if value in set(known)]
            and unknown == [value for value in declared if value in set(unknown)],
            "complete ordered known and unknown training coverage required",
        )
        require(
            all(
                type(payload[key]) is int and payload[key] >= 0
                for key in ("positive_count", "negative_count", "unverified_count")
            )
            and payload["positive_count"] + payload["negative_count"] == len(known)
            and payload["unverified_count"] == len(unknown),
            "complete full-training known and unknown counts required",
        )
        object.__setattr__(
            self,
            "_payload",
            MappingProxyType(
                {
                    key: tuple(value) if type(value) is list else value
                    for key, value in payload.items()
                }
            ),
        )

    def to_dict(self):
        return strict_json_object_bytes(self._json.encode(), maximum_bytes=1024 * 1024)


def fit_full_training_prior_work_cost_gate(training):
    """Fit checked training-only rows using fixed, original measured targets.

    The caller authenticates original teacher/complement/fit/label artifacts.
    Unknown targets remain in the declared denominator and artifact identity.
    """
    started = perf_counter_ns()
    required = {
        "schema_version",
        "training_scope",
        "excluded_case_ids",
        "feature_profile",
        "feature_names",
        "cost_target_profile",
        "training_rows",
        "unverified_rows",
        "verified_positive_count",
        "verified_negative_count",
        "normalization_scope",
        "gate_fitted",
        "independent_evaluation",
        "prior_work_join_profile",
        "seed_policy_hash",
        "teacher_roster_hash",
        "declared_training_sample_hashes",
    }
    require(
        type(training) is dict
        and set(training) == required
        and training["schema_version"] == FULL_TRAINING_PROFILE
        and training["training_scope"] == "declared_training_only"
        and type(training["excluded_case_ids"]) is list
        and training["excluded_case_ids"] == []
        and training["prior_work_join_profile"] == JOIN_PROFILE
        and training["feature_profile"] == PRIOR_WORK_PROFILE
        and training["cost_target_profile"] == TARGET_PROFILE,
        "exact checked full-training input scope required",
    )
    require(
        training["gate_fitted"] is False
        and training["independent_evaluation"] is False
        and type(training["normalization_scope"]) is str
        and training["normalization_scope"]
        and type(training["training_rows"]) is list
        and type(training["unverified_rows"]) is list,
        "original unpromoted full-training table required",
    )
    _hash(training["seed_policy_hash"])
    _hash(training["teacher_roster_hash"])
    declared = _hash_roster(training["declared_training_sample_hashes"], nonempty=True)
    _feature_layout(training["feature_names"])
    require(
        type(training["feature_names"]) is list, "exact training feature list required"
    )
    seen, known, unknown, targets = set(), [], [], []
    for collection, roster in (("training_rows", known), ("unverified_rows", unknown)):
        for row in training[collection]:
            require(
                type(row) is dict
                and set(row)
                == {
                    "case_id",
                    "source_sample_hash",
                    "parent_hash",
                    "seed_fit_index",
                    "policy_hash",
                    "values",
                    "label",
                    "cost_repetitions",
                    "cost_target",
                    "prior_work_context",
                    "model_features",
                },
                "exact causal training row fields required",
            )
            _row_key(row)
            sample = row["source_sample_hash"]
            require(
                sample not in seen
                and row["policy_hash"] != training["seed_policy_hash"],
                "unique original sample and out-of-fold teacher required",
            )
            seen.add(sample)
            roster.append(sample)
            _, _, features = _checked_row_inputs(row)
            require(
                _bytes(features["feature_names"]) == _bytes(training["feature_names"])
                and type(row["values"]) is list
                and all(_finite_number(value) for value in row["values"])
                and _bytes(features["values"]) == _bytes(row["values"]),
                "exact checked predecessor feature values required",
            )
            repetitions = row["cost_repetitions"]
            require(
                type(repetitions) is list and len(repetitions) == 3,
                "three original cost repetitions required",
            )
            for repetition in repetitions:
                require(
                    type(repetition) is dict
                    and set(repetition)
                    == {
                        "repetition",
                        "comparison_pass",
                        "decision",
                        "path_time_ratio",
                        "report_hash",
                    }
                    and type(repetition["repetition"]) is int
                    and type(repetition["comparison_pass"]) is bool
                    and type(repetition["decision"]) is str
                    and repetition["decision"]
                    and (
                        repetition["path_time_ratio"] is None
                        or (
                            _finite_number(repetition["path_time_ratio"])
                            and repetition["path_time_ratio"] > 0
                        )
                    ),
                    "typed original measured repetitions required",
                )
                _hash(repetition["report_hash"])
            target = cost_target(row["cost_repetitions"])
            label = label_from_repetitions(row["cost_repetitions"])["label"]
            if collection == "training_rows":
                require(
                    type(row["label"]) is bool
                    and row["label"] is label
                    and type(row["cost_target"]) is float
                    and _finite_number(row["cost_target"])
                    and target is not None
                    and row["cost_target"] == target,
                    "original verified measured full-training target required",
                )
                targets.append(target)
            else:
                require(
                    row["label"] is None
                    and label is None
                    and row["cost_target"] is None
                    and target is None,
                    "original unknown cost denominator required",
                )
    require(
        seen == set(declared)
        and known == [value for value in declared if value in set(known)]
        and unknown == [value for value in declared if value in set(unknown)],
        "complete ordered declared training coverage required",
    )
    require(
        all(
            type(training[key]) is int and training[key] >= 0
            for key in ("verified_positive_count", "verified_negative_count")
        )
        and training["verified_positive_count"]
        == sum(row["label"] is True for row in training["training_rows"])
        and training["verified_negative_count"]
        == sum(row["label"] is False for row in training["training_rows"]),
        "complete original verified label counts required",
    )
    scope = dict(
        training_scope=training["training_scope"],
        cost_target_profile=TARGET_PROFILE,
        seed_policy_hash=training["seed_policy_hash"],
        teacher_roster_hash=training["teacher_roster_hash"],
        declared_training_sample_hashes=list(declared),
        unverified_sample_hashes=unknown,
        unverified_count=len(unknown),
    )
    gate, receipt = _fit_gate(
        training, targets, FullTrainingPriorWorkCostMarginGate, scope_fields=scope
    )
    receipt.update(
        training_scope=training["training_scope"],
        seed_policy_hash=gate.seed_policy_hash,
        teacher_roster_hash=training["teacher_roster_hash"],
        declared_rows=len(declared),
        declared_training_sample_hashes=list(declared),
        unverified_sample_hashes=list(unknown),
        target_profile=TARGET_PROFILE,
        feature_profile=PRIOR_WORK_PROFILE,
        fit_completed=True,
        unknown_work=False,
        gate_cost_in_training_target=False,
        predecessor_counter_authenticity_established=False,
        historical_training_admitted=False,
        online_extraction_cost_in_target=False,
        independent_evaluation=False,
        fit_wall_ns=perf_counter_ns() - started,
    )
    return gate, receipt


def full_training_prior_work_guard_binding(gate, *, policy, model_features):
    """Bind the full gate to its actual destination seed, without fake folds."""
    require(
        type(gate) is FullTrainingPriorWorkCostMarginGate
        and type(policy) is RCControlSeedPolicy
        and type(model_features) is FiberFrameWarmStartModelFeatures,
        "exact immutable full gate, seed and model features required",
    )
    seed = policy.to_dict()
    require(
        gate.seed_policy_hash == policy.policy_hash
        and tuple(seed["training_sample_hashes"])
        == gate._payload["declared_training_sample_hashes"]
        and seed["model_context_hash"] == model_features.context_hash
        and tuple(seed["model_feature_names"]) == model_features.feature_names,
        "actual full-training seed, sample roster and model binding required",
    )
    return dict(
        guard=gate.guard(model_features),
        guard_identity=gate.policy_hash,
        seed_policy_hash=gate.seed_policy_hash,
        excluded_case_ids=(),
    )
